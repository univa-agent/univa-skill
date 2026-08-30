# UniVA 模型参数配置分析报告

> 分析日期: 2026-07-17 | 项目: UniVA | 分支: HEAD (commit 1245e21)

---

## 一、架构概览

UniVA 系统存在 **两条独立的模型调用链路**，分别服务于不同的目的：

| 层级 | 用途 | 框架 | 配置来源 |
|------|------|------|----------|
| **Layer A — 核心 Agent 模型** | PlanAgent（规划）和 ActAgent（执行）的"大脑" | `agno` 框架 | `.env` → `config.py` |
| **Layer B — MCP Tool 内部 LLM 调用** | 各 MCP 工具内的辅助 LLM 调用（prompt 优化、视频理解等） | 原生 `requests` HTTP 调用 | `config.yaml` → `query_llm.py` |

此外还有 **Layer C — WaveSpeed 生成 API**（图片/视频/音频生成），配置在 `config.yaml` 中。

---

## 二、配置源头汇总

### 2.1 环境变量文件：`.env`

**路径**: `/home/u2023311g18/univa/.env`

**模板**: `/home/u2023311g18/univa/.env.example`

当前 `.env` 中配置的模型参数：

```bash
# Plan Agent
PLAN_MODEL_PROVIDER=deepseek
PLAN_MODEL_ID=deepseek-reasoner
PLAN_MODEL_API_KEY=REMOVED
PLAN_MODEL_BASE_URL=https://api.deepseek.com
PLAN_MODEL_EXTRA_PARAMS={}

# Act Agent
ACT_MODEL_PROVIDER=deepseek
ACT_MODEL_ID=deepseek-reasoner
ACT_MODEL_API_KEY=REMOVED
ACT_MODEL_BASE_URL=https://api.deepseek.com
ACT_MODEL_EXTRA_PARAMS={}

# MCP Tools 共享 LLM
LLM_OPENAI_API_KEY=REMOVED

# WaveSpeed 生成 API
WAVESPEED_API_KEYREMOVED
```

### 2.2 代码默认值：`config.py`

**路径**: `/home/u2023311g18/univa/univa/config/config.py`

`get_default_config()` 函数（第 7–47 行）定义了硬编码默认值：

| 配置键 | 默认值 | 行号 |
|--------|--------|------|
| `plan_model_provider` | `"openai"` | L28 |
| `plan_model_id` | `"gpt-5"` | L29 |
| `plan_model_api_key` | `""` | L30 |
| `plan_model_base_url` | `""` | L31 |
| `plan_model_extra_params` | `""` | L32 |
| `act_model_provider` | `"openai"` | L35 |
| `act_model_id` | `"gpt-5"` | L36 |
| `act_model_api_key` | `""` | L37 |
| `act_model_base_url` | `""` | L38 |
| `act_model_extra_params` | `""` | L39 |

**Provider → 默认 base_url 映射**（第 159–167 行）：

| Provider | 默认 Base URL |
|----------|--------------|
| `openai` | `https://cc2.caaa.tech/v1` |
| `deepseek` | `https://api.deepseek.com` |
| `dashscope` | `https://dashscope.aliyuncs.com/compatible-mode/v1` |

### 2.3 YAML 配置文件：`config.yaml`

**路径**: `/home/u2023311g18/univa/univa/config/mcp_tools_config/config.yaml`

当前 `llm` 段配置：

```yaml
llm:
  model: "qwen-vl-max"
  openai_api_key: "REMOVED"
  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
```

### 2.4 MCP 服务器注册配置：`mcp_configs.json`

**路径**: `/home/u2023311g18/univa/univa/config/mcp_configs.json`

定义了 6 个 MCP 服务器及其 Python 模块路径，每个工具作为独立子进程运行。

---

## 三、完整调用链路分析

### 3.1 Layer A：核心 Agent 模型调用链

