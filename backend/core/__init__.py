"""EchoMind Pluggable Micro-Kernel Core (`backend/core/`).

Exposes:
- Pluggable Contracts (`VADProvider`, `ASRProvider`, `SpeakerProvider`, `ExtractorProvider`, `EmbeddingProvider`, `IngestAdapter`)
- Centralized `ProviderRegistry` (`registry`)
- Bidirectional `EventBus` (`event_bus`) with pre-execution `@filter_hook` and post-event `@hook`
- Capability-scoped `EchoMindPlugin`, `PluginContext`, `ScopedKVStore`, and `HealthBoard` (`plugin_manager`, `health_board`)
- Autonomous `RuntimeManager` (`runtime_manager`) with `Passes` loop and durable `Effects` queue
"""
from backend.core.event_bus import EventBus, event_bus
from backend.core.interfaces import (
    ASRProvider,
    EmbeddingProvider,
    ExtractorProvider,
    IngestAdapter,
    SpeakerMatchResult,
    SpeakerProvider,
    TranscriptionResult,
    VADProvider,
)
from backend.core.plugin_manager import (
    EchoMindPlugin,
    HealthBoard,
    PluginContext,
    PluginManager,
    ScopedKVStore,
    filter_hook,
    health_board,
    hook,
    plugin_manager,
)
from backend.core.registry import ProviderRegistry, registry
from backend.core.runtime import RuntimeManager, runtime_manager

__all__ = [
    "ASRProvider",
    "EchoMindPlugin",
    "EmbeddingProvider",
    "EventBus",
    "ExtractorProvider",
    "HealthBoard",
    "IngestAdapter",
    "PluginContext",
    "PluginManager",
    "ProviderRegistry",
    "RuntimeManager",
    "ScopedKVStore",
    "SpeakerMatchResult",
    "SpeakerProvider",
    "TranscriptionResult",
    "VADProvider",
    "event_bus",
    "filter_hook",
    "health_board",
    "hook",
    "plugin_manager",
    "registry",
    "runtime_manager",
]
