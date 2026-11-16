# 面向个人多文件资料的知识库问答系统

一个人多文件资料问答 Web 原型（毕业设计）：导入 PDF、DOCX、Markdown、TXT、PPTX、XLSX、网页链接或粘贴文本，按标题/段落切片并建立向量与 BM25 索引，围绕资料集或指定文件提问，回答流式输出并附带可展开的原文引用；资料不足时明确说明无法确认。

## 技术栈

- 前端：React 18、Vite、TypeScript、Tailwind CSS
- 后端：Python、FastAPI、SQLAlchemy、Psycopg
- 数据库：PostgreSQL 16 + pgvector
- 运行模式：本地单用户，首次启动自动创建/复用本机用户，无需注册登录
- 模型：用户自配 OpenAI 兼容服务（服务商地址由后端白名单固定），支持 OpenAI、阿里云百炼、智谱 AI、硅基流动、DeepSeek、本地 Ollama；模型名可自定义，DeepSeek 仅用于回答模型，Ollama 无需 API Key
- 解析：pypdf、python-docx、python-pptx、openpyxl、Markdown/TXT、trafilatura（网页正文）
- 检索：pgvector 语义召回 + jieba 分词 BM25 + RRF 融合 + 可选 rerank（硅基流动 bge-reranker）

## 已实现功能

- 本地单用户模式：自动归属本机用户，不做注册、登录和账号切换
- 从多用户版本升级时会复用数据库中最早创建的用户以保留已有资料；其他用户的数据不会自动合并
- 模型服务配置：加密保存 API Key、掩码展示、连接测试、更新与删除；添加时选择“检索 / 回答 / 两者”，检索与回答可分别使用不同服务商，新增配置不会覆盖已有角色
- 资料集创建、重命名、删除
- 文件上传、处理状态、失败原因、失败重试、重复内容检测、停用、软删除、版本替换
- 多源入库：文件上传、粘贴文本、网页链接导入（含 SSRF 防护）；PDF/DOCX/Markdown/TXT/PPTX/XLSX 解析，按标题/段落/句子切片并保留页码或标题路径
- 语义检索 + BM25 关键词检索，RRF 融合，上下文保留 3–5 条；可配置 rerank 精排，失败自动回退
- 提问时可显式勾选检索范围（整个资料集或指定文件），与问题中提到的文件名取交集，越权文件直接拒绝
- pgvector 按 768/1024/1536/3072 维建立表达式 HNSW 索引；`chunk_terms` 倒排表支撑 BM25，未命中向量维度自动退化为精确扫描
- 资料集重建索引：切换 Embedding 模型或维度时全量重算向量、递增索引版本，失败保留旧索引
- 同会话追问改写与复合问题拆分；用户明确写出的文件名会作为检索过滤条件
- 单 Agent 可主动调用受控 `search_documents` 工具补充检索，后端限制工具名、查询长度、调用轮数与次数，并强制用户/资料集/文件状态过滤
- 引用校验、证据不足提示、无引用提示与检索轨迹日志；引用卡片可直接打开原文件，PDF 自动跳到对应页，并可展开前后片段核对上下文
- SSE 流式回答：检索与生成分阶段推送，结束后统一校验引用并落库
- 资料集文件列表支持查看/下载原文件（PDF 内联、Markdown/TXT 原文，Office 文件下载）
- 问答/上传/重建限流；本地服务只监听回环地址时使用
- 入库可切换 inline（进程内后台任务）或 worker（`processing_jobs` 任务表 + 独立进程消费）：失败指数退避重试、超时锁回收、多 worker 用 `SKIP LOCKED` 不重复处理
- 替换或删除文件时清理旧片段与倒排词表
- 会话历史与引用快照
- 离线评测脚本、Recall@K/MRR 轨迹分析、单元测试与集成测试

## 快速开始

### 1. 配置环境变量

```powershell
Copy-Item .env.example .env
```

编辑 `.env`，生成并填入模型 API Key 的加密主密钥：

```powershell
python -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

单用户模式启动后自动使用本机用户，无需登录。

### 2. 启动数据库

```powershell
docker compose up -d db
```

没有 Docker 时改用带 pgvector 的云数据库，或本机安装 PostgreSQL 16 + pgvector（Windows 也可用 WSL2 只跑数据库），步骤见 [部署说明第 5 节](docs/deployment.md)。项目只要求数据库是 PostgreSQL + pgvector，前后端都在本机运行。

### 3. 启动后端

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\alembic upgrade head
.\.venv\Scripts\uvicorn app.main:app --reload --port 8000
```

