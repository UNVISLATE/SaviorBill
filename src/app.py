from fastapi import FastAPI

from lifespan import lifespan
from utils.config import AppConfig

settings = AppConfig()

DESCRIPTION = "**SaviorBill** — событийная биллинг-система."

TAGS_META = [
    {"name": "auth", "description": "Регистрация, вход, JWT-токены, выход."},
    {"name": "oauth", "description": "Вход через внешних OIDC-провайдеров."},
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
]

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=DESCRIPTION,
    openapi_tags=TAGS_META,
    lifespan=lifespan,
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
