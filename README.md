# 🧠 EchoMind — 开源、100% 本地纯 CPU 的「个人数字第二大脑」与 AI 穿戴记忆中枢

<p align="center">
  <strong>The Open-Source, Self-Hosted Memory Backend Inspired by MemoMind (极米记得), Omi, Plaud Note, Screenpipe & Mem0</strong>
</p>

<p align="center">
  <a href="https://github.com/zhaimingyou/EchoMind/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-emerald.svg" alt="MIT License"></a>
  <a href="https://github.com/k2-fsa/sherpa-onnx"><img src="https://img.shields.io/badge/Inference-Pure%20CPU%20(Zero%20GPU)-blue.svg" alt="Pure CPU"></a>
  <a href="https://github.com/zhaimingyou/EchoMind"><img src="https://img.shields.io/badge/MCP-FastMCP%20Ready-indigo.svg" alt="MCP Ready"></a>
  <a href="https://github.com/zhaimingyou/EchoMind"><img src="https://img.shields.io/badge/Privacy-100%25%20Local%20Audio-amber.svg" alt="100% Local"></a>
</p>

---

## 🌟 为什么做 EchoMind？(Why EchoMind?)

2025~2026 年，以 **极米记得（MemoMind One / G1 / L1）**、**[Even Realities G1](https://www.reddit.com/r/EvenRealities/comments/1gfgjpg/even_realities_officially_supports_open_source/)**、**[Brilliant Labs Frame](https://github.com/brilliantlabsAR/frame-codebase)** 为代表的近眼显示 AI 眼镜，以及 **[BasedHardware/omi](https://github.com/BasedHardware/omi)**、**Plaud Note / NotePin**、**Limitless Pendant** 等随身 AI 穿戴硬件迎来了爆发。

然而，无论是个人极客还是智能硬件创业同行，在落地“全天候语音伴随”时都面临四大核心痛点：
1. **记录的割裂感与 Token 黑洞**：24 小时开启拾音，如何过滤看电视/路人闲聊等无效背景音？如何把源源不断的音频流切成上下文完整的“记忆卡片（Episode）”？
2. **昂贵的云端订阅与隐私焦虑**：商业录音卡按月收取高昂转写订阅费，且全天私密谈话上传第三方云端存在合规与隐私隐患。
3. **重度依赖独立显卡**：传统本地 Whisper 方案极其消耗 GPU 显存，无法在普通 NAS、轻薄本或边缘迷你主机（如 Intel N100）上 24/7 低功耗常驻。
4. **“只记录、不推进”与记忆前后矛盾**：普通录音转写只会堆砌海量文字，缺少极米式的**“待办承诺抓取 + 随口愿望清单提取 + 早晚安 Memo 主动推进”**，以及类 **[mem0ai/mem0](https://github.com/mem0ai/mem0)** 的人物/项目长期事实冲突消解。

**EchoMind** 正是为解决上述痛点而生的 **MIT 开源软件底座** —— **零独立显卡依赖（纯 CPU 实时率 `RTF < 0.05`）、硬件无关协议接入、微内核插件化扩展、100% 本地语音与声纹闭环**。

---

## 📊 开源生态横向对比 (Ecosystem Comparison)

| 核心维度 | 极米记得 (MemoMind) / Plaud | [BasedHardware/omi](https://github.com/BasedHardware/omi) | [screenpipe](https://github.com/screenpipe/screenpipe) | [mem0ai/mem0](https://github.com/mem0ai/mem0) | **🚀 EchoMind (本项目)** |
| --- | --- | --- | --- | --- | --- |
| **开源协议** | 商业闭源 + 订阅制 | MIT (重度绑定海外云服务) | MIT | Apache-2.0 (仅文本 SDK) | **MIT License (全栈开箱即用)** |
| **本地算力要求** | 依赖云端 ASR 借道转写 | 依赖 Deepgram / OpenAI 云端 | 本地跑 Whisper 吃 CPU/GPU | 无语音处理能力 | **纯 CPU 极速推理 (内存 `< 1GB`, `RTF < 0.05`)** |
| **中文 + 情绪/笑声识别** | 商业私有模型 | 中文支持较弱，无情绪标签 | 依赖 Whisper，无声学事件 | 不支持 | **内置 [SenseVoice-Small (int8)](https://github.com/QwenAudio/SenseVoice) 中英混杂 + 情绪/笑声/叹气标签** |
| **主人声纹锚定与降噪** | 硬件端声学定向拾音 | 依赖云端配置 | 无主人声纹过滤 | 不支持 | **[3D-Speaker](https://github.com/modelscope/3D-Speaker) 主人声纹锚定 + `<1.2s` 短语音豁免 + 主人缺席零 Token 销毁** |
| **极米式“主动推进”** | 记忆卡片 + 待办 + 愿望清单 + 早晚安 Memo | 基础总结与插件流 | 偏重桌面历史回溯 | 被动 API 调用 | **完整复刻：记忆卡片 + 待办(含原话防幻觉) + 随口愿望/线索 + 早晚安 Memo** |
| **智能眼镜 HUD 适配** | 极米双目单绿光波导专属 | 无近眼 HUD 下行帧规范 | 无硬件显示交互 | 不支持 | **原生 WebSocket 40 字单绿光波导 HUD 逆向推送 + 网页 HUD 模拟器** |
| **AI Agent / 知识库连接** | 封闭 App 生态 | Webhook 插件 | MCP 支持 | Python/JS SDK | **原生暴露 4 个 FastMCP 工具 + Obsidian `[[实体双链]]` 自动同步** |

---

## 🏗️ 微内核与插件化系统架构 (Pluggable Micro-Kernel Architecture)

为了方便**智能眼镜/穿戴硬件同行**直接拿去作为后端底座，并为后续版本（`v0.1 -> v1.0`）预留充足的迭代空间，EchoMind 采用 **「微内核 + 异步事件总线 (`EventBus`) + 四大可插拔抽象契约」** 设计：

```text
+---------------------------------------------------------------------------------------+
|                   扩展点 1: 多模态接入适配器 (IngestAdapter Protocol)                  |
|  [WebSocket 实时流]   [Audio Inbox 录音监听]   [Omi/ESP32 BLE*]   [Screen/Calendar*]  |
+---------+---------------------+----------------------+-------------------+------------+
          |                     |                      |                   |
          +---------------------+----------+-----------+-------------------+
                                           | 16kHz Mono PCM / Context Frame
                                           v
+---------------------------------------------------------------------------------------+
|                   扩展点 2: 纯 CPU 语音算力层 (SpeechProvider Protocol)                |
|  - Silero-VAD: 毫秒级静音帧内存丢弃（零磁盘写入）                                      |
|  - 3D-Speaker: 192维主人声纹锚定 [HOST] + <1.2s 短语音豁免 + Guest 在线增量质心聚类     |
|  - SenseVoice-Small (int8): 中英粤日韩转写 + 情绪 (HAPPY/SAD) + 事件 (LAUGHTER/SIGH)  |
+------------------------------------------+--------------------------------------------+
                                           | Structured Utterance
                                           v
+---------------------------------------------------------------------------------------+
|                        核心微内核: 记忆与认知状态机 (Memory Core)                      |
|  1. EpisodeSegmenter: 3分钟物理静默闭合 / 25分钟滑动重叠窗口(保留末尾5句) / 缺席销毁   |
|  2. CognitiveExtractor: 第一人称卡片摘要 + 高确定性待办(附原话) + 随口愿望清单/线索     |
|  3. FactResolver: 类 Mem0 人物/项目长期画像 ADD / UPDATE / NOOP 自动消解冲突           |
|  4. ProactiveMemoGenerator: 每日定时生成「早安 Memo」与「晚安 Memo」                    |
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
| 扩展点 3: 混合存储层   |    | 扩展点 4: 生态连接器       |   | 第三方行业扩展插件目录    |
| - SQLite (WAL + FTS5) |    | - FastMCP Server (4 Tools)|   | (plugins/*.py)           |
| - Hybrid Vector RRF   |    | - Obsidian [[双链]] 同步   |   | - 智能眼镜 HUD 提词插件  |
| - metadata_json 扩展列 |    | - 飞书/企微/Bark Webhook  |   | - 销售 CRM / 医疗问诊插件|
+-----------------------+    +---------------------------+   +--------------------------+
```

详细规格与设计文档请查阅 [`specs/`](./specs/) 目录：
* 📋 **产品与需求规格说明书**：[`specs/spec.md`](./specs/spec.md)
* 📐 **系统架构与详细技术设计**：[`specs/design.md`](./specs/design.md)
* ✅ **敏捷开发任务拆解清单**：[`specs/tasks.md`](./specs/tasks.md)

---

## ⚡ 3 分钟快速启动 (Quick Start)

### 方式一：本地 Python 极速体验（自带仿真与 Web HUD 工作台）

```bash
# 1. 克隆仓库
git clone https://github.com/zhaimingyou/EchoMind.git
cd EchoMind

# 2. 安装核心依赖
pip install -e ".[dev]"

# 3. (可选) 一键下载纯 CPU ONNX 量化语音模型 (SenseVoice + Silero-VAD + 3D-Speaker)
python3 scripts/download_models.py

# 4. 运行全链路命令行仿真 (体验声纹锚定、短语音豁免、极米式卡片与 Mem0 冲突消解)
python3 scripts/simulate_stream.py

# 5. 启动 Web 工作台与 API 服务
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

浏览器打开 **`http://localhost:8000`**，点击右上角 **「✨ 一键注入极米+Mem0演示数据」**，即可直接体验：
* **单绿光波导智能眼镜 HUD 模拟器**（40 字实时字幕与待办触发逆向推送）
* **情景记忆卡片流（Episodes）** 与原始声纹/情绪剧本回放
* **待办事项（Action Items）** 与 **随口愿望清单/线索（Wishlist & Clues 一键转待办）**
* **动态人物/项目记忆图谱（Mem0 Facts）**（自动将“王总报价底线 50万”更新为“35万”并保留历史变更轨迹）
* **早安 Memo / 晚安 Memo** 主动推进简报与 `data/obsidian_vault/` 双链笔记实时生成

### 方式二：Docker Compose 一键常驻部署（NAS / 边缘主机推荐）

```bash
cp .env.example .env
# 可在 .env 中填入 DeepSeek / Qwen / OpenAI API Key 或本地 Ollama 地址（不填默认启用本地高精规则引擎）
docker compose up -d
```

---

## 🔌 30 行代码开发一个自定义插件 (Write a Plugin in 30 Lines)

得益于微内核 `EventBus` 架构，任何硬件团队或垂直行业开发者只需在 [`plugins/`](./plugins/) 目录下新建一个 `.py` 文件，即可无侵入订阅全生命周期事件（参考 [`plugins/example_hud_logger.py`](./plugins/example_hud_logger.py)）：

```python
from backend.core.plugin_manager import EchoMindPlugin, hook

class MySmartGlassesOrCRMPlugin(EchoMindPlugin):
    name = "custom_glasses_crm_bridge"
    version = "0.1.0"
    description = "Push real-time captions to BLE glasses and sync closed episodes to CRM."

    @hook("utterance.created")
    async def on_speech(self, payload: dict):
        # payload 包含 speaker_role (HOST/GUEST_1), emotion_tag, acoustic_event, text_content
        print(f"[眼镜 HUD 实时上屏] {payload['speaker_role']}: {payload['text_content']}")

    @hook("episode.closed")
    async def on_episode(self, payload: dict):
        # payload 包含 title, summary, action_items, clues_and_wishlists, facts_updated
        print(f"[新记忆卡片闭合] 《{payload['title']}》 待办数: {len(payload['action_items'])}")
```

---

## 🤖 接入 Claude Desktop / Cursor (FastMCP Server)

在 Claude Desktop 或 Cursor 的 MCP 配置文件中添加以下配置，让你的 AI 编程/办公助手直接检索你线下开会说过的每一句话：

```json
{
  "mcpServers": {
    "echomind-memory": {
      "command": "python3",
      "args": ["-m", "backend.connectors.mcp_server"],
      "cwd": "/path/to/EchoMind"
    }
  }
}
```

暴露的 4 个标准 MCP 工具：
1. `search_personal_memory(query, category, limit)`：SQLite FTS5 BM25 + 向量语义 RRF 混合检索历史对话与卡片。
2. `get_pending_todos(assignee)`：获取所有口头承诺但尚未完成的待办清单及原话出处。
3. `get_wishlists_and_clues(clue_type)`：获取日常闲聊中提到的愿望清单（`WISHLIST`）、跟进线索（`FOLLOW_UP_CLUE`）与灵感火花（`IDEA_SPARK`）。
4. `query_entity_graph(entity_name)`：查询某个客户、项目或主人自己的最新沉淀事实与历史变更轨迹。

---

## 🗺️ 持续迭代路线图 (Roadmap: v0.1 -> v1.0)

* [x] **v0.1 MVP（当前版本）**：纯 CPU 语音与声纹锚定底座 + 极米式记忆卡片/待办/愿望线索 + 类 Mem0 事实冲突消解 + Web PWA 看板（含智能眼镜单绿 HUD 模拟器）+ FastMCP Server + Obsidian 双链同步。
* [ ] **v0.2（开源硬件固件与多模态上下文）**：发布 ESP32-S3 随身胸针固件示例、[BasedHardware/omi](https://github.com/BasedHardware/omi) 蓝牙直接桥接插件、以及桌面截屏 OCR 上下文适配器（融合 [screenpipe](https://github.com/screenpipe/screenpipe) 理念）。
* [ ] **v0.3（智能眼镜实时暗访提词器 Real-time Teleprompter）**：在对话进行中实时匹配 `semantic_facts` 人物图谱，在智能眼镜 HUD 上浮现“对方上次提到的痛点与报价底线”。
* [ ] **v1.0（团队共享记忆库与行业插件市场）**：支持 PostgreSQL + pgvector 多租户部署，开放销售跟单 CRM、医疗问诊记录、律所访谈等行业提炼插件模板。

---

## 📄 开源协议与免责声明 (License & Disclaimer)

* 本项目源代码基于 **[MIT License](./LICENSE)** 开源，欢迎任何个人开发者、智能眼镜/穿戴硬件厂商自由使用、修改与商业集成。
* *Disclaimer: EchoMind is an independent open-source software project inspired by product concepts from MemoMind (极米记得), Omi, Plaud Note, Screenpipe, and Mem0. It is not officially affiliated with or endorsed by XGIMI or other mentioned brands.*
