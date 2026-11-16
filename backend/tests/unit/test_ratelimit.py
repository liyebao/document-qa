import pytest

from app.core.errors import AppError
from app.core.ratelimit import SlidingWindowLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_limiter_blocks_after_limit_and_recovers_after_window() -> None:
    clock = FakeClock()
    limiter = SlidingWindowLimiter(2, window_seconds=60, clock=clock)

    limiter.hit("user")
    limiter.hit("user")
    with pytest.raises(AppError) as exc:
        limiter.hit("user")
    assert exc.value.code == "RATE_LIMITED"
    assert exc.value.status_code == 429

    clock.advance(61)
    limiter.hit("user")


def test_limiter_isolated_by_key() -> None:
    clock = FakeClock()
    limiter = SlidingWindowLimiter(1, window_seconds=60, clock=clock)
    limiter.hit("a")
    limiter.hit("b")
    with pytest.raises(AppError):
        limiter.hit("a")


def test_limiter_can_be_disabled_or_reset() -> None:
    clock = FakeClock()
    limiter = SlidingWindowLimiter(0, window_seconds=60, clock=clock)
    limiter.hit("user")

    enabled = SlidingWindowLimiter(1, window_seconds=60, clock=clock)
    enabled.hit("user")
    enabled.reset()
    enabled.hit("user")
