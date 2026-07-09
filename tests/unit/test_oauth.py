"""Тесты Этапа B: чистка легаси-полей OAuth-провайдера, иконка, LuaRequest в start."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from starlette.requests import Request

from dependencies.oauth import build_lua_request
from models.oauth_providers import OAuthProvidersModel
from schemas.oauth import Provider
from schemas.oauth_provider import OAuthProvider, OAuthProviderCreate, OAuthProviderPatch

pytestmark = pytest.mark.unit


def _asgi_request(
    method: str = "GET",
    query: str = "a=1&b=2",
    headers: list[tuple[bytes, bytes]] | None = None,
    client: tuple[str, int] | None = ("1.2.3.4", 12345),
) -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": "/api/v1/oauth/google",
        "query_string": query.encode(),
        "headers": headers or [(b"user-agent", b"pytest")],
        "client": client,
    }
    return Request(scope)


class TestBuildLuaRequest:
    def test_builds_full_request_data(self) -> None:
        req = _asgi_request()
        lr = build_lua_request(req)
        assert lr.method == "GET"
        assert lr.ip == "1.2.3.4"
        assert lr.headers.get("user-agent") == "pytest"
        assert lr.query == {"a": "1", "b": "2"}
        # start — GET-редирект без тела, но контейнер body всегда присутствует
        assert lr.body == {}

    def test_no_client_gives_none_ip(self) -> None:
        req = _asgi_request(client=None)
        lr = build_lua_request(req)
        assert lr.ip is None

    def test_headers_lowercased(self) -> None:
        req = _asgi_request(headers=[(b"X-Custom", b"Value")])
        lr = build_lua_request(req)
        assert lr.headers == {"x-custom": "Value"}


class TestOAuthProvidersModelLegacyFieldsRemoved:
    def test_legacy_columns_absent(self) -> None:
        cols = {c.name for c in OAuthProvidersModel.__table__.columns}
        for legacy in (
            "parent_id",
            "client_id",
            "client_secret_enc",
            "issuer",
            "authorize_url",
            "token_url",
            "userinfo_url",
            "jwks_uri",
        ):
            assert legacy not in cols, f"легаси-поле {legacy} должно быть удалено"

    def test_icon_media_id_present_and_nullable(self) -> None:
        col = OAuthProvidersModel.__table__.columns["icon_media_id"]
        assert col.nullable is True
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        assert fks[0].column.table.name == "system_media"


class TestOAuthProviderSchemas:
    def test_create_accepts_icon_media_id(self) -> None:
        body = OAuthProviderCreate(slug="google", script_id=1, icon_media_id=42)
        assert body.icon_media_id == 42

    def test_create_icon_optional(self) -> None:
        body = OAuthProviderCreate(slug="google", script_id=1)
        assert body.icon_media_id is None

    def test_patch_accepts_icon_media_id_null_to_clear(self) -> None:
        body = OAuthProviderPatch(icon_media_id=None)
        assert "icon_media_id" in body.model_fields_set
        assert body.icon_media_id is None

    def test_from_model_with_icon(self) -> None:
        media = SimpleNamespace(token="tok123")
        m = SimpleNamespace(
            id=1,
            slug="google",
            title="Google",
            enabled=True,
            script_id=5,
            icon_media_id=7,
            icon=media,
            scopes="openid email",
            extra={},
        )
        out = OAuthProvider.from_model(m)
        assert out.icon_media_id == 7
        assert out.icon_url == "/media/tok123"

    def test_from_model_without_icon(self) -> None:
        m = SimpleNamespace(
            id=1,
            slug="google",
            title="Google",
            enabled=True,
            script_id=5,
            icon_media_id=None,
            icon=None,
            scopes="openid email",
            extra={},
        )
        out = OAuthProvider.from_model(m)
        assert out.icon_media_id is None
        assert out.icon_url is None


class TestPublicProviderSchema:
    def test_provider_has_icon_url_field(self) -> None:
        p = Provider(slug="google", title="Google", icon_url="/media/tok123")
        assert p.icon_url == "/media/tok123"

    def test_provider_icon_url_optional(self) -> None:
        p = Provider(slug="google", title="Google")
        assert p.icon_url is None
