# 模型可用性审核

| 项目 | 内容 |
|---|---|
| 审核日期 | 2026-11-12 |
| 对应实现 | `backend/app/services/model_provider.py`、`embeddings.py`、`agent_tools.py` |
| 审核口径 | 不只看 HTTP 能否连通，还看模型 ID 是否存在、是否支持当前协议、是否支持工具调用、Embedding 维度/批量是否符合代码，以及是否已被官方标记弃用 |
| 结论边界 | 未使用用户真实 API Key 批量调用外部服务；账号权限、地域和实际计费额度仍需以控制台为准 |

## 1. 代码对模型的实际要求

本项目的模型调用分三条路径：

1. **Embedding**：`POST /embeddings`，要求返回数量与输入一致、每条形如 `data[].embedding`；用于切片入库和检索。
2. **回答生成**：`POST /chat/completions`，要求返回 `choices[0].message.content`。
3. **Agent 工具调用**：同样调用 `/chat/completions`，但带 `tools` 和 `tool_choice=auto`，要求返回标准 OpenAI 工具调用格式。

因此一个模型“能连上”不等于“能用”：

- Embedding 模型必须支持批量输入，且批量不能超过服务商上限。
- 回答模型必须能返回非空 `content`；推理模型还要避免被 `temperature`、`max_tokens` 参数拒绝。
- 不支持工具调用的模型仍可回答（`agent_tools.py` 会回退到计划检索），但会缺少 Agent 主动补充检索能力。
- 向量维度最好落在 768/1024/1536/3072，才能命中 HNSW；其他维度可用，但会退化为精确扫描。

## 2. 逐模型审核

### OpenAI

| 模型 | 角色 | 工具调用 | 实际可用性 | 说明 |
|---|---|---|---|---|
| `gpt-4.1-mini` | 回答 | 支持 | ✅ 推荐默认 | Chat Completions、tools、temperature 均兼容 |
| `gpt-4.1` | 回答 | 支持 | ✅ 可用 | 同上，成本高于 mini |
| `gpt-4o-mini` | 回答 | 支持 | ✅ 可用 | 稳定旧型号 |
| `gpt-5.1` | 回答 | 支持 | ⚠️ 条件可用 | 推理模型；代码已自动省略 `temperature`，改用 `max_completion_tokens`；是否可用取决于账号 |
| `gpt-5` | 回答 | 支持 | ⚠️ 已弃用 | OpenAI 模型页标记 Deprecated；保留兼容，不建议新配置 |
| `gpt-5-mini` | 回答 | 支持 | ⚠️ 条件可用 | 同 GPT-5 系列参数限制 |
| `text-embedding-3-small` | 检索 | — | ✅ 可用 | 默认 1536 维，命中 HNSW |
| `text-embedding-3-large` | 检索 | — | ✅ 可用 | 默认 3072 维，使用 halfvec HNSW |

OpenAI 的 GPT-5 系列会拒绝 `temperature`，且部分推理模型不接受旧 `max_tokens`。代码已按模型前缀自动切换为 `max_completion_tokens` 并省略温度参数；普通 GPT-4.x 仍发送 temperature。

### 阿里云百炼（DashScope）

| 模型 | 角色 | 工具调用 | 实际可用性 | 说明 |
|---|---|---|---|---|
| `text-embedding-v4` | 检索 | — | ✅ 已修复 | 默认 1024 维；**单次最多 10 条文本**，代码已按服务商上限分批 |
| `text-embedding-v3` | 检索 | — | ✅ 可用 | 默认 1024 维；批量上限按 v3 保守值 10 处理 |
| `qwen-max` | 回答 | 支持 | ✅ 推荐默认 | 稳定型号，兼容 Chat Completions |
| `qwen-plus` | 回答 | 支持 | ✅ 可用 | 成本更低 |
| `qwen-flash` | 回答 | 支持 | ✅ 可用 | 更快、更便宜 |
| `qwen3.8-max` | 回答 | 支持 | ✅ 条件可用 | 官方支持 Function Calling；代码设置 `reasoning_effort=none`，避免思维链耗尽短回答预算 |
| `qwen3.7-max` | 回答 | 支持 | ✅ 条件可用 | 同上 |
| `qwen3.7-plus` | 回答 | 支持 | ✅ 条件可用 | 同上 |
| `qwen3.8-flash` | 回答 | 支持 | ✅ 条件可用 | 同上 |
| `qwen3-coder-plus` | 回答 | 支持 | ⚠️ 可用 | 偏代码，通用问答可用但未关闭思考参数 |

