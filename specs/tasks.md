# EchoMind 开源开发任务拆解清单 (Implementation Tasks - v0.1 MVP & v0.2 二次开发微内核底座)

> 本文档严格对应 [`specs/spec.md`](./spec.md) 与 [`specs/design.md`](./design.md)。
> - **Phase 1 ~ Phase 6（已完成 `[x]`）**：v0.1 MVP 端到端闭环。
> - **Phase 7 ~ Phase 10（已完成 `[x]`）**：**v0.2 面向二次开发的微内核底座深度打磨**（融合 **[deepseek-ai/dsh-superagent-prototype](https://github.com/deepseek-ai/dsh-superagent-prototype)** 的受限上下文 `Narrow PluginContext`、持久化幂等副作用队列 `EffectsQueue`、注意力预算门控 `HUD Attention Policy` 与 `Cookbook` 编号文档体系）。

---

## 第一部分：v0.1 MVP 基础闭环（已完成）

- [x] **Phase 1：微内核抽象底座与混合存储层构建 (`pyproject.toml`, `event_bus.py`, `database.py`, `vector_store.py`)**
- [x] **Phase 2：纯 CPU 语音与声纹引擎 (`download_models.py`, `speaker_id.py`, `vad_buffer.py`, `transcriber.py`)**
- [x] **Phase 3：极米式认知大脑与类 Mem0 记忆演进 (`segmenter.py`, `extractor.py`, `fact_resolver.py`, `proactive_cron.py`)**
- [x] **Phase 4 ~ 6：多源接入网关、REST API、MCP/Obsidian 连接器与 Web PWA (`ws_stream.py`, `mcp_server.py`, `web_pwa/index.html`)**

---

## 第二部分：v0.2 面向二次开发的微内核底座打磨（已完成）

### Phase 7：五大引擎契约与统一注册表 (`ProviderRegistry`)

- [x] **Task 7.1：扩展五大核心 Provider 抽象契约 (`backend/core/interfaces.py`)**
  - **实现内容**：补全 `@runtime_checkable` 的 `VADProvider`、`ASRProvider`、`SpeakerProvider`、`ExtractorProvider`、`EmbeddingProvider` 与 `IngestAdapter` 协议。
  - **验证方式**：对默认内置实现执行 `isinstance(impl, Protocol)` 类型断言测试全部通过。

- [x] **Task 7.2：实现全局服务注册表与默认引擎自动挂载 (`backend/core/registry.py`)**
  - **实现内容**：实现 `ProviderRegistry` 单例（`registry`），支持五大引擎与 `IngestAdapter` 的注册、按名解析、默认切换与优雅回退，并提供 `list_providers()` 自省方法。
  - **验证方式**：单测验证注册自定义 Provider 后全局解析立即切换。

- [x] **Task 7.3：将接入层、记忆核心与向量检索层重构为通过 `ProviderRegistry` 解耦调用**
  - **实现内容**：重构 `ws_stream.py`、`segmenter.py`、`vector_store.py` 与 `routes_voiceprint.py`，通过 `registry` 获取算力与认知组件。
  - **验证方式**：原有端到端测试 100% 通过，且替换任一 Provider 时无需改动业务层代码。

---

### Phase 8：双向事件总线（前置拦截管线）与受限安全上下文 (`EventBus` & `Narrow PluginContext`)

- [x] **Task 8.1：升级 `EventBus` 支持前置链式拦截管线与异常上报 (`backend/core/event_bus.py`)**
  - **实现内容**：新增 `subscribe_filter(stage, handler, priority)` 与 `apply_filters(stage, data)`；支持 `utterance.before_save`、`episode.before_extract`、`episode.before_save` 三大拦截阶段；返回 `None` 时主动拦截丢弃，抛出异常时自动隔离并上报健康状态。
  - **验证方式**：单测验证前置脱敏改写、返回 `None` 丢弃及异常隔离。

- [x] **Task 8.2：实现插件隔离 KV 存储与持久化副作用表 (`backend/storage/database.py`, `models.py`)**
  - **实现内容**：在 SQLite 中新增 `plugin_kv` 表（按 `plugin_name + key` 隔离存储插件状态）与 `effects` 表（支持 `(kind, effect_key)` 幂等合并、状态流转与指数退避重试记录）。
  - **验证方式**：单测验证不同插件同名 key 互不干扰，以及相同 `(kind, effect_key)` 入队自动幂等覆盖。

- [x] **Task 8.3：升级 `EchoMindPlugin`、受限 `PluginContext` 与自定义路由挂载 (`backend/core/plugin_manager.py`)**
  - **实现内容**：
    - 实现 `ScopedKVStore` 与 `PluginContext`（提供 `ctx.kv`、`ctx.report_health`、`ctx.enqueue_effect`、`ctx.ingest_utterance`；当插件卸载或禁用后自动拒绝写入）。
    - 支持 `@filter_hook`、`on_startup(ctx)`、`on_shutdown()`、`get_router()`（自动挂载至 `/api/v1/ext/{plugin.name}`）以及 `entry_points(group="echomind.plugins")` 发现。
  - **验证方式**：验证插件通过 `ctx.kv` 读写配置、挂载自定义 API 路由以及禁用后写入自动失效。

---

### Phase 9：认知提炼模板化、自治 `Passes` 运行时与注意力预算门控 (`RuntimeManager`)

- [x] **Task 9.1：实现认知提炼自定义指令注入与 `custom_metadata` 扩展落库 (`schemas.py`, `extractor.py`, `segmenter.py`)**
  - **实现内容**：在 `EpisodeCognitiveResult` 中新增 `custom_metadata` 字段并自动合并写入 `Episode.metadata_json`；支持通过配置或 API 注入垂直行业提取规则；在 `ws_stream.py` 中支持 `HUD_ATTENTION_POLICY`（`verbose` / `action_only` / `silent_record`）。
  - **验证方式**：验证自定义行业字段自动落库至 `Episode.metadata_json`，以及 `action_only` 模式下平时说话不打扰 HUD、仅生成待办卡片时推送 HUD。

- [x] **Task 9.2：实现 `RuntimeManager`（后台 `Passes` 循环 + `Effects` 指数退避执行器 + `HealthBoard`）并集成至 `main.py`**
  - **实现内容**：
    - 实现 `RuntimeManager` (`backend/core/runtime.py`)：统一执行 `run_pass()`（消费到期 `Effects` 并处理指数退避重试、巡检静默超时闭合 Episode、扫描 `audio_inbox`、检查早晚安 Memo）。
    - 新增 `GET /api/v1/system/kernel` 与 `POST /api/v1/system/pass` 接口，优先展示 `needs_attention`（故障插件或失败 Effects），方便运维与调试。
  - **验证方式**：单测模拟 Effect 失败自动退避重试、连续失败进入 `needs_attention` 列表，以及 `run_pass()` 自动完成收件箱与超时切片处理。

---

### Phase 10：二次开发样板插件、Cookbook 文档与全量测试套件

- [x] **Task 10.1：编写全方位二次开发样板插件 (`plugins/example_custom_dev_template.py`)**
  - **实现内容**：展示前置手机号脱敏与词库纠错（`@filter_hook("utterance.before_save")`）、行业扩展字段注入（`@filter_hook("episode.before_save")`）、使用 `ctx.kv` 与 `ctx.enqueue_effect`、以及挂载自定义路由 `/api/v1/ext/dev_template/*`。
  - **验证方式**：请求 `/api/v1/ext/dev_template/info` 并测试脱敏与扩展字段写入。

- [x] **Task 10.2：编写编号式 Cookbook 二次开发指南 (`docs/plugin-sdk.md`)**
  - **实现内容**：采用 `dsh-superagent` 循序渐进的编号文档风格（000 核心哲学与注意力预算 -> 001 插件与受限上下文 -> 002 前置拦截与行业定制 -> 003 替换五大算力 Provider -> 004 接入新穿戴硬件与自定义路由），并更新 `README.md` 与 `docs/development.md` 导航链接。
  - **验证方式**：检查所有代码示例与实际接口完全一致。

- [x] **Task 10.3：编写微内核底座专项单元测试 (`tests/test_microkernel_sdk.py`)**
  - **实现内容**：全面覆盖 `ProviderRegistry`、`@filter_hook` 改写与拦截、`Narrow PluginContext` 与 `ScopedKVStore`、`Effects` 幂等合并与指数退避重试、`HealthBoard` 故障隔离、注意力门控 HUD 以及自定义路由挂载。
  - **验证方式**：运行 `python3 -m unittest discover -s tests -v`，9 个测试套件 100% 通过。
