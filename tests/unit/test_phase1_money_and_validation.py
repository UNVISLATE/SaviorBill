"""Unit-тесты для Фазы 1: Валидация логина, возврат бонусов, суммы платежей и payment_url."""

from decimal import Decimal
from types import SimpleNamespace
import pytest
from pydantic import ValidationError

from schemas.auth import Reg
from schemas.user import UserCreateAdmin
from schemas.payments import Payment
from models.user_services import UserServicesMngr
from models.user_payments import UserPaymentsModel


@pytest.mark.unit
def test_login_validation_accepts_latin_cyrillic_digits():
    valid_logins = [
        "ivan_123",
        "Иван_123",
        "user-name.test",
        "Пользователь.1",
        "admin-user",
        "Ёлка-2026",
    ]
    for login in valid_logins:
        reg = Reg(login=login, password="password123")
        assert reg.login == login

        admin_create = UserCreateAdmin(login=login, password="password123")
        assert admin_create.login == login


@pytest.mark.unit
def test_login_validation_rejects_email_and_colons():
    invalid_logins = [
        "user@mail.com",
        "google:12345",
        "user name",
        "user/slash",
        "user\\slash",
        "ab",  # < 3
        "user!name",
        "user#hash",
    ]
    for login in invalid_logins:
        with pytest.raises(ValidationError):
            Reg(login=login, password="password123")

        with pytest.raises(ValidationError):
            UserCreateAdmin(login=login, password="password123")


@pytest.mark.unit
def test_charge_and_refund_bonus_split_integrity():
    """Тест исключения отмывания бонусов: бонусы и баланс списываются и возвращаются строго в своих долях."""
    acc = SimpleNamespace(
        id=1,
        bonus_balance=Decimal("30.00"),
        balance=Decimal("70.00"),
    )

    # Покупка на 50: 30 с бонусов, 20 с основного баланса
    from_bonus, from_balance = UserServicesMngr._charge(acc, Decimal("50.00"))
    assert from_bonus == Decimal("30.00")
    assert from_balance == Decimal("20.00")
    assert acc.bonus_balance == Decimal("0.00")
    assert acc.balance == Decimal("50.00")

    # Возврат: 30 должно вернуться в bonus_balance, 20 — в balance
    UserServicesMngr._refund(acc, from_bonus, from_balance)
    assert acc.bonus_balance == Decimal("30.00")
    assert acc.balance == Decimal("70.00")


@pytest.mark.unit
def test_payment_url_extraction_and_schema():
    """Тест извлечения и нормализации payment_url в модели и публичной схеме."""
    m = UserPaymentsModel(
        id=10,
        account_id=1,
        provider="test_prov",
        amount=Decimal("150.00"),
        currency="RUB",
        status="pending",
        target="service",
        public_data={"pay_url": "https://gateway.example.test/pay/abc123xyz"},
        created_at=None,
    )
    assert m.payment_url == "https://gateway.example.test/pay/abc123xyz"

    # Преобразование в Pydantic схему
    p = Payment(
        id=m.id,
        provider=m.provider,
        amount=m.amount,
        currency=m.currency,
        status=m.status,
        target=m.target,
        public_data=m.public_data,
        payment_url=m.payment_url,
        created_at="2026-10-21T00:00:00Z",
    )
    assert p.payment_url == "https://gateway.example.test/pay/abc123xyz"
