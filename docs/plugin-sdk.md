# EchoMind 二次开发与微内核扩展指南 (Plugin & Provider SDK Cookbook)

> 本指南采用循序渐进的编号式结构（灵感来自 [`deepseek-ai/dsh-superagent-prototype`](https://github.com/deepseek-ai/dsh-superagent-prototype) 的文档哲学），帮助智能硬件团队、本地 AI 玩家与垂直行业开发者在 **不修改 EchoMind 核心业务代码** 的前提下完成二次开发。

---

## 000 核心设计哲学与注意力预算 (Philosophy & Attention Budget)

EchoMind 的微内核底座遵循两条核心原则：

1. **消耗最少的人类注意力，交付最大的记忆价值**（*Take as little human attention as possible, and give as much value as possible*）：
   - 智能眼镜光波导 HUD 只有 40 个字符的视野。通过环境变量 `HUD_ATTENTION_POLICY`，你可以控制系统的打扰程度：
     - `verbose`（默认调试模式）：每句实时语音转写与卡片生成都推送到 HUD。
     - `action_only`（推荐日常佩戴模式）：平时说话保持 HUD 安静，**仅当提炼出明确待办事项、愿望线索或重要度 `>= 4` 的卡片时**才点亮眼镜 HUD。
     - `silent_record`（静默记录模式）：全程无感记录并同步至本地库/Obsidian，绝不主动弹窗打扰。
2. **窄接口受限上下文与故障隔离**（*Narrow Context & Fault Isolation*）：
   - 任何第三方插件抛出的未捕获异常都会被微内核自动拦截并记录到 `HealthBoard`（可通过 `GET /api/v1/system/kernel` 查看 `needs_attention` 列表），**绝不会导致主语音拾音流或数据库崩溃**。

---

## 001 编写第一个插件与使用受限上下文 (`EchoMindPlugin` & `PluginContext`)

在 `plugins/` 目录下新建任意 `.py` 文件，继承 `EchoMindPlugin` 即可在服务启动时自动热加载。每个插件都会收到专属的受限上下文 `PluginContext`（包含命名空间隔离的 `ctx.kv` 持久化存储、`ctx.report_health` 健康上报、`ctx.enqueue_effect` 持久化副作用队列与 `ctx.ingest_utterance` 话语注入接口）：

```python
from backend.core.plugin_manager import EchoMindPlugin, PluginContext, hook

class MyCrmSyncPlugin(EchoMindPlugin):
    name = "my_crm_sync"
    version = "0.1.0"
    description = "当对话生成新待办时，异步入队同步至外部 CRM"

    async def on_startup(self, ctx: PluginContext) -> None:
        # 1. 使用按插件名隔离的 SQLite KV 存储读取配置或状态
        sync_count = ctx.kv.get("synced_count", 0)
        ctx.report_health("ok", f"CRM 插件就绪，历史已同步 {sync_count} 条")

    @hook("todo.created")
    async def on_new_todo(self, payload: dict) -> None:
        if not self.context:
            return
        # 2. 将耗时或易因网络抖动失败的操作放入持久化 Effects 队列（相同 key 自动幂等合并，失败指数退避重试）
        self.context.enqueue_effect(
            kind="crm_push_todo",
            key=payload["id"],
            payload=payload,
        )
```

---

## 002 前置拦截管线：隐私脱敏、术语纠错与垂直行业字段扩展 (`@filter_hook`)

如果事后监听（`@hook`）不够用，你需要在**数据写入 SQLite 之前**或**送入大模型提炼之前**修改数据，可以使用 `@filter_hook(stage, priority)`。完整样板见 [`plugins/example_custom_dev_template.py`](../plugins/example_custom_dev_template.py)。

系统内置三大标准拦截阶段：

| 拦截阶段 (`stage`) | 输入/输出类型 | 典型二次开发用途 |
| :--- | :--- | :--- |
| `utterance.before_save` | 输入 `Utterance`，返回修改后的 `Utterance` 或 `None` | **专有词库/人名纠错**、**手机号/身份证 PII 脱敏**，或返回 `None` 直接丢弃无效噪音 |
| `episode.before_extract` | 输入 `List[Utterance]`，返回修改后的列表 | 在送入 LLM 提炼前补充外部日历/地理位置上下文，或裁剪冗余寒暄 |
| `episode.before_save` | 输入 `EpisodeCognitiveResult`，返回修改后的对象或 `None` | 向 `cog.custom_metadata` 注入**垂直行业结构化字段**（自动存入 `Episode.metadata_json`） |

### 示例：医疗/销售场景前置脱敏与自定义 Prompt 指令注入

```python
import re
from backend.core.plugin_manager import EchoMindPlugin, PluginContext, filter_hook
from backend.memory_core.extractor import get_extractor
from backend.memory_core.schemas import EpisodeCognitiveResult
from backend.storage.models import Utterance

class SalesBantPlugin(EchoMindPlugin):
    name = "sales_bant_Helper"
    version = "0.1.0"

    async def on_startup(self, ctx: PluginContext) -> None:
        # 向认知提炼器追加垂直行业 System Prompt 规则
        get_extractor().register_custom_instruction(
            "sales_bant",
            "若对话涉及客户洽谈，请在总结中明确标注客户的预算(Budget)、决策人(Authority)与时间表(Timeline)。"
        )

    @filter_hook("utterance.before_save", priority=10)
    def redact_phone(self, utt: Utterance) -> Utterance:
        utt.text_content = re.sub(r"(1[3-9]\d)\d{4}(\d{4})", r"\1****\2", utt.text_content)
        return utt

    @filter_hook("episode.before_save", priority=20)
    def tag_industry_meta(self, cog: EpisodeCognitiveResult) -> EpisodeCognitiveResult:
        cog.custom_metadata["vertical_domain"] = "b2b_sales"
        return cog
```

---

## 003 零侵入替换五大底层算力与认知引擎 (`ProviderRegistry`)

EchoMind 将语音活动检测（`VADProvider`）、语音识别（`ASRProvider`）、声纹识别（`SpeakerProvider`）、认知提炼（`ExtractorProvider`）和向量化（`EmbeddingProvider`）全部解耦到了 [`backend/core/registry.py`](../backend/core/registry.py) 中。

你可以在插件中实现协议并调用 `registry.register_*` 一键接管底层引擎，无需改动 `ws_stream.py` 或 `segmenter.py`：

```python
from typing import Sequence, Optional
from backend.core.interfaces import ASRProvider, TranscriptionResult
from backend.core.registry import registry

class MyWhisperCppASR:
    """自定义 Whisper.cpp 或云端 ASR 引擎实现"""
    def transcribe(
        self,
        samples: Sequence[float],
        sample_rate: int = 16000,
        hint_text: Optional[str] = None,
    ) -> TranscriptionResult:
        # 调用你自己的本地/远程推理逻辑
        return TranscriptionResult(
            clean_text="自定义引擎转写文本",
            lang="zh",
            emotion_tag="NEUTRAL",
            acoustic_event="NONE",
        )

# 注册并立即设为全局默认 ASR 引擎
registry.register_asr("whisper_cpp", MyWhisperCppASR(), set_default=True)
```

---

## 004 接入自定义智能眼镜/穿戴硬件与挂载专属 API 路由 (`get_router()`)

如果你正在开发智能眼镜（如 Even Realities G1、Frame）或 ESP32 随身胸针，可以在插件中直接实现 `get_router()`，系统会自动将其挂载到 `/api/v1/ext/{plugin.name}` 下，并可通过 `self.context.ingest_utterance(...)` 将硬件传回的文本或解码后语音注入主记忆流：

```python
from fastapi import APIRouter
from pydantic import BaseModel
from backend.core.plugin_manager import EchoMindPlugin

class GlassesFramePayload(BaseModel):
    device_sn: str
    transcript: str
    is_owner: bool = True

class SmartGlassesBridgePlugin(EchoMindPlugin):
    name = "glasses_bridge"
    version = "0.1.0"

    def get_router(self) -> APIRouter:
        router = APIRouter()

        @router.post("/push-caption")
        async def receive_glasses_caption(body: GlassesFramePayload):
            # 自动经过 utterance.before_save 脱敏管线、落库并广播至 HUD 与记忆切片器
            utt = await self.context.ingest_utterance(
                text=body.transcript,
                speaker_role="HOST" if body.is_owner else "GUEST_1",
                device_id=body.device_sn,
            )
            return {"accepted": utt is not None, "utterance_id": utt.id if utt else None}

        return router
```

启动服务后，你的硬件即可直接请求 `POST http://127.0.0.1:8000/api/v1/ext/glasses_bridge/push-caption`，并在 `GET http://127.0.0.1:8000/api/v1/system/kernel` 中实时查看插件健康状态与内核运行指标。
