"""Example Smart Glasses HUD Teleprompter & Logger Plugin.

Demonstrates how hardware teams (MemoMind-style optical waveguide glasses,
Even Realities G1, Brilliant Labs Frame, or Omi wearables) can extend EchoMind
in ~30 lines of Python without touching core state machine code.
"""
import logging
from typing import Any, Dict, List
from backend.core.plugin_manager import EchoMindPlugin, hook

logger = logging.getLogger("echomind.plugin.hud_logger")


class SmartGlassesHudPlugin(EchoMindPlugin):
    """Formats real-time captions and proactive todo notifications for Micro-LED HUDs."""

    name = "smart_glasses_hud_formatter"
    version = "0.1.0"
    description = "Formats 40-char green Micro-LED waveguide HUD notifications for smart glasses (MemoMind / G1 / Frame)."
    enabled = True

    def __init__(self) -> None:
        self.recent_hud_frames: List[Dict[str, Any]] = []

    @hook("utterance.created")
    async def on_utterance(self, payload: Dict[str, Any]) -> None:
        speaker = "我" if payload.get("speaker_role") == "HOST" else payload.get("speaker_role", "对方")
        text = payload.get("text_content", "")[:32]
        hud_line = f"[{speaker}] {text}"
        self.recent_hud_frames.append({"type": "caption", "hud_display": hud_line})
        if len(self.recent_hud_frames) > 50:
            self.recent_hud_frames.pop(0)
        logger.debug("HUD Caption Frame: %s", hud_line)

    @hook("episode.closed")
    async def on_episode_closed(self, payload: Dict[str, Any]) -> None:
        title = payload.get("title", "新记忆卡片")
        todos = payload.get("action_items", [])
        clues = payload.get("clues_and_wishlists", [])
        hud_line = f"✓ 记忆已存《{title[:10]}》| 待办:{len(todos)} 线索:{len(clues)}"
        self.recent_hud_frames.append({"type": "episode_alert", "hud_display": hud_line})
        logger.info("HUD Episode Alert: %s", hud_line)
