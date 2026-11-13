"""Unit tests for SMTP enhancements: custom ports, encryption modes, and timeouts."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import aiosmtplib
import pytest
from fastapi import HTTPException

from api.v1.admin.settings.smtp import SmtpTestIn, test_smtp_connection
from core.config import AppConfig
from dependencies.mail import build_mail_svc
from utils.mail import MailSvc


@pytest.mark.unit
@pytest.mark.asyncio
async def test_smtp_custom_port_ssl():
    """Verify custom port (e.g. 9465) with SSL sets use_tls=True and start_tls=False."""
    svc = MailSvc(
        host="smtp.bz",
        port=9465,
        user="test_user",
        password="test_password",
        sender="noreply@example.com",
        encryption="ssl",
        timeout=15.0,
    )

    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        await svc.send("user@example.com", "Subject", "Body")
        assert mock_send.call_count == 1
        _, kwargs = mock_send.call_args
        assert kwargs["hostname"] == "smtp.bz"
        assert kwargs["port"] == 9465
        assert kwargs["use_tls"] is True
        assert kwargs["start_tls"] is False
        assert kwargs["timeout"] == 15.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_smtp_custom_port_starttls():
    """Verify custom port (e.g. 9587) with STARTTLS sets start_tls=True and use_tls=False."""
    svc = MailSvc(
        host="smtp.bz",
        port=9587,
        user="test_user",
        password="test_password",
        sender="noreply@example.com",
        encryption="starttls",
        timeout=10.0,
    )

    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        await svc.send("user@example.com", "Subject", "Body")
        assert mock_send.call_count == 1
        _, kwargs = mock_send.call_args
        assert kwargs["hostname"] == "smtp.bz"
        assert kwargs["port"] == 9587
        assert kwargs["use_tls"] is False
        assert kwargs["start_tls"] is True
        assert kwargs["timeout"] == 10.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_smtp_from_name_and_overrides():
    """Verify from_name and sender overrides in MailSvc."""
    svc = MailSvc(
        host="smtp.example.com",
        port=587,
        user="user",
        password="pwd",
        sender="default@example.com",
        from_name="Default Shop",
        encryption="starttls",
    )

    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        # Default sender & from_name
        await svc.send("user@example.com", "Subject", "Body")
        msg = mock_send.call_args[0][0]
        assert "Default Shop" in msg["From"]
        assert "default@example.com" in msg["From"]

        # Overridden sender & from_name
        await svc.send(
            "user@example.com",
            "Subject",
            "Body",
            sender_override="custom@example.com",
            from_name_override="Custom Store",
        )
        msg_override = mock_send.call_args[0][0]
        assert "Custom Store" in msg_override["From"]
        assert "custom@example.com" in msg_override["From"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_build_mail_svc_fallback_to_cfg():
    """Verify build_mail_svc uses AppConfig when DB settings are empty."""
    mock_settings = AsyncMock()
    mock_settings.get_group.return_value = {}

    cfg = AppConfig(
        DB_PASS="test",
        SECRETS_MASTER_KEY="0123456789abcdef0123456789abcdef",
        SMTP_HOST="smtp.fromcfg.com",
        SMTP_PORT=9465,
        SMTP_USER="cfg_user",
        SMTP_PASS="cfg_pass",
        SMTP_FROM="cfg@example.com",
        SMTP_FROM_NAME="Cfg Name",
        SMTP_ENCRYPTION="ssl",
        SMTP_TIMEOUT=12,
    )

    svc = await build_mail_svc(mock_settings, cfg)
    assert svc.host == "smtp.fromcfg.com"
    assert svc.port == 9465
    assert svc.user == "cfg_user"
    assert svc.sender == "cfg@example.com"
    assert svc.from_name == "Cfg Name"
    assert svc.encryption == "ssl"
    assert svc.timeout == 12.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_smtp_test_connection_exceptions():
    """Verify test_smtp_connection returns structured error messages for auth, connect, and timeout."""
    mock_settings = AsyncMock()
    mock_settings.get_group.return_value = {
        "smtp.host": "smtp.example.com",
        "smtp.port": "587",
        "smtp.from": "test@example.com",
    }

    body = SmtpTestIn(to_email="recipient@example.com")

    # Timeout error
    with patch("aiosmtplib.send", side_effect=asyncio.TimeoutError()):
        with pytest.raises(HTTPException) as exc_info:
            await test_smtp_connection(body, mock_settings)
        assert exc_info.value.status_code == 400
        assert "connection timeout" in exc_info.value.detail

    # Auth error
    with patch("aiosmtplib.send", side_effect=aiosmtplib.errors.SMTPAuthenticationError(535, "Auth failed")):
        with pytest.raises(HTTPException) as exc_info:
            await test_smtp_connection(body, mock_settings)
        assert exc_info.value.status_code == 400
        assert "authentication failed" in exc_info.value.detail
