"""Webhook Notifier for Feishu / WeCom / DingTalk / Bark push alerts."""
import json
import logging
from typing import Any, Dict, Optional
import urllib.request
from backend.config import settings
from backend.core.event_bus import event_bus

logger = logging.getLogger("echomind.webhook")


class WebhookNotifier:
    """Sends real-time notifications when high-priority episodes or daily memos are generated."""

    def __init__(self, webhook_url: Optional[str] = None) -> None:
        self.webhook_url = webhook_url if webhook_url is not None else settings.webhook_url

    async def on_memo_generated(self, payload: Dict[str, Any]) -> bool:
        if not self.webhook_url:
            return False
        body = json.dumps(
            {
                "msg_type": "text",
                "content": {
                    "text": payload.get("content_markdown", "")[:1500],
                },
            }
        ).encode("utf-8")
        try:
            try:
                import httpx

                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.post(
                        self.webhook_url,
                        content=body,
                        headers={"Content-Type": "application/json"},
                    )
            except ImportError:
                req = urllib.request.Request(
                    self.webhook_url,
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=5.0):
                    pass
            return True
        except Exception as exc:
            logger.warning("Webhook delivery failed: %s", exc)
            return False


_webhook_notifier: Optional[WebhookNotifier] = None


def register_webhook_connector() -> WebhookNotifier:
    global _webhook_notifier
    if _webhook_notifier is None:
        _webhook_notifier = WebhookNotifier()
        event_bus.subscribe("memo.generated", _webhook_notifier.on_memo_generated)
    return _webhook_notifier
