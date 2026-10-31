"""Mem0-style Semantic Fact Pre-fetcher and Conflict Resolver."""
from typing import List, Optional
from backend.storage.database import StorageEngine, get_storage
from backend.storage.models import SemanticFact
from backend.memory_core.schemas import FactOperationExtract


class FactResolver:
    """Retrieves relevant prior facts before LLM extraction and applies ADD/UPDATE operations."""

    def __init__(self, storage: Optional[StorageEngine] = None) -> None:
        self.storage = storage or get_storage()

    def prefetch_relevant_facts(self, transcript_text: str, limit: int = 15) -> List[SemanticFact]:
        """Recall existing active facts whose subject appears in the conversation or belong to HOST."""
        all_active = self.storage.list_semantic_facts()
        matched: List[SemanticFact] = []
        for fact in all_active:
            if fact.subject == "HOST" or fact.subject in transcript_text or fact.predicate in transcript_text:
                matched.append(fact)
            if len(matched) >= limit:
                break
        return matched

    def format_facts_for_prompt(self, facts: List[SemanticFact]) -> str:
        if not facts:
            return "（暂无已知历史事实）"
        lines = []
        for f in facts:
            lines.append(
                f"- [fact_id={f.id}] 主体:{f.subject} | 属性:{f.predicate} | 当前值:{f.object_value}"
            )
        return "\n".join(lines)

    def apply_fact_operations(
        self,
        operations: List[FactOperationExtract],
        source_episode_id: str,
    ) -> List[SemanticFact]:
        """Execute ADD / UPDATE operations against SQLite `semantic_facts` table."""
        applied: List[SemanticFact] = []
        for op in operations:
            if op.operation == "NOOP":
                continue
            saved = self.storage.upsert_semantic_fact(
                subject=op.subject,
                predicate=op.predicate,
                object_value=op.object_value,
                confidence=op.confidence,
                source_episode_id=source_episode_id,
                existing_fact_id=op.existing_fact_id if op.operation == "UPDATE" else None,
            )
            applied.append(saved)
        return applied


_default_resolver: Optional[FactResolver] = None


def get_fact_resolver() -> FactResolver:
    global _default_resolver
    if _default_resolver is None:
        _default_resolver = FactResolver()
    return _default_resolver