```
用户请求 (HTTP POST /chat/stream)
  │
  ▼
[1] univa_server.py:235  chat()
  │   创建 StreamingResponse，调用 stream_chat_response()
  │
  ▼
[2] univa_server.py:190  stream_chat_response()
  │   调用 system.execute_task_stream(session_id, user_prompt, ...)
  │
  ▼
[3] univa_agent.py:841  PlanActSystem.execute_task_stream()
  │   ├── 判断 chat vs work 请求 (L900 is_chat_request)
  │   ├── chat 请求：直接调用 plan_agent.agent.arun() (L906)
  │   └── work 请求：
  │       ├── plan_agent.generate_plan() (L930) → 调用 PlanAgent
  │       └── act_agent._execute_step() (L1000) → 调用 ActAgent
  │
  ▼
[4] PlanAgent.__init__() (univa_agent.py:255)
  │   读取 config:
  │     config.get('plan_model_provider', 'openai')           L269
  │     config.get('plan_model_id', 'gpt-5-2025-08-07')      L270
  │     config.get('plan_model_api_key', '')                 L271
  │     config.get('plan_model_base_url', '')                L272
  │     config.get('plan_model_extra_params', '')            L273
  │   调用 create_model() 创建 agno Model 对象              L277-283
  │   传入 Agent(model=...)                                  L275-291
  │
  ▼
[5] ActAgent.__init__() (univa_agent.py:433)
  │   读取 config:
  │     config.get('act_model_provider', 'openai')           L459
  │     config.get('act_model_id', 'gpt-5-2025-08-07')      L460
  │     config.get('act_model_api_key', '')                 L461
  │     config.get('act_model_base_url', '')                L462
  │     config.get('act_model_extra_params', '')            L463
  │   调用 create_model() 创建 agno Model 对象              L467-473
  │   传入 Agent(model=..., tools=[mcp_tools])              L465-477
  │
  ▼
[6] model_factory.py:18  create_model()
  │   根据 provider 字符串分发到具体的 agno Model 类:
  │   ├── "openai" / "openai_compatible" / "vllm" / "sglang" / "ollama"
  │   │     → agno.models.openai.OpenAIChat        L39-51
  │   ├── "deepseek" → agno.models.deepseek.DeepSeek  L82-90
  │   ├── "anthropic" → agno.models.anthropic.Claude   L63-70
  │   ├── "dashscope" → agno.models.dashscope.DashScope L72-80
  │   ├── "groq" → agno.models.groq.Groq               L53-61
  │   ├── "gemini" / "google" → agno.models.google.gemini.Gemini L92-99
  │   ├── "azure_openai" / "azure" → AzureOpenAIChat    L101-124
  │   └── fallback → OpenAIChat                         L127-139
  │
  ▼
[7] agno 框架内部
  │   Agent.arun() → Model.ainvoke() → HTTP 请求到 LLM API
  │   使用 base_url + api_key + model_id
  │
  ▼
LLM API (DeepSeek / OpenAI / DashScope / ...)
```

**关键文件调用顺序**:
1. `.env` → `config.py:load_config()` → 解析环境变量覆盖默认值
2. `univa_server.py:120` → `initialize_global_agents()` → 加载 `mcp_configs.json`
3. `univa_agent.py:767` → `PlanActSystem.__init__()` → 创建 `MultiMCPTools`
4. `univa_agent.py:802` → `PlanAgent.__init__()` → 调用 `create_model()`
5. `univa_agent.py:803` → `ActAgent.__init__()` → 调用 `create_model()`
6. `model_factory.py:18` → `create_model()` → 返回 agno Model 实例
7. `PlanAgent.generate_plan()` / `ActAgent._execute_step()` → `agent.arun()` → 实际 API 调用

---

### 3.2 Layer B：MCP Tool 内部 LLM 调用链

```
MCP Tool 执行 (例如 vision2text_gen)
  │
  ▼
[1] 各 MCP Tool 模块加载时 (video_understanding.py:21-23)
  │   读取 config/mcp_tools_config/config.yaml
  │   config = yaml.safe_load(f)
  │
  ▼
[2] query_llm.py:15-21  模块级加载
  │   读取同一个 config.yaml 的 llm 段
  │   llm_config = config.get('llm', {})
  │   包含: model, openai_api_key, base_url
  │
  ▼
[3] 具体工具函数调用 query_llm 中的函数:
  │
  ├── refine_gen_prompt()  (query_llm.py:490)
  │     → query_openai(
  │         api_key=llm_config.get('openai_api_key'),        L503
  │         model=llm_config.get('model', 'gpt-5'),          L504
  │         base_url=llm_config.get('base_url', '...'),      L505
  │         messages=..., max_completion_tokens=8192)
  │
  ├── audio_prompt_gen()  (query_llm.py:516)
  │     → query_openai(api_key=llm_config.get('openai_api_key'), ...)
  │
  ├── speech_prompt_gen()  (query_llm.py:536)
  │     → query_openai(api_key=llm_config.get('openai_api_key'), ...)
  │
  └── multimodal_query()  (query_llm.py:557)
        → query_openai(api_key=llm_config.get('openai_api_key'), ...)
  │
  ▼
[4] query_openai()  (query_llm.py:438)
  │   url = f"{base_url}/chat/completions"                   L446
  │   headers = {"Authorization": f"Bearer {api_key}"}      L449-451
  │   payload = {"model": model, "messages": messages, ...}  L453-458
  │   → requests.post(url, ...) → _post_json_with_retry()   L461
  │
  ▼
LLM API (当前: DashScope qwen-vl-max)
```

