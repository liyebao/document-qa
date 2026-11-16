# 部署与运行说明

| 项目 | 内容 |
|---|---|
| 文档版本 | v2.1 |
| 适用范围 | 本地开发、答辩演示、Docker Compose 运行与无 Docker 的本机/云数据库运行 |

## 1. 环境要求

- Python 3.12（后端）
- Node.js 20 及以上、npm 10 及以上（前端）
- PostgreSQL 16 + pgvector（推荐 `pgvector/pgvector:pg16` 镜像）
- Docker 与 Docker Compose（使用容器方式时）；没有 Docker 时改成本机 PostgreSQL 或云数据库，见第 5 节

## 2. 环境变量

复制根目录 `.env.example` 为 `.env`：

| 变量 | 说明 |
|---|---|
| `DATABASE_URL` | 数据库连接，格式 `postgresql+psycopg://用户:密码@主机:5432/库名` |
| `CREDENTIAL_ENCRYPTION_KEY` | 用户模型 API Key 的 AES-GCM 主密钥，base64 编码的 32 字节随机值 |
| `CREDENTIAL_ENCRYPTION_KEY_VERSION` | 主密钥版本号，默认 `1`；轮换后递增 |

生成主密钥：

```powershell
python -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

其余可调参数：`UPLOAD_DIR`、`MAX_UPLOAD_MB`、`CORS_ORIGINS`、`RETRIEVAL_CANDIDATES`、`RETRIEVAL_TOP_K`、`RRF_K`、`AGENT_MAX_TOOL_ROUNDS`、`AGENT_MAX_TOOL_CALLS`、`CHUNK_TARGET_TOKENS`、`CHUNK_MIN_TOKENS`、`CHUNK_OVERLAP_TOKENS`、`MODEL_HTTP_TIMEOUT`、`EMBEDDING_BATCH_SIZE`、`RATE_LIMIT_ASK_PER_MINUTE`、`RATE_LIMIT_UPLOAD_PER_MINUTE`、`RATE_LIMIT_REINDEX_PER_MINUTE`。

`CREDENTIAL_ENCRYPTION_KEY` 必须与数据库密文分开保管。限流为单进程内存计数，多 worker/多实例部署时需要替换为 Redis 等共享存储。

### 2.1 主密钥轮换

更换 `CREDENTIAL_ENCRYPTION_KEY` 前先备份数据库，然后在 `backend` 目录运行：

```powershell
.\.venv\Scripts\python scripts\rotate_credential_key.py --new-key "<新的 base64 32 字节密钥>"
```

脚本会把全部旧版本密文重新加密到新版本（默认当前版本 + 1），并打印新版本号。随后把 `.env` 中的 `CREDENTIAL_ENCRYPTION_KEY` 和 `CREDENTIAL_ENCRYPTION_KEY_VERSION` 改为新值并重启后端。旧版本配置存在时脚本会提示，需要确认是否继续轮换。

## 3. 本地启动（推荐开发方式）

### 3.1 启动数据库

```powershell
docker compose up -d db
```

数据库默认：`localhost:5432`，库 `document_qa`，用户/密码 `qa/qa`；同时创建测试库 `document_qa_test`。

### 3.2 启动后端

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\alembic upgrade head
.\.venv\Scripts\uvicorn app.main:app --reload --port 8000
```

接口文档：`http://localhost:8000/docs`；健康检查：`http://localhost:8000/api/health`。

### 3.3 启动前端

```powershell
cd frontend
npm install
npm run dev
```

访问 `http://127.0.0.1:5173`。开发端口固定为 5173（`vite.config.ts` 中 `strictPort: true`），被占用时启动会直接失败，不会顺延到 5174。Vite 已将 `/api` 代理到 `http://127.0.0.1:8000`。

### 3.4 使用流程

1. 打开页面直接进入资料集列表；本地单用户模式没有注册、登录和账号切换。
2. 在“模型服务”选择服务商、填写 API Key 并保存；模型默认使用推荐值，需要时展开“更改模型”调整检索/回答/重排模型，在“当前使用”里切换检索与回答服务商。
3. 创建资料集，上传或导入文件（PDF/DOCX/Markdown/TXT/PPTX/XLSX、网页链接、粘贴文本），等待状态变为“可检索”。
4. 新建会话并提问，可先勾选检索范围；回答流式返回，展开引用可核对前后片段或打开原文件。

