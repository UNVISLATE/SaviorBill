"""OAuth-флоу через Lua-скрипты провайдеров (action-driven, как платежи).

У каждого провайдера один auth-скрипт: ``start`` строит authorize_url, ``callback``
обменивает код на нормализованный профиль (``OAuthUser``). Секреты провайдера
шифруются в ``oauth_cfg.secrets_enc`` и прокидываются в скрипт как ``provider.secrets``.
"""

from __future__ import annotations

import hmac
import json

import valkey.asyncio as valkey
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from lua.deps import get_lua_bus_configured
from dependencies.email import get_email_sender
from dependencies.sec import get_secbox
from dependencies.settings import SystemSettingsMngr, get_settings_mngr
from dependencies.valkey import get_valkey_client
from enums import AuthAction
from models.oauth_providers import OAuthProvidersModel
from models.system_scripts import SystemScriptsModel
from models.user import UserModel
from models.user_oauth import UserOauthModel
from lua.schemas import LuaRequest
from lifecycle.notifications import EmailEvent, EmailSender
from schemas.oauth import OAuthPendingLink, OAuthStart, OAuthUser
from lua.context import LuaRunner
from core.config import AppConfig
from lua.bus import LuaBus
from security.sec.box import SecBox
from security.sec.crypt import generate_base_token, generate_numeric_code

# Ключ state в Valkey и его TTL (антифрод/CSRF на время редиректа).
_STATE = "oauth:state:"
_STATE_TTL = 600
# Незавершённая привязка OAuth к существующему аккаунту (найден по email, но
# владение аккаунтом не подтверждено — см. AUDIT.md §1.4/§2.1). Хранится
# отдельно от подтверждающего кода, чтобы можно было проверять неверные
# попытки без сброса самой заявки на привязку.
_PENDING = "oauth:pendinglink:"
_PENDING_CODE = "oauth:pendinglink:code:"
_PENDING_TTL = 600
_CODE_DIGITS = 6


def build_lua_request(request: Request) -> LuaRequest:
    """Собрать :class:`LuaRequest` из FastAPI-запроса (метод/ip/заголовки/query).

    Общий хелпер для всех action'ов (``start``, ``callback``) — скрипту всегда
    доступны полные данные входящего HTTP-запроса, а не только то, что платформа
    явно вынесла в отдельные поля контекста (state/code/nonce и т.п.).
    """
    return LuaRequest.build(
        method=request.method,
        ip=request.client.host if request.client else None,
        headers={k.lower(): v for k, v in request.headers.items()},
        query=dict(request.query_params),
        body={},
    )


