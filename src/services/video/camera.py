"""Правила камеры: адрес RTSP, режим GET и команды ffmpeg.

Живой поток, архив и снимок идут из одного процесса ffmpeg.
Второй RTSP-клиент к дешёвой камере часто рвёт первый.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from src.common.consts import CNConnectorTypes

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_RTSP_USERINFO_RE = re.compile(r"(rtsps?://)([^/\s@]+)@")


KEY_RTSP = "rtspUrl"
KEY_ARCHIVE = "archivePath"
KEY_RETENTION = "retentionHours"


def _config_dict(raw: Any) -> dict:
    if isinstance(raw, str):
        raw = json.loads(raw) if raw.strip() else {}
    if not isinstance(raw, dict):
        raise ValueError("Конфигурация камеры должна быть объектом JSON.")
    return raw


def _pick(raw: dict, *keys: str) -> Any:
    for key in keys:
        if key in raw and raw[key] not in (None, ""):
            return raw[key]
    return None


def config_is_camera(raw: Any) -> bool:
    """Камера — коннектор, в чьём prsJsonConfigString есть ключ rtspUrl."""
    try:
        data = _config_dict(raw)
    except (ValueError, json.JSONDecodeError, TypeError):
        return False
    return _pick(data, KEY_RTSP) is not None


def is_camera_connector(entity_type_code: Any) -> bool:
    try:
        return int(entity_type_code) == int(CNConnectorTypes.CN_CAMERA)
    except (TypeError, ValueError):
        return False


def is_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(value or ""))


def redact_rtsp(text: str) -> str:
    """Убирает userinfo из rtsp://user:pass@host, чтобы пароль не попал в лог."""
    return _RTSP_USERINFO_RE.sub(r"\1", text or "")


@dataclass(frozen=True)
class CameraConfig:
    rtsp_url: str
    transport: str
    archive_path: Path | None = None
    retention_hours: float = 24.0

    @property
    def log_target(self) -> str:
        parts = urlsplit(self.rtsp_url)
        port = f":{parts.port}" if parts.port else ""
        return f"{parts.scheme}://{parts.hostname}{port}{parts.path}"

    def segment_dir(self, connector_id: str) -> Path:
        if self.archive_path is not None:
            return self.archive_path
        from src.services.video.archive_config import default_archive_config
        return default_archive_config().path / connector_id


def parse_camera_config(raw: Any) -> CameraConfig:
    raw = _config_dict(raw)
    url = str(_pick(raw, KEY_RTSP) or "").strip()
    parts = urlsplit(url)
    if parts.scheme not in ("rtsp", "rtsps") or not parts.hostname:
        raise ValueError(
            "В prsJsonConfigString нужен ключ rtspUrl вида rtsp://хост/путь."
        )
    transport = str(raw.get("rtspTransport") or "tcp").strip().lower()
    if transport not in ("tcp", "udp"):
        transport = "tcp"
    archive_path = None
    path_raw = str(_pick(raw, KEY_ARCHIVE) or "").strip()
    if path_raw:
        archive_path = Path(path_raw).expanduser()
        if not archive_path.is_absolute():
            raise ValueError("Ключ archivePath должен быть абсолютным путём.")
        archive_path = archive_path.resolve()
    retention = 24.0
    retention_raw = _pick(raw, KEY_RETENTION)
    if retention_raw is not None:
        retention = float(retention_raw)
    if retention <= 0:
        raise ValueError("Ключ retentionHours должен быть больше нуля.")
    return CameraConfig(
        rtsp_url=url,
        transport=transport,
        archive_path=archive_path,
        retention_hours=retention,
    )


def video_get_mode(fields: set[str]) -> str:
    """Режим чтения тега типа 6 по тем ключам, которые клиент действительно передал.

    ``finish`` по умолчанию подставляется платформой, но в набор полей не входит,
    если клиент его не прислал.
    """
    if "timeStep" in fields or "count" in fields:
        return "unsupported"
    if "start" in fields:
        return "fragment"
    if "finish" in fields:
        return "snapshot"
    return "live"


def archive_dir() -> Path:
    from src.services.video.archive_config import current_archive
    return current_archive().path


def segment_seconds() -> int:
    from src.services.video.archive_config import current_archive
    return current_archive().segment_seconds


