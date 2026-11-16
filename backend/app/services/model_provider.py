import json
import logging
import random
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.secrets import decrypt_secret, encrypt_secret, mask_secret
from app.models.model_provider_config import (
    CONFIG_STATUS_CONFIGURED,
    CONFIG_STATUS_ERROR,
    CONFIG_STATUS_OK,
    ModelProviderConfig,
)
from app.models.user import User
from app.schemas.settings import (
    ConnectionTestResult,
    EffectiveModelOut,
    ModelProviderConfigCreate,
    ModelProviderConfigOut,
    ModelProviderSettingsOut,
    ProviderInfo,
)

logger = logging.getLogger(__name__)

# 只重试明确的临时故障：限流、服务端错误、连接层异常。参数类 4xx 立即失败。
_RETRY_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
_RETRY_BACKOFF_SECONDS = (0.5, 2.0, 8.0)

_client: httpx.Client | None = None
_client_lock = threading.Lock()


@dataclass(frozen=True)
class ProviderSpec:
    key: str
    label: str
    base_url: str
    embedding_models: tuple[str, ...]
    chat_models: tuple[str, ...]
    requires_api_key: bool = True
    # 服务商单次 Embedding 请求的批量上限；应用会取它与全局批大小的较小值。
    max_embedding_batch: int = 16
    # 请求 Embedding 时显式指定的维度；None 表示使用服务商默认维度。
    embedding_dimensions: int | None = None
    # 支持的重排模型；为空表示该服务商不提供 rerank 接口。
    rerank_models: tuple[str, ...] = ()
    rerank_path: str = "/rerank"


# 服务商地址只允许来自后端白名单，避免用户输入任意 URL。
PROVIDERS: dict[str, ProviderSpec] = {
    "openai": ProviderSpec(
        key="openai",
        label="OpenAI",
        base_url="https://api.openai.com/v1",
        embedding_models=("text-embedding-3-small", "text-embedding-3-large"),
        chat_models=(
            "gpt-4.1-mini",
            "gpt-4.1",
            "gpt-4o-mini",
            "gpt-5.1",
            "gpt-5",
            "gpt-5-mini",
        ),
        max_embedding_batch=2048,
    ),
    "dashscope": ProviderSpec(
        key="dashscope",
        label="阿里云百炼（DashScope）",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        embedding_models=("text-embedding-v4", "text-embedding-v3"),
        chat_models=(
            "qwen-max",
            "qwen-plus",
            "qwen-flash",
            "qwen3.8-max",
            "qwen3.7-max",
            "qwen3.7-plus",
            "qwen3.8-flash",
            "qwen3-coder-plus",
        ),
        max_embedding_batch=10,
    ),
    "siliconflow": ProviderSpec(
        key="siliconflow",
        label="硅基流动（SiliconFlow）",
        base_url="https://api.siliconflow.cn/v1",
        # bge-large-zh-v1.5 单条输入上限只有 512 token，低于本项目的切片长度，
        # 会在长片段入库时失败，因此不作为可选模型。
        embedding_models=("BAAI/bge-m3",),
        chat_models=(
            "deepseek-ai/DeepSeek-V4.1-Flash",
            "deepseek-ai/DeepSeek-V4-Pro",
            "Qwen/Qwen3-235B-A22B-Instruct-2507",
            "Qwen/Qwen3-32B",
            "Qwen/Qwen3-8B",
        ),
        max_embedding_batch=16,
        rerank_models=("BAAI/bge-reranker-v2-m3",),
    ),
    "deepseek": ProviderSpec(
        key="deepseek",
        label="DeepSeek",
        base_url="https://api.deepseek.com/v1",
        embedding_models=(),
        chat_models=(
            "deepseek-flash",
            "deepseek-v4-pro",
        ),
    ),
    "zhipu": ProviderSpec(
        key="zhipu",
        label="智谱 AI",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        embedding_models=("embedding-3",),
        chat_models=(
            "glm-5.1",
            "glm-5",
            "glm-5-turbo",
            "glm-4.6",
            "glm-4.5",
            "glm-4-flash",
        ),
        max_embedding_batch=64,
        embedding_dimensions=1024,
    ),
    "ollama": ProviderSpec(
        key="ollama",
        label="本地 Ollama",
        base_url="http://localhost:11434/v1",
        embedding_models=("bge-m3", "qwen3-embedding:0.6b", "nomic-embed-text"),
        chat_models=(
            "qwen3:4b",
            "qwen3:8b",
            "qwen3:14b",
            "qwen3:32b",
            "deepseek-r1:8b",
            "deepseek-r1:14b",
            "llama3.3:70b",
            "gemma3:12b",
            "qwen2.5:7b",
        ),
        requires_api_key=False,
        max_embedding_batch=1,
    ),
}


