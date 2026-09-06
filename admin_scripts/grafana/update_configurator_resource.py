#!/usr/bin/env python3
"""Update Configurator dashboard in Grafana 12 unified resource storage."""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--configurator-json",
        default="src/grafana/configurator/Configurator.json",
        help="Path to Configurator.json dashboard body",
    )
    parser.add_argument(
        "--db",
        default="/var/lib/grafana/grafana.db",
        help="Path to grafana.db",
    )
    parser.add_argument(
        "--uid",
        default="ddy59kw4v5ssgc",
        help="Configurator dashboard UID in Grafana resource storage",
    )
    args = parser.parse_args()

    dash = json.loads(Path(args.configurator_json).read_text(encoding="utf-8"))
    payload = {
        "apiVersion": "dashboard.grafana.app/v1beta1",
        "kind": "Dashboard",
        "metadata": {"name": args.uid, "namespace": "default"},
        "spec": dash,
    }
    value = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    con = sqlite3.connect(args.db)
    cur = con.cursor()
    row = cur.execute(
        'SELECT guid, resource_version FROM resource WHERE "group" = ? AND name = ?',
        ("dashboard.grafana.app", args.uid),
    ).fetchone()
    if not row:
        print(f"Dashboard resource {args.uid!r} not found")
        return 1

    guid, _rv = row
    new_rv = int(time.time() * 1_000_000_000)
    cur.execute(
        'UPDATE resource SET value = ?, resource_version = ?, action = 2 WHERE guid = ?',
        (value, new_rv, guid),
    )
    con.commit()
    con.close()
    print(
        f"Updated resource {args.uid}: "
        f"prsBindAllObjectTreeDnd={value.count('prsBindAllObjectTreeDnd')}, "
        f"bytes={len(value)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
