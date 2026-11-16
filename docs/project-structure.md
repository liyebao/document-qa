# 项目文件目录规范

| 项目 | 内容 |
|---|---|
| 文档版本 | v2.0 |
| 适用项目 | 面向个人多文件资料的知识库问答系统 |
| 关联文档 | `docs/PRD.md`、`docs/system-design.md`、`docs/project-plan.md`、`docs/model-compatibility.md` |
| 文档作用 | 规定仓库目录、文件落位、命名和禁止事项，作为开发与代码评审的检查依据 |

## 1. 基本原则

1. **单仓库**：前端、后端、部署配置、文档和评测资料放在同一仓库，便于个人开发和答辩演示。
2. **按需创建**：不预先创建空文件或空目录；开始实现某个模块时再建对应文件，避免目录膨胀。
3. **一文件一职责**：一个文件只承担一个明确职责，超过约 200 行的路由或服务文件应拆分。
4. **目录即边界**：跨目录调用只能按"路由 → 服务 → 数据/外部能力"方向进行，不允许反向依赖。
5. **就近放置**：只服务单一模块的辅助代码放在该模块目录内，不提前抽到公共工具目录。
6. **规范变更**：新增顶层目录、调整分层或新增文档类别时，先修改本文件与 `.trae/rules/project_rules.md`，再写代码。

## 2. 根目录结构

```text
毕设/                              # 仓库根目录
├─ README.md                       # 项目介绍、环境要求、启动与演示步骤
├─ LICENSE                         # MIT 许可证
├─ .editorconfig                   # 跨编辑器缩进与换行约定
├─ .pre-commit-config.yaml         # 提交前 Ruff / Prettier 检查
├─ .gitignore                      # 排除密钥、上传资料、缓存、构建产物
├─ .env.example                    # 环境变量名称与示例值，不含真实密钥
├─ .github/workflows/ci.yml        # 后端 lint/测试与前端 lint/test/build
├─ docker-compose.yml              # 前端、后端、PostgreSQL/pgvector 本地编排
├─ docker/
│  └─ init-test-db.sql             # 首次初始化测试库
├─ .trae/
│  └─ rules/
│     └─ project_rules.md          # 本项目 AI 开发规则
├─ docs/                           # 需求基线、项目设计、目录规范等全部文档
├─ backend/                        # Python/FastAPI 后端
├─ frontend/                       # React/Vite 前端
├─ evaluation/                     # 离线评测脚本、样例数据集和报告
└─ storage/                        # 本地上传目录（内容不提交）
```

**根目录只允许**：配置文件、部署文件、README，以及 `docs/`、`backend/`、`frontend/`、`evaluation/`、`storage/`、`docker/`、`.trae/` 目录。需求与设计文档统一放 `docs/`，根目录不保留文档副本；临时脚本、调试输出、个人笔记不得放在根目录。

## 3. 后端 `backend/`

```text
backend/
├─ pyproject.toml                  # 依赖与格式化、检查、测试工具配置
├─ Dockerfile
├─ alembic.ini
├─ alembic/
│  └─ versions/                    # 迁移脚本，命名见第 7 节
├─ app/
│  ├─ main.py                      # FastAPI 应用入口，只做装配
│  ├─ core/                        # 配置、加密、日志、限流、统一错误
│  │  ├─ config.py
│  │  ├─ secrets.py
│  │  ├─ ratelimit.py
│  │  ├─ errors.py
│  │  └─ logging.py
│  ├─ db/
│  │  ├─ session.py                # 数据库会话
│  │  └─ base.py                   # ORM 模型注册
│  ├─ models/                      # 持久化实体
│  ├─ schemas/                     # 请求/响应结构
│  ├─ api/
│  │  ├─ deps.py                   # 本地用户、归属校验、数据库依赖
│  │  └─ routes/                   # 按资源拆分的路由
│  └─ services/                    # 业务逻辑与外部能力适配
├─ scripts/
│  ├─ init_local_db.sql            # 无 Docker 时建库建账号
│  ├─ rebuild_terms.py             # 补建 BM25 词表
│  └─ rotate_credential_key.py     # 主密钥轮换脚本
└─ tests/
   ├─ conftest.py                  # 测试夹具（按需创建）
   ├─ unit/
   └─ integration/
```

### 3.1 各目录职责

| 目录 | 放什么 | 禁止放什么 |
|---|---|---|
| `app/main.py` | 应用创建、路由注册、中间件、启动/关闭钩子 | 业务逻辑、SQL |
| `app/core/` | 环境配置、Key 加解密、日志与脱敏、限流、统一业务异常 | 业务规则、数据表操作 |
| `app/db/` | 引擎、会话、Base 与模型导入 | 业务查询、路由逻辑 |
| `app/models/` | SQLAlchemy 实体、字段、关系、约束 | 检索流程、Pydantic 校验 |
| `app/schemas/` | Pydantic 请求/响应模型、字段校验 | 数据库读写 |
| `app/api/deps.py` | 本地用户、资源归属、分页等通用依赖 | 具体业务流程 |
| `app/api/routes/` | HTTP 方法、路径、状态码、依赖注入、调用 service | SQL、模型调用、复杂分支 |
| `app/services/` | 业务编排、解析、切片、检索、回答、外部服务适配 | HTTP 相关对象（Request/Response） |
| `tests/` | 单元与集成测试 | 生产代码、调试脚本 |

