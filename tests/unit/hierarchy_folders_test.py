"""Пользовательские папки prsFolder.

Живой slapd с objectClass prsFolder здесь не поднимается. Классификация
проверяется на списке классов, который OpenLDAP возвращает для структурного
класса и его SUP: сначала класс, которым создавали запись, затем prsModelNode
и top. Второй пример — тот же набор, если SUP оказался раньше.
"""
import asyncio
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import ldap

from src.common.hierarchy import CN_SCOPE_ONELEVEL, Hierarchy
from src.common.hierarchy_folders import node_class_from_object_classes
from src.common.model_crud_svc import ModelCRUDSvc
from src.services.alerts.model_crud.alerts_model_crud_settings import AlertsModelCRUDSettings
from src.services.connectors.model_crud.connectors_model_crud_settings import ConnectorsModelCRUDSettings
from src.services.dataStorages.model_crud.dataStorages_model_crud_settings import (
    DataStoragesModelCRUDSettings,
)
from src.services.objects.api_crud.objects_api_crud_svc import FolderUpdate
from src.services.objects.model_crud.objects_model_crud_settings import ObjectsModelCRUDSettings
from src.services.objects.model_crud.objects_model_crud_svc import ObjectsModelCRUD
from src.services.schedules.model_crud.schedules_model_crud_settings import SchedulesModelCRUDSettings
from src.services.tags.model_crud.tags_model_crud_settings import TagsModelCRUDSettings

ROOT = Path(__file__).resolve().parents[2]
DASHBOARD = ROOT / "src/grafana/configurator/Configurator.json"
CODE_VERSION = "20261029-user-folders-v1"


