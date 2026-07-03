"""/api/v1/admin"""

from fastapi import APIRouter

from .catalogs import router as catalogs_router
from .email import router as email_router
from .lua import router as lua_router
from .me import router as me_router
from .media import router as media_router
from .oauth import router as oauth_router
from .orders import router as orders_router
from .promo import router as promo_router
from .purchases import router as purchases_router
from .roles import router as roles_router
from .services import router as services_router
from .settings import router as settings_router
from .triggers import router as triggers_router
from .users import router as users_router

router = APIRouter(prefix="/api/v1/admin")
router.include_router(me_router, tags=["admin: me"])
router.include_router(users_router, tags=["admin: users"])
router.include_router(roles_router, tags=["admin: roles"])
router.include_router(services_router, tags=["admin: services"])
router.include_router(catalogs_router, tags=["admin: catalogs"])
router.include_router(orders_router, tags=["admin: orders"])
router.include_router(purchases_router, tags=["admin: purchases"])
router.include_router(promo_router, tags=["admin: promo"])
router.include_router(oauth_router, tags=["admin: oauth"])
router.include_router(lua_router, tags=["admin: lua"])
router.include_router(email_router, tags=["admin: email"])
router.include_router(triggers_router, tags=["admin: triggers"])
router.include_router(media_router, tags=["admin: media"])
router.include_router(settings_router, tags=["admin: settings"])

__all__ = ["router"]
