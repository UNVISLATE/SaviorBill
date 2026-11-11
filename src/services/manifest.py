"""Сервис авторитетной валидации манифестов и изоляции пользовательского ввода (sbuiSDK).

Гарантирует принцип Zero-Trust:
- Входящие данные покупателя валидируются строго по спецификации client_order_form
- Посторонние поля (Anti-Pollution) отсекаются
- Проверенные поля изолируются в ctx.order.form.<key>
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException, status
from pydantic import ValidationError

from schemas.manifest import FieldDefinition, FieldType, ScriptManifest


class ManifestValidationError(HTTPException):
    """Ошибка валидации пользовательской формы заказа по манифесту."""

    def __init__(self, detail: str, field_id: str | None = None) -> None:
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "form_validation_failed", "field": field_id, "message": detail},
        )


def parse_manifest(raw: str | dict[str, Any]) -> ScriptManifest:
    """Безопасный парсинг и валидация структуры manifest.json."""
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        return ScriptManifest.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Некорректная схема манифеста: {e}",
        ) from e


def _cond_values_match(actual: Any, expected: Any) -> bool:
    """Сравнить значение родительского поля с ожидаемым в условии ``depends_on``.

    Нормализует bool vs ``"true"``/``"false"`` без учёта регистра (так как в
    Python ``str(True) == "True"``, а в JSON-манифестах часто пишут ``"true"``).
    """
    if actual is None:
        return expected is None
    if isinstance(actual, bool) or isinstance(expected, bool):
        def _to_bool(v: Any) -> bool | None:
            if isinstance(v, bool):
                return v
            if isinstance(v, str):
                low = v.strip().lower()
                if low == "true":
                    return True
                if low == "false":
                    return False
            return None

        b_actual = _to_bool(actual)
        b_expected = _to_bool(expected)
        if b_actual is not None and b_expected is not None:
            return b_actual is b_expected
        return False
    return actual == expected or str(actual) == str(expected)


def _is_field_active(field_def: FieldDefinition, form_values: dict[str, Any]) -> bool:
    """Проверка условия активности/видимости поля (depends_on)."""
    cond = field_def.depends_on
    if not cond:
        return True

    parent_val = form_values.get(cond.field)
    if cond.equals is not None and not _cond_values_match(parent_val, cond.equals):
        return False
    if cond.not_equals is not None and _cond_values_match(parent_val, cond.not_equals):
        return False
    if cond.in_values is not None and not any(
        _cond_values_match(parent_val, candidate) for candidate in cond.in_values
    ):
        return False
    if cond.not_in_values is not None and any(
        _cond_values_match(parent_val, candidate) for candidate in cond.not_in_values
    ):
        return False
    return True


def validate_client_order_form(
    manifest: ScriptManifest,
    user_input: dict[str, Any] | None,
) -> dict[str, Any]:
    """Авторитетная валидация формы заказа по клиентскому манифесту.

    :param manifest: Корневой манифест скрипта интеграции.
    :param user_input: Сырые данные, переданные клиентом при чекауте.
    :return: Очищенный, валидированный словарь значений для ctx.order.form.
    :raises ManifestValidationError: при нарушении правил валидации полей.
    """
    raw_data = user_input or {}
    sanitized: dict[str, Any] = {}

    for field_def in manifest.client_order_form:
        fid = field_def.id

        # Проверка условия зависимости
        if not _is_field_active(field_def, sanitized):
            continue

        raw_val = raw_data.get(fid)

        # 1. Проверка обязательности поля
        is_empty = raw_val is None or (isinstance(raw_val, str) and not raw_val.strip())
        if is_empty:
            if field_def.required:
                raise ManifestValidationError(
                    detail=f"Поле {field_def.label!r} обязательно к заполнению",
                    field_id=fid,
                )
            if field_def.default is not None:
                sanitized[fid] = field_def.default
            continue

        # 2. Валидация в зависимости от типа поля
        if field_def.type in (FieldType.TEXT, FieldType.PASSWORD, FieldType.TEXTAREA):
            val_str = str(raw_val).strip()

            if field_def.min_length is not None and len(val_str) < field_def.min_length:
                raise ManifestValidationError(
                    detail=f"Длина поля {field_def.label!r} должна быть не менее {field_def.min_length} символов",
                    field_id=fid,
                )
            if field_def.max_length is not None and len(val_str) > field_def.max_length:
                raise ManifestValidationError(
                    detail=f"Длина поля {field_def.label!r} не должна превышать {field_def.max_length} символов",
                    field_id=fid,
                )
            if field_def.regex:
                try:
                    if not re.match(field_def.regex, val_str):
                        err_msg = field_def.regex_error or f"Поле {field_def.label!r} имеет неверный формат"
                        raise ManifestValidationError(detail=err_msg, field_id=fid)
                except re.error:
                    pass

            sanitized[fid] = val_str

        elif field_def.type in (FieldType.NUMBER, FieldType.RANGE):
            try:
                dec_val = Decimal(str(raw_val).strip())
            except (InvalidOperation, ValueError):
                raise ManifestValidationError(
                    detail=f"Поле {field_def.label!r} должно быть числом",
                    field_id=fid,
                ) from None

            if field_def.min is not None and dec_val < field_def.min:
                raise ManifestValidationError(
                    detail=f"Значение поля {field_def.label!r} не может быть меньше {field_def.min}",
                    field_id=fid,
                )
            if field_def.max is not None and dec_val > field_def.max:
                raise ManifestValidationError(
                    detail=f"Значение поля {field_def.label!r} не может превышать {field_def.max}",
                    field_id=fid,
                )
            if field_def.step is not None and field_def.min is not None:
                step_dec = field_def.step
                if step_dec > 0 and ((dec_val - field_def.min) % step_dec) != Decimal("0"):
                    raise ManifestValidationError(
                        detail=f"Значение поля {field_def.label!r} должно быть кратно шагу {step_dec}",
                        field_id=fid,
                    )

            sanitized[fid] = int(dec_val) if dec_val % 1 == 0 else float(dec_val)

        elif field_def.type == FieldType.SELECT:
            val_str = str(raw_val).strip()
            allowed = {opt.value for opt in (field_def.options or [])}
            if val_str not in allowed:
                raise ManifestValidationError(
                    detail=f"Недопустимое значение для поля {field_def.label!r}. Допустимо: {', '.join(allowed)}",
                    field_id=fid,
                )
            sanitized[fid] = val_str

        elif field_def.type == FieldType.TOGGLE:
            if isinstance(raw_val, bool):
                sanitized[fid] = raw_val
            elif isinstance(raw_val, str):
                sanitized[fid] = raw_val.strip().lower() in ("true", "1", "yes", "on")
            else:
                sanitized[fid] = bool(raw_val)

        elif field_def.type == FieldType.DATETIME:
            val_str = str(raw_val).strip()
            # Базовая проверка длины и формата ISO-строки
            if len(val_str) < 10:
                raise ManifestValidationError(
                    detail=f"Поле {field_def.label!r} должно быть датой в формате ISO 8601",
                    field_id=fid,
                )
            sanitized[fid] = val_str

        else:
            sanitized[fid] = raw_val

    return sanitized


__all__ = [
    "ManifestValidationError",
    "parse_manifest",
    "validate_client_order_form",
]
