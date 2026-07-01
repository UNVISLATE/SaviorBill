"""Фикстуры интеграционных тестов.

Тесты гоняются против ПОДНЯТОГО стека (Postgres + Valkey + LuaWorker + billing):
HTTP-вызовы идут на ``BASE_URL`` (контейнер billing), а сидинг данных — напрямую
в БД через async-движок SQLAlchemy. Поэтому раннер должен иметь сетевой доступ
и к billing, и к Postgres (см. docker-compose.test.yml).
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, TypeVar

import httpx
import pytest
import pytest_asyncio
import valkey.asyncio as valkey
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from utils.config import AppConfig
from utils.luabus import LuaBus, LuaError

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
CALLBACK_SECRET = os.environ.get("PAY_CALLBACK_SECRET", "test-callback-secret")

T = TypeVar("T")


async def wait_until(
    factory: Callable[[], Awaitable[T]],
    predicate: Callable[[T], bool],
    *,
    timeout: float = 30.0,
    interval: float = 0.25,
) -> T:
    """Опрашивать ``factory`` пока ``predicate`` не станет истинным либо не выйдет время.

    Нужен для тестов против async-обработки (lua-воркер, billing-loop): на медленном
    CI терминальное состояние наступает не мгновенно, поэтому вместо единичной
    проверки статуса ждём его достижения.

    :arg factory: корутина-фабрика, дающая свежий результат на каждой итерации.
    :arg predicate: условие завершения ожидания над результатом factory.
    :arg timeout: предел ожидания в секундах.
    :arg interval: пауза между попытками в секундах.
    :return: последний результат factory, удовлетворивший predicate.
    :raises AssertionError: если за timeout условие не выполнено.
    """
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    last: Any = None
    while True:
        last = await factory()
        if predicate(last):
            return last
        if loop.time() >= deadline:
            raise AssertionError(
                f"wait_until: условие не выполнено за {timeout}s (последнее={last!r})"
            )
        await asyncio.sleep(interval)


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


@pytest_asyncio.fixture(scope="session", autouse=True)
async def worker_ready(cfg: AppConfig) -> AsyncIterator[None]:
    """Прогреть lua-воркер до старта интеграционных тестов.

    На холодном стеке consumer-группа воркера и его соединение готовы не мгновенно.
    Гоняем тривиальную ``eval``-задачу через шину, пока воркер не ответит — так
    убираем гонку «задача ушла раньше готовности воркера» на медленном CI.
    """
    vk = valkey.from_url(cfg.valkey_url, decode_responses=True)
    bus = LuaBus(vk, cfg.LUA_TASK_STREAM, cfg.LUA_RESP_STREAM, default_timeout=5)
    loop = asyncio.get_event_loop()
    deadline = loop.time() + 60.0
    try:
        while True:
            try:
                res = await bus.call("eval", {"code": "return 1", "data": {}})
                if res.get("result") == 1:
                    break
            except LuaError:
                pass
            if loop.time() >= deadline:
                raise RuntimeError("lua-воркер не готов за 60s — прерываю тесты")
            await asyncio.sleep(0.5)
        yield
    finally:
        await vk.aclose()


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