class _Logger:
    def error(self, *args, **kwargs):
        pass

    def debug(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass


class Mem:
    def __init__(self):
        self.nodes = {}
        self.added = []
        self.deleted = []
        self.moved = []

    def put(self, node_id, parent, object_class, cn):
        self.nodes[node_id] = {"parent": parent, "oc": object_class, "cn": cn}

    async def does_node_exist(self, node_id):
        return node_id in self.nodes

    async def get_node_class(self, node_id):
        node = self.nodes.get(node_id)
        if not node:
            raise ValueError(f"Узел {node_id} не найден.")
        return node["oc"]

    async def get_parent(self, node_id):
        parent = self.nodes[node_id]["parent"]
        if not parent:
            raise ValueError("Родительский узел не найден.")
        return parent, None

    async def get_node_id(self, node_dn):
        cn = node_dn.split(",")[0].split("=", 1)[1]
        for node_id, node in self.nodes.items():
            if node["cn"] == cn and node["parent"] == "prs":
                return node_id
        return None

    def _row(self, node_id):
        node = self.nodes[node_id]
        classes = [node["oc"], "top"] if node["oc"] == "prsModelNode" else [node["oc"], "prsModelNode", "top"]
        return (node_id, f"cn={node['cn']}", {"cn": [node["cn"]], "objectClass": classes})

    def _match(self, node, filt):
        for key, values in (filt or {}).items():
            if key == "objectClass" and node["oc"] not in values:
                return False
            if key == "cn" and "*" not in values and node["cn"] not in values:
                return False
            if key == "entryUUID" and node not in values:
                return False
        return True

    async def search(self, payload):
        ids = payload.get("id")
        if isinstance(ids, str):
            ids = [ids]
        if ids:
            return [self._row(node_id) for node_id in ids if node_id in self.nodes]
        base = payload.get("base")
        scope = payload.get("scope", 2)
        filt = payload.get("filter") or {}
        found = []
        if scope == 0:
            if base in self.nodes and self._match(self.nodes[base], filt):
                found.append(self._row(base))
            return found

        def walk(parent_id):
            for node_id, node in list(self.nodes.items()):
                if node["parent"] != parent_id:
                    continue
                if self._match(node, filt):
                    found.append(self._row(node_id))
                if scope >= 2:
                    walk(node_id)

        if scope >= 2 and base in self.nodes and self._match(self.nodes[base], filt):
            found.append(self._row(base))
        walk(base)
        return found

    async def add(self, parent, attrs):
        self.added.append((parent, dict(attrs)))
        cn = attrs["cn"]
        for node in self.nodes.values():
            if node["parent"] == parent and node["cn"] == cn:
                return None
        node_id = f"new-{cn}"
        self.nodes[node_id] = {
            "parent": parent,
            "oc": attrs["objectClass"][0],
            "cn": cn,
        }
        return node_id

    async def modify(self, node_id, attrs):
        cn = attrs.get("cn")
        if not cn:
            return None
        parent = self.nodes[node_id]["parent"]
        for other_id, node in self.nodes.items():
            if other_id != node_id and node["parent"] == parent and node["cn"] == cn:
                raise ldap.ALREADY_EXISTS()
        self.nodes[node_id]["cn"] = cn
        return None

    async def move(self, node_id, new_parent):
        self.moved.append((node_id, new_parent))
        self.nodes[node_id]["parent"] = new_parent

    async def delete(self, node_id):
        self.deleted.append(node_id)

        def drop(current):
            for child_id, node in list(self.nodes.items()):
                if node["parent"] == current:
                    drop(child_id)
            self.nodes.pop(current, None)

        drop(node_id)


def _tree():
    mem = Mem()
    mem.put("prs", None, "prsModelNode", "prs")
    for name in ("objects", "tags", "connectors", "schedules", "dataStorages", "methods"):
        mem.put(name, "prs", "prsModelNode", name)
    mem.put("stdlib", "methods", "prsModelNode", "stdlib")
    mem.put("obj-1", "objects", "prsObject", "pump")
    mem.put("sys-1", "obj-1", "prsModelNode", "system")
    mem.put("tag-1", "obj-1", "prsTag", "temp")
    return mem


def _svc(mem, published=None):
    svc = object.__new__(ObjectsModelCRUD)
    svc._hierarchy = mem
    svc._logger = _Logger()
    svc._config = SimpleNamespace(svc_name="objects_model_crud", hierarchy={"class": "prsObject"})

    async def post_message(mes, reply=False, routing_key=None):
        if published is not None:
            published.append((routing_key, mes))
        return {}

    svc._post_message = post_message
    return svc


def _classes_text(value):
    if isinstance(value, list):
        return ",".join(value)
    return str(value)


def test_openldap_object_class_order_reports_prs_folder():
    # Порядок, который slapd обычно отдаёт, если клиент указал только структурный класс.
    # Живой slapd в этом прогоне не проверялся.
    assert node_class_from_object_classes([b"prsFolder", b"prsModelNode", b"top"]) == "prsFolder"
    assert node_class_from_object_classes(["top", "prsModelNode", "prsFolder"]) == "prsFolder"
    assert node_class_from_object_classes([b"prsModelNode", b"top"]) == "prsModelNode"
    assert node_class_from_object_classes([b"prsTag", b"prsModelNode", b"top"]) == "prsTag"
    assert node_class_from_object_classes([b"alias", b"extensibleObject"]) == "alias"
    assert "node_class_from_object_classes" in inspect.getsource(Hierarchy.get_node_class)


def test_parent_class_lists_allow_folders_only_for_folder_services():
    assert "prsFolder" in _classes_text(ObjectsModelCRUDSettings().hierarchy["parent_classes"])
    assert "prsObject" in _classes_text(ObjectsModelCRUDSettings().hierarchy["parent_classes"])
    assert "prsFolder" in _classes_text(TagsModelCRUDSettings().hierarchy["parent_classes"])
    assert "prsFolder" in _classes_text(ConnectorsModelCRUDSettings().hierarchy["parent_classes"])
    assert "prsFolder" in _classes_text(SchedulesModelCRUDSettings().hierarchy["parent_classes"])
    assert "prsFolder" in _classes_text(DataStoragesModelCRUDSettings().hierarchy["parent_classes"])
    assert "prsFolder" not in _classes_text(AlertsModelCRUDSettings().hierarchy["parent_classes"])


def test_folder_context_nesting_and_forbidden_parents():
    mem = _tree()
    svc = _svc(mem)
    created = asyncio.run(svc._folder_create({"parentId": "objects", "attributes": {"cn": "Цех"}}))
    assert created["id"] == "new-Цех"
    assert mem.added[0][1]["objectClass"] == ["prsFolder"]
    assert all(item[1].get("cn") != ["system"] for item in mem.added)
    nested = asyncio.run(svc._folder_create({"parentId": created["id"], "attributes": {"cn": "Участок"}}))
    assert nested["id"] == "new-Участок"
    assert mem.nodes[nested["id"]]["parent"] == created["id"]

    system = asyncio.run(svc._folder_create({"parentId": "sys-1", "attributes": {"cn": "x"}}))
    assert system["error"]["code"] == 422
    methods = asyncio.run(svc._folder_create({"parentId": "methods", "attributes": {"cn": "x"}}))
    assert methods["error"]["code"] == 422
    catalog = asyncio.run(svc._folder_create({"parentId": "stdlib", "attributes": {"cn": "x"}}))
    assert catalog["error"]["code"] == 422
    inside_tag = asyncio.run(svc._folder_create({"parentId": "tag-1", "attributes": {"cn": "x"}}))
    assert inside_tag["error"]["code"] == 422
    conflict = asyncio.run(svc._folder_create({"parentId": "objects", "attributes": {"cn": "Цех"}}))
    assert conflict["error"]["code"] == 422


def test_folder_accepts_child_by_root_context():
    mem = _tree()
    mem.put("obj-folder", "objects", "prsFolder", "group")
    mem.put("tag-folder", "tags", "prsFolder", "loose")
    mem.put("conn-folder", "connectors", "prsFolder", "links")

    async def allowed(parent_id, child_class, parent_classes):
        svc = object.__new__(ModelCRUDSvc)
        svc._hierarchy = mem
        svc._config = SimpleNamespace(
            hierarchy={"class": child_class, "node_id": "absent", "parent_classes": parent_classes}
        )
        return await svc._check_parent_class(parent_id)

    assert asyncio.run(allowed("obj-folder", "prsTag", ["prsObject", "prsFolder"])) is True
    assert asyncio.run(allowed("obj-folder", "prsObject", ["prsObject", "prsFolder"])) is True
    assert asyncio.run(allowed("tag-folder", "prsTag", ["prsObject", "prsFolder"])) is True
    assert asyncio.run(allowed("tag-folder", "prsObject", ["prsObject", "prsFolder"])) is False
    assert asyncio.run(allowed("conn-folder", "prsConnector", ["prsFolder"])) is True
    assert asyncio.run(allowed("conn-folder", "prsTag", ["prsObject", "prsFolder"])) is False
    assert asyncio.run(allowed("obj-1", "prsAlert", ["prsTag"])) is False


def test_service_root_get_parent_stays_null():
    parent_class = {"value": "prsModelNode"}

    async def search(_payload):
        return [("child", "cn=child,cn=objects,cn=prs", {"cn": ["child"]})]

    async def get_parent(_node_id):
        return "root-or-folder", "cn=objects,cn=prs"

    async def get_node_class(_node_id):
        return parent_class["value"]

    async def further(_mes, result):
        return result

    svc = object.__new__(ModelCRUDSvc)
    svc._config = SimpleNamespace(
        svc_name="objects_model_crud",
        hierarchy={"class": "prsObject", "node": "objects", "node_id": "objects"},
    )
    svc._logger = _Logger()
    svc._hierarchy = SimpleNamespace(search=search, get_parent=get_parent, get_node_class=get_node_class)
    svc._further_read = further
    root = asyncio.run(
        svc._read({"id": "child", "base": None, "hierarchy": False, "scope": 0, "filter": {}, "getParent": True})
    )
    assert root["data"][0]["parentId"] is None
    parent_class["value"] = "prsFolder"
    nested = asyncio.run(
        svc._read({"id": "child", "base": None, "hierarchy": False, "scope": 0, "filter": {}, "getParent": True})
    )
    assert nested["data"][0]["parentId"] == "root-or-folder"


def test_hierarchy_walk_includes_folders_without_changing_plain_tree():
    root_id = "11111111-1111-1111-1111-111111111111"

    async def search(payload):
        if payload.get("base") == root_id and payload.get("scope") == CN_SCOPE_ONELEVEL:
            return [("obj-1", "dn", {"cn": ["pump"]})]
        return []

    calls = []

    async def recording(payload):
        calls.append(payload)
        return await search(payload)

    async def further(_mes, result):
        return result

    svc = object.__new__(ModelCRUDSvc)
    svc._config = SimpleNamespace(
        svc_name="objects_model_crud",
        hierarchy={"class": "prsObject", "node": "objects", "node_id": "objects"},
    )
    svc._logger = _Logger()
    svc._hierarchy = SimpleNamespace(search=recording)
    svc._further_read = further
    tree = asyncio.run(
        svc._read({"base": root_id, "hierarchy": True, "scope": 2, "filter": {}, "getParent": False})
    )
    calls.clear()
    flat = asyncio.run(
        svc._read({"base": root_id, "hierarchy": False, "scope": 1, "filter": {}, "getParent": False})
    )
    assert [item["id"] for item in tree["data"]] == [item["id"] for item in flat["data"]] == ["obj-1"]
    assert "children" not in flat["data"][0]
    assert calls[0]["filter"]["objectClass"] == ["prsObject"]

    calls.clear()
    asyncio.run(svc._read({"base": root_id, "hierarchy": True, "scope": 2, "filter": {}, "getParent": False}))
    assert calls[0]["filter"]["objectClass"] == ["prsObject", "prsFolder"]
    assert calls[0]["scope"] == CN_SCOPE_ONELEVEL


def test_folder_move_rejects_cycle_and_foreign_context():
    mem = _tree()
    mem.put("folder-a", "objects", "prsFolder", "a")
    mem.put("folder-b", "folder-a", "prsFolder", "b")
    mem.put("folder-t", "tags", "prsFolder", "t")
    svc = _svc(mem)
    cycle = asyncio.run(svc._folder_update({"id": "folder-a", "parentId": "folder-b"}))
    assert cycle["error"]["code"] == 422
    assert mem.moved == []
    foreign = asyncio.run(svc._folder_update({"id": "folder-t", "parentId": "objects"}))
    assert foreign["error"]["code"] == 422
    moved = asyncio.run(svc._folder_update({"id": "folder-b", "parentId": "obj-1"}))
    assert moved == {}
    assert mem.nodes["folder-b"]["parent"] == "obj-1"
    renamed = asyncio.run(svc._folder_update({"id": "folder-a", "attributes": {"cn": "Цех"}}))
    assert renamed == {}
    assert mem.nodes["folder-a"]["cn"] == "Цех"
    mem.put("folder-c", "objects", "prsFolder", "Цех")
    conflict = asyncio.run(svc._folder_update({"id": "folder-a", "attributes": {"cn": "Цех"}}))
    assert conflict["error"]["code"] == 422


def test_folder_delete_emits_deleted_for_nested_tag():
    mem = _tree()
    mem.put("folder-a", "objects", "prsFolder", "a")
    mem.put("folder-b", "folder-a", "prsFolder", "b")
    mem.put("tag-in", "folder-b", "prsTag", "flow")
    published = []
    svc = _svc(mem, published)
    tag_svc = object.__new__(ModelCRUDSvc)
    tag_svc._config = SimpleNamespace(svc_name="tags_model_crud", hierarchy={"class": "prsTag"})
    tag_svc._logger = _Logger()
    tag_svc._hierarchy = mem
    tag_svc._post_message = svc._post_message

    async def post_message(mes, reply=False, routing_key=None):
        published.append(routing_key)
        if routing_key and routing_key.startswith("prsTag.api_crud.delete"):
            return await tag_svc._delete({"id": mes["id"]})
        if routing_key and ".model.may_delete." in routing_key:
            return {"response": True}
        if routing_key and ".model.deleting." in routing_key:
            return {"response": True}
        return {}

    svc._post_message = post_message
    tag_svc._post_message = post_message
    result = asyncio.run(svc._folder_delete({"id": "folder-a"}))
    assert result == {}
    assert any(key and key.startswith("prsTag.model.deleted.tag-in") for key in published)
    assert mem.deleted[:2] == ["tag-in", "folder-b"]
    assert "folder-a" in mem.deleted
    assert "tag-in" not in mem.nodes


def test_folder_update_does_not_invent_active_flag():
    body = FolderUpdate.model_validate(
        {"id": "11111111-1111-1111-1111-111111111111", "attributes": {"cn": "Цех"}}
    ).model_dump(exclude_unset=True)
    assert body["attributes"] == {"cn": "Цех"}


def test_configurator_folder_menu_version_and_sort():
    dashboard = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    javascript = dashboard["panels"][0]["options"]["onRender"]
    assert dashboard["uid"] == "ddy59kw4v5ssgc"
    assert f'prsConfiguratorCodeVersion="{CODE_VERSION}"' in javascript
    assert '["userFolders","fa-folder","Новая папка"]' in javascript
    assert 'case"prsFolder":a(prsUserFolderMenuItems(e))' in javascript
    assert 'case"prsModelNode":a(["methodFolders","catalogMethods","methodDescription","__active__","__delete__"])' in javascript
    assert 'prsFolder:"/v1/folders"' in javascript
    assert 'return"prsFolder"===t?-1:"prsObject"===t?0:' in javascript
    assert "function prsCreateUserFolder" in javascript
    assert 'prsFolder:"Папка"' in javascript
    assert "prsTreeRowDropTarget" in javascript
