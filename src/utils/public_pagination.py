"""Помощник квантования и нормализации пагинации для неавторизованных/публичных запросов.

Цель:
1. Защита от перегрузки базы данных и DDoS через чрезмерно большие страницы.
2. Предотвращение фрагментации кэша: запросы со случайными значениями limit (например 7, 13, 29)
   квантуются к фиксированному шагу (5 или 10), сводя число уникальных вариантов
   кэш-ключей к минимуму и доводя Cache Hit Rate до максимума.
"""

from __future__ import annotations


def snap_public_limit_setting(val: int, step: int = 10) -> int:
    """Округление настройки максимального limit при сохранении в конфигурацию.

    Правила (по ТЗ):
    - Шаг step может быть строго 5 или 10 (иначе fallback 10).
    - Если значение <= step (например 4), округляется до step (5 или 10).
    - В остальных случаях округляется вниз до меньшего значения, кратного шагу.
    - Ограничено сверху потолком системы 200.
    """
    if step not in (5, 10):
        step = 10
    if val <= step:
        return step
    rounded = (val // step) * step
    return min(rounded, 200)


def normalize_public_limit(requested_limit: int, max_limit: int = 50, step: int = 10) -> int:
    """Нормализовать запрошенный клиентом limit для неавторизованного запроса.

    - step: 5 или 10 (по умолчанию 10).
    - max_limit: максимальный разрешённый лимит для публичных клиентов (по умолчанию 50).
    - requested_limit квантуется к ближайшему кратному step (минимум 1 шаг, не более max_limit).
    """
    if step not in (5, 10):
        step = 10
    clamped_max = snap_public_limit_setting(max_limit, step)
    if requested_limit <= 0:
        return step
    # Округление до ближайшего кратного шага (минимум step)
    rounded = max(step, round(requested_limit / step) * step)
    return min(rounded, clamped_max)


__all__ = ["snap_public_limit_setting", "normalize_public_limit"]
