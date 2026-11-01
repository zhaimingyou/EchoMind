"""Autonomous Runtime Daemon, Passes Loop, and Durable Effects Executor (`backend/core/runtime.py`).

Inspired by `deepseek-ai/dsh-superagent-prototype` (`src/app/runtime.ts`, `passes.ts`, `effects.ts`):
- **Single Pass Loop (`run_pass`)**: Executes due durable side-effects with exponential backoff,
  evaluates silence-timeout episode segmentation, scans `data/audio_inbox/`, and checks daily memos.
- **Durable Effects Queue**: Side-effects enqueued by core connectors or plugins are processed
  asynchronously with retry and reported to `HealthBoard` if they fail `effect_max_attempts` times.
- **Lifecycle Orchestration**: Manages startup and graceful shutdown of all `EchoMindPlugin`
  instances and `IngestAdapter` services.
"""
import asyncio
from datetime import datetime, timezone
import inspect
import logging
from typing import Any, Awaitable, Callable, Dict, Optional, Union
from backend.config import settings
from backend.core.event_bus import event_bus
from backend.core.plugin_manager import HealthBoard, PluginManager, health_board, plugin_manager
from backend.core.registry import ProviderRegistry, registry
from backend.storage.database import StorageEngine, get_storage
from backend.storage.models import DurableEffect

logger = logging.getLogger("echomind.runtime")

EffectHandler = Union[Callable[[Dict[str, Any]], Awaitable[None]], Callable[[Dict[str, Any]], None]]


