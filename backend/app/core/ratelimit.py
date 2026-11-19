import time
from collections import defaultdict, deque
from collections.abc import Callable
from threading import Lock

from app.core.config import get_settings
from app.core.errors import AppError


class SlidingWindowLimiter:
    """单进程滑动窗口限流。

    MVP 使用内置内存计数，适合单实例部署；多 worker/多实例时需要替换为
    Redis 等共享存储，否则每个进程各自计数。
    """

    def __init__(
        self,
        limit: int,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()
        self._last_cleanup = clock()

    def hit(self, key: str) -> None:
        if self._limit <= 0:
            return
        now = self._clock()
        with self._lock:
            queue = self._events[key]
            while queue and now - queue[0] >= self._window:
                queue.popleft()
            if len(queue) >= self._limit:
                raise AppError("RATE_LIMITED", "请求过于频繁，请稍后再试", 429)
            queue.append(now)
            self._cleanup(now)

    def reset(self) -> None:
        with self._lock:
            self._events.clear()
            self._last_cleanup = self._clock()

    def _cleanup(self, now: float) -> None:
        if now - self._last_cleanup < self._window:
            return
        expired = [
            key
            for key, queue in self._events.items()
            if not queue or now - queue[-1] >= self._window
        ]
        for key in expired:
            self._events.pop(key, None)
        self._last_cleanup = now


def _build_limiters() -> tuple[
    SlidingWindowLimiter, SlidingWindowLimiter, SlidingWindowLimiter
]:
    settings = get_settings()
    return (
        SlidingWindowLimiter(settings.rate_limit_ask_per_minute),
        SlidingWindowLimiter(settings.rate_limit_upload_per_minute),
        SlidingWindowLimiter(settings.rate_limit_reindex_per_minute),
    )


ask_limiter, upload_limiter, reindex_limiter = _build_limiters()
settings_limiter = SlidingWindowLimiter(
    get_settings().rate_limit_settings_per_minute
)
