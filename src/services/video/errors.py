"""JSON-ошибка видеотега. Тело одно и то же на всех трёх HTTP-хопах."""

from __future__ import annotations

from starlette.responses import JSONResponse


def error_response(code: int, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=code)
