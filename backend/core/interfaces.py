"""Pluggable provider contracts for EchoMind's micro-kernel architecture."""
from dataclasses import dataclass, field
from typing import Any, Dict, Protocol, Sequence, runtime_checkable


@dataclass
class TranscriptionResult:
    """Structured output from an ASR provider (e.g., SenseVoice-Small)."""

    clean_text: str
    raw_text: str = ""
    lang: str = "zh"
    emotion_tag: str = "NEUTRAL"
    acoustic_event: str = "NONE"
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SpeakerMatchResult:
    """Structured output from the Speaker Identification & Clustering engine."""

    speaker_role: str  # "HOST", "GUEST_1", "GUEST_2", ..., or "UNKNOWN"
    similarity_score: float
    is_short_inherited: bool = False


@runtime_checkable
class ASRProvider(Protocol):
    """Protocol for Speech-to-Text engines (Sherpa-ONNX, Whisper.cpp, FunASR, etc.)."""

    def transcribe(self, samples: Sequence[float], sample_rate: int = 16000) -> TranscriptionResult:
        """Transcribe a mono float audio segment."""
        ...


@runtime_checkable
class SpeakerProvider(Protocol):
    """Protocol for Speaker Embedding extraction (3D-Speaker, WeSpeaker, etc.)."""

    def extract_embedding(self, samples: Sequence[float], sample_rate: int = 16000) -> Sequence[float]:
        """Extract L2-normalized speaker embedding vector."""
        ...


@runtime_checkable
class IngestAdapter(Protocol):
    """Protocol for audio or multi-modal context ingestion adapters."""

    async def start(self) -> None:
        """Start listening for incoming streams or events."""
        ...

    async def stop(self) -> None:
        """Gracefully stop the adapter."""
        ...
