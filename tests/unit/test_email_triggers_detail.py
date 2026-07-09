"""Тесты Этапа D: получение одного email-шаблона (с телом) и одного триггера."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from models.email_templates import EmailMngr
from schemas.email import EmailTemplate, EmailTemplateDetail
from schemas.trigger import Trigger

pytestmark = pytest.mark.unit


def _email_row(filename: str, **overrides) -> SimpleNamespace:
    base = dict(
        id=1,
        slug="welcome",
        name="Welcome",
        subject="Привет, {{ name }}!",
        filename=filename,
        is_html=True,
        is_active=True,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class TestEmailMngrReadBody:
    @pytest.mark.asyncio
    async def test_reads_existing_file(self, tmp_path) -> None:
        (tmp_path / "t1.html").write_text("<p>Привет!</p>", encoding="utf-8")
        mngr = EmailMngr(session=None, templates_dir=str(tmp_path))
        row = _email_row("t1.html")
        body = await mngr.read_body(row)
        assert body == "<p>Привет!</p>"

    @pytest.mark.asyncio
    async def test_missing_file_raises_404(self, tmp_path) -> None:
        mngr = EmailMngr(session=None, templates_dir=str(tmp_path))
        row = _email_row("missing.html")
        with pytest.raises(HTTPException) as exc:
            await mngr.read_body(row)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_rejects_path_escape(self, tmp_path) -> None:
        mngr = EmailMngr(session=None, templates_dir=str(tmp_path))
        row = _email_row("../../etc/passwd")
        with pytest.raises(HTTPException) as exc:
            await mngr.read_body(row)
        assert exc.value.status_code == 400


class TestEmailTemplateDetailSchema:
    def test_from_model_with_body_includes_body(self) -> None:
        row = _email_row("t1.html")
        detail = EmailTemplateDetail.from_model_with_body(row, "<p>тело</p>")
        assert detail.body == "<p>тело</p>"
        assert detail.slug == "welcome"
        assert detail.subject == "Привет, {{ name }}!"
        assert detail.is_html is True

    def test_detail_is_email_template_subclass(self) -> None:
        assert issubclass(EmailTemplateDetail, EmailTemplate)

    def test_list_schema_has_no_body_field(self) -> None:
        assert "body" not in EmailTemplate.model_fields
        assert "body" in EmailTemplateDetail.model_fields


class TestTriggerSchemaFullConfig:
    def test_from_model_includes_full_config_and_cond(self) -> None:
        row = SimpleNamespace(
            id=1,
            name="Приветственное письмо",
            event="user.registered",
            action="email",
            config={"template_id": 5, "to_field": "email"},
            cond={"payment.target": "service"},
            is_active=True,
        )
        trig = Trigger.from_model(row)
        assert trig.config == {"template_id": 5, "to_field": "email"}
        assert trig.cond == {"payment.target": "service"}