本次实际发现并修复的问题：数据库中一份 PDF 的失败原因是：

```text
阿里云百炼（DashScope） 返回错误：
InternalError.Algo.InvalidParameter: Value error, batch size is invalid,
it should not be larger than 10.: input.contents
```

原代码全局批量默认为 16，超过百炼 `text-embedding-v4` 的 10 条限制。现在 `embeddings.py` 会取“全局批大小”和“服务商上限”的较小值，百炼固定不超过 10。

### 硅基流动（SiliconFlow）

| 模型 | 角色 | 工具调用 | 实际可用性 | 说明 |
|---|---|---|---|---|
| `BAAI/bge-m3` | 检索 | — | ✅ 可用 | 1024 维，命中 HNSW；单条上限 8192 token，批量按 16 保守处理 |
| ~~`BAAI/bge-large-zh-v1.5`~~ | 检索 | — | ❌ 已移除 | 单条输入上限仅 512 token，低于本项目 600–800 token 切片，长片段会失败 |
| `deepseek-ai/DeepSeek-V4.1-Flash` | 回答 | 支持 | ⚠️ 条件可用 | 当前平台主推；默认可能思考，短回答更慢，账号和模型上下线以平台为准 |
| `deepseek-ai/DeepSeek-V4-Pro` | 回答 | 支持 | ⚠️ 条件可用 | 同上，成本更高 |
| `Qwen/Qwen3-235B-A22B-Instruct-2507` | 回答 | 支持 | ⚠️ 条件可用 | 代码关闭 `enable_thinking`；该系列模型可能被平台标记弃用，以账号模型广场为准 |
| `Qwen/Qwen3-32B` | 回答 | 支持 | ✅ 条件可用 | 代码关闭 `enable_thinking` |
| `Qwen/Qwen3-8B` | 回答 | 支持 | ✅ 条件可用 | 代码关闭 `enable_thinking`，适合低成本 |

硅基流动文档说明：函数调用通过 `tools` 支持，但部分 DeepSeek 旧型号要求 `enable_thinking=false`。当前 V4 型号是否默认思考由平台决定；如果回答为空或工具调用异常，优先换 Qwen3 或 DeepSeek 非思考型号。

### DeepSeek

| 模型 | 角色 | 工具调用 | 实际可用性 | 说明 |
|---|---|---|---|---|
| `deepseek-flash` | 回答 | 支持 | ✅ 推荐默认 | 官方当前主推；支持 Tool Calls；代码关闭思考模式 |
| `deepseek-v4-pro` | 回答 | 支持 | ✅ 可用 | 官方当前旗舰；支持 Tool Calls；代码关闭思考模式 |
| `deepseek-chat` | 回答 | 支持 | ❌ 已移除 | 官方当前 Models & Pricing 不再列出；旧页面标注将弃用 |
| `deepseek-reasoner` | 回答 | 不支持/有限 | ❌ 已移除 | 旧推理型号，工具调用兼容性不稳定 |

DeepSeek 不提供 Embedding，因此不能把它作为检索模型；前端选择“检索模型”时也会被后端拒绝。

### 智谱 AI

| 模型 | 角色 | 工具调用 | 实际可用性 | 说明 |
|---|---|---|---|---|
| `embedding-3` | 检索 | — | ✅ 已适配 | 默认 2048 维；代码显式请求 1024 维，命中 HNSW；批量上限 64 |
| `glm-5.1` | 回答 | 支持 | ✅ 推荐默认 | 2026 旗舰，支持工具调用与 temperature |
| `glm-5` | 回答 | 支持 | ✅ 可用 | 上一代旗舰 |
| `glm-5-turbo` | 回答 | 支持 | ✅ 可用 | 更低延迟 |
| `glm-4.6` | 回答 | 支持 | ⚠️ 旧型号 | 可用性以账号为准 |
| `glm-4.5` | 回答 | 支持 | ⚠️ 旧型号 | 可用性以账号为准 |
| `glm-4-flash` | 回答 | 支持 | ⚠️ 旧型号 | 成本低，能力较弱 |

### 本地 Ollama

