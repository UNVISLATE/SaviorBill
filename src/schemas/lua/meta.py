"""Схема данных самого шаблона (скрипта) для контекста Lua: ``ctx.lua.*``.

Отдаётся скрипту вместе с профильным контекстом (service/payment/trigger), чтобы
шаблон мог узнать собственные метаданные (id/slug/kind/actions) и общие настройки
(``ctx.lua.settings.*``). Настройки задаются один раз на скрипт и разделяются
всеми услугами/провайдерами, которые его используют, — вместо дублирования одной
и той же конфигурации (напр. учётных данных внешней панели) в каждой услуге.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LuaMeta(BaseModel):
    """Метаданные и настройки шаблона (``ctx.lua``)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str | None = None
    kind: str
    actions: list = Field(default_factory=list)
    settings: dict = Field(default_factory=dict)

    @classmethod
    def from_model(cls, m) -> "LuaMeta":  # noqa: ANN001 — SystemScriptsModel
        """Преобразовать ORM-скрипт в схему контекста ``lua``."""
        return cls.model_validate(m)


__all__ = ["LuaMeta"]