## 4. Docker Compose 运行

```powershell
docker compose up --build
```

- 前端：`http://127.0.0.1:5173`（Nginx 提供生产构建产物，并把 `/api` 反向代理到后端）
- 后端：`http://127.0.0.1:8001`（容器内仍监听 8000，宿主机映射到 8001，避免与本地 uvicorn 冲突；Compose 端口只绑定回环地址）
- 数据库数据保存在 `pgdata` 卷；上传文件保存在 `./storage`。

后端容器启动时自动执行 `alembic upgrade head`。前端容器使用多阶段构建：Node 构建静态文件，Nginx 提供服务；上传大小上限 100 MB，`/api` 代理超时 10 分钟以支持重建索引。

如果改变前端访问地址，需要同步把该地址加入 `CORS_ORIGINS`，否则浏览器的写请求会被 `ORIGIN_REJECTED` 拒绝。

### 4.1 容器访问宿主机 Ollama

容器里的 `localhost` 指向容器自身，连不到 Windows 上的 Ollama。使用本地模型时需要：

1. 让 Ollama 监听所有网卡，并指定模型目录（Windows 用户环境变量）：

```powershell
[Environment]::SetEnvironmentVariable("OLLAMA_HOST", "0.0.0.0:11434", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_MODELS", "D:\Ollama", "User")
```

然后完全退出托盘里的 Ollama 并重新启动。

2. Compose 已为 backend 和 worker 设置：

```yaml
OLLAMA_BASE_URL: http://host.docker.internal:11434/v1
```

3. 本地开发（uvicorn 直接在 Windows 上跑）时，`.env` 保持：

```ini
OLLAMA_BASE_URL=http://localhost:11434/v1
```

注意：`OLLAMA_HOST=0.0.0.0` 会让同局域网设备也能访问 11434，建议在 Windows 防火墙里只放行 Docker 网段，或仅在本机使用。

## 5. 无 Docker 运行

前后端本来就是本机进程，容器只用于提供 PostgreSQL 16 + pgvector，所以不装 Docker 也能完整运行，差别只在数据库从哪来：

| 方式 | 适合 | 代价 |
|---|---|---|
| 带 pgvector 的云数据库（Neon、Supabase、阿里云 RDS PostgreSQL） | 不想在 Windows 上编译扩展 | 需要联网，资料不在本机 |
| 本机安装 PostgreSQL 16 + pgvector | 离线、资料只存本机 | Windows 需要编译扩展，或改用 WSL2 |
| 只装 PostgreSQL、不装 pgvector | 不可行 | 缺少 `vector` 类型，`alembic upgrade head` 直接失败 |

数据库不能换成 SQLite 或 MySQL，也不能用纯 Python 向量库顶替：检索层依赖 pgvector 的 `vector` 列、表达式 HNSW 索引，以及 `chunk_terms` 倒排表。

### 5.1 方式一：云数据库（最省事）

1. 注册支持 pgvector 的服务，创建数据库并拿到连接串。
2. 修改 `.env`，保留 SQLAlchemy 驱动前缀 `postgresql+psycopg://`，公网连接追加 `sslmode=require`：

```ini
DATABASE_URL=postgresql+psycopg://<用户>:<密码>@<主机>:5432/<库名>?sslmode=require
```

3. 之后与 3.2、3.3 相同：`alembic upgrade head` 会自动执行 `CREATE EXTENSION vector` 与 `pg_trgm`。
4. 集成测试需要另一个库；把 `TEST_DATABASE_URL` 留空时集成测试自动跳过，不影响本地开发。

### 5.2 方式二：Windows 本机安装

```powershell
winget install PostgreSQL.PostgreSQL.16
```

安装向导里设置 postgres 超级用户密码，端口保持 5432，并确保 `psql` 可用（默认在 `C:\Program Files\PostgreSQL\16\bin`）。

pgvector 不随 EDB 安装包提供，需要单独编译（先装 Visual Studio 生成工具）：

```powershell
winget install --id Microsoft.VisualStudio.2022.BuildTools --override "--wait --quiet --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
$env:PGROOT = "C:\Program Files\PostgreSQL\16"
cd $env:TEMP
git clone --branch v0.8.0 https://github.com/pgvector/pgvector.git
cd pgvector
cmd /c '"C:\Program Files\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" && nmake /F Makefile.win && nmake /F Makefile.win install'
```

