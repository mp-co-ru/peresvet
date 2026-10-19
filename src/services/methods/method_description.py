"""Разбор YAML-описания каталога методов.

Файл задаёт папки и методы. Методы можно вкладывать в папки.
Пробный вызов берёт список ``probe``, а если его нет — значения по типу параметра.
"""
from __future__ import annotations

from typing import Any

from src.services.methods.method_catalog import VALUE_TYPE_CODES, as_int

TYPE_NAMES = {
    "int": 1,
    "integer": 1,
    "целый": 1,
    "float": 2,
    "double": 2,
    "number": 2,
    "вещественный": 2,
    "str": 3,
    "string": 3,
    "строка": 3,
    "json": 4,
}


def _text(value: Any, field: str, path: str) -> str:
    if value is None:
        raise ValueError(f"{path}: не заполнено поле {field}.")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{path}: не заполнено поле {field}.")
    return text


def value_type_code(value: Any, path: str) -> int:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{path}: тип параметра должен быть 1, 2, 3, 4 или именем типа.")
    code = as_int(value)
    if code in VALUE_TYPE_CODES:
        return code
    name = str(value).strip().lower()
    if name in TYPE_NAMES:
        return TYPE_NAMES[name]
    raise ValueError(f"{path}: неизвестный тип параметра '{value}'.")


def default_probe_value(type_code: int) -> Any:
    if type_code == 1:
        return 1
    if type_code == 2:
        return 1.0
    if type_code == 3:
        return "probe"
    return {}


def _parameters(raw: Any, path: str) -> list[dict]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"{path}: parameters должен быть списком.")
    parameters: list[dict] = []
    for offset, item in enumerate(raw, start=1):
        item_path = f"{path}.parameters[{offset}]"
        if not isinstance(item, dict):
            raise ValueError(f"{item_path}: параметр должен быть объектом.")
        cn = _text(item.get("cn") or item.get("name"), "cn", item_path)
        index = as_int(item.get("prsIndex") if item.get("prsIndex") is not None else item.get("index"))
        if index is None:
            index = offset
        type_value = item.get("prsValueTypeCode")
        if type_value is None:
            type_value = item.get("type")
        if type_value is None:
            type_value = 2
        parameters.append(
            {
                "cn": cn,
                "prsIndex": index,
                "prsValueTypeCode": value_type_code(type_value, item_path),
                "description": str(item.get("description") or "").strip(),
            }
        )
    return parameters


def _probe(raw: Any, parameters: list[dict], path: str) -> list:
    if raw is None:
        return [default_probe_value(item["prsValueTypeCode"]) for item in parameters]
    if not isinstance(raw, list):
        raise ValueError(f"{path}: probe должен быть списком аргументов.")
    return list(raw)


def _method(raw: Any, path: str) -> dict:
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: метод должен быть объектом.")
    address = _text(
        raw.get("prsMethodAddress") or raw.get("address"),
        "address",
        path,
    )
    cn = str(raw.get("cn") or raw.get("name") or address).strip() or address
    parameters = _parameters(raw.get("parameters"), path)
    return {
        "cn": cn,
        "description": str(raw.get("description") or "").strip(),
        "prsMethodAddress": address,
        "parameters": parameters,
        "probe": _probe(raw.get("probe"), parameters, path),
    }


def _folder(raw: Any, path: str) -> dict:
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: папка должна быть объектом.")
    cn = _text(raw.get("cn") or raw.get("name"), "cn", path)
    return {
        "cn": cn,
        "description": str(raw.get("description") or "").strip(),
        "methods": [_method(item, f"{path}/{cn}") for item in raw.get("methods") or []],
        "folders": [_folder(item, f"{path}/{cn}") for item in raw.get("folders") or []],
    }


def parse_method_description(text: str) -> dict:
    """Возвращает дерево ``{methods, folders}``."""
    if not str(text or "").strip():
        raise ValueError("Файл описания пуст.")
    try:
        import yaml
    except ImportError as ex:
        raise ValueError("Разбор YAML недоступен: не установлен пакет PyYAML.") from ex
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as ex:
        raise ValueError(f"Файл описания не является YAML: {ex}") from ex
    if loaded is None:
        raise ValueError("Файл описания пуст.")
    if isinstance(loaded, list):
        loaded = {"methods": loaded}
    if not isinstance(loaded, dict):
        raise ValueError("Корень описания должен быть объектом или списком методов.")
    if "methods" not in loaded and "folders" not in loaded:
        if loaded.get("prsMethodAddress") or loaded.get("address"):
            loaded = {"methods": [loaded]}
        else:
            raise ValueError("В описании нет methods и folders.")
    return {
        "methods": [_method(item, "methods") for item in loaded.get("methods") or []],
        "folders": [_folder(item, "folders") for item in loaded.get("folders") or []],
    }


def iter_methods(tree: dict):
    """Плоский список методов с путём папок."""

    def walk(node: dict, path: list[str]):
        for method in node.get("methods") or []:
            yield path, method
        for folder in node.get("folders") or []:
            yield from walk(folder, path + [folder["cn"]])

    yield from walk(tree, [])


async def apply_method_description(
    tree: dict,
    parent_id: str,
    *,
    ensure_folder,
    create_method,
    find_by_address,
) -> dict:
    """Создаёт отсутствующие папки и методы. Уже известный адрес не создаётся повторно."""
    created: list[dict] = []
    probes: list[dict] = []

    async def walk(node: dict, folder_id: str, path: list[str]) -> None:
        for folder in node.get("folders") or []:
            folder_path = path + [folder["cn"]]
            folder_node_id, status, message = await ensure_folder(folder_id, folder)
            created.append(
                {
                    "kind": "folder",
                    "cn": folder["cn"],
                    "path": "/".join(folder_path),
                    "id": folder_node_id,
                    "status": status,
                    "message": message,
                }
            )
            if folder_node_id:
                await walk(folder, folder_node_id, folder_path)
        for method in node.get("methods") or []:
            method_path = "/".join(path + [method["cn"]])
            existing = await find_by_address(method["prsMethodAddress"])
            if existing:
                created.append(
                    {
                        "kind": "method",
                        "cn": method["cn"],
                        "path": method_path,
                        "id": existing,
                        "address": method["prsMethodAddress"],
                        "status": "exists",
                        "message": "",
                    }
                )
                method_id = existing
            else:
                method_id, status, message = await create_method(folder_id, method)
                created.append(
                    {
                        "kind": "method",
                        "cn": method["cn"],
                        "path": method_path,
                        "id": method_id,
                        "address": method["prsMethodAddress"],
                        "status": status,
                        "message": message,
                    }
                )
            if method_id:
                probes.append(
                    {
                        "id": method_id,
                        "cn": method["cn"],
                        "path": method_path,
                        "address": method["prsMethodAddress"],
                        "arguments": method["probe"],
                    }
                )

    await walk(tree, parent_id, [])
    return {"created": created, "probes": probes}
