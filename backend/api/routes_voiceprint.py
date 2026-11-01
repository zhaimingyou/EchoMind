"""REST API routes for Host Voiceprint Registration, Plugins, and Micro-Kernel Introspection."""
import io
from typing import Any, Dict, Optional
from fastapi import APIRouter, File, UploadFile
import numpy as np
import soundfile as sf
from backend.core.event_bus import event_bus
from backend.core.plugin_manager import plugin_manager
from backend.core.registry import registry
from backend.core.runtime import runtime_manager

router = APIRouter(prefix="/api/v1", tags=["Voiceprint, Plugins & Micro-Kernel"])


@router.get("/voiceprint/status")
def get_voiceprint_status() -> Dict[str, Any]:
    identifier = registry.get_speaker()
    return {
        "enrolled": identifier.has_host_voiceprint(),
        "voiceprint_path": str(getattr(identifier, "voiceprint_path", "")),
        "host_threshold": getattr(identifier, "host_threshold", 0.65),
    }


@router.post("/voiceprint/enroll")
async def enroll_voiceprint(file: Optional[UploadFile] = File(default=None)) -> Dict[str, Any]:
    """Enroll the owner's `[HOST]` voiceprint via uploaded WAV or synthetic demo signal."""
    identifier = registry.get_speaker()
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
        "voiceprint_path": str(getattr(identifier, "voiceprint_path", "")),
    }


@router.get("/plugins")
def list_active_plugins() -> Dict[str, Any]:
    return {
        "plugins": plugin_manager.list_plugins(),
        "recent_events": event_bus.get_recent_events(limit=15),
    }


@router.get("/system/kernel")
def inspect_microkernel_status() -> Dict[str, Any]:
    """Return attention-first micro-kernel health, active providers, plugins, and durable effects."""
    return runtime_manager.get_kernel_status()


@router.post("/system/pass")
async def trigger_maintenance_pass() -> Dict[str, Any]:
    """Manually trigger one atomic RuntimeManager pass (due effects, silence segmentation, audio inbox)."""
    return await runtime_manager.run_pass()
