"""Google — стандартный OIDC-провайдер (пример «как есть»)."""

from __future__ import annotations

from integrations.oauth.base import OIDCBase
from integrations.oauth.registry import reg


@reg("google")
class Google(OIDCBase):
    """Google полностью соответствует OIDC: хватает issuer + discovery."""

    default_issuer = "https://accounts.google.com"
