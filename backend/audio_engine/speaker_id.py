"""Host Voiceprint Anchoring, Short-Utterance Immunity, and Online Guest Clustering.

Implements the 3-tier speaker identification design from `specs/design.md`:
1. Short-Utterance Immunity (< 1.2s inherits recent speaker within 3.0s window)
2. Host Voiceprint Cosine Anchoring (>= 0.65 -> HOST, with EMA adaptation >= 0.80)
3. Online Guest Centroid Pool (>= 0.60 -> GUEST_i, otherwise allocates new GUEST_{k+1})
"""
from dataclasses import dataclass
import json
import math
from pathlib import Path
import time
from typing import Dict, List, Optional, Sequence, Tuple
from backend.audio_engine.engine_manager import engine_manager
from backend.config import settings
from backend.core.interfaces import SpeakerMatchResult


@dataclass
class _GuestCentroid:
    role: str
    vector: List[float]
    count: int = 1


class SpeakerIdentifier:
    """Manages Host voiceprint enrollment and real-time speaker diarization/clustering."""

    def __init__(
        self,
        voiceprint_path: Optional[Path] = None,
        host_threshold: Optional[float] = None,
        guest_threshold: Optional[float] = None,
        short_utterance_ms: Optional[int] = None,
        inherit_window_sec: Optional[float] = None,
    ) -> None:
        self.voiceprint_path = voiceprint_path or settings.voiceprint_path
        self.host_threshold = host_threshold if host_threshold is not None else settings.host_similarity_threshold
        self.guest_threshold = guest_threshold if guest_threshold is not None else settings.guest_cluster_threshold
        self.short_utterance_ms = (
            short_utterance_ms if short_utterance_ms is not None else settings.short_utterance_ms
        )
        self.inherit_window_sec = (
            inherit_window_sec if inherit_window_sec is not None else settings.inherit_speaker_window_sec
        )

        self._host_embedding: Optional[List[float]] = self._load_host_embedding()
        self._guest_pools: Dict[str, List[_GuestCentroid]] = {}
        self._last_device_speaker: Dict[str, Tuple[str, float, float]] = {}

    def _load_host_embedding(self) -> Optional[List[float]]:
        if self.voiceprint_path.exists():
            try:
                raw = json.loads(self.voiceprint_path.read_text(encoding="utf-8"))
                return self._l2_normalize([float(x) for x in raw])
            except Exception:
                return None
        return None

    @staticmethod
    def _l2_normalize(vec: Sequence[float]) -> List[float]:
        norm = math.sqrt(sum(float(x) * float(x) for x in vec))
        if norm < 1e-8:
            return [float(x) for x in vec]
        return [float(x) / norm for x in vec]

    @staticmethod
    def _dot(a: Sequence[float], b: Sequence[float]) -> float:
        return sum(float(x) * float(y) for x, y in zip(a, b))

    def extract_embedding(self, samples: Sequence[float], sample_rate: int = 16000) -> List[float]:
        """Extract a 192-d L2-normalized embedding via 3D-Speaker ONNX or spectral filterbank fallback."""
        extractor = engine_manager.get_speaker_extractor()
        if extractor is not None:
            stream = extractor.create_stream()
            stream.accept_waveform(sample_rate=sample_rate, waveform=list(samples))
            stream.input_finished()
            if extractor.is_ready(stream):
                emb = list(extractor.compute(stream))
                return self._l2_normalize(emb)

        return self._extract_spectral_embedding(samples, sample_rate=sample_rate, dim=192)

    def _extract_spectral_embedding(
        self, samples: Sequence[float], sample_rate: int = 16000, dim: int = 192
    ) -> List[float]:
        n = len(samples)
        if n == 0:
            return [0.0] * dim

        # Fast multi-frequency Goertzel / resonator filterbank across 192 pitch & formant bands (80Hz ~ 3200Hz)
        stride = max(1, n // 1024)
        sub = [float(samples[i]) for i in range(0, n, stride)][:1024]
        eff_sr = sample_rate / stride
        m = len(sub)

        feats: List[float] = []
        for b in range(dim):
            freq = 80.0 + (3120.0 * b) / max(dim - 1, 1)
            omega = 2.0 * math.pi * freq / max(eff_sr, 1.0)
            coeff = 2.0 * math.cos(omega)
            s1 = 0.0
            s2 = 0.0
            for x in sub:
                s0 = x + coeff * s1 - s2
                s2 = s1
                s1 = s0
            power = s1 * s1 + s2 * s2 - coeff * s1 * s2
            feats.append(math.sqrt(max(0.0, power / max(m, 1))))

        return self._l2_normalize(feats)

    def enroll_host_voice(self, samples: Sequence[float], sample_rate: int = 16000) -> List[float]:
        """Enroll the device owner's voiceprint and persist to disk."""
        emb = self.extract_embedding(samples, sample_rate=sample_rate)
        self.voiceprint_path.parent.mkdir(parents=True, exist_ok=True)
        self.voiceprint_path.write_text(json.dumps(emb), encoding="utf-8")
        self._host_embedding = emb
        return emb

    def has_host_voiceprint(self) -> bool:
        return self._host_embedding is not None

    def reset_guest_pool(self, device_id: Optional[str] = None) -> None:
        """Clear online guest centroids when an Episode closes."""
        if device_id:
            self._guest_pools.pop(device_id, None)
        else:
            self._guest_pools.clear()

    def identify_speaker(
        self,
        samples: Sequence[float],
        duration_ms: Optional[int] = None,
        device_id: str = "default_mic",
        sample_rate: int = 16000,
        now_ts: Optional[float] = None,
    ) -> SpeakerMatchResult:
        """Identify speaker role ('HOST', 'GUEST_1', 'GUEST_2', or 'UNKNOWN')."""
        now = now_ts if now_ts is not None else time.time()
        if duration_ms is None:
            duration_ms = int(len(samples) * 1000 / max(sample_rate, 1))

        # 1. Short-Utterance Immunity (< 1.2s)
        if duration_ms < self.short_utterance_ms:
            prev = self._last_device_speaker.get(device_id)
            if prev is not None and (now - prev[2]) <= self.inherit_window_sec:
                role, score, _ = prev
                self._last_device_speaker[device_id] = (role, score, now)
                return SpeakerMatchResult(
                    speaker_role=role,
                    similarity_score=score,
                    is_short_inherited=True,
                )
            return SpeakerMatchResult(
                speaker_role="UNKNOWN",
                similarity_score=0.0,
                is_short_inherited=True,
            )

        curr_emb = self.extract_embedding(samples, sample_rate=sample_rate)

        if self._host_embedding is None:
            self._last_device_speaker[device_id] = ("HOST", 1.0, now)
            return SpeakerMatchResult(speaker_role="HOST", similarity_score=1.0)

        # 2. Host Voiceprint Cosine Similarity Check
        host_score = self._dot(curr_emb, self._host_embedding)
        if host_score >= self.host_threshold:
            if host_score >= 0.80:
                blended = [0.98 * h + 0.02 * c for h, c in zip(self._host_embedding, curr_emb)]
                self._host_embedding = self._l2_normalize(blended)
            self._last_device_speaker[device_id] = ("HOST", round(host_score, 4), now)
            return SpeakerMatchResult(speaker_role="HOST", similarity_score=round(host_score, 4))

        # 3. Online Guest Centroid Pool Clustering
        pool = self._guest_pools.setdefault(device_id, [])
        best_idx = -1
        best_guest_sim = -1.0
        for idx, centroid in enumerate(pool):
            sim = self._dot(curr_emb, centroid.vector)
            if sim > best_guest_sim:
                best_guest_sim = sim
                best_idx = idx

        if best_idx >= 0 and best_guest_sim >= self.guest_threshold:
            matched = pool[best_idx]
            updated_vec = [matched.count * m + c for m, c in zip(matched.vector, curr_emb)]
            matched.vector = self._l2_normalize(updated_vec)
            matched.count += 1
            role = matched.role
        else:
            if len(pool) < settings.max_guest_centroids:
                role = f"GUEST_{len(pool) + 1}"
                pool.append(_GuestCentroid(role=role, vector=curr_emb, count=1))
            else:
                role = pool[max(best_idx, 0)].role

        self._last_device_speaker[device_id] = (role, round(host_score, 4), now)
        return SpeakerMatchResult(speaker_role=role, similarity_score=round(host_score, 4))


_default_speaker_id: Optional[SpeakerIdentifier] = None


def get_speaker_identifier() -> SpeakerIdentifier:
    global _default_speaker_id
    if _default_speaker_id is None:
        _default_speaker_id = SpeakerIdentifier()
    return _default_speaker_id
