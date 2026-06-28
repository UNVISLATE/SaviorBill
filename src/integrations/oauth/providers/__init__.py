"""Авто-импорт всех скриптов-провайдеров в пакете.

Каждый ``*.py`` (кроме служебных) подключается автоматически, чтобы сработали
декораторы ``@reg(...)``. Достаточно просто положить новый файл рядом.
"""

from __future__ import annotations

import importlib
import pkgutil

for _mod in pkgutil.iter_modules(__path__):
    if not _mod.name.startswith("_"):
        importlib.import_module(f"{__name__}.{_mod.name}")