class OAuthSvc:
    """Высокоуровневые операции OAuth-флоу через Lua-скрипты провайдеров."""

    def __init__(
        self,
        session: AsyncSession,
        vk: valkey.Valkey,
        bus: LuaBus,
        cfg: AppConfig,
        box: SecBox,
        sender: EmailSender,
        settings: SystemSettingsMngr,
    ) -> None:
        self.s = session
        self.vk = vk
        self.cfg = cfg
        self.box = box
        self.sender = sender
        self.settings = settings
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
                status.HTTP_404_NOT_FOUND, f"provider {slug} is unavailable"
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
                status.HTTP_400_BAD_REQUEST, "provider has no auth script configured"
            )
        script = await self.s.get(SystemScriptsModel, prov.script_id)
        if script is None or not script.is_active:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "provider auth script is unavailable"
            )
        supported = script.actions or []
        if supported and action not in supported:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"auth script does not support action '{action}'",
            )
        return script

    # --- старт авторизации ------------------------------------------------
    async def start(
        self,
        slug: str,
        *,
        account_id: int | None = None,
        request: Request | None = None,
    ) -> OAuthStart:
        """Собрать authorize_url через скрипт (action=start) и запомнить state.

        :arg slug: провайдер.
        :arg account_id: если задан — привязываем к уже вошедшему аккаунту
            (флоу «привязать провайдера»), иначе — вход/регистрация.
        :arg request: исходный HTTP-запрос — прокидывается скрипту целиком
            (метод/ip/заголовки/query), как и в callback, чтобы скрипт мог
            читать любые нестандартные данные запроса (не только то, что
            платформа явно выделила в отдельные поля контекста).
        :return: authorize_url для редиректа + state.
        """
        prov = await self._provider(slug)
        script = await self._script(prov, AuthAction.START)
        state = generate_base_token()
        # Nonce — чисто транспортная роль платформы: сгенерировать и надёжно
        # сохранить между start/callback (это может сделать только платформа,
        # т.к. именно она хранит state между двумя разными HTTP-запросами).
        # Содержательную проверку (сверку с claim id_token) делает сам скрипт —
        # не все провайдеры используют OIDC/nonce.
        nonce = generate_base_token()

        res = await self.runner.run_auth(
            script,
            AuthAction.START,
            prov,
            self._secrets(prov),
            redirect_uri=self.redirect_uri(slug),
            state=state,
            nonce=nonce,
            request=build_lua_request(request) if request is not None else None,
        )
        pub = res.get("public") or {}
        authorize_url = pub.get("authorize_url")
        if not authorize_url:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, "script did not return authorize_url"
            )

        payload = {"slug": slug, "account_id": account_id, "nonce": nonce}
        await self.vk.set(_STATE + state, json.dumps(payload), ex=_STATE_TTL)
        return OAuthStart(authorize_url=authorize_url, state=state)

    async def _pop_state(self, slug: str, state: str) -> dict:
        """Проверить и погасить state, вернуть сохранённую нагрузку."""
        saved = await self.vk.get(_STATE + state)
        if not saved:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid or expired state")
        try:
            payload = json.loads(saved)
        except json.JSONDecodeError:
            payload = {"slug": saved}
        if payload.get("slug") != slug:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid or expired state")
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
            expected_nonce=payload.get("nonce"),
            request=request,
        )
        priv = res.get("private") or {}
        if not priv.get("ok") or not priv.get("sub"):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "failed to fetch user profile",
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
    async def link_account(
        self, slug: str, user: OAuthUser
    ) -> tuple[UserModel | None, OAuthPendingLink | None]:
        """Найти/создать аккаунт по внешней учётке и обновить привязку.

        :return: ``(acc, None)`` — привязка выполнена/аккаунт создан сразу;
            ``(None, pending)`` — найден существующий аккаунт с тем же
            подтверждённым email, но это первый вход этой внешней учётки —
            владение аккаунтом не подтверждено, требуется код с почты
            существующего аккаунта (см. ``confirm_pending_link``).
        """
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
            # Связываем с существующим аккаунтом только при подтверждённом
            # email — и даже тогда не сразу: сначала подтверждение владения
            # (см. _start_pending_link), чтобы захват чужого аккаунта через
            # OAuth-провайдера со слабой проверкой email был невозможен.
            if user.email and user.email_verified:
                existing = await self.s.scalar(
                    select(UserModel).where(UserModel.email == user.email)
                )
                if existing is not None:
                    pending = await self._start_pending_link(slug, user, existing)
                    return None, pending
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
        return acc, None

    async def _pending_ttl(self) -> int:
        return await self.settings.get_int("mail.code_ttl", _PENDING_TTL)

    async def _start_pending_link(
        self, slug: str, user: OAuthUser, existing: UserModel
    ) -> OAuthPendingLink:
        """Завести заявку на привязку и отправить код на email существующего
        аккаунта (не создаёт привязку/сессию, пока код не подтверждён)."""
        pending_token = generate_base_token()
        code = generate_numeric_code(_CODE_DIGITS)
        ttl = await self._pending_ttl()
        payload = {
            "slug": slug,
            "sub": user.sub,
            "email": user.email,
            "email_verified": user.email_verified,
            "name": user.name,
            "picture": user.picture,
            "raw": user.raw,
            "account_id": existing.id,
        }
        await self.vk.set(_PENDING + pending_token, json.dumps(payload), ex=ttl)
        await self.vk.set(_PENDING_CODE + pending_token, code, ex=ttl)

        ctx = {
            "user": {"id": existing.id, "login": existing.login, "email": existing.email},
            "provider": slug,
            "code": code,
            "ttl_minutes": max(1, ttl // 60),
        }
        sent = await self.sender.send_template(
            EmailEvent.OAUTH_LINK_CONFIRM, existing.email, ctx
        )
        if not sent:
            await self.sender.mail.send(
                existing.email,
                "Confirm account link",
                f"Someone tried to sign in to your account via {slug}. "
                f"Confirmation code: {code}",
            )
        return OAuthPendingLink(pending_token=pending_token)

    async def confirm_pending_link(self, pending_token: str, code: str) -> UserModel:
        """Подтвердить заявку на привязку кодом с почты существующего аккаунта.

        :raises HTTPException: заявка не найдена/истекла, либо код неверный.
        :return: аккаунт, к которому подтверждена привязка OAuth-учётки.
        """
        raw = await self.vk.get(_PENDING + pending_token)
        if raw is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "pending link not found or expired"
            )
        stored_code = await self.vk.get(_PENDING_CODE + pending_token)
        if stored_code is None or not hmac.compare_digest(stored_code, code):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid code")

        payload = json.loads(raw)
        acc = await self.s.get(UserModel, payload["account_id"])
        if acc is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")

        conn = await self.s.scalar(
            select(UserOauthModel).where(
                UserOauthModel.provider == payload["slug"],
                UserOauthModel.subject == payload["sub"],
            )
        )
        if conn is None:
            conn = UserOauthModel(
                account_id=acc.id,
                provider=payload["slug"],
                subject=payload["sub"],
                email=payload.get("email"),
                raw=payload.get("raw") or {},
            )
            self.s.add(conn)
        else:
            conn.account_id = acc.id
            conn.email = payload.get("email")
            conn.raw = payload.get("raw") or {}

        await self.vk.delete(_PENDING + pending_token)
        await self.vk.delete(_PENDING_CODE + pending_token)
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
                "this external account is already linked to another account",
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
    bus: LuaBus = Depends(get_lua_bus_configured),
    sender: EmailSender = Depends(get_email_sender),
    settings: SystemSettingsMngr = Depends(get_settings_mngr),
) -> OAuthSvc:
    return OAuthSvc(session, vk, bus, request.app.state.settings, box, sender, settings)


__all__ = ["OAuthSvc", "get_secbox", "get_oauth_svc", "build_lua_request"]