def list_providers() -> list[ProviderInfo]:
    return [
        ProviderInfo(
            key=spec.key,
            label=spec.label,
            embedding_models=list(spec.embedding_models),
            chat_models=list(spec.chat_models),
            rerank_models=list(spec.rerank_models),
            requires_api_key=spec.requires_api_key,
        )
        for spec in PROVIDERS.values()
    ]


def get_provider_spec(provider_key: str) -> ProviderSpec:
    spec = PROVIDERS.get(provider_key)
    if spec is None:
        raise AppError("UNSUPPORTED_PROVIDER", "不支持该模型服务商", 422)
    if provider_key == "ollama":
        # 本地开发用 localhost；Docker 部署通过 OLLAMA_BASE_URL 指向宿主机。
        configured = get_settings().ollama_base_url.strip().rstrip("/")
        if configured and configured != spec.base_url:
            return replace(spec, base_url=configured)
    return spec


def _mask_ciphertext(ciphertext: str, key_version: int) -> str:
    try:
        return mask_secret(decrypt_secret(ciphertext, key_version))
    except Exception:  # noqa: BLE001  主密钥变更后仍要能展示配置状态
        # 不抛错是为了不影响列表展示，但必须留下线索：通常是主密钥已轮换。
        logger.warning(
            "模型配置密钥解密失败，key_version=%s；请检查 CREDENTIAL_ENCRYPTION_KEY 是否已轮换",
            key_version,
        )
        return "****"


def serialize_config(
    config: ModelProviderConfig,
    *,
    preferred_embedding: str | None = None,
    preferred_chat: str | None = None,
) -> ModelProviderConfigOut:
    return ModelProviderConfigOut(
        id=config.id,
        provider_key=config.provider_key,
        embedding_model=config.embedding_model,
        chat_model=config.chat_model,
        rerank_model=config.rerank_model or "",
        status=config.status,
        key_masked=_mask_ciphertext(config.api_key_ciphertext, config.key_version),
        last_tested_at=config.last_tested_at,
        updated_at=config.updated_at,
        is_embedding_default=config.provider_key == preferred_embedding,
        is_chat_default=config.provider_key == preferred_chat,
    )


def list_configs(db: Session, user: User) -> list[ModelProviderConfigOut]:
    configs = db.scalars(
        select(ModelProviderConfig)
        .where(ModelProviderConfig.user_id == user.id)
        .order_by(ModelProviderConfig.updated_at.desc())
    ).all()
    return [
        serialize_config(
            item,
            preferred_embedding=user.preferred_embedding_provider,
            preferred_chat=user.preferred_chat_provider,
        )
        for item in configs
    ]


def _effective_model(
    config: ModelProviderConfig | None, model: str | None
) -> EffectiveModelOut | None:
    if config is None or not model:
        return None
    spec = PROVIDERS.get(config.provider_key)
    return EffectiveModelOut(
        config_id=config.id,
        provider_key=config.provider_key,
        provider_label=spec.label if spec else config.provider_key,
        model=model,
    )


def build_settings(db: Session, user: User) -> ModelProviderSettingsOut:
    embedding = preferred_embedding_config(db, user.id)
    chat = preferred_chat_config(db, user.id)
    rerank = preferred_rerank_config(db, user.id)
    return ModelProviderSettingsOut(
        providers=list_providers(),
        configs=list_configs(db, user),
        preferred_embedding_provider=user.preferred_embedding_provider,
        preferred_chat_provider=user.preferred_chat_provider,
        effective_embedding=_effective_model(
            embedding, embedding.embedding_model if embedding else None
        ),
        effective_chat=_effective_model(chat, chat.chat_model if chat else None),
        effective_rerank=_effective_model(
            rerank, rerank.rerank_model if rerank else None
        ),
    )


def get_user_config(
    db: Session, user_id: uuid.UUID, provider_key: str
) -> ModelProviderConfig | None:
    return db.scalar(
        select(ModelProviderConfig).where(
            ModelProviderConfig.user_id == user_id,
            ModelProviderConfig.provider_key == provider_key,
        )
    )


