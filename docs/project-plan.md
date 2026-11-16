# 面向个人多文件资料的知识库问答系统：项目目录结构规划

> 注：本文件是早期规划稿，认证/多用户相关规划仅作历史追溯；当前实现已改为本地单用户模式，以 `docs/PRD.md`、`docs/system-design.md` 和实际代码为准。

| 项目 | 内容 |
|---|---|
| 文档版本 | v1.1 |

## 1. 规划原则

- 一个仓库管理前端、后端、部署和评测资料，便于个人开发和答辩演示。
- 后端按 API、数据模型、业务服务拆分；解析、切片、检索、回答逻辑各自独立，方便评测对照。
- MVP 不先引入 Celery、Redis、Kafka 等后台基础设施；文件处理先由后端任务服务管理，完成后再按需要扩展。
- 上传文件、数据库数据、密钥和运行日志不提交到 Git；仓库只保留示例配置和脱敏样例。

## 2. 推荐仓库目录

```text
document-qa-agent/
├─ README.md                       # 项目介绍、环境要求、启动和演示步骤
├─ .gitignore                      # 排除密钥、上传资料、缓存、构建产物
├─ .env.example                    # 环境变量名称和示例值，不放真实密钥
├─ docker-compose.yml              # 前端、后端、PostgreSQL/pgvector 本地编排
├─ docs/
│  ├─ PRD.md                       # 精简复制/链接最终版产品需求
│  ├─ system-design.md             # 架构、模块、数据流和安全设计
│  ├─ api.md                       # API 契约和错误码
│  ├─ evaluation.md                # 评测集格式、指标、对照方案和结果
│  └─ deployment.md                # 本地启动、备份、恢复和演示部署说明
├─ backend/
│  ├─ pyproject.toml               # Python 依赖及工具配置
│  ├─ alembic.ini                  # 数据库迁移配置
│  ├─ alembic/
│  │  └─ versions/                 # 数据库结构迁移脚本
│  ├─ app/
│  │  ├─ main.py                   # FastAPI 应用入口
│  │  ├─ core/
│  │  │  ├─ config.py              # 环境配置读取
│  │  │  ├─ (已移除) security.py   # 单用户模式不再使用密码/JWT
│  │  │  ├─ secrets.py             # 用户模型 API Key 的认证加密/解密
│  │  │  └─ logging.py             # 日志配置与敏感字段过滤
│  │  ├─ db/
│  │  │  ├─ session.py             # SQLAlchemy/Psycopg 会话
│  │  │  └─ base.py                # ORM 模型注册
│  │  ├─ models/                   # 数据库实体
│  │  │  ├─ user.py
│  │  │  ├─ model_provider_config.py # 用户模型服务商和加密 Key 配置
│  │  │  ├─ collection.py
│  │  │  ├─ document.py
│  │  │  ├─ chunk.py
│  │  │  ├─ conversation.py
│  │  │  ├─ message.py
│  │  │  └─ citation.py
│  │  ├─ schemas/                  # 请求与响应结构
│  │  ├─ api/
│  │  │  ├─ deps.py                # 本地用户、归属和数据库依赖
│  │  │  └─ routes/
│  │  │     ├─ settings.py          # 查询/保存/测试/删除模型服务配置
│  │  │     ├─ collections.py
│  │  │     ├─ documents.py
│  │  │     └─ conversations.py
│  │  └─ services/
│  │     ├─ ingestion.py           # 文件处理状态和入库编排
│  │     ├─ query_planner.py       # 同会话追问改写、复合问题拆分
│  │     ├─ parsers/
│  │     │  ├─ pdf.py
│  │     │  ├─ docx.py
│  │     │  └─ markdown.py
│  │     ├─ chunking.py            # 按标题/段落/句子切片并保留位置
│  │     ├─ embeddings.py          # Embedding 服务封装
│  │     ├─ model_provider.py       # 支持服务商适配、密钥读取和连接测试
│  │     ├─ retrieval/
│  │     │  ├─ vector.py           # pgvector 语义检索
│  │     │  ├─ keyword.py          # PostgreSQL 全文关键词检索
│  │     │  └─ fusion.py           # RRF 合并、去重和排序
│  │     ├─ answering.py           # 单 Agent 提示、回答和引用校验
│  │     └─ storage.py             # 上传文件读写与删除
│  └─ tests/
│     ├─ unit/                     # 切片、RRF、查询规划等单元检查
│     └─ integration/              # 入库、权限隔离、引用生命周期检查
├─ frontend/
│  ├─ package.json                # 前端依赖和脚本
│  ├─ vite.config.ts
│  ├─ index.html
│  └─ src/
│     ├─ main.tsx                 # React 入口
│     ├─ app/                     # 页面路由和全局布局
│     ├─ api/                     # 后端 API 客户端和类型
│     ├─ components/
│     │  ├─ FileStatus.tsx
│     │  ├─ CitationCard.tsx
│     │  └─ ChatMessage.tsx
│     ├─ pages/
│     │  ├─ CollectionsPage.tsx
│     │  ├─ CollectionPage.tsx
│     │  └─ ConversationPage.tsx
│     └─ styles/
├─ evaluation/
│  ├─ dataset.example.jsonl       # 脱敏的问题/答案/证据片段格式示例
│  ├─ run_evaluation.py           # 离线评测入口
│  ├─ metrics.py                  # Recall@K、MRR、引用和拒答统计
│  └─ reports/                    # 评测结果与失败案例，不存秘密
└─ storage/
   └─ .gitkeep                    # 本地上传目录占位；实际文件忽略提交
```

