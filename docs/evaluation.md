# 评测说明

| 项目 | 内容 |
|---|---|
| 文档版本 | v1.2 |
| 状态 | 评测脚本、Recall@K/MRR 轨迹分析与示例数据集已建立；日志自动落盘，报告可自动补齐检索指标；尚未在真实资料上运行，不提供任何效果结论 |

## 1. 评测集格式

`evaluation/dataset.example.jsonl` 每行一个 JSON 对象，字段如下：

| 字段 | 必填 | 说明 |
|---|---|---|
| `question` | 是 | 用户问题 |
| `category` | 否 | 单文件事实题、精确匹配题、跨文件比较题、组合/多跳题、无答案题 |
| `expected_refusal` | 否 | 是否预期拒答，默认 `false` |
| `expected_points` | 否 | 预期答案要点的字符串列表，用于粗略命中统计 |
| `expected_evidence` | 否 | 预期支持片段或文件的人工标注说明 |
| `expected_files` | 否 | 预期支持该问题的文件名列表，用于文件级 Recall@K/MRR |
| `expected_chunk_ids` | 否 | 预期片段的 UUID 列表，用于片段级 Recall@K/MRR；可从数据库或检索轨迹中人工标注 |

示例数据集只演示格式，不代表真实资料。`expected_files` 必须与上传后的文件名一致（大小写不敏感）；`expected_chunk_ids` 可以为空，此时只统计文件级指标。

## 2. 指标定义

实现见 `evaluation/metrics.py`：

- **拒答准确性**：有答案问题未拒绝、无答案问题正确拒绝的比例。
- **引用存在率**：预期可回答的问题中，至少返回一条引用的比例。
- **答案要点命中率**：预期要点字符串出现在回答中的比例；仅作为人工核对前的粗略指标。
- **Recall@5 / Recall@10**：轨迹融合排名前 K 个文件中是否至少命中一个 `expected_files`，按文件计算；同时支持 `expected_chunk_ids` 的片段级指标。
- **MRR**：第一个命中文件/片段的排名倒数；没有命中记 0。
- **人工核对项**：引用是否指向真实片段和正确页码/章节、结论是否被引用支持、冲突资料是否分别展示。
- Recall@K/MRR 由 `analyze_traces.py` 基于实际轨迹计算；尚未在真实资料上统计，不能把未统计的指标写成结果。

## 3. 检索轨迹日志

每次问答会向后端日志输出一行 `retrieval_trace` 结构化 JSON，包含：

- 会话 ID、资料集 ID、检索问题数量
- Agent 工具调用轮数、工具实际检索次数、总检索次数
- 使用的 Embedding / 回答服务商与模型标识
- 每个检索问题的向量候选 chunk_id、关键词候选 chunk_id、RRF 融合结果与分数
- 融合候选中每个片段的 chunk_id、document_id、文件名，用于计算文件级 Recall@K/MRR
- 最终进入上下文的片段 ID、被引用的片段 ID
- 复合问题各子问题是否有片段进入上下文
- 计数类问题的全文补证条数（`full_scan_chunks`）与按编号补证条数（`reference_chunks`，含其它文件的同一编号、同一文件里被分页切开的后续片段）；后者用于核对「资料里明明有这条，回答却说无法确认」的情况
- 检索耗时、回答耗时、回答状态（`completed`、`insufficient`、`failed`）与错误码

轨迹不记录资料正文、用户问题和 API Key，但会记录文件名和 chunk/document ID；如果文件名本身敏感，请在脱敏后的资料集上评测。

后端启动时会同时写入控制台和 `logs/backend.log`（5 MB 轮转、保留 3 份），容器内通过 `LOG_DIR=/app/logs` 挂载到宿主 `./logs`。`run_evaluation.py` 默认读取该日志，按 `conversation_id` 自动把报告中的题目与轨迹关联，补齐文件级/片段级 Recall 与 MRR；日志不存在时只输出提示，不会伪造指标。也可以对已有报告单独重算：

```powershell
backend\.venv\Scripts\python evaluation\analyze_traces.py `
  --log logs\backend.log `
  --report evaluation\reports\<运行报告>.json
```

脚本输出 `<时间>-trace-<报告名>.json/.md`，并按召回模式与重排策略分组。

## 4. 运行方式

先启动后端并准备一个已建立索引的资料集。单用户模式无需登录：

```powershell
cd backend
.\.venv\Scripts\python ..\evaluation\run_evaluation.py `
  --collection-id <资料集 UUID> `
  --dataset ..\evaluation\dataset.example.jsonl
```

脚本会为每道题创建独立会话，记录 `conversation_id`、实际回答、状态、引用以及 `expected_files` / `expected_chunk_ids`，输出到 `evaluation/reports/<时间>-api-<数据集>.json` 与同名 `.md`。随后用 `analyze_traces.py` 计算检索指标。

## 5. 问法鲁棒性评测

`evaluation/paraphrase_cases.json` 按「意图」组织用例：同一意图下面挂多条问法（同义改写、语序调整、术语替换、口语化、中英文混用、全角数字等），每条用例声明期望的意图指纹与预期事实。

意图指纹由 `app/services/query_intent.py` 生成，格式为 `意图|编号|项号`（如 `content|第七十一条|第二项`、`count`、`last`）。同一意图的所有问法必须得到同一个指纹，这是「换一种问法仍走同一条检索路径」的可直接断言版本。

先做不调用模型的归一化检查（可放进 CI）：

```powershell
cd backend
.\.venv\Scripts\python ..\evaluation\evaluate_paraphrases.py --offline
```

再做真实接口评测（每个问法单独开会话，避免上下文影响结论）：

```powershell
cd backend
.\.venv\Scripts\python ..\evaluation\evaluate_paraphrases.py `
  --base-url http://127.0.0.1:8002 `
  --collection-id <资料集 UUID>
```

报告输出到 `evaluation/reports/<时间>-paraphrase.json` 与同名 `.md`，指标口径：

| 指标 | 含义 |
|---|---|
| 意图稳定性 | 所有问法归一到期望指纹的比例 |
| 作答率 | 状态正常且没有落入「无法确认」的比例 |
| 要点命中率 | 回答包含该意图预期事实的比例 |
| 文件覆盖 | 预期文件都出现在引用里的比例 |
| 引用稳定性 | 与首个问法的引用集合 Jaccard 均值 |
| 回答稳定性 | 与首个问法的回答字符二元组 Jaccard 均值 |

只报告本次实际运行的数据；新增资料或修改提示词后需要重跑并保留新旧报告。

## 6. 记录要求

- 报告只写本次实际运行的环境、结果与失败案例。
- 修改切片长度、候选数量、RRF 参数、提示词或模型后，需要重新运行并保留新旧报告。
- 不得把外部文章的准确率、阈值或延迟写入本项目结论。
- 评测材料中的个人资料与 Key 不得提交到 Git（`evaluation/reports/` 已忽略，仅保留 `.gitkeep`）。
