# EchoMind 开源开发任务拆解清单 (Implementation Tasks - v0.1 MVP)

> 本文档严格对应 [`specs/spec.md`](./spec.md) 与 [`specs/design.md`](./design.md)，包含**微内核事件总线（EventBus）+ 四大可插拔接口 + 极米式认知大脑 + GitHub 破圈门面工程**，共拆解为 **6 个阶段（Phase 1 ~ Phase 6，19 个原子工程任务）**。

---

## Phase 1：微内核抽象底座与混合存储层构建 (Micro-Kernel & Storage)

**目标**：建立 MIT 开源规范的项目骨架、异步事件总线（`EventBus`）、插件热加载器（`PluginManager`）以及带 `metadata_json` 扩展能力的 SQLite (WAL + FTS5) + LanceDB 混合存储层。

- [ ] **Task 1.1：初始化 MIT 仓库结构与全局配置 (`pyproject.toml`, `LICENSE`, `backend/config.py`)**
  - **实现内容**：
    - 创建 MIT `LICENSE`、`pyproject.toml` 与 `.env.example`。
    - 编写 `backend/config.py`，支持通过配置切换 `ASR_PROVIDER`、`LLM_MODEL`、声纹阈值（`HOST_SIMILARITY_THRESHOLD=0.65`）、静默切片时间（`SILENCE_SPLIT_SECONDS=180`）及启用的插件列表。
  - **对应需求**：`NFR-PRIV-01`, `NFR-LIC-01`, `NFR-EXT-01`
  - **验证方式**：运行 `python -c "from backend.config import settings; print(settings.model_dump())"`。

- [ ] **Task 1.2：实现微内核异步事件总线与插件热加载器 (`backend/core/event_bus.py`, `plugin_manager.py`, `interfaces.py`)**
  - **实现内容**：
    - 定义 `ASRProvider`、`SpeakerProvider`、`IngestAdapter` 抽象协议接口（`typing.Protocol`）。
    - 实现异步 `EventBus`（支持 `publish` / `subscribe`）与 `@hook(topic)` 装饰器，自动扫描加载 `plugins/` 目录下的扩展插件。
    - 编写示例插件 `plugins/example_hud_logger.py` 验证无侵入挂载。
  - **对应需求**：`REQ-EXT-01`, `US-06`
  - **验证方式**：运行 `pytest tests/test_event_bus.py` 验证发布 `episode.closed` 事件时外部插件自动异步触发且异常隔离。

- [ ] **Task 1.3：实现 SQLite ORM 模型（含扩展列）与 FTS5 全文检索表 (`backend/storage/models.py`, `database.py`)**
  - **实现内容**：
    - 定义 `Utterance`, `Episode`, `ActionItem`, `ClueAndWishlist`, `SemanticFact`, `DailyMemo` 六个 SQLModel 数据模型（预留 `metadata_json` 扩展列）。
    - 开启 SQLite `PRAGMA journal_mode=WAL;`，创建 `episodes_fts` 虚拟表及同步触发器。
  - **对应需求**：`REQ-CONN-01`
  - **验证方式**：运行 `pytest tests/test_storage.py` 验证表自动创建与 FTS5 中文关键词检索。

- [ ] **Task 1.4：实现 LanceDB 本地向量库与 Hybrid RRF 混合检索 (`backend/storage/vector_store.py`)**
  - **实现内容**：
    - 封装本地嵌入式 LanceDB 表 `episodes_vec` 与轻量本地特征向量化。
    - 实现 `hybrid_search(query, limit)`：通过 Reciprocal Rank Fusion (RRF) 融合 SQLite FTS5 BM25 与向量语义检索结果。
  - **对应需求**：`REQ-CONN-01`
  - **验证方式**：插入测试记忆卡片后调用 `hybrid_search`，验证关键词与语义检索合并排序。

---

