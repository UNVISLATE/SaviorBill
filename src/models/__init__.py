from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase): ...


from .tenant import Tenant
from .server import AgentServer
from .role import Role
from .project import Project
from .profile import Profile
from .log import ApiLog

# Для Alembic и импортов приложения
__all__ = ["Base", "Tenant", "AgentServer", "Role", "Project", "Profile", "ApiLog"]
