#!/usr/bin/env python3
"""Возвращает имя контейнера сервиса из docker compose config (JSON).

Вывод (одна строка): container_name

Аргументы: compose_file [compose_project_name] [service]

Если compose_project_name пустой, используется имя проекта по умолчанию
(basename каталога compose-файла), как у ``docker compose`` без ``-p``.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys


def default_project_name(compose_file: str) -> str:
    return os.path.basename(os.path.dirname(os.path.abspath(compose_file)))


def main() -> int:
    if len(sys.argv) < 3:
        print(
            "usage: resolve_compose_container.py COMPOSE_FILE [PROJECT] SERVICE",
            file=sys.stderr,
        )
        return 2
    compose_file = sys.argv[1]
    if len(sys.argv) > 3:
        project_flag = sys.argv[2]
        service = sys.argv[3]
    else:
        project_flag = ""
        service = sys.argv[2]

    cmd = ["docker", "compose"]
    if project_flag:
        cmd.extend(["-p", project_flag])
    cmd.extend(["-f", compose_file, "config", "--format", "json"])
    cwd = os.environ.get("RESOLVE_CWD")
    try:
        raw = subprocess.check_output(cmd, text=True, cwd=cwd or None)
    except subprocess.CalledProcessError as e:
        print(f"resolve_compose_container: docker compose config failed: {e}", file=sys.stderr)
        return 1
    except FileNotFoundError:
        print("resolve_compose_container: docker not found in PATH", file=sys.stderr)
        return 1

    cfg = json.loads(raw)
    services = cfg.get("services") or {}
    if service not in services:
        print(
            f"resolve_compose_container: service {service!r} not in compose config",
            file=sys.stderr,
        )
        return 1

    container_name = services[service].get("container_name")
    if not container_name:
        project_name = (
            cfg.get("name")
            or (project_flag if project_flag else None)
            or default_project_name(compose_file)
        )
        container_name = f"{project_name}-{service}-1"

    print(container_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
