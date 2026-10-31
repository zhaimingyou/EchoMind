"""REST API routes for Host Voiceprint Registration, Plugins, and HUD Event Feed."""
import io
from typing import Any, Dict, Optional
from fastapi import APIRouter, File, UploadFile
import numpy as np
import soundfile as sf
from backend.audio_engine.speaker_id import get_speaker_identifier
from backend.core.event_bus import event_bus
from backend.core.plugin_manager import plugin_manager

router = APIRouter(prefix="/api/v1", tags=["Voiceprint, Plugins & HUD"])


@router.get("/voiceprint/status")
def get_voiceprint_status() -> Dict[str, Any]:
    identifier = get_speaker_identifier()
    return {
        "enrolled": identifier.has_host_voiceprint(),
        "voiceprint_path": str(identifier.voiceprint_path),
        "host_threshold": identifier.host_threshold,
    }


@router.post("/voiceprint/enroll")
async def enroll_voiceprint(file: Optional[UploadFile] = File(default=None)) -> Dict[str, Any]:
    """Enroll the owner's `[HOST]` voiceprint via uploaded WAV or synthetic demo signal."""
    identifier = get_speaker_identifier()
    if file is not None:
        raw_bytes = await file.read()
        samples, sr = sf.read(io.BytesIO(raw_bytes), dtype="float32")
        if samples.ndim > 1:
            samples = samples[:, 0]
        emb = identifier.enroll_host_voice(samples, sample_rate=sr)
    else:
        t = np.linspace(0, 3.0, 16000 * 3, endpoint=False, dtype=np.float32)
        demo_wave = 0.5 * np.sin(2 * np.pi * 180.0 * t) + 0.25 * np.sin(2 * np.pi * 360.0 * t)
        emb = identifier.enroll_host_voice(demo_wave, sample_rate=16000)

    return {
        "status": "enrolled",
        "embedding_dim": int(len(emb)),
        "voiceprint_path": str(identifier.voiceprint_path),
    }


@router.get("/plugins")
def list_active_plugins() -> Dict[str, Any]:
    return {
        "plugins": plugin_manager.list_plugins(),
        "recent_events": event_bus.get_recent_events(limit=15),
    }
