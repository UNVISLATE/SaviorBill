"""Юнит-тесты защиты от path traversal в файловых менеджерах (AUDIT.md M1/L1).

``_safe_target()`` в ``SystemScriptsMngr``/``EmailMngr`` раньше использовал
``str(target).startswith(str(base))`` — у этой проверки есть sibling-баг:
``base=/data/scripts``, ``target=/data/scripts_evil/x`` проходит проверку
префикса строки, хотя ``scripts_evil`` — другая директория. Исправлено на
``Path.relative_to()``.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from models.email_templates import EmailMngr
from models.system_scripts import SystemScriptsMngr

pytestmark = pytest.mark.unit


def test_system_scripts_rejects_traversal_dotdot(tmp_path):
    mngr = SystemScriptsMngr(session=None, scripts_dir=str(tmp_path / "scripts"))
    with pytest.raises(HTTPException):
        mngr._safe_target("../outside.lua")


def test_system_scripts_rejects_sibling_dir_prefix_bug(tmp_path):
    """Регрессия sibling-бага: ``scripts_evil`` не должен пройти как ``scripts``."""
    base = tmp_path / "scripts"
    base.mkdir()
    evil_sibling = tmp_path / "scripts_evil"
    evil_sibling.mkdir()
    (evil_sibling / "payload.lua").write_text("-- evil")

    mngr = SystemScriptsMngr(session=None, scripts_dir=str(base))
    # Абсолютный путь к файлу вне base, но с префиксом "scripts" в имени.
    with pytest.raises(HTTPException):
        mngr._safe_target(str(evil_sibling / "payload.lua"))


def test_system_scripts_allows_normal_filename(tmp_path):
    mngr = SystemScriptsMngr(session=None, scripts_dir=str(tmp_path / "scripts"))
    target = mngr._safe_target("services/abc123.lua")
    assert target.name == "abc123.lua"


def test_email_templates_rejects_traversal(tmp_path):
    mngr = EmailMngr(session=None, templates_dir=str(tmp_path / "templates"))
    with pytest.raises(HTTPException):
        mngr._safe_target("../../etc/passwd")
