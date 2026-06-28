"""/api/v1/admin"""

from fastapi import APIRouter

from .catalogs import router as catalogs_router
from .lua import router as lua_router
from .oauth import router as oauth_router
from .orders import router as orders_router
from .purchases import router as purchases_router
from .roles import router as roles_router
from .services import router as services_router
from .users import router as users_router

router = APIRouter(prefix="/api/v1/admin")
router.include_router(users_router, tags=["admin: users"])
router.include_router(roles_router, tags=["admin: roles"])
router.include_router(services_router, tags=["admin: services"])
router.include_router(catalogs_router, tags=["admin: catalogs"])
router.include_router(orders_router, tags=["admin: orders"])
router.include_router(purchases_router, tags=["admin: purchases"])
router.include_router(oauth_router, tags=["admin: oauth"])
router.include_router(lua_router, tags=["admin: lua"])

__all__ = ["router"]
