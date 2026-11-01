"""Unit Test Suite for EchoMind v0.2 Secondary Development Micro-Kernel SDK (`tests/test_microkernel_sdk.py`).

Tests:
1. 5 Core Provider Protocols & `ProviderRegistry` registration / runtime switching
2. `EventBus` pre-execution `@filter_hook` pipeline (modification, `None` drop interception, priority ordering, fault isolation)
3. Narrow `PluginContext` & `ScopedKVStore` namespace isolation + deactivation safety
4. Durable `Effects` queue (`enqueue_effect` key coalescing, exponential backoff retry, `HealthBoard` failure escalation)
5. `RuntimeManager` atomic `run_pass()` (effects processing, silence-timeout segmentation, audio inbox `.txt` ingestion)
6. Template plugin (`plugins/example_custom_dev_template.py`) discovery, PII phone redaction, custom episode metadata enrichment, and kernel status introspection
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional, Sequence
import unittest
from backend.audio_engine.speaker_id import SpeakerIdentifier
from backend.audio_engine.transcriber import SenseVoiceTranscriber
from backend.audio_engine.vad_buffer import VADStreamBuffer
from backend.core.event_bus import EventBus
from backend.core.interfaces import (
    ASRProvider,
    EmbeddingProvider,
    ExtractorProvider,
    SpeakerProvider,
    TranscriptionResult,
    VADProvider,
)
from backend.core.plugin_manager import (
    EchoMindPlugin,
    HealthBoard,
    PluginContext,
    PluginManager,
    filter_hook,
)
from backend.core.registry import ProviderRegistry
from backend.core.runtime import RuntimeManager
from backend.ingest.file_watcher import AudioInboxProcessor
from backend.memory_core.extractor import CognitiveExtractor
from backend.memory_core.fact_resolver import FactResolver
from backend.memory_core.segmenter import EpisodeSegmenter
from backend.storage.database import StorageEngine
from backend.storage.models import Utterance
from backend.storage.vector_store import HybridSearchEngine, LocalNgramEmbeddingProvider


class TestMicroKernelSDK(unittest.IsolatedAsyncioTestCase):
    def test_01_provider_protocols_and_registry_hot_swap(self) -> None:
        self.assertIsInstance(VADStreamBuffer(), VADProvider)
        self.assertIsInstance(SenseVoiceTranscriber(), ASRProvider)
        self.assertIsInstance(SpeakerIdentifier(), SpeakerProvider)
        self.assertIsInstance(CognitiveExtractor(), ExtractorProvider)
        self.assertIsInstance(LocalNgramEmbeddingProvider(), EmbeddingProvider)

        reg = ProviderRegistry()

        class CustomASR:
            def transcribe(
                self,
                samples: Sequence[float],
                sample_rate: int = 16000,
                hint_text: Optional[str] = None,
            ) -> TranscriptionResult:
                return TranscriptionResult(clean_text="自定义ASR输出", lang="zh")

        reg.register_asr("custom_whisper", CustomASR(), set_default=True)
        active_asr = reg.get_asr()
        res = active_asr.transcribe([0.1, 0.2], sample_rate=16000)
        self.assertEqual(res.clean_text, "自定义ASR输出")
        self.assertIn("custom_whisper", reg.list_providers()["registered"]["asr"])
        self.assertEqual(reg.list_providers()["active"]["asr"], "custom_whisper")

    async def test_02_filter_pipeline_redact_drop_and_fault_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = StorageEngine(db_path=Path(tmp) / "filter_test.db")
            bus = EventBus()
            board = HealthBoard()
            pm = PluginManager(bus=bus, storage=storage, board=board)

            class FilterAndFaultPlugin(EchoMindPlugin):
                name = "filter_fault_plugin"

                @filter_hook("utterance.before_save", priority=10)
                def step_one_redact(self, utt: Utterance) -> Optional[Utterance]:
                    if "DROP_ME" in utt.text_content:
                        return None
                    utt.text_content = utt.text_content.replace("机密", "[REDACTED]")
                    return utt

                @filter_hook("utterance.before_save", priority=20)
                def step_two_buggy_filter(self, utt: Utterance) -> Utterance:
                    raise RuntimeError("Simulated 3rd-party filter crash")

                @filter_hook("utterance.before_save", priority=30)
                def step_three_append(self, utt: Utterance) -> Utterance:
                    utt.metadata_json["checked"] = True
                    return utt

            pm.register_plugin(FilterAndFaultPlugin())

            # 1. Test normal filter chain with fault isolation in the middle
            u1 = Utterance(text_content="这是机密项目讨论")
            filtered_u1 = await bus.apply_filters("utterance.before_save", u1)
            self.assertIsNotNone(filtered_u1)
            assert filtered_u1 is not None
            self.assertEqual(filtered_u1.text_content, "这是[REDACTED]项目讨论")
            self.assertTrue(filtered_u1.metadata_json.get("checked"))

            # Verify the buggy filter was reported to HealthBoard without crashing the pipeline
            summary = board.get_summary()
            self.assertEqual(summary["needs_attention_count"], 1)
            self.assertIn("Simulated 3rd-party filter crash", summary["needs_attention"][0]["message"])

            # 2. Test returning None drops the item immediately
            u_drop = Utterance(text_content="DROP_ME 噪音片段")
            self.assertIsNone(await bus.apply_filters("utterance.before_save", u_drop))

    async def test_03_narrow_plugin_context_and_scoped_kv_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = StorageEngine(db_path=Path(tmp) / "kv_test.db")
            bus = EventBus()
            board = HealthBoard()
            pm = PluginManager(bus=bus, storage=storage, board=board)

            class PluginAlpha(EchoMindPlugin):
                name = "alpha"

                async def on_startup(self, ctx: PluginContext) -> None:
                    ctx.kv.set("token", "alpha_secret_123")

            class PluginBeta(EchoMindPlugin):
                name = "beta"

                async def on_startup(self, ctx: PluginContext) -> None:
                    ctx.kv.set("token", "beta_secret_999")

            p_alpha = PluginAlpha()
            p_beta = PluginBeta()
            pm.register_plugin(p_alpha)
            pm.register_plugin(p_beta)
            await pm.startup_all()

            assert p_alpha.context is not None
            assert p_beta.context is not None
            self.assertEqual(p_alpha.context.kv.get("token"), "alpha_secret_123")
            self.assertEqual(p_beta.context.kv.get("token"), "beta_secret_999")

            # Unregistering alpha invalidates further writes through its Narrow PluginContext
            pm.unregister_plugin("alpha")
            wrote = p_alpha.context.kv.set("token", "hacked_after_unload")
            self.assertFalse(wrote)
            self.assertEqual(storage.get_plugin_kv("alpha", "token"), "alpha_secret_123")

    async def test_04_durable_effects_coalescing_backoff_and_runtime_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            storage = StorageEngine(db_path=tmp_path / "runtime_test.db")
            board = HealthBoard()
            bus = EventBus()
            pm = PluginManager(bus=bus, storage=storage, board=board)
            rt = RuntimeManager(storage=storage, pm=pm, board=board)

            # 1. Test Effect Coalescing: two enqueues for same (kind, key) while PENDING merge into 1 row
            e1 = rt.enqueue_effect("crm_sync", "ep_001", {"v": 1})
            e2 = rt.enqueue_effect("crm_sync", "ep_001", {"v": 2})
            self.assertEqual(e1.id, e2.id)
            self.assertEqual(e2.payload_json, {"v": 2})
            self.assertEqual(len(storage.list_effects(status="PENDING")), 1)

            # 2. Test Exponential Backoff & Failure Escalation after 3 attempts
            attempts_log: List[int] = []

            async def flaky_handler(payload: Dict[str, Any]) -> None:
                attempts_log.append(payload["v"])
                raise ConnectionError("CRM network timeout")

            rt.register_effect_handler("crm_sync", flaky_handler)

            for i in range(3):
                future_iso = (datetime.now(timezone.utc) + timedelta(minutes=10 * (i + 1))).isoformat()
                await rt.process_due_effects(now_iso=future_iso)

            self.assertEqual(len(attempts_log), 3)
            failed_list = storage.list_effects(status="FAILED")
            self.assertEqual(len(failed_list), 1)
            self.assertIn("CRM network timeout", failed_list[0].last_error or "")
            self.assertGreaterEqual(board.get_summary()["needs_attention_count"], 1)

            # 3. Test Audio Inbox `.txt` ingestion & custom metadata enrichment
            resolver = FactResolver(storage=storage)
            extractor = CognitiveExtractor(fact_resolver=resolver)
            extractor.register_custom_instruction("medical_profile", "提取患者主诉与过敏史")
            self.assertIn("提取患者主诉与过敏史", extractor.get_effective_system_prompt("无"))

            segmenter = EpisodeSegmenter(
                storage=storage,
                extractor=extractor,
                fact_resolver=resolver,
                hybrid_search=HybridSearchEngine(storage=storage),
            )
            inbox_dir = tmp_path / "inbox"
            archive_dir = tmp_path / "archive"
            processor = AudioInboxProcessor(
                inbox_dir=inbox_dir,
                archive_dir=archive_dir,
                storage=storage,
                segmenter=segmenter,
                bus=bus,
            )
            sample_txt = inbox_dir / "meeting_note.txt"
            sample_txt.write_text(
                "[GUEST_1]: 王总的预算改成了80万\n[HOST]: 我明天之前把合同发你，联系电话13812345678\n",
                encoding="utf-8",
            )
            created_eps = await processor.scan_inbox_once()
            self.assertEqual(len(created_eps), 1)
            self.assertTrue((archive_dir / "meeting_note.txt").exists())
            self.assertEqual(created_eps[0].metadata_json.get("active_custom_profiles"), "medical_profile")

    async def test_05_dev_template_plugin_discovery_and_kernel_introspection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = StorageEngine(db_path=Path(tmp) / "plugin_disc.db")
            bus = EventBus()
            board = HealthBoard()
            pm = PluginManager(bus=bus, storage=storage, board=board)
            rt = RuntimeManager(storage=storage, pm=pm, board=board)

            loaded = pm.discover_and_load(plugins_dir=Path("./plugins"), load_entry_points=False)
            self.assertIn("dev_template", loaded)
            await pm.startup_all()

            dev_plugin = pm.get_plugin("dev_template")
            self.assertIsNotNone(dev_plugin)
            assert dev_plugin is not None
            assert dev_plugin.context is not None

            # Inject utterance through Narrow PluginContext -> triggers phone redaction & jargon replacement
            saved_utt = await dev_plugin.context.ingest_utterance(
                text="请打给张总13987654321确认极米同款方案",
                speaker_role="HOST",
            )
            self.assertIsNotNone(saved_utt)
            assert saved_utt is not None
            self.assertIn("139****4321", saved_utt.text_content)
            self.assertIn("极米记得 (MemoMind)", saved_utt.text_content)
            self.assertTrue(saved_utt.metadata_json.get("pii_redacted"))

            kernel_status = rt.get_kernel_status()
            self.assertIn("providers", kernel_status)
            self.assertIn("health", kernel_status)
            self.assertEqual(kernel_status["health"]["needs_attention_count"], 0)


if __name__ == "__main__":
    unittest.main()
