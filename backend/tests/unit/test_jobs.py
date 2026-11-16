from datetime import timedelta

from app.services.jobs import backoff_delay


def test_backoff_grows_then_caps() -> None:
    assert backoff_delay(1) == timedelta(minutes=1)
    assert backoff_delay(2) == timedelta(minutes=4)
    assert backoff_delay(3) == timedelta(minutes=16)
    assert backoff_delay(4) == timedelta(minutes=60)
    assert backoff_delay(10) == timedelta(minutes=60)
