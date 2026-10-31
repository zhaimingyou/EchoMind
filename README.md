# EchoMind

EchoMind 用来把对话整理成可检索的记忆卡片，保留原文，并从中提取待办、愿望和人物或项目相关的信息。

这是一个早期原型。目前可以用文本和演示数据跑通整理、存储和查询流程，也提供了本地语音模型的接入代码。后端使用 Python、FastAPI 和 SQLite，附带一个简单的网页工作台。

## 目前能做什么

- 将对话保存为卡片，查看摘要和原始发言。
- 提取待办、愿望与跟进线索，保留对应原话。
- 更新人物或项目的事实，保存当前值和上一个值。
- 搜索历史卡片，手动生成早晚简报。
- 将卡片和简报写入 Obsidian 目录，通过 MCP 查询已有记录。

没有配置有效的模型 API 密钥时，内容提取使用本地规则。这个模式适合看流程，处理自由对话的能力还很有限。

## 本地运行

需要 Python 3.10 或更高版本。以下命令在项目根目录执行：

```bash
git clone https://github.com/zhaimingyou/EchoMind.git
cd EchoMind

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

打开 <http://127.0.0.1:8000>，点击右上角的演示数据按钮，可以查看卡片、待办和事实更新。也可以在页面中输入对话文本，再点击“立即闭合生成卡片”。演示数据会写入本地数据库。

API 文档在 <http://127.0.0.1:8000/docs>。运行数据默认保存在 `data/`，导出的 Markdown 笔记在 `data/obsidian_vault/`。

### 尝试语音转写

```bash
python -m pip install -e ".[full]"
python scripts/download_models.py
```

下载脚本会将模型保存到 `models/`。服务通过 WebSocket 接收单声道 PCM16 音频，默认采样率为 16 kHz，接口为 `/api/v1/stream/audio`。

本地转写需要安装 `sherpa-onnx` 并准备 SenseVoice 权重。缺少依赖或权重时，后端返回的是占位文本，不是真实转写结果。声纹识别同样需要对应模型；网页上的声纹注册按钮目前使用合成音频演示，真实录音注册可使用：

```bash
python scripts/enroll_speaker.py --wav /path/to/voice.wav
```

### 配置内容提取模型

可将 [`.env.example`](.env.example) 复制为 `.env`，设置 `LLM_MODEL`、`LLM_API_KEY` 和 `LLM_API_BASE`。模型调用使用 LiteLLM，包含在上面的 `full` 可选依赖中。

默认规则模式不调用外部模型。配置外部模型服务后，对话文本会发送到指定服务；配置 `WEBHOOK_URL` 后，生成的简报也会发送到该地址。

## MCP

安装 `fastmcp` 后，可以通过 stdio 启动 MCP 服务：

```bash
python -m pip install fastmcp
python -m backend.connectors.mcp_server
```

服务提供四个工具：

| 工具 | 用途 |
| --- | --- |
| `search_personal_memory` | 搜索卡片及相关对话 |
| `get_pending_todos` | 查询未完成待办 |
| `get_wishlists_and_clues` | 查询愿望和跟进线索 |
| `query_entity_graph` | 查询某个人物或项目的事实 |

在 MCP 客户端中，将命令设为虚拟环境中的 Python，参数设为 `-m backend.connectors.mcp_server`，工作目录设为项目根目录。API 服务和 MCP 服务需使用同一数据目录。

## 当前的限制

- 语音活动检测目前使用能量阈值；缺少声纹模型时，使用简单的频谱特征作为替代。
- 检索使用 SQLite FTS5 和字符特征向量，还没有接入语义嵌入模型。
- 录音目录已有处理函数，但服务启动时还不会自动扫描；早晚简报也尚未接入定时调度。
- 网页中的 HUD 用于演示消息显示，尚未实现具体眼镜或胸针的蓝牙适配。

目前没有真实设备上的性能基准，也没有对转写和信息提取做系统的准确率评估。

## 开发

运行现有测试：

```bash
python -m unittest discover -s tests -v
```

主要代码目录：

```text
backend/
  audio_engine/   音频分段、转写和声纹识别
  ingest/         WebSocket 接入与录音文件处理
  memory_core/    卡片整理、信息提取和事实更新
  storage/        SQLite 存储与检索
  connectors/     MCP、Obsidian 和 Webhook
plugins/          事件订阅插件示例
web_pwa/          网页工作台
scripts/          模型下载、声纹注册和流程演示
```

插件示例见 [`plugins/example_hud_logger.py`](plugins/example_hud_logger.py)。设计和计划见 [`specs/`](specs/)，其中部分内容尚未实现。

## 许可证

[MIT](LICENSE)。模型权重不包含在仓库中，使用时需遵守各模型的许可。
