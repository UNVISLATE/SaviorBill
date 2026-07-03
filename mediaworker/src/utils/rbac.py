"""Проверка иерархических прав (копия минимальной логики billing RBAC).

Домены разделены: mediaworker не импортирует код billing, поэтому крошечная
проверка ``has_perm`` продублирована здесь.
"""

from __future__ import annotations


def has_perm(perms: dict | None, path: str) -> bool:
    """Проверить, даёт ли набор прав ``perms`` доступ к ``path`` (с наследованием)."""
    if not perms:
        return False
    node: object = perms
    for seg in path.split("."):
        if node is True:
            return True
        if not isinstance(node, dict):
            return False
        if node.get("*") is True:
            return True
        if seg not in node:
            return False
        node = node[seg]
    return node is True or isinstance(node, dict)


__all__ = ["has_perm"]
