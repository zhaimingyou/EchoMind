# EchoMind 系统架构与详细技术设计文档 (Technical Design - v0.1 MVP & Micro-Kernel Architecture)

> 本文档基于 [`specs/spec.md`](./spec.md) 编写。为了确保项目开源后**具备极强的后期升级空间，并方便同行/硬件团队无侵入地二次开发**，系统在模块化单体内部采用**「微内核 + 异步事件总线 (EventBus) + 四大可插拔抽象接口 (Providers & Plugins)」**架构设计。

---

## 1. 微内核与插件化全局架构图 (Pluggable Micro-Kernel Architecture)

同行开发者无需改动 `memory_core` 核心状态机，只需在对应扩展点挂载 Adapter 或 Plugin 即可接入新硬件、切换新模型或定制垂直行业提炼逻辑：

```text
+---------------------------------------------------------------------------------------+
|                   扩展点 1: 多模态接入适配器 (IngestAdapter Protocol)                  |
|  [WS Audio Stream]   [Audio Inbox Watcher]   [Omi/BLE Bridge*]   [Screen/Calendar*]  |
+---------+---------------------+----------------------+-------------------+------------+
          |                     |                      |                   |
          +---------------------+----------+-----------+-------------------+
                                           | Unified AudioChunk / ContextEvent
                                           v
+---------------------------------------------------------------------------------------+
|                   扩展点 2: 语音算力抽象层 (SpeechProvider Protocol)                   |
|   默认内置: SherpaOnnxLocalProvider (Silero-VAD + 3D-Speaker + SenseVoice int8 CPU)   |
|   后期平替: WhisperCppProvider / FunASRServerProvider / CloudASRProvider              |
+------------------------------------------+--------------------------------------------+
                                           | Structured Utterance (含声纹/情绪/笑声叹气)
                                           v
+---------------------------------------------------------------------------------------+
|                        核心微内核: 记忆与认知状态机 (Memory Core)                      |
|  1. EpisodeSegmenter (3min静默 / 25min滑动重叠窗口 / 主人缺席零Token静默销毁)          |
|  2. CognitiveExtractor (极米式卡片纪要 + 待办事项 + 随口愿望清单/线索)                 |
|  3. FactResolver (类 Mem0 人物/项目长期画像 ADD / UPDATE / NOOP 冲突消解)             |
|  4. ProactiveScheduler (早安 Memo 主动推进 / 晚安 Memo 复盘生成)                      |
+------------------------------------------+--------------------------------------------+
                                           |
                                           v
+=======================================================================================+
|                     核心解耦中枢: 异步事件总线 (Async EventBus)                       |
|   Topics: [utterance.created]  [episode.closed]  [todo.created]  [memo.generated]     |
+=========+================================+===============================+============+
          |                                |                               |
          v                                v                               v
+-----------------------+    +---------------------------+   +--------------------------+
| 扩展点 3: 存储引擎     |    | 扩展点 4: 触达与生态插件   |   | 第三方行业扩展插件目录    |
| (StorageProvider)     |    | (Connectors & HUD Sinks)  |   | (plugins/*.py)           |
| - SQLite + FTS5       |    | - FastMCP Server (4 Tools)|   | - 销售CRM客户跟进插件*    |
| - LanceDB Vector      |    | - Obsidian 双链笔记同步    |   | - 智能眼镜实时提词插件*  |
| - (后期) PG + pgvector|    | - 智能眼镜 HUD 字幕推送器  |   | - 飞书/Notion/Apple同步* |
+-----------------------+    +---------------------------+   +--------------------------+
(* 注：带 * 号为架构已预留标准接口、可在 v0.2+ 零重构平滑挂载的扩展模块)
```

---

## 2. 为后期迭代预留的「四大抽象扩展契约」 (`backend/core/`)

为了防止代码写死导致后期升级牵一发而动全身，我们在 `backend/core/` 中定义四个核心抽象层（基于 Python `typing.Protocol` 与 `abc.ABC`）：

### 2.1 统一事件总线与插件基类 (`backend/core/event_bus.py` & `plugin_manager.py`)
所有核心模块之间通过事件解耦。当外部同行想基于 EchoMind 开发“自动同步待办到飞书日历”或“智能眼镜实时提词器”时，只需在 `plugins/` 目录下新建一个 Python 文件：

