"""Cognitive Memory Extractor (LiteLLM + Intelligent Local Heuristic Fallback).

Extracts MemoMind-style episode cards, action items with source quotes,
wishlists/clues, Mem0-style fact updates, and custom domain metadata from a list of Utterances.
"""
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import re
from typing import Dict, List, Optional
from backend.config import settings
from backend.memory_core.fact_resolver import FactResolver, get_fact_resolver
from backend.memory_core.prompts import EPISODE_EXTRACTION_SYSTEM_PROMPT
from backend.memory_core.schemas import (
    ActionItemExtract,
    ClueAndWishlistExtract,
    EpisodeCognitiveResult,
    FactOperationExtract,
)
from backend.storage.models import SemanticFact, Utterance

logger = logging.getLogger("echomind.extractor")


class CognitiveExtractor:
    """Extracts structured episodic memory, todos, wishlists, semantic facts, and domain metadata."""

    def __init__(self, fact_resolver: Optional[FactResolver] = None) -> None:
        self.fact_resolver = fact_resolver or get_fact_resolver()
        self._custom_instructions: Dict[str, str] = {}

    def register_custom_instruction(self, name: str, instruction: str) -> None:
        """Register additional vertical-domain extraction instructions (e.g., medical, sales CRM)."""
        self._custom_instructions[name] = instruction.strip()

    def unregister_custom_instruction(self, name: str) -> None:
        self._custom_instructions.pop(name, None)

    def get_effective_system_prompt(self, existing_facts_block: str) -> str:
        """Build the system prompt combining base template and any custom domain instructions."""
        base = EPISODE_EXTRACTION_SYSTEM_PROMPT.format(
            current_time=datetime.now(timezone.utc).isoformat(),
            existing_facts_block=existing_facts_block,
        )
        extras: List[str] = []
        if settings.custom_extraction_prompt:
            extras.append(settings.custom_extraction_prompt.strip())
        if settings.custom_extraction_prompt_file:
            p = Path(settings.custom_extraction_prompt_file)
            if p.exists():
                extras.append(p.read_text(encoding="utf-8").strip())
        extras.extend(self._custom_instructions.values())

        if extras:
            joined = "\n\n".join(extras)
            base = f"{base}\n\n## 垂直领域附加提取规则 (Custom Domain Instructions)\n{joined}"
        return base

    def format_dialogue_script(self, utterances: List[Utterance]) -> str:
        lines: List[str] = []
        for u in utterances:
            prefix = "[CONTEXT_PREFIX] " if u.is_context_prefix else ""
            event_str = f" [{u.acoustic_event}]" if u.acoustic_event != "NONE" else ""
            lines.append(
                f"{prefix}[{u.timestamp[:19]}] [{u.speaker_role}] [{u.emotion_tag}]{event_str}: {u.text_content}"
            )
        return "\n".join(lines)

    async def extract_episode(self, utterances: List[Utterance]) -> EpisodeCognitiveResult:
        """Run cognitive extraction via LiteLLM (if configured) or deterministic local heuristic engine."""
        active_utts = [u for u in utterances if not u.is_context_prefix]
        if not active_utts:
            active_utts = utterances

        concat_text = "\n".join(u.text_content for u in active_utts)
        existing_facts = self.fact_resolver.prefetch_relevant_facts(concat_text)

        if (
            settings.llm_api_key
            and settings.llm_api_key != "your_api_key_here"
            and settings.llm_model != "mock"
        ):
            try:
                import litellm

                sys_prompt = self.get_effective_system_prompt(
                    existing_facts_block=self.fact_resolver.format_facts_for_prompt(existing_facts)
                )
                script = self.format_dialogue_script(utterances)
                resp = await litellm.acompletion(
                    model=settings.llm_model,
                    api_key=settings.llm_api_key,
                    api_base=settings.llm_api_base,
                    messages=[
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": script},
                    ],
                    response_format=EpisodeCognitiveResult,
                    temperature=0.1,
                )
                raw_json = resp.choices[0].message.content
                return EpisodeCognitiveResult.model_validate_json(raw_json)
            except Exception as exc:
                logger.warning("LiteLLM call failed (%s), falling back to local heuristic extractor.", exc)

        return self._heuristic_extract(active_utts, existing_facts)

    def _heuristic_extract(
        self,
        utterances: List[Utterance],
        existing_facts: List[SemanticFact],
    ) -> EpisodeCognitiveResult:
        """High-precision deterministic local rule & regex extractor for zero-key offline execution."""
        todos: List[ActionItemExtract] = []
        clues: List[ClueAndWishlistExtract] = []
        fact_ops: List[FactOperationExtract] = []
        summary_bullets: List[str] = []

        todo_triggers = ("必须", "之前把", "前把", "我今晚", "我明天", "我回头", "记一下", "待办", "联调", "发你", "提交")
        wishlist_triggers = ("想买", "想要", "要是能有", "真想试", "想去", "种草", "愿望")
        idea_triggers = ("灵感", "点子", "我们可以做个", "如果做成", "开源", "新方案")
        clue_triggers = ("打听", "留意一下", "回头问问", "顺便看看", "线索")

        category = "CHITCHAT"
        importance = 2

        for u in utterances:
            txt = u.text_content.strip()
            if not txt:
                continue

            speaker_label = "我" if u.speaker_role == "HOST" else u.speaker_role
            summary_bullets.append(f"- **{speaker_label}**：{txt}")

            if any(k in txt for k in todo_triggers):
                category = "WORK"
                importance = max(importance, 4)
                due_iso = None
                if "今晚" in txt or "今天" in txt:
                    due_iso = (datetime.now(timezone.utc) + timedelta(hours=8)).strftime("%Y-%m-%d")
                elif "明天" in txt:
                    due_iso = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
                elif "下周" in txt:
                    due_iso = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%d")

                todos.append(
                    ActionItemExtract(
                        content=txt,
                        assignee="HOST" if u.speaker_role == "HOST" else u.speaker_role,
                        due_date_iso=due_iso,
                        priority="HIGH" if ("必须" in txt or "紧急" in txt) else "MEDIUM",
                        source_quote=txt,
                    )
                )

            if any(k in txt for k in wishlist_triggers):
                clues.append(
                    ClueAndWishlistExtract(
                        clue_type="WISHLIST",
                        content=txt,
                        source_quote=txt,
                    )
                )
                if category == "CHITCHAT":
                    category = "LIFE"
                importance = max(importance, 3)
            elif any(k in txt for k in idea_triggers):
                clues.append(
                    ClueAndWishlistExtract(
                        clue_type="IDEA_SPARK",
                        content=txt,
                        source_quote=txt,
                    )
                )
                if category == "CHITCHAT":
                    category = "IDEA"
                importance = max(importance, 4)
            elif any(k in txt for k in clue_triggers):
                clues.append(
                    ClueAndWishlistExtract(
                        clue_type="FOLLOW_UP_CLUE",
                        content=txt,
                        source_quote=txt,
                    )
                )
                importance = max(importance, 3)

            budget_match = re.search(
                r"([\u4e00-\u9fa5A-Za-z0-9_]{2,8}?)(?:的)?(预算|报价底线|报价|交付周期|偏好)(?:目前是|是|为|改成了|调整为|降到|定在)?([^，。！？,.!?]+)",
                txt,
            )
            if budget_match:
                subj = budget_match.group(1).strip().rstrip("的")
                pred = budget_match.group(2).strip()
                obj_val = budget_match.group(3).strip()
                matched_existing = next(
                    (f for f in existing_facts if f.subject == subj and f.predicate == pred),
                    None,
                )
                if matched_existing:
                    fact_ops.append(
                        FactOperationExtract(
                            operation="UPDATE" if matched_existing.object_value != obj_val else "NOOP",
                            existing_fact_id=matched_existing.id,
                            subject=subj,
                            predicate=pred,
                            object_value=obj_val,
                            confidence=0.95,
                        )
                    )
                else:
                    fact_ops.append(
                        FactOperationExtract(
                            operation="ADD",
                            subject=subj,
                            predicate=pred,
                            object_value=obj_val,
                            confidence=0.9,
                        )
                    )
                category = "MEETING" if u.speaker_role != "HOST" else "WORK"
                importance = max(importance, 4)

        first_sentence = utterances[0].text_content.strip() if utterances else "日常对话记录"
        clean_title = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", first_sentence)[:10] or "对话记忆卡片"
        summary_md = "### 核心对话纪要（第一人称视角）\n" + "\n".join(summary_bullets[:8])

        custom_meta: Dict[str, str] = {}
        if self._custom_instructions:
            custom_meta["active_custom_profiles"] = ",".join(sorted(self._custom_instructions.keys()))

        return EpisodeCognitiveResult(
            is_meaningful=len(utterances) > 0,
            title=clean_title,
            category=category,
            importance_score=importance,
            summary_markdown=summary_md,
            action_items=todos,
            clues_and_wishlists=clues,
            fact_operations=fact_ops,
            custom_metadata=custom_meta,
        )


_default_extractor: Optional[CognitiveExtractor] = None


def get_extractor() -> CognitiveExtractor:
    global _default_extractor
    if _default_extractor is None:
        _default_extractor = CognitiveExtractor()
    return _default_extractor
