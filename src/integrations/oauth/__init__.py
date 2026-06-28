"""OAuth-интеграции. Импорт провайдеров для само-регистрации в реестре."""

from integrations.oauth import providers  # noqa: F401  (триггерит регистрацию)
from integrations.oauth.base import OAuthRT, OIDCBase
from integrations.oauth.registry import get_provider, known, reg

__all__ = ["OAuthRT", "OIDCBase", "get_provider", "known", "reg"]
