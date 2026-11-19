"""独立入库 worker：从 processing_jobs 领取任务并执行解析与索引。

用法（在 backend 目录执行）：
    python -m app.worker
"""
import logging
import os
import signal
import socket
import threading
import time
import uuid

from sqlalchemy import func, update

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.models.processing_job import JOB_STATUS_RUNNING, ProcessingJob
from app.services import ingestion, jobs

logger = logging.getLogger(__name__)

_stop = False
# 大文件入库可能远超锁超时；处理期间定期续期，避免被 reap_stale 误判为死任务。
_HEARTBEAT_SECONDS = 30


def _start_heartbeat(job_id: uuid.UUID) -> threading.Event:
    """后台线程定期刷新 locked_at；收到停止信号或任务结束时退出。"""
    stop = threading.Event()

    def beat() -> None:
        while not stop.wait(_HEARTBEAT_SECONDS):
            db = SessionLocal()
            try:
                db.execute(
                    update(ProcessingJob)
                    .where(
                        ProcessingJob.id == job_id,
                        ProcessingJob.status == JOB_STATUS_RUNNING,
                    )
                    .values(locked_at=func.now())
                )
                db.commit()
            except Exception:  # noqa: BLE001  心跳失败不能让任务直接中断
                db.rollback()
                logger.warning("任务心跳更新失败 job_id=%s", job_id)
            finally:
                db.close()

    thread = threading.Thread(
        target=beat, name=f"job-heartbeat-{job_id}", daemon=True
    )
    thread.start()
    return stop


def _handle_signal(signum: int, frame: object) -> None:
    global _stop
    _stop = True
    logger.info("收到停止信号，等待当前任务结束后退出")


def _run_once(worker_id: str) -> bool:
    db = SessionLocal()
    try:
        jobs.reap_stale(db, get_settings().worker_lock_timeout_seconds)
        job = jobs.claim_next(db, worker_id)
    finally:
        db.close()

    if job is None:
        return False

    heartbeat = _start_heartbeat(job.id)
    try:
        ingestion.run_ingestion(job.document_id)
    except Exception as exc:  # noqa: BLE001  失败要写回任务表
        logger.exception("任务失败 job_id=%s document_id=%s", job.id, job.document_id)
        db = SessionLocal()
        try:
            current = db.get(ProcessingJob, job.id)
            if current is not None:
                jobs.mark_failed(db, current, str(exc))
        finally:
            db.close()
    else:
        db = SessionLocal()
        try:
            current = db.get(ProcessingJob, job.id)
            if current is not None:
                jobs.mark_succeeded(db, current)
        finally:
            db.close()
    finally:
        heartbeat.set()

    return True


def main() -> None:
    configure_logging()
    settings = get_settings()
    worker_id = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    logger.info("入库 worker 启动 id=%s", worker_id)

    while not _stop:
        try:
            worked = _run_once(worker_id)
        except Exception:  # noqa: BLE001  单次异常不能让 worker 退出
            logger.exception("worker 循环异常")
            worked = False
        if not worked:
            time.sleep(settings.worker_poll_seconds)

    logger.info("入库 worker 退出 id=%s", worker_id)


if __name__ == "__main__":
    main()
