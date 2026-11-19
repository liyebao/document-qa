import logging
from logging.handlers import RotatingFileHandler

from app.core.config import get_settings

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_configured = False


def configure_logging() -> None:
    """统一日志格式；业务代码不得记录 API Key、密码或文档正文。

    同时写 stdout 和 logs/backend.log：检索轨迹（retrieval_trace）需要落盘，
    离线评测脚本才能按 conversation_id 关联到具体问题。
    """
    global _configured
    if _configured:
        return

    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        log_dir = get_settings().log_dir
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                log_dir / "backend.log",
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
        )
    except OSError:
        # 目录不可写时保留控制台输出，不能因为日志配置让服务起不来。
        logging.getLogger(__name__).warning("日志目录不可写，仅输出到控制台")

    logging.basicConfig(level=logging.INFO, format=_LOG_FORMAT, handlers=handlers)
    _configured = True
