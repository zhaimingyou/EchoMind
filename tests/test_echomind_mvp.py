"""Comprehensive End-to-End Test Suite for EchoMind v0.1 MVP (`tests/test_echomind_mvp.py`)."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import math
from pathlib import Path
import tempfile
from typing import List
import unittest
from backend.audio_engine.speaker_id import SpeakerIdentifier
from backend.audio_engine.transcriber import parse_sensevoice_output
from backend.audio_engine.vad_buffer import VADStreamBuffer
from backend.connectors.obsidian_sync import ObsidianSyncConnector
from backend.core.event_bus import EventBus
from backend.core.plugin_manager import EchoMindPlugin, PluginManager, hook
from backend.memory_core.extractor import CognitiveExtractor
from backend.memory_core.fact_resolver import FactResolver
from backend.memory_core.proactive_cron import ProactiveMemoGenerator
from backend.memory_core.segmenter import EpisodeSegmenter
from backend.storage.database import StorageEngine
from backend.storage.models import Utterance
from backend.storage.vector_store import HybridSearchEngine


def _make_tone(freq_hz: float, duration_sec: float = 2.0, sr: int = 16000) -> List[float]:
    n = int(sr * duration_sec)
    return [0.6 * math.sin(2.0 * math.pi * freq_hz * i / sr) for i in range(n)]


class TestEchoMindMVP(unittest.IsolatedAsyncioTestCase):
    async def test_01_event_bus_and_plugin_system(self) -> None:
        bus = EventBus()
        pm = PluginManager(bus=bus)
        received: List[str] = []

        class CustomTestPlugin(EchoMindPlugin):
            name = "test_plugin"

            @hook("episode.closed")
            async def on_closed(self, payload: dict) -> None:
                received.append(payload["title"])

        pm.register_plugin(CustomTestPlugin())
        await bus.publish("episode.closed", {"title": "测试插件触发卡片"})
        self.assertEqual(received, ["测试插件触发卡片"])
        self.assertEqual(len(pm.list_plugins()), 1)

    def test_02_speaker_id_host_short_immunity_and_guest_clustering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vp_file = Path(tmp) / "host.json"
            identifier = SpeakerIdentifier(
                voiceprint_path=vp_file,
                host_threshold=0.65,
                guest_threshold=0.60,
                short_utterance_ms=1200,
                inherit_window_sec=3.0,
            )

            host_wave = _make_tone(180.0, duration_sec=2.0)
            identifier.enroll_host_voice(host_wave, sample_rate=16000)
            self.assertTrue(identifier.has_host_voiceprint())

            # 1. Host 2.0s speech -> matches HOST
            res_host = identifier.identify_speaker(
                host_wave, duration_ms=2000, device_id="dev1", now_ts=100.0
            )
            self.assertEqual(res_host.speaker_role, "HOST")
            self.assertGreaterEqual(res_host.similarity_score, 0.65)

            # 2. Short 0.6s utterance within 1.0s -> inherits HOST via Short-Utterance Immunity!
            short_clip = _make_tone(950.0, duration_sec=0.6)
            res_short = identifier.identify_speaker(
                short_clip, duration_ms=600, device_id="dev1", now_ts=101.0
            )
            self.assertEqual(res_short.speaker_role, "HOST")
            self.assertTrue(res_short.is_short_inherited)

            # 3. Guest 1 (1900Hz wave) -> GUEST_1
            guest1_wave = _make_tone(1900.0, duration_sec=2.0)
            res_g1 = identifier.identify_speaker(
                guest1_wave, duration_ms=2000, device_id="dev1", now_ts=105.0
            )
            self.assertEqual(res_g1.speaker_role, "GUEST_1")

            # 4. Guest 2 (820Hz wave) -> GUEST_2
            guest2_wave = _make_tone(820.0, duration_sec=2.0)
            res_g2 = identifier.identify_speaker(
                guest2_wave, duration_ms=2000, device_id="dev1", now_ts=108.0
            )
            self.assertEqual(res_g2.speaker_role, "GUEST_2")

            # 5. Guest 1 speaks again -> clusters back into GUEST_1
            res_g1_again = identifier.identify_speaker(
                guest1_wave, duration_ms=2000, device_id="dev1", now_ts=110.0
            )
            self.assertEqual(res_g1_again.speaker_role, "GUEST_1")

    def test_03_sensevoice_tag_parser_and_vad(self) -> None:
        parsed = parse_sensevoice_output("<|zh|><|HAPPY|><|Laughter|>今天这个开源架构太棒了")
        self.assertEqual(parsed.lang, "zh")
        self.assertEqual(parsed.emotion_tag, "HAPPY")
        self.assertEqual(parsed.acoustic_event, "LAUGHTER")
        self.assertEqual(parsed.clean_text, "今天这个开源架构太棒了")

        vad = VADStreamBuffer(sample_rate=16000, min_speech_ms=400, min_silence_ms=300)
        silence = [0.0] * 8000
        voiced = _make_tone(300.0, duration_sec=1.0)
        self.assertEqual(vad.accept_float_samples(silence), [])
        chunks = vad.accept_float_samples(voiced + silence)
        self.assertEqual(len(chunks), 1)
        self.assertGreaterEqual(chunks[0].duration_ms, 900)

    async def test_04_segmenter_host_absence_overlap_and_mem0_conflict_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            storage = StorageEngine(db_path=tmp_path / "test.db")
            hybrid = HybridSearchEngine(storage=storage)
            resolver = FactResolver(storage=storage)
            extractor = CognitiveExtractor(fact_resolver=resolver)
            segmenter = EpisodeSegmenter(
                storage=storage,
                extractor=extractor,
                fact_resolver=resolver,
                hybrid_search=hybrid,
            )

            # 1. Test Host-Absence Filter (0% HOST speech -> DISCARDED without LLM token spend)
            storage.insert_utterance(
                Utterance(
                    speaker_role="GUEST_1",
                    text_content="电视机正在播放新闻联播背景音",
                    timestamp="2026-10-31T10:00:00+00:00",
                )
            )
            ep_discarded = await segmenter.inspect_and_segment(
                now_dt=datetime.fromisoformat("2026-10-31T10:05:00+00:00")
            )
            self.assertIsNotNone(ep_discarded)
            assert ep_discarded is not None
            self.assertEqual(ep_discarded.category, "DISCARDED")
            self.assertEqual(ep_discarded.host_word_ratio, 0.0)

            # 2. Test Episode 1: Work commitment + Wishlist + Initial Fact (王总的报价底线是50万)
            t_base = datetime(2026, 10, 31, 14, 0, 0, tzinfo=timezone.utc)
            storage.insert_utterance(
                Utterance(
                    speaker_role="GUEST_1",
                    text_content="王总的报价底线是50万，希望尽快推进。",
                    timestamp=t_base.isoformat(),
                )
            )
            storage.insert_utterance(
                Utterance(
                    speaker_role="HOST",
                    text_content="下周三之前必须把智能眼镜接口联调完，另外我真想买一台3D打印机。",
                    timestamp=(t_base + timedelta(seconds=20)).isoformat(),
                )
            )
            ep1 = await segmenter.inspect_and_segment(force_flush=True)
            self.assertIsNotNone(ep1)

            todos = storage.list_action_items()
            clues = storage.list_clues()
            facts = storage.list_semantic_facts(subject="王总")
            self.assertEqual(len(todos), 1)
            self.assertIn("联调", todos[0].content)
            self.assertEqual(len(clues), 1)
            self.assertEqual(clues[0].clue_type, "WISHLIST")
            self.assertEqual(len(facts), 1)
            self.assertEqual(facts[0].object_value, "50万")
            self.assertIsNone(facts[0].previous_value)

            # 3. Test Episode 2: Fact Conflict Update (50万 -> 35万) & 25-min Max Span Overlap Window
            t2_start = datetime(2026, 10, 31, 15, 0, 0, tzinfo=timezone.utc)
            for i in range(6):
                storage.insert_utterance(
                    Utterance(
                        speaker_role="HOST" if i % 2 == 0 else "GUEST_1",
                        text_content=(
                            "王总的报价底线调整为35万"
                            if i == 5
                            else f"这是长会议第 {i+1} 阶段的技术讨论。"
                        ),
                        timestamp=(t2_start + timedelta(minutes=i * 6)).isoformat(),
                    )
                )
            ep2 = await segmenter.inspect_and_segment(
                now_dt=t2_start + timedelta(minutes=30, seconds=10)
            )
            self.assertIsNotNone(ep2)
            assert ep2 is not None

            updated_facts = storage.list_semantic_facts(subject="王总")
            self.assertEqual(len(updated_facts), 1)
            self.assertEqual(updated_facts[0].object_value, "35万")
            self.assertEqual(updated_facts[0].previous_value, "50万")

            remaining_buffer = storage.get_unassigned_utterances()
            self.assertEqual(len(remaining_buffer), 5)
            self.assertTrue(all(u.is_context_prefix for u in remaining_buffer))

            # 4. Verify Morning Memo & Obsidian Sync
            memo_gen = ProactiveMemoGenerator(storage=storage)
            morning_memo = await memo_gen.generate_daily_memo("MORNING_BRIEF")
            self.assertIn("早安 Memo", morning_memo.content_markdown)
            self.assertIn("35万", morning_memo.content_markdown)

            obs = ObsidianSyncConnector(vault_dir=tmp_path / "obsidian")
            md_path = await obs.on_episode_closed(
                {
                    **ep2.model_dump(),
                    "action_items": [t.model_dump() for t in todos],
                    "clues_and_wishlists": [c.model_dump() for c in clues],
                    "facts_updated": [f.model_dump() for f in updated_facts],
                }
            )
            self.assertIsNotNone(md_path)
            assert md_path is not None
            self.assertTrue(md_path.exists())
            self.assertIn("[[王总]]", md_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
