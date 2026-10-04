"""Разбор GET /v1/data/ для видеосервера."""

from __future__ import annotations

from starlette.requests import Request

from src.services.tags.app_api.tags_app_api_svc import DataGet


def payload_from_request(request: Request) -> DataGet:
    query = request.query_params
    packed = query.get("q")
    if packed:
        return DataGet.model_validate_json(packed)
    tag_ids = query.getlist("tagId")
    if not tag_ids:
        raise ValueError("Нужен tagId.")
    body: dict = {"tagId": tag_ids}
    for key in ("start", "finish", "timeStep", "count"):
        if key in query:
            body[key] = query.get(key)
    return DataGet.model_validate(body)
