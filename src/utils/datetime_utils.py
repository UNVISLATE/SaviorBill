from datetime import datetime, timezone


def utc_now():
    """Текущее время в UTC"""
    return datetime.now(timezone.utc)


def timestamp_now() -> int:
    """Текущий Unix timestamp"""
    return int(utc_now().timestamp())


def is_time_expired(expiry_time: datetime) -> bool:
    """Истекло ли время"""
    return expiry_time < utc_now()
