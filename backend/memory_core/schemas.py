"""Structured output schemas for EchoMind's Cognitive Memory Core."""
from dataclasses import asdict, dataclass, field
import json
from typing import Any, Dict, List, Literal, Optional


@dataclass
class ActionItemExtract:
    """High-certainty commitment or to-do extracted from conversation."""

    content: str
    assignee: str = "HOST"
    due_date_iso: Optional[str] = None
    priority: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"
    source_quote: str = ""


@dataclass
class ClueAndWishlistExtract:
    """MemoMind-style casual wishlist item, follow-up clue, or idea spark."""

    clue_type: Literal["WISHLIST", "FOLLOW_UP_CLUE", "IDEA_SPARK"]
    content: str
    source_quote: str = ""


@dataclass
class FactOperationExtract:
    """Mem0-style dynamic long-term fact operation (ADD / UPDATE / NOOP)."""

    operation: Literal["ADD", "UPDATE", "NOOP"]
    subject: str
    predicate: str
    object_value: str
    existing_fact_id: Optional[str] = None
    confidence: float = 0.9


@dataclass
class EpisodeCognitiveResult:
    """Complete structured cognitive output for a closed Episode."""

    title: str
    summary_markdown: str
    is_meaningful: bool = True
    category: Literal["WORK", "MEETING", "IDEA", "LIFE", "CHITCHAT"] = "WORK"
    importance_score: int = 3
    action_items: List[ActionItemExtract] = field(default_factory=list)
    clues_and_wishlists: List[ClueAndWishlistExtract] = field(default_factory=list)
    fact_operations: List[FactOperationExtract] = field(default_factory=list)

    def model_dump(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def model_validate_json(cls, raw_json: str) -> "EpisodeCognitiveResult":
        data = json.loads(raw_json)
        return cls(
            is_meaningful=bool(data.get("is_meaningful", True)),
            title=str(data.get("title", "对话记忆卡片")),
            category=data.get("category", "WORK"),
            importance_score=int(data.get("importance_score", 3)),
            summary_markdown=str(data.get("summary_markdown", "")),
            action_items=[ActionItemExtract(**a) for a in data.get("action_items", [])],
            clues_and_wishlists=[ClueAndWishlistExtract(**c) for c in data.get("clues_and_wishlists", [])],
            fact_operations=[FactOperationExtract(**f) for f in data.get("fact_operations", [])],
        )