### 3.2 关键模块落位

| 文件 | 职责 |
|---|---|
| `services/ingestion.py` | 文件处理状态机与入库编排：校验 → 解析 → 切片 → 向量化 → 写库；启动恢复中断任务 |
| `services/collections.py` | 资料集增删改查、物理文件清理与全量重建索引 |
| `services/query_planner.py` | 同会话追问改写、复合问题拆分、提取用户明确提到的文件名过滤；不生成权限条件 |
| `services/parsers/pdf.py`、`docx.py`、`markdown.py` | 按格式提取正文与页码/标题；不做问答 |
| `services/chunking.py` | 片段边界、重叠、标题路径与来源元数据；不调用 LLM |
| `services/embeddings.py` | Embedding 服务封装与批量请求 |
| `services/model_provider.py` | 支持服务商白名单、密钥读取、连接测试 |
| `services/retrieval/vector.py`、`keyword.py`、`fusion.py` | 语义召回、关键词召回、RRF 融合去重；不生成自然语言 |
| `services/agent.py` | 单 Agent 的检索范围、证据选择与上下文组织 |
| `services/agent_tools.py` | `search_documents` 工具定义、参数校验与工具调用循环 |
| `services/answering.py` | 回答流程编排、提示词、证据不足处理 |
| `services/citations.py` | 引用编号校验与无引用提示 |
| `services/trace.py` | 结构化检索轨迹日志 |
| `services/local_user.py` | 单用户模式：复用或创建本地用户 |
| `services/conversations.py` | 会话、消息与引用读取，编排一次问答 |
| `services/storage.py` | 上传文件读写、随机命名、删除 |
| `services/model_provider.py` | 服务商白名单、模型能力/批量适配、密钥读取、连接测试 |
| `api/routes/settings.py`、`collections.py`、`documents.py`、`conversations.py` | 对应资源的 HTTP 层，含原文件读取接口 |

**新增文件落位决策表**

| 要写的代码 | 放哪里 |
|---|---|
| 新的 HTTP 接口 | `app/api/routes/<资源复数>.py`，必要时在 `main.py` 注册 |
| 请求/响应模型 | `app/schemas/<资源>.py` |
| 新的数据库实体 | `app/models/<实体>.py`，并在 `db/base.py` 注册，配套迁移 |
| 新的业务能力 | `app/services/<能力>.py` |
| 新的解析格式 | `app/services/parsers/<格式>.py`，并在 ingestion 中接入 |
| 新的检索策略 | `app/services/retrieval/<策略>.py` |
| 通用纯函数 | 就近放在使用它的模块内，不预先建 utils 目录 |
| 单元/集成测试 | `tests/unit/test_<模块>.py`、`tests/integration/test_<场景>.py` |

## 4. 前端 `frontend/`

```text
frontend/
├─ package.json
├─ package-lock.json              # 依赖锁定文件
├─ vite.config.ts
├─ tsconfig.json
├─ tailwind.config.js
├─ postcss.config.js
├─ index.html
├─ Dockerfile                      # 多阶段构建：Node 构建 + Nginx 静态服务
├─ nginx.conf                      # SPA 回退与 /api 反向代理
├─ eslint.config.js
├─ .prettierrc.json
├─ vitest.config.ts
└─ src/
   ├─ main.tsx                     # React 入口
   ├─ app/                         # 路由、全局布局、错误边界
   ├─ api/                         # 后端 API 客户端、类型与前端请求测试
   ├─ components/                  # 可复用展示组件
   ├─ lib/                         # 引用原文链接等前端纯函数
   ├─ pages/                       # 页面级组件
   └─ styles/                      # Tailwind 入口与全局样式
```

| 目录 | 放什么 | 禁止放什么 |
|---|---|---|
| `src/app/` | 路由表、布局、全局 Provider | 具体业务请求 |
| `src/api/` | 按资源拆分的请求函数、类型定义、错误转换 | UI 状态、组件 |
| `src/components/` | `FileStatus`、`CitationCard`、`ChatMessage`、`DocumentSection`、`ProviderEditor`、`ModelRoles` 等展示组件 | 页面级数据编排 |
| `src/pages/` | `CollectionsPage`、`CollectionPage`、`ConversationPage`、`SettingsPage` | 直接拼 URL 请求后端 |
| `src/styles/` | Tailwind 指令与全局样式 | 组件级样式逻辑 |

- 新增页面时同时登记到 `src/app/` 路由。
- 新增请求模块时按资源建文件（如 `api/collections.ts`），类型统一放 `api/types.ts` 或同文件导出。
- 不在 `components/` 内直接调用后端；需要数据时由页面传入。

## 5. 文档 `docs/`

