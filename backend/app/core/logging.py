import logging


def configure_logging() -> None:
    """统一日志格式；业务代码不得记录 API Key、密码或文档正文。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
