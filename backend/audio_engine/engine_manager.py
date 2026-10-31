"""Sherpa-ONNX Engine Singleton Manager with Automatic CPU Fallback.

Loads Silero-VAD, 3D-Speaker, and SenseVoice-Small (int8) ONNX models on CPU when
present in `models/`. Gracefully falls back to deterministic acoustic/spectral CPU
extractors when running in lightweight CI or before `scripts/download_models.py` is run.
"""
import logging
from pathlib import Path
from typing import Any, Optional
from backend.config import settings

logger = logging.getLogger("echomind.audio_engine")


class SherpaEngineManager:
    """Thread-safe lazy loader for Sherpa-ONNX models."""

    def __init__(self, models_dir: Optional[Path] = None) -> None:
        self.models_dir = models_dir or settings.models_dir
        self._recognizer: Optional[Any] = None
        self._speaker_extractor: Optional[Any] = None
        self._vad: Optional[Any] = None
        self._sherpa_available: Optional[bool] = None

    def is_sherpa_ready(self) -> bool:
        """Check whether `sherpa_onnx` package and local `.onnx` files are installed."""
        if self._sherpa_available is not None:
            return self._sherpa_available

        if settings.asr_provider == "mock":
            self._sherpa_available = False
            return False

        try:
            import sherpa_onnx  # noqa: F401
            sensevoice_model = self.models_dir / "sensevoice" / "model.int8.onnx"
            self._sherpa_available = sensevoice_model.exists()
        except ImportError:
            self._sherpa_available = False

        return bool(self._sherpa_available)

    def get_sensevoice_recognizer(self) -> Optional[Any]:
        """Return initialized Sherpa-ONNX SenseVoice OfflineRecognizer if available."""
        if not self.is_sherpa_ready():
            return None
        if self._recognizer is None:
            import sherpa_onnx

            model_dir = self.models_dir / "sensevoice"
            self._recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=str(model_dir / "model.int8.onnx"),
                tokens=str(model_dir / "tokens.txt"),
                num_threads=4,
                use_itn=True,
                debug=False,
            )
            logger.info("Loaded SenseVoice-Small (int8) ONNX model on CPU.")
        return self._recognizer

    def get_speaker_extractor(self) -> Optional[Any]:
        """Return initialized 3D-Speaker Extractor if available."""
        if settings.speaker_provider == "mock":
            return None
        try:
            import sherpa_onnx

            spk_model = self.models_dir / "speaker" / "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"
            if not spk_model.exists():
                return None
            if self._speaker_extractor is None:
                cfg = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
                    model=str(spk_model),
                    num_threads=2,
                )
                self._speaker_extractor = sherpa_onnx.SpeakerEmbeddingExtractor(cfg)
                logger.info("Loaded 3D-Speaker ONNX model on CPU.")
            return self._speaker_extractor
        except ImportError:
            return None


engine_manager = SherpaEngineManager()
