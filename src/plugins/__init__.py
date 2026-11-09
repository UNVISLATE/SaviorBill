"""Модуль расширений ядра SaviorBill (Core Plugins Engine)."""

from .base import BasePlugin, PluginContext
from .manager import PluginMngr, PluginManifestSchema, PluginPermissionSchema
from .migrator import PluginMigrator

__all__ = [
    "BasePlugin",
    "PluginContext",
    "PluginMngr",
    "PluginManifestSchema",
    "PluginPermissionSchema",
    "PluginMigrator",
]
