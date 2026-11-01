"""Secondary Development Template Plugin (`plugins/example_custom_dev_template.py`).

Demonstrates EchoMind v0.2 Micro-Kernel capabilities for 3rd-party developers:
1. Pre-save filter (`@filter_hook("utterance.before_save")`): PII phone number redaction & domain jargon correction.
2. Pre-save episode enrichment (`@filter_hook("episode.before_save")`): Injecting vertical domain `custom_metadata`.
3. Post-event hook (`@hook("episode.closed")`) + Narrow `PluginContext` (`ctx.kv`, `ctx.report_health`).
4. Custom FastAPI `APIRouter` (`get_router()`) automatically mounted at `/api/v1/ext/dev_template/*`.
"""
import re
from typing import Any, Dict, Optional
from backend.core.plugin_manager import EchoMindPlugin, PluginContext, filter_hook, hook
from backend.memory_core.schemas import EpisodeCognitiveResult
from backend.storage.models import Utterance

_PHONE_REGEX = re.compile(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)")


class DevTemplatePlugin(EchoMindPlugin):
    """Reference template for building vertical domain or hardware extensions on EchoMind."""

    name = "dev_template"
    version = "0.2.0"
    description = "二次开发样板插件：演示前置手机号脱敏、术语纠错、行业扩展元数据注入、隔离 KV 存储与自定义 API 路由"
    author = "EchoMind Community"
    enabled = True

    def __init__(self) -> None:
        self._router: Optional[Any] = None
        self.redacted_count: int = 0
        self.custom_jargon_map: Dict[str, str] = {
            "极米同款": "极米记得 (MemoMind)",
        }

    async def on_startup(self, ctx: PluginContext) -> None:
        saved_jargon = ctx.kv.get("jargon_map")
        if isinstance(saved_jargon, dict):
            self.custom_jargon_map.update(saved_jargon)
        ctx.report_health("ok", f"Started with {len(self.custom_jargon_map)} jargon rules")

    @filter_hook("utterance.before_save", priority=20)
    def preprocess_utterance(self, utt: Utterance) -> Optional[Utterance]:
        """Redact 11-digit mobile numbers and apply domain jargon replacements before DB save."""
        txt = utt.text_content
        if txt.strip() == "[IGNORE_THIS_NOISE]":
            # Returning None drops the utterance from the pipeline completely
            return None

        for src, dst in self.custom_jargon_map.items():
            if src in txt:
                txt = txt.replace(src, dst)

        redacted_txt, n_subs = _PHONE_REGEX.subn(r"\1****\2", txt)
        if n_subs > 0:
            self.redacted_count += n_subs
            utt.metadata_json["pii_redacted"] = True

        utt.text_content = redacted_txt
        return utt

    @filter_hook("episode.before_save", priority=50)
    def enrich_episode_metadata(self, cog: EpisodeCognitiveResult) -> EpisodeCognitiveResult:
        """Attach vertical-domain metadata before the Episode is saved to SQLite."""
        cog.custom_metadata.setdefault("processed_by_plugin", self.name)
        cog.custom_metadata.setdefault("action_items_count", len(cog.action_items))
        return cog

    @hook("episode.closed")
    async def on_episode_closed(self, payload: Dict[str, Any]) -> None:
        if self.context is not None:
            total = int(self.context.kv.get("episodes_observed", 0)) + 1
            self.context.kv.set("episodes_observed", total)
            self.context.report_health("ok", f"Observed {total} episodes")

    def get_router(self) -> Optional[Any]:
        if self._router is None:
            try:
                from fastapi import APIRouter
            except ImportError:
                return None

            router = APIRouter()

            @router.get("/info")
            def get_plugin_info() -> Dict[str, Any]:
                observed = self.context.kv.get("episodes_observed", 0) if self.context else 0
                return {
                    "plugin": self.name,
                    "version": self.version,
                    "redacted_phone_numbers": self.redacted_count,
                    "episodes_observed": observed,
                    "jargon_rules": self.custom_jargon_map,
                }

            @router.post("/jargon")
            def add_jargon_rule(rule: Dict[str, str]) -> Dict[str, Any]:
                self.custom_jargon_map.update(rule)
                if self.context is not None:
                    self.context.kv.set("jargon_map", self.custom_jargon_map)
                return {"status": "updated", "jargon_rules": self.custom_jargon_map}

            self._router = router
        return self._router
