"""Lua-скрипты системы (SystemScriptsModel) + менеджер (SystemScriptsMngr)."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from pathlib import Path

import shutil

from fastapi import HTTPException, status
from sqlalchemy import (
    func,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from models import Base
from enums import ScriptKind, PayAction, AuthAction, ServiceAction
from utils.datetime_utils import utc_now

# Подпапка хранения по виду скрипта (внутри LUA_SCRIPTS_DIR).
_SUBDIR_BY_KIND = {
    ScriptKind.SERVICE: "services",
    ScriptKind.PAYMENT: "payments",
    ScriptKind.AUTH: "auth",
    ScriptKind.TRIGGER: "triggers",
}


class SystemScriptsModel(Base):
    """Запись о Lua-скрипте."""

    __tablename__ = "lua_scripts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    slug: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # service | payment | generic (см. ScriptKind).
    kind: Mapped[str] = mapped_column(
        String(16), default=ScriptKind.SERVICE, nullable=False
    )
    # Имя файла относительно LUA_SCRIPTS_DIR (генерируется системой, напр.
    # "services/3f9c1a....lua"). Клиент имя файла не задаёт.
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Поддерживаемые действия скрипта. Для payment-скриптов обязательны
    # create/callback (см. PayAction); для service — по крайней мере create.
    actions: Mapped[list] = mapped_column(
        JSON, default=list, server_default="[]", nullable=False
    )
    # Настройки самого шаблона (ctx.lua.settings.*). Задаются один раз на скрипт
    # и разделяются всеми услугами/провайдерами, которые его используют (напр.
    # учётные данные внешней панели), чтобы не дублировать их в каждой услуге.
    settings: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}", nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Номер текущей (последней) версии — растёт на 1 при каждом изменении кода.
    current_version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )


class LuaScriptVersionModel(Base):
    """Снимок версии кода Lua-скрипта (история, для diff/восстановления/пиннинга)."""

    __tablename__ = "lua_script_versions"
    __table_args__ = (UniqueConstraint("script_id", "version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    script_id: Mapped[int] = mapped_column(
        ForeignKey("lua_scripts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    # Неизменяемый файл этой версии (относительно LUA_SCRIPTS_DIR).
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    commit_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )


async def resolve_version_filename(
    session: AsyncSession, script: SystemScriptsModel, version: int | None
) -> str:
    """Разрешить путь файла нужной версии скрипта.

    ``version=None`` — всегда latest. Если версия указана, но такой записи
    больше нет (удалена/не найдена) — тихий фоллбэк на latest (см. задачу:
    ссылки на скрипт не должны падать из-за истёкшей версии).

    :arg session: активная сессия БД.
    :arg script: модель скрипта (источник ``filename``/``current_version``).
    :arg version: желаемый номер версии или ``None`` (latest).
    :return: путь файла версии (относительно LUA_SCRIPTS_DIR).
    """
    if version is None or version == script.current_version:
        return script.filename
    row = await session.scalar(
        select(LuaScriptVersionModel).where(
            LuaScriptVersionModel.script_id == script.id,
            LuaScriptVersionModel.version == version,
        )
    )
    return row.filename if row is not None else script.filename


class SystemScriptsMngr:
    """Регистрация и хранение Lua-скриптов в монтируемой папке."""

    def __init__(self, session: AsyncSession, scripts_dir: str) -> None:
        self.s = session
        self.dir = Path(scripts_dir)

    async def list_all(self) -> list[SystemScriptsModel]:
        rows = await self.s.scalars(
            select(SystemScriptsModel).order_by(SystemScriptsModel.id)
        )
        return list(rows)

    async def by_slug(self, slug: str) -> SystemScriptsModel | None:
        return await self.s.scalar(
            select(SystemScriptsModel).where(SystemScriptsModel.slug == slug)
        )

    def _gen_base(self, kind: str) -> str:
        """Сгенерировать базовый путь-каталог скрипта (uuid4 + подпапка по виду)."""
        subdir = _SUBDIR_BY_KIND.get(kind, "generic")
        return f"{subdir}/{uuid.uuid4().hex}"

    async def create(self, data, created_by: int | None = None) -> SystemScriptsModel:
        """Записать тело скрипта (v1) в файл со сгенерированным именем и сохранить карту."""
        if await self.by_slug(data.slug):
            raise HTTPException(status.HTTP_409_CONFLICT, "script slug already taken")

        actions = list(getattr(data, "actions", None) or [])
        self._check_actions(data.kind, actions)

        base = self._gen_base(data.kind)
        filename = f"{base}/v1.lua"
        target = self._safe_target(filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(data.code, encoding="utf-8")
        sha256 = hashlib.sha256(data.code.encode()).hexdigest()

        row = SystemScriptsModel(
            slug=data.slug,
            name=data.name,
            kind=data.kind,
            filename=filename,
            sha256=sha256,
            description=data.description,
            actions=actions,
            settings=dict(getattr(data, "settings", None) or {}),
            current_version=1,
        )
        self.s.add(row)
        await self.s.flush()

        self.s.add(
            LuaScriptVersionModel(
                script_id=row.id,
                version=1,
                filename=filename,
                sha256=sha256,
                commit_message=getattr(data, "commit_message", None) or "Начальная версия",
                created_by=created_by,
            )
        )
        await self.s.flush()
        return row

    @staticmethod
    def _check_actions(kind: str, actions: list[str]) -> None:
        """Проверить обязательные действия скрипта по его виду.

        :arg kind: вид скрипта (см. :class:`enums.ScriptKind`).
        :arg actions: заявленные поддерживаемые действия.
        :raises HTTPException: если обязательные действия не заявлены.
        """
        if kind == ScriptKind.PAYMENT:
            missing = [a for a in PayAction.MANDATORY if a not in actions]
            if missing:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"payment script must support: {', '.join(missing)}",
                )
        elif kind == ScriptKind.AUTH:
            missing = [a for a in AuthAction.MANDATORY if a not in actions]
            if missing:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"auth script must support: {', '.join(missing)}",
                )
        elif kind == ScriptKind.SERVICE:
            if actions and ServiceAction.CREATE not in actions:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "service script must support create",
                )

    async def by_id(self, script_id: int) -> SystemScriptsModel | None:
        return await self.s.get(SystemScriptsModel, script_id)

    async def read_code(self, row: SystemScriptsModel) -> str:
        """Прочитать тело скрипта из файла."""
        target = self._safe_target(row.filename)
        if not target.exists():
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "script body file is missing"
            )
        return target.read_text(encoding="utf-8")

    def _safe_target(self, filename: str) -> Path:
        """Разрешить ``filename`` внутри ``self.dir``, отклонить выход за его пределы.

        ``relative_to()`` — не ``startswith()`` на строках путей: у последнего
        есть sibling-баг (``self.dir=/data/scripts``, а
        ``target=/data/scripts_evil/x`` проходит проверку — префикс строки
        совпадает, хотя это другая директория).
        """
        base = self.dir.resolve()
        target = (base / filename).resolve()
        try:
            target.relative_to(base)
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "invalid file path"
            ) from exc
        return target

    async def patch(self, script_id: int, data, actor_id: int | None = None) -> SystemScriptsModel:
        """Обновить тело и/или настройки скрипта (только переданные поля).

        Изменение ``code`` создаёт новую immutable-версию (``current_version + 1``)
        в отдельном файле — старые версии не перезатираются.

        :arg script_id: id скрипта.
        :arg data: схема с опциональными ``code``/``settings``/``commit_message``.
        :arg actor_id: id актора (для истории версий).
        :return: обновлённая запись.
        """
        row = await self.by_id(script_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "script not found")

        code = getattr(data, "code", None)
        if code is not None:
            base = str(Path(row.filename).parent)
            new_version = row.current_version + 1
            filename = f"{base}/v{new_version}.lua"
            target = self._safe_target(filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(code, encoding="utf-8")
            sha256 = hashlib.sha256(code.encode()).hexdigest()

            row.filename = filename
            row.sha256 = sha256
            row.current_version = new_version
            self.s.add(
                LuaScriptVersionModel(
                    script_id=row.id,
                    version=new_version,
                    filename=filename,
                    sha256=sha256,
                    commit_message=getattr(data, "commit_message", None),
                    created_by=actor_id,
                )
            )

        settings = getattr(data, "settings", None)
        if settings is not None:
            row.settings = dict(settings)

        await self.s.flush()
        return row

    async def list_versions(self, script_id: int) -> list[LuaScriptVersionModel]:
        """Список версий скрипта (новые сверху)."""
        rows = await self.s.scalars(
            select(LuaScriptVersionModel)
            .where(LuaScriptVersionModel.script_id == script_id)
            .order_by(LuaScriptVersionModel.version.desc())
        )
        return list(rows)

    async def get_version(
        self, script_id: int, version: int
    ) -> LuaScriptVersionModel | None:
        return await self.s.scalar(
            select(LuaScriptVersionModel).where(
                LuaScriptVersionModel.script_id == script_id,
                LuaScriptVersionModel.version == version,
            )
        )

    async def read_code_at(self, filename: str) -> str:
        """Прочитать тело скрипта из произвольного файла версии."""
        target = self._safe_target(filename)
        if not target.exists():
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "script version body file is missing"
            )
        return target.read_text(encoding="utf-8")

    async def _references(self, script_id: int) -> list[str]:
        """Найти сущности, ссылающиеся на скрипт (для дружелюбного 409).

        DB-уровень (FK ondelete=RESTRICT) — финальный барьер; здесь же собираем
        человекочитаемый список ссылок, чтобы вернуть осмысленную ошибку.

        :arg script_id: id проверяемого скрипта.
        :return: список описаний ссылающихся сущностей (пусто — если ссылок нет).
        """
        from models.oauth_providers import OAuthProvidersModel
        from models.payment_providers import PaymentProvidersModel
        from models.service import ServiceModel

        refs: list[str] = []
        svc = await self.s.scalars(
            select(ServiceModel.slug).where(ServiceModel.lua_script_id == script_id)
        )
        refs += [f"услуга:{s}" for s in svc]
        pay = await self.s.scalars(
            select(PaymentProvidersModel.slug).where(
                PaymentProvidersModel.script_id == script_id
            )
        )
        refs += [f"платёжный провайдер:{s}" for s in pay]
        oauth = await self.s.scalars(
            select(OAuthProvidersModel.slug).where(
                OAuthProvidersModel.script_id == script_id
            )
        )
        refs += [f"oauth-провайдер:{s}" for s in oauth]
        return refs

    async def delete(self, script_id: int) -> None:
        """Удалить запись скрипта и его файл.

        Скрипт нельзя удалить, пока на него ссылается услуга, платёжный или
        oauth-провайдер — иначе сломается их логика. Предпроверяем ссылки и
        отдаём 409; на уровне БД тот же инвариант закреплён FK ``ondelete=RESTRICT``.
        """
        row = await self.by_id(script_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "script not found")
        refs = await self._references(script_id)
        if refs:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "script is in use and cannot be deleted: " + ", ".join(refs),
            )
        target = self._safe_target(row.filename)
        version_dir = target.parent
        if version_dir != self.dir.resolve() and version_dir.exists():
            shutil.rmtree(version_dir, ignore_errors=True)
        elif target.exists():
            target.unlink()
        await self.s.delete(row)
        await self.s.flush()


__all__ = [
    "SystemScriptsModel",
    "SystemScriptsMngr",
    "LuaScriptVersionModel",
    "resolve_version_filename",
]
