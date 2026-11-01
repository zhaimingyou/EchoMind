# EchoMind 产品与需求规格说明书 (Specification - v0.1 MVP & v0.2 二次开发微内核底座)

> **开源定位一句话 Pitch**：
> **EchoMind** —— 面向二次开发的开源、100% 本地纯 CPU 运行的「个人数字第二大脑」与 AI 穿戴记忆中枢底座（The Open-Source, Extensible Memory Micro-Kernel for **MemoMind (极米记得)**, **Plaud Note**, **[Omi](https://github.com/BasedHardware/omi)**, **[Even Realities G1](https://www.reddit.com/r/EvenRealities/comments/1gfgjpg/even_realities_officially_supports_open_source/)** & **[Brilliant Labs Frame](https://github.com/brilliantlabsAR/frame-codebase)**，微内核设计融合 **[deepseek-ai/dsh-superagent-prototype](https://github.com/deepseek-ai/dsh-superagent-prototype)** 架构思想）。

---

## 1. 开源授权合规性与二次开发定位策略

### 1.1 MIT 开源协议合规设计 (License Compliance)
* **源码协议**：EchoMind 仓库所有源代码采用 **MIT License** 开源，允许任何个人、硬件创业团队、同行开发者自由修改、私有化部署及商业集成（仅需保留版权声明）。
* **依赖与模型权重解耦（规避协议传染）**：
  * 核心推理框架 [k2-fsa/sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)（Apache-2.0）、声纹库 [modelscope/3D-Speaker](https://github.com/modelscope/3D-Speaker)（[Apache-2.0](https://github.com/modelscope/3D-Speaker/blob/main/LICENSE)）、语音识别源码 [QwenAudio/SenseVoice](https://github.com/QwenAudio/SenseVoice)（MIT）均属于宽松开源许可证，与 MIT 100% 兼容。
  * **预训练模型权重动态拉取**：Git 仓库本身**不包含**任何模型二进制权重，而是通过 `scripts/download_models.py` 在用户本地首次启动时按需下载。这既保证了 Git 仓库轻量纯净，又在法律边界上将“MIT 授权的软件框架”与“第三方模型权重条款”完全解耦。

### 1.2 二次开发目标受众与场景定位矩阵
为了让硬件创业者、垂直行业开发者和独立 Hacker 能直接拿 EchoMind 做二次开发（零侵入定制，无需 Fork 后大改核心目录），项目提供开箱即用的扩展底座：

| 二次开发者画像 | 典型二开诉求 | EchoMind 底座提供的核心支撑 |
| --- | --- | --- |
| **AI 眼镜/穿戴硬件团队**<br>对标极米记得 (MemoMind)、[Even Realities G1](https://www.reddit.com/r/EvenRealities/comments/1gfgjpg/even_realities_officially_supports_open_source/)、[Brilliant Labs Frame](https://github.com/brilliantlabsAR/frame-codebase)、[BasedHardware/omi](https://github.com/BasedHardware/omi) | 已有自有蓝牙协议、BLE 音频包格式或专属 App 鉴权，需要接入后端并下发自定义眼镜 HUD 画面。 | **可插拔 `IngestAdapter` + 插件级 FastAPI 路由 (`get_router()`) + 注意力预算 HUD 门控 (`hud_policy`)**：一个插件文件即可新增私有硬件接入端点，并按需静默记录或高价值点亮 HUD。 |
| **本地 AI 与算力折腾玩家**<br>Mac Apple Silicon (MLX)、RK3588 边缘盒子、企业私有 GPU 集群 | 想把默认的 `sherpa-onnx` 换成 `Whisper.cpp`、`MLX-Whisper`、`FunASR` 或本地 `bge-m3` 向量模型。 | **五大引擎注册表 (`ProviderRegistry`)**：支持通过 `@register_asr`、`@register_extractor`、`@register_embedding` 装饰器注册并通过 `.env` 一键切换。 |
| **垂直行业应用开发者**<br>医疗问诊记录、律所案情访谈、B2B 销售跟单 CRM、课堂学习助手 | 默认的“日常待办+愿望清单”不满足行业需求，需要脱敏、纠正行业黑话，并提取结构化病历/BANT 销售线索。 | **前置拦截管线 (`@filter_hook`) + 可定制认知模板 (`Profile/Schema`)**：落库前脱敏/纠错，提炼时注入行业 Prompt 并将扩展字段存入 `metadata_json`。 |
| **效率工具与 Agent 生态开发者**<br>[screenpipe](https://github.com/screenpipe/screenpipe)、Obsidian、飞书/Notion、Claude Desktop / Cursor | 希望将线下对话记忆实时同步到企业 IM、知识库或供外部 AI Agent 随时检索调用，且断网不丢数据。 | **受限插件上下文 (`Narrow PluginContext`) + 持久化副作用队列 (`EffectsQueue`) + 原生 `FastMCP Server`**：支持安全隔离存储与断网退避重试。 |

---

## 2. 核心用户故事 (User Stories)

### 2.1 终端用户体验故事 (v0.1 核心闭环)
* **US-01（多端无感拾音）**：作为用户或硬件开发者，我希望通过网页蓝牙麦克风、开源穿戴硬件（ESP32/Omi/Frame）或手机录音文件夹自动同步，把全天对话无感汇入本地服务，无需手动点击每次会议的开始和结束。
* **US-02（主人声纹锚定与防噪音污染）**：作为全天候开启拾音的用户，我希望系统能精准认出我的声音（`[HOST]`），并在我看视频、听播客或路过别人闲聊（无我参与）时自动丢弃无效音频，不污染记忆库也不浪费 LLM Token。
* **US-03（极米同款记忆卡片与主动线索抓取）**：作为用户，我希望一段对话结束后，看板自动生成结构化的“记忆卡片（Episode）”，不仅包含第一人称总结和明确承诺的 To-Do，还能从随口闲聊中抓取我的“愿望清单/兴趣线索（Wishlist & Clues）”。
* **US-04（动态人物与项目记忆图谱）**：作为用户，当我多次和“王总”聊到“A项目报价”时，我希望系统能像 [mem0ai/mem0](https://github.com/mem0ai/mem0) 一样自动更新王总的最新报价底线，而不是存一堆互相矛盾的旧事实。
* **US-05（早晚安 Memo 主动推送）**：作为用户，我希望每天早上收到“早安 Memo”（今日待办、昨日未完线索、重要人物提醒），晚上收到“晚安 Memo”（全天记忆卡片汇总、新增认知事实与灵感回顾）。

### 2.2 二次开发者故事 (v0.2 微内核底座强化 & 融合 dsh-superagent 架构思想)
* **US-06（零侵入替换底层 AI 算力 Provider）**：作为二次开发者，我希望能编写自定义的 `ASRProvider`、`SpeakerProvider`、`VADProvider`、`ExtractorProvider` 或 `EmbeddingProvider` 并注册到 `ProviderRegistry`，只需修改 `.env` 配置即可替换系统默认实现，无需改动 `backend/` 核心代码。
* **US-07（前置数据流拦截、纠错与隐私脱敏）**：作为企业或行业二次开发者，我希望在语音转写生成 `Utterance` 落库前、或在 `Episode` 送入大模型提炼前，通过前置拦截钩子（`@filter_hook`）修改文本（如医疗/工业术语纠错、手机号/身份证脱敏）或直接丢弃无效片段。
* **US-08（受限能力上下文与插件自定义路由）**：作为硬件或第三方集成开发者，我希望在编写 `EchoMindPlugin` 时，获得受限且安全的 `PluginContext`（包含按插件命名空间隔离的 `kv` 存储、受控 `receive_utterance` 入口、健康状态上报 `report_health` 及副作用入队 `enqueue_effect`），并能直接向主应用挂载自定义 FastAPI 路由（如 `/api/v1/ext/{plugin_name}/*`）。
* **US-09（垂直场景认知提炼模板与扩展字段）**：作为垂直行业开发者，我希望通过配置或插件注入自定义的提取 Prompt 与附加字段，让提炼出的行业专属结构化数据（如客户预算阶段、患者主诉症状）自动落库到 `Episode.metadata_json` 中。
* **US-10（全自治后台 Passes 循环、持久化 Effects 队列与注意力预算门控）**：作为部署者，我希望服务启动后自动运行后台 `Passes` 守护循环（处理到期的外部副作用 `Effects` 重试、静默超时自动闭合卡片、扫描录音收件箱、定时生成早晚安简报），并支持通过 `HUD_ATTENTION_POLICY` 控制智能眼镜 HUD 的打扰频率（遵循 *"Take as little human attention as possible, and give as much value as possible"* 原则）。

---

## 3. 功能性需求规格 (Functional Requirements - EARS 语法)

### 3.1 可插拔多源接入层 (Pluggable Ingest Layer)
* **REQ-ING-01 (WebSocket 实时流)**：**When** 客户端通过 `ws://<host>:8000/api/v1/stream/audio` 建立连接并发送包含 `device_id`、`codec` (`pcm_s16le` 或 `opus`)、`sample_rate` (默认 16000) 的握手帧后，系统 **shall** 持续接收二进制音频分片并推入对应设备的内存流式缓冲区。
* **REQ-ING-02 (本地文件夹监听)**：**When** 用户将 `.wav` / `.txt` 录音或转写文件放入 `data/audio_inbox/` 目录时，系统后台守护进程 **shall** 自动检测新文件并注入处理管线，处理完成后移入 `data/audio_archive/`。
* **REQ-ING-03 (基于注意力预算的 HUD 逆向下行反馈)**：**When** 实时流识别出有效话语或生成新记忆卡片时，系统 **shall** 根据 `HUD_ATTENTION_POLICY`（`verbose` 全量字幕 / `action_only` 仅待办与高优卡片点亮 / `silent_record` 静默只记不推）决定是否向智能眼镜推送 `hud_display`（40 字内），以最小化对人类注意力的消耗。

### 3.2 纯 CPU 语音预处理与声纹管线 (Audio Engine Provider)
* **REQ-AUD-01 (帧级 VAD 过滤)**：**While** 接收音频流时，系统 **shall** 通过可插拔 `VADProvider` 进行语音活动检测；连续静音帧直接在内存中丢弃。
* **REQ-AUD-02 (主人声纹注册与锚定)**：**When** 用户通过 CLI 或 Web 端上传/录制个人语音时，系统 **shall** 通过 `SpeakerProvider` 提取 192 维特征均值向量并持久化；实时推理中余弦相似度 `>= 0.65`（可配置）的语音段 **shall** 标记为 `HOST`。
* **REQ-AUD-03 (短语音声纹豁免与在线 Guest 聚类)**：**If** 单个有效语音段时长 `< 1.2s`，系统 **shall** 豁免独立声纹比对，直接继承同一设备 3 秒内前一句的 `speaker_role`；**Where** 语音段时长 `>= 1.2s` 且非 `HOST`，系统 **shall** 在当前会话的在线质心池中进行余弦聚类（阈值 `0.60`），自动分配稳定的 `GUEST_1`、`GUEST_2` 标签。
* **REQ-AUD-04 (SenseVoice 多维转写)**：**When** VAD 切出有效语音段时，系统 **shall** 调用当前激活的 `ASRProvider` 完成转写，并同步提取情绪标签与声学事件标签。

### 3.3 动态话题切片与认知提炼引擎 (Memory Core)
* **REQ-MEM-01 (三维触发话题切片)**：后台巡检器定期扫描未闭合的 `utterances` 缓冲区，满足以下任一条件时 **shall** 闭合当前话题并触发 Episode 提炼：
  1. **物理静默切分**：距离最新一句有效语音已超过 `180 秒`（可配置）。
  2. **最大跨度切分（带滑动重叠窗口）**：连续高密度对话时长达到 `25 分钟`，强制切片，并将末尾最后 `5 句` Utterances 作为只读上下文前缀（`is_context_prefix=True`）复制到下一切片。
  3. **主人缺席静默销毁**：当前缓冲段内 `HOST` 发言字数占比为 `0%` 且未开启“纯旁听会议模式”时，直接标记为 `DISCARDED`，**不调用** LLM。
* **REQ-MEM-02 (极米式多维认知提取与自定义模板)**：**When** 有效话题切片闭合后，系统 **shall** 调用激活的 `ExtractorProvider`，生成标题、分类、第一人称纪要、附带 `source_quote` 的待办、愿望清单线索，以及可选的自定义扩展结构数据（`custom_metadata` 写入 `Episode.metadata_json`）。
* **REQ-MEM-03 (长期事实 Upsert 与冲突消解)**：**When** 提取出新的实体事实（`fact_operations`）时，系统 **shall** 先召回同一主体的历史事实；若存在冲突或演进，执行 `UPDATE` 更新最新值并保留 `previous_value` 审计轨迹。
* **REQ-MEM-04 (早安/晚安 Memo 主动生成)**：系统 **shall** 支持定时调度与手动触发生成每日早安 Memo 与晚安 Memo，写入数据库并发布 `memo.generated` 事件。

### 3.4 二次开发微内核底座规格 (Micro-Kernel & SDK Requirements - v0.2)
* **REQ-EXT-01 (五大 Provider 统一注册表)**：系统 **shall** 在 `backend/core/registry.py` 中提供全局 `ProviderRegistry`，支持注册、按名称解析及运行时热切换 `asr`、`speaker`、`vad`、`extractor`、`embedding` 五类核心 Provider，并在找不到外部依赖时优雅降级至内置 CPU 实现。
* **REQ-EXT-02 (前置拦截管线 Filter Pipeline)**：系统 `EventBus` 除支持事后异步广播（`publish` / `@hook`）外，**shall** 支持前置同步/异步拦截管线（`apply_filters` / `@filter_hook`）：
  * 在 `utterance.before_save` 阶段，允许插件修改 `Utterance` 字段（如术语纠错、敏感信息脱敏）或返回 `None` 直接拦截丢弃该条语音；
  * 在 `episode.before_extract` 阶段，允许插件过滤/重排待提炼的对话列表；
  * 在 `episode.before_save` 阶段，允许插件向 `EpisodeCognitiveResult` 注入自定义行业字段或追加待办。
* **REQ-EXT-03 (受限能力上下文 Narrow PluginContext 与路由挂载)**：借鉴 `dsh-superagent` 的 `SourceContext` 最小权限思想，`EchoMindPlugin` **shall** 接收受限且绑定插件身份的 `PluginContext`：
  * 提供命名空间隔离的 `ctx.kv.get(key)` / `ctx.kv.set(key, val)` / `ctx.kv.delete(key)` 持久化键值存储；
  * 提供受控只读查询与 `ctx.receive_utterance(...)` 标准注入入口；
  * 提供插件健康状态上报 `ctx.report_health(status, message)`，当插件被卸载或禁用后，其 `PluginContext` 写入自动失效；
  * 支持 `def get_router(self) -> Optional[APIRouter]`，由 `PluginManager` 自动挂载至 FastAPI `/api/v1/ext/{plugin_name}` 命名空间下；
  * 同时支持本地 `plugins/*.py` 文件扫描与 Python 标准 `importlib.metadata.entry_points(group="echomind.plugins")` 第三方包发现。
* **REQ-EXT-04 (后台 Passes 循环、持久化 Effects 队列与 HealthBoard)**：借鉴 `dsh-superagent` 的 `Passes + Effects + HealthBoard` 架构，系统 **shall** 在 `backend/core/runtime.py` 与 `database.py` 中提供：
  * **SQLite 持久化副作用队列 (`effects` 表)**：支持 `enqueue_effect(kind, key, payload)`（相同 waiting key 自动合并覆盖幂等更新），失败时按指数退避（exponential backoff）自动重试，连续失败 3 次自动在 `HealthBoard` 标记告警；
  * **后台 `Passes` 巡检循环**：定期执行到期 `Effects`、巡检静默超时自动闭合 Episode、扫描 `audio_inbox` 以及触发早晚安 Memo；
  * **注意力优先自省看板 (`/api/v1/system/kernel`)**：仅高亮需要人工关注的异常（如连续失败的 Effect、降级的插件），健康组件保持精简展示。

---

## 4. 非功能性需求与演进路线图 (Roadmap v0.1 -> v1.0)

### 4.1 性能与工程约束
1. **纯 CPU 推理性能 (NFR-PERF-01)**：4 核 CPU 无独显条件下，联合推理实时率 `RTF < 0.10`。
2. **内存占用约束 (NFR-RES-01)**：后端常驻进程总内存占用 `< 1.2 GB`。
3. **插件故障隔离 (NFR-ISO-01)**：任何第三方插件在 `@hook`、`@filter_hook` 或 `on_startup` 中抛出未捕获异常时，微内核 **shall** 捕获并记录到 `HealthBoard`，绝不阻塞或崩溃主音频流与记忆存储管线。
4. **向后兼容性 (NFR-COMP-01)**：v0.2 微内核底座升级 **shall** 100% 兼容 v0.1 已有的 REST API、WebSocket 握手协议、MCP 工具签名及现有单元测试。
