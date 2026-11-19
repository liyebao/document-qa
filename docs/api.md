# API 契约

| 项目 | 内容 |
|---|---|
| 文档版本 | v2.0 |
| 对应实现 | `backend/app/api/routes/` |
| 基础路径 | `/api` |

## 1. 通用约定

- 本项目为本地单用户模式：首次启动自动创建/复用本机用户，所有请求自动归属该用户，没有注册、登录、令牌或账号接口。
- 写请求如果携带 `Origin`，必须命中后端 `CORS_ORIGINS` 白名单，否则返回 `403 ORIGIN_REJECTED`；命令行客户端通常不发送 `Origin`。
- 请求与响应均为 JSON，字段使用小写下划线（snake_case）。
- 资源归属仍按本地用户校验；请求体或查询参数中的用户标识一律不被信任。
- 错误响应统一格式：

```json
{
  "error": {
    "code": "DUPLICATE_FILE",
    "message": "资料集中已存在内容相同的文件"
  }
}
```

- 列表接口按创建时间倒序返回，MVP 暂不分页。

## 2. 模型服务设置 `/api/settings`

### GET `/api/settings/model-providers`

返回后端支持的服务商白名单和当前用户已保存的配置。配置中只包含掩码 Key，不返回完整 Key。

```json
{
  "providers": [
    {
      "key": "openai",
      "label": "OpenAI",
      "embedding_models": ["text-embedding-3-small"],
      "chat_models": ["gpt-4o-mini"],
      "requires_api_key": true
    }
  ],
  "configs": [
    {
      "id": "<uuid>",
      "provider_key": "openai",
      "embedding_model": "text-embedding-3-small",
      "chat_model": "gpt-4o-mini",
      "status": "configured",
      "key_masked": "sk-****abcd",
      "last_tested_at": null,
      "updated_at": "2026-11-09T12:00:00Z",
      "is_embedding_default": true,
      "is_chat_default": true
    }
  ],
  "preferred_embedding_provider": "openai",
  "preferred_chat_provider": "openai"
}
```

`preferred_embedding_provider` 与 `preferred_chat_provider` 分别表示当前用于检索和回答的服务商，二者可以不同；为空时后端回退到最近更新的可用配置。

### POST `/api/settings/model-providers`

按服务商保存或更新配置；同一用户同一服务商只有一条配置。

```json
{
  "provider_key": "openai",
  "api_key": "sk-...",
  "embedding_model": "text-embedding-3-small",
  "chat_model": "gpt-4o-mini",
  "role": "chat"
}
```

`role` 可选，取值 `embedding`、`chat`、`both` 或不填。填写时保存成功后会把该服务商设为对应角色的当前配置：`embedding` 只设为检索，`chat` 只设为回答，`both` 同时设为两者；不填时保持原有角色选择。

- 首次保存必须提供 `api_key`，否则返回 `API_KEY_REQUIRED`。
- 更新时 `api_key` 可省略，表示保留原 Key。
- `embedding_model` 与 `chat_model` 可选：新建时留空使用该服务商的推荐模型；更新时留空保留原模型；也可以直接填写自定义模型名。
- DeepSeek 当前只提供回答模型，不提供 Embedding；选择 DeepSeek 后需另外配置一个支持 Embedding 的服务商（OpenAI、百炼、智谱或硅基流动）。
- `requires_api_key=false` 的服务商（本地 Ollama）首次保存时可以不填 `api_key`，后端会写入占位值。
- 首次保存时，若用户尚未指定检索/回答服务商，该配置会自动成为对应角色的默认项；之后新增其他服务商不会抢占已有选择。
- 响应 `200`，字段同上面的配置对象。

### POST `/api/settings/model-providers/{id}/role`

显式指定某个配置用于检索或回答。检索与回答可以来自不同服务商。

```json
{ "role": "chat" }
```

`role` 取值 `embedding` 或 `chat`。把没有 Embedding 模型的配置（如 DeepSeek）设为检索配置时返回 `422 MODEL_NOT_CONFIGURED`。

响应 `200`，返回更新后的完整模型设置对象（字段同 `GET /api/settings/model-providers`）。

### POST `/api/settings/model-providers/{id}/test`

分别调用一次 Embedding 和回答模型验证连接，可能消耗服务商额度。请求体可选：

```json
{ "role": "embedding" }
```

指定 `role` 时只测试对应角色；不传则两者都测试。Embedding 测试会发送两条文本并校验返回数量与维度，不只检查 HTTP 状态。

```json
{
  "ok": false,
  "embedding_ok": true,
  "chat_ok": false,
  "message": "Embedding 服务连接正常；回答模型连接失败：..."
}
```

### DELETE `/api/settings/model-providers/{id}`

删除本地加密配置，返回 `204`。不会代替用户在服务商处撤销 Key。

## 3. 资料集 `/api/collections`

### GET `/api/collections`

```json
[
  {
    "id": "<uuid>",
    "name": "毕业设计调研",
    "embedding_provider": "openai",
    "embedding_model": "text-embedding-3-small",
    "embedding_dimension": 1536,
    "index_version": 1,
    "created_at": "2026-11-09T12:00:00Z",
    "document_count": 3
  }
]
```

