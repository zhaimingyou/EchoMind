"""Dynamic Episode Segmenter State Machine with Sliding Overlap & Host-Absence Filter.

Implements the 3 core segmentation triggers from `specs/design.md`:
- Condition A (Physical Silence): > 180s since last utterance -> close & extract
- Condition B (Max Span + Sliding Overlap): >= 25 min continuous conversation -> force split & copy last 5 utterances as `is_context_prefix=True`
- Condition C (Host Absence Filter): 0% HOST word ratio (and not bystander mode) -> mark `DISCARDED` with zero LLM token consumption
"""
from datetime import datetime, timezone
import logging
from typing import List, Optional
from backend.audio_engine.speaker_id import get_speaker_identifier
from backend.config import settings
from backend.core.event_bus import event_bus
from backend.memory_core.extractor import CognitiveExtractor, get_extractor
from backend.memory_core.fact_resolver import FactResolver, get_fact_resolver
from backend.storage.database import StorageEngine, get_storage
from backend.storage.models import ActionItem, ClueAndWishlist, Episode, Utterance
from backend.storage.vector_store import HybridSearchEngine, get_hybrid_search

logger = logging.getLogger("echomind.segmenter")


def _parse_iso(ts: str) -> datetime:
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return datetime.now(timezone.utc)


class EpisodeSegmenter:
    """Monitors buffered utterances and segments them into structured Episodes."""

    def __init__(
        self,
        storage: Optional[StorageEngine] = None,
        extractor: Optional[CognitiveExtractor] = None,
        fact_resolver: Optional[FactResolver] = None,
        hybrid_search: Optional[HybridSearchEngine] = None,
    ) -> None:
        self.storage = storage or get_storage()
        self.extractor = extractor or get_extractor()
        self.fact_resolver = fact_resolver or get_fact_resolver()
        self.hybrid_search = hybrid_search or get_hybrid_search()

    async def inspect_and_segment(
        self,
        force_flush: bool = False,
        now_dt: Optional[datetime] = None,
    ) -> Optional[Episode]:
        """Inspect unassigned utterances and close an Episode if trigger conditions are met."""
        unassigned = self.storage.get_unassigned_utterances()
        real_utterances = [u for u in unassigned if not u.is_context_prefix]
        if not real_utterances:
            return None

        now = now_dt or datetime.now(timezone.utc)
        first_dt = _parse_iso(real_utterances[0].timestamp)
        last_dt = _parse_iso(real_utterances[-1].timestamp)

        silence_elapsed_sec = (now - last_dt).total_seconds()
        span_duration_sec = (last_dt - first_dt).total_seconds()

        is_silence_triggered = silence_elapsed_sec >= settings.silence_split_seconds
        is_max_span_triggered = span_duration_sec >= settings.max_episode_duration_seconds

        if not (force_flush or is_silence_triggered or is_max_span_triggered):
            return None

        return await self._close_buffer(
            unassigned=unassigned,
            real_utterances=real_utterances,
            retain_overlap=is_max_span_triggered and not force_flush,
        )

    async def _close_buffer(
        self,
        unassigned: List[Utterance],
        real_utterances: List[Utterance],
        retain_overlap: bool = False,
    ) -> Episode:
        total_chars = sum(len(u.text_content) for u in real_utterances)
        host_chars = sum(len(u.text_content) for u in real_utterances if u.speaker_role == "HOST")
        host_ratio = round(host_chars / max(total_chars, 1), 4)

        start_time = real_utterances[0].timestamp
        end_time = real_utterances[-1].timestamp
        all_ids = [u.id for u in unassigned]

        # Condition C: Host Absence Filter (0% Host speech -> discard without calling LLM!)
        if host_ratio == 0.0 and not settings.meeting_bystander_mode:
            discarded_ep = Episode(
                start_time=start_time,
                end_time=end_time,
                title="[背景音自动过滤]",
                summary="检测到该时段无主人（HOST）声纹参与，已由静默降噪规则自动归档，零 Token 消耗。",
                category="DISCARDED",
                importance_score=1,
                host_word_ratio=0.0,
            )
            self.storage.insert_episode(discarded_ep)
            self.storage.assign_utterances_to_episode(all_ids, discarded_ep.id)
            get_speaker_identifier().reset_guest_pool()
            logger.info("Discarded background episode %s (host_word_ratio=0.0)", discarded_ep.id)
            return discarded_ep

        # Extract cognitive summary, action items, wishlists/clues, and semantic facts
        cog = await self.extractor.extract_episode(unassigned)

        ep = Episode(
            start_time=start_time,
            end_time=end_time,
            title=cog.title,
            summary=cog.summary_markdown,
            category=cog.category,
            importance_score=cog.importance_score,
            host_word_ratio=host_ratio,
            is_vectorized=True,
        )
        concat_text = " ".join(u.text_content for u in real_utterances)
        self.storage.insert_episode(ep, utterances_concat=concat_text)
        self.storage.assign_utterances_to_episode(all_ids, ep.id)
        self.hybrid_search.index_episode(ep, concat_text)

        # Persist Action Items
        saved_todos: List[ActionItem] = []
        for item in cog.action_items:
            todo = self.storage.insert_action_item(
                ActionItem(
                    episode_id=ep.id,
                    content=item.content,
                    assignee=item.assignee,
                    priority=item.priority,
                    due_date=item.due_date_iso,
                    source_quote=item.source_quote,
                )
            )
            saved_todos.append(todo)
            await event_bus.publish("todo.created", todo.model_dump())

        # Persist Clues & Wishlists
        saved_clues: List[ClueAndWishlist] = []
        for c in cog.clues_and_wishlists:
            clue = self.storage.insert_clue(
                ClueAndWishlist(
                    episode_id=ep.id,
                    clue_type=c.clue_type,
                    content=c.content,
                    source_quote=c.source_quote,
                )
            )
            saved_clues.append(clue)

        # Apply Semantic Fact Upserts
        saved_facts = self.fact_resolver.apply_fact_operations(cog.fact_operations, source_episode_id=ep.id)

        # Condition B: If triggered by 25-minute max span, duplicate last N utterances as read-only context prefix
        if retain_overlap:
            overlap_n = settings.overlap_context_utterances
            tail_utterances = real_utterances[-overlap_n:]
            for orig in tail_utterances:
                prefix_copy = Utterance(
                    timestamp=orig.timestamp,
                    duration_ms=orig.duration_ms,
                    speaker_role=orig.speaker_role,
                    speaker_score=orig.speaker_score,
                    emotion_tag=orig.emotion_tag,
                    acoustic_event=orig.acoustic_event,
                    text_content=orig.text_content,
                    is_context_prefix=True,
                    episode_id=None,
                    device_id=orig.device_id,
                )
                self.storage.insert_utterance(prefix_copy)
        else:
            get_speaker_identifier().reset_guest_pool()

        # Publish `episode.closed` event to EventBus for plugins, HUDs, and Obsidian Sync
        await event_bus.publish(
            "episode.closed",
            {
                **ep.model_dump(),
                "action_items": [t.model_dump() for t in saved_todos],
                "clues_and_wishlists": [c.model_dump() for c in saved_clues],
                "facts_updated": [f.model_dump() for f in saved_facts],
            },
        )
        return ep


_default_segmenter: Optional[EpisodeSegmenter] = None


def get_segmenter() -> EpisodeSegmenter:
    global _default_segmenter
    if _default_segmenter is None:
        _default_segmenter = EpisodeSegmenter()
    return _default_segmenter
