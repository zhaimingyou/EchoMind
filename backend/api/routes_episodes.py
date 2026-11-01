"""REST API routes for Episodes, Utterances, Hybrid Search, and Daily Memos."""
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from backend.core.event_bus import event_bus
from backend.memory_core.proactive_cron import get_memo_generator
from backend.memory_core.segmenter import get_segmenter
from backend.storage.database import get_storage
from backend.storage.models import Utterance
from backend.storage.vector_store import get_hybrid_search

router = APIRouter(prefix="/api/v1", tags=["Episodes & Memos"])


class UtteranceCreateRequest(BaseModel):
    text_content: str
    speaker_role: str = "HOST"
    speaker_score: float = 0.90
    emotion_tag: str = "NEUTRAL"
    acoustic_event: str = "NONE"
    duration_ms: int = 2000
    device_id: str = "web_pwa"


@router.get("/episodes")
def list_or_search_episodes(
    q: Optional[str] = Query(default=None, description="Hybrid search query (FTS5 + Vector RRF)"),
    category: Optional[str] = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
) -> Dict[str, Any]:
    storage = get_storage()
    if q and q.strip():
        episodes = get_hybrid_search().hybrid_search(query=q, category=category, limit=limit)
    else:
        episodes = storage.list_episodes(category=category, limit=limit)

    items = []
    for ep in episodes:
        utts = storage.get_utterances_by_episode(ep.id)
        todos = storage.list_action_items(episode_id=ep.id)
        items.append(
            {
                **ep.model_dump(),
                "utterances": [u.model_dump() for u in utts],
                "action_items": [t.model_dump() for t in todos],
            }
        )
    return {"count": len(items), "episodes": items}


@router.get("/episodes/{episode_id}")
def get_episode_detail(episode_id: str) -> Dict[str, Any]:
    storage = get_storage()
    ep = storage.get_episode(episode_id)
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")
    utts = storage.get_utterances_by_episode(ep.id)
    todos = storage.list_action_items(episode_id=ep.id)
    return {
        **ep.model_dump(),
        "utterances": [u.model_dump() for u in utts],
        "action_items": [t.model_dump() for t in todos],
    }


@router.post("/utterances")
async def push_utterance(req: UtteranceCreateRequest) -> Dict[str, Any]:
    """Push a real-time or simulated utterance through the `utterance.before_save` filter pipeline into the buffer."""
    utt = Utterance(
        text_content=req.text_content,
        speaker_role=req.speaker_role,
        speaker_score=req.speaker_score,
        emotion_tag=req.emotion_tag,
        acoustic_event=req.acoustic_event,
        duration_ms=req.duration_ms,
        device_id=req.device_id,
    )
    filtered = await event_bus.apply_filters("utterance.before_save", utt)
    if filtered is None:
        return {"status": "dropped_by_filter", "utterance": None}

    get_storage().insert_utterance(filtered)
    await event_bus.publish("utterance.created", filtered.model_dump())
    return {"status": "buffered", "utterance": filtered.model_dump()}


@router.get("/utterances/buffer")
def get_buffered_utterances() -> Dict[str, Any]:
    """Return currently unassigned utterances waiting in the active conversation buffer."""
    unassigned = get_storage().get_unassigned_utterances()
    return {
        "count": len(unassigned),
        "utterances": [u.model_dump() for u in unassigned],
    }


@router.post("/episodes/flush")
async def flush_current_episode() -> Dict[str, Any]:
    """Immediately close the current conversation buffer and extract a MemoMind Episode card."""
    ep = await get_segmenter().inspect_and_segment(force_flush=True)
    if not ep:
        return {"status": "empty_buffer", "episode": None}
    return {"status": "flushed", "episode": ep.model_dump()}


@router.get("/memos")
def list_daily_memos(memo_type: Optional[str] = None) -> Dict[str, Any]:
    memos = get_storage().list_daily_memos(memo_type=memo_type)
    return {"count": len(memos), "memos": [m.model_dump() for m in memos]}


@router.post("/memos/generate")
async def trigger_daily_memo(memo_type: str = Query(default="MORNING_BRIEF")) -> Dict[str, Any]:
    if memo_type not in ("MORNING_BRIEF", "EVENING_REVIEW"):
        raise HTTPException(status_code=400, detail="memo_type must be MORNING_BRIEF or EVENING_REVIEW")
    memo = await get_memo_generator().generate_daily_memo(memo_type=memo_type)  # type: ignore[arg-type]
    return {"status": "generated", "memo": memo.model_dump()}
