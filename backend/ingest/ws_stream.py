"""Hardware-Agnostic WebSocket Audio Stream Gateway & Reverse Smart Glasses HUD Push.

Supports:
1. Binary PCM 16-bit 16kHz audio frames -> Pluggable VAD -> SpeakerProvider -> ASRProvider -> `utterance.before_save` Filter -> Utterance DB
2. Text JSON frames (for simulated/pre-decoded speech or instant hardware triggers)
3. Attention-Budgeted Reverse HUD push (`HUD_ATTENTION_POLICY`: `verbose` | `action_only` | `silent_record`) inspired by `dsh-superagent` 000-philosophy
"""
from __future__ import annotations
import json
import logging
from typing import Any, Dict, List, Optional, Sequence
from backend.config import settings
from backend.core.event_bus import event_bus
from backend.core.registry import registry
from backend.storage.database import get_storage
from backend.storage.models import Utterance

try:
    from fastapi import WebSocket, WebSocketDisconnect
except ImportError:  # pragma: no cover - fallback for bare stdlib test runner
    WebSocket = Any  # type: ignore[misc,assignment]

    class WebSocketDisconnect(Exception):  # type: ignore[no-redef]
        pass

logger = logging.getLogger("echomind.ws_stream")


class AudioStreamGateway:
    """Manages active WebSocket clients, audio ingestion, and attention-gated HUD notifications."""

    def __init__(self) -> None:
        self.active_connections: List[Any] = []
        event_bus.subscribe("utterance.created", self._broadcast_utterance_hud, owner="core")
        event_bus.subscribe("episode.closed", self._broadcast_episode_hud, owner="core")

    async def _broadcast_utterance_hud(self, payload: Dict[str, Any]) -> None:
        policy = settings.hud_attention_policy
        if policy in ("silent_record", "action_only"):
            return

        speaker_label = "我" if payload.get("speaker_role") == "HOST" else payload.get("speaker_role", "对方")
        hud_text = f"[{speaker_label}] {payload.get('text_content', '')[:32]}"
        frame = {
            "event": "realtime_utterance",
            "utterance_id": payload.get("id"),
            "timestamp": payload.get("timestamp"),
            "speaker_role": payload.get("speaker_role"),
            "speaker_score": payload.get("speaker_score"),
            "emotion_tag": payload.get("emotion_tag"),
            "acoustic_event": payload.get("acoustic_event"),
            "text": payload.get("text_content"),
            "hud_display": hud_text,
        }
        await self.broadcast_json(frame)

    async def _broadcast_episode_hud(self, payload: Dict[str, Any]) -> None:
        policy = settings.hud_attention_policy
        if policy == "silent_record":
            return

        todos = payload.get("action_items", [])
        clues = payload.get("clues_and_wishlists", [])
        importance = int(payload.get("importance_score", 3))
        if policy == "action_only" and not todos and not clues and importance < 4:
            return

        title = payload.get("title", "新记忆卡片")
        hud_text = f"✓ 已记《{title[:10]}》| 待办:{len(todos)} 线索:{len(clues)}"
        frame = {
            "event": "episode_created",
            "episode_id": payload.get("id"),
            "title": title,
            "category": payload.get("category"),
            "todos_count": len(todos),
            "clues_count": len(clues),
            "hud_display": hud_text,
        }
        await self.broadcast_json(frame)

    async def broadcast_json(self, message: Dict[str, Any]) -> None:
        stale: List[Any] = []
        for ws in self.active_connections:
            try:
                await ws.send_json(message)
            except Exception:
                stale.append(ws)
        for ws in stale:
            if ws in self.active_connections:
                self.active_connections.remove(ws)

    async def ingest_audio_chunk(
        self,
        samples: Sequence[float],
        duration_ms: int,
        device_id: str = "ws_client",
        sample_rate: int = 16000,
        hint_text: Optional[str] = None,
    ) -> Optional[Utterance]:
        """Run active SpeakerProvider + ASRProvider on a voiced chunk, run `utterance.before_save` filter, and persist."""
        spk_res = registry.get_speaker().identify_speaker(
            samples=samples,
            duration_ms=duration_ms,
            device_id=device_id,
            sample_rate=sample_rate,
        )
        asr_res = registry.get_asr().transcribe(
            samples=samples,
            sample_rate=sample_rate,
            hint_text=hint_text,
        )

        utt = Utterance(
            duration_ms=duration_ms,
            speaker_role=spk_res.speaker_role,
            speaker_score=spk_res.similarity_score,
            emotion_tag=asr_res.emotion_tag,
            acoustic_event=asr_res.acoustic_event,
            text_content=asr_res.clean_text,
            device_id=device_id,
            metadata_json={"is_short_inherited": spk_res.is_short_inherited, "lang": asr_res.lang},
        )
        filtered = await event_bus.apply_filters("utterance.before_save", utt)
        if filtered is None:
            return None

        get_storage().insert_utterance(filtered)
        await event_bus.publish("utterance.created", filtered.model_dump())
        return filtered

    async def handle_websocket(self, websocket: Any) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        device_id = "wearable_default"
        sample_rate = 16000
        vad_buffer = registry.create_vad(sample_rate=sample_rate)

        try:
            while True:
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    break

                if "text" in msg and msg["text"]:
                    data = json.loads(msg["text"])
                    msg_type = data.get("type", "handshake")
                    if msg_type == "handshake" or ("device_id" in data and "text" not in data):
                        device_id = data.get("device_id", device_id)
                        sample_rate = int(data.get("sample_rate", 16000))
                        vad_buffer = registry.create_vad(sample_rate=sample_rate)
                        await websocket.send_json(
                            {
                                "event": "handshake_ack",
                                "device_id": device_id,
                                "status": "ready",
                                "hud_display": f"EchoMind 已连接 [{device_id}]",
                            }
                        )
                    elif msg_type == "simulated_utterance" or "text" in data:
                        utt = Utterance(
                            duration_ms=int(data.get("duration_ms", 2000)),
                            speaker_role=data.get("speaker_role", "HOST"),
                            speaker_score=float(data.get("speaker_score", 0.88)),
                            emotion_tag=data.get("emotion_tag", "NEUTRAL"),
                            acoustic_event=data.get("acoustic_event", "NONE"),
                            text_content=data["text"],
                            device_id=data.get("device_id", device_id),
                        )
                        filtered = await event_bus.apply_filters("utterance.before_save", utt)
                        if filtered is not None:
                            get_storage().insert_utterance(filtered)
                            await event_bus.publish("utterance.created", filtered.model_dump())

                elif "bytes" in msg and msg["bytes"]:
                    chunks = vad_buffer.accept_pcm16_bytes(msg["bytes"])
                    for chunk in chunks:
                        await self.ingest_audio_chunk(
                            samples=chunk.samples,
                            duration_ms=chunk.duration_ms,
                            device_id=device_id,
                            sample_rate=chunk.sample_rate,
                        )
        except WebSocketDisconnect:
            logger.info("WebSocket client disconnected: %s", device_id)
        finally:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)


_default_gateway: Optional[AudioStreamGateway] = None


def get_stream_gateway() -> AudioStreamGateway:
    global _default_gateway
    if _default_gateway is None:
        _default_gateway = AudioStreamGateway()
    return _default_gateway