## Phase 2：纯 CPU 可插拔语音引擎研发 (Sherpa-ONNX Speech Provider)

**目标**：实现 `SherpaOnnxLocalProvider`，在无 GPU 环境下跑通 `Silero-VAD` 静音过滤 + `3D-Speaker` 主人声纹锚定/短语音豁免/Guest 在线聚类 + `SenseVoice-Small (int8)` 多维转写。

- [ ] **Task 2.1：编写 ONNX 量化模型按需下载器 (`scripts/download_models.py`, `engine_manager.py`)**
  - **实现内容**：
    - 自动从 [k2-fsa/sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) GitHub Releases 按需下载 `SenseVoice-Small (int8)`、`silero_vad.onnx` 与 `3D-Speaker` 模型至本地 `models/` 目录（保证 Git 仓库纯 MIT 代码零权重污染）。
    - 实现线程安全的模型单例预热加载器与 Mock 降级模式（方便 CI/CD 无模型快速单测）。
  - **对应需求**：`NFR-PERF-01`, `AC-01`
  - **验证方式**：运行 `python scripts/download_models.py` 完成模型就位，内存占用 `< 800MB`。

- [ ] **Task 2.2：实现主人声纹注册、短语音豁免与在线 Guest 聚类 (`backend/audio_engine/speaker_id.py`)**
  - **实现内容**：
    - 实现 `enroll_host_voice(audio_samples)` 提取 192 维 L2 归一化均值向量保存至 `data/voiceprint/host_embedding.npy`。
    - 实现 `identify_speaker(audio_samples, duration_ms, device_id)`：
      1. `< 1.2s` 短语音自动继承该设备 3 秒内上句角色；
      2. 余弦相似度 `>= 0.65` 判定为 `HOST`；
      3. 其余语音在会话级 `GuestCentroidPool` 中进行在线增量聚类，稳定输出 `GUEST_1`, `GUEST_2`。
  - **对应需求**：`REQ-AUD-02`, `REQ-AUD-03`
  - **验证方式**：运行 `pytest tests/test_speaker_id.py` 验证主人音频、短音频（0.8s）与双 Guest 交替音频的角色分配。

- [ ] **Task 2.3：实现 Silero-VAD 缓冲与 SenseVoice 情绪/事件转写 (`vad_buffer.py`, `transcriber.py`)**
  - **实现内容**：
    - 封装流式 `VADBuffer`：静音帧直接丢弃，检测到完整语句（0.5s~30s）时吐出 `SpeechChunk`。
    - 封装 `SenseVoiceTranscriber`：提取 `emotion_tag` (`HAPPY`/`NEUTRAL`/`ANGRY`/`SAD`)、声学事件 (`LAUGHTER`/`SIGH`) 与纯净文本，并通过 `EventBus` 广播 `utterance.created`。
  - **对应需求**：`REQ-AUD-01`, `REQ-AUD-04`, `AC-02`
  - **验证方式**：运行 `python scripts/simulate_stream.py --file sample.wav`，2 秒内打印带 `[HOST]`、情绪标签与耗时的转写流水（RTF `< 0.10`）。

---

## Phase 3：极米式认知大脑与类 Mem0 记忆演进 (Memory Core)

**目标**：实现动态话题切片状态机（含 25 分钟滑动重叠窗口与主人缺席过滤）、极米同款“纪要+待办+愿望线索”提炼、类 Mem0 事实冲突消解与早晚安 Memo 调度。

- [ ] **Task 3.1：实现三维动态话题切片状态机 (`backend/memory_core/segmenter.py`)**
  - **实现内容**：
    - 实现 `EpisodeSegmenter`：① 物理静默超 3 分钟闭合；② 连续对话满 25 分钟强制闭合，并复制最后 5 句（标记 `is_context_prefix=True`）留给下一段；③ 若缓冲段内 `HOST` 字数占比为 `0%` 且非旁听模式，直接标记 `category='DISCARDED'` 归档，零 Token 消耗。
  - **对应需求**：`REQ-MEM-01`, `AC-03`
  - **验证方式**：运行 `pytest tests/test_segmenter.py` 测试 3 分钟静默闭合、25 分钟重叠保留、以及纯 Guest 背景音零 Token 丢弃。

