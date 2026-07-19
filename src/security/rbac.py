"""Иерархический RBAC: реестр прав, дерево и проверка доступа."""

from __future__ import annotations

# Глобальный реестр всех объявленных в приложении прав (для админ-UI).
_REGISTRY: set[str] = set()


def reg_perm(path: str) -> str:
    """Зарегистрировать право (вызывается при объявлении роута). Возвращает path."""
    _REGISTRY.add(path)
    return path


def all_perms() -> list[str]:
    """Плоский отсортированный список всех известных прав."""
    return sorted(_REGISTRY)


def perms_tree() -> dict:
    """Собрать дерево прав из реестра: ``{"users": {"read": {}, "edit": {}}}``."""
    tree: dict = {}
    for path in _REGISTRY:
        node = tree
        for seg in path.split("."):
            node = node.setdefault(seg, {})
    return tree


def has_perm(perms: dict | None, path: str) -> bool:
    """Проверить, даёт ли набор прав ``perms`` доступ к ``path`` (с наследованием)."""
    if not perms:
        return False
    node: object = perms
    for seg in path.split("."):
        if node is True:
            return True  # родитель открыт целиком
        if not isinstance(node, dict):
            return False
        if node.get("*") is True:
            return True  # wildcard на этом уровне
        if seg not in node:
            return False
        node = node[seg]
    return node is True or isinstance(node, dict)


__all__ = ["reg_perm", "all_perms", "perms_tree", "has_perm"]
