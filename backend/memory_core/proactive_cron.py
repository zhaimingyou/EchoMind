"""Proactive Morning Brief & Evening Review Memo Generator (MemoMind Feature)."""
from datetime import datetime, timezone
from typing import Literal, Optional
from backend.core.event_bus import event_bus
from backend.storage.database import StorageEngine, get_storage
from backend.storage.models import DailyMemo


class ProactiveMemoGenerator:
    """Generates proactive Morning Briefs and Evening Reviews from structured memories."""

    def __init__(self, storage: Optional[StorageEngine] = None) -> None:
        self.storage = storage or get_storage()

    async def generate_daily_memo(
        self,
        memo_type: Literal["MORNING_BRIEF", "EVENING_REVIEW"] = "MORNING_BRIEF",
        target_date: Optional[str] = None,
    ) -> DailyMemo:
        date_str = target_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        pending_todos = self.storage.list_action_items(status="PENDING")
        active_clues = self.storage.list_clues(status="ACTIVE")
        recent_episodes = self.storage.list_episodes(limit=10)
        facts = self.storage.list_semantic_facts()

        if memo_type == "MORNING_BRIEF":
            lines = [
                f"# 🌅 早安 Memo ({date_str}) — 今日主动推进简报",
                "",
                "## 1. 待兑现承诺与高优待办 (Pending To-Dos)",
            ]
            if pending_todos:
                for idx, t in enumerate(pending_todos[:8], 1):
                    due = f" (截止: {t.due_date})" if t.due_date else ""
                    lines.append(f"{idx}. **[{t.priority}]** {t.content}{due} — *原话: “{t.source_quote}”*")
            else:
                lines.append("- 今日暂无积压待办，轻装上阵！")

            lines.extend(["", "## 2. 随口提及的愿望清单与跟进线索 (Wishlist & Clues)"])
            if active_clues:
                for c in active_clues[:6]:
                    lines.append(f"- **[{c.clue_type}]** {c.content} (*“{c.source_quote}”*)")
            else:
                lines.append("- 暂无未处理的潜在线索。")

            lines.extend(["", "## 3. 关键人物与项目画像备忘 (Active Memory Graph)"])
            for f in facts[:6]:
                prev_note = f" *(原为: {f.previous_value})*" if f.previous_value else ""
                lines.append(f"- **{f.subject}** · {f.predicate}：**{f.object_value}**{prev_note}")
        else:
            lines = [
                f"# 🌙 晚安 Memo ({date_str}) — 全天记忆复盘与认知沉淀",
                "",
                f"## 1. 今日情景记忆卡片汇总 (共 {len(recent_episodes)} 张有效卡片)",
            ]
            if recent_episodes:
                for ep in recent_episodes[:8]:
                    lines.append(f"### 📌 《{ep.title}》 (`{ep.category}` | 重要度 {'★' * ep.importance_score})")
                    lines.append(ep.summary)
                    lines.append("")
            else:
                lines.append("- 今日暂无已闭合的对话卡片。")

            lines.extend(["## 2. 最新沉淀的长期认知事实 (Semantic Facts)"])
            if facts:
                for f in facts[:8]:
                    prev_note = f"（已由旧值 `{f.previous_value}` 动态更新）" if f.previous_value else ""
                    lines.append(f"- **{f.subject}** 的 `{f.predicate}` -> **{f.object_value}** {prev_note}")
            else:
                lines.append("- 今日暂无新增实体画像。")

        memo = DailyMemo(
            memo_date=date_str,
            memo_type=memo_type,
            content_markdown="\n".join(lines),
        )
        self.storage.insert_daily_memo(memo)
        await event_bus.publish("memo.generated", memo.model_dump())
        return memo


_default_memo_gen: Optional[ProactiveMemoGenerator] = None


def get_memo_generator() -> ProactiveMemoGenerator:
    global _default_memo_gen
    if _default_memo_gen is None:
        _default_memo_gen = ProactiveMemoGenerator()
    return _default_memo_gen
