"""Фикстуры интеграционных тестов.

Тесты гоняются против ПОДНЯТОГО стека (Postgres + Valkey + LuaWorker + billing):
HTTP-вызовы идут на ``BASE_URL`` (контейнер billing), а сидинг данных — напрямую
в БД через async-движок SQLAlchemy. Поэтому раннер должен иметь сетевой доступ
и к billing, и к Postgres (см. docker-compose.test.yml).
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from utils.config import AppConfig

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
CALLBACK_SECRET = os.environ.get("PAY_CALLBACK_SECRET", "test-callback-secret")


@pytest.fixture(scope="session")
def cfg() -> AppConfig:
    return AppConfig()


@pytest_asyncio.fixture
async def engine(cfg: AppConfig) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(cfg.db_url)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest_asyncio.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as client:
        yield client


def uniq(prefix: str) -> str:
    """Уникальный суффикс, чтобы тесты не конфликтовали на персистентной БД."""
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


@pytest_asyncio.fixture
async def new_user(http: httpx.AsyncClient):
    """Зарегистрировать нового пользователя, вернуть (login, password, tokens)."""

    async def _make():
        login = uniq("user")
        pwd = "secret123"
        r = await http.post(
            "/api/v1/auth/register",
            json={"login": login, "email": f"{login}@test.io", "password": pwd},
        )
        r.raise_for_status()
        return login, pwd, r.json()

    return _make


@pytest_asyncio.fixture
async def seed(engine: AsyncEngine):
    """Набор хелперов сидинга прямо в БД (возвращают созданные id)."""

    class Seeder:
        async def key_service(self, price: str = "10.00", keys: int = 2) -> int:
            slug = uniq("key_svc")
            async with engine.begin() as c:
                sid = await c.scalar(
                    text(
                        "INSERT INTO services (slug,name,price,currency,delivery,params,is_active) "
                        "VALUES (:slug,'Key svc',:price,'RUB','key','{}',true) RETURNING id"
                    ),
                    {"slug": slug, "price": price},
                )
                for i in range(keys):
                    await c.execute(
                        text(
                            "INSERT INTO digi_keys (service_id,value,is_used) "
                            "VALUES (:sid,:val,false)"
                        ),
                        {"sid": sid, "val": f"KEY-{slug}-{i}"},
                    )
            return sid

        async def lua_service(self, price: str = "5.00") -> int:
            slug = uniq("lua_svc")
            async with engine.begin() as c:
                script_id = await c.scalar(
                    text(
                        "INSERT INTO lua_scripts (slug,name,kind,filename,is_active) "
                        "VALUES (:slug,'demo','service','services/demo_service.lua',true) "
                        "RETURNING id"
                    ),
                    {"slug": uniq("script")},
                )
                sid = await c.scalar(
                    text(
                        "INSERT INTO services (slug,name,price,currency,delivery,lua_script_id,params,is_active) "
                        "VALUES (:slug,'Lua svc',:price,'RUB','lua',:script,'{\"message\":\"hi\"}',true) "
                        "RETURNING id"
                    ),
                    {"slug": slug, "price": price, "script": script_id},
                )
            return sid

        async def pay_provider(self, secret: str = "test-callback-secret") -> str:
            """Создать платёжного провайдера на демо-скриптах (init + callback).

            Секреты кладём сырым JSON (SecBox.open вернёт как есть) — этого
            достаточно для демо-callback, который сверяет ``request.sign`` с
            ``settings.secret``.

            :arg secret: общий секрет для проверки подписи в демо-колбэке.
            :return: slug созданного провайдера.
            """
            slug = uniq("pay")
            async with engine.begin() as c:
                init_id = await c.scalar(
                    text(
                        "INSERT INTO lua_scripts (slug,name,kind,filename,is_active) "
                        "VALUES (:slug,'demo-init','payment','payments/demo_init.lua',true) "
                        "RETURNING id"
                    ),
                    {"slug": uniq("init")},
                )
                cb_id = await c.scalar(
                    text(
                        "INSERT INTO lua_scripts (slug,name,kind,filename,is_active) "
                        "VALUES (:slug,'demo-cb','payment','payments/demo_callback.lua',true) "
                        "RETURNING id"
                    ),
                    {"slug": uniq("cb")},
                )
                await c.execute(
                    text(
                        "INSERT INTO pay_providers "
                        "(slug,title,enabled,secrets_enc,currency,init_script_id,cb_script_id,extra) "
                        "VALUES (:slug,'Demo',true,:sec,'RUB',:init,:cb,'{}')"
                    ),
                    {
                        "slug": slug,
                        "sec": json.dumps({"secret": secret}),
                        "init": init_id,
                        "cb": cb_id,
                    },
                )
            return slug

        async def make_admin(self, login: str) -> None:
            async with engine.begin() as c:
                await c.execute(
                    text(
                        "UPDATE accounts SET role_id=(SELECT id FROM roles WHERE name='admin') "
                        "WHERE login=:login"
                    ),
                    {"login": login},
                )

    return Seeder()
