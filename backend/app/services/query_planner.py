import json
import logging
import re
import uuid
from pathlib import Path

from app.core.errors import AppError
from app.core.secrets import read_secret
from app.models.message import Message
from app.models.model_provider_config import ModelProviderConfig
from app.services import model_provider

logger = logging.getLogger(__name__)

_COMPOUND_MARKERS = ("分别", "各自", "以及", "同时", "对比", "比较", "异同", "分项", "哪些方面")
_FOLLOW_UP_MARKERS = (
    "它",
    "他",
    "她",
    "其",
    "这个",
    "那个",
    "这些",
    "那些",
    "上述",
    "该",
    "这",
    "那",
    "后来",
    "然后",
    "还有",
    "另外",
    "其中",
    "前者",
    "后者",
    "呢",
    "此",
)

PLANNER_SYSTEM_PROMPT = """你是检索问题整理器。根据最近对话，把用户当前问题改写为可以独立检索的中文问题；
如果当前问题包含多个需要分别检索的子问题，可以拆成最多 4 个检索问题。

规则：
1. 只补全指代和省略信息，不得添加用户没有表达的事实。
2. 不得生成、放宽或覆盖任何权限、用户、资料集或过滤条件。
3. 保持用户原始意图，不回答问题，只输出检索问题。
4. 只输出 JSON，格式为 {"queries": ["问题1", "问题2"]}。"""


def looks_compound(question: str) -> bool:
    return any(marker in question for marker in _COMPOUND_MARKERS)


def looks_followup(question: str) -> bool:
    """只对含指代、省略或承接词的短追问调用改写。

    长问题通常自带完整语境，即使出现“这个/上述”等词也不应继承旧话题；
    直接跳过改写可以降低把新问题错误绑定到上一轮主题的概率。
    """
    text = question.strip()
    if not text or len(text) > 30:
        return False
    return any(marker in text for marker in _FOLLOW_UP_MARKERS)


# 用户可能直接用文件名指代资料，扩展名列表需与 storage 支持的上传格式保持一致。
_FILE_EXTENSION_PATTERN = re.compile(
    r"[\w\u4e00-\u9fff.\-]+\.(?:pdf|docx|doc|pptx|ppt|xlsx|xls|csv|md|markdown|txt"
    # 扩展名后面必须是一个词边界：否则「如何导入.csv文件」里的「导入.csv」会被
    # 当成点名了一个不存在的文件，把整个检索范围清空。
    r"|html|htm|epub|png|jpg|jpeg|webp|gif|tiff|bmp)(?![A-Za-z0-9_\u4e00-\u9fff])",
    re.IGNORECASE,
)


def extract_document_ids(
    question: str, documents: list[tuple[uuid.UUID, str]]
) -> list[uuid.UUID] | None:
    """只提取用户问题中明确写出的文件名，不生成或放宽任何权限条件。

    返回 `None` 表示没有显式文件名条件；返回空列表表示用户写了文件名
    但当前资料集中不存在，此时不应退化为全资料集检索。
    完整文件名直接匹配；也可以匹配长度不少于 4 个字符的文件名主干，
    避免“报告”这类通用词造成误过滤。
    """
    text = question.casefold()
    matched: list[uuid.UUID] = []
    for document_id, filename in documents:
        name = filename.casefold()
        stem = Path(name).stem
        if name and name in text:
            matched.append(document_id)
        elif len(stem) >= 4 and stem in text:
            matched.append(document_id)
    if matched:
        return matched
    for match in _FILE_EXTENSION_PATTERN.finditer(question):
        # 与上面的正向匹配用同一门槛：主干不足 4 个字符时无法与通用词区分，
        # 例如「如何导入.csv文件」「这个.epub打不开」里的「导入.csv」「这个.epub」
        # 不应被当成点名了一个不存在的文件——那会直接把检索结果清空。
        if len(Path(match.group(0)).stem) >= 4:
            return []
    return None


def parse_queries(raw: str, original: str, max_queries: int = 4) -> list[str]:
    """解析规划模型输出；任何异常都回退到原始问题。"""
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return [original]
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return [original]
    queries = data.get("queries") if isinstance(data, dict) else None
    if not isinstance(queries, list):
        return [original]
    result: list[str] = []
    for item in queries:
        if not isinstance(item, str):
            continue
        query = item.strip()
        if not query or len(query) > 300 or query in result:
            continue
        result.append(query)
    return result[:max_queries] or [original]


def _format_history(history: list[Message]) -> str:
    lines: list[str] = []
    for message in history[-6:]:
        role = "用户" if message.role == "user" else "助手"
        lines.append(f"{role}：{message.content[:500]}")
    return "\n".join(lines)


def plan_queries(
    question: str,
    history: list[Message],
    config: ModelProviderConfig | None,
) -> list[str]:
    if config is None:
        return [question]
    needs_planning = looks_compound(question) or (bool(history) and looks_followup(question))
    if not needs_planning:
        return [question]

    history_text = _format_history(history)
    user_content = (
        f"最近对话：\n{history_text}\n\n当前问题：{question}"
        if history_text
        else f"当前问题：{question}"
    )
    try:
        spec = model_provider.get_provider_spec(config.provider_key)
        api_key = read_secret(config.api_key_ciphertext, config.key_version)
        raw = model_provider.chat_completion(
            spec,
            api_key,
            config.chat_model,
            [
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
            max_tokens=300,
        )
    except AppError as exc:
        logger.warning("问题改写失败，回退到原始问题：%s", exc.message)
        return [question]
    return parse_queries(raw, question)
