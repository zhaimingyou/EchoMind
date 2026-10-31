"""EchoMind Native FastMCP Server (`backend/connectors/mcp_server.py`).

Exposes 4 standard Model Context Protocol (MCP) tools so external coding/office agents
(Claude Desktop, Cursor, Windsurf, OpenCode) can query the user's real-world spoken memories:
1. `search_personal_memory(query, category, limit)`
2. `get_pending_todos(assignee)`
3. `get_wishlists_and_clues(clue_type)`
4. `query_entity_graph(entity_name)`
"""
from typing import Optional
from backend.storage.database import get_storage
from backend.storage.vector_store import get_hybrid_search


def search_personal_memory(
    query: str,
    category: Optional[str] = None,
    limit: int = 5,
) -> str:
    """Hybrid search (SQLite FTS5 BM25 + Vector RRF) across personal spoken episodes and utterances."""
    storage = get_storage()
    episodes = get_hybrid_search().hybrid_search(query=query, category=category, limit=limit)
    if not episodes:
        return f"未找到与“{query}”相关的个人语音记忆卡片。"

    blocks = [f"### 检索到 {len(episodes)} 条相关个人语音记忆（查询词：{query}）\n"]
    for ep in episodes:
        utts = storage.get_utterances_by_episode(ep.id)
        quotes = "\n".join(
            f"  - [{u.speaker_role}] ({u.emotion_tag}): {u.text_content}"
            for u in utts
            if not u.is_context_prefix
        )
        blocks.append(
            f"#### 📌 《{ep.title}》 (ID: `{ep.id}` | 分类: `{ep.category}` | 时间: {ep.start_time[:19]})\n"
            f"{ep.summary}\n"
            f"**原始对话摘录**：\n{quotes}\n"
        )
    return "\n".join(blocks)


def get_pending_todos(assignee: str = "HOST") -> str:
    """Return all pending commitments and action items extracted from daily conversations."""
    todos = get_storage().list_action_items(status="PENDING", assignee=assignee if assignee != "ALL" else None)
    if not todos:
        return "当前没有未完成的口头待办事项（PENDING To-Dos）。"

    lines = [f"### 待兑现口头承诺与待办清单 (共 {len(todos)} 项)\n"]
    for idx, t in enumerate(todos, 1):
        due_str = f" | 截止: `{t.due_date}`" if t.due_date else ""
        lines.append(
            f"{idx}. **[{t.priority}]** {t.content} (责任人: `{t.assignee}`{due_str})\n"
            f"   - *原话出处*: “{t.source_quote}” (卡片 `{t.episode_id}`)"
        )
    return "\n".join(lines)


def get_wishlists_and_clues(clue_type: Optional[str] = None) -> str:
    """Return casual wishlists (`WISHLIST`), follow-up clues (`FOLLOW_UP_CLUE`), and idea sparks (`IDEA_SPARK`)."""
    clues = get_storage().list_clues(clue_type=clue_type, status="ACTIVE")
    if not clues:
        return "当前没有活跃的愿望清单或跟进线索。"

    lines = [f"### 随口提及的愿望清单与灵感线索 (共 {len(clues)} 项)\n"]
    for idx, c in enumerate(clues, 1):
        lines.append(
            f"{idx}. **[{c.clue_type}]** {c.content}\n"
            f"   - *原话出处*: “{c.source_quote}”"
        )
    return "\n".join(lines)


def query_entity_graph(entity_name: str) -> str:
    """Query dynamic long-term semantic facts (Mem0-style entity graph) for a person, project, or HOST."""
    facts = get_storage().list_semantic_facts(subject=entity_name)
    if not facts:
        return f"记忆图谱中暂无关于“{entity_name}”的沉淀事实。"

    lines = [f"### 实体长期记忆图谱：{entity_name} (共 {len(facts)} 条有效事实)\n"]
    for f in facts:
        history = f" *(历史旧值: `{f.previous_value}`)*" if f.previous_value else ""
        lines.append(
            f"- **{f.subject}** · `{f.predicate}` = **{f.object_value}**{history} "
            f"(置信度: {f.confidence:.2f}, 更新于 {f.last_updated[:19]})"
        )
    return "\n".join(lines)


def create_mcp_app():
    """Create FastMCP instance if `fastmcp` is installed."""
    try:
        from fastmcp import FastMCP

        mcp = FastMCP("EchoMind-Personal-Memory")
        mcp.tool()(search_personal_memory)
        mcp.tool()(get_pending_todos)
        mcp.tool()(get_wishlists_and_clues)
        mcp.tool()(query_entity_graph)
        return mcp
    except ImportError:
        return None


if __name__ == "__main__":
    mcp_app = create_mcp_app()
    if mcp_app is not None:
        mcp_app.run()
    else:
        print("EchoMind MCP Tools ready. Install `fastmcp` (`pip install fastmcp`) to run stdio server.")
