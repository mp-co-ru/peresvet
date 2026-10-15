"""Список ``nodes`` — поле конфигурации сервиса, не узел LDAP."""

from __future__ import annotations


def serves(nodes, entity_id: str) -> bool:
    """Пустой список значит «все id этой роли». Иначе только перечисленные."""
    listed = [str(item) for item in (nodes or []) if str(item)]
    return not listed or str(entity_id) in listed


def http_base(settings) -> str:
    return str(getattr(settings, "http_base_url", "") or "").strip().rstrip("/")
