"""Юнит-тесты utils/datetime_utils."""

from datetime import datetime, timedelta, timezone

import pytest

from utils.datetime_utils import is_time_expired, timestamp_now, utc_now

pytestmark = pytest.mark.unit


def test_utc_now_returns_utc():
    dt = utc_now()
    assert dt.tzinfo is not None
    assert dt.utcoffset().total_seconds() == 0


def test_timestamp_now_is_int():
    ts = timestamp_now()
    assert isinstance(ts, int)
    assert ts > 0


def test_timestamp_now_close_to_real():
    import time

    ts = timestamp_now()
    assert abs(ts - int(time.time())) <= 2


def test_is_time_expired_past():
    past = utc_now() - timedelta(seconds=1)
    assert is_time_expired(past) is True


def test_is_time_expired_future():
    future = utc_now() + timedelta(seconds=60)
    assert is_time_expired(future) is False


def test_is_time_expired_exact_boundary():
    # Практически сейчас: может быть True или False в зависимости от наносекунд.
    # Важно — не бросает исключений.
    dt = datetime.now(timezone.utc)
    result = is_time_expired(dt)
    assert isinstance(result, bool)
