from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase): ...


# Импорт моделей после объявления Base (порядок важен для регистрации в metadata).
from .roles import Role
from .user import Account
from .oauth_cfg import OAuthCfg
from .oauth_conn import OAuthConn
from .luadb import LuaScript
from .svc_catalog import SvcCatalog
from .service import Service
from .digikey import DigiKey
from .user_svc import UserSvc
from .pay_provider import PayProvider
from .payment import Payment
from .promocode import Promocode
from .promo_use import PromoUse
from .setting import Setting
from .log import ApiLog

# Для Alembic и импортов приложения
__all__ = [
    "Base",
    "Role",
    "Account",
    "OAuthCfg",
    "OAuthConn",
    "LuaScript",
    "SvcCatalog",
    "Service",
    "DigiKey",
    "UserSvc",
    "PayProvider",
    "Payment",
    "Promocode",
    "PromoUse",
    "Setting",
    "ApiLog",
]