`vcvars64.bat` 的位置随 VS 版本变化（Community / BuildTools，也可能在 `Program Files (x86)` 下），以本机实际安装路径为准。装完可以先用 5.1 的云数据库或 5.4 的 WSL2 顶上，避免在答辩前折腾编译。

建账号和库：

```powershell
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -f backend\scripts\init_local_db.sql
```

脚本创建 `qa/qa` 账号与 `document_qa`、`document_qa_test` 两个库，权限与 Compose 里的 `POSTGRES_USER` 一致（超级用户，便于迁移创建扩展），可重复执行。

确认扩展已就绪，两行都出现才能启动后端：

```powershell
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -d document_qa -c "SELECT name, default_version FROM pg_available_extensions WHERE name IN ('vector','pg_trgm');"
```

### 5.3 方式三：macOS / Linux 本机安装

```bash
# macOS
brew install pgvector        # 会自动安装匹配的 PostgreSQL 主版本
brew services start postgresql   # 服务名不符时按 brew services list 显示的 postgresql@XX 启动
psql -d postgres -f backend/scripts/init_local_db.sql

# Ubuntu 24.04（官方源已含 pgvector，其他版本先加 PGDG 源）
sudo apt install postgresql-16 postgresql-16-pgvector
sudo -u postgres psql -f backend/scripts/init_local_db.sql
```

### 5.4 方式四：Windows 用 WSL2 只跑数据库

不想编译 pgvector 时，可在 WSL2 里运行数据库，前后端仍留在 Windows：

```powershell
wsl --install -d Ubuntu
```

Ubuntu 内执行：

```bash
sudo apt install postgresql-16 postgresql-16-pgvector
sudo -u postgres psql -f /mnt/d/毕业设计/毕设/backend/scripts/init_local_db.sql
```

WSL2 默认开启 localhost 转发，`.env` 保持 `localhost:5432` 即可；不要与 Windows 版 PostgreSQL 同时占用 5432。

### 5.5 与容器方式的差异

- 后端和前端日志直接输出在各自终端，没有 `docker compose logs`。
- 备份改用本机 `pg_dump`，命令去掉 `docker compose exec db` 前缀（见第 6 节）。
- 需要异步入库时，在 `.env` 设置 `INGESTION_MODE=worker` 并另开终端运行 `python -m app.worker`，没有 Compose 的 `worker` 服务。

## 6. 数据库备份与恢复

备份：

```powershell
docker compose exec db pg_dump -U qa -d document_qa -Fc -f /tmp/document_qa.dump
docker compose cp db:/tmp/document_qa.dump .\document_qa.dump
```

恢复：

```powershell
docker compose cp .\document_qa.dump db:/tmp/document_qa.dump
docker compose exec db pg_restore -U qa -d document_qa --clean /tmp/document_qa.dump
```

上传原件位于 `storage/uploads/`，需要与数据库备份一起保存；恢复后文件路径才能对应。

## 7. 测试与评测

单元测试：

```powershell
cd backend
.\.venv\Scripts\pytest tests\unit
```

集成测试（会清空测试库表结构，不要指向开发库）：

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://qa:qa@localhost:5432/document_qa_test"
.\.venv\Scripts\pytest tests\integration
```

前端检查：

```powershell
cd frontend
npm run lint
npm run format:check
npm test
npm run build
```

评测入口与指标见 `docs/evaluation.md`。

## 8. 演示与安全注意事项

- 单用户模式没有账号认证，只应在本机使用；建议后端和前端都绑定 `127.0.0.1`，不要把 8000 端口暴露到公网。
- 如确需局域网访问，应在前面增加反向代理和访问控制，或恢复账号认证，不能直接裸奔。
- 真实 `.env`、上传原件、数据库卷、模型 API Key 不得提交到 Git。
- 写请求仍校验 Origin 白名单，避免浏览器跨站请求本地服务。
- 删除用户模型配置不会代替其在服务商处撤销 Key。
- MVP 为单机原型，文件处理在应用进程内后台执行；进程重启会丢失未完成的任务，需要重新上传。
