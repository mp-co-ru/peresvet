"""Пользовательские папки иерархии (класс prsFolder).

Папка не является prsModelNode: этот класс уже занят служебными корнями,
узлом cn=system и папками каталога методов. Формула parentId для
prsModelNode здесь не меняется.
"""
from __future__ import annotations

from typing import Any

ROOT_NAMES = ("objects", "tags", "connectors", "schedules", "dataStorages")

_FILTER_META = set("()\\*\x00,=<>")

# Какие классы допустимы внутри папки данного корня.
CONTEXT_CHILD_CLASSES = {
    "objects": frozenset({"prsFolder", "prsObject", "prsTag"}),
    "tags": frozenset({"prsFolder", "prsTag"}),
    "connectors": frozenset({"prsFolder", "prsConnector"}),
    "schedules": frozenset({"prsFolder", "prsSchedule"}),
    "dataStorages": frozenset({"prsFolder", "prsDataStorage"}),
}

# Класс -> его SUP. Нужен, чтобы выбрать структурный класс, а не prsModelNode,
# независимо от порядка objectClass, который вернул slapd.
_SUPERIOR_OF = {
    "prsModelNode": "top",
    "prsTag": "prsModelNode",
    "prsAlertLevel": "prsModelNode",
    "prsDataStorage": "prsModelNode",
    "prsConnector": "prsModelNode",
    "prsAlert": "prsModelNode",
    "prsMethod": "prsModelNode",
    "prsObject": "prsModelNode",
    "prsTemplate": "prsModelNode",
    "prsConstant": "prsModelNode",
    "prsSchedule": "prsModelNode",
    "prsView": "prsModelNode",
    "prsJsonConfig": "top",
    "prsConnectorTagData": "prsModelNode",
    "prsMethodParameter": "prsModelNode",
    "prsDatastorageTagData": "prsModelNode",
    "prsDatastorageAlertData": "prsModelNode",
    "prsDatastorageOperation": "prsModelNode",
    "prsDatastorageOperationParameter": "prsModelNode",
    "prsDatastorageTagOperation": "prsModelNode",
    "prsDatastorageTagOperationParameter": "prsModelNode",
    "prsFolder": "prsModelNode",
    "alias": "top",
    "extensibleObject": "top",
}

_IGNORED_ON_MOVE = frozenset({"prsModelNode", "alias", "extensibleObject", "top"})

FOLDER_LDAP_KEYS = ("cn", "description", "prsIndex", "prsActive")

ENTITY_DELETE_ROUTING = {
    "prsObject": "prsObject.api_crud.delete",
    "prsTag": "prsTag.api_crud.delete",
    "prsAlert": "prsAlert.api_crud.delete",
    "prsMethod": "prsMethod.api_crud.delete",
    "prsConnector": "prsConnector.api_crud.delete",
    "prsSchedule": "prsSchedule.api_crud.delete",
    "prsDataStorage": "prsDataStorage.api_crud.delete",
}


def _decode_class_name(item: Any) -> str:
    if isinstance(item, bytes):
        item = item.decode()
    return str(item or "").strip()


def _is_superior_of(candidate: str, other: str) -> bool:
    seen: set[str] = set()
    current = _SUPERIOR_OF.get(other)
    while current and current not in seen:
        if current == candidate:
            return True
        seen.add(current)
        current = _SUPERIOR_OF.get(current)
    return False


def node_class_from_object_classes(object_classes) -> str:
    """Структурный класс узла.

    OpenLDAP хранит структурный класс вместе с SUP (prsFolder, prsModelNode, top).
    ``get_node_class`` берёт первое значение после ``top``. Если slapd отдаёт
    SUP раньше структурного класса, первое значение было бы prsModelNode и
    папка выглядела бы как служебный корень. Здесь остаётся самый конкретный
    класс. Если в списке один класс, результат совпадает с прежней формулой.
    """
    names: list[str] = []
    for item in object_classes or []:
        text = _decode_class_name(item)
        if text and text not in names:
            names.append(text)
    without_top = [name for name in names if name != "top"]
    if not without_top:
        return "top" if "top" in names else ""
    specific = [
        name
        for name in without_top
        if not any(_is_superior_of(name, other) for other in without_top if other != name)
    ]
    return (specific or without_top)[0]


def folder_name_error(cn: str | None) -> str | None:
    """Имя ``system`` занято служебным узлом и не годится для папки."""
    if str(cn or "").strip() == "system":
        return "Имя system зарезервировано."
    return None


def node_ref_error(node_ref: str | None) -> str | None:
    """Ссылка на узел — GUID или короткое имя, не DN и не кусок LDAP-фильтра."""
    text = str(node_ref or "")
    if not text or any(char in text for char in _FILTER_META):
        return "Некорректный идентификатор узла."
    return None


def folder_ldap_attributes(raw: dict | None, *, creating: bool) -> dict:
    """Атрибуты папки для LDAP. objectClass выставляется только при создании."""
    source = dict(raw or {})
    attrs: dict = {}
    if "cn" in source and source["cn"] not in (None, ""):
        cn = source["cn"]
        if isinstance(cn, list):
            cn = cn[0] if cn else ""
        text = str(cn).strip() if isinstance(cn, str) else cn
        if text not in (None, ""):
            attrs["cn"] = text
    description = source.get("description")
    if isinstance(description, list):
        description = description[0] if description else None
    if isinstance(description, str):
        description = description.strip()
    if description not in (None, ""):
        attrs["description"] = description
    if source.get("prsIndex") is not None:
        attrs["prsIndex"] = source["prsIndex"]
    if "prsActive" in source and source["prsActive"] is not None:
        attrs["prsActive"] = source["prsActive"]
    elif creating:
        attrs["prsActive"] = True
    if creating:
        attrs["objectClass"] = ["prsFolder"]
    return attrs


