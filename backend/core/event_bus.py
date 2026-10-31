"""Asynchronous EventBus for decoupling EchoMind's micro-kernel and plugins."""
import asyncio
import inspect
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Union

logger = logging.getLogger("echomind.event_bus")

EventHandler = Union[Callable[[Dict[str, Any]], Awaitable[None]], Callable[[Dict[str, Any]], None]]


class EventBus:
    """In-memory asynchronous publish/subscribe event bus with error isolation."""

    def __init__(self, max_history: int = 100) -> None:
        self._subscribers: Dict[str, List[EventHandler]] = defaultdict(list)
        self._history: List[Dict[str, Any]] = []
        self._max_history = max_history

    def subscribe(self, topic: str, handler: EventHandler) -> None:
        """Subscribe a sync or async callable to a topic (e.g., 'episode.closed')."""
        if handler not in self._subscribers[topic]:
            self._subscribers[topic].append(handler)
            logger.debug("Subscribed handler %s to topic '%s'", getattr(handler, "__name__", str(handler)), topic)

    def unsubscribe(self, topic: str, handler: EventHandler) -> None:
        """Remove a handler from a topic."""
        if handler in self._subscribers.get(topic, []):
            self._subscribers[topic].remove(handler)

    async def publish(self, topic: str, payload: Dict[str, Any]) -> int:
        """Publish an event to all subscribers of `topic` and wildcard `*`.

        Returns the number of handlers invoked. Individual plugin errors are caught
        and logged so a buggy 3rd-party plugin never crashes the core pipeline.
        """
        event_envelope = {
            "topic": topic,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        self._history.append(event_envelope)
        if len(self._history) > self._max_history:
            self._history.pop(0)

        handlers = list(self._subscribers.get(topic, [])) + list(self._subscribers.get("*", []))
        invoked = 0
        for handler in handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    await handler(payload)
                else:
                    res = handler(payload)
                    if asyncio.iscoroutine(res):
                        await res
                invoked += 1
            except Exception as exc:
                logger.error(
                    "Plugin handler %s failed on topic '%s': %s",
                    getattr(handler, "__qualname__", str(handler)),
                    topic,
                    exc,
                    exc_info=True,
                )
        return invoked

    def get_recent_events(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return recent published events for debugging and HUD inspection."""
        return list(reversed(self._history[-limit:]))


# Global singleton event bus
event_bus = EventBus()
