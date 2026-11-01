# EchoMind 系统架构与详细技术设计文档 (Technical Design - v0.2 二次开发微内核底座)

> 本文档基于 [`specs/spec.md`](./spec.md) 编写。为了确保项目真正成为**面向二次开发的开源底座**，系统在 v0.1 模块化单体的基础上，深度吸收了 **[deepseek-ai/dsh-superagent-prototype](https://github.com/deepseek-ai/dsh-superagent-prototype)** 的核心工程哲学（*“消耗最少的人类注意力，交付最大的价值”*、受限能力上下文 `Narrow Context`、持久化幂等副作用队列 `Durable Effects Queue`、以及只展示异常问题的 `HealthBoard`），演进为五层微内核架构。

---

## 1. 面向二次开发的微内核全局架构图 (Extensible Micro-Kernel Architecture)

第三方开发者无需修改 `backend/` 核心代码，即可通过 **Provider 注册表**、**前置拦截器 (`@filter_hook`)**、**事后订阅钩子 (`@hook`)**、**持久化副作用处理器 (`Effects`)** 以及 **插件自定义路由 (`get_router()`)** 在任意环节定制系统行为：

```text
+---------------------------------------------------------------------------------------------------+
|                        扩展层 A: 多模态接入与插件自定义路由 (Ingest & Plugin Routers)               |
|  [内置 WS Audio Stream]   [内置 Audio Inbox 守护]   [插件路由: /api/v1/ext/{plugin_name}/*]         |
+------------+-------------------------+-----------------------------------+------------------------+
             |                         |                                   |
             +-------------------------+-----------------+-----------------+
                                                         | Raw Audio PCM / Device Frame
                                                         v
+---------------------------------------------------------------------------------------------------+
|                        核心底座 1: 统一引擎注册表 (ProviderRegistry)                                |
|  - VADProvider       : "silero_onnx" | "rms_energy" | <第三方自定义 VAD>                            |
|  - SpeakerProvider   : "sherpa_3dspeaker" | "spectral" | <第三方声纹模型>                           |
|  - ASRProvider       : "sensevoice_onnx" | "whisper_cpp"* | "funasr"* | <第三方 ASR>               |
|  - ExtractorProvider : "litellm" | "heuristic" | <第三方行业专属提取器>                              |
|  - EmbeddingProvider : "local_ngram" | "onnx_bge"* | "openai_emb"* | <第三方向量引擎>               |
+--------------------------------------------------------+------------------------------------------+
                                                         | Raw Utterance Draft
                                                         v
+===================================================================================================+
|                        核心底座 2: 双向事件与前置拦截总线 (EventBus & Filter Pipeline)              |
|                                                                                                   |
|  [前置拦截管线 @filter_hook] (可修改数据、纠错、脱敏、注入扩展字段，或返回 None 拦截丢弃)            |
|    1. utterance.before_save   -> 专有词库纠错 / 敏感信息脱敏 / 噪音片段丢弃                         |
|    2. episode.before_extract  -> 提炼前上下文增强 / 外部日历或位置信息注入                          |
|    3. episode.before_save     -> 垂直行业 Schema 字段补充 / 待办优先级重算                          |
|                                                                                                   |
|  [事后异步广播 @hook] (异常自动捕获并上报 HealthBoard，绝不阻塞主链路)                              |
|    - utterance.created  -> 注意力门控 HUD 字幕推送 (verbose / action_only / silent_record)          |
|    - episode.closed     -> 触发 Obsidian 双链 / CRM 同步 / Outbox 副作用入队                       |
|    - todo.created       -> 飞书/企微/Apple Reminders 同步                                          |
|    - memo.generated     -> 早晚安简报推送                                                           |
+========================================================+==========================================+
                                                         |
                                                         v
+---------------------------------------------------------------------------------------------------+
|          核心底座 3: 自治守护运行时、持久化副作用队列与健康看板 (Runtime Passes & Effects)          |
|  - Passes Loop        : 周期执行到期 Effects -> 巡检静默超时切片 -> 扫描 Audio Inbox -> 定时 Memo    |
|  - Durable Effects    : SQLite `effects` 表幂等合并 (kind + key)，失败指数退避重试 (2s -> 60s)     |
|  - Narrow Context     : 为每个插件分配独立命名空间 KV 存储 (`plugin_kv`) 与受控能力门面             |
|  - HealthBoard        : 追踪各插件与 Effect 连续失败次数，在 /api/v1/system/kernel 优先展示待处理项 |
+---------------------------------------------------------------------------------------------------+
```

---

## 2. 二次开发底座核心模块详细设计 (`backend/core/`)

### 2.1 五大可插拔契约定义 (`backend/core/interfaces.py`)

定义运行时可检查（`@runtime_checkable`）的五大核心算力与认知协议：
1. `VADProvider`：`accept_pcm16_bytes(raw_bytes)`、`accept_float_samples(samples)`、`flush()`。
2. `ASRProvider`：`transcribe(samples, sample_rate=16000, hint_text=None) -> TranscriptionResult`。
3. `SpeakerProvider`：`identify_speaker(samples, duration_ms, device_id, sample_rate) -> SpeakerMatchResult`、`enroll_host_voice(samples, sample_rate) -> List[float]`。
4. `ExtractorProvider`：`async extract_episode(utterances) -> EpisodeCognitiveResult`。
5. `EmbeddingProvider`：`embed_text(text: str) -> List[float]`。
6. `IngestAdapter`：`async start()`、`async stop()`。

### 2.2 统一服务注册表 (`backend/core/registry.py`)

`ProviderRegistry` 集中管理所有算力与认知实现，消除业务代码对具体实现类的硬编码依赖：
* 内置默认绑定：`sherpa_onnx` / `sensevoice` (`ASRProvider`)、`sherpa_onnx` / `3dspeaker` (`SpeakerProvider`)、`rms_energy` (`VADProvider`)、`default` (`ExtractorProvider`)、`local_ngram` (`EmbeddingProvider`)。
* 二次开发者可在插件 `on_startup(ctx)` 中调用 `ctx.registry.register_asr("my_asr", MyASR(), set_default=True)` 动态替换默认引擎。

### 2.3 双向事件与前置拦截总线 (`backend/core/event_bus.py`)

在保留原有 `publish(topic, payload)` 事后异步广播的基础上，新增**前置链式过滤器 (`apply_filters`)** 与 **错误回调上报**：
* `subscribe_filter(stage: str, handler: FilterHandler, priority: int = 100)`：按 `priority` 升序排列。
* `async apply_filters(stage: str, data: Any) -> Any`：
  * 每个拦截器接收 `data` 并返回修改后的 `data`；
  * 若任意拦截器返回 `None`，立即中止后续拦截器并返回 `None`（代表主动丢弃该语音或卡片）；
  * 若某个第三方拦截器或事件监听器抛出异常，捕获异常并回调 `HealthBoard` 记录故障，保留原 `data` 继续向下流转，严格保障主链路高可用。

### 2.4 受限能力上下文 (`Narrow PluginContext`) 与插件管理器 (`backend/core/plugin_manager.py`)

借鉴 [`dsh-superagent-prototype`](https://github.com/deepseek-ai/dsh-superagent-prototype) 中 `SourceContext` 的安全边界设计，第三方插件不再直接操作底层数据库连接，而是通过绑定其 `plugin_name` 的 `PluginContext` 交互：

```python
class ScopedKVStore:
    """绑定插件命名空间的隔离键值存储 (底层存储在 SQLite plugin_kv 表)。"""
    def get(self, key: str, default: Any = None) -> Any: ...
    def set(self, key: str, value: Any) -> None: ...
    def delete(self, key: str) -> None: ...
    def keys(self) -> List[str]: ...

class PluginContext:
    """注入给每个插件的受限安全门面 (Narrow Facade)。"""
    plugin_name: str
    settings: Any
    event_bus: EventBus
    registry: ProviderRegistry
    kv: ScopedKVStore

    def report_health(self, status: Literal["ok", "warn", "error"], message: str = "") -> None:
        """向内核 HealthBoard 上报当前插件健康状态（插件被卸载后调用自动忽略）。"""

    def enqueue_effect(self, kind: str, key: str, payload: Dict[str, Any]) -> None:
        """将外部耗时/易失败副作用（如推送外部 CRM、发送飞书通知）幂等入队，由内核指数退避重试。"""

    async def ingest_utterance(
        self,
        text: str,
        speaker_role: str = "HOST",
        device_id: str = "plugin_source",
        emotion_tag: str = "NEUTRAL",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Any]:
        """供硬件/外部数据源插件使用的标准话语注入入口（自动经过 before_save 拦截管线与 HUD 广播）。"""
```

### 2.5 自治后台运行时、持久化副作用队列与注意力门控 (`backend/core/runtime.py`)

融合 `dsh-superagent` 的 `Passes`、`Effects` 与 `000-philosophy.md` 注意力预算原则：

1. **持久化幂等副作用队列 (`Effects` Table & Handler)**：
   * 在 SQLite 中新增 `effects` 表：`kind`（副作用类型，如 `"webhook_notify"`、`"obsidian_sync"` 或插件自定义类型）、`effect_key`（业务幂等键，如 `ep_123`）、`payload_json`、`status` (`PENDING` / `DONE` / `FAILED`)、`attempts`、`next_run_at`、`last_error`。
   * **幂等合并（Coalescing）**：同一 `(kind, effect_key)` 若仍处于 `PENDING` 状态，再次 `enqueue_effect` 时直接更新其 `payload_json` 并将 `next_run_at` 设为立即执行，不产生重复队列项。
   * **指数退避重试（Exponential Backoff）**：处理器执行失败时，`attempts += 1`，延迟 `min(60, 2 ** attempts)` 秒后重试；若连续失败达 3 次，标记为 `FAILED` 并在 `HealthBoard` 上报异常，等待人工干预或重试。
2. **智能眼镜 HUD 注意力预算策略 (`HUD_ATTENTION_POLICY`)**：
   * `verbose`（默认开发演示模式）：每句实时转写（`realtime_utterance`）与卡片闭合均推送到 HUD。
   * `action_only`（低打扰伴随模式）：遵循 *"speaks only when someone must act or can use a result"*，平时说话保持 HUD 安静，仅当识别出包含新待办/线索的卡片闭合或高优提醒时才点亮眼镜 HUD。
   * `silent_record`（静默记录模式）：只落库与提取，不向眼镜端主动推送任何打扰消息。
3. **健康与待关注看板 (`HealthBoard` & `GET /api/v1/system/kernel`)**：
   * 汇总所有插件、Provider、后台 Passes 以及失败的 Effects，将 `needs_attention`（报错的插件或连续失败的副作用）排在最前面，健康状态不占用额外视觉噪音。