```python
from backend.core.plugin_manager import EchoMindPlugin, hook

class MyCustomGlassesPlugin(EchoMindPlugin):
    name = "even_realities_g1_hud"
    version = "0.1.0"

    @hook("utterance.created")
    async def on_realtime_speech(self, payload: dict):
        # 实时拿到主人或客户的每一句话，推送到智能眼镜 BLE / WebSocket
        pass

    @hook("episode.closed")
    async def on_episode_ready(self, payload: dict):
        # 拿到提炼好的极米式记忆卡片、To-Do 和愿望清单，同步到外部 CRM 或 Notion
        pass
```

### 2.2 语音算力 Provider 接口 (`backend/core/providers.py`)
将语音识别与声纹提取抽象为 `ASRProvider` 与 `SpeakerProvider`：
* **v0.1 默认实现 (`SherpaOnnxLocalProvider`)**：基于 [k2-fsa/sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) 在纯 CPU 上运行 `Silero-VAD` + `SenseVoice-Small (int8)` + [modelscope/3D-Speaker](https://github.com/modelscope/3D-Speaker)。
* **后期无感升级空间**：如果未来阿里开源了 `SenseVoice-V2`、或者用户在 Mac M4 上想切换 `MLX-Whisper`、或者企业部署想接 GPU 集群 `FunASR`，只需新增一个 `Provider` 子类并修改 `.env` 中的 `ASR_PROVIDER=sherpa_onnx`，业务层代码一行不用改。

### 2.3 多模态上下文预留字段 (`metadata_json`)
在数据库设计中，为 `utterances`、`episodes` 和 `semantic_facts` 统一预留 `metadata_json TEXT DEFAULT '{}'` 扩展列：
* **v0.1** 存放设备电量、音频信噪比、SenseVoice 原始置信度。
* **v0.2+** 当引入 GPS 地理位置（“在星巴克聊的灵感”）、心率手环数据（极米手环 L1 形态）、或桌面屏幕窗口标题（[screenpipe](https://github.com/screenpipe/screenpipe) 形态）时，无需执行破坏性数据库 `ALTER TABLE` 迁移，直接通过 `metadata_json` 平滑承载。

---

## 3. 工程目录结构规范 (Repository Layout)

```text
EchoMind/
├── README.md                       # 开源门面文档（含极米/Omi/Plaud对比矩阵、架构图、QuickStart）
├── LICENSE                         # MIT 开源协议
├── docker-compose.yml              # 一键容器编排
├── Dockerfile                      # Python 3.11-slim + ffmpeg + sherpa-onnx 环境
├── Makefile                        # 常用开发指令 (make setup, make dev, make test)
├── pyproject.toml                  # Python 依赖管理 (uv / pip 兼容)
├── .env.example                    # 环境变量模板
├── specs/                          # Spec-Driven Development 规范文档
│   ├── spec.md                     # 产品需求、开源定位与演进路线图
│   ├── design.md                   # 微内核插件化架构与详细技术设计
│   └── tasks.md                    # 敏捷开发任务拆解清单
├── plugins/                        # [开放生态目录] 第三方/社区插件热加载目录
│   ├── __init__.py
│   └── example_hud_logger.py       # 示例插件：监听事件总线并输出 HUD 提词日志
├── scripts/
│   ├── download_models.py          # 按需拉取 SenseVoice / Silero-VAD / 3D-Speaker 权重
│   ├── enroll_speaker.py           # 命令行快速注册主人声纹工具
│   └── simulate_stream.py          # 模拟 WebSocket 实时推流与本地测试脚本
├── models/                         # [Git Ignored] 本地 ONNX 模型存放目录
├── data/                           # [Git Ignored] 本地持久化数据目录
│   ├── sqlite.db                   # 核心业务与 FTS5 全文数据库
│   ├── lancedb/                    # 本地嵌入式向量库目录
│   ├── voiceprint/                 # host_embedding.npy 主人声纹特征文件
│   ├── audio_inbox/                # 外部录音文件自动监听导入目录
│   └── obsidian_vault/             # 默认本地 Markdown 记忆导出目录
├── backend/
│   ├── __init__.py
│   ├── main.py                     # FastAPI 应用入口、插件加载、生命周期与路由挂载
│   ├── config.py                   # Pydantic Settings 全局配置管理
│   ├── core/                       # [微内核抽象层 - 支撑后期平滑升级]
│   │   ├── __init__.py
│   │   ├── event_bus.py            # 异步发布/订阅事件总线 (Async EventBus)
│   │   ├── plugin_manager.py       # 插件装饰器 (@hook) 与动态扫描加载器
│   │   └── interfaces.py           # ASRProvider, SpeakerProvider, IngestAdapter 抽象契约
│   ├── api/                        # REST API 路由层
│   │   ├── routes_episodes.py      # 记忆卡片、早晚安 Memo 查询与手动 Flush 接口
│   │   ├── routes_actions.py       # 待办事项 (To-Do) 与愿望清单状态流转接口
│   │   ├── routes_facts.py         # 人物/项目长期记忆图谱查询接口
│   │   └── routes_voiceprint.py    # Web 端在线录制注册主人声纹與插件状态接口
│   ├── ingest/                     # [多源接入层]
│   │   ├── ws_stream.py            # WebSocket 实时音频流网关 + HUD 下行通知
│   │   └── file_watcher.py         # 本地录音文件夹监听与 FFmpeg 异步转码
│   ├── audio_engine/               # [纯 CPU 语音引擎层]
│   │   ├── engine_manager.py       # Sherpa-onnx 模型单例加载器
│   │   ├── vad_buffer.py           # Silero-VAD 滑动窗口与断句状态机
│   │   ├── speaker_id.py           # 3D-Speaker 锚定、短语音豁免与在线 Guest 聚类
│   │   └── transcriber.py          # SenseVoice-Small 转写与情感/事件标签解析
│   ├── memory_core/                # [认知与第二大脑层]
│   │   ├── schemas.py              # Pydantic 严格结构化输出定义
│   │   ├── prompts.py              # 认知提炼、事实冲突消解、早晚安 Memo Prompts
│   │   ├── segmenter.py            # 动态话题边界切分器（含滑动重叠窗口）
│   │   ├── extractor.py            # LiteLLM 异步提炼管线
│   │   ├── fact_resolver.py        # 长期语义事实 Upsert 与冲突消解器
│   │   └── proactive_cron.py       # 早安/晚安 Memo 定时生成调度器
│   ├── storage/                    # [混合存储层]
│   │   ├── models.py               # SQLModel ORM 表模型（含 metadata_json 扩展列）
│   │   ├── database.py             # SQLite WAL 连接池与 FTS5 触发器初始化
│   │   └── vector_store.py         # LanceDB 向量化与 Hybrid RRF 混合检索
│   └── connectors/                 # [内置生态连接器层]
│       ├── mcp_server.py           # FastMCP 标准工具暴露
│       ├── obsidian_sync.py        # 基于事件总线的 Obsidian 双链 Markdown 同步器
│       └── webhook_notifier.py     # 基于事件总线的 Bark / 飞书 / 企微 Webhook 推送器
├── tests/                          # 单元测试与端到端集成测试
└── web_pwa/                        # Next.js 响应式工作台 + WebAudio 蓝牙拾音端
```

---

## 4. 核心算法与状态机详细设计

### 4.1 声纹锚定、短语音豁免与在线 Guest 聚类 (`audio_engine/speaker_id.py`)

1. **短语音豁免机制 (Short-Utterance Immunity)**：
   * 当 VAD 切出的语音片段 `duration_ms < 1200`（小于 1.2 秒）时，声纹特征信噪比极低。
   * 若当前设备在过去 `3.0 秒` 内有上一句有效语音，直接继承上一句的 `speaker_role`；否则标记为 `UNKNOWN`。
2. **主人声纹强锚定 (Host Anchoring)**：
   * 提取 192 维 L2 归一化特征向量 $v_{curr}$，与本地持久化的主人声纹向量 $v_{host}$ 计算余弦相似度 $S_{host} = v_{curr} \cdot v_{host}$。
   * 当 $S_{host} \ge \theta_{host}$（默认 `0.65`）时，直接判定为 `HOST`，并使用指数移动平均（EMA，$\alpha = 0.02$）在高置信度（$S_{host} \ge 0.80$）时微调会话级适应性声纹。
3. **会话内 Guest 在线增量质心聚类 (Online Guest Centroid Pool)**：
   * 当 $S_{host} < 0.65$ 时，判定为外部交谈者（Guest）。
   * 每个活跃会话维护最多 $K=5$ 个 Guest 质心向量 $\{c_1, c_2, \dots, c_k\}$。
   * 计算 $v_{curr}$ 与现有各质心的余弦相似度：若最大相似度 $\max(S_i) \ge \theta_{guest}$（默认 `0.60`），归入对应 `GUEST_i` 并更新质心；否则开辟新角色 `GUEST_{k+1}`。
   * 当话题切片（Episode）闭合后，清空临时 Guest 质心池，避免跨场景误串。

### 4.2 SenseVoice 富文本标签解析器 (`audio_engine/transcriber.py`)

[QwenAudio/SenseVoice](https://github.com/QwenAudio/SenseVoice) 原生输出带有特殊 Token 的文本，如 `<|zh|><|HAPPY|><|Laughter|>今天这个方案太棒了`。
解析器通过正则将其拆解为结构化字段：
* `lang`: `"zh"` / `"en"` / `"yue"` / `"ja"` / `"ko"`
* `emotion_tag`: `"NEUTRAL"` | `"HAPPY"` | `"ANGRY"` | `"SAD"` | `"FEARFUL"`
* `acoustic_event`: `"NONE"` | `"LAUGHTER"` | `"SIGH"` | `"APPLAUSE"` | `"COUGH"`
* `clean_text`: `"今天这个方案太棒了"`

### 4.3 带滑动重叠窗口的话题切片状态机 (`memory_core/segmenter.py`)

* **条件 A（物理静默闭合）**：距离最新一句有效语音已超过 `180 秒` 且 `HOST` 发言字数占比 `> 0%`，正常闭合当前 Episode，触发 `episode.closed` 事件。
* **条件 B（25 分钟最大跨度 + 滑动重叠窗口）**：连续高密度对话时长达到 `25 分钟`，强制闭合当前 Episode，并将末尾最后 `5 句` Utterances 标记 `is_context_prefix=True` 复制到下一段，彻底解决长会议硬切丢失上下文的痛点。
* **条件 C（主人缺席零 Token 过滤）**：静默超 `180 秒` 且整个缓冲段内 `HOST` 发言占比为 `0%`（且未开启旁听模式），判定为电视背景音或路人交谈，直接标记 `category='DISCARDED'`，零 Token 消耗。

### 4.4 极米式主动记忆提炼与类 Mem0 事实冲突消解 (`extractor.py` & `fact_resolver.py`)

#### Pydantic 结构化认知模型 (`memory_core/schemas.py`)

```python
from pydantic import BaseModel, Field
from typing import List, Optional, Literal

class ActionItemExtract(BaseModel):
    content: str = Field(description="明确承诺的具体待办事项或行动项")
    assignee: str = Field(description="执行人，主人填 HOST，其他人填具体称呼")
    due_date_iso: Optional[str] = Field(default=None, description="推算出的 ISO 截止时间，无则 null")
    priority: Literal["HIGH", "MEDIUM", "LOW"] = Field(default="MEDIUM")
    source_quote: str = Field(description="触发该待办的原话引用，用于防幻觉核对")

class ClueAndWishlistExtract(BaseModel):
    clue_type: Literal["WISHLIST", "FOLLOW_UP_CLUE", "IDEA_SPARK"] = Field(
        description="WISHLIST=随口提到的想买/想体验的事物；FOLLOW_UP_CLUE=非硬性承诺但值得后续跟进的线索；IDEA_SPARK=一闪而过的灵感"
    )
    content: str = Field(description="提炼后的愿望、线索或灵感内容")
    source_quote: str = Field(description="对应的原话引用")

class FactOperationExtract(BaseModel):
    operation: Literal["ADD", "UPDATE", "NOOP"] = Field(
        description="对比已有事实库：新增填 ADD，修正/更新旧事实填 UPDATE，重复无变化填 NOOP"
    )
    existing_fact_id: Optional[str] = Field(default=None, description="当 operation 为 UPDATE 时填入被更新的旧事实 ID")
    subject: str = Field(description="主体名称，如 'HOST', '王总', 'EchoMind项目'")
    predicate: str = Field(description="关系或属性，如 '饮食禁忌', '报价底线', '交付节点', '技术偏好'")
    object_value: str = Field(description="最新的具体事实描述")
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)

class EpisodeCognitiveResult(BaseModel):
    is_meaningful: bool = Field(description="是否为有实质信息的对话（纯测试音、破碎口头禅返回 false）")
    title: str = Field(description="10字以内的记忆卡片标题")
    category: Literal["WORK", "MEETING", "IDEA", "LIFE", "CHITCHAT"]
    importance_score: int = Field(ge=1, le=5, description="1=纯闲聊，3=常规记录，5=核心决策或高价值灵感")
    summary_markdown: str = Field(description="第一人称（‘我’）视角撰写的结构化要点总结")
    action_items: List[ActionItemExtract] = Field(default_factory=list)
    clues_and_wishlists: List[ClueAndWishlistExtract] = Field(default_factory=list)
    fact_operations: List[FactOperationExtract] = Field(default_factory=list)
```

---

## 5. 数据库表结构设计 (SQLite Schema + `metadata_json` 扩展列)

在 6 张核心表中统一预留 `metadata_json` 字段，保障 v0.1 到 v1.0 升级无需破坏性迁移：

```sql
-- 1. 语音原子流水表 (Utterances)
CREATE TABLE utterances (
    id TEXT PRIMARY KEY,
    timestamp DATETIME NOT NULL,
    duration_ms INTEGER NOT NULL,
    speaker_role TEXT NOT NULL,           -- 'HOST', 'GUEST_1', 'GUEST_2', 'UNKNOWN'
    speaker_score REAL DEFAULT 0.0,
    emotion_tag TEXT DEFAULT 'NEUTRAL',
    acoustic_event TEXT DEFAULT 'NONE',   -- 'LAUGHTER', 'SIGH', 'APPLAUSE', 'NONE'
    text_content TEXT NOT NULL,
    is_context_prefix BOOLEAN DEFAULT 0,
    episode_id TEXT,
    device_id TEXT DEFAULT 'default_mic',
    metadata_json TEXT DEFAULT '{}'       -- 预留多模态上下文扩展 (GPS/设备状态/屏幕窗口)
);

-- 2. 情景记忆卡片表 (Episodes)
CREATE TABLE episodes (
    id TEXT PRIMARY KEY,
    start_time DATETIME NOT NULL,
    end_time DATETIME NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    category TEXT NOT NULL,               -- 'WORK', 'MEETING', 'IDEA', 'LIFE', 'CHITCHAT', 'DISCARDED'
    importance_score INTEGER DEFAULT 3,
    host_word_ratio REAL DEFAULT 0.0,
    is_vectorized BOOLEAN DEFAULT 0,
    metadata_json TEXT DEFAULT '{}',      -- 预留外部插件挂载数据 (如 CRM ID / 会议地点)
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 3. 行动与待办表 (Action Items)
CREATE TABLE action_items (
    id TEXT PRIMARY KEY,
    episode_id TEXT REFERENCES episodes(id),
    content TEXT NOT NULL,
    assignee TEXT DEFAULT 'HOST',
    priority TEXT DEFAULT 'MEDIUM',
    due_date DATETIME,
    status TEXT DEFAULT 'PENDING',        -- 'PENDING', 'DONE', 'DISMISSED'
    source_quote TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 4. 愿望清单与潜在线索表 (Clues & Wishlists - 极米特色能力)
CREATE TABLE clues_and_wishlists (
    id TEXT PRIMARY KEY,
    episode_id TEXT REFERENCES episodes(id),
    clue_type TEXT NOT NULL,              -- 'WISHLIST', 'FOLLOW_UP_CLUE', 'IDEA_SPARK'
    content TEXT NOT NULL,
    source_quote TEXT,
    status TEXT DEFAULT 'ACTIVE',         -- 'ACTIVE', 'ARCHIVED', 'CONVERTED_TO_TODO'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 5. 长期语义事实与人物/项目图谱表 (Semantic Facts - 类 Mem0 动态更新)
CREATE TABLE semantic_facts (
    id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object_value TEXT NOT NULL,
    previous_value TEXT,                  -- 记录被 UPDATE 前的旧值
    confidence REAL DEFAULT 0.9,
    status TEXT DEFAULT 'ACTIVE',         -- 'ACTIVE', 'DEPRECATED'
    last_updated DATETIME NOT NULL,
    source_episode_id TEXT REFERENCES episodes(id)
);

-- 6. 主动推进早晚安日报表 (Daily Memos)
CREATE TABLE daily_memos (
    id TEXT PRIMARY KEY,
    memo_date TEXT NOT NULL,
    memo_type TEXT NOT NULL,              -- 'MORNING_BRIEF', 'EVENING_REVIEW'
    content_markdown TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 7. SQLite FTS5 全文检索引擎虚拟表
CREATE VIRTUAL TABLE episodes_fts USING fts5(
    episode_id UNINDEXED,
    title,
    summary,
    utterances_concat
);
```
