"""Local Audio Inbox Watcher (Plaud Note / Voice Recorder / iPhone Shortcut Sync).

Monitors `data/audio_inbox/` for dropped `.wav` or `.txt` transcript files,
processes them through the pluggable VAD + SpeakerProvider + ASRProvider + Episode Segmenter pipeline,
and archives processed files into `data/audio_archive/`.
"""
import logging
from pathlib import Path
import shutil
from typing import List, Optional
import wave
from backend.config import settings
from backend.core.event_bus import event_bus
from backend.core.registry import registry
from backend.memory_core.segmenter import get_segmenter
from backend.storage.database import get_storage
from backend.storage.models import Episode, Utterance

logger = logging.getLogger("echomind.file_watcher")


def _read_wav_mono_float(file_path: Path) -> tuple[List[float], int]:
    """Read `.wav` file using soundfile (if installed) or Python stdlib `wave` fallback."""
    try:
        import soundfile as sf

        samples, sr = sf.read(str(file_path), dtype="float32")
        if samples.ndim > 1:
            samples = samples[:, 0]
        return list(samples), int(sr)
    except ImportError:
        with wave.open(str(file_path), "rb") as wf:
            sr = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)
            from array import array

            pcm16 = array("h")
            pcm16.frombytes(raw)
            return [s / 32768.0 for s in pcm16], sr


class AudioInboxProcessor:
    """Processes audio (`.wav`) and transcript (`.txt`) files dropped into `data/audio_inbox/`."""

    def __init__(
        self,
        inbox_dir: Optional[Path] = None,
        archive_dir: Optional[Path] = None,
        storage=None,
        segmenter=None,
        bus=None,
    ) -> None:
        self.inbox_dir = inbox_dir or settings.audio_inbox_dir
        self.archive_dir = archive_dir or settings.audio_archive_dir
        self._storage = storage
        self._segmenter = segmenter
        self._bus = bus or event_bus
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    @property
    def storage(self):
        return self._storage or get_storage()

    @property
    def segmenter(self):
        return self._segmenter or get_segmenter()

    async def _ingest_audio_samples(self, samples: List[float], duration_ms: int, device_id: str, sr: int) -> None:
        spk_res = registry.get_speaker().identify_speaker(
            samples=samples,
            duration_ms=duration_ms,
            device_id=device_id,
            sample_rate=sr,
        )
        asr_res = registry.get_asr().transcribe(samples=samples, sample_rate=sr)
        utt = Utterance(
            duration_ms=duration_ms,
            speaker_role=spk_res.speaker_role,
            speaker_score=spk_res.similarity_score,
            emotion_tag=asr_res.emotion_tag,
            acoustic_event=asr_res.acoustic_event,
            text_content=asr_res.clean_text,
            device_id=device_id,
        )
        filtered = await self._bus.apply_filters("utterance.before_save", utt)
        if filtered is not None:
            self.storage.insert_utterance(filtered)
            await self._bus.publish("utterance.created", filtered.model_dump())

    async def process_file(self, file_path: Path) -> Optional[Episode]:
        """Process a single `.wav` or `.txt` file and trigger Episode extraction."""
        if not file_path.exists():
            return None

        device_id = f"inbox_{file_path.stem}"
        suffix = file_path.suffix.lower()

        if suffix == ".wav":
            samples, sr = _read_wav_mono_float(file_path)
            vad = registry.create_vad(sample_rate=sr)
            chunks = vad.accept_float_samples(samples) + vad.flush()
            if not chunks and len(samples) > 0:
                await self._ingest_audio_samples(
                    samples=samples,
                    duration_ms=int(len(samples) * 1000 / max(sr, 1)),
                    device_id=device_id,
                    sr=sr,
                )
            else:
                for ch in chunks:
                    await self._ingest_audio_samples(
                        samples=ch.samples,
                        duration_ms=ch.duration_ms,
                        device_id=device_id,
                        sr=sr,
                    )
        elif suffix == ".txt":
            raw_text = file_path.read_text(encoding="utf-8")
            for line in raw_text.splitlines():
                clean = line.strip()
                if not clean:
                    continue
                role = "HOST"
                if clean.startswith("[GUEST") and "]" in clean:
                    role = clean[1 : clean.index("]")]
                    clean = clean[clean.index("]") + 1 :].strip().lstrip(":： ")
                elif clean.startswith("[HOST]"):
                    clean = clean[6:].strip().lstrip(":： ")
                utt = Utterance(
                    text_content=clean,
                    speaker_role=role,
                    device_id=device_id,
                )
                filtered = await self._bus.apply_filters("utterance.before_save", utt)
                if filtered is not None:
                    self.storage.insert_utterance(filtered)
                    await self._bus.publish("utterance.created", filtered.model_dump())

        dest = self.archive_dir / file_path.name
        shutil.move(str(file_path), str(dest))
        logger.info("Processed and archived inbox file: %s -> %s", file_path.name, dest)
        return await self.segmenter.inspect_and_segment(force_flush=True)

    async def scan_inbox_once(self) -> List[Episode]:
        """Scan `data/audio_inbox/` for any pending `.wav` or `.txt` files and process them."""
        created: List[Episode] = []
        candidates = sorted(list(self.inbox_dir.glob("*.wav")) + list(self.inbox_dir.glob("*.txt")))
        for f in candidates:
            ep = await self.process_file(f)
            if ep:
                created.append(ep)
        return created


_default_inbox: Optional[AudioInboxProcessor] = None


def get_inbox_processor() -> AudioInboxProcessor:
    global _default_inbox
    if _default_inbox is None:
        _default_inbox = AudioInboxProcessor()
    return _default_inbox