**关键文件调用顺序**:
1. MCP Tool 模块加载 → 读取 `config.yaml`
2. `query_llm.py` 模块加载 → 读取 `config.yaml` 的 `llm` 段
3. MCP Tool 函数 → 调用 `query_llm` 中的辅助函数
4. `query_llm.py:438` → `query_openai()` → HTTP POST 到 OpenAI 兼容 API

**注意**：`query_llm.py` 还提供了 `query_openrouter()`、`query_gemini()`、`query_claude()` 等函数，但当前未被 MCP tools 使用。

---

### 3.3 Layer C：WaveSpeed 生成 API 调用链

```
MCP Tool (例如 text2video_gen)
  │
  ▼
[1] video_gen.py:17-19  模块加载时
  │   读取 config.yaml
  │   video_gen_config = config.get('video_gen', {})
  │
  ▼
[2] text2video_gen()  (video_gen.py:31)
  │   api_key = video_gen_config.get("wavespeed_api")        L51
  │   model = video_gen_config.get("text_to_video")          L48
  │
  ▼
[3] wavespeed_api.py:193  text_to_video_generate()
  │   url = f"https://api.wavespeed.ai/api/v3/{provider}/{model}"  L194
  │   headers = {"Authorization": f"Bearer {api_key}"}       L196-198
  │   → requests.post(url, ...) → 轮询结果
  │
  ▼
WaveSpeed API (https://api.wavespeed.ai)
```

---

## 四、涉及文件完整清单

### 配置文件

| 文件 | 作用 | 配置内容 |
|------|------|----------|
| `.env` | **主配置文件**（最高优先级） | Plan/Act Agent 的 provider、model_id、api_key、base_url；MCP LLM 的 api_key；WaveSpeed api_key |
| `.env.example` | 配置模板 | 同上结构，含多供应商示例 |
| `univa/config/config.py` | 代码默认值 + 环境变量加载逻辑 | 默认 provider/model，provider→base_url 映射 |
| `univa/config/mcp_tools_config/config.yaml` | MCP 工具内部 LLM 配置 + 生成 API 配置 | llm 段（model, api_key, base_url）；各工具段（wavespeed_api, 模型选择） |
| `univa/config/mcp_configs.json` | MCP 服务器注册 | 各工具子进程的启动命令和 Python 模块路径 |

### 核心代码文件

| 文件 | 作用 | 关键行号 |
|------|------|----------|
| `univa/univa_server.py` | FastAPI 服务器入口，SSE 流式响应 | L190-232 流式处理；L120-156 初始化 |
| `univa/univa_agent.py` | PlanAgent + ActAgent + PlanActSystem 定义 | L255-291 PlanAgent 模型配置；L433-477 ActAgent 模型配置；L767-810 PlanActSystem 初始化 |
| `univa/utils/model_factory.py` | Provider → agno Model 类映射工厂 | L18-139 create_model() |
| `univa/utils/query_llm.py` | MCP 工具内部 LLM 调用（原生 HTTP） | L15-21 配置加载；L438-486 query_openai()；L490-513 refine_gen_prompt() |
| `univa/utils/pipeline_orchestrator.py` | 多阶段流水线编排 | L96-105 使用 plan_agent.agent.model.id |
| `univa/utils/skill_loader.py` | Skill 文件加载（不直接涉及模型配置） | - |

### MCP Tool 文件（均读取 config.yaml）