- [ ] **Task 3.2：实现 LLM 结构化提取器与类 Mem0 事实冲突消解 (`extractor.py`, `fact_resolver.py`)**
  - **实现内容**：
    - 编写 `schemas.py` 与 `prompts.py`（内置口语纠错、第一人称视角、带 `source_quote` 的待办提取、`WISHLIST/FOLLOW_UP_CLUE/IDEA_SPARK` 抓取）。
    - 实现 `fact_resolver.py`：预召回相关的已知 `semantic_facts`，指导 LLM 输出 `ADD` / `UPDATE` / `NOOP`，自动更新冲突事实并记录 `previous_value`，完成后向 `EventBus` 发布 `episode.closed` 与 `todo.created` 事件。
  - **对应需求**：`REQ-MEM-02`, `REQ-MEM-03`, `AC-04`
  - **验证方式**：运行 `pytest tests/test_memory_core.py` 验证记忆卡片、待办、愿望清单及事实冲突更新。

- [ ] **Task 3.3：实现「早安 Memo」与「晚安 Memo」主动推进调度器 (`proactive_cron.py`)**
  - **实现内容**：
    - 基于 `APScheduler` 注册每日定时任务与手动触发接口，生成 `MORNING_BRIEF` 与 `EVENING_REVIEW`，落库 `daily_memos` 并发布 `memo.generated` 事件。
  - **对应需求**：`REQ-MEM-04`
  - **验证方式**：调用 `generate_daily_memo("MORNING_BRIEF")` 与 `"EVENING_REVIEW"` 验证生成的 Markdown 内容。

---

## Phase 4：多源音频接入网关与 REST API (Ingest & Backend API)

**目标**：打通 WebSocket 实时双向流（含智能眼镜 HUD 逆向字幕/通知推送）、本地文件夹监听自动导入以及供前端调用的全套 REST API。

- [ ] **Task 4.1：实现 WebSocket 实时音频网关与 HUD 逆向推送 (`backend/ingest/ws_stream.py`)**
  - **实现内容**：
    - 实现 `/api/v1/stream/audio` 端点：解析握手帧，接收 PCM 二进制流送入 `VADBuffer`。
    - 订阅 `EventBus` 的 `utterance.created` 与 `episode.closed` 事件，向连接的智能眼镜/PWA 逆向推送带 `hud_display`（40 字内）的实时 JSON 帧。
  - **对应需求**：`REQ-ING-01`, `REQ-ING-03`
  - **验证方式**：运行 `python scripts/simulate_stream.py --ws` 验证双向推流与 HUD 通知接收。

- [ ] **Task 4.2：实现本地录音收件箱监听器 (`backend/ingest/file_watcher.py`)**
  - **实现内容**：
    - 使用 `watchdog` 监听 `data/audio_inbox/`，自动将拖入的 `.wav/.mp3/.m4a` 录音转为 16kHz PCM 并注入管线，支持 Plaud Note / 录音笔 / iPhone 快捷指令无感同步。
  - **对应需求**：`REQ-ING-02`
  - **验证方式**：将测试音频放入 `data/audio_inbox/`，验证自动转写并归档至 `data/audio_archive/`。

- [ ] **Task 4.3：实现全套业务与插件管理 REST API (`backend/api/routes_*.py`, `main.py`)**
  - **实现内容**：
    - 实现 `/api/v1/episodes`（列表/搜索/手动 Flush）、`/api/v1/actions`（待办流转）、`/api/v1/clues`（愿望清单管理与一键转待办）、`/api/v1/facts`（人物/项目图谱）、`/api/v1/memos`（早晚安 Memo）、`/api/v1/voiceprint/enroll`（在线声纹注册）及 `/api/v1/plugins`（已挂载插件列表）。
  - **对应需求**：`US-01` ~ `US-06`
  - **验证方式**：运行 `pytest tests/test_api.py` 全量通过所有 REST 端点测试。

