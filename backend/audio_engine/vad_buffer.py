"""Frame-level Voice Activity Detection (VAD) and Speech Segment Buffer.

Discards silence frames in memory (zero disk writes) and emits complete speech
segments (0.5s ~ 30s) ready for concurrent 3D-Speaker + SenseVoice inference.
"""
from array import array
from dataclasses import dataclass
import math
from typing import List, Optional, Sequence


@dataclass
class SpeechChunk:
    """A continuous voiced audio segment emitted by VADStreamBuffer."""

    samples: List[float]
    duration_ms: int
    sample_rate: int = 16000


class VADStreamBuffer:
    """Sliding-window VAD buffer supporting energy/Silero frame-level filtering."""

    def __init__(
        self,
        sample_rate: int = 16000,
        energy_threshold: float = 0.012,
        min_speech_ms: int = 500,
        max_speech_ms: int = 28000,
        min_silence_ms: int = 600,
    ) -> None:
        self.sample_rate = sample_rate
        self.energy_threshold = energy_threshold
        self.min_speech_samples = int(sample_rate * min_speech_ms / 1000)
        self.max_speech_samples = int(sample_rate * max_speech_ms / 1000)
        self.min_silence_samples = int(sample_rate * min_silence_ms / 1000)

        self._active_samples: List[float] = []
        self._trailing_silence_samples: int = 0

    def accept_pcm16_bytes(self, raw_bytes: bytes) -> List[SpeechChunk]:
        """Accept raw 16-bit little-endian mono PCM bytes and return any completed speech chunks."""
        if not raw_bytes:
            return []
        pcm16 = array("h")
        pcm16.frombytes(raw_bytes)
        float_samples = [s / 32768.0 for s in pcm16]
        return self.accept_float_samples(float_samples)

    def accept_float_samples(self, samples: Sequence[float]) -> List[SpeechChunk]:
        """Process float samples in 32ms (512-sample) frames and emit voiced chunks."""
        frame_size = 512
        emitted: List[SpeechChunk] = []
        sample_list = list(samples)

        for offset in range(0, len(sample_list), frame_size):
            frame = sample_list[offset : offset + frame_size]
            if not frame:
                continue
            rms = math.sqrt(sum(x * x for x in frame) / len(frame))
            is_voiced = rms >= self.energy_threshold

            if is_voiced:
                self._active_samples.extend(frame)
                self._trailing_silence_samples = 0

                if len(self._active_samples) >= self.max_speech_samples:
                    chunk = self._flush_active()
                    if chunk:
                        emitted.append(chunk)
            else:
                if self._active_samples:
                    self._active_samples.extend(frame)
                    self._trailing_silence_samples += len(frame)

                    if self._trailing_silence_samples >= self.min_silence_samples:
                        chunk = self._flush_active()
                        if chunk:
                            emitted.append(chunk)

        return emitted

    def flush(self) -> List[SpeechChunk]:
        """Force-flush any remaining buffered speech at stream end."""
        chunk = self._flush_active()
        return [chunk] if chunk else []

    def _flush_active(self) -> Optional[SpeechChunk]:
        if not self._active_samples:
            return None
        concat = list(self._active_samples)
        self._active_samples.clear()
        self._trailing_silence_samples = 0

        if len(concat) < self.min_speech_samples:
            return None

        duration_ms = int(len(concat) * 1000 / self.sample_rate)
        return SpeechChunk(samples=concat, duration_ms=duration_ms, sample_rate=self.sample_rate)