需要异步入库时，在 `.env` 设置 `INGESTION_MODE=worker`，并另开一个终端启动 worker：

```powershell
cd backend
.\.venv\Scripts\python -m app.worker
```

老数据升级后，执行一次 `python scripts\rebuild_terms.py` 补建 BM25 词表。

### 4. 启动前端

```powershell
cd frontend
npm install
npm run dev
```

打开 `http://127.0.0.1:5173`。开发端口固定为 5173：被占用时 Vite 会直接报错，不会自动顺延到 5174，先停掉占用进程再启动。

打开后直接进入资料集页面。在“模型服务”里选择服务商、填写 API Key、保存即可，模型默认使用服务商推荐值；需要更换模型或配置重排时展开“更改模型”，需要让检索和回答使用不同服务商时在“当前使用”里切换。

### 5. 一键容器方式（可选）

```powershell
docker compose up --build
```

Compose 已包含 `worker` 服务，但默认 `INGESTION_MODE=inline`；需要异步入库时先在 `.env` 设置 `INGESTION_MODE=worker`。

## 目录

```text
backend/app/          FastAPI 应用（models / schemas / api / services）
backend/tests/        单元测试与集成测试
backend/scripts/      建库脚本、主密钥轮换等运维脚本
frontend/src/         React 页面、组件与 API 客户端
evaluation/           离线评测脚本、轨迹分析、样例数据集与报告目录
docs/                 需求、设计、目录规范、API、评测与部署文档
storage/              本地上传目录（内容不提交）
.github/workflows/    CI（后端 lint/测试，前端 lint/format/test/build）
```

目录与命名约定见 `docs/project-structure.md`，接口契约见 `docs/api.md`。

## 测试

```powershell
cd backend
.\.venv\Scripts\pytest tests\unit --cov=app --cov-report=term-missing

$env:TEST_DATABASE_URL = "postgresql+psycopg://qa:qa@localhost:5432/document_qa_test"
.\.venv\Scripts\pytest tests\integration
```

集成测试使用独立测试库 `document_qa_test`，会重建表结构，不要指向开发库。

前端检查：

```powershell
cd frontend
npm run lint
npm run format:check
npm test
npm run build
```

## 评测

评测运行方式与指标定义见 `docs/evaluation.md`。`evaluation/run_evaluation.py` 记录实际回答、引用与拒答情况，`evaluation/analyze_traces.py` 读取后端 `retrieval_trace` 日志计算文件级/片段级 Recall@K 与 MRR。当前尚未在真实资料上运行，不提供任何准确率结论。

## 安全说明

- 用户 API Key 使用 AES-GCM 加密后存储，接口只返回掩码；前端不保存 Key，也不直接请求模型服务。
- 本地单用户模式不做账号认证，建议只监听 `127.0.0.1`，不要把服务暴露到公网。
- 写请求校验 Origin，跨站来源直接拒绝；问答、上传、重建索引和连接测试有限流。
- 服务商地址只来自后端白名单；限流为单进程内存计数，多实例部署需要换成共享存储。
- 检索在 SQL 层先行过滤用户、资料集和文件状态。
- 文档正文按不可信数据处理，提示词要求忽略其中的指令。
- 回答渲染禁用原始 HTML、远程图片与自动加载内容。
- 生产前端由 Nginx 设置 CSP、`X-Content-Type-Options`、`X-Frame-Options` 与 `Referrer-Policy`。
- `.env`、上传原件、数据库卷和评测私有数据不进入 Git。

## MVP 边界

- 不支持扫描件 OCR、图片/音视频理解和复杂表格解析。
- 不包含 Celery/Redis/Kafka、多 Agent、管理员后台、云盘同步和生产级集群部署。
- 文件处理在应用进程内后台执行，重启时会把未完成任务标记为失败，需要用户手动重试。
- 重建索引是同步操作，片段很多时会较慢；按片段增量重建、后台重建进度条仍不在范围内。
- 限流为单进程内存实现，多 worker 部署时需要替换为 Redis 等共享存储。

## 文档

- [产品需求](docs/PRD.md)
- [系统设计](docs/system-design.md)
- [目录与命名规范](docs/project-structure.md)
- [API 契约](docs/api.md)
- [评测说明](docs/evaluation.md)
- [部署说明](docs/deployment.md)
- [模型可用性审核](docs/model-compatibility.md)
