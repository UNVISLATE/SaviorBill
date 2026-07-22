"""/api/v1/admin"""

from fastapi import APIRouter

from .catalogs import router as catalogs_router
from .audit import router as audit_router
from .analytics import router as analytics_router
from .email import router as email_router
from .email_domains import router as email_domains_router
from .lua import router as lua_router
from .me import router as me_router
from .media import router as media_router
from .oauth import router as oauth_router
from .orders import router as orders_router
from .promo import router as promo_router
from .purchases import router as purchases_router
from .roles import router as roles_router
from .services import router as services_router
from .servicekeys import router as servicekeys_router
from .settings import router as settings_router
from .tasks import router as tasks_router
from .triggers import router as triggers_router
from .users import router as users_router

router = APIRouter(prefix="/api/v1/admin")
# Каждый саброутер получает свой сегмент пути здесь, а не дублирует его в
# каждом отдельном @router.get(...)/... внутри своего файла (см. upd_plan для
# истории вопроса). roles_router — исключение: в одном файле смешаны два
# разных ресурса (/perms и /roles), поэтому единый префикс сюда не накладываем.
router.include_router(me_router, tags=["admin: me"])
router.include_router(users_router, prefix="/users", tags=["admin: users"])
router.include_router(roles_router, tags=["admin: roles"])
router.include_router(services_router, prefix="/services", tags=["admin: services"])
router.include_router(servicekeys_router, prefix="/services", tags=["admin: services"])
router.include_router(catalogs_router, prefix="/catalogs", tags=["admin: catalogs"])
router.include_router(orders_router, prefix="/orders", tags=["admin: orders"])
router.include_router(purchases_router, prefix="/purchases", tags=["admin: purchases"])
router.include_router(promo_router, prefix="/promo", tags=["admin: promo"])
router.include_router(oauth_router, prefix="/oauth", tags=["admin: oauth"])
router.include_router(lua_router, prefix="/lua", tags=["admin: lua"])
router.include_router(email_router, prefix="/email/templates", tags=["admin: email"])
router.include_router(triggers_router, prefix="/triggers", tags=["admin: triggers"])
router.include_router(media_router, prefix="/media", tags=["admin: media"])
router.include_router(settings_router, prefix="/settings", tags=["admin: settings"])
router.include_router(
    email_domains_router,
    prefix="/settings/email-domains",
    tags=["admin: settings"],
)
router.include_router(audit_router, prefix="/audit", tags=["admin: audit"])
# tasks_router без единого верхнего тега здесь: media.py/lua.py сами задают
# "admin: tasks/media" и "admin: tasks/lua" при регистрации внутри пакета
# (см. api/v1/admin/tasks/__init__.py) — тот же паттерн, что у analytics.
router.include_router(tasks_router, prefix="/tasks")
# analytics_router: единый префикс "/analytics" задан здесь (тот же паттерн,
# что у tasks_router выше); basic_router/advanced_router внутри пакета
# объявляют только свой суффикс ("/basic"/"/advanced"), теги — при монтировании
# в admin/analytics/__init__.py.
router.include_router(analytics_router, prefix="/analytics")

__all__ = ["router"]
