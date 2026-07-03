import logging

from fastapi import FastAPI

from lifespan import lifespan
from utils.config import AppConfig, APP_NAME, APP_VERSION
from utils.telemetry import metrics_app, setup_telemetry

settings = AppConfig()

setup_telemetry(APP_NAME)


logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
)

DESCRIPTION = (
    "**SaviorBill** — событийная биллинг-система.\n\n"
    f"Медиа-подсистема (загрузка/конвертация/отдача файлов) вынесена в отдельный "
    f"сервис **mediaworker** — его OpenAPI-документация (форматы загрузки и "
    f"ответов) доступна по адресу [{settings.media_docs_url}]({settings.media_docs_url})."
    if settings.DOCS_ENABLED
    else "**SaviorBill** — событийная биллинг-система."
)

TAGS_META = [
    {"name": "auth", "description": "Регистрация, вход, JWT-токены, выход."},
    {"name": "oauth", "description": "Вход через внешних OAuth-провайдеров (Lua)."},
    {"name": "catalog", "description": "Публичный каталог услуг и дерево каталогов."},
    {
        "name": "user",
        "description": "Профиль, услуги, платежи и привязки пользователя.",
    },
    {
        "name": "promocodes",
        "description": "Активация промокодов (бонус/скидка/услуга).",
    },
    {"name": "callback", "description": "Колбэки платёжных систем и OAuth."},
    {"name": "media", "description": "Загрузка медиа-файлов (изображения, аватарки)."},
    {"name": "admin: me", "description": "Профиль текущего администратора."},
    {"name": "admin: users", "description": "Список и редактирование пользователей."},
    {"name": "admin: roles", "description": "Роли и каталог прав (RBAC)."},
    {"name": "admin: services", "description": "Управление услугами каталога."},
    {"name": "admin: catalogs", "description": "Управление каталогами услуг."},
    {"name": "admin: orders", "description": "Выданные услуги и ручная выдача."},
    {"name": "admin: purchases", "description": "Платежи и платёжные провайдеры."},
    {"name": "admin: promo", "description": "Каталоги промокодов и выпуск кодов."},
    {"name": "admin: oauth", "description": "Управление OAuth-провайдерами."},
    {"name": "admin: lua", "description": "Загрузка/редактирование Lua-скриптов."},
    {"name": "admin: email", "description": "Email-шаблоны рассылок."},
    {
        "name": "admin: triggers",
        "description": "Триггеры: событие → действие (email/lua).",
    },
    {"name": "admin: audit", "description": "Аудит финансовых и админ-действий."},
]

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description=DESCRIPTION,
    openapi_tags=TAGS_META,
    lifespan=lifespan,
    docs_url="/docs" if settings.DOCS_ENABLED else None,
    redoc_url="/redoc" if settings.DOCS_ENABLED else None,
    openapi_url="/openapi.json" if settings.DOCS_ENABLED else None,
)

# Экспорт метрик Prometheus (/metrics). None, если prometheus_client не установлен
# или METRICS_ENABLED=false — тогда эндпоинт отсутствует.
_metrics = metrics_app()
if _metrics is not None:
    app.mount("/metrics", _metrics)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
