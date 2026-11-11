"""Старт one_app после удаления Router.startup() в Starlette."""

import asyncio
from pathlib import Path

from fastapi import FastAPI
from starlette.routing import Mount

from src.common import runtime_flags
from src.services.one_app.one_app import app, lifespan, platform_version


def test_mounted_apps_start_and_stop_without_router_startup():
    events: list[str] = []

    async def on_startup() -> None:
        events.append(f"startup:{runtime_flags.platform_shutting_down}")

    async def on_shutdown() -> None:
        events.append(f"shutdown:{runtime_flags.platform_shutting_down}")

    sub = FastAPI(on_startup=[on_startup], on_shutdown=[on_shutdown])
    assert not hasattr(sub.router, "startup")

    parent = FastAPI()
    parent.mount("/", sub)

    async def run() -> None:
        async with lifespan(parent):
            events.append("running")

    try:
        asyncio.run(run())
    finally:
        runtime_flags.set_platform_shutting_down(False)

    assert events == ["startup:False", "running", "shutdown:True"]


def test_platform_version_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("PRS_VERSION", "v0.24.1")
    assert platform_version() == "v0.24.1"

    monkeypatch.setenv("PRS_VERSION", "  ")
    assert platform_version() == ""


def test_version_route_is_registered_before_mounted_apps():
    paths = [getattr(route, "path", None) for route in app.routes]
    assert "/v1/version" in paths
    first_mount = next(index for index, route in enumerate(app.routes) if isinstance(route, Mount))
    assert paths.index("/v1/version") < first_mount

    root = Path(__file__).resolve().parents[2]
    nginx = (root / "config/nginx/peresvet/locations/peresvet.locations.conf.template").read_text(
        encoding="utf-8"
    )
    assert "location = /v1/version" in nginx
    assert "proxy_pass http://objects_api_crud;" in nginx.split("location = /v1/version", 1)[1].split("location =", 1)[0]
    compose = (root / "docker/compose/docker-compose.one_app.yml").read_text(encoding="utf-8")
    assert "PRS_VERSION: ${PRS_VERSION:-}" in compose
    for name in (
        "packaging/build_product_distribution.sh",
        "packaging/build_dev_distribution.sh",
    ):
        text = (root / name).read_text(encoding="utf-8")
        assert 'printf \'%s\\n\' "${version}" > "${stage_dir}/VERSION"' in text
