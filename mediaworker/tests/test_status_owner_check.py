"""Юнит-тесты owner-check для GET /api/media/status/{token} (AUDIT.md §4.3)."""

from api.status import _may_view_status


def test_owner_can_view_own_status():
    assert _may_view_status("42", acc_id=42, perms=None) is True


def test_stranger_without_perm_is_denied():
    assert _may_view_status("42", acc_id=7, perms=None) is False


def test_stranger_with_manage_any_is_allowed():
    perms = {"admin": {"media": {"manage_any": True}}}
    assert _may_view_status("42", acc_id=7, perms=perms) is True


def test_missing_owner_id_does_not_block():
    """Записи без owner_id штатно не создаются (upload.py требует JWT), но
    если такая всё же встретится — не блокируем несуществующим сравнением."""
    assert _may_view_status(None, acc_id=7, perms=None) is True


def test_owner_id_mismatch_without_manage_any_perm_denied():
    perms = {"media": {"upload": True}}
    assert _may_view_status("1", acc_id=2, perms=perms) is False
