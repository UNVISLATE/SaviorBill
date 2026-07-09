"""Генерация markdown-описания полей тела запроса для Swagger.

Строит булет-список полей pydantic-схемы (имя + описание из ``Field(description=)``
+ пометка обязательности), чтобы вставлять его в ``description`` роутов.

NOTE: по решению владельца проекта этот helper больше НЕ используется в роутах
(дублировал то, что и так видно в схеме тела запроса в Swagger UI) — оставлен
только как утилита на случай точечной необходимости, вызывать без явной нужды
не стоит.
"""

from __future__ import annotations

from pydantic import BaseModel
from pydantic.fields import FieldInfo

_OPTIONAL_MARK = "`optional`"
_REQUIRED_MARK = "`required`"


def _field_line(name: str, field: FieldInfo) -> str:
    """Собрать строку булет-списка для одного поля."""
    desc = (field.description or "").strip()
    required = field.is_required()
    if not desc:
        desc = _REQUIRED_MARK if required else _OPTIONAL_MARK
    elif _OPTIONAL_MARK not in desc and _REQUIRED_MARK not in desc:
        # Пометку обязательности добавляем автоматически, если её нет в описании.
        desc = f"{desc} {_REQUIRED_MARK if required else _OPTIONAL_MARK}"
    return f"- `{name}`: {desc}"


def fields_doc(model: type[BaseModel], title: str = "Request body (JSON)") -> str:
    """Markdown-описание полей схемы для вставки в ``description`` роута.

    :arg model: pydantic-схема тела запроса.
    :arg title: заголовок блока (жирным) над списком полей.
    :return: markdown-текст с булет-списком полей.
    """
    lines = [f"**{title}:**", ""]
    lines.extend(_field_line(name, field) for name, field in model.model_fields.items())
    return "\n".join(lines)


def with_fields(
    prose: str, model: type[BaseModel], title: str = "Request body (JSON)"
) -> str:
    """Склеить прозу описания роута с булет-списком полей схемы.

    :arg prose: вводный текст описания ручки.
    :arg model: pydantic-схема тела запроса.
    :arg title: заголовок блока полей.
    :return: итоговый ``description`` для декоратора роута.
    """
    prose = prose.strip()
    block = fields_doc(model, title)
    return f"{prose}\n\n{block}" if prose else block


__all__ = ["fields_doc", "with_fields"]
