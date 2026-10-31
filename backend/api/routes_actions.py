"""REST API routes for Action Items (To-Dos) and Clues & Wishlists (MemoMind Feature)."""
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from backend.storage.database import get_storage
from backend.storage.models import ActionItem

router = APIRouter(prefix="/api/v1", tags=["Actions & Wishlists"])


class StatusUpdateRequest(BaseModel):
    status: str


@router.get("/actions")
def list_actions(
    status: Optional[str] = Query(default=None),
    assignee: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    items = get_storage().list_action_items(status=status, assignee=assignee)
    return {"count": len(items), "action_items": [i.model_dump() for i in items]}


@router.patch("/actions/{item_id}")
def update_action_status(item_id: str, req: StatusUpdateRequest) -> Dict[str, Any]:
    updated = get_storage().update_action_item_status(item_id, req.status)
    if not updated:
        raise HTTPException(status_code=404, detail="Action item not found")
    return {"status": "updated", "action_item": updated.model_dump()}


@router.get("/clues")
def list_clues_and_wishlists(
    clue_type: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default="ACTIVE"),
) -> Dict[str, Any]:
    clues = get_storage().list_clues(clue_type=clue_type, status=status)
    return {"count": len(clues), "clues": [c.model_dump() for c in clues]}


@router.post("/clues/{clue_id}/convert-to-todo")
def convert_clue_to_todo(clue_id: str) -> Dict[str, Any]:
    """Promote a casual wishlist item or clue into a formal Action Item (To-Do)."""
    storage = get_storage()
    clue = storage.update_clue_status(clue_id, "CONVERTED_TO_TODO")
    if not clue:
        raise HTTPException(status_code=404, detail="Clue not found")

    new_todo = storage.insert_action_item(
        ActionItem(
            episode_id=clue.episode_id,
            content=f"[由愿望/线索转化] {clue.content}",
            assignee="HOST",
            priority="MEDIUM",
            source_quote=clue.source_quote,
        )
    )
    return {
        "status": "converted",
        "clue": clue.model_dump(),
        "action_item": new_todo.model_dump(),
    }