def latest_config(db: Session, user_id: uuid.UUID) -> ModelProviderConfig | None:
    return db.scalar(
        select(ModelProviderConfig)
        .where(ModelProviderConfig.user_id == user_id)
        .order_by(ModelProviderConfig.updated_at.desc())
        .limit(1)
    )


def latest_embedding_config(
    db: Session, user_id: uuid.UUID
) -> ModelProviderConfig | None:
    """只选择配置了 Embedding 模型的服务商，跳过 DeepSeek 这类仅回答模型。"""
    return db.scalar(
        select(ModelProviderConfig)
        .where(
            ModelProviderConfig.user_id == user_id,
            ModelProviderConfig.embedding_model != "",
        )
        .order_by(ModelProviderConfig.updated_at.desc())
        .limit(1)
    )


def get_preferred_config(
    db: Session, user_id: uuid.UUID, role: str
) -> ModelProviderConfig | None:
    """读取用户显式选择的检索/回答服务商；未选择或配置缺失时返回 None。"""
    user = db.get(User, user_id)
    if user is None:
        return None
    provider_key = (
        user.preferred_embedding_provider
        if role == "embedding"
        else user.preferred_chat_provider
    )
    if not provider_key:
        return None
    config = get_user_config(db, user_id, provider_key)
    if config is None:
        return None
    if role == "embedding" and not config.embedding_model:
        return None
    return config


def preferred_embedding_config(
    db: Session, user_id: uuid.UUID
) -> ModelProviderConfig | None:
    return get_preferred_config(db, user_id, "embedding") or latest_embedding_config(
        db, user_id
    )


def preferred_chat_config(db: Session, user_id: uuid.UUID) -> ModelProviderConfig | None:
    return get_preferred_config(db, user_id, "chat") or latest_config(db, user_id)


def preferred_rerank_config(
    db: Session, user_id: uuid.UUID
) -> ModelProviderConfig | None:
    """重排跟随回答服务商；若它没有配置重排模型，则退到最近配置过的服务商。"""
    config = get_preferred_config(db, user_id, "chat") or latest_config(db, user_id)
    if config is not None and config.rerank_model:
        return config
    return db.scalar(
        select(ModelProviderConfig)
        .where(
            ModelProviderConfig.user_id == user_id,
            ModelProviderConfig.rerank_model != "",
        )
        .order_by(ModelProviderConfig.updated_at.desc())
        .limit(1)
    )


def set_preferred_provider(
    db: Session, user: User, config_id: uuid.UUID, role: str
) -> ModelProviderSettingsOut:
    config = db.scalar(
        select(ModelProviderConfig).where(
            ModelProviderConfig.id == config_id,
            ModelProviderConfig.user_id == user.id,
        )
    )
    if config is None:
        raise AppError("NOT_FOUND", "模型服务配置不存在", 404)
    if role == "embedding":
        if not config.embedding_model:
            raise AppError(
                "MODEL_NOT_CONFIGURED", "该服务商没有配置 Embedding 模型", 422
            )
        user.preferred_embedding_provider = config.provider_key
    else:
        user.preferred_chat_provider = config.provider_key
    db.commit()
    db.refresh(user)
    return build_settings(db, user)


