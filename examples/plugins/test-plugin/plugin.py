from plugins.base import BasePlugin
from .routers import admin_router, public_router


class TestPlugin(BasePlugin):
    """Демонстрационный тестовый плагин (автор: UNVI.XYZ)."""

    async def on_load(self) -> None:
        self.include_router(admin_router)
        self.include_router(public_router)

    async def on_unload(self) -> None:
        pass
