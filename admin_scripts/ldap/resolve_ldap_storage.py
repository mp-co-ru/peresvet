#!/usr/bin/env python3
"""Читает смонтированный путь OpenLDAP из docker compose config (JSON).

Вывод (одна строка, для shell):
  volume\\t<полное_имя_docker_тома>
или
  bind\\t<абсолютный_путь_на_хосте>

Аргументы: compose_file [compose_project_name] [ldap_service]

Если compose_project_name пустой, используется имя проекта по умолчанию
(basename каталога compose-файла), как у ``docker compose`` без ``-p``.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

LDAP_MOUNT = "/var/lib/ldap"
MARKER = ":/var/lib/ldap"


def default_project_name(compose_file: str) -> str:
    return os.path.basename(os.path.dirname(os.path.abspath(compose_file)))


def main() -> int:
    if len(sys.argv) < 2:
        print(
            "usage: resolve_ldap_storage.py COMPOSE_FILE [PROJECT] [SERVICE]",
            file=sys.stderr,
        )
        return 2
    compose_file = sys.argv[1]
    project_flag = sys.argv[2] if len(sys.argv) > 2 else ""
    service = sys.argv[3] if len(sys.argv) > 3 else "ldap"

    cmd = ["docker", "compose"]
    if project_flag:
        cmd.extend(["-p", project_flag])
    cmd.extend(["-f", compose_file, "config", "--format", "json"])
    cwd = os.environ.get("RESOLVE_CWD")
    try:
        raw = subprocess.check_output(cmd, text=True, cwd=cwd or None)
    except subprocess.CalledProcessError as e:
        print(f"resolve_ldap_storage: docker compose config failed: {e}", file=sys.stderr)
        return 1
    except FileNotFoundError:
        print("resolve_ldap_storage: docker not found in PATH", file=sys.stderr)
        return 1

    cfg = json.loads(raw)
    effective_project = (
        cfg.get("name")
        or (project_flag if project_flag else None)
        or default_project_name(compose_file)
    )
    services = cfg.get("services") or {}
    if service not in services:
        print(f"resolve_ldap_storage: service {service!r} not in compose config", file=sys.stderr)
        return 1
    vols = services[service].get("volumes") or []
    compose_dir = os.path.dirname(os.path.abspath(compose_file))

    for entry in vols:
        if isinstance(entry, dict) and (entry.get("type") or "").lower() == "tmpfs":
            continue
        src, tgt = parse_volume_entry(entry)
        if not tgt or os.path.normpath(tgt) != os.path.normpath(LDAP_MOUNT):
            continue
        if not src:
            continue
        if is_bind_source(src):
            host_path = src if os.path.isabs(src) else os.path.normpath(os.path.join(compose_dir, src))
            print(f"bind\t{host_path}")
            return 0
        print(f"volume\t{effective_project}_{src}")
        return 0

    print(
        f"resolve_ldap_storage: no mount for {LDAP_MOUNT!r} on service {service!r}",
        file=sys.stderr,
    )
    return 1


def parse_volume_entry(entry: object) -> tuple[str | None, str | None]:
    if isinstance(entry, dict):
        src = entry.get("source")
        tgt = entry.get("target")
        vtype = (entry.get("type") or "").lower()
        if vtype == "bind" and src:
            return src, tgt
        if vtype == "volume" and src:
            return src, tgt
        return src, tgt
    if isinstance(entry, str):
        if MARKER in entry:
            src = entry.split(MARKER, 1)[0]
            return src, LDAP_MOUNT
        parts = entry.split(":")
        if len(parts) >= 2 and parts[-1] in ("rw", "ro", "z", "Z"):
            parts = parts[:-1]
        if len(parts) >= 2:
            tgt = parts[-1]
            src = ":".join(parts[:-1])
            if tgt == LDAP_MOUNT or os.path.normpath("/" + tgt.lstrip("/")) == LDAP_MOUNT:
                return src, LDAP_MOUNT
    return None, None


def is_bind_source(src: str) -> bool:
    if not src:
        return False
    return src.startswith("/") or src.startswith(".")


if __name__ == "__main__":
    raise SystemExit(main())