| 文件 | 注册的 MCP 工具 | 依赖的模型/API |
|------|----------------|---------------|
| `univa/mcp_tools/video_gen.py` | text2video_gen, storyvideo_gen, entity2video, image2video_gen, video_extension, frame2frame_video_gen, merge2videos | WaveSpeed API + query_llm (prompt refine) |
| `univa/mcp_tools/image_gen.py` | text2image_generate, image2image_generate, sequential_image_gen | WaveSpeed API |
| `univa/mcp_tools/video_editing.py` | depth_modify, pose_reference, style_transfer, repainting | WaveSpeed API / VACE 本地模型 |
| `univa/mcp_tools/video_understanding.py` | vision2text_gen | query_llm.multimodal_query() |
| `univa/mcp_tools/video_tracking.py` | video_referring_segmentation | 本地模型 (Sa2VA, SAM) |
| `univa/mcp_tools/audio_gen.py` | audio_gen, speech_gen | WaveSpeed API |
| `univa/mcp_tools/base.py` | ToolResponse, setup_logger | 无模型依赖 |

### API 封装文件

| 文件 | 作用 |
|------|------|
| `univa/utils/wavespeed_api.py` | WaveSpeed 生成 API 封装（text_to_image, image_to_video, audio_gen 等） |

---

## 五、整体逻辑阐述

### 5.1 配置加载优先级

```
.env 环境变量  >  config.yaml  >  config.py 默认值
```

1. `config.py:load_config()` 首先读取 TOML 配置（或创建默认值）
2. 然后解析 `.env` 文件，用环境变量覆盖 TOML 中的对应字段
3. 如果 `base_url` 为空，根据 `provider` 自动推断默认 URL
4. `config.yaml` 独立加载（不被 `.env` 中的 Plan/Act 配置影响），但 `WAVESPEED_API_KEY` 和 `LLM_OPENAI_API_KEY` 环境变量会覆盖它

### 5.2 模型参数流向

```
                    ┌──────────────────────────────────────┐
                    │           .env 文件                    │
                    │  PLAN_MODEL_PROVIDER=deepseek         │
                    │  PLAN_MODEL_ID=deepseek-reasoner      │
                    │  PLAN_MODEL_API_KEY=sk-...            │
                    │  PLAN_MODEL_BASE_URL=...              │
                    │  ACT_MODEL_PROVIDER=deepseek          │
                    │  ACT_MODEL_ID=deepseek-reasoner       │
                    │  ACT_MODEL_API_KEY=sk-...             │
                    │  ACT_MODEL_BASE_URL=...               │
                    │  LLM_OPENAI_API_KEY=sk-...            │
                    │  WAVESPEED_API_KEY=wsk_...            │
                    └──────┬───────────────┬───────────────┘
                           │               │
              ┌────────────▼──────┐  ┌─────▼──────────────┐
              │   config.py       │  │  config.yaml         │
              │   load_config()   │  │  (mcp_tools_config)  │
              │   解析 .env 覆盖   │  │                       │
              └────────┬──────────┘  └─────┬───────────────┘
                       │                    │
          ┌────────────▼──────────┐  ┌──────▼──────────────┐
          │  univa_agent.py       │  │  query_llm.py        │
          │  PlanAgent / ActAgent │  │  模块级加载 llm 段    │
          │  config.get(...)      │  │  llm_config = {...}   │
          └────────────┬──────────┘  └──────┬──────────────┘
                       │                    │
          ┌────────────▼──────────┐  ┌──────▼──────────────┐
          │  model_factory.py     │  │  query_openai()      │
          │  create_model()       │  │  HTTP POST 到        │
          │  返回 agno Model      │  │  OpenAI 兼容 API     │
          └────────────┬──────────┘  └──────────────────────┘
                       │
          ┌────────────▼──────────┐
          │  agno Agent           │
          │  agent.arun()         │
          │  → Model.ainvoke()    │
          │  → HTTP API 调用      │
          └───────────────────────┘
```

### 5.3 两条链路的关键区别

| 维度 | Layer A (Agent 模型) | Layer B (MCP 内部 LLM) |
|------|---------------------|------------------------|
| 配置键前缀 | `PLAN_MODEL_*` / `ACT_MODEL_*` | `llm.*` (在 config.yaml) |
| 配置位置 | `.env` → `config.py` | `config/mcp_tools_config/config.yaml` |
| 模型框架 | agno (OpenAIChat, DeepSeek, Claude 等) | 原生 requests + OpenAI 兼容 API |
| 灵活性 | 支持多种 provider，自动路由 | 仅 OpenAI 兼容格式 (query_openai) |
| Plan/Act 独立配置 | 是（各自独立 provider/model/key） | 否（共享一个 llm 配置） |