class RuntimeManager:
    """Orchestrates background passes, durable effect handlers, and plugin/adapter lifecycles."""

    def __init__(
        self,
        storage: Optional[StorageEngine] = None,
        pm: PluginManager = plugin_manager,
        provider_registry: ProviderRegistry = registry,
        board: HealthBoard = health_board,
    ) -> None:
        self._storage = storage
        self.pm = pm
        self.registry = provider_registry
        self.board = board
        self._effect_handlers: Dict[str, EffectHandler] = {}
        self._pass_lock = asyncio.Lock()
        self._bg_task: Optional[asyncio.Task] = None
        self._running: bool = False
        self._passes_completed: int = 0
        self._last_pass_at: Optional[str] = None

    @property
    def storage(self) -> StorageEngine:
        return self._storage or get_storage()

    def register_effect_handler(self, kind: str, handler: EffectHandler) -> None:
        """Register a handler for a durable effect `kind` (e.g., 'webhook_notify', 'obsidian_sync')."""
        self._effect_handlers[kind] = handler
        self.board.report(f"effect:{kind}", "ok", "Handler registered")
        logger.debug("Registered durable effect handler for kind '%s'", kind)

    def enqueue_effect(self, kind: str, key: str, payload: Dict[str, Any]) -> DurableEffect:
        """Enqueue or coalesce a durable side-effect in SQLite."""
        return self.storage.enqueue_effect(kind=kind, effect_key=key, payload=payload)

    async def process_due_effects(self, now_iso: Optional[str] = None, limit: int = 20) -> Dict[str, int]:
        """Process due PENDING effects in order, applying exponential backoff on failure."""
        due = self.storage.list_due_effects(now_iso=now_iso, limit=limit)
        succeeded = 0
        failed = 0

        for eff in due:
            handler = self._effect_handlers.get(eff.kind)
            if handler is None:
                err = f"No handler registered for effect kind '{eff.kind}'"
                updated = self.storage.record_effect_failure(
                    eff.id, err, max_attempts=settings.effect_max_attempts
                )
                failed += 1
                if updated and updated.status == "FAILED":
                    self.board.report(f"effect:{eff.kind}", "error", f"Effect {eff.effect_key} failed: {err}")
                continue

            try:
                if inspect.iscoroutinefunction(handler):
                    await handler(eff.payload_json)
                else:
                    res = handler(eff.payload_json)
                    if asyncio.iscoroutine(res):
                        await res
                self.storage.mark_effect_done(eff.id)
                self.board.report(f"effect:{eff.kind}", "ok", f"Last succeeded: {eff.effect_key}")
                succeeded += 1
            except Exception as exc:
                failed += 1
                updated = self.storage.record_effect_failure(
                    eff.id,
                    str(exc),
                    max_attempts=settings.effect_max_attempts,
                )
                logger.warning(
                    "Effect %s (%s:%s) attempt failed: %s",
                    eff.id,
                    eff.kind,
                    eff.effect_key,
                    exc,
                )
                if updated and updated.status == "FAILED":
                    self.board.report(
                        f"effect:{eff.kind}",
                        "error",
                        f"Exhausted {updated.attempts} retries on key '{eff.effect_key}': {exc}",
                    )
                else:
                    self.board.report(
                        f"effect:{eff.kind}",
                        "warn",
                        f"Retrying key '{eff.effect_key}' after transient error: {exc}",
                    )

        return {"processed": len(due), "succeeded": succeeded, "failed": failed}

    async def run_pass(self, now_dt: Optional[datetime] = None) -> Dict[str, Any]:
        """Execute one atomic maintenance pass (Effects -> Segmenter -> Audio Inbox)."""
        async with self._pass_lock:
            now = now_dt or datetime.now(timezone.utc)
            now_iso = now.isoformat()

            # 1. Process due durable side-effects
            effects_res = await self.process_due_effects(now_iso=now_iso)

            # 2. Evaluate due silence/span episode segmentation
            from backend.memory_core.segmenter import get_segmenter

            closed_ep = await get_segmenter().inspect_and_segment(force_flush=False, now_dt=now)

            # 3. Scan `data/audio_inbox/` for dropped audio/transcript files
            from backend.ingest.file_watcher import get_inbox_processor

            inbox_episodes = await get_inbox_processor().scan_inbox_once()

            self._passes_completed += 1
            self._last_pass_at = now_iso
            self.board.report("runtime:passes", "ok", f"Completed pass #{self._passes_completed}")

            return {
                "pass_number": self._passes_completed,
                "timestamp": now_iso,
                "effects": effects_res,
                "auto_closed_episode_id": closed_ep.id if closed_ep else None,
                "inbox_episodes_created": [ep.id for ep in inbox_episodes],
            }

    async def _background_loop(self) -> None:
        interval = max(0.5, float(settings.runtime_pass_interval_sec))
        while self._running:
            try:
                await self.run_pass()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Runtime background pass error: %s", exc, exc_info=True)
                self.board.report("runtime:passes", "error", str(exc))
            await asyncio.sleep(interval)

    async def start(self, start_background_loop: Optional[bool] = None) -> None:
        """Start plugins, ingest adapters, and optional background pass loop."""
        if self._running:
            return
        self._running = True

        await self.pm.startup_all()

        for name, adapter in self.registry.get_ingest_adapters().items():
            try:
                await adapter.start()
                self.board.report(f"adapter:{name}", "ok", "Running")
            except Exception as exc:
                logger.error("IngestAdapter '%s' failed to start: %s", name, exc, exc_info=True)
                self.board.report(f"adapter:{name}", "error", str(exc))

        should_loop = (
            start_background_loop
            if start_background_loop is not None
            else settings.enable_background_passes
        )
        if should_loop:
            self._bg_task = asyncio.create_task(self._background_loop())

    async def stop(self) -> None:
        """Gracefully stop background passes, ingest adapters, and plugins."""
        self._running = False
        if self._bg_task is not None:
            self._bg_task.cancel()
            try:
                await self._bg_task
            except asyncio.CancelledError:
                pass
            self._bg_task = None

        for name, adapter in self.registry.get_ingest_adapters().items():
            try:
                await adapter.stop()
            except Exception as exc:
                logger.error("IngestAdapter '%s' failed to stop: %s", name, exc, exc_info=True)

        await self.pm.shutdown_all()

    def get_kernel_status(self) -> Dict[str, Any]:
        """Return attention-first micro-kernel introspection snapshot."""
        return {
            "running": self._running,
            "passes_completed": self._passes_completed,
            "last_pass_at": self._last_pass_at,
            "hud_attention_policy": settings.hud_attention_policy,
            "health": self.board.get_summary(),
            "providers": self.registry.list_providers(),
            "plugins": self.pm.list_plugins(),
            "event_bus": event_bus.list_subscriptions(),
            "pending_effects_count": len(self.storage.list_effects(status="PENDING")),
            "failed_effects": [e.model_dump() for e in self.storage.list_effects(status="FAILED", limit=10)],
        }


runtime_manager = RuntimeManager()