def upsert_config(
    db: Session, user: User, payload: ModelProviderConfigCreate
) -> ModelProviderConfigOut:
    spec = get_provider_spec(payload.provider_key)
    embedding_model = (payload.embedding_model or "").strip() or None
    chat_model = (payload.chat_model or "").strip() or None
    rerank_model = (payload.rerank_model or "").strip()
    if rerank_model and rerank_model not in spec.rerank_models:
        raise AppError("UNSUPPORTED_PROVIDER", "该服务商不支持所选重排模型", 422)
    if embedding_model and not spec.embedding_models:
        raise AppError("UNSUPPORTED_PROVIDER", "该服务商不提供 Embedding 模型", 422)
    if payload.role in ("embedding", "both") and not spec.embedding_models:
        raise AppError("UNSUPPORTED_PROVIDER", "该服务商不提供 Embedding 模型", 422)
    if not spec.chat_models:
        raise AppError("UNSUPPORTED_PROVIDER", "该服务商没有可用的回答模型", 422)
    config = get_user_config(db, user.id, payload.provider_key)
    if config is None:
        if spec.requires_api_key and not payload.api_key:
            raise AppError("API_KEY_REQUIRED", "首次保存时必须填写 API Key", 422)
        # 本地服务不需要真实 Key，用占位值加密保存，避免空密文
        ciphertext, key_version = encrypt_secret(payload.api_key or "local-no-key")
        default_embedding = spec.embedding_models[0] if spec.embedding_models else ""
        if payload.role == "chat" and not embedding_model:
            # 回答专用配置不顺便写入 Embedding 模型，避免被自动选为检索配置。
            default_embedding = ""
        config = ModelProviderConfig(
            user_id=user.id,
            provider_key=payload.provider_key,
            api_key_ciphertext=ciphertext,
            key_version=key_version,
            embedding_model=embedding_model or default_embedding,
            chat_model=chat_model or spec.chat_models[0],
            rerank_model=rerank_model,
            status=CONFIG_STATUS_CONFIGURED,
        )
        db.add(config)
    else:
        if payload.api_key:
            ciphertext, key_version = encrypt_secret(payload.api_key)
            config.api_key_ciphertext = ciphertext
            config.key_version = key_version
        if embedding_model:
            config.embedding_model = embedding_model
        if chat_model:
            config.chat_model = chat_model
        if payload.rerank_model is not None:
            config.rerank_model = rerank_model
        config.status = CONFIG_STATUS_CONFIGURED

    if payload.role in ("embedding", "both"):
        if not config.embedding_model:
            raise AppError(
                "MODEL_NOT_CONFIGURED", "该服务商没有可用的 Embedding 模型", 422
            )
        user.preferred_embedding_provider = config.provider_key
    if payload.role in ("chat", "both"):
        user.preferred_chat_provider = config.provider_key
    if payload.role is None:
        # 未指定用途时，首次保存自动成为默认；之后不抢占已有选择。
        if user.preferred_embedding_provider is None and config.embedding_model:
            user.preferred_embedding_provider = config.provider_key
        if user.preferred_chat_provider is None:
            user.preferred_chat_provider = config.provider_key
    db.commit()
    db.refresh(config)
    db.refresh(user)
    return serialize_config(
        config,
        preferred_embedding=user.preferred_embedding_provider,
        preferred_chat=user.preferred_chat_provider,
    )


def delete_config(db: Session, user: User, config_id: uuid.UUID) -> None:
    config = db.scalar(
        select(ModelProviderConfig).where(
            ModelProviderConfig.id == config_id,
            ModelProviderConfig.user_id == user.id,
        )
    )
    if config is None:
        raise AppError("NOT_FOUND", "模型服务配置不存在", 404)
    provider_key = config.provider_key
    db.delete(config)
    if user.preferred_embedding_provider == provider_key:
        user.preferred_embedding_provider = None
    if user.preferred_chat_provider == provider_key:
        user.preferred_chat_provider = None
    db.commit()


def _safe_provider_error(spec: ProviderSpec, response: httpx.Response, api_key: str) -> str:
    message = ""
    try:
        body = response.json()
        error = body.get("error") if isinstance(body, dict) else None
        if isinstance(error, dict):
            message = str(error.get("message", ""))
        elif isinstance(error, str):
            message = error
    except ValueError:
        message = ""
    if not message:
        message = f"HTTP {response.status_code}"
    message = message.replace(api_key, "***")[:200]
    return f"{spec.label} 返回错误：{message}"


def _http_client() -> httpx.Client:
    """模块级复用的连接池，避免每批 embedding、每次提问都重新握一次 TCP+TLS。"""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = httpx.Client(
                    limits=httpx.Limits(max_connections=16, max_keepalive_connections=8)
                )
    return _client


def close_http_client() -> None:
    """应用退出时释放连接池，避免 keep-alive 连接悬挂到进程结束。"""
    global _client
    with _client_lock:
        if _client is not None:
            _client.close()
            _client = None


def _max_attempts() -> int:
    return max(1, get_settings().model_max_retries + 1)


def _sleep_backoff(attempt: int) -> None:
    """指数退避加少量抖动，避免多个并发请求在同一时刻重试。"""
    base = _RETRY_BACKOFF_SECONDS[min(attempt, len(_RETRY_BACKOFF_SECONDS) - 1)]
    time.sleep(base + random.uniform(0, 0.2))


