"""Тесты расширенного сопоставления условий триггеров (Triggers 2.0)."""

import pytest
from decimal import Decimal
from lifecycle.triggers import TriggerDispatcher, TriggerEvent, ALL_EVENTS

pytestmark = pytest.mark.unit


def test_triggers_2_events_registered():
    """Проверка регистрации новых событий Triggers 2.0 в каталоге ALL_EVENTS."""
    new_events = [
        TriggerEvent.ORDER_FAILED,
        TriggerEvent.ORDER_CANCELLED,
        TriggerEvent.USER_BALANCE_CHANGED,
        TriggerEvent.PROMOCODE_APPLIED,
        TriggerEvent.KEY_STOCK_LOW,
    ]
    for ev in new_events:
        assert ev in ALL_EVENTS
        assert isinstance(ev, str)


def test_triggers_match_empty_condition():
    """Пустое условие всегда истинно."""
    assert TriggerDispatcher._match({}, {"order": {"id": 1}}) is True
    assert TriggerDispatcher._match({}, {}) is True


def test_triggers_match_legacy_equality():
    """Сохранение обратной совместимости с простыми условиями {path: expected}."""
    ctx = {
        "order": {
            "id": 100,
            "status": "paid",
            "is_test": True,
        },
        "user": {
            "role": "user",
        },
    }
    assert TriggerDispatcher._match({"order.status": "paid"}, ctx) is True
    assert TriggerDispatcher._match({"order.status": "pending"}, ctx) is False
    assert TriggerDispatcher._match({"order.id": 100, "user.role": "user"}, ctx) is True
    assert TriggerDispatcher._match({"order.is_test": True}, ctx) is True


def test_triggers_match_numeric_operators():
    """Проверка операторов gt, gte, lt, lte с разными числовыми типами."""
    ctx = {
        "order": {
            "amount": Decimal("1500.00"),
            "discount": 50,
            "zero": 0,
        }
    }

    # gt (строго больше)
    assert TriggerDispatcher._match({"order.amount": {"gt": 1000}}, ctx) is True
    assert TriggerDispatcher._match({"order.amount": {"gt": 1500}}, ctx) is False

    # gte (больше или равно)
    assert TriggerDispatcher._match({"order.amount": {"gte": 1500}}, ctx) is True
    assert TriggerDispatcher._match({"order.amount": {"gte": "1500.00"}}, ctx) is True
    assert TriggerDispatcher._match({"order.amount": {"gte": 2000}}, ctx) is False

    # lt / lte (меньше / меньше или равно)
    assert TriggerDispatcher._match({"order.discount": {"lt": 100}}, ctx) is True
    assert TriggerDispatcher._match({"order.discount": {"lt": 50}}, ctx) is False
    assert TriggerDispatcher._match({"order.discount": {"lte": 50}}, ctx) is True

    # Диапазон (комбинация gt и lte в одном поле)
    assert TriggerDispatcher._match({"order.amount": {"gte": 1000, "lte": 2000}}, ctx) is True
    assert TriggerDispatcher._match({"order.amount": {"gt": 1500, "lte": 2000}}, ctx) is False


def test_triggers_match_equality_operators():
    """Проверка операторов eq и ne."""
    ctx = {
        "user": {
            "country": "RU",
            "verified": False,
        }
    }
    assert TriggerDispatcher._match({"user.country": {"eq": "RU"}}, ctx) is True
    assert TriggerDispatcher._match({"user.country": {"ne": "US"}}, ctx) is True
    assert TriggerDispatcher._match({"user.country": {"ne": "RU"}}, ctx) is False
    assert TriggerDispatcher._match({"user.verified": {"eq": False}}, ctx) is True


def test_triggers_match_in_and_not_in():
    """Проверка операторов in и not_in."""
    ctx = {
        "order": {
            "currency": "EUR",
            "status": "failed",
        }
    }
    # Вхождение в список
    assert TriggerDispatcher._match({"order.currency": {"in": ["USD", "EUR", "RUB"]}}, ctx) is True
    assert TriggerDispatcher._match({"order.currency": {"in": ["USD", "GBP"]}}, ctx) is False

    # not_in
    assert TriggerDispatcher._match({"order.status": {"not_in": ["paid", "delivered"]}}, ctx) is True
    assert TriggerDispatcher._match({"order.status": {"not_in": ["failed", "cancelled"]}}, ctx) is False


def test_triggers_match_contains_and_regex():
    """Проверка операторов contains (подстрока/элемент) и regex."""
    ctx = {
        "user": {
            "email": "alex.smith@company.org",
            "tags": ["vip", "beta_tester"],
        },
        "order": {
            "title": "WireGuard Enterprise Gateway #89",
        },
    }

    # contains
    assert TriggerDispatcher._match({"user.tags": {"contains": "vip"}}, ctx) is True
    assert TriggerDispatcher._match({"user.tags": {"contains": "fraud"}}, ctx) is False
    assert TriggerDispatcher._match({"order.title": {"contains": "Enterprise"}}, ctx) is True

    # regex
    assert TriggerDispatcher._match({"user.email": {"regex": r".*@company\.org$"}}, ctx) is True
    assert TriggerDispatcher._match({"user.email": {"regex": r".*@gmail\.com$"}}, ctx) is False
    assert TriggerDispatcher._match({"order.title": {"regex": r"#\d+"}}, ctx) is True