| 模型 | 角色 | 工具调用 | 实际可用性 | 说明 |
|---|---|---|---|---|
| `bge-m3` | 检索 | — | ✅ 需本地安装 | 1024 维；批量固定 1，避免兼容性问题 |
| `qwen3-embedding:0.6b` | 检索 | — | ✅ 本地已安装 | 1024 维，轻量检索模型 |
| `nomic-embed-text` | 检索 | — | ✅ 需本地安装 | 768 维；批量固定 1 |
| `qwen3:4b` | 回答 | 支持 | ✅ 推荐本地默认 | 4B 轻量，显存有限时首选 |
| `qwen3:8b` | 回答 | 支持 | ✅ 需本地安装 | 效果更好，需要先 `ollama pull qwen3:8b` |
| `qwen3:14b` | 回答 | 支持 | ✅ 需足够内存 | 需要本地拉取 |
| `qwen3:32b` | 回答 | 支持 | ⚠️ 需较大显存/内存 | 需要本地拉取 |
| `deepseek-r1:8b/14b` | 回答 | 不支持 | ⚠️ 仅回答回退 | 可生成回答，但 Agent 工具调用会回退为计划检索 |
| `llama3.3:70b` | 回答 | 有限 | ⚠️ 资源要求高 | 需要大显存；工具能力以模型模板为准 |
| `gemma3:12b` | 回答 | 不支持 | ⚠️ 仅回答回退 | 适合普通生成，不适合 Agent 工具调用 |
| `qwen2.5:7b` | 回答 | 有限 | ⚠️ 旧型号 | 可用性以本地模型模板为准 |

数据库中另一份文件的失败原因是：

```text
无法连接 本地 Ollama，请检查网络后重试
```

这不是模型 ID 错误，而是本机 Ollama 服务未启动或未拉取对应模型。使用本地模型前需要：

```powershell
ollama serve
ollama pull qwen3:8b
ollama pull bge-m3
```

## 3. 本次代码修复

1. **DashScope 批量上限**：`ProviderSpec.max_embedding_batch`，百炼 10、Ollama 1、智谱 64；`embeddings.py` 取最小值分批。
2. **智谱维度**：`embedding-3` 请求显式 `dimensions=1024`，避免默认 2048 维退化为精确扫描。
3. **OpenAI 推理参数**：GPT-5/6/o 系列自动省略 `temperature`，改用 `max_completion_tokens`，避免 400。
4. **DeepSeek 思考模式**：请求时设置 `thinking.type=disabled`，避免短回答预算被思维链消耗，并兼容工具调用。
5. **Qwen 思考模式**：硅基流动 Qwen3 设置 `enable_thinking=false`；百炼 Qwen3.7/3.8 设置 `reasoning_effort=none`。
6. **模型清单**：移除 DeepSeek 旧 `deepseek-chat`/`deepseek-reasoner`；更新硅基流动为当前 V4/Qwen3 型号；OpenAI 默认改为稳定的 `gpt-4.1-mini`。
7. **连接测试升级**：Embedding 测试改为发送 2 条文本，验证返回数量和维度一致性，并提示维度是否命中 HNSW；不再只判断 HTTP 200。

## 4. 仍需在真实账号上确认

- 你的账号是否有 `qwen3.8-max`、`glm-5.1`、`gpt-5.1` 等型号权限。
- 百炼地域与 API Key 是否匹配（北京/新加坡等地域 Key 不通用）。
- 硅基流动 V4 型号的实际上下线状态和计费。
- 本地 Ollama 是否已启动、是否已拉取对应模型、显存是否足够。
- 工具调用能力：不支持的模型会自动回退，但不会具备主动补充检索能力。

## 5. 官方核对来源

- OpenAI Models：https://platform.openai.com/docs/models
- OpenAI GPT-5 模型页：https://developers.openai.com/api/docs/models/gpt-5
- DeepSeek Models & Pricing：https://api-docs.deepseek.com/quick_start/pricing
- DeepSeek Chat Completions：https://api-docs.deepseek.com/api/create-chat-completion
- 百炼文本向量化：https://help.aliyun.com/zh/model-studio/embedding
- 百炼 Function Calling：https://help.aliyun.com/zh/model-studio/qwen-function-calling
- 智谱 Embedding-3：https://docs.bigmodel.cn/cn/guide/models/embedding/embedding-3
- 硅基流动 Chat Completions：https://docs.siliconflow.com/en/api-reference/chat-completions/chat-completions
- Ollama 模型库：https://ollama.com/library
