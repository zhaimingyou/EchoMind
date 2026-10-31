"""Local Hybrid Search Engine (SQLite FTS5 BM25 + CPU Feature Vector RRF).

Provides zero-config local vector similarity + keyword Reciprocal Rank Fusion (RRF)
without requiring external GPU or cloud embedding API keys.
"""
import hashlib
import math
from typing import Dict, List, Optional, Tuple
from backend.storage.database import StorageEngine, get_storage
from backend.storage.models import Episode


def compute_local_text_embedding(text: str, dim: int = 256) -> List[float]:
    """Compute a fast, deterministic L2-normalized character/bi-gram feature vector on CPU."""
    vec = [0.0] * dim
    clean = text.strip().lower()
    if not clean:
        return vec

    tokens = list(clean) + [clean[i : i + 2] for i in range(len(clean) - 1)]
    for tok in tokens:
        if not tok.strip():
            continue
        digest = hashlib.md5(tok.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:2], "little") % dim
        sign = 1.0 if (digest[2] & 1) == 0 else -1.0
        vec[idx] += sign

    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 1e-8:
        vec = [v / norm for v in vec]
    return vec


def _dot(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


class HybridSearchEngine:
    """Combines SQLite FTS5 keyword search with vector cosine similarity via RRF."""

    def __init__(self, storage: Optional[StorageEngine] = None) -> None:
        self.storage = storage or get_storage()
        self._vectors: Dict[str, List[float]] = {}

    def index_episode(self, ep: Episode, utterances_text: str = "") -> None:
        """Index an episode into the local vector store."""
        combined = f"{ep.title} {ep.summary} {utterances_text}"
        self._vectors[ep.id] = compute_local_text_embedding(combined)

    def hybrid_search(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 5,
        rrf_k: int = 60,
    ) -> List[Episode]:
        """Perform Reciprocal Rank Fusion (RRF) across FTS5 keyword & vector search."""
        if not query.strip():
            return self.storage.list_episodes(category=category, limit=limit)

        fts_hits = self.storage.search_episodes_fts(query, limit=limit * 3)
        if category:
            fts_hits = [ep for ep in fts_hits if ep.category == category]

        all_episodes = self.storage.list_episodes(category=category, limit=200)
        q_vec = compute_local_text_embedding(query)

        vec_scored: List[Tuple[float, Episode]] = []
        for ep in all_episodes:
            if ep.id not in self._vectors:
                utts = self.storage.get_utterances_by_episode(ep.id)
                utt_text = " ".join(u.text_content for u in utts)
                self.index_episode(ep, utt_text)
            score = _dot(q_vec, self._vectors[ep.id])
            if score > 0.05:
                vec_scored.append((score, ep))

        vec_scored.sort(key=lambda x: x[0], reverse=True)
        vec_hits = [ep for _, ep in vec_scored[: limit * 3]]

        rrf_scores: Dict[str, float] = {}
        ep_lookup: Dict[str, Episode] = {}

        for rank, ep in enumerate(fts_hits):
            ep_lookup[ep.id] = ep
            rrf_scores[ep.id] = rrf_scores.get(ep.id, 0.0) + 1.0 / (rrf_k + rank + 1)

        for rank, ep in enumerate(vec_hits):
            ep_lookup[ep.id] = ep
            rrf_scores[ep.id] = rrf_scores.get(ep.id, 0.0) + 0.8 / (rrf_k + rank + 1)

        ranked_ids = sorted(rrf_scores.keys(), key=lambda eid: rrf_scores[eid], reverse=True)
        return [ep_lookup[eid] for eid in ranked_ids[:limit]]


_default_hybrid: Optional[HybridSearchEngine] = None


def get_hybrid_search() -> HybridSearchEngine:
    global _default_hybrid
    if _default_hybrid is None:
        _default_hybrid = HybridSearchEngine()
    return _default_hybrid
