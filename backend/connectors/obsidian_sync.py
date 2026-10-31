"""EventBus-Driven Obsidian Bi-Directional Markdown Sync Connector.

Automatically writes every closed Episode and Daily Memo into `data/obsidian_vault/`
with YAML frontmatter and `[[Entity]]` wiki-links so the user's Obsidian Second Brain
stays updated in real time.
"""
from pathlib import Path
import re
from typing import Any, Dict, Optional
from backend.config import settings
from backend.core.event_bus import event_bus
from backend.storage.database import get_storage


class ObsidianSyncConnector:
    """Writes Episodes and Daily Memos as interlinked Markdown notes."""

    def __init__(self, vault_dir: Optional[Path] = None) -> None:
        self.vault_dir = vault_dir or settings.obsidian_vault_dir
        self.episodes_dir = self.vault_dir / "Episodes"
        self.memos_dir = self.vault_dir / "DailyMemos"
        self.episodes_dir.mkdir(parents=True, exist_ok=True)
        self.memos_dir.mkdir(parents=True, exist_ok=True)

    def _inject_wikilinks(self, text: str) -> str:
        """Replace known semantic fact subjects in text with `[[Subject]]` Obsidian links."""
        facts = get_storage().list_semantic_facts()
        subjects = sorted({f.subject for f in facts if len(f.subject) >= 2 and f.subject != "HOST"}, key=len, reverse=True)
        linked = text
        for subj in subjects:
            if f"[[{subj}]]" not in linked and subj in linked:
                linked = linked.replace(subj, f"[[{subj}]]")
        return linked

    async def on_episode_closed(self, payload: Dict[str, Any]) -> Optional[Path]:
        if not settings.obsidian_sync_enabled or payload.get("category") == "DISCARDED":
            return None

        ep_id = payload.get("id", "ep_unknown")
        title = payload.get("title", "未命名卡片")
        safe_title = re.sub(r'[\\/*?:"<>|]', "_", title)
        date_prefix = str(payload.get("start_time", ""))[:10]
        file_path = self.episodes_dir / f"{date_prefix}_{safe_title}_{ep_id[-4:]}.md"

        todos = payload.get("action_items", [])
        clues = payload.get("clues_and_wishlists", [])
        facts = payload.get("facts_updated", [])

        md_lines = [
            "---",
            f"id: {ep_id}",
            f"title: \"{title}\"",
            f"date: {payload.get('start_time', '')}",
            f"category: {payload.get('category', 'WORK')}",
            f"importance: {payload.get('importance_score', 3)}",
            "tags:",
            "  - echomind",
            f"  - {str(payload.get('category', 'work')).lower()}",
            "---",
            "",
            f"# {title}",
            "",
            self._inject_wikilinks(payload.get("summary", "")),
            "",
        ]

        if todos:
            md_lines.append("## 待办事项 (Action Items)")
            for t in todos:
                md_lines.append(f"- [ ] **{t.get('content')}** (责任人: `{t.get('assignee')}`) — *“{t.get('source_quote')}”*")
            md_lines.append("")

        if clues:
            md_lines.append("## 愿望清单与灵感线索 (Wishlist & Clues)")
            for c in clues:
                md_lines.append(f"- **[{c.get('clue_type')}]** {c.get('content')} — *“{c.get('source_quote')}”*")
            md_lines.append("")

        if facts:
            md_lines.append("## 关联实体画像更新 (Memory Graph)")
            for f in facts:
                md_lines.append(f"- [[{f.get('subject')}]] · `{f.get('predicate')}`: **{f.get('object_value')}**")
            md_lines.append("")

        file_path.write_text("\n".join(md_lines), encoding="utf-8")
        return file_path

    async def on_memo_generated(self, payload: Dict[str, Any]) -> Optional[Path]:
        if not settings.obsidian_sync_enabled:
            return None
        memo_date = payload.get("memo_date", "today")
        memo_type = payload.get("memo_type", "MORNING_BRIEF")
        file_path = self.memos_dir / f"{memo_date}_{memo_type}.md"
        content = self._inject_wikilinks(payload.get("content_markdown", ""))
        file_path.write_text(content, encoding="utf-8")
        return file_path


_obsidian_connector: Optional[ObsidianSyncConnector] = None


def register_obsidian_connector() -> ObsidianSyncConnector:
    global _obsidian_connector
    if _obsidian_connector is None:
        _obsidian_connector = ObsidianSyncConnector()
        event_bus.subscribe("episode.closed", _obsidian_connector.on_episode_closed)
        event_bus.subscribe("memo.generated", _obsidian_connector.on_memo_generated)
    return _obsidian_connector