```text
docs/
├─ PRD.md                 # 产品需求文档（需求基线）
├─ system-design.md       # 项目设计文档（架构、数据、流程、安全）
├─ project-plan.md        # 原始目录结构规划稿，仅作追溯
├─ project-structure.md   # 本文件：目录与命名规范（以此为准）
├─ api.md                 # API 契约与错误码
├─ evaluation.md          # 评测集格式、指标、对照方案与结果
└─ deployment.md          # 本地启动、备份恢复、演示部署
```

- 需求基线为 `PRD.md` 与 `system-design.md`；目录以 `project-structure.md` 为准，`project-plan.md` 与规范冲突时以规范为准。
- `PRD.md` 为固定名称，其余文档使用小写英文短横线命名。
- 文档修改后需在文首版本表更新版本号；根目录不保留文档副本。

## 6. 评测 `evaluation/` 与存储 `storage/`

```text
evaluation/
├─ dataset.example.jsonl          # 脱敏的问答/证据样例格式
├─ run_evaluation.py              # 通过 API 运行问题集
├─ analyze_traces.py              # 从 retrieval_trace 计算 Recall@K/MRR
├─ metrics.py                     # Recall@K、MRR、引用与拒答统计
└─ reports/                       # 评测结果与失败案例，不存秘密

storage/
├─ .gitkeep
└─ uploads/                       # 运行时生成，不提交
```

- 评测报告命名：`reports/<YYYYMMDD>-<检索方案>-<数据集名>.md`，同名原始数据存 `.json`。
- 报告中不得包含真实用户材料、API Key 或个人隐私。
- 上传文件路径约定 `storage/uploads/<collection_id>/<document_id>.<ext>`；原始文件名只存数据库，不用于磁盘路径。
- `storage/` 下除 `.gitkeep` 外全部忽略提交。

## 7. 命名规范

### 7.1 文件与代码

| 类别 | 规范 | 示例 |
|---|---|---|
| Python 模块 | 小写下划线 | `query_planner.py` |
| Python 类 | 大驼峰 | `ModelProviderConfig` |
| Python 函数/变量 | 小写下划线 | `build_context()` |
| 常量/枚举值 | 大写下划线 | `DOCUMENT_STATUS_READY` |
| 测试文件 | `test_` + 被测模块 | `test_chunking.py` |
| React 组件/页面 | 大驼峰 + `.tsx` | `CitationCard.tsx`、`SettingsPage.tsx` |
| Hook | `use` + 大驼峰 | `useConversation.ts` |
| 前端请求模块 | 小驼峰或资源名 | `collections.ts` |
| 文档 | 小写英文短横线 | `project-structure.md` |
| 迁移脚本 | Alembic 生成的 `revision_<说明>` | `a1b2c3_add_citations.py` |

### 7.2 数据库

| 对象 | 规范 | 示例 |
|---|---|---|
| 表名 | 小写复数下划线 | `users`、`model_provider_configs`、`chunks` |
| 字段 | 小写下划线 | `created_at`、`page_start` |
| 外键 | `<单数表名>_id` | `collection_id` |
| 索引 | `ix_<表>_<字段>` | `ix_chunks_document_id` |
| 唯一约束 | `uq_<表>_<字段>` | `uq_documents_checksum` |

### 7.3 接口与配置

- API 路径：`/api/<资源复数>`，子资源嵌套，如 `/api/collections/{id}/documents`、`/api/conversations/{id}/messages`。
- JSON 字段：小写下划线，与前端 TypeScript 类型一致，不做自动驼峰转换。
- 环境变量：大写下划线，如 `DATABASE_URL`、`CREDENTIAL_ENCRYPTION_KEY`。
- 服务商标识：小写下划线，如 `openai`、`dashscope`。

### 7.4 Git

- 分支：`feat/<功能>`、`fix/<问题>`、`docs/<文档>`、`chore/<杂项>`。
- 提交信息：`<type>: <中文简述>`，type 取 `feat|fix|refactor|docs|test|chore`。
- 一次提交只做一件事，不把格式化与功能改动混在一起。

## 8. 禁止事项

1. 在 `api/routes/` 写 SQL、模型调用或大段业务分支。
2. 在 `schemas/` 中操作数据库，或在 `models/` 中写业务流程。
3. 在 `chunking.py` 中调用 LLM，或在 `retrieval/` 中生成自然语言回答。
4. 跳过权限过滤直接检索全库，再在前端或应用层筛选。
5. 提交 `.env`、真实 API Key、上传原件、数据库卷、`__pycache__`、`.venv`、`node_modules`、构建产物、个人评测材料。
6. 预建大量空目录或占位文件。
7. 在根目录堆放临时脚本、调试输出或文档副本。
8. 未经评测依据直接修改切片长度、候选数、阈值等检索参数。

## 9. 实施顺序

按「配置与入口 → 单文件上传到引用问答闭环 → 多文件与权限隔离 → 混合检索与评测 → 查询规划与证据可靠性 → 可选精排 → 交付整理」推进；每完成一个模块再创建对应目录与文件。
