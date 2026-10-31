"""Data models for EchoMind's 6 core tables (SQLite + FTS5 + metadata_json extensibility)."""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import uuid


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class _ModelBase:
    def model_dump(self) -> Dict[str, Any]:
        return asdict(self)  # type: ignore[arg-type]


@dataclass
class Utterance(_ModelBase):
    """Atomic speech transcription record with voiceprint & emotion tags."""

    text_content: str
    id: str = field(default_factory=lambda: f"utt_{uuid.uuid4().hex[:10]}")
    timestamp: str = field(default_factory=_utc_now_iso)
    duration_ms: int = 1500
    speaker_role: str = "HOST"  # HOST, GUEST_1, GUEST_2, UNKNOWN
    speaker_score: float = 0.85
    emotion_tag: str = "NEUTRAL"  # NEUTRAL, HAPPY, ANGRY, SAD
    acoustic_event: str = "NONE"  # NONE, LAUGHTER, SIGH, APPLAUSE
    is_context_prefix: bool = False
    episode_id: Optional[str] = None
    device_id: str = "default_mic"
    metadata_json: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Episode(_ModelBase):
    """MemoMind-style episodic memory card."""

    title: str
    summary: str
    id: str = field(default_factory=lambda: f"ep_{uuid.uuid4().hex[:10]}")
    start_time: str = field(default_factory=_utc_now_iso)
    end_time: str = field(default_factory=_utc_now_iso)
    category: str = "WORK"  # WORK, MEETING, IDEA, LIFE, CHITCHAT, DISCARDED
    importance_score: int = 3
    host_word_ratio: float = 1.0
    is_vectorized: bool = False
    metadata_json: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utc_now_iso)


@dataclass
class ActionItem(_ModelBase):
    """High-certainty commitment or to-do extracted from conversation."""

    content: str
    id: str = field(default_factory=lambda: f"todo_{uuid.uuid4().hex[:10]}")
    episode_id: Optional[str] = None
    assignee: str = "HOST"
    priority: str = "MEDIUM"  # HIGH, MEDIUM, LOW
    due_date: Optional[str] = None
    status: str = "PENDING"  # PENDING, DONE, DISMISSED
    source_quote: str = ""
    created_at: str = field(default_factory=_utc_now_iso)


@dataclass
class ClueAndWishlist(_ModelBase):
    """MemoMind-inspired casual wishlist item, follow-up clue, or idea spark."""

    content: str
    id: str = field(default_factory=lambda: f"clue_{uuid.uuid4().hex[:10]}")
    episode_id: Optional[str] = None
    clue_type: str = "WISHLIST"  # WISHLIST, FOLLOW_UP_CLUE, IDEA_SPARK
    source_quote: str = ""
    status: str = "ACTIVE"  # ACTIVE, ARCHIVED, CONVERTED_TO_TODO
    created_at: str = field(default_factory=_utc_now_iso)


@dataclass
class SemanticFact(_ModelBase):
    """Mem0-style dynamic long-term entity/person/project fact with conflict tracking."""

    subject: str
    predicate: str
    object_value: str
    id: str = field(default_factory=lambda: f"fact_{uuid.uuid4().hex[:10]}")
    previous_value: Optional[str] = None
    confidence: float = 0.9
    status: str = "ACTIVE"  # ACTIVE, DEPRECATED
    last_updated: str = field(default_factory=_utc_now_iso)
    source_episode_id: Optional[str] = None


@dataclass
class DailyMemo(_ModelBase):
    """Proactive Morning Brief & Evening Review memo."""

    memo_date: str
    memo_type: str  # MORNING_BRIEF, EVENING_REVIEW
    content_markdown: str
    id: str = field(default_factory=lambda: f"memo_{uuid.uuid4().hex[:10]}")
    created_at: str = field(default_factory=_utc_now_iso)