---

## Phase 5：生态连接器 —— FastMCP Server、Obsidian 双链与 Webhook (`connectors/`)

**目标**：通过事件总线挂载 Obsidian 同步与 Webhook 通知，并暴露标准 FastMCP Server 供 Claude Desktop / Cursor 直接调用。

- [ ] **Task 5.1：实现原生 FastMCP Server (`backend/connectors/mcp_server.py`)**
  - **实现内容**：
    - 暴露 `search_personal_memory`、`get_pending_todos`、`get_wishlists_and_clues`、`query_entity_graph` 四个标准 MCP Tools。
  - **对应需求**：`REQ-CONN-02`, `AC-06`
  - **验证方式**：运行 `pytest tests/test_mcp.py` 验证 4 个 MCP 工具返回结构化 Markdown 上下文。

- [ ] **Task 5.2：实现基于事件总线的 Obsidian 双链笔记同步与 Webhook 推送 (`obsidian_sync.py`, `webhook_notifier.py`)**
  - **实现内容**：
    - 监听 `episode.closed` 与 `memo.generated` 事件，自动在 `data/obsidian_vault/` 生成带 YAML Frontmatter 和 `[[实体双链]]` 的 Markdown 笔记，并推送到飞书/企微/Bark Webhook。
  - **对应需求**：`REQ-CONN-03`
  - **验证方式**：触发 Episode 生成后检查 `data/obsidian_vault/Episodes/` 下的双链 Markdown 文件。

---

## Phase 6：极米同款 Web PWA 工作台与 GitHub 开源门面打包 (`web_pwa/` & Release)

**目标**：打造响应式 Web 工作台，并编写高吸引力的中英双语开源 `README.md`（覆盖极米记得/Omi/Plaud/Frame 关键词矩阵与插件开发指南）。

- [ ] **Task 6.1：搭建 Next.js 响应式工作台与 WebAudio 实时拾音组件 (`web_pwa/`)**
  - **实现内容**：
    - 顶部「伴随拾音与智能眼镜 HUD 模拟器控制台」：麦克风选择、16kHz WebSocket 实时推流、主人声纹在线录制弹窗、智能眼镜单绿光波导 HUD 实时预览条、立即生成卡片（Flush）按钮。
    - 四大核心视图 Tab：**记忆卡片流 (Episodes)**、**行动与愿望清单 (To-Do & Wishlist)**、**动态认知图谱 (Memory Graph)**、**早晚安 Memo (Daily Brief)**。
  - **对应需求**：`AC-05`
  - **验证方式**：启动前后端，在浏览器完整体验声纹注册、实时说话上屏、卡片生成与待办勾选。

- [ ] **Task 6.2：编写 Dockerfile、docker-compose.yml 与高传播力 GitHub README.md**
  - **实现内容**：
    - 编写 `Dockerfile` 与 `docker-compose.yml` 一键部署编排。
    - 编写极具吸引力的 `README.md`：包含中英双语介绍、对标 **极米记得 (MemoMind) / Plaud Note / [Omi](https://github.com/BasedHardware/omi) / [Even Realities G1](https://www.reddit.com/r/EvenRealities/comments/1gfgjpg/even_realities_officially_supports_open_source/) / [Brilliant Labs Frame](https://github.com/brilliantlabsAR/frame-codebase)** 的功能矩阵、30 行代码编写自定义插件教程、以及推荐的 GitHub Topics 标签清单。
  - **对应需求**：`NFR-LIC-01`
  - **验证方式**：按 `README.md` 指引一键跑通端到端演示。