### POST `/api/collections`

```json
{ "name": "毕业设计调研" }
```

响应 `201`，返回资料集对象（不含 `document_count`）。

### GET `/api/collections/{id}`

返回当前用户的资料集；不存在或不属于当前用户时返回 `404`。

### PATCH `/api/collections/{id}`

```json
{ "name": "新名称" }
```

### DELETE `/api/collections/{id}`

删除资料集及其文件、片段、会话，返回 `204`。

### POST `/api/collections/{id}/reindex`

用当前用户最近保存的 Embedding 配置（或请求中指定的服务商）重算该资料集全部片段向量。切换 Embedding 模型或向量维度后必须调用。

请求：

```json
{ "provider_key": "openai" }
```

`provider_key` 可省略或为 `null`，表示使用最近更新的、支持 Embedding 的服务商配置。

响应 `200`：

```json
{
  "id": "<uuid>",
  "name": "毕业设计调研",
  "embedding_provider": "openai",
  "embedding_model": "text-embedding-3-small",
  "embedding_dimension": 1536,
  "index_version": 2,
  "created_at": "2026-11-09T12:00:00Z",
  "chunk_count": 128
}
```

- 全部向量请求成功后才写库并切换；失败时旧向量和旧元数据保持不变。
- 成功后 `index_version` 递增，避免新旧向量空间混用。
- 该接口同步执行，耗时取决于片段数量和 Embedding 服务；前端超时时间放宽到 10 分钟。
- 资料集没有可重建片段时返回 `409 REINDEX_EMPTY`；同一资料集已有重建任务时返回 `409 REINDEX_IN_PROGRESS`。

### GET `/api/collections/{id}/conversations`

返回资料集下的会话列表。

### POST `/api/collections/{id}/conversations`

```json
{ "title": "可选标题" }
```

响应 `201`，未提供标题时使用“新会话”，首次提问后自动以问题前 30 个字符命名。

## 4. 文件 `/api`

### POST `/api/collections/{id}/documents`

`multipart/form-data`，字段名 `file`。支持 `.pdf`、`.docx`、`.md`、`.markdown`、`.txt`、`.pptx`、`.xlsx`，单份不超过 100 MB。

响应 `202`，文件进入处理队列：

```json
{
  "id": "<uuid>",
  "collection_id": "<uuid>",
  "filename": "report.pdf",
  "format": "pdf",
  "checksum": "<sha256>",
  "version": 1,
  "status": "processing",
  "failure_reason": null,
  "is_enabled": true,
  "is_current": true,
  "created_at": "2026-11-09T12:00:00Z"
}
```

处理状态：`processing` → `ready` 或 `failed`。失败原因通过 `failure_reason` 返回。

### POST `/api/collections/{id}/documents/text`

```json
{ "title": "会议纪要", "content": "粘贴的正文……" }
```

把粘贴文本作为 `.txt` 资料入库，`title` 1–200 字、`content` 最长 200,000 字，响应 `202`，结构同上，`source_type = "text"`。

### POST `/api/collections/{id}/documents/url`

```json
{ "url": "https://example.com/report" }
```

抓取网页正文后作为 Markdown 资料入库，响应 `202`，`source_type = "url"`，同时保存 `source_url` 和 `fetched_at`。只允许 http/https 公网地址，重定向逐跳校验；内网或保留地址返回 `422 URL_FORBIDDEN`，正文超过 5 MB 返回 `413 URL_TOO_LARGE`。

### GET `/api/collections/{id}/documents`

返回当前有效版本文件列表（不含已删除、历史版本）。

### GET `/api/documents/{id}/file`

返回当前用户有权限访问的原文件，供前端“查看/下载原文”使用。PDF 以 `application/pdf` 内联返回，浏览器可直接打开并支持 `#page=N` 页码跳转；Markdown 以 `text/plain` 返回；DOCX 返回原始 Office 文件，浏览器通常会下载。只允许当前版本、未删除的文件。

### GET `/api/documents/{id}/chunks/{chunk_id}/context`

返回引用片段及其前后各一段，供前端展开核对：

```json
{
  "document_id": "<uuid>",
  "document_name": "report.pdf",
  "format": "pdf",
  "chunk": { "chunk_id": "<uuid>", "ordinal": 3, "source_location": "第 3 页 · 3.2 风险应对", "text": "……" },
  "previous": { "chunk_id": "<uuid>", "ordinal": 2, "source_location": "第 2 页 · 3.1 风险识别", "text": "……" },
  "next": null
}
```

### POST `/api/documents/{id}/replace`

`multipart/form-data`，字段名 `file`。上传新版本；新版本处理成功后才切换为当前版本，失败时保留旧版本。响应 `202`。

### PATCH `/api/documents/{id}`

```json
{ "is_enabled": false }
```

停用后该文件不再参与新问题的检索，历史引用快照仍然保留。

### POST `/api/documents/{id}/retry`

