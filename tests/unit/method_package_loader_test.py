import asyncio
import json
from pathlib import Path

from src.common.hierarchy import CN_SCOPE_ONELEVEL, CN_SCOPE_SUBTREE
from src.services.methods.model_crud.method_package_loader import seed_method_packages


class _MemoryHierarchy:
    def __init__(self):
        self.nodes = {}
        self.seq = 0

    async def add(self, parent, attrs):
        self.seq += 1
        node_id = f"n{self.seq}"
        stored = {}
        for key, value in attrs.items():
            stored[key] = value if isinstance(value, list) else [value]
        self.nodes[node_id] = {"parent": parent, "attrs": stored}
        return node_id

    def _match(self, attrs, filt):
        for key, expected in filt.items():
            have = attrs.get(key, [])
            if not isinstance(have, list):
                have = [have]
            if not any(item in have or str(item) in [str(value) for value in have] for item in expected):
                return False
        return True

    def _ids(self, base, scope):
        children = [node_id for node_id, node in self.nodes.items() if node["parent"] == base]
        if scope == CN_SCOPE_ONELEVEL:
            return children
        found = []

        def walk(parent_id):
            for node_id, node in self.nodes.items():
                if node["parent"] == parent_id:
                    found.append(node_id)
                    walk(node_id)

        walk(base)
        return found

    async def search(self, payload):
        filt = payload.get("filter") or {}
        rows = []
        for node_id in self._ids(payload.get("base"), payload.get("scope", CN_SCOPE_SUBTREE)):
            attrs = self.nodes[node_id]["attrs"]
            if self._match(attrs, filt):
                rows.append((node_id, None, attrs))
        return rows


def test_stdlib_package_seeds_folder_and_four_methods_once(monkeypatch, tmp_path):
    root = Path(__file__).resolve().parents[2] / "methods" / "packages"
    monkeypatch.setenv("PRS_METHOD_PACKAGES_DIR", str(root))
    hierarchy = _MemoryHierarchy()
    created = asyncio.run(seed_method_packages(hierarchy, "methods-root"))
    assert created == 4
    folders = [
        node for node in hierarchy.nodes.values()
        if node["parent"] == "methods-root" and node["attrs"].get("objectClass") == ["prsModelNode"]
    ]
    assert folders and folders[0]["attrs"]["cn"] == ["stdlib"]
    addresses = sorted(
        node["attrs"]["prsMethodAddress"][0]
        for node in hierarchy.nodes.values()
        if node["attrs"].get("objectClass") == ["prsMethod"]
    )
    assert addresses == ["prs.stdlib.add", "prs.stdlib.div", "prs.stdlib.mul", "prs.stdlib.sub"]
    again = asyncio.run(seed_method_packages(hierarchy, "methods-root"))
    assert again == 0
    assert sum(1 for node in hierarchy.nodes.values() if node["attrs"].get("objectClass") == ["prsMethod"]) == 4


def test_loader_skips_empty_license_env_and_does_not_import_worker(monkeypatch, tmp_path):
    package = tmp_path / "partner"
    package.mkdir()
    (package / "worker.py").write_text("raise SystemExit('worker imported')\n", encoding="utf-8")
    (package / "manifest.json").write_text(
        json.dumps(
            {
                "id": "partner",
                "license": {"mode": "env", "variable": "PRS_PARTNER_LICENSE"},
                "folder": {"cn": "partner"},
                "methods": [{"cn": "x", "prsMethodAddress": "partner.x", "parameters": []}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("PRS_PARTNER_LICENSE", raising=False)
    monkeypatch.setenv("PRS_METHOD_PACKAGES_DIR", str(tmp_path))
    hierarchy = _MemoryHierarchy()
    assert asyncio.run(seed_method_packages(hierarchy, "methods-root")) == 0
    assert hierarchy.nodes == {}

    monkeypatch.setenv("PRS_PARTNER_LICENSE", "ok")
    assert asyncio.run(seed_method_packages(hierarchy, "methods-root")) == 1
    assert any(
        node["attrs"].get("prsMethodAddress") == ["partner.x"] for node in hierarchy.nodes.values()
    )


def test_loader_ignores_missing_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("PRS_METHOD_PACKAGES_DIR", str(tmp_path / "missing"))
    assert asyncio.run(seed_method_packages(_MemoryHierarchy(), "methods-root")) == 0
