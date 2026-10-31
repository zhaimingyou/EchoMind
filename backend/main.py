"""EchoMind FastAPI Application Entrypoint (`backend/main.py`).

Mounts:
- Interactive Web PWA & Smart Glasses HUD Simulator (`/`)
- REST APIs (`/api/v1/episodes`, `/api/v1/actions`, `/api/v1/clues`, `/api/v1/facts`, `/api/v1/memos`, `/api/v1/voiceprint`, `/api/v1/plugins`)
- Hardware-Agnostic WebSocket Audio & HUD Stream (`/api/v1/stream/audio`)
- Dynamic Plugin Discovery (`plugins/`) & Built-in Connectors (Obsidian Sync & Webhook)
- Demo Scenario Seeder (`/api/v1/demo/seed`) for instant out-of-the-box evaluation
"""
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Dict
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from backend.api import routes_actions, routes_episodes, routes_facts, routes_voiceprint
from backend.config import settings
from backend.core.plugin_manager import plugin_manager
from backend.ingest.ws_stream import get_stream_gateway
from backend.memory_core.proactive_cron import get_memo_generator
from backend.memory_core.segmenter import get_segmenter
from backend.storage.database import get_storage
from backend.storage.models import Utterance


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    get_storage()
    plugin_manager.discover_and_load()
    try:
        from backend.connectors.obsidian_sync import register_obsidian_connector
        from backend.connectors.webhook_notifier import register_webhook_connector

        register_obsidian_connector()
        register_webhook_connector()
    except ImportError:
        pass
    yield


app = FastAPI(
    title="EchoMind — Open-Source Personal 2nd Brain & Wearable Memory Hub",
    description=(
        "100% Local CPU-First Memory Backend inspired by MemoMind (极米记得), "
        "Omi, Plaud Note, Screenpipe, and Mem0."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_episodes.router)
app.include_router(routes_actions.router)
app.include_router(routes_facts.router)
app.include_router(routes_voiceprint.router)


@app.get("/", response_class=HTMLResponse)
def serve_web_pwa() -> HTMLResponse:
    """Serve the interactive EchoMind Web PWA & Smart Glasses HUD Workbench."""
    pwa_file = Path(__file__).resolve().parent.parent / "web_pwa" / "index.html"
    if pwa_file.exists():
        return HTMLResponse(content=pwa_file.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>EchoMind API Running. Open /docs for OpenAPI UI.</h1>")


@app.get("/health")
def health_check() -> Dict[str, Any]:
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": "0.1.0",
        "plugins_loaded": len(plugin_manager.list_plugins()),
    }


@app.websocket("/api/v1/stream/audio")
async def websocket_audio_endpoint(websocket: WebSocket) -> None:
    await get_stream_gateway().handle_websocket(websocket)


@app.post("/api/v1/demo/seed")
async def seed_demo_data() -> Dict[str, Any]:
    """Populate realistic MemoMind-style conversations, todos, wishlists, and Mem0 fact updates."""
    storage = get_storage()
    segmenter = get_segmenter()

    ep1_utterances = [
        Utterance(
            speaker_role="GUEST_1",
            speaker_score=0.31,
            emotion_tag="NEUTRAL",
            text_content="王总的报价底线是50万，希望我们在两周内完成智能眼镜 HUD 字幕接口。",
            device_id="memo_glasses_g1",
        ),
        Utterance(
            speaker_role="HOST",
            speaker_score=0.92,
            emotion_tag="HAPPY",
            acoustic_event="LAUGHTER",
            text_content="哈哈没问题，下周三之前必须把产线 WebSocket 语音流接口联调完！",
            device_id="memo_glasses_g1",
        ),
        Utterance(
            speaker_role="HOST",
            speaker_score=0.89,
            emotion_tag="NEUTRAL",
            text_content="真想买一台拓竹 3D 打印机来打我们自己的开源智能胸针外壳。",
            device_id="memo_glasses_g1",
        ),
    ]
    for u in ep1_utterances:
        storage.insert_utterance(u)
    ep1 = await segmenter.inspect_and_segment(force_flush=True)

    ep2_utterances = [
        Utterance(
            speaker_role="GUEST_1",
            speaker_score=0.29,
            emotion_tag="SAD",
            acoustic_event="SIGH",
            text_content="唉，刚刚收到通知，王总的报价底线调整为35万，但交付周期可以放宽到一个月。",
            device_id="memo_glasses_g1",
        ),
        Utterance(
            speaker_role="HOST",
            speaker_score=0.94,
            emotion_tag="NEUTRAL",
            text_content="收到，我今晚发你一份精简版纯 CPU 本地部署方案，另外我们可以做个支持 Obsidian 双链的开源插件。",
            device_id="memo_glasses_g1",
        ),
    ]
    for u in ep2_utterances:
        storage.insert_utterance(u)
    ep2 = await segmenter.inspect_and_segment(force_flush=True)

    morning_memo = await get_memo_generator().generate_daily_memo("MORNING_BRIEF")
    evening_memo = await get_memo_generator().generate_daily_memo("EVENING_REVIEW")

    return {
        "status": "seeded",
        "episodes_created": [ep1.id if ep1 else None, ep2.id if ep2 else None],
        "morning_memo_id": morning_memo.id,
        "evening_memo_id": evening_memo.id,
    }
