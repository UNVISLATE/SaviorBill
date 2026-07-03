"""OAuth-флоу через Lua-скрипты провайдеров (action-driven, как платежи).

У каждого провайдера один auth-скрипт: ``start`` строит authorize_url, ``callback``
обменивает код на нормализованный профиль (``OAuthUser``). Секреты провайдера
шифруются в ``oauth_cfg.secrets_enc`` и прокидываются в скрипт как ``provider.secrets``.
"""

from __future__ import annotations

import json

import valkey.asyncio as valkey
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from dependencies.lua import get_lua_bus
from dependencies.sec import get_secbox
from dependencies.valkey import get_valkey_client
from enums import AuthAction
from models.oauth_providers import OAuthProvidersModel
from models.system_scripts import SystemScriptsModel
from models.user import UserModel
from models.user_oauth import UserOauthModel
from schemas.lua import LuaRequest
from schemas.oauth import OAuthStart, OAuthUser
from services.lua_ctx import LuaRunner
from utils.config import AppConfig
from utils.luabus import LuaBus
from utils.sec.box import SecBox
from utils.sec.crypt import generate_base_token

# Ключ state в Valkey и его TTL (антифрод/CSRF на время редиректа).
_STATE = "oauth:state:"
_STATE_TTL = 600


class OAuthSvc:
    """Высокоуровневые операции OAuth-флоу через Lua-скрипты провайдеров."""

    def __init__(
        self,
        session: AsyncSession,
        vk: valkey.Valkey,
        bus: LuaBus,
        cfg: AppConfig,
        box: SecBox,
    ) -> None:
        self.s = session
        self.vk = vk
        self.cfg = cfg
        self.box = box
        self.runner = LuaRunner(bus)

    def redirect_uri(self, slug: str) -> str:
        base = self.cfg.PUBLIC_URL.rstrip("/")
        return f"{base}/api/v1/callback/oauth/{slug}"

    # --- доступ к провайдеру/секретам/скрипту ----------------------------
    async def _provider(
        self, slug: str, *, enabled: bool = True
    ) -> OAuthProvidersModel:
        stmt = select(OAuthProvidersModel).where(OAuthProvidersModel.slug == slug)
        if enabled:
            stmt = stmt.where(OAuthProvidersModel.enabled.is_(True))
        row = await self.s.scalar(stmt)
        if row is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"провайдер {slug} недоступен"
            )
        return row

    def _secrets(self, prov: OAuthProvidersModel) -> dict:
        """Расшифровать и распарсить JSON секретов провайдера."""
        if not prov.secrets_enc:
            return {}
        raw = self.box.open(prov.secrets_enc)
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {}
        return data if isinstance(data, dict) else {}

    async def _script(
        self, prov: OAuthProvidersModel, action: str
    ) -> SystemScriptsModel:
        """Получить auth-скрипт провайдера и проверить поддержку действия."""
        if not prov.script_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "у провайдера не задан auth-скрипт"
            )
        script = await self.s.get(SystemScriptsModel, prov.script_id)
        if script is None or not script.is_active:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "auth-скрипт провайдера недоступен"
            )
        supported = script.actions or []
        if supported and action not in supported:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"auth-скрипт не поддерживает действие «{action}»",
            )
        return script

    # --- старт авторизации ------------------------------------------------
    async def start(self, slug: str, *, account_id: int | None = None) -> OAuthStart:
        """Собрать authorize_url через скрипт (action=start) и запомнить state.

        :arg slug: провайдер.
        :arg account_id: если задан — привязываем к уже вошедшему аккаунту
            (флоу «привязать провайдера»), иначе — вход/регистрация.
        :return: authorize_url для редиректа + state.
        """
        prov = await self._provider(slug)
        script = await self._script(prov, AuthAction.START)
        state = generate_base_token()

        res = await self.runner.run_auth(
            script,
            AuthAction.START,
            prov,
            self._secrets(prov),
            redirect_uri=self.redirect_uri(slug),
            state=state,
        )
        pub = res.get("public") or {}
        authorize_url = pub.get("authorize_url")
        if not authorize_url:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "скрипт не вернул authorize_url"
            )

        payload = {"slug": slug, "account_id": account_id}
        await self.vk.set(_STATE + state, json.dumps(payload), ex=_STATE_TTL)
        return OAuthStart(authorize_url=authorize_url, state=state)

    async def _pop_state(self, slug: str, state: str) -> dict:
        """Проверить и погасить state, вернуть сохранённую нагрузку."""
        saved = await self.vk.get(_STATE + state)
        if not saved:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "неверный или истёкший state"
            )
        try:
            payload = json.loads(saved)
        except json.JSONDecodeError:
            payload = {"slug": saved}
        if payload.get("slug") != slug:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "неверный или истёкший state"
            )
        await self.vk.delete(_STATE + state)
        return payload

    async def finish(
        self, slug: str, code: str, state: str, request: LuaRequest | None = None
    ) -> tuple[OAuthUser, int | None]:
        """Проверить state, обменять код через скрипт и вернуть профиль.

        :return: кортеж (нормализованный профиль, account_id из state | None).
        """
        payload = await self._pop_state(slug, state)
        prov = await self._provider(slug)
        script = await self._script(prov, AuthAction.CALLBACK)

        res = await self.runner.run_auth(
            script,
            AuthAction.CALLBACK,
            prov,
            self._secrets(prov),
            redirect_uri=self.redirect_uri(slug),
            state=state,
            code=code,
            request=request,
        )
        priv = res.get("private") or {}
        if not priv.get("ok") or not priv.get("sub"):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "не удалось получить профиль пользователя",
            )
        user = OAuthUser(
            sub=str(priv["sub"]),
            email=priv.get("email"),
            email_verified=bool(priv.get("email_verified")),
            name=priv.get("name"),
            picture=priv.get("picture"),
            raw=priv.get("raw") or {},
        )
        return user, payload.get("account_id")

    # --- привязка/создание аккаунта --------------------------------------
    async def link_account(self, slug: str, user: OAuthUser) -> UserModel:
        """Найти/создать аккаунт по внешней учётке и обновить привязку."""
        conn = await self.s.scalar(
            select(UserOauthModel).where(
                UserOauthModel.provider == slug, UserOauthModel.subject == user.sub
            )
        )
        if conn is not None:
            conn.email = user.email
            conn.raw = user.raw
            acc = await self.s.get(UserModel, conn.account_id)
            if acc is None:  # осиротевшая привязка — пересоздадим аккаунт ниже
                conn = None

        if conn is None:
            acc = None
            # Связываем с существующим аккаунтом только при подтверждённом email.
            if user.email and user.email_verified:
                acc = await self.s.scalar(
                    select(UserModel).where(UserModel.email == user.email)
                )
            if acc is None:
                acc = UserModel(
                    login=f"{slug}:{user.sub}"[:64],
                    email=user.email,
                )
                # Роль по факту верификации email провайдером: user либо guest.
                from models.user import UserMngr
                from enums import BaseRole

                role_key = BaseRole.USER if user.email_verified else BaseRole.GUEST
                role = await UserMngr(self.s).role_by_key(role_key)
                acc.role_id = role.id if role else None
                self.s.add(acc)
                await self.s.flush()
                acc.role = role
            self.s.add(
                UserOauthModel(
                    account_id=acc.id,
                    provider=slug,
                    subject=user.sub,
                    email=user.email,
                    raw=user.raw,
                )
            )

        await self.s.flush()
        return acc

    async def link_to_existing(
        self, acc: UserModel, slug: str, user: OAuthUser
    ) -> UserOauthModel:
        """Привязать внешнюю учётку к уже вошедшему аккаунту.

        :arg acc: текущий (аутентифицированный) аккаунт.
        :arg slug: провайдер.
        :arg user: нормализованный профиль от провайдера.
        :raises HTTPException: если учётка уже привязана к другому аккаунту.
        :return: созданная/обновлённая привязка.
        """
        conn = await self.s.scalar(
            select(UserOauthModel).where(
                UserOauthModel.provider == slug, UserOauthModel.subject == user.sub
            )
        )
        if conn is not None and conn.account_id != acc.id:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "эта внешняя учётка уже привязана к другому аккаунту",
            )
        if conn is None:
            conn = UserOauthModel(
                account_id=acc.id,
                provider=slug,
                subject=user.sub,
                email=user.email,
                raw=user.raw,
            )
            self.s.add(conn)
        else:
            conn.email = user.email
            conn.raw = user.raw
        await self.s.flush()
        return conn


def get_oauth_svc(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    vk: valkey.Valkey = Depends(get_valkey_client),
    box: SecBox = Depends(get_secbox),
) -> OAuthSvc:
    return OAuthSvc(session, vk, get_lua_bus(request), request.app.state.settings, box)


__all__ = ["OAuthSvc", "get_secbox", "get_oauth_svc"]
