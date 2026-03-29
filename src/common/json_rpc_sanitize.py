"""Приведение ответов RPC к виду, который гарантированно сериализуется ``json.dumps``."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any


def sanitize_for_json_rpc(obj: Any) -> Any:
    """Рекурсивно: tuple/set → list, Decimal/numpy-scalar → float/int, bytes → str."""
    if obj is None:
        return None
    if isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, int) and not isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        return obj
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, tuple):
        return [sanitize_for_json_rpc(x) for x in obj]
    if isinstance(obj, list):
        return [sanitize_for_json_rpc(x) for x in obj]
    if isinstance(obj, dict):
        return {k: sanitize_for_json_rpc(v) for k, v in obj.items()}
    if isinstance(obj, set):
        return [sanitize_for_json_rpc(x) for x in obj]
    item = getattr(obj, "item", None)
    if callable(item):
        try:
            return sanitize_for_json_rpc(item())
        except Exception:
            pass
    return obj


def to_redis_json_scalar(y: Any) -> Any:
    """Скаляр для Redis JSON (например prsLastAcceptedY): без numpy/Decimal в проводе."""
    if y is None:
        return None
    if isinstance(y, (bool, str)):
        return y
    if isinstance(y, int) and not isinstance(y, bool):
        return y
    if isinstance(y, float):
        return y
    if isinstance(y, Decimal):
        return float(y)
    if isinstance(y, bytes):
        return y.decode("utf-8", errors="replace")
    item = getattr(y, "item", None)
    if callable(item):
        try:
            return to_redis_json_scalar(item())
        except Exception:
            pass
    try:
        return float(y)
    except (TypeError, ValueError):
        return y
