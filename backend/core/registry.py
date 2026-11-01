"""Centralized ProviderRegistry for EchoMind's Pluggable Micro-Kernel.

Allows secondary developers and plugins to register and hot-swap:
1. `ASRProvider` (Speech-to-Text: SenseVoice, Whisper.cpp, FunASR, Cloud ASR)
2. `SpeakerProvider` (Voiceprint & Diarization: 3D-Speaker, Spectral, WeSpeaker)
3. `VADProvider` (Voice Activity Detection: Silero-VAD, RMS Energy)
4. `ExtractorProvider` (Cognitive LLM / Heuristic / Vertical Domain Agent)
5. `EmbeddingProvider` (Vector Embedding: Local N-gram, ONNX BGE, OpenAI)
6. `IngestAdapter` (Hardware / Stream / File Watchers)
"""
import logging
from typing import Any, Callable, Dict, List, Optional
from backend.config import settings
from backend.core.interfaces import (
    ASRProvider,
    EmbeddingProvider,
    ExtractorProvider,
    IngestAdapter,
    SpeakerProvider,
    VADProvider,
)

logger = logging.getLogger("echomind.registry")


class ProviderRegistry:
    """Manages registration, lookup, and hot-swapping of core AI and hardware providers."""

    def __init__(self) -> None:
        self._asr: Dict[str, ASRProvider] = {}
        self._speaker: Dict[str, SpeakerProvider] = {}
        self._vad_factories: Dict[str, Callable[..., VADProvider]] = {}
        self._extractors: Dict[str, ExtractorProvider] = {}
        self._embeddings: Dict[str, EmbeddingProvider] = {}
        self._ingest_adapters: Dict[str, IngestAdapter] = {}

        self._active_asr: Optional[str] = None
        self._active_speaker: Optional[str] = None
        self._active_vad: Optional[str] = None
        self._active_extractor: Optional[str] = None
        self._active_embedding: Optional[str] = None
        self._defaults_initialized: bool = False

    def _ensure_defaults(self) -> None:
        if self._defaults_initialized:
            return
        self._defaults_initialized = True

        from backend.audio_engine.speaker_id import get_speaker_identifier
        from backend.audio_engine.transcriber import get_transcriber
        from backend.audio_engine.vad_buffer import VADStreamBuffer
        from backend.memory_core.extractor import get_extractor
        from backend.storage.vector_store import LocalNgramEmbeddingProvider

        default_asr = get_transcriber()
        self._asr.setdefault("sherpa_onnx", default_asr)
        self._asr.setdefault("sensevoice", default_asr)
        self._asr.setdefault("default", default_asr)

        default_spk = get_speaker_identifier()
        self._speaker.setdefault("sherpa_onnx", default_spk)
        self._speaker.setdefault("3dspeaker", default_spk)
        self._speaker.setdefault("default", default_spk)

        self._vad_factories.setdefault("rms_energy", lambda **kw: VADStreamBuffer(**kw))
        self._vad_factories.setdefault("silero_onnx", lambda **kw: VADStreamBuffer(**kw))
        self._vad_factories.setdefault("default", lambda **kw: VADStreamBuffer(**kw))

        default_ext = get_extractor()
        self._extractors.setdefault("default", default_ext)
        self._extractors.setdefault("litellm", default_ext)
        self._extractors.setdefault("heuristic", default_ext)

        default_emb = LocalNgramEmbeddingProvider()
        self._embeddings.setdefault("local_ngram", default_emb)
        self._embeddings.setdefault("default", default_emb)

    # --- 1. ASR Provider ---
    def register_asr(self, name: str, provider: ASRProvider, set_default: bool = False) -> None:
        self._ensure_defaults()
        self._asr[name] = provider
        if set_default:
            self._active_asr = name
        logger.info("Registered ASRProvider '%s' (set_default=%s)", name, set_default)

    def get_asr(self, name: Optional[str] = None) -> ASRProvider:
        self._ensure_defaults()
        target = name or self._active_asr or settings.asr_provider
        if target in self._asr:
            return self._asr[target]
        logger.warning("ASRProvider '%s' not found, falling back to 'default'", target)
        return self._asr["default"]

    # --- 2. Speaker Provider ---
    def register_speaker(self, name: str, provider: SpeakerProvider, set_default: bool = False) -> None:
        self._ensure_defaults()
        self._speaker[name] = provider
        if set_default:
            self._active_speaker = name
        logger.info("Registered SpeakerProvider '%s' (set_default=%s)", name, set_default)

    def get_speaker(self, name: Optional[str] = None) -> SpeakerProvider:
        self._ensure_defaults()
        target = name or self._active_speaker or settings.speaker_provider
        if target in self._speaker:
            return self._speaker[target]
        logger.warning("SpeakerProvider '%s' not found, falling back to 'default'", target)
        return self._speaker["default"]

    # --- 3. VAD Provider Factory ---
    def register_vad_factory(
        self, name: str, factory: Callable[..., VADProvider], set_default: bool = False
    ) -> None:
        self._ensure_defaults()
        self._vad_factories[name] = factory
        if set_default:
            self._active_vad = name
        logger.info("Registered VADProvider factory '%s' (set_default=%s)", name, set_default)

    def create_vad(self, name: Optional[str] = None, **kwargs: Any) -> VADProvider:
        self._ensure_defaults()
        target = name or self._active_vad or settings.vad_provider
        factory = self._vad_factories.get(target) or self._vad_factories["default"]
        return factory(**kwargs)

    # --- 4. Cognitive Extractor Provider ---
    def register_extractor(
        self, name: str, provider: ExtractorProvider, set_default: bool = False
    ) -> None:
        self._ensure_defaults()
        self._extractors[name] = provider
        if set_default:
            self._active_extractor = name
        logger.info("Registered ExtractorProvider '%s' (set_default=%s)", name, set_default)

    def get_extractor(self, name: Optional[str] = None) -> ExtractorProvider:
        self._ensure_defaults()
        target = name or self._active_extractor or settings.extractor_provider
        if target in self._extractors:
            return self._extractors[target]
        logger.warning("ExtractorProvider '%s' not found, falling back to 'default'", target)
        return self._extractors["default"]

    # --- 5. Embedding Provider ---
    def register_embedding(
        self, name: str, provider: EmbeddingProvider, set_default: bool = False
    ) -> None:
        self._ensure_defaults()
        self._embeddings[name] = provider
        if set_default:
            self._active_embedding = name
        logger.info("Registered EmbeddingProvider '%s' (set_default=%s)", name, set_default)

    def get_embedding(self, name: Optional[str] = None) -> EmbeddingProvider:
        self._ensure_defaults()
        target = name or self._active_embedding or settings.embedding_provider
        if target in self._embeddings:
            return self._embeddings[target]
        logger.warning("EmbeddingProvider '%s' not found, falling back to 'default'", target)
        return self._embeddings["default"]

    # --- 6. Ingest Adapters ---
    def register_ingest_adapter(self, name: str, adapter: IngestAdapter) -> None:
        self._ingest_adapters[name] = adapter
        logger.info("Registered IngestAdapter '%s'", name)

    def get_ingest_adapters(self) -> Dict[str, IngestAdapter]:
        return dict(self._ingest_adapters)

    def list_providers(self) -> Dict[str, Any]:
        """Return registered providers and currently active selections."""
        self._ensure_defaults()
        return {
            "active": {
                "asr": self._active_asr or settings.asr_provider,
                "speaker": self._active_speaker or settings.speaker_provider,
                "vad": self._active_vad or settings.vad_provider,
                "extractor": self._active_extractor or settings.extractor_provider,
                "embedding": self._active_embedding or settings.embedding_provider,
            },
            "registered": {
                "asr": sorted(self._asr.keys()),
                "speaker": sorted(self._speaker.keys()),
                "vad": sorted(self._vad_factories.keys()),
                "extractor": sorted(self._extractors.keys()),
                "embedding": sorted(self._embeddings.keys()),
                "ingest_adapters": sorted(self._ingest_adapters.keys()),
            },
        }


# Global singleton registry
registry = ProviderRegistry()
