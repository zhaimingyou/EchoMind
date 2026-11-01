"""Pluggable provider contracts for EchoMind's micro-kernel architecture."""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Sequence, runtime_checkable


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
class VADProvider(Protocol):
    """Protocol for frame-level Voice Activity Detection and speech segmentation."""

    def accept_pcm16_bytes(self, raw_bytes: bytes) -> List[Any]:
        """Accept raw 16-bit mono PCM bytes and return completed speech chunks."""
        ...

    def accept_float_samples(self, samples: Sequence[float]) -> List[Any]:
        """Accept normalized float samples and return completed speech chunks."""
        ...

    def flush(self) -> List[Any]:
        """Flush any buffered speech at stream end."""
        ...


@runtime_checkable
class ASRProvider(Protocol):
    """Protocol for Speech-to-Text engines (Sherpa-ONNX, Whisper.cpp, FunASR, etc.)."""

    def transcribe(
        self,
        samples: Sequence[float],
        sample_rate: int = 16000,
        hint_text: Optional[str] = None,
    ) -> TranscriptionResult:
        """Transcribe a mono float audio segment."""
        ...


@runtime_checkable
class SpeakerProvider(Protocol):
    """Protocol for Speaker Embedding & Diarization engines (3D-Speaker, WeSpeaker, etc.)."""

    def extract_embedding(self, samples: Sequence[float], sample_rate: int = 16000) -> Sequence[float]:
        """Extract L2-normalized speaker embedding vector."""
        ...

    def enroll_host_voice(self, samples: Sequence[float], sample_rate: int = 16000) -> List[float]:
        """Enroll the device owner's voiceprint and persist it."""
        ...

    def has_host_voiceprint(self) -> bool:
        """Return whether a host voiceprint is currently enrolled."""
        ...

    def reset_guest_pool(self, device_id: Optional[str] = None) -> None:
        """Reset online guest speaker centroids when an Episode closes."""
        ...

    def identify_speaker(
        self,
        samples: Sequence[float],
        duration_ms: Optional[int] = None,
        device_id: str = "default_mic",
        sample_rate: int = 16000,
        now_ts: Optional[float] = None,
    ) -> SpeakerMatchResult:
        """Identify speaker role ('HOST', 'GUEST_1', ..., or 'UNKNOWN')."""
        ...


@runtime_checkable
class ExtractorProvider(Protocol):
    """Protocol for Cognitive Memory Extraction engines (LiteLLM, Heuristic, Vertical Domain Agents)."""

    async def extract_episode(self, utterances: List[Any]) -> Any:
        """Extract structured episodic summary, todos, clues, and fact operations."""
        ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Protocol for text embedding engines (Local N-gram, ONNX BGE, OpenAI Embedding, etc.)."""

    def embed_text(self, text: str) -> List[float]:
        """Compute L2-normalized vector embedding for a text string."""
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
