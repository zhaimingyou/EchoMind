"""Dynamic plugin system for EchoMind.

Third-party developers can drop a Python file into `plugins/` and subclass
`EchoMindPlugin` with `@hook("episode.closed")` methods to extend EchoMind.
"""
import importlib.util
import inspect
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List
from backend.core.event_bus import EventBus, event_bus

logger = logging.getLogger("echomind.plugins")


def hook(topic: str) -> Callable:
    """Decorator to mark a plugin method as an EventBus subscriber for `topic`."""
    def decorator(func: Callable) -> Callable:
        setattr(func, "_echomind_hook_topic", topic)
        return func
    return decorator


class EchoMindPlugin:
    """Base class for all EchoMind extensions (HUD drivers, CRM sync, custom extractors)."""

    name: str = "unnamed_plugin"
    version: str = "0.1.0"
    description: str = ""
    enabled: bool = True

    def on_load(self) -> None:
        """Optional lifecycle hook called when the plugin is registered."""
        pass


class PluginManager:
    """Discovers, loads, and binds plugins to the EventBus."""

    def __init__(self, bus: EventBus = event_bus) -> None:
        self.bus = bus
        self._plugins: Dict[str, EchoMindPlugin] = {}

    def register_plugin(self, plugin: EchoMindPlugin) -> None:
        """Register a plugin instance and bind all `@hook` decorated methods."""
        if not plugin.enabled:
            logger.info("Skipping disabled plugin: %s", plugin.name)
            return

        self._plugins[plugin.name] = plugin
        plugin.on_load()

        for _, method in inspect.getmembers(plugin, predicate=inspect.ismethod):
            topic = getattr(method, "_echomind_hook_topic", None)
            if topic:
                self.bus.subscribe(topic, method)
                logger.info("Plugin '%s' (v%s) hooked into '%s'", plugin.name, plugin.version, topic)

    def discover_and_load(self, plugins_dir: Path = Path("./plugins")) -> List[str]:
        """Dynamically scan `plugins_dir` and register all `EchoMindPlugin` subclasses."""
        loaded_names: List[str] = []
        if not plugins_dir.exists():
            return loaded_names

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
                            self.register_plugin(instance)
                            loaded_names.append(instance.name)
            except Exception as exc:
                logger.error("Failed to load plugin from %s: %s", py_file, exc, exc_info=True)
        return loaded_names

    def list_plugins(self) -> List[Dict[str, Any]]:
        """Return metadata for all registered plugins."""
        return [
            {
                "name": p.name,
                "version": p.version,
                "description": p.description,
                "enabled": p.enabled,
            }
            for p in self._plugins.values()
        ]


plugin_manager = PluginManager()
