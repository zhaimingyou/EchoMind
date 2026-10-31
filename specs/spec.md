# EchoMind 产品与需求规格说明书 (Specification - v0.1 MVP & Evolution Roadmap)

> **开源定位一句话 Pitch**：
> **EchoMind** —— 开源、100% 本地纯 CPU 运行的「个人数字第二大脑」与 AI 穿戴记忆中枢（The Open-Source, Self-Hosted Memory Backend for **MemoMind (极米记得)**, **Plaud Note**, **[Omi](https://github.com/BasedHardware/omi)**, **[Even Realities G1](https://www.reddit.com/r/EvenRealities/comments/1gfgjpg/even_realities_officially_supports_open_source/)** & **[Brilliant Labs Frame](https://github.com/brilliantlabsAR/frame-codebase)**）。

---

## 1. 开源授权合规性与 GitHub 破圈定位策略

### 1.1 MIT 开源协议合规设计 (License Compliance)
* **源码协议**：EchoMind 仓库所有源代码采用 **MIT License** 开源，允许任何个人、硬件创业团队、同行开发者自由修改、私有化部署及商业集成（仅需保留版权声明）。
* **依赖与模型权重解耦（规避协议传染）**：
  * 核心推理框架 [k2-fsa/sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)（Apache-2.0）、声纹库 [modelscope/3D-Speaker](https://github.com/modelscope/3D-Speaker)（[Apache-2.0](https://github.com/modelscope/3D-Speaker/blob/main/LICENSE)）、语音识别源码 [QwenAudio/SenseVoice](https://github.com/QwenAudio/SenseVoice)（MIT）均属于宽松开源许可证，与 MIT 100% 兼容。
  * **预训练模型权重动态拉取**：Git 仓库本身**不包含**任何模型二进制权重，而是通过 `scripts/download_models.py` 在用户本地首次启动时按需下载。这既保证了 Git 仓库轻量纯净，又在法律边界上将“MIT 授权的软件框架”与“第三方模型权重条款”完全解耦。

### 1.2 GitHub 热门关键词矩阵与同行吸引策略 (SEO & Positioning)
为了吸引关注 AI 硬件、AI 眼镜、AI 录音卡及个人知识库的开发者主动检索并复用本项目，在 GitHub `README.md`、Repository Description 及 Topics 中合法合规地建立如下“开源平替与底座”定位矩阵（说明接口灵感或兼容适配关系，声明非官方附属以避免商标侵权）：

| 热点赛道与对标产品 | 同行/用户核心痛点 | EchoMind 提供的“开箱即用底座”价值 |
| --- | --- | --- |
| **AI 近眼显示眼镜**<br>极米记得 (MemoMind One / G1)、[Even Realities G1](https://www.reddit.com/r/EvenRealities/comments/1gfgjpg/even_realities_officially_supports_open_source/)、[Brilliant Labs Frame](https://github.com/brilliantlabsAR/frame-codebase)、Rokid / 闪极 AI 眼镜 | 硬件团队做好了光波导/Micro-LED 和蓝牙麦克风，但缺乏一套懂中文、能提炼“早晚安 Memo + 愿望清单 + 实时 HUD 字幕”的后端大脑。 | 提供标准 **WebSocket 双向 HUD 协议**与插件化 **`HudDriver`**，硬件同行只需 50 行代码即可把自家眼镜接上极米同款“Memo 记忆系统”。 |
| **全天候 AI 穿戴胸针/项链**<br>[BasedHardware/omi](https://github.com/BasedHardware/omi)、Limitless Pendant、ESP32-S3 DIY 穿戴 | Omi 原生后端重度绑定海外云服务（Deepgram/OpenAI/Firebase），国内网络难跑通且存在云端隐私顾虑。 | 提供 **100% 本地纯 CPU 中文语音+声纹底座**，兼容 Omi/ESP32 音频流，成为国内 DIY 穿戴玩家的首选私有化后端。 |
| **AI 录音卡/工牌**<br>Plaud Note / NotePin、传统录音笔、iPhone 语音备忘录 | 按月收取高昂的云端转写与总结订阅费；多段录音之间缺乏跨天的人物/项目长期记忆图谱连接。 | 内置 **`AudioInbox` 文件夹监听** + 类 [mem0ai/mem0](https://github.com/mem0ai/mem0) **动态人物/项目图谱**，录音拖入自动生成纪要并更新长期认知，零订阅费。 |
| **个人长记忆与本地 Agent**<br>[screenpipe](https://github.com/screenpipe/screenpipe)、Obsidian、Claude Desktop / Cursor | Screenpipe 跑 Whisper 占算力且无主人声纹过滤；Claude/Cursor 缺少真实线下口语交互的记忆上下文。 | 原生暴露 **FastMCP Server** 与 **Obsidian 双链同步**，让线上 Coding Agent 随时检索你线下开会说过的每一句话。 |

---

## 2. 核心用户故事 (User Stories)

* **US-01（多端无感拾音）**：作为用户或硬件开发者，我希望通过网页蓝牙麦克风、开源穿戴硬件（ESP32/Omi/Frame）或手机录音文件夹自动同步，把全天对话无感汇入本地服务，无需手动点击每次会议的开始和结束。
* **US-02（主人声纹锚定与防噪音污染）**：作为全天候开启拾音的用户，我希望系统能精准认出我的声音（`[HOST]`），并在我看视频、听播客或路过别人闲聊（无我参与）时自动丢弃无效音频，不污染记忆库也不浪费 LLM Token。
* **US-03（极米同款记忆卡片与主动线索抓取）**：作为用户，我希望一段对话结束后 1 分钟内，看板自动生成结构化的“记忆卡片（Episode）”，不仅包含第一人称总结和明确承诺的 To-Do，还能从随口闲聊中抓取我的“愿望清单/兴趣线索（Wishlist & Clues）”。
* **US-04（动态人物与项目记忆图谱）**：作为用户，当我多次和“王总”聊到“A项目报价”时，我希望系统能像 [mem0ai/mem0](https://github.com/mem0ai/mem0) 一样自动更新王总的最新报价底线，而不是存一堆互相矛盾的旧事实。
* **US-05（早晚安 Memo 主动推送）**：作为用户，我希望每天早上收到“早安 Memo”（今日待办、昨日未完线索、重要人物提醒），晚上收到“晚安 Memo”（全天记忆卡片汇总、新增认知事实与灵感回顾）。
* **US-06（同行插件扩展与二次开发）**：作为一名垂直领域开发者（如做销售 CRM 助手、医疗问诊记录或智能眼镜固件），我希望能通过简单的 Python 插件（Plugin Hook）或协议适配器（Provider/Adapter）挂载自定义逻辑，而无需修改 EchoMind 核心源码。

---

## 3. 功能性需求规格 (Functional Requirements - EARS 语法)

### 3.1 可插拔多源接入层 (Pluggable Ingest Layer)
* **REQ-ING-01 (WebSocket 实时流)**：**When** 客户端通过 `ws://<host>:8000/api/v1/stream/audio` 建立连接并发送包含 `device_id`、`codec` (`pcm_s16le` 或 `opus`)、`sample_rate` (默认 16000) 的握手帧后，系统 **shall** 持续接收二进制音频分片并推入对应设备的内存环形缓冲区。
* **REQ-ING-02 (本地文件夹监听)**：**When** 用户将 `.wav` / `.mp3` / `.m4a` 录音文件放入 `data/audio_inbox/` 目录时，系统 **shall** 在 3 秒内自动检测文件写入完成，转码为 16kHz 单声道 PCM 并按文件创建时间注入语音处理管线。
* **REQ-ING-03 (HUD 逆向下行反馈)**：**When** 实时流识别出高优指令或生成新待办时，系统 **shall** 通过可插拔的 `HudFormatter` 向终端下行推送精简 JSON 帧（字数 `<= 40` 字），供智能眼镜 HUD 或手机通知栏即时渲染。

### 3.2 纯 CPU 语音预处理与声纹管线 (Audio Engine Provider)
* **REQ-AUD-01 (帧级 VAD 过滤)**：**While** 接收音频流时，系统 **shall** 使用 `Silero-VAD` 进行毫秒级语音活动检测；连续静音帧 **shall** 直接在内存中丢弃，零磁盘写入。
* **REQ-AUD-02 (主人声纹注册与锚定)**：**When** 用户上传或录制 10~30 秒个人纯净语音时，系统 **shall** 通过 `3D-Speaker` 提取 192 维特征均值向量并持久化为 `host_embedding.npy`；在实时推理中，余弦相似度 `>= 0.65`（可配置）的语音段 **shall** 标记为 `HOST`。
* **REQ-AUD-03 (短语音声纹豁免与在线 Guest 聚类)**：**If** 单个有效语音段时长 `< 1.2s`，系统 **shall** 豁免独立声纹比对，直接继承同一设备 3 秒内前一句的 `speaker_role`（若无则标为 `UNKNOWN`）；**Where** 语音段时长 `>= 1.2s` 且非 `HOST`，系统 **shall** 在当前会话的在线质心池（Guest Centroid Pool）中进行余弦聚类（阈值 `0.60`），自动分配稳定的 `GUEST_1`、`GUEST_2` 标签。
* **REQ-AUD-04 (SenseVoice 多维转写)**：**When** VAD 切出有效语音段（0.5s ~ 30s）时，系统 **shall** 调用 `SenseVoice-Small (int8)` 模型完成中英混杂转写，并同步提取情绪标签（`NEUTRAL`, `HAPPY`, `ANGRY`, `SAD`）与声学事件标签（`LAUGHTER`, `SIGH`, `APPLAUSE`）。

### 3.3 动态话题切片与认知提炼引擎 (Memory Core & Event Bus)
* **REQ-MEM-01 (三维触发话题切片)**：后台巡检器每 30 秒扫描一次未闭合的 `utterances` 缓冲区，满足以下任一条件时 **shall** 闭合当前话题并触发 Episode 提炼：
  1. **物理静默切分**：距离最新一句有效语音已超过 `180 秒`（可配置）。
  2. **最大跨度切分（带滑动重叠窗口）**：连续高密度对话时长达到 `25 分钟`，强制切片，并将末尾最后 `5 句` Utterances 作为只读上下文前缀（Context Prefix）复制到下一切片。
  3. **主人缺席静默销毁**：当前缓冲段内 `HOST` 发言字数占比为 `0%` 且未开启“纯旁听会议模式”时，判定为电视/播客背景音或路人交谈，直接标记为 `DISCARDED`，**不调用** LLM。
* **REQ-MEM-02 (极米式多维认知提取)**：**When** 有效话题切片闭合后，系统 **shall** 调用 LiteLLM 并强制校验 Pydantic Schema，一次性生成标题、分类、第一人称纪要、附带 `source_quote` 的待办（`action_items`）、以及愿望清单与跟进线索（`clues_and_wishlists`）。
* **REQ-MEM-03 (长期事实 Upsert 与冲突消解)**：**When** 提取出新的实体事实（`fact_operations`）时，系统 **shall** 先召回同一主体的历史事实；若存在冲突或演进，系统 **shall** 执行 `UPDATE` 更新最新值并保留 `previous_value` 审计轨迹。
* **REQ-MEM-04 (早安/晚安 Memo 主动生成)**：系统 **shall** 通过定时调度器生成每日早安 Memo 与晚安 Memo，写入专属看板并发布事件。
* **REQ-EXT-01 (异步事件总线与插件机制)**：**When** 系统发生关键生命周期事件（`utterance.created`, `episode.closed`, `todo.created`, `memo.generated`）时，系统 **shall** 通过内部异步 `EventBus` 广播事件，允许 `plugins/` 目录下的第三方插件无侵入订阅与扩展。

---

## 4. 非功能性需求与长期演进路线图 (Roadmap v0.1 -> v1.0)

### 4.1 性能与资源约束
1. **纯 CPU 推理性能 (NFR-PERF-01)**：4 核 CPU 无独显条件下，联合推理实时率 `RTF < 0.10`。
2. **内存占用约束 (NFR-RES-01)**：后端常驻进程总内存占用 `< 1.2 GB`。
3. **协议可扩展性 (NFR-EXT-01)**：语音引擎（ASR/VAD/Speaker）、存储后端（Vector/DB）、接入源（Ingest）与触达端（Connectors/Plugins）均必须通过抽象基类（Python `Protocol` / `ABC`）解耦，支持通过配置文件一键切换实现。

### 4.2 持续迭代演进路线图 (Evolution Architecture)
* **v0.1 MVP（当前阶段 - 核心语音记忆闭环）**：纯 CPU Sherpa-ONNX 管线 + 主人声纹锚定 + 极米式记忆卡片/待办/愿望线索 + 类 Mem0 事实冲突消解 + Web PWA 看板 + FastMCP Server。
* **v0.2（多模态上下文与硬件固件生态）**：
  * 新增 `ContextSourceProvider`：可选接入桌面截图 OCR（融合 [screenpipe](https://github.com/screenpipe/screenpipe) 能力）与移动端位置/日历上下文。
  * 发布 `firmware/esp32_s3_badge` 示例固件与 [BasedHardware/omi](https://github.com/BasedHardware/omi) 蓝牙桥接插件。
* **v0.3（主动实时副驾 Real-time Copilot & 眼镜提词）**：
  * 在对话进行中（无需等 Episode 闭合）实时检索 `semantic_facts` 人物画像，向智能眼镜 HUD 推送“对方上次提到的痛点/报价底线”实时暗访提词（Teleprompter）。
* **v1.0（多租户与插件市场生态）**：
  * 支持 PostgreSQL + pgvector 团队共享知识库模式；开放社区 `plugins/` 插件仓库（销售 CRM、医疗问诊、课堂闪卡等垂类 Extractor）。
