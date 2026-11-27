# 个人知识库问答系统

把 PDF、Word、网页等资料放进去，用中文提问。系统从资料里找依据回答，句末的 `[1]` 可以点开原文对应页；资料里没有答案时会直接说"当前资料无法确认"。

本地单用户，不需要注册登录。

## 快速开始

### 1. 准备配置

在项目根目录执行：

```powershell
Copy-Item .env.example .env
```

打开 `.env`，填入加密主密钥（没有就新增，有就改等号右边）：

```dotenv
CREDENTIAL_ENCRYPTION_KEY=下面命令生成的结果
```

```powershell
# 有 Python
python -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"

# 没有 Python
[Convert]::ToBase64String([byte[]](1..32 | ForEach-Object { Get-Random -Minimum 0 -Maximum 256 }))
```

### 2. 启动

```powershell
docker compose up --build
```

第一次要下载镜像，等几分钟。看到 `healthy` 即可。

### 3. 打开页面

浏览器访问 `http://127.0.0.1:5173`。

> 只在本机使用。系统没有登录校验，不要把端口暴露到公网。

### 4. 配置模型

左侧 **模型服务** → 选服务商 → 填 API Key → 角色选 **两者** → 保存 → 测试连接。

用本地 Ollama 时不用填 Key。测试连接会消耗少量额度，属正常。

## 怎么用

1. **新建资料集**：首页点「新建资料集」，按主题建（一个主题一个，检索更准）
2. **上传文件**：进资料集点「上传」，等状态从"处理中"变成"就绪"
3. **提问**：新建会话，输入问题

回答里要注意两处：

- 句末的 `[1]` 是引用编号，**点它会打开原文对应页**
- 下方"引用来源"可展开看前后文，核对依据

想缩小范围就点输入框上方的「整个资料集」，勾选指定文件。

## 支持的文件

**文档**：pdf、docx、doc、md、markdown、txt、epub
**表格**：xlsx、xls、csv
**演示**：pptx、ppt
**网页**：html、htm
**图片**：png、jpg、jpeg、webp、gif、tiff、bmp

几个限制：

- 图片**没有 OCR**，只记录尺寸格式，图里的字搜不到
- 扫描版 PDF 需要自带文字层，否则解析失败
- `.doc` 需 Word 97+，`.xls` 需 Excel 97–2003

## 常见问题

| 现象 | 解决 |
|---|---|
| `Port 5173 is already in use` | 已有一个前端在跑。关掉多余的 `npm run dev`，或改用下面的开发方式，不要同时开 |
| 页面能开但提示"网络异常" | 开发模式下代理指错端口，见下方第 2 条 |
| 后端起不来报密钥错误 | `.env` 里 `CREDENTIAL_ENCRYPTION_KEY` 未填，或不是 base64 编码的 32 字节密钥 |
| 测试连接失败 | Key 错误或额度用完；429 会自动重试 2 次 |
| 上传后一直"处理中" | 点该行「重试」；或在 `.env` 设 `INGESTION_MODE=worker` |
| 上传失败 | 展开看原因：加密文件、扫描件、格式不支持（改了后缀的文件会被拒） |

## 改代码时

Docker 只跑数据库和后端，前端本地启动以支持热更新：

```powershell
docker compose up -d db backend

cd frontend
Copy-Item .env.example .env.local
```

把 `.env.local` 里的代理改成容器端口：

```dotenv
VITE_PROXY_TARGET=http://127.0.0.1:8002
```

```powershell
npm install
npm run dev
```

**两种方式只能选一种**，否则 5173 端口冲突。

## 测试

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/unit -q

cd frontend
npm run lint; npm test; npm run build
```

集成测试需要独立测试库（会重建表结构，别指向自己的资料库）：

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://qa:qa@localhost:5432/document_qa_test"
.\.venv\Scripts\python.exe -m pytest tests/integration -q
```

## 调整检索策略

`.env` 里有几个实验开关，改完重启后端才生效：

```dotenv
RETRIEVAL_MODE=hybrid      # vector / keyword / hybrid
RERANK_STRATEGY=auto       # auto / off / llm
DIVERSITY_ENABLED=true     # MMR 多样性排序
EVIDENCE_EXPANSION_ROUNDS=1
```

对照实验的跑法与指标见 [评测说明](docs/evaluation.md)。

## 技术栈

前端 React 18 + TypeScript + Tailwind；后端 FastAPI + SQLAlchemy；数据库 PostgreSQL 16 + pgvector；检索为向量召回 + jieba BM25，经 RRF 融合后可选重排。

```text
backend/app/     FastAPI 应用
backend/tests/   单元与集成测试
frontend/src/    React 页面与组件
evaluation/      评测脚本与数据
docs/            需求、设计、API、部署文档
storage/         上传原件（不提交）
```

## 文档

[产品需求](docs/PRD.md) · [系统设计](docs/system-design.md) · [API 契约](docs/api.md) · [评测说明](docs/evaluation.md) · [部署说明](docs/deployment.md) · [目录规范](docs/project-structure.md)
