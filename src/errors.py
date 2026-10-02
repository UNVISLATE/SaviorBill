"""Domain errors shared by application services."""

from __future__ import annotations


class LuaScriptVersionMissingError(RuntimeError):
    """A requested Lua script version is no longer available."""

    def __init__(self, script_id: int, requested_version: int) -> None:
        self.script_id = script_id
        self.requested_version = requested_version
        super().__init__(
            f"Lua script {script_id} version {requested_version} is unavailable"
        )


class AuthSessionLimitError(RuntimeError):
    """The account has reached its configured active-session limit."""


__all__ = ["AuthSessionLimitError", "LuaScriptVersionMissingError"]
