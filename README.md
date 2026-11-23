# 面向个人多文件资料的知识库问答系统

一个本地运行的问答网站：把你的 PDF、Word、网页等资料放进去，然后用中文提问。系统会从资料里找证据，流式给出回答，并在句末标出 `[1]` 这样的引用编号——点一下就能打开原文对应位置。资料里没有答案时，它会明确说"当前资料无法确认"，不会瞎编。

> 毕业设计项目。本地单用户，不需要注册登录。

---

## 一、开始之前要准备什么

| 准备项 | 说明 | 没有怎么办 |
|---|---|---|
| **Docker Desktop** | 一键启动数据库和后端 | 没有 Docker 就走[本机开发方式](#六不用-docker-的开发方式)，需要自己装 PostgreSQL 16 + pgvector |
| **一个模型服务商的 API Key** | 系统靠它把文字转成向量、生成回答 | 也可以用本地 Ollama，不用 Key；配置方法见[模型配置说明](#25-第-5-步配置模型最关键) |
| **浏览器** | Chrome / Edge 都可以 | 需要支持网页内打开 PDF |

不需要提前装 Python 或 Node——Docker 方式会把这些打包好。

---

## 二、第一次运行（5 步，约 10 分钟）

### 2.1 第 1 步：复制配置文件

在项目根目录（`D:\毕业设计\毕设`）打开 PowerShell，执行：

```powershell
Copy-Item .env.example .env
```

这会生成你的私人配置文件 `.env`。**它不会上传到仓库**，里面会存密钥。

### 2.2 第 2 步：填两个密钥

用记事本打开刚生成的 `.env`。如果没有 `JWT_SECRET` 这一行，就在文件末尾**新增**下面两行；如果已经有，就把等号右边替换掉：

```dotenv
JWT_SECRET=随便写一段至少32个字符的随机文字
CREDENTIAL_ENCRYPTION_KEY=粘贴下面命令生成的字符串
```

生成 `CREDENTIAL_ENCRYPTION_KEY`（二选一）：

```powershell
# 有 Python 时
python -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"

# 没有 Python，纯 PowerShell
[Convert]::ToBase64String([byte[]](1..32 | ForEach-Object { Get-Random -Minimum 0 -Maximum 256 }))
```

> **为什么要做这一步？** `JWT_SECRET` 用来签登录状态，`CREDENTIAL_ENCRYPTION_KEY` 用来加密你后面填的模型 API Key。不填的话后端会拒绝启动，这是故意的——避免密钥明文落盘。

### 2.3 第 3 步：一键启动

```powershell
docker compose up --build
```

第一次会下载镜像和安装依赖，需要等几分钟。看到后端和前端都显示 `healthy` 或 `started` 就成功了。

> 如果以前没用过 Docker：这条命令会同时启动 4 个容器——数据库、后端、任务进程、前端。所有数据都存在本机的 `storage/` 和数据库卷里。

### 2.4 第 4 步：打开页面

浏览器访问：

```
http://127.0.0.1:5173
```

看到"我的资料集"页面就说明跑起来了。

> **端口 5173 被占用？** 说明你本机还开着一个 `npm run dev`。两种方式只能选一个：要么关掉本机的（找到那个终端按 Ctrl+C），要么用本机开发方式（见第六节），不要同时跑。

### 2.5 第 5 步：配置模型（最关键）

点击左侧 **模型服务**，然后：

1. 选择服务商（OpenAI / 阿里云百炼 / 智谱 / 硅基流动 / DeepSeek / 本地 Ollama）
2. 填入 API Key（Ollama 不用填）
3. 角色选 **两者**（表示同一个服务既做检索向量、又做回答生成）
4. 点 **保存配置**，再点 **测试连接**
5. 顶部绿色提示显示成功即可

> **为什么要做这一步？** 系统本身不带模型。向量化资料需要"检索模型"，生成答案需要"回答模型"。两者可以不同服务商，但第一次建议都用同一个，省事。
>
> 测试连接会消耗一点点服务商额度，属于正常现象。

---

## 三、第一次提问（4 步）

### 3.1 第 1 步：新建资料集

回到"我的资料集"页面，点 **新建资料集**，起个名字，比如"数据库课程资料"。

> 资料集就是一个文件夹。不同主题的资料分开放，提问时检索更准。

### 3.2 第 2 步：上传文件

进入刚建的资料集，点 **上传**，选择文件。支持 PDF、Word、Markdown、Excel、PPT 等，见[支持的文件格式](#五支持哪些文件)。

上传后文件状态会从"处理中"变成"就绪"。几百页的 PDF 可能要等十几秒。

> 还可以用"粘贴文本"和"网页链接导入"两种方式添加资料。

### 3.3 第 3 步：等状态变成"就绪"

如果显示"失败"，点该行的 **重试** 或展开看失败原因。常见原因是文件加密、扫描件没有文字层，或模型配置不对。

### 3.4 第 4 步：提问并核对引用

点开资料集里的会话，输入问题，比如"什么是左外连接？"。

- 回答会一个字一个字地流出来
- 句末的 `[1]` 是引用编号，**点它就能打开原文对应页**
- 下方"引用来源"可以展开看前后文
- 如果资料里没有答案，它会说"当前资料无法确认"

> 想缩小范围时，点输入框上方的"整个资料集"按钮，勾选指定文件即可。

---

## 四、遇到问题先看这里

| 现象 | 原因 | 怎么办 |
|---|---|---|
| `Port 5173 is already in use` | Docker 前端和本机 `npm run dev` 抢同一个端口 | 二选一：关掉本机 dev，或只用本机方式（第六节） |
| 页面能开，但提示"网络异常" | 本机 dev 的代理指错了后端端口 | `frontend/.env.local` 里改 `VITE_PROXY_TARGET=http://127.0.0.1:8001`，重启 dev |
| 后端起不来，报密钥错误 | 第 2 步的两个密钥没填或太短 | 重新生成并填写，`JWT_SECRET` 至少 32 字符 |
| 测试连接失败 | API Key 错误、额度用完、网络不通 | 换 Key 或换服务商；系统对 429 会自动重试 2 次 |
| 上传图片后搜不到图中文字 | 系统没有 OCR | 图片只入库元信息（尺寸、格式），图像里的字无法检索 |
| 扫描版 PDF 处理失败 | 没有文字层，又没有 OCR | 用 OCR 软件先转成可复制文字的 PDF |
| 回答偶尔换措辞 | 检索词由模型自主生成，每次可能不同 | 已把回答温度固定为 0；要完全可复现需关闭 Agent 自主检索与证据扩展（见 `.env.example`） |
| 上传后一直是"处理中" | 默认 `inline` 模式，重启会中断任务 | 点重试；或在 `.env` 设 `INGESTION_MODE=worker` 并重启容器 |

---

## 五、支持哪些文件

| 类别 | 格式 |
|---|---|
| 文档 | `pdf`、`docx`、`doc`、`md`、`markdown`、`txt`、`epub` |
| 表格 | `xlsx`、`xls`、`csv` |
| 演示 | `pptx`、`ppt` |
| 网页 | `html`、`htm` |
| 图片 | `png`、`jpg`、`jpeg`、`webp`、`gif`、`tiff`、`bmp` |

上传时会校验文件头（不只看扩展名），改了后缀的假文件会被拒绝。

几个边界：

- 图片**没有 OCR**，只记录格式、尺寸、色彩模式、大小；图中的文字搜不到
- 扫描版 PDF 需要本身带文字层，否则解析失败
- `.doc` 只支持 Word 97 及以后；`.xls` 只支持 Excel 97–2003（BIFF8）；更早版本会明确拒绝并建议另存为新格式
- EPUB 不支持 DRM，也没有页码，引用会显示章节名
- 文本类文件支持 UTF-8 和 GB18030 编码

---

## 六、不用 Docker 的开发方式

适合要改代码、想热更新的场景。**注意：此时前端跑在 5173，后端容器暴露在 8001，两者不能搞混。**

### 6.1 启动数据库和后端

```powershell
docker compose up -d db backend
```

### 6.2 启动前端

```powershell
cd frontend
Copy-Item .env.example .env.local
```

编辑 `.env.local`，把代理改成容器暴露的端口：

```dotenv
VITE_PROXY_TARGET=http://127.0.0.1:8001
```

然后启动：

```powershell
npm install
npm run dev
```

打开 `http://127.0.0.1:5173`。

> `vite.config.ts` 设了 `strictPort: true`，端口被占用会直接报错，不会自动换端口。

### 6.3 完全不用 Docker

需要本机安装 PostgreSQL 16 + pgvector，然后按 `.env` 里的 `DATABASE_URL` 配好连接，其余步骤见 [部署说明第 5 节](docs/deployment.md)。

---

## 七、测试与评测

### 7.1 跑测试

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/unit -q
```

集成测试需要独立的测试库（会重建表结构，**不要指向你的资料库**）：

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://qa:qa@localhost:5432/document_qa_test"
.\.venv\Scripts\python.exe -m pytest tests/integration -q
```

前端：

```powershell
cd frontend
npm run lint
npm test
npm run build
```

### 7.2 检索质量评测

方法、指标和对照方案（A0–A4）见 [评测说明](docs/evaluation.md)。

- `evaluation/run_evaluation.py`：跑问题集，记录回答、引用与拒答
- `evaluation/analyze_traces.py`：读取 `retrieval_trace` 日志算 Recall@K、MRR、nDCG

当前样例数据集只有 6 条，`expected_chunk_ids` 为空，chunk 级指标暂时是 `None`。要做正式评测需要先补充带标注的问题集。

---

## 八、想了解实现再看这一节

### 8.1 技术栈

- 前端：React 18、Vite、TypeScript、Tailwind CSS、react-markdown
- 后端：Python 3.12、FastAPI、SQLAlchemy 2、Psycopg
- 数据库：PostgreSQL 16 + pgvector（HNSW 索引 + pg_trgm）
- 检索：向量召回 + jieba 分词 BM25 → RRF 融合 → 可选 rerank → MMR 多样性排序
- 模型：用户自配 OpenAI 兼容服务（OpenAI / 百炼 / 智谱 / 硅基流动 / DeepSeek / 本地 Ollama）

### 8.2 目录结构

```text
backend/app/          FastAPI 应用（api / schemas / services / models）
backend/alembic/      数据库迁移
backend/tests/        单元测试与集成测试
backend/scripts/      运维脚本
frontend/src/         React 页面、组件与 API 客户端
evaluation/           评测脚本、轨迹分析、样例数据
docs/                 需求、设计、API、评测、部署文档
storage/              本地上传目录（不提交）
.github/workflows/    CI
```

完整约定见 [目录规范](docs/project-structure.md)，接口见 [API 契约](docs/api.md)。

### 8.3 已知边界

- 不支持扫描件 OCR、图片/音视频理解、复杂表格解析
- 不包含 Celery / Redis / Kafka、多 Agent、管理员后台、生产集群
- 重建索引是同步操作，片段很多时会较慢
- 限流是单进程内存实现，多实例部署需换成共享存储

---

## 九、安全说明

- API Key 用 AES-GCM 加密存储，接口只返回掩码；前端不保存 Key
- 本地单用户不做账号认证，**只监听 `127.0.0.1`，不要暴露到公网**
- 写请求校验 Origin；问答、上传、重建、连接测试都有限流
- 服务商地址来自后端白名单，不能任意填 URL
- 检索在 SQL 层先过滤用户、资料集、文件状态
- 文档正文按不可信数据处理，提示词要求忽略其中的指令
- `.env`、上传原件、数据库卷、评测私有数据不进 Git

---

## 十、完整文档

| 文档 | 内容 |
|---|---|
| [产品需求](docs/PRD.md) | 要做什么、不做什么 |
| [系统设计](docs/system-design.md) | 架构、检索方案、评测计划 |
| [目录规范](docs/project-structure.md) | 文件放哪里、怎么命名 |
| [API 契约](docs/api.md) | 接口定义 |
| [评测说明](docs/evaluation.md) | 指标、数据集、运行方法 |
| [部署说明](docs/deployment.md) | 无 Docker、云数据库等场景 |
| [模型兼容性](docs/model-compatibility.md) | 各服务商的可用模型 |
