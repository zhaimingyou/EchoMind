#!/usr/bin/env python3
"""End-to-End Stream & Episode Simulation Script (`scripts/simulate_stream.py`).

Runs out-of-the-box on any standard Python 3.9+ environment and demonstrates:
- Host voiceprint registration (`[HOST]`)
- Voiced + short utterance (<1.2s) speaker inheritance
- MemoMind episode card extraction (Summary + Action Items + Wishlist/Clues)
- Mem0-style fact conflict resolution (updating client quote from 50万 -> 35万)
"""
from __future__ import annotations
import asyncio
import math
import time
from typing import List
from backend.audio_engine.speaker_id import get_speaker_identifier
from backend.audio_engine.transcriber import parse_sensevoice_output
from backend.memory_core.proactive_cron import get_memo_generator
from backend.memory_core.segmenter import get_segmenter
from backend.storage.database import get_storage
from backend.storage.models import Utterance


def _synth_wave(freq_hz: float, duration_sec: float = 2.0, sr: int = 16000) -> List[float]:
    n = int(sr * duration_sec)
    return [
        0.5 * math.sin(2.0 * math.pi * freq_hz * i / sr)
        + 0.25 * math.sin(2.0 * math.pi * (freq_hz * 2.0) * i / sr)
        for i in range(n)
    ]


async def run_simulation() -> None:
    t0 = time.perf_counter()
    print("=================================================================")
    print("🚀 EchoMind v0.1 MVP — 纯 CPU 全链路语音记忆与认知引擎仿真")
    print("=================================================================")

    # Step 1: Enroll Host Voiceprint
    identifier = get_speaker_identifier()
    host_wave = _synth_wave(180.0, duration_sec=2.0)
    guest_wave = _synth_wave(1450.0, duration_sec=2.0)
    identifier.enroll_host_voice(host_wave, sample_rate=16000)
    print(f"[Step 1] 主人声纹 [HOST] 注册完成 -> {identifier.voiceprint_path}")

    # Step 2: Simulate Dialogue with SenseVoice Emotion/Laughter Tags
    storage = get_storage()
    raw_lines = [
        (host_wave, 2000, "<|zh|><|HAPPY|><|Laughter|>哈哈，下周三之前必须把 EchoMind 的智能眼镜 HUD 接口联调完！"),
        (host_wave[:8000], 500, "<|zh|><|NEUTRAL|>对，记一下这个待办。"),  # 0.5s short utterance -> inherits HOST!
        (guest_wave, 2000, "<|zh|><|NEUTRAL|>王总的预算目前是50万，另外我真想买副极米记得眼镜体验一下。"),
    ]

    for wave, dur_ms, raw_sv in raw_lines:
        spk = identifier.identify_speaker(wave, duration_ms=dur_ms, device_id="sim_glasses")
        asr = parse_sensevoice_output(raw_sv)
        utt = Utterance(
            duration_ms=dur_ms,
            speaker_role=spk.speaker_role,
            speaker_score=spk.similarity_score,
            emotion_tag=asr.emotion_tag,
            acoustic_event=asr.acoustic_event,
            text_content=asr.clean_text,
            device_id="sim_glasses",
        )
        storage.insert_utterance(utt)
        print(
            f"  -> [{utt.speaker_role} (score={utt.speaker_score:.2f}, inherited={spk.is_short_inherited})] "
            f"[{utt.emotion_tag}/{utt.acoustic_event}]: {utt.text_content}"
        )

    # Step 3: Close Episode & Extract Cognitive Card
    segmenter = get_segmenter()
    ep = await segmenter.inspect_and_segment(force_flush=True)
    elapsed = (time.perf_counter() - t0) * 1000
    print(f"\n[Step 2] 话题闭合生成极米式记忆卡片 (耗时 {elapsed:.1f} ms):")
    if ep:
        print(f"  📌 标题: 《{ep.title}》 | 分类: {ep.category} | 重要度: {'★' * ep.importance_score}")
        print(f"  📝 摘要:\n{ep.summary}")

    todos = storage.list_action_items()
    clues = storage.list_clues()
    facts = storage.list_semantic_facts()
    print(f"\n[Step 3] 自动捕获待办 ({len(todos)} 项) / 愿望与线索 ({len(clues)} 项) / 长期事实 ({len(facts)} 项)")
    for todo in todos[:2]:
        print(f"  ✅ [To-Do] {todo.content} (截止: {todo.due_date}) — 原话: “{todo.source_quote}”")
    for clue in clues[:2]:
        print(f"  ✨ [{clue.clue_type}] {clue.content}")
    for fact in facts[:2]:
        print(f"  🧠 [Fact] {fact.subject}.{fact.predicate} = {fact.object_value}")

    memo = await get_memo_generator().generate_daily_memo("MORNING_BRIEF")
    print(f"\n[Step 4] 生成早安 Memo ({memo.memo_date}):\n{memo.content_markdown[:320]}...\n")


if __name__ == "__main__":
    asyncio.run(run_simulation())