def archive_keep_seconds() -> int:
    from src.services.video.archive_config import current_archive
    return int(current_archive().retention_hours * 3600)


def max_fragment_seconds() -> int:
    from src.services.video.archive_config import current_archive
    return current_archive().max_fragment_seconds


def ffmpeg_bin() -> str:
    return os.environ.get("FFMPEG_BIN", "ffmpeg")


def live_snapshot_skew_us() -> int:
    return 3_000_000


@dataclass(frozen=True)
class Segment:
    start_us: int
    end_us: int
    path: Path


def list_segments(directory: Path, *, segment_seconds_value: int, now_us: int) -> list[Segment]:
    if not directory.is_dir():
        return []
    starts: list[tuple[int, Path]] = []
    for path in directory.glob("*.ts"):
        try:
            start_sec = int(path.stem)
        except ValueError:
            continue
        starts.append((start_sec * 1_000_000, path))
    starts.sort(key=lambda item: item[0])
    segments: list[Segment] = []
    span = segment_seconds_value * 1_000_000
    for index, (start_us, path) in enumerate(starts):
        if index + 1 < len(starts):
            end_us = starts[index + 1][0]
        else:
            end_us = max(start_us + span, now_us)
        segments.append(Segment(start_us=start_us, end_us=end_us, path=path))
    return segments


def segment_at(segments: list[Segment], moment_us: int) -> Segment | None:
    for segment in segments:
        if segment.start_us <= moment_us < segment.end_us:
            return segment
    return None


def segments_overlapping(segments: list[Segment], start_us: int, finish_us: int) -> list[Segment]:
    return [
        segment for segment in segments
        if segment.start_us < finish_us and segment.end_us > start_us
    ]


def session_ffmpeg_args(
    camera: CameraConfig,
    directory: Path,
    segment_seconds_value: int,
    ffmpeg: str | None = None,
) -> list[str]:
    pattern = str(directory / "%s.ts")
    return [
        ffmpeg or ffmpeg_bin(),
        "-hide_banner",
        "-loglevel", "error",
        "-rtsp_transport", camera.transport,
        "-timeout", "8000000",
        "-use_wallclock_as_timestamps", "1",
        "-fflags", "+genpts",
        "-i", camera.rtsp_url,
        "-map", "0:v:0", "-an",
        "-vf", "scale=640:-2",
        "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-pix_fmt", "yuv420p",
        "-f", "segment",
        "-segment_time", str(segment_seconds_value),
        "-segment_format", "mpegts",
        "-reset_timestamps", "1",
        "-strftime", "1",
        pattern,
        "-map", "0:v:0", "-an",
        "-vf", "fps=8,scale=960:-2",
        "-c:v", "mjpeg", "-q:v", "8",
        "-f", "mpjpeg",
        "pipe:1",
    ]


def snapshot_file_args(
    path: Path,
    offset_sec: float,
    ffmpeg: str | None = None,
) -> list[str]:
    """Один кадр JPEG из фрагмента.

    ``-ss`` стоит после ``-i``: у сегмента метки времени начинаются не с нуля,
    и поиск до входного файла часто не попадает в кадр.
    ``yuvj420p`` нужен, потому что архив — ограниченный YUV, а MJPEG его
    иначе не кодирует.
    """
    return [
        ffmpeg or ffmpeg_bin(),
        "-hide_banner", "-loglevel", "error",
        "-i", str(path),
        "-ss", f"{max(0.0, offset_sec):.3f}",
        "-an", "-frames:v", "1",
        "-pix_fmt", "yuvj420p",
        "-f", "image2pipe", "-vcodec", "mjpeg",
        "pipe:1",
    ]


def write_concat_list(path: Path, files: list[Path]) -> None:
    lines = []
    for file in files:
        escaped = str(file).replace("'", r"'\''")
        lines.append(f"file '{escaped}'")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def fragment_ffmpeg_args(
    concat_list: Path,
    output: Path,
    offset_sec: float,
    duration_sec: float,
    ffmpeg: str | None = None,
) -> list[str]:
    return [
        ffmpeg or ffmpeg_bin(),
        "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-ss", f"{max(0.0, offset_sec):.3f}",
        "-t", f"{max(0.1, duration_sec):.3f}",
        "-an",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output),
    ]