---

## 六、切换模型供应商操作指南

### 6.1 切换 Layer A — 核心 Agent 模型

**适用场景**：将 PlanAgent 或 ActAgent 从当前 DeepSeek 切换到 OpenAI、DashScope、Claude 等。

#### 修改文件：`.env`

编辑 `/home/u2023311g18/univa/.env`，修改 Plan/Act Agent 的环境变量：

##### 切换到 OpenAI
```bash
PLAN_MODEL_PROVIDER=openai
PLAN_MODEL_ID=gpt-5
PLAN_MODEL_API_KEY=sk-your-openai-key
PLAN_MODEL_BASE_URL=https://api.openai.com/v1
PLAN_MODEL_EXTRA_PARAMS={}

ACT_MODEL_PROVIDER=openai
ACT_MODEL_ID=gpt-5
ACT_MODEL_API_KEY=sk-your-openai-key
ACT_MODEL_BASE_URL=https://api.openai.com/v1
ACT_MODEL_EXTRA_PARAMS={}
```

##### 切换到 DashScope (阿里云通义千问)
```bash
PLAN_MODEL_PROVIDER=dashscope
PLAN_MODEL_ID=qwen-plus-latest
PLAN_MODEL_API_KEY=sk-your-dashscope-key
PLAN_MODEL_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
PLAN_MODEL_EXTRA_PARAMS={}
```

##### 切换到 Anthropic Claude
```bash
PLAN_MODEL_PROVIDER=anthropic
PLAN_MODEL_ID=claude-sonnet-4-20250514
PLAN_MODEL_API_KEY=sk-ant-your-key
PLAN_MODEL_BASE_URL=https://api.anthropic.com
PLAN_MODEL_EXTRA_PARAMS={}
```

##### 切换到本地 vLLM/Ollama
```bash
PLAN_MODEL_PROVIDER=openai
PLAN_MODEL_ID=Qwen/Qwen2.5-7B-Instruct
PLAN_MODEL_API_KEY=dummy
PLAN_MODEL_BASE_URL=http://localhost:8000/v1
PLAN_MODEL_EXTRA_PARAMS={}
```

##### Plan 和 Act 使用不同供应商
只需分别设置 `PLAN_MODEL_*` 和 `ACT_MODEL_*` 即可，例如：
```bash
# Plan 用 Claude（擅长规划）
PLAN_MODEL_PROVIDER=anthropic
PLAN_MODEL_ID=claude-sonnet-4-20250514
PLAN_MODEL_API_KEY=sk-ant-...

# Act 用 GPT-5（擅长工具调用）
ACT_MODEL_PROVIDER=openai
ACT_MODEL_ID=gpt-5
ACT_MODEL_API_KEY=sk-...
ACT_MODEL_BASE_URL=https://api.openai.com/v1
```

#### 无需修改的文件

- `config.py` — 如果 `.env` 中设置了值，则不需要修改。仅当需要修改默认 provider 的 base_url 映射时才需要修改 `get_default_base_url()` 函数（L159-167）。
- `model_factory.py` — 仅当需要添加新的 provider 类型时才需要添加新的分支。

---

### 6.2 切换 Layer B — MCP Tool 内部 LLM

**适用场景**：将 MCP 工具内部使用的 LLM（prompt 优化、视频理解等）从当前 DashScope (qwen-vl-max) 切换到其他供应商。

#### 修改文件：`univa/config/mcp_tools_config/config.yaml`

编辑 `/home/u2023311g18/univa/univa/config/mcp_tools_config/config.yaml`，修改 `llm` 段：

##### 切换到 OpenAI
```yaml
llm:
  model: "gpt-4o"
  openai_api_key: "sk-your-openai-key"
  base_url: "https://api.openai.com/v1"
```

##### 切换到 DeepSeek
```yaml
llm:
  model: "deepseek-chat"
  openai_api_key: "sk-your-deepseek-key"
  base_url: "https://api.deepseek.com"
```

##### 切换到本地服务
```yaml
llm:
  model: "Qwen2.5-VL-32B-Instruct"
  openai_api_key: "dummy"
  base_url: "http://localhost:8000/v1"
```

