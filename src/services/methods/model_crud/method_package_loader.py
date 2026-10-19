"""Идемпотентная загрузка пакетов методов в LDAP.

Читает только manifest.json. Python пакета (worker.py) не импортируется.
Каталог задаётся PRS_METHOD_PACKAGES_DIR, иначе methods/packages рядом с репозиторием.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from src.common.hierarchy import CN_SCOPE_ONELEVEL, CN_SCOPE_SUBTREE


def packages_dir() -> Path:
    override = os.environ.get("PRS_METHOD_PACKAGES_DIR", "").strip()
    if override:
        return Path(override)
    # src/services/methods/model_crud/this_file.py -> корень репозитория или образ one_app
    return Path(__file__).resolve().parents[4] / "methods" / "packages"


def license_allows(manifest: dict) -> bool:
    license_info = manifest.get("license") or {"mode": "none"}
    if not isinstance(license_info, dict):
        return False
    mode = str(license_info.get("mode") or "none").strip().lower()
    if mode == "none":
        return True
    if mode == "env":
        variable = str(license_info.get("variable") or license_info.get("env") or "").strip()
        if not variable:
            return False
        return bool(os.environ.get(variable, "").strip())
    return False


def _load_manifests(root: Path) -> list[tuple[Path, dict]]:
    if not root.is_dir():
        return []
    found: list[tuple[Path, dict]] = []
    for entry in sorted(root.iterdir()):
        manifest_path = entry / "manifest.json"
        if not entry.is_dir() or not manifest_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(manifest, dict):
            found.append((entry, manifest))
    return found


async def _find_child(hierarchy, parent_id: str, *, object_class: str, cn: str) -> str | None:
    rows = await hierarchy.search(
        {
            "base": parent_id,
            "scope": CN_SCOPE_ONELEVEL,
            "filter": {"objectClass": [object_class], "cn": [cn]},
            "attributes": ["cn"],
        }
    )
    if not rows:
        return None
    return rows[0][0]


async def _existing_addresses(hierarchy, methods_root_id: str) -> set[str]:
    rows = await hierarchy.search(
        {
            "base": methods_root_id,
            "scope": CN_SCOPE_SUBTREE,
            "filter": {"objectClass": ["prsMethod"]},
            "attributes": ["prsMethodAddress"],
        }
    )
    found: set[str] = set()
    for row in rows or []:
        raw = row[2].get("prsMethodAddress", [""])
        value = raw[0] if isinstance(raw, list) and raw else raw
        if isinstance(value, (bytes, bytearray)):
            value = value.decode()
        text = str(value or "").strip()
        if text:
            found.add(text)
    return found


async def _ensure_folder(hierarchy, parent_id: str, folder: dict) -> str | None:
    cn = str(folder.get("cn") or "").strip()
    if not cn:
        return parent_id
    existing = await _find_child(hierarchy, parent_id, object_class="prsModelNode", cn=cn)
    if existing:
        return existing
    attrs = {
        "objectClass": ["prsModelNode"],
        "cn": cn,
        "prsActive": True,
    }
    description = folder.get("description")
    if description:
        attrs["description"] = description
    return await hierarchy.add(parent_id, attrs)


async def _ensure_method(hierarchy, parent_id: str, method: dict) -> str | None:
    address = str(method.get("prsMethodAddress") or "").strip()
    if not address:
        return None
    created = await hierarchy.add(
        parent_id,
        {
            "objectClass": ["prsMethod"],
            "cn": method.get("cn") or address,
            "description": method.get("description") or "",
            "prsMethodAddress": address,
            "prsEntityTypeCode": 0,
            "prsActive": True,
        },
    )
    if not created:
        return None
    system_id = await hierarchy.add(created, {"cn": "system"})
    await hierarchy.add(system_id, {"cn": "initiatedBy"})
    parameters_id = await hierarchy.add(system_id, {"cn": "parameters"})
    for parameter in method.get("parameters") or []:
        await hierarchy.add(
            parameters_id,
            {
                "objectClass": ["prsMethodParameter"],
                "cn": parameter.get("cn") or "p",
                "prsIndex": parameter.get("prsIndex"),
                "prsValueTypeCode": parameter.get("prsValueTypeCode"),
                "prsActive": True,
            },
        )
    return created


async def seed_method_packages(hierarchy, methods_root_id: str | None, logger=None) -> int:
    """Создаёт отсутствующие методы пакетов. Уже существующий prsMethodAddress не трогает.

    Возвращает число новых методов. Пустой каталог, пустая лицензионная переменная
    и неизвестный режим лицензии пропускают пакет без ошибки.
    """
    if not methods_root_id:
        return 0
    created = 0
    try:
        manifests = _load_manifests(packages_dir())
    except Exception as ex:
        if logger:
            logger.error(f"methods_model_crud :: Не удалось прочитать пакеты методов: {ex}")
        return 0
    if not manifests:
        return 0
    try:
        known = await _existing_addresses(hierarchy, methods_root_id)
    except Exception as ex:
        if logger:
            logger.error(f"methods_model_crud :: Не удалось прочитать каталог методов: {ex}")
        return 0

    for _entry, manifest in manifests:
        package_id = manifest.get("id") or _entry.name
        if not license_allows(manifest):
            if logger:
                logger.info(
                    f"methods_model_crud :: Пакет методов '{package_id}' пропущен: лицензия не выполнена."
                )
            continue
        try:
            parent_id = await _ensure_folder(hierarchy, methods_root_id, manifest.get("folder") or {})
        except Exception as ex:
            if logger:
                logger.error(f"methods_model_crud :: Папка пакета '{package_id}' не создана: {ex}")
            continue
        if not parent_id:
            continue
        for method in manifest.get("methods") or []:
            address = str(method.get("prsMethodAddress") or "").strip()
            if not address or address in known:
                continue
            try:
                new_id = await _ensure_method(hierarchy, parent_id, method)
            except Exception as ex:
                if logger:
                    logger.error(
                        f"methods_model_crud :: Метод '{address}' пакета '{package_id}' не создан: {ex}"
                    )
                continue
            if new_id:
                known.add(address)
                created += 1
    if logger and created:
        logger.info(f"methods_model_crud :: В каталог добавлено методов: {created}.")
    return created
