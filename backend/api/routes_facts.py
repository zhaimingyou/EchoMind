"""REST API routes for Semantic Facts (Mem0-style Entity Graph)."""
from typing import Any, Dict, Optional
from fastapi import APIRouter, Query
from backend.storage.database import get_storage

router = APIRouter(prefix="/api/v1", tags=["Semantic Facts & Entity Graph"])


@router.get("/facts")
def list_semantic_facts(subject: Optional[str] = Query(default=None)) -> Dict[str, Any]:
    facts = get_storage().list_semantic_facts(subject=subject)
    return {"count": len(facts), "facts": [f.model_dump() for f in facts]}
