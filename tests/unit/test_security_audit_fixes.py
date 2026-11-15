import pytest
from decimal import Decimal
from pydantic import ValidationError
from starlette.testclient import TestClient

from app import app
from schemas.auth import MePatch, PassResetRequest
from schemas.payments import PaymentCreate
from schemas.promo import PromoCatalogCreate, PromoCodeBatch
from schemas.types import normalize_email
from schemas.user import BalanceAdjust, UserCreateAdmin, UserPatch
from schemas.app_tokens import AppTokenCreate
from schemas.service import ServicePatch


def test_norm_email_validation():
    # Valid emails
    assert normalize_email("user@gmail.com") == "user@gmail.com"
    assert normalize_email("  A.B-C@Domain.CO.UK  ") == "a.b-c@domain.co.uk"
    assert normalize_email(None) is None
    assert normalize_email("") is None

    # Invalid emails
    for invalid in [
        "not-an-email",
        "user@localhost",
        "user@domain.com, hidden@evil.com",
        "user@domain.com\r\nbcc: evil@evil.com",
        "user@domain.com\0",
        "@nodomain.com",
        "user@",
    ]:
        with pytest.raises(ValueError):
            normalize_email(invalid)


def test_pass_reset_request_rejects_invalid_email():
    with pytest.raises(ValidationError):
        PassResetRequest(email="not-an-email")


def test_payment_create_schema_validation():
    # Valid balance
    p1 = PaymentCreate(provider="sbp", target="balance", amount=Decimal("100"))
    assert p1.target == "balance"

    # Valid service
    p2 = PaymentCreate(provider="sbp", target="service", service_id=42)
    assert p2.target == "service"

    # Invalid target
    with pytest.raises(ValidationError):
        PaymentCreate(provider="sbp", target="invalid_target", amount=Decimal("100"))

    # Balance without amount
    with pytest.raises(ValidationError):
        PaymentCreate(provider="sbp", target="balance")

    # Service without service_id
    with pytest.raises(ValidationError):
        PaymentCreate(provider="sbp", target="service")


def test_user_patch_and_create_boundary_validation():
    # Negative balance rejected
    with pytest.raises(ValidationError):
        UserPatch(balance=Decimal("-10"))

    # Negative bonus balance rejected
    with pytest.raises(ValidationError):
        UserPatch(bonus_balance=Decimal("-5"))

    # Invalid role_id (< 1) rejected
    with pytest.raises(ValidationError):
        UserPatch(role_id=0)

    with pytest.raises(ValidationError):
        UserCreateAdmin(login="testuser", password="password123", role_id=0)


def test_balance_adjust_rejects_zero_and_nan():
    # Zero amount rejected
    with pytest.raises(ValidationError):
        BalanceAdjust(amount=Decimal("0"), kind="main", reason="test")

    # NaN rejected
    with pytest.raises(ValidationError):
        BalanceAdjust(amount=Decimal("NaN"), kind="main", reason="test")


def test_me_patch_login_regex():
    # Valid login
    assert MePatch(login="valid_login-123").login == "valid_login-123"

    # Invalid login (spaces, special chars)
    with pytest.raises(ValidationError):
        MePatch(login="invalid login with spaces")

    with pytest.raises(ValidationError):
        MePatch(login="invalid$char")


def test_promo_catalog_validation():
    # Negative value rejected
    with pytest.raises(ValidationError):
        PromoCatalogCreate(name="Test", slug="test-promo", kind="bonus", value=Decimal("-50"))

    # Percent discount > 100 rejected
    with pytest.raises(ValidationError):
        PromoCatalogCreate(
            name="Test",
            slug="test-promo",
            kind="discount",
            discount_type="percent",
            value=Decimal("101"),
        )

    # Valid percent discount
    p = PromoCatalogCreate(
        name="Test",
        slug="test-promo",
        kind="discount",
        discount_type="percent",
        value=Decimal("50"),
    )
    assert p.value == Decimal("50")


def test_promo_code_batch_validation():
    # Invalid code length in batch rejected
    with pytest.raises(ValidationError):
        PromoCodeBatch(catalog_id=1, codes=["a"])  # < 2 chars

    # Negative catalog_id rejected
    with pytest.raises(ValidationError):
        PromoCodeBatch(catalog_id=0, count=10)


def test_service_patch_validation():
    # Negative price rejected
    with pytest.raises(ValidationError):
        ServicePatch(price=Decimal("-10"))

    # Empty name rejected
    with pytest.raises(ValidationError):
        ServicePatch(name="")

    # Invalid catalog_id (< 1) rejected
    with pytest.raises(ValidationError):
        ServicePatch(catalog_id=0)


def test_app_token_create_ip_allowlist_validation():
    # Valid IPs and CIDRs
    t = AppTokenCreate(
        name="Test Token",
        ip_allowlist=["192.168.1.1", "10.0.0.0/24", "2001:db8::/32"],
    )
    assert len(t.ip_allowlist) == 3

    # Invalid IP string rejected
    with pytest.raises(ValidationError):
        AppTokenCreate(name="Test Token", ip_allowlist=["not-an-ip"])


def test_request_tracker_middleware_rejects_oversized_payload():
    client = TestClient(app)
    # Content-length > 16MB (e.g. 20MB)
    response = client.post(
        "/api/health",
        headers={"Content-Length": str(20 * 1024 * 1024)},
        content=b"x",
    )
    assert response.status_code == 413
    assert "Payload too large" in response.text
