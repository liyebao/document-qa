import base64
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 宿主机结构是 <项目>/backend/app/core/config.py，项目根在 parents[3]；
# 容器里是 /app/app/core/config.py，没有 backend 这一层，parents[3] 会落到 /，
# 使 storage/uploads 这类相对路径解析到容器内非挂载区——重启后文件全部丢失。
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = (
    _BACKEND_ROOT.parent if _BACKEND_ROOT.name == "backend" else _BACKEND_ROOT
)


class Settings(BaseSettings):
    """后端运行时配置，全部来自环境变量或仓库根目录的 .env。"""

    model_config = SettingsConfigDict(
        env_file=(".env", str(PROJECT_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "个人知识库问答助手"
    database_url: str = "postgresql+psycopg://qa:qa@localhost:5432/document_qa"

    credential_encryption_key: str = ""
    credential_key_version: int = 1

    # 单进程内存限流，按用户计数；设为 0 可关闭。
    rate_limit_ask_per_minute: int = 30
    rate_limit_upload_per_minute: int = 30
    rate_limit_reindex_per_minute: int = 3
    # 模型配置写入会触发真实计费调用（连接测试），单独限流，避免脚本刷爆。
    rate_limit_settings_per_minute: int = 30

    upload_dir: Path = PROJECT_ROOT / "storage" / "uploads"
    # 检索轨迹等日志的落盘目录；容器内用 LOG_DIR=/app/logs。
    log_dir: Path = PROJECT_ROOT / "logs"
    max_upload_mb: int = 100

    # 本地 Ollama 的 OpenAI 兼容地址；Docker 部署时设为
    # http://host.docker.internal:11434/v1，本地开发保持 localhost。
    ollama_base_url: str = "http://localhost:11434/v1"

    # inline：上传请求内用后台任务处理；worker：写入 processing_jobs 由独立进程消费。
    ingestion_mode: Literal["inline", "worker"] = "inline"
    worker_poll_seconds: float = 2.0
    worker_lock_timeout_seconds: int = 600
    job_max_attempts: int = 3
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    retrieval_candidates: int = 20
    retrieval_top_k: int = 5
    rrf_k: int = 60
    # 召回组合：hybrid=向量+关键词后 RRF 融合；vector / keyword 用于消融对照实验。
    retrieval_mode: Literal["hybrid", "vector", "keyword"] = "hybrid"
    # RRF 之后进入重排的候选数量；未配置重排模型时该参数不生效。
    rerank_candidates: int = 15
    # 重排策略：auto=配置了 rerank 模型才重排；off=关闭（消融对照基线）；
    # llm=用回答模型做二元证据判证，不依赖 rerank 服务商。
    rerank_strategy: Literal["auto", "off", "llm"] = "auto"
    # 多样性排序：MMR 抑制同一文件的相邻片段占满上下文，余量按分数回补。
    diversity_enabled: bool = True
    mmr_lambda: float = 0.7
    mmr_max_per_document: int = 2
    # 证据驱动扩展：从已命中片段抽取术语再检索，弥补问题与原文用词不一致的漏召回。
    evidence_expansion_rounds: int = 1
    evidence_expansion_terms: int = 2
    agent_max_tool_rounds: int = 3
    agent_max_tool_calls: int = 6

    chunk_target_tokens: int = 800
    chunk_min_tokens: int = 600
    chunk_overlap_tokens: int = 80

    # 本地 Ollama 首次加载模型可能超过 60 秒，默认给足时间。
    model_http_timeout: float = 180.0
    # 只对 429/5xx 与连接层异常重试；免费额度常见的瞬时限流不必整单失败。
    model_max_retries: int = 2
    embedding_batch_size: int = 16

    @field_validator("upload_dir")
    @classmethod
    def _resolve_upload_dir(cls, value: Path) -> Path:
        if not value.is_absolute():
            value = PROJECT_ROOT / value
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    def validate_runtime_secrets(self) -> None:
        """启动时检查关键密钥，缺失时直接失败，避免带病运行。"""
        if not self.credential_encryption_key:
            raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY 未配置，请参考 .env.example")
        try:
            key = base64.urlsafe_b64decode(self.credential_encryption_key)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "CREDENTIAL_ENCRYPTION_KEY 必须是 base64 编码的 32 字节密钥"
            ) from exc
        if len(key) != 32:
            raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY 必须是 base64 编码的 32 字节密钥")


@lru_cache
def get_settings() -> Settings:
    return Settings()
