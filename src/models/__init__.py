from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase): ...


from .roles import Role
from .user import UserModel, UserMngr
from .oauth_providers import OAuthProvidersModel, OAuthProvidersMngr
from .user_oauth import UserOauthModel, UserOauthMngr
from .system_scripts import SystemScriptsModel, SystemScriptsMngr
from .service_catalogs import ServiceCatalogsModel, ServiceCatalogsMngr
from .service import ServiceModel, ServiceMngr
from .service_attachment import ServiceAttachmentModel, ServiceAttachmentMngr
from .service_keys import ServiceKeysModel, ServiceKeysMngr
from .user_services import UserServicesModel, UserServicesMngr
from .payment_providers import PaymentProvidersModel, PaymentProvidersMngr
from .user_payments import UserPaymentsModel, UserPaymentsMngr
from .promo_codes import PromoCodesModel, PromoCodesMngr
from .promo_catalogs import PromoCatalogsModel, PromoCatalogsMngr
from .promo_use import PromoUseModel
from .system_settings import SystemSettingsModel, SystemSettingsMngr
from .system_media import SystemMediaModel, SystemMediaMngr
from .email_templates import EmailModel, EmailMngr
from .triggers import TriggerModel, TriggerMngr
from .log import LogModel

__all__ = [
    "Base",
    "Role",
    "UserModel",
    "UserMngr",
    "OAuthProvidersModel",
    "OAuthProvidersMngr",
    "UserOauthModel",
    "UserOauthMngr",
    "SystemScriptsModel",
    "SystemScriptsMngr",
    "ServiceCatalogsModel",
    "ServiceCatalogsMngr",
    "ServiceModel",
    "ServiceMngr",
    "ServiceAttachmentModel",
    "ServiceAttachmentMngr",
    "ServiceKeysModel",
    "ServiceKeysMngr",
    "UserServicesModel",
    "UserServicesMngr",
    "PaymentProvidersModel",
    "PaymentProvidersMngr",
    "UserPaymentsModel",
    "UserPaymentsMngr",
    "PromoCodesModel",
    "PromoCodesMngr",
    "PromoCatalogsModel",
    "PromoCatalogsMngr",
    "PromoUseModel",
    "SystemSettingsModel",
    "SystemSettingsMngr",
    "SystemMediaModel",
    "SystemMediaMngr",
    "EmailModel",
    "EmailMngr",
    "TriggerModel",
    "TriggerMngr",
    "LogModel",
]
