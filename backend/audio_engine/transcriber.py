"""SenseVoice-Small (int8) Transcriber and Emotion/Acoustic Event Tag Parser."""
import re
from typing import Optional, Sequence
from backend.audio_engine.engine_manager import engine_manager
from backend.core.interfaces import TranscriptionResult

_TAG_PATTERN = re.compile(r"<\|([^|>]+)\|>")

_EMOTION_MAP = {
    "HAPPY": "HAPPY",
    "SAD": "SAD",
    "ANGRY": "ANGRY",
    "NEUTRAL": "NEUTRAL",
    "FEARFUL": "FEARFUL",
    "DISGUSTED": "ANGRY",
    "SURPRISED": "HAPPY",
}

_EVENT_MAP = {
    "LAUGHTER": "LAUGHTER",
    "SIGH": "SIGH",
    "APPLAUSE": "APPLAUSE",
    "COUGH": "COUGH",
    "CRY": "SAD",
}

_LANG_CODES = {"zh", "en", "yue", "ja", "ko", "nospeech"}


def parse_sensevoice_output(raw_text: str) -> TranscriptionResult:
    """Parse SenseVoice special tokens (e.g. `<|zh|><|HAPPY|><|Laughter|>今天这个方案太棒了`)."""
    tags = _TAG_PATTERN.findall(raw_text)
    clean_text = _TAG_PATTERN.sub("", raw_text).strip()

    lang = "zh"
    emotion_tag = "NEUTRAL"
    acoustic_event = "NONE"

    for tag in tags:
        low = tag.lower()
        up = tag.upper()
        if low in _LANG_CODES:
            lang = low
        elif up in _EMOTION_MAP:
            emotion_tag = _EMOTION_MAP[up]
        elif up in _EVENT_MAP:
            acoustic_event = _EVENT_MAP[up]

    if acoustic_event == "NONE":
        if "哈哈" in clean_text or "[笑]" in clean_text:
            acoustic_event = "LAUGHTER"
            if emotion_tag == "NEUTRAL":
                emotion_tag = "HAPPY"
        elif "唉" in clean_text or "[叹气]" in clean_text:
            acoustic_event = "SIGH"

    return TranscriptionResult(
        clean_text=clean_text,
        raw_text=raw_text,
        lang=lang,
        emotion_tag=emotion_tag,
        acoustic_event=acoustic_event,
    )


class SenseVoiceTranscriber:
    """Pure-CPU SenseVoice ONNX wrapper with fallback support for simulated audio."""

    def transcribe(
        self,
        samples: Sequence[float],
        sample_rate: int = 16000,
        hint_text: Optional[str] = None,
    ) -> TranscriptionResult:
        """Transcribe audio samples using Sherpa-ONNX SenseVoice or fallback hint."""
        if hint_text is not None:
            return parse_sensevoice_output(hint_text)

        recognizer = engine_manager.get_sensevoice_recognizer()
        if recognizer is not None:
            stream = recognizer.create_stream()
            stream.accept_waveform(sample_rate, list(samples))
            recognizer.decode_stream(stream)
            raw_out = stream.result.text
            return parse_sensevoice_output(raw_out)

        duration_sec = round(len(samples) / max(sample_rate, 1), 1)
        return parse_sensevoice_output(
            f"<|zh|><|NEUTRAL|>收到一段 {duration_sec} 秒的本地语音流（运行 scripts/download_models.py 可启用 SenseVoice 离线模型）"
        )


_default_transcriber: Optional[SenseVoiceTranscriber] = None


def get_transcriber() -> SenseVoiceTranscriber:
    global _default_transcriber
    if _default_transcriber is None:
        _default_transcriber = SenseVoiceTranscriber()
    return _default_transcriber