#### 也可通过环境变量覆盖

在 `.env` 中设置：
```bash
LLM_OPENAI_API_KEY=sk-your-key
```

这会通过 `config.py:load_mcp_config()` 中的 `set_config("llm", "openai_api_key", ...)` 覆盖 YAML 中的值（config.py L79）。

---

### 6.3 切换 Layer C — WaveSpeed 生成 API

#### 修改文件：`univa/config/mcp_tools_config/config.yaml`

每个工具段的 `wavespeed_api` 字段：
```yaml
image_gen:
  wavespeed_api: "your-new-api-key"

video_gen:
  wavespeed_api: "your-new-api-key"

video_editing:
  wavespeed_api: "your-new-api-key"

audio_gen:
  wavespeed_api: "your-new-api-key"
```

#### 或通过环境变量全局覆盖

在 `.env` 中设置：
```bash
WAVESPEED_API_KEY=your-new-key
```

这会覆盖所有工具段中的 `wavespeed_api`（config.py L72-77）。

---

### 6.4 添加新 Provider 类型

如果 `model_factory.py` 中不支持你需要的 provider，需要：

1. **编辑** `univa/utils/model_factory.py`，在 `create_model()` 函数中添加新的 `if` 分支。
2. **编辑** `univa/config/config.py`，在 `get_default_base_url()` 函数（L159-167）中添加新 provider 的默认 base_url。
3. 在 `.env` 中设置对应的 `PLAN_MODEL_PROVIDER` / `ACT_MODEL_PROVIDER`。

---

### 6.5 切换检查清单

| 检查项 | 文件 | 具体操作 |
|--------|------|----------|
| ☐ Plan Agent 模型 | `.env` | 修改 `PLAN_MODEL_PROVIDER`, `PLAN_MODEL_ID`, `PLAN_MODEL_API_KEY`, `PLAN_MODEL_BASE_URL` |
| ☐ Act Agent 模型 | `.env` | 修改 `ACT_MODEL_PROVIDER`, `ACT_MODEL_ID`, `ACT_MODEL_API_KEY`, `ACT_MODEL_BASE_URL` |
| ☐ 额外参数 | `.env` | 如需传递特殊参数，设置 `PLAN_MODEL_EXTRA_PARAMS` / `ACT_MODEL_EXTRA_PARAMS`（JSON 字符串） |
| ☐ MCP 内部 LLM | `config.yaml` | 修改 `llm.model`, `llm.openai_api_key`, `llm.base_url` |
| ☐ WaveSpeed API | `config.yaml` 或 `.env` | 修改各段 `wavespeed_api` 或设置 `WAVESPEED_API_KEY` |
| ☐ 本地模型路径 | `.env` 或 `config.yaml` | 如需修改 `VIDEO_EDIT_MODEL_PATH` 等 |
| ☐ 代理设置 | `.env` | 如需要，设置 `PROXY_HOST` / `PROXY_PORT` |

### 6.6 验证方法

1. 修改配置后重启 UniVA 服务
2. 检查启动日志中 `Plan Agent: loaded instructions from skill files` 和 `Act Agent: loaded instructions from skill files`
3. 发送一个简单测试请求验证模型响应
4. 检查日志中 MCP 工具调用的 API 请求 URL 是否正确

---

## 七、附录：Provider 支持矩阵

| Provider | model_factory 中的类 | base_url | api_key 认证方式 | 备注 |
|----------|---------------------|----------|-----------------|------|
| `openai` | OpenAIChat | `https://cc2.caaa.tech/v1` (默认) | Bearer Token | 兼容所有 OpenAI 格式 API |
| `deepseek` | DeepSeek | `https://api.deepseek.com` | Bearer Token | - |
| `anthropic` | Claude | `https://api.anthropic.com` | x-api-key | 不支持 base_url 参数 |
| `dashscope` | DashScope | `https://dashscope.aliyuncs.com/compatible-mode/v1` | Bearer Token | - |
| `groq` | Groq | (无默认) | Bearer Token | - |
| `gemini` / `google` | Gemini | (无默认) | API Key | - |
| `azure` / `azure_openai` | AzureOpenAIChat | (无默认) | API Key | - |
| `vllm` / `sglang` / `ollama` | OpenAIChat | (无默认) | Bearer Token | 本地部署 |