## 3. 首期真正需要实现的部分

### P0：贯通可演示流程

1. `backend/app/main.py`、配置、数据库连接和初始迁移。
2. 本地用户依赖和资源归属检查；模型设置页保存加密 Key 并测试连接。
3. 资料集与文件 API、文件状态、PDF/DOCX/Markdown 解析。
4. 重复文件检测、切片及来源位置保存、Embedding 和 PostgreSQL 索引。
5. 同会话追问改写、复合问题拆分、语义与关键词检索、RRF 融合、引用式回答和历史记录。
6. 前端资料集/文件列表、问答页面和引用详情。
7. `docker-compose.yml`、`.env.example`、README 启动说明。

### P1：有评测证据后再加

- `services/reranking.py`：仅在混合检索的评测结果显示排序仍是主要问题时增加。
- HyDE 和多角度查询扩展：只有确认问题表达差异造成明显漏召回，且成本和延迟可接受时增加。同会话追问改写属于 MVP。
- 更复杂的异步队列、Redis 缓存、追踪平台或生产级部署：不属于首期必要结构。

## 4. 文件与模块边界

- **`models/`**只描述持久化实体和关系，不放检索流程。
- **`schemas/`**只负责 API 输入输出校验，不直接执行数据库操作。
- **`api/routes/`**处理 HTTP 和权限依赖，把业务交给 `services/`。
- **`query_planner.py`**只改写同会话指代或拆分明确的复合问题，不生成权限条件，不改变用户意图。
- **`services/parsers/`**提取文本与页码/标题等来源；不负责回答问题。
- **`chunking.py`**负责片段边界、重叠和来源元数据；不调用 LLM。
- **`services/retrieval/`**只返回候选片段及排序/来源信息；不生成自然语言回答。
- **`answering.py`**组织证据、调用模型并检查引用 ID；不能自行扩大检索权限。
- 文件删除从检索中软排除；历史引用依靠快照展示。物理清理前需处理 Citation 外键关系。
- **`evaluation/`**使用独立标注集对配置做离线比较；不将外部文章报告的准确率写成项目结果。

## 5. 配置与 Git 管理约定

- `.env.example` 包含 `DATABASE_URL`、`CREDENTIAL_ENCRYPTION_KEY`、上传目录和文件大小限制的示例配置；不包含用户自己的模型 API Key。`CREDENTIAL_ENCRYPTION_KEY` 只用于加密用户 Key，必须与数据库密文分开保管。
- `.env`、真实 API Key、用户上传原件、数据库卷、个人评测材料均加入 `.gitignore`。
- `pyproject.toml` 与前端 lockfile 应提交，保证依赖安装可复现；容器镜像标签应固定，不用 `latest`。
- 只提交明确允许公开的演示样例；未经授权的课程或个人资料不放入仓库。
- PRD、系统设计和 API 文档统一维护在 `docs/`；根目录保留用户当前使用的正式文档，实施时再复制为仓库内文档并标注版本。

## 6. 推荐创建顺序

先建根目录配置、后端应用入口和数据库迁移，再实现单文件上传到引用问答的最小闭环；随后扩展多文件、混合检索、权限隔离和评测，最后整理 Docker Compose 与文档。暂时不需要预先创建所有空文件；按模块开始实现时再创建对应文件，避免目录先膨胀而无实际内容。
