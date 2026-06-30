"""DI для промокодов и их каталогов."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies.db import get_db_session
from models.promo_catalogs import PromoCatalogsMngr
from models.promo_codes import PromoCodesMngr


def get_promo_mngr(
    session: AsyncSession = Depends(get_db_session),
) -> PromoCodesMngr:
    """Менеджер промокодов."""
    return PromoCodesMngr(session)


def get_promo_catalog_mngr(
    session: AsyncSession = Depends(get_db_session),
) -> PromoCatalogsMngr:
    """Менеджер каталогов промокодов."""
    return PromoCatalogsMngr(session)


__all__ = [
    "PromoCodesMngr",
    "PromoCatalogsMngr",
    "get_promo_mngr",
    "get_promo_catalog_mngr",
]
