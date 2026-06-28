"""Юнит-тесты иерархического RBAC (реестр, дерево, проверка доступа)."""

import pytest

from utils.rbac import all_perms, has_perm, perms_tree, reg_perm

pytestmark = pytest.mark.unit


def test_reg_perm_returns_path_and_registers():
    assert reg_perm("demo.read") == "demo.read"
    assert "demo.read" in all_perms()


def test_perms_tree_builds_nested_structure():
    reg_perm("things.read")
    reg_perm("things.edit")
    tree = perms_tree()
    assert "read" in tree["things"]
    assert "edit" in tree["things"]


def test_superadmin_wildcard_grants_everything():
    perms = {"*": True}
    assert has_perm(perms, "users.read") is True
    assert has_perm(perms, "anything.at.all") is True


def test_parent_true_inherits_children():
    perms = {"users": True}
    assert has_perm(perms, "users.read") is True
    assert has_perm(perms, "users.edit") is True


def test_explicit_leaf_permission():
    perms = {"users": {"read": True}}
    assert has_perm(perms, "users.read") is True
    assert has_perm(perms, "users.edit") is False


def test_no_permission_paths():
    assert has_perm(None, "users.read") is False
    assert has_perm({}, "users.read") is False
    assert has_perm({"topups": {"read": True}}, "users.read") is False


def test_intermediate_dict_node_is_truthy_branch():
    # Узел-словарь на конце пути считается «есть доступ к разделу».
    perms = {"users": {"read": {}}}
    assert has_perm(perms, "users.read") is True
