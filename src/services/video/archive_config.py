"""Настройки видеоархива: путь, срок хранения, длина сегмента.

Значения приходят из хранилища типа 3 (``prsEntityTypeCode``).
Если узла нет, берутся переменные окружения видеосервера.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ArchiveConfig:
    path: Path
    retention_hours: float
    segment_seconds: int
    max_fragment_seconds: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "retentionHours": self.retention_hours,
            "segmentSeconds": self.segment_seconds,
            "maxFragmentSeconds": self.max_fragment_seconds,
        }


def _env_path() -> Path:
    raw = os.environ.get("VIDEO_ARCHIVE_DIR")
    if raw:
        return Path(raw)
    return Path("log") / "video"


def _env_retention_hours() -> float:
    try:
        return float(os.environ.get("VIDEO_ARCHIVE_HOURS", "24"))
    except ValueError:
        return 24.0


def _env_segment_seconds() -> int:
    try:
        return int(os.environ.get("VIDEO_SEGMENT_SECONDS", "10"))
    except ValueError:
        return 10


def _env_max_fragment_seconds() -> int:
    try:
        return int(os.environ.get("VIDEO_MAX_FRAGMENT_SECONDS", "7200"))
    except ValueError:
        return 7200


def default_archive_config() -> ArchiveConfig:
    return ArchiveConfig(
        path=_env_path(),
        retention_hours=max(0.1, _env_retention_hours()),
        segment_seconds=max(2, _env_segment_seconds()),
        max_fragment_seconds=max(1, _env_max_fragment_seconds()),
    )


def parse_archive_config(raw: Any) -> ArchiveConfig:
    """Собрать настройки из JSON хранилища. Пустые поля дополняются окружением."""
    base = default_archive_config()
    if raw is None:
        return base
    if isinstance(raw, str):
        import json
        raw = json.loads(raw) if raw.strip() else {}
    if not isinstance(raw, dict):
        raise ValueError("Конфигурация видеоархива должна быть объектом JSON.")

    path_raw = raw.get("path")
    if path_raw:
        path = Path(str(path_raw)).expanduser()
        if not path.is_absolute():
            raise ValueError("Путь архива должен быть абсолютным.")
        path = path.resolve()
    else:
        path = base.path

    hours = base.retention_hours
    if raw.get("retentionHours") is not None and raw.get("retentionHours") != "":
        hours = float(raw["retentionHours"])
    if hours <= 0:
        raise ValueError("Время хранения архива должно быть больше нуля.")

    segment = base.segment_seconds
    if raw.get("segmentSeconds") is not None and raw.get("segmentSeconds") != "":
        segment = int(raw["segmentSeconds"])
    if segment < 2:
        raise ValueError("Длина сегмента должна быть не меньше 2 секунд.")

    limit = base.max_fragment_seconds
    if raw.get("maxFragmentSeconds") is not None and raw.get("maxFragmentSeconds") != "":
        limit = int(raw["maxFragmentSeconds"])
    if limit < 1:
        raise ValueError("Максимальная длина фрагмента должна быть больше нуля.")

    return ArchiveConfig(
        path=path,
        retention_hours=hours,
        segment_seconds=segment,
        max_fragment_seconds=limit,
    )


_current = default_archive_config()


def current_archive() -> ArchiveConfig:
    return _current


def apply_archive_config(config: ArchiveConfig) -> ArchiveConfig:
    global _current
    _current = config
    return _current


def reset_archive_config() -> ArchiveConfig:
    return apply_archive_config(default_archive_config())