重试处理失败的文件，返回 `202`。仅 `status = failed` 的文件可重试，其他状态返回 `409 DOCUMENT_NOT_FAILED`。

### DELETE `/api/documents/{id}`

软删除文件并删除本地原件，返回 `204`。该文件不再参与检索。

## 5. 会话与问答 `/api/conversations`

### GET `/api/conversations/{id}`

```json
{
  "id": "<uuid>",
  "collection_id": "<uuid>",
  "title": "项目风险是什么",
  "created_at": "2026-11-09T12:00:00Z",
  "messages": [
    {
      "id": "<uuid>",
      "role": "user",
      "content": "项目风险是什么？",
      "status": "completed",
      "created_at": "2026-11-09T12:00:00Z",
      "citations": []
    },
    {
      "id": "<uuid>",
      "role": "assistant",
      "content": "项目存在进度风险[1]。",
      "status": "completed",
      "created_at": "2026-11-09T12:00:01Z",
      "citations": [
        {
          "id": "<uuid>",
          "chunk_id": "<uuid>",
          "document_id": "<uuid>",
          "marker_index": 1,
          "document_name": "report.pdf",
          "source_location": "第 3 页 · 3.2 风险应对",
          "quote_snapshot": "原文片段……"
        }
      ]
    }
  ]
}
```

`status` 取值：`completed`、`insufficient`（证据不足）、`failed`。

### POST `/api/conversations/{id}/messages`

请求：

```json
{ "content": "这两份报告对风险的结论有什么异同？" }
```

响应 `200`：

```json
{
  "user_message": { "...": "同消息对象" },
  "assistant_message": { "...": "同消息对象，含 citations" }
}
```

- 回答仅引用本轮检索候选中的片段，非法引用编号由后端剔除。
- 回答模型使用用户显式选择的回答服务商配置；Embedding 使用资料集固定的服务商配置，因此二者可以来自不同服务商。未显式选择时回退到最近更新的可用配置。
- 如果问题中明确写出了资料集内的文件名，后端只在该文件范围内检索；写出的文件名不存在时不会退化为全资料集检索。
- 无足够证据时 `assistant_message.status = insufficient`，内容为“当前资料无法确认……”。

### POST `/api/conversations/{id}/messages/stream`

请求体与上一个接口相同，响应 `text/event-stream`，事件顺序如下：

| event | data |
|---|---|
| `status` | `{"stage": "retrieval"}` 或 `{"stage": "answering"}` |
| `delta` | `{"text": "增量文本"}` |
| `done` | `{"assistant_message": {…含 citations}, "user_message": {…}}` |
| `error` | `{"code": "…", "message": "…"}` |

检索结束后后端会释放数据库连接，模型生成期间不占用连接池；客户端断开时会用独立会话保存已生成的内容（`status = failed`），不会留下只有提问没有回答的会话。

### DELETE `/api/conversations/{id}`

删除会话及其消息、引用，返回 `204`。

## 6. 系统

### GET `/api/health`

```json
{ "status": "ok" }
```

会执行一次 `SELECT 1`；数据库不可用时返回 500，供 Docker healthcheck 和前端启动依赖真实判断。

## 7. 错误码

| HTTP | code | 含义 |
|---|---|---|
| 400 | `EMPTY_FILE` | 上传文件为空 |
| 403 | `ORIGIN_REJECTED` | 写请求来源不在 `CORS_ORIGINS` 白名单内 |
| 404 | `NOT_FOUND` | 资源不存在 |
| 409 | `DUPLICATE_FILE` | 资料集内存在相同内容文件 |
| 409 | `DOCUMENT_NOT_FAILED` | 仅处理失败的文件可以重试 |
| 409 | `DOCUMENT_NOT_CURRENT` | 只能替换当前版本的文件 |
| 409 | `REINDEX_EMPTY` | 资料集没有可重建索引的片段 |
| 409 | `REINDEX_IN_PROGRESS` | 该资料集正在重建索引 |
| 413 | `FILE_TOO_LARGE` | 文件超过大小限制 |
| 415 | `UNSUPPORTED_FORMAT` | 不支持的文件格式或文件头不匹配 |
| 422 | `VALIDATION_ERROR` | 请求参数不合法 |
| 422 | `UNSUPPORTED_PROVIDER` | 不在服务商白名单内 |
| 422 | `API_KEY_REQUIRED` | 首次保存缺少 API Key |
| 422 | `MODEL_NOT_CONFIGURED` | 尚未配置模型服务 |
| 429 | `RATE_LIMITED` | 请求过于频繁，短暂等待后重试 |
| 502 | `MODEL_PROVIDER_ERROR` | 模型服务调用失败 |
| 502 | `CONVERSATION_FAILED` | 回答生成失败 |
| 500 | `INTERNAL_ERROR` | 未预期的系统错误 |

说明：`MODEL_PROVIDER_ERROR` 在模型服务返回错误或网络失败时是 `502`；当资料集已固定的 Embedding 模型与当前配置不一致、或向量维度不匹配时，后端返回 `422`，提示先恢复配置或重建索引。
