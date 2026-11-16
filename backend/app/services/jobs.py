"""基于 PostgreSQL 的入库任务队列。"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.models.processing_job import (
    ACTIVE_JOB_STATUSES,
    JOB_KIND_INGEST,
    JOB_STATUS_FAILED,
    JOB_STATUS_PENDING,
    JOB_STATUS_RUNNING,
    JOB_STATUS_SUCCEEDED,
    ProcessingJob,
)

_BACKOFF_MINUTES = (1, 4, 16, 60)


def backoff_delay(attempts: int) -> timedelta:
    """第 N 次失败后的等待时间：1、4、16、60 分钟。"""
    index = min(max(attempts - 1, 0), len(_BACKOFF_MINUTES) - 1)
    return timedelta(minutes=_BACKOFF_MINUTES[index])


def enqueue(
    db: Session,
    document_id: uuid.UUID,
    *,
    kind: str = JOB_KIND_INGEST,
    max_attempts: int = 3,
) -> ProcessingJob:
    """同一文档的同类任务已在排队或执行时不重复入队。"""
    existing = db.scalar(
        select(ProcessingJob).where(
            ProcessingJob.document_id == document_id,
            ProcessingJob.kind == kind,
            ProcessingJob.status.in_(ACTIVE_JOB_STATUSES),
        )
    )
    if existing is not None:
        return existing
    job = ProcessingJob(
        document_id=document_id,
        kind=kind,
        max_attempts=max_attempts,
    )
    db.add(job)
    db.flush()
    return job


_CLAIM_SQL = text(
    """
    UPDATE processing_jobs
    SET status = 'running',
        locked_by = :worker_id,
        locked_at = now(),
        attempts = attempts + 1,
        updated_at = now()
    WHERE id = (
        SELECT id
        FROM processing_jobs
        WHERE status = 'pending'
          AND kind = :kind
          AND run_after <= now()
        ORDER BY run_after
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING id
    """
)


def claim_next(
    db: Session, worker_id: str, *, kind: str = JOB_KIND_INGEST
) -> ProcessingJob | None:
    """原子领取一个待处理任务；多 worker 并发时不会重复。"""
    row = db.execute(_CLAIM_SQL, {"worker_id": worker_id, "kind": kind}).first()
    db.commit()
    if row is None:
        return None
    job = db.get(ProcessingJob, row[0])
    if job is not None:
        # Core UPDATE 不会同步 ORM 身份映射，显式刷新避免读到旧的 pending 状态。
        db.refresh(job)
    return job


def mark_succeeded(db: Session, job: ProcessingJob) -> None:
    job.status = JOB_STATUS_SUCCEEDED
    job.locked_by = None
    job.locked_at = None
    job.last_error = None
    db.commit()


def mark_failed(db: Session, job: ProcessingJob, error: str) -> None:
    """未达上限时退避重试，达到上限后置为 failed。"""
    job.last_error = (error or "")[:1000]
    job.locked_by = None
    job.locked_at = None
    if job.attempts >= job.max_attempts:
        job.status = JOB_STATUS_FAILED
    else:
        job.status = JOB_STATUS_PENDING
        job.run_after = datetime.now(UTC) + backoff_delay(job.attempts)
    db.commit()


def reap_stale(db: Session, timeout_seconds: int) -> int:
    """把执行超时的任务重新放回队列，避免 worker 崩溃后任务永久卡住。"""
    cutoff = datetime.now(UTC) - timedelta(seconds=timeout_seconds)
    result = db.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.status == JOB_STATUS_RUNNING,
            ProcessingJob.locked_at.is_not(None),
            ProcessingJob.locked_at < cutoff,
        )
        .values(
            status=JOB_STATUS_PENDING,
            locked_by=None,
            locked_at=None,
            run_after=datetime.now(UTC),
        )
    )
    db.commit()
    return result.rowcount or 0
