"""Asynchronous EventBus and Pre-Execution Filter Pipeline for EchoMind.

Supports two complementary extension mechanisms:
1. `apply_filters(stage, data)` (`@filter_hook`): Synchronous/asynchronous pre-processing
   pipeline where plugins can transform data (e.g., PII redaction, medical/domain jargon
   correction, custom metadata injection) or return `None` to drop/intercept the item.
2. `publish(topic, payload)` (`@hook`): Post-action asynchronous broadcast with strict
   exception isolation and health reporting so a faulty 3rd-party plugin never crashes
   the core pipeline.
"""
import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import inspect
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("echomind.event_bus")

EventHandler = Union[Callable[[Dict[str, Any]], Awaitable[None]], Callable[[Dict[str, Any]], None]]
FilterHandler = Callable[[Any], Any]
ErrorReporter = Callable[[str, str], None]


@dataclass
class _FilterEntry:
    priority: int
    order: int
    handler: FilterHandler
    owner: str = "anonymous"


class EventBus:
    """In-memory asynchronous publish/subscribe event bus and filter pipeline with error isolation."""

    def __init__(self, max_history: int = 100) -> None:
        self._subscribers: Dict[str, List[EventHandler]] = defaultdict(list)
        self._handler_owners: Dict[Any, str] = {}
        self._filters: Dict[str, List[_FilterEntry]] = defaultdict(list)
        self._filter_counter: int = 0
        self._history: List[Dict[str, Any]] = []
        self._max_history = max_history
        self._error_reporter: Optional[ErrorReporter] = None

    def set_error_reporter(self, reporter: ErrorReporter) -> None:
        """Attach a callback `(owner_name, error_msg)` to report handler failures to HealthBoard."""
        self._error_reporter = reporter

    def subscribe(self, topic: str, handler: EventHandler, owner: str = "core") -> None:
        """Subscribe a sync or async callable to a topic (e.g., 'episode.closed')."""
        if handler not in self._subscribers[topic]:
            self._subscribers[topic].append(handler)
            self._handler_owners[handler] = owner
            logger.debug("Subscribed handler %s (%s) to topic '%s'", getattr(handler, "__name__", str(handler)), owner, topic)

    def unsubscribe(self, topic: str, handler: EventHandler) -> None:
        """Remove a handler from a topic."""
        if handler in self._subscribers.get(topic, []):
            self._subscribers[topic].remove(handler)

    def subscribe_filter(
        self,
        stage: str,
        handler: FilterHandler,
        priority: int = 100,
        owner: str = "core",
    ) -> None:
        """Register a pre-execution filter for `stage` (e.g. 'utterance.before_save').

        Filters run in ascending `priority` order. A filter returns the modified data object,
        or returns `None` to abort/drop the item from the pipeline.
        """
        existing = [e for e in self._filters[stage] if e.handler == handler]
        if existing:
            return
        self._filter_counter += 1
        entry = _FilterEntry(priority=priority, order=self._filter_counter, handler=handler, owner=owner)
        self._filters[stage].append(entry)
        self._filters[stage].sort(key=lambda e: (e.priority, e.order))
        logger.debug("Registered filter %s (%s, priority=%d) on stage '%s'", getattr(handler, "__name__", str(handler)), owner, priority, stage)

    def unsubscribe_owner(self, owner: str) -> None:
        """Remove all event subscribers and filters registered by `owner`."""
        for topic, handlers in list(self._subscribers.items()):
            self._subscribers[topic] = [h for h in handlers if self._handler_owners.get(h) != owner]
        for stage, entries in list(self._filters.items()):
            self._filters[stage] = [e for e in entries if e.owner != owner]

    async def apply_filters(self, stage: str, data: Any) -> Any:
        """Run all registered filters for `stage` sequentially.

        - If any filter returns `None`, execution halts and `None` is returned (item intercepted/dropped).
        - If a filter raises an exception, it is logged and reported to HealthBoard, and the previous
          valid `data` continues down the pipeline (fault isolation).
        """
        entries = list(self._filters.get(stage, []))
        current = data
        for entry in entries:
            if current is None:
                return None
            try:
                if inspect.iscoroutinefunction(entry.handler):
                    result = await entry.handler(current)
                else:
                    result = entry.handler(current)
                    if asyncio.iscoroutine(result):
                        result = await result
                current = result
            except Exception as exc:
                logger.error(
                    "Filter handler %s (%s) failed on stage '%s': %s",
                    getattr(entry.handler, "__qualname__", str(entry.handler)),
                    entry.owner,
                    stage,
                    exc,
                    exc_info=True,
                )
                if self._error_reporter:
                    self._error_reporter(entry.owner, f"Filter error on {stage}: {exc}")
        return current

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
                owner = self._handler_owners.get(handler, "unknown_plugin")
                logger.error(
                    "Plugin handler %s (%s) failed on topic '%s': %s",
                    getattr(handler, "__qualname__", str(handler)),
                    owner,
                    topic,
                    exc,
                    exc_info=True,
                )
                if self._error_reporter:
                    self._error_reporter(owner, f"Hook error on {topic}: {exc}")
        return invoked

    def list_subscriptions(self) -> Dict[str, Any]:
        """Return introspection metadata of active topics and filter stages."""
        return {
            "topics": {
                t: [getattr(h, "__qualname__", str(h)) for h in hs]
                for t, hs in self._subscribers.items()
                if hs
            },
            "filters": {
                s: [
                    {
                        "handler": getattr(e.handler, "__qualname__", str(e.handler)),
                        "owner": e.owner,
                        "priority": e.priority,
                    }
                    for e in es
                ]
                for s, es in self._filters.items()
                if es
            },
        }

    def get_recent_events(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return recent published events for debugging and HUD inspection."""
        return list(reversed(self._history[-limit:]))


# Global singleton event bus
event_bus = EventBus()