def _scope_subtree() -> int:
    from src.common.hierarchy import CN_SCOPE_SUBTREE

    return CN_SCOPE_SUBTREE


async def _node_cn(hierarchy, node_id: str) -> str:
    rows = await hierarchy.search({"id": node_id, "attributes": ["cn"]})
    if not rows:
        return ""
    raw = (rows[0][2] or {}).get("cn") or [""]
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    if isinstance(raw, bytes):
        raw = raw.decode()
    return str(raw or "")


async def root_context(hierarchy, node_id: str | None) -> str | None:
    """Контекст ветки: objects, tags, connectors, schedules или dataStorages.

    None, если узел лежит под запрещённым родителем (cn=system, каталог
    методов, тег, тревога, метод, привязка).
    """
    current = node_id
    seen: set[str] = set()
    for _ in range(64):
        if not current or current in seen:
            return None
        seen.add(current)
        try:
            node_class = await hierarchy.get_node_class(current)
        except Exception:
            return None
        cn = await _node_cn(hierarchy, current)
        if cn == "system":
            return None
        if node_class == "prsModelNode":
            if cn not in CONTEXT_CHILD_CLASSES:
                return None
            # Корнем ветки считается только прямой потомок cn=prs.
            # Одноимённый prsModelNode в каталоге методов корнем не является.
            try:
                parent_id, _ = await hierarchy.get_parent(current)
            except Exception:
                return None
            if await _node_cn(hierarchy, parent_id) == "prs":
                return cn
            return None
        if node_class == "prsObject":
            return "objects"
        if node_class != "prsFolder":
            return None
        try:
            parent_id, _ = await hierarchy.get_parent(current)
        except Exception:
            return None
        if not parent_id or parent_id == current:
            return None
        current = parent_id
    return None


async def resolve_folder_parent_id(hierarchy, parent_ref: str | None) -> tuple[str | None, str | None]:
    """Имя корня или UUID -> id узла. Второе значение — текст ошибки."""
    if parent_ref in (None, ""):
        return None, "Укажите родителя папки."
    if parent_ref == "methods":
        return None, "Папку нельзя создать в каталоге методов."
    if parent_ref in ROOT_NAMES:
        node_id = await hierarchy.get_node_id(f"cn={parent_ref},cn=prs")
        if not node_id:
            return None, f"Корень {parent_ref} не найден."
        return node_id, None
    ref_error = node_ref_error(str(parent_ref))
    if ref_error:
        return None, ref_error
    return str(parent_ref), None


async def folder_parent_allowed(hierarchy, parent_id: str | None) -> bool:
    if not parent_id:
        return False
    return await root_context(hierarchy, parent_id) in CONTEXT_CHILD_CLASSES


async def folder_accepts_child(hierarchy, folder_id: str, child_class: str) -> bool:
    context = await root_context(hierarchy, folder_id)
    if not context:
        return False
    return child_class in CONTEXT_CHILD_CLASSES[context]


async def is_under(hierarchy, node_id: str | None, ancestor_id: str | None) -> bool:
    """True, если node_id совпадает с ancestor_id или лежит внутри него."""
    if not node_id or not ancestor_id:
        return False
    current = node_id
    seen: set[str] = set()
    for _ in range(64):
        if not current or current in seen:
            return False
        if current == ancestor_id:
            return True
        seen.add(current)
        try:
            parent_id, _ = await hierarchy.get_parent(current)
        except Exception:
            return False
        current = parent_id
    return False


async def subtree_child_classes(hierarchy, node_id: str) -> set[str]:
    rows = await hierarchy.search(
        {
            "base": node_id,
            "scope": _scope_subtree(),
            "filter": {"cn": ["*"]},
            "attributes": ["cn"],
            "deref": False,
        }
    )
    found: set[str] = set()
    for row in rows or []:
        if row[0] == node_id:
            continue
        try:
            name = await hierarchy.get_node_class(row[0])
        except Exception:
            continue
        if name and name not in _IGNORED_ON_MOVE:
            found.add(name)
    return found


async def folder_move_error(hierarchy, folder_id: str, new_parent_id: str) -> str | None:
    if folder_id == new_parent_id or await is_under(hierarchy, new_parent_id, folder_id):
        return "Нельзя переместить папку внутрь самой себя или своей подиерархии."
    source = await root_context(hierarchy, folder_id)
    target = await root_context(hierarchy, new_parent_id)
    if not target:
        return "Недопустимый родитель папки."
    if source != target:
        return "Контекст нового родителя не совпадает с контекстом папки."
    allowed = CONTEXT_CHILD_CLASSES[target]
    extra = await subtree_child_classes(hierarchy, folder_id)
    blocked = sorted(name for name in extra if name not in allowed)
    if blocked:
        return "В папке есть узлы, которые нельзя перенести в этот контекст."
    return None