def _auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def _post_json(spec: ProviderSpec, api_key: str, path: str, payload: dict) -> dict:
    settings = get_settings()
    url = f"{spec.base_url}{path}"
    headers = _auth_headers(api_key)
    attempts = _max_attempts()
    for attempt in range(attempts):
        last_attempt = attempt + 1 >= attempts
        try:
            response = _http_client().post(
                url, headers=headers, json=payload, timeout=settings.model_http_timeout
            )
        except httpx.TimeoutException as exc:
            if not last_attempt:
                _sleep_backoff(attempt)
                continue
            raise AppError(
                "MODEL_PROVIDER_ERROR",
                f"{spec.label} 响应超时，本地模型可能正在加载；请稍后重试或增大 MODEL_HTTP_TIMEOUT",
                504,
            ) from exc
        except httpx.HTTPError as exc:
            if not last_attempt:
                _sleep_backoff(attempt)
                continue
            raise AppError(
                "MODEL_PROVIDER_ERROR", f"无法连接 {spec.label}，请检查网络后重试", 502
            ) from exc

        if response.status_code >= 400:
            if response.status_code in _RETRY_STATUS_CODES and not last_attempt:
                logger.warning(
                    "%s 返回 %s，第 %s 次重试", spec.label, response.status_code, attempt + 1
                )
                _sleep_backoff(attempt)
                continue
            raise AppError(
                "MODEL_PROVIDER_ERROR", _safe_provider_error(spec, response, api_key), 502
            )
        try:
            return response.json()
        except ValueError as exc:
            raise AppError(
                "MODEL_PROVIDER_ERROR", f"{spec.label} 返回了无法解析的响应", 502
            ) from exc
    raise AppError("MODEL_PROVIDER_ERROR", f"{spec.label} 请求失败", 502)  # pragma: no cover


def request_embeddings(
    spec: ProviderSpec, api_key: str, model: str, texts: list[str]
) -> list[list[float]]:
    payload: dict = {"model": model, "input": texts}
    if spec.embedding_dimensions is not None:
        payload["dimensions"] = spec.embedding_dimensions
    body = _post_json(spec, api_key, "/embeddings", payload)
    data = body.get("data")
    if not isinstance(data, list) or len(data) != len(texts):
        raise AppError("MODEL_PROVIDER_ERROR", f"{spec.label} 返回的向量数量不正确", 502)
    ordered = sorted(data, key=lambda item: item.get("index", 0))
    vectors: list[list[float]] = []
    for item in ordered:
        embedding = item.get("embedding")
        if not isinstance(embedding, list) or not embedding:
            raise AppError("MODEL_PROVIDER_ERROR", f"{spec.label} 返回的向量格式不正确", 502)
        vectors.append([float(value) for value in embedding])
    return vectors


