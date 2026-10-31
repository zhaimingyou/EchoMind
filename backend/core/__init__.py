"""Micro-kernel core abstractions, event bus, and plugin manager."""
from backend.core.event_bus import EventBus, event_bus
from backend.core.plugin_manager import EchoMindPlugin, PluginManager, hook, plugin_manager

__all__ = [
    "EventBus",
    "event_bus",
    "EchoMindPlugin",
    "PluginManager",
    "hook",
    "plugin_manager",
]
