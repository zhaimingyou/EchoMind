"""Dynamic Plugin SDK, Narrow PluginContext, and Router Mounting for EchoMind.

Absorbs key architectural patterns from `deepseek-ai/dsh-superagent-prototype`:
1. **Narrow PluginContext (`ScopedKVStore`, `report_health`, `enqueue_effect`, `ingest_utterance`)**:
   Each plugin interacts with the host through a capability-scoped context bound to its
   `plugin_name`. If a plugin is disabled or unregistered, its context writes become no-ops.
2. **Pre-execution `@filter_hook` and Post-event `@hook`**:
   Plugins can intercept/modify utterances and episodes before persistence or subscribe to
   asynchronous domain events.
3. **Custom FastAPI `APIRouter` mounting (`get_router()`)**:
   Plugins can expose hardware- or domain-specific endpoints under `/api/v1/ext/{plugin.name}`.
4. **Dual Discovery**:
   Supports both local `plugins/*.py` drop-in files and `pip` package `entry_points(group="echomind.plugins")`.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
import importlib.metadata
import importlib.util
import inspect
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Set, TYPE_CHECKING
from backend.config import settings
from backend.core.event_bus import EventBus, event_bus
from backend.core.registry import ProviderRegistry, registry
from backend.storage.database import StorageEngine, get_storage
from backend.storage.models import DurableEffect, Utterance

if TYPE_CHECKING:
    from fastapi import APIRouter, FastAPI

logger = logging.getLogger("echomind.plugins")


def hook(topic: str) -> Callable:
    """Decorator to mark a plugin method as an EventBus subscriber for `topic`."""
    def decorator(func: Callable) -> Callable:
        setattr(func, "_echomind_hook_topic", topic)
        return func
    return decorator


def filter_hook(stage: str, priority: int = 100) -> Callable:
    """Decorator to mark a plugin method as a pre-execution filter for `stage`.

    Supported stages:
    - `'utterance.before_save'`: receives `Utterance`, returns modified `Utterance` or `None` to drop.
    - `'episode.before_extract'`: receives `List[Utterance]`, returns modified list.
    - `'episode.before_save'`: receives `EpisodeCognitiveResult`, returns modified result.
    """
    def decorator(func: Callable) -> Callable:
        setattr(func, "_echomind_filter_stage", stage)
        setattr(func, "_echomind_filter_priority", priority)
        return func
    return decorator


class ScopedKVStore:
    """Namespace-isolated key-value store bound to a single `plugin_name`."""

    def __init__(
        self,
        plugin_name: str,
        storage: StorageEngine,
        is_active_fn: Callable[[], bool],
    ) -> None:
        self._plugin_name = plugin_name
        self._storage = storage
        self._is_active = is_active_fn

    def get(self, key: str, default: Any = None) -> Any:
        return self._storage.get_plugin_kv(self._plugin_name, key, default=default)

    def set(self, key: str, value: Any) -> bool:
        if not self._is_active():
            logger.warning("Ignored KV write from inactive plugin '%s'", self._plugin_name)
            return False
        self._storage.set_plugin_kv(self._plugin_name, key, value)
        return True

    def delete(self, key: str) -> bool:
        if not self._is_active():
            return False
        self._storage.delete_plugin_kv(self._plugin_name, key)
        return True

    def keys(self) -> List[str]:
        return self._storage.list_plugin_kv_keys(self._plugin_name)


@dataclass
class HealthEntry:
    """Health status claimed by a plugin or effect kind on the HealthBoard."""

    source: str
    status: Literal["ok", "warn", "error"] = "ok"
    message: str = ""
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class HealthBoard:
    """Tracks component health and surfaces only items needing human attention first."""

    def __init__(self) -> None:
        self._entries: Dict[str, HealthEntry] = {}

    def report(
        self,
        source: str,
        status: Literal["ok", "warn", "error"],
        message: str = "",
    ) -> None:
        self._entries[source] = HealthEntry(
            source=source,
            status=status,
            message=message,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    def remove(self, source: str) -> None:
        self._entries.pop(source, None)

    def get_summary(self) -> Dict[str, Any]:
        """Return attention-first health report (inspired by dsh-superagent Panel)."""
        needs_attention = [
            {
                "source": e.source,
                "status": e.status,
                "message": e.message,
                "updated_at": e.updated_at,
            }
            for e in self._entries.values()
            if e.status in ("warn", "error")
        ]
        healthy = [e.source for e in self._entries.values() if e.status == "ok"]
        return {
            "healthy_count": len(healthy),
            "healthy_sources": sorted(healthy),
            "needs_attention_count": len(needs_attention),
            "needs_attention": needs_attention,
        }


health_board = HealthBoard()


class PluginContext:
    """Narrow capability facade injected into an `EchoMindPlugin` instance."""

    def __init__(
        self,
        plugin_name: str,
        storage: StorageEngine,
        bus: EventBus,
        provider_registry: ProviderRegistry,
        board: HealthBoard,
        is_active_fn: Callable[[], bool],
        plugin_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.plugin_name = plugin_name
        self.settings = settings
        self.storage = storage
        self.event_bus = bus
        self.registry = provider_registry
        self._board = board
        self._is_active = is_active_fn
        self.plugin_config: Dict[str, Any] = plugin_config or {}
        self.kv = ScopedKVStore(plugin_name=plugin_name, storage=storage, is_active_fn=is_active_fn)

    def report_health(self, status: Literal["ok", "warn", "error"], message: str = "") -> None:
        """Report health status for this plugin. Ignored if the plugin was unregistered."""
        if not self._is_active():
            return
        self._board.report(f"plugin:{self.plugin_name}", status, message)

    def enqueue_effect(self, kind: str, key: str, payload: Dict[str, Any]) -> Optional[DurableEffect]:
        """Enqueue a durable side-effect coalesced by `(kind, key)`."""
        if not self._is_active():
            return None
        return self.storage.enqueue_effect(kind=kind, effect_key=key, payload=payload)

    async def ingest_utterance(
        self,
        text: str,
        speaker_role: str = "HOST",
        device_id: Optional[str] = None,
        emotion_tag: str = "NEUTRAL",
        acoustic_event: str = "NONE",
        duration_ms: int = 1500,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Utterance]:
        """Standard entry point for hardware/source plugins to inject an Utterance through the filter pipeline."""
        if not self._is_active():
            return None
        utt = Utterance(
            text_content=text,
            speaker_role=speaker_role,
            device_id=device_id or f"plugin_{self.plugin_name}",
            emotion_tag=emotion_tag,
            acoustic_event=acoustic_event,
            duration_ms=duration_ms,
            metadata_json=metadata or {"source_plugin": self.plugin_name},
        )
        filtered = await self.event_bus.apply_filters("utterance.before_save", utt)
        if filtered is None:
            return None
        self.storage.insert_utterance(filtered)
        await self.event_bus.publish("utterance.created", filtered.model_dump())
        return filtered


class EchoMindPlugin:
    """Base class for all EchoMind extensions (HUD drivers, CRM sync, domain filters, custom hardware routes)."""

    name: str = "unnamed_plugin"
    version: str = "0.1.0"
    description: str = ""
    author: str = "community"
    enabled: bool = True
    context: Optional[PluginContext] = None

    def on_load(self) -> None:
        """Synchronous lifecycle hook called when the plugin is registered (v0.1 compatible)."""
        pass

    async def on_startup(self, ctx: PluginContext) -> None:
        """Async lifecycle hook called during application startup with a scoped `PluginContext`."""
        pass

    async def on_shutdown(self) -> None:
        """Async lifecycle hook called during application shutdown."""
        pass

    def get_router(self) -> Optional[Any]:
        """Optional FastAPI `APIRouter` to mount at `/api/v1/ext/{self.name}`."""
        return None


class PluginManager:
    """Discovers, loads, binds, and manages lifecycle of `EchoMindPlugin` extensions."""

    def __init__(
        self,
        bus: EventBus = event_bus,
        storage: Optional[StorageEngine] = None,
        provider_registry: ProviderRegistry = registry,
        board: HealthBoard = health_board,
    ) -> None:
        self.bus = bus
        self._storage = storage
        self.registry = provider_registry
        self.board = board
        self._plugins: Dict[str, EchoMindPlugin] = {}
        self._mounted_routers: Set[str] = set()
        self.bus.set_error_reporter(self._on_bus_error)

    @property
    def storage(self) -> StorageEngine:
        return self._storage or get_storage()

    def _on_bus_error(self, owner: str, error_msg: str) -> None:
        if owner and owner != "core":
            self.board.report(f"plugin:{owner}", "error", error_msg)

    def is_plugin_active(self, plugin_name: str) -> bool:
        p = self._plugins.get(plugin_name)
        return bool(p and p.enabled)

    def register_plugin(
        self,
        plugin: EchoMindPlugin,
        plugin_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register a plugin instance, inject its Narrow `PluginContext`, and bind all `@hook` and `@filter_hook` methods."""
        if not plugin.enabled:
            logger.info("Skipping disabled plugin: %s", plugin.name)
            return

        ctx = PluginContext(
            plugin_name=plugin.name,
            storage=self.storage,
            bus=self.bus,
            provider_registry=self.registry,
            board=self.board,
            is_active_fn=lambda name=plugin.name: self.is_plugin_active(name),
            plugin_config=plugin_config,
        )
        plugin.context = ctx
        self._plugins[plugin.name] = plugin
        self.board.report(f"plugin:{plugin.name}", "ok", "Loaded")

        try:
            plugin.on_load()
        except Exception as exc:
            logger.error("Plugin '%s' on_load failed: %s", plugin.name, exc, exc_info=True)
            self.board.report(f"plugin:{plugin.name}", "error", f"on_load failed: {exc}")

        for _, method in inspect.getmembers(plugin, predicate=inspect.ismethod):
            topic = getattr(method, "_echomind_hook_topic", None)
            if topic:
                self.bus.subscribe(topic, method, owner=plugin.name)
                logger.info("Plugin '%s' (v%s) hooked into event '%s'", plugin.name, plugin.version, topic)

            filter_stage = getattr(method, "_echomind_filter_stage", None)
            if filter_stage:
                priority = int(getattr(method, "_echomind_filter_priority", 100))
                self.bus.subscribe_filter(filter_stage, method, priority=priority, owner=plugin.name)
                logger.info(
                    "Plugin '%s' (v%s) registered filter on '%s' (priority=%d)",
                    plugin.name,
                    plugin.version,
                    filter_stage,
                    priority,
                )

    def unregister_plugin(self, plugin_name: str) -> bool:
        """Unregister a plugin, detach its hooks/filters, and invalidate its Narrow `PluginContext`."""
        plugin = self._plugins.pop(plugin_name, None)
        if not plugin:
            return False
        plugin.enabled = False
        self.bus.unsubscribe_owner(plugin_name)
        self.board.remove(f"plugin:{plugin_name}")
        return True

    def discover_and_load(
        self,
        plugins_dir: Path = Path("./plugins"),
        load_entry_points: bool = True,
    ) -> List[str]:
        """Dynamically scan `plugins_dir` and `echomind.plugins` pip entry_points."""
        loaded_names: List[str] = []
        if plugins_dir.exists():
            for py_file in sorted(plugins_dir.glob("*.py")):
                if py_file.name.startswith("_"):
                    continue
                try:
                    spec = importlib.util.spec_from_file_location(f"plugins.{py_file.stem}", py_file)
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        for _, obj in inspect.getmembers(module, predicate=inspect.isclass):
                            if issubclass(obj, EchoMindPlugin) and obj is not EchoMindPlugin:
                                instance = obj()
                                if instance.name not in self._plugins:
                                    self.register_plugin(instance)
                                    loaded_names.append(instance.name)
                except Exception as exc:
                    logger.error("Failed to load plugin from %s: %s", py_file, exc, exc_info=True)
                    self.board.report(f"plugin_file:{py_file.name}", "error", str(exc))

        if load_entry_points:
            try:
                eps = importlib.metadata.entry_points()
                selected = eps.select(group="echomind.plugins") if hasattr(eps, "select") else eps.get("echomind.plugins", [])
                for ep in selected:
                    try:
                        plugin_cls = ep.load()
                        if inspect.isclass(plugin_cls) and issubclass(plugin_cls, EchoMindPlugin):
                            instance = plugin_cls()
                            if instance.name not in self._plugins:
                                self.register_plugin(instance)
                                loaded_names.append(instance.name)
                    except Exception as exc:
                        logger.error("Failed to load entry_point plugin '%s': %s", ep.name, exc)
                        self.board.report(f"entry_point:{ep.name}", "error", str(exc))
            except Exception:
                pass

        return loaded_names

    def mount_plugin_routers(self, app: Any) -> List[str]:
        """Mount custom `APIRouter` from plugins onto `/api/v1/ext/{plugin.name}`."""
        mounted: List[str] = []
        for name, plugin in self._plugins.items():
            if not plugin.enabled or name in self._mounted_routers:
                continue
            try:
                router = plugin.get_router()
                if router is not None:
                    prefix = f"/api/v1/ext/{name}"
                    app.include_router(router, prefix=prefix, tags=[f"Plugin: {name}"])
                    self._mounted_routers.add(name)
                    mounted.append(prefix)
                    logger.info("Mounted custom router for plugin '%s' at '%s'", name, prefix)
            except Exception as exc:
                logger.error("Failed to mount router for plugin '%s': %s", name, exc, exc_info=True)
                self.board.report(f"plugin:{name}", "error", f"Router mount failed: {exc}")
        return mounted

    async def startup_all(self) -> None:
        """Invoke `await plugin.on_startup(ctx)` for all registered plugins with error isolation."""
        for name, plugin in list(self._plugins.items()):
            if not plugin.enabled or plugin.context is None:
                continue
            try:
                await plugin.on_startup(plugin.context)
            except Exception as exc:
                logger.error("Plugin '%s' on_startup failed: %s", name, exc, exc_info=True)
                self.board.report(f"plugin:{name}", "error", f"on_startup failed: {exc}")

    async def shutdown_all(self) -> None:
        """Invoke `await plugin.on_shutdown()` for all registered plugins."""
        for name, plugin in list(self._plugins.items()):
            try:
                await plugin.on_shutdown()
            except Exception as exc:
                logger.error("Plugin '%s' on_shutdown failed: %s", name, exc, exc_info=True)

    def get_plugin(self, name: str) -> Optional[EchoMindPlugin]:
        return self._plugins.get(name)

    def list_plugins(self) -> List[Dict[str, Any]]:
        """Return detailed metadata for all registered plugins."""
        result: List[Dict[str, Any]] = []
        for p in self._plugins.values():
            hooks: List[str] = []
            filters: List[str] = []
            for _, method in inspect.getmembers(p, predicate=inspect.ismethod):
                t = getattr(method, "_echomind_hook_topic", None)
                if t:
                    hooks.append(t)
                f = getattr(method, "_echomind_filter_stage", None)
                if f:
                    filters.append(f)
            has_router = False
            try:
                has_router = p.get_router() is not None
            except Exception:
                has_router = False
            result.append(
                {
                    "name": p.name,
                    "version": p.version,
                    "description": p.description,
                    "author": p.author,
                    "enabled": p.enabled,
                    "hooks": hooks,
                    "filters": filters,
                    "has_custom_router": has_router,
                    "router_prefix": f"/api/v1/ext/{p.name}" if has_router else None,
                }
            )
        return result


plugin_manager = PluginManager()