def request_rerank(
    spec: ProviderSpec,
    api_key: str,
    model: str,
    query: str,
    documents: list[str],
    top_n: int,
) -> list[tuple[int, float]]:
    """调用服务商 rerank 接口，返回 (原始下标, 相关性分数)。"""
    if not spec.rerank_models:
        raise AppError("UNSUPPORTED_PROVIDER", "该服务商不支持重排模型", 422)
    payload = {
        "model": model,
        "query": query,
        "documents": documents,
        "top_n": max(1, min(top_n, len(documents))),
    }
    body = _post_json(spec, api_key, spec.rerank_path, payload)
    results = body.get("results")
    if not isinstance(results, list):
        raise AppError("MODEL_PROVIDER_ERROR", f"{spec.label} 返回的重排结果格式不正确", 502)
    parsed: list[tuple[int, float]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        index = item.get("index")
        score = item.get("relevance_score")
        if isinstance(index, int) and isinstance(score, int | float):
            parsed.append((index, float(score)))
    if not parsed:
        raise AppError("MODEL_PROVIDER_ERROR", f"{spec.label} 未返回有效的重排结果", 502)
    return parsed


def _is_reasoning_model(spec: ProviderSpec, model: str) -> bool:
    """OpenAI 推理模型使用 max_completion_tokens，且不接受 temperature。"""
    return spec.key == "openai" and model.lower().startswith(
        ("gpt-5", "gpt-6", "o1", "o3", "o4")
    )


def _chat_payload(
    spec: ProviderSpec,
    model: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
) -> dict:
    reasoning = _is_reasoning_model(spec, model)
    payload: dict = {"model": model, "messages": messages}
    if reasoning:
        # 推理模型把思考 token 也算进输出预算；给足预算避免只返回 reasoning_content。
        payload["max_completion_tokens"] = 4096
    else:
        payload["max_tokens"] = max_tokens
        payload["temperature"] = temperature
    # DeepSeek V4 默认开启思考模式；问答不需要长思考，关闭后可避免工具调用限制和额外计费。
    if spec.key == "deepseek":
        payload["thinking"] = {"type": "disabled"}
    # 硅基流动的 Qwen3 默认开启思考；关闭后更符合短问答和工具调用场景。
    if (
        spec.key == "siliconflow"
        and model.startswith("Qwen/Qwen3")
        and "Instruct" not in model
    ):
        payload["enable_thinking"] = False
    # Qwen3.7/3.8 默认高强度思考；RAG 短回答关闭思考，避免 1200 token 预算被思维链吃光。
    if spec.key == "dashscope" and model.startswith(("qwen3.8", "qwen3.7")):
        payload["reasoning_effort"] = "none"
    return payload


def chat_completion(
    spec: ProviderSpec,
    api_key: str,
    model: str,
    messages: list[dict],
    *,
    temperature: float = 0.2,
    max_tokens: int = 1200,
) -> str:
    body = _post_json(
        spec,
        api_key,
        "/chat/completions",
        _chat_payload(spec, model, messages, temperature, max_tokens),
    )
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AppError("MODEL_PROVIDER_ERROR", f"{spec.label} 未返回回答内容", 502)
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise AppError("MODEL_PROVIDER_ERROR", f"{spec.label} 未返回回答内容", 502)
    return content.strip()


def chat_completion_stream(
    spec: ProviderSpec,
    api_key: str,
    model: str,
    messages: list[dict],
    *,
    temperature: float = 0.2,
    max_tokens: int = 1200,
) -> Iterator[str]:
    """流式读取 OpenAI 兼容的 SSE 响应，只产出正文增量。

    重试只覆盖"建立连接 + 首响应状态码"：一旦开始产出正文就不再重试，
    否则会把已经展示给用户的半截回答重放一遍。
    """
    settings = get_settings()
    payload = _chat_payload(spec, model, messages, temperature, max_tokens)
    payload["stream"] = True
    url = f"{spec.base_url}/chat/completions"
    headers = _auth_headers(api_key)
    attempts = _max_attempts()
    client = _http_client()

    for attempt in range(attempts):
        last_attempt = attempt + 1 >= attempts
        try:
            request = client.build_request(
                "POST",
                url,
                headers=headers,
                json=payload,
                timeout=settings.model_http_timeout,
            )
            response = client.send(request, stream=True)
        except httpx.TimeoutException as exc:
            if not last_attempt:
                _sleep_backoff(attempt)
                continue
            raise AppError(
                "MODEL_PROVIDER_ERROR",
                f"{spec.label} 响应超时，本地模型可能正在加载；请稍后重试或增大 MODEL_HTTP_TIMEOUT",
                504,
            ) from exc
        except httpx.HTTPError as exc:
            if not last_attempt:
                _sleep_backoff(attempt)
                continue
            raise AppError(
                "MODEL_PROVIDER_ERROR", f"无法连接 {spec.label}，请检查网络后重试", 502
            ) from exc

        try:
            if response.status_code >= 400:
                response.read()
                if response.status_code in _RETRY_STATUS_CODES and not last_attempt:
                    logger.warning(
                        "%s 流式返回 %s，第 %s 次重试",
                        spec.label,
                        response.status_code,
                        attempt + 1,
                    )
                    _sleep_backoff(attempt)
                    continue
                raise AppError(
                    "MODEL_PROVIDER_ERROR",
                    _safe_provider_error(spec, response, api_key),
                    502,
                )
            try:
                yield from _iter_sse_content(response)
            except httpx.HTTPError as exc:
                raise AppError(
                    "MODEL_PROVIDER_ERROR", f"{spec.label} 连接中断，请稍后重试", 502
                ) from exc
            return
        finally:
            response.close()


def _iter_sse_content(response: httpx.Response) -> Iterator[str]:
    for line in response.iter_lines():
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            return
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue
        choices = chunk.get("choices")
        if not isinstance(choices, list) or not choices:
            continue
        delta = choices[0].get("delta") if isinstance(choices[0], dict) else None
        content = delta.get("content") if isinstance(delta, dict) else None
        if isinstance(content, str) and content:
            yield content


def chat_with_tools(
    spec: ProviderSpec,
    api_key: str,
    model: str,
    messages: list[dict],
    tools: list[dict],
    *,
    temperature: float = 0.2,
    max_tokens: int = 1200,
) -> dict:
    """返回原始 assistant message，可能包含 tool_calls。

    工具定义由调用方提供；用户、资料集、文件状态等权限条件始终由后端注入，
    本函数不解析、也不信任模型给出的范围参数。
    """
    payload = _chat_payload(spec, model, messages, temperature, max_tokens)
    payload["tools"] = tools
    payload["tool_choice"] = "auto"
    body = _post_json(spec, api_key, "/chat/completions", payload)
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AppError("MODEL_PROVIDER_ERROR", f"{spec.label} 未返回回答内容", 502)
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise AppError("MODEL_PROVIDER_ERROR", f"{spec.label} 返回的回答格式不正确", 502)
    return message


def test_connection(
    db: Session,
    user: User,
    config_id: uuid.UUID,
    role: str | None = None,
) -> ConnectionTestResult:
    config = db.scalar(
        select(ModelProviderConfig).where(
            ModelProviderConfig.id == config_id,
            ModelProviderConfig.user_id == user.id,
        )
    )
    if config is None:
        raise AppError("NOT_FOUND", "模型服务配置不存在", 404)
    if role == "embedding" and not config.embedding_model:
        raise AppError("MODEL_NOT_CONFIGURED", "该服务商没有配置 Embedding 模型", 422)
    if role == "chat" and not config.chat_model:
        raise AppError("MODEL_NOT_CONFIGURED", "该服务商没有配置回答模型", 422)

    spec = get_provider_spec(config.provider_key)
    api_key = decrypt_secret(config.api_key_ciphertext, config.key_version)

    test_embedding = role in (None, "embedding")
    test_chat = role in (None, "chat")
    embedding_tested = bool(config.embedding_model) and test_embedding
    embedding_ok = False
    chat_ok = False
    messages: list[str] = []
    if embedding_tested:
        try:
            # 不止验证 HTTP 200：同时验证批量输入、向量数量和维度一致性。
            probe_texts = [
                f"连接测试 {index}" for index in range(min(2, spec.max_embedding_batch))
            ]
            vectors = request_embeddings(
                spec, api_key, config.embedding_model, probe_texts
            )
            if not vectors:
                raise AppError("MODEL_PROVIDER_ERROR", "Embedding 未返回向量", 502)
            dimension = len(vectors[0])
            if dimension == 0 or any(
                len(vector) != dimension for vector in vectors
            ):
                raise AppError(
                    "MODEL_PROVIDER_ERROR", "Embedding 返回的向量维度不一致", 502
                )
            embedding_ok = True
            indexed = dimension in {768, 1024, 1536, 3072}
            messages.append(
                f"Embedding 服务正常（{dimension} 维，"
                f"{'已建立 HNSW 索引' if indexed else '精确扫描'}）"
            )
        except AppError as exc:
            messages.append(f"Embedding 服务连接失败：{exc.message}")
    elif test_embedding:
        messages.append("该服务商未配置 Embedding，跳过 Embedding 测试")

    if test_chat:
        try:
            chat_completion(
                spec,
                api_key,
                config.chat_model,
                [{"role": "user", "content": "请只回复：连接成功"}],
                temperature=0,
                # 推理模型会先消耗 token 输出 reasoning_content；本地 qwen3
                # 的思考较长，256 会被思考全部吃光，导致 content 为空。
                max_tokens=512 if spec.key == "ollama" else 256,
            )
            chat_ok = True
            messages.append("回答模型连接正常")
        except AppError as exc:
            messages.append(f"回答模型连接失败：{exc.message}")

    ok = (embedding_ok if embedding_tested else True) and (
        chat_ok if test_chat else True
    )
    config.status = CONFIG_STATUS_OK if ok else CONFIG_STATUS_ERROR
    config.last_tested_at = datetime.now(UTC)
    db.commit()
    return ConnectionTestResult(
        ok=ok,
        embedding_ok=embedding_ok,
        chat_ok=chat_ok,
        message="；".join(messages),
    )
