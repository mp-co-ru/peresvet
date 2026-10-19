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
KEY_ARCHIVE_WIDTH = "archiveWidth"
KEY_ARCHIVE_FPS = "archiveFps"
KEY_ONVIF_PORT = "onvifPort"
KEY_ONVIF_USER = "onvifUser"
KEY_ONVIF_PASSWORD = "onvifPassword"


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
    archive_width: int | None = None
    archive_fps: float | None = None
    onvif_port: int = 8899
    onvif_user: str | None = None
    onvif_password: str | None = None

    @property
    def onvif_host(self) -> str:
        return urlsplit(self.rtsp_url).hostname or ""

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


def _ldap_value(attrs: dict, name: str) -> Any:
    raw = attrs.get(name)
    if raw is None or raw == [] or raw == "":
        return None
    if isinstance(raw, (list, tuple)):
        raw = raw[0]
    if isinstance(raw, bytes):
        raw = raw.decode()
    return raw


def camera_from_connector_attributes(attrs: dict) -> CameraConfig | None:
    """Активная камера по атрибутам узла коннектора.

    ``None`` — коннектор выключен или в конфигурации нет ``rtspUrl``.
    ``ValueError`` — JSON или путь архива нельзя применить.
    """
    active = _ldap_value(attrs, "prsActive")
    if active is not None and str(active).upper() != "TRUE":
        return None
    raw = _ldap_value(attrs, "prsJsonConfigString")
    if isinstance(raw, str):
        raw = json.loads(raw) if raw.strip() else {}
    if not config_is_camera(raw or {}):
        return None
    return parse_camera_config(raw or {})


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
        archive_width=_optional_even_width(raw),
        archive_fps=_optional_fps(raw),
        onvif_port=_onvif_port(raw),
        onvif_user=_optional_text(raw, KEY_ONVIF_USER),
        onvif_password=_optional_text(raw, KEY_ONVIF_PASSWORD),
    )


def _optional_text(raw: dict, key: str) -> str | None:
    value = _pick(raw, key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _onvif_port(raw: dict) -> int:
    value = _pick(raw, KEY_ONVIF_PORT)
    if value is None:
        return 8899
    if isinstance(value, bool):
        raise ValueError("Ключ onvifPort должен быть портом от 1 до 65535.")
    try:
        port = int(value)
    except (TypeError, ValueError) as ex:
        raise ValueError("Ключ onvifPort должен быть портом от 1 до 65535.") from ex
    if port < 1 or port > 65535:
        raise ValueError("Ключ onvifPort должен быть портом от 1 до 65535.")
    return port


def _optional_even_width(raw: dict) -> int | None:
    value = _pick(raw, KEY_ARCHIVE_WIDTH)
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("Ключ archiveWidth должен быть чётной шириной в пикселях.")
    try:
        number = float(value)
    except (TypeError, ValueError) as ex:
        raise ValueError("Ключ archiveWidth должен быть чётной шириной в пикселях.") from ex
    width = int(number)
    if width != number or width < 2 or width % 2:
        raise ValueError("Ключ archiveWidth должен быть чётной шириной в пикселях.")
    return width


def _optional_fps(raw: dict) -> float | None:
    value = _pick(raw, KEY_ARCHIVE_FPS)
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("Ключ archiveFps должен быть больше нуля.")
    try:
        fps = float(value)
    except (TypeError, ValueError) as ex:
        raise ValueError("Ключ archiveFps должен быть больше нуля.") from ex
    if fps <= 0:
        raise ValueError("Ключ archiveFps должен быть больше нуля.")
    return fps


def _format_fps(fps: float) -> str:
    if fps == int(fps):
        return str(int(fps))
    return f"{fps:g}"


def archive_video_filter(camera: CameraConfig) -> str | None:
    """Фильтр архива. Пусто — в файл пишется размер и частота камеры."""
    parts: list[str] = []
    if camera.archive_fps is not None:
        parts.append(f"fps={_format_fps(camera.archive_fps)}")
    if camera.archive_width is not None:
        parts.append(f"scale={camera.archive_width}:-2")
    if not parts:
        return None
    return ",".join(parts)


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


def session_audio_args(target: str) -> list[str]:
    """Звук того же RTSP отдельным MP3. Картинка архива остаётся без звука."""
    return [
        "-map", "0:a:0?",
        "-vn",
        "-af", "aresample=async=1:first_pts=0",
        "-c:a", "libmp3lame",
        "-ar", "22050",
        "-ac", "1",
        "-b:a", "32k",
        "-f", "mp3",
        "-muxdelay", "0",
        "-muxpreload", "0",
        target,
    ]


def session_ffmpeg_args(
    camera: CameraConfig,
    directory: Path,
    segment_seconds_value: int,
    ffmpeg: str | None = None,
    *,
    audio_target: str | None = None,
) -> list[str]:
    pattern = str(directory / "%s.ts")
    archive_encode = [
        "-map", "0:v:0", "-an",
    ]
    video_filter = archive_video_filter(camera)
    if video_filter:
        archive_encode.extend(["-vf", video_filter])
    archive_encode.extend([
        "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-pix_fmt", "yuv420p",
        "-f", "segment",
        "-segment_time", str(segment_seconds_value),
        "-segment_format", "mpegts",
        "-reset_timestamps", "1",
        "-strftime", "1",
        pattern,
    ])
    args = [
        ffmpeg or ffmpeg_bin(),
        "-hide_banner",
        "-loglevel", "error",
        "-rtsp_transport", camera.transport,
        "-timeout", "8000000",
        "-use_wallclock_as_timestamps", "1",
        "-fflags", "+genpts",
        "-i", camera.rtsp_url,
        *archive_encode,
        "-map", "0:v:0", "-an",
        "-vf", "fps=8,scale=960:-2",
        "-c:v", "mjpeg", "-q:v", "8",
        "-f", "mpjpeg",
        "pipe:1",
    ]
    if audio_target is not None:
        preview = args.index("fps=8,scale=960:-2")
        insert_at = max(index for index, item in enumerate(args[:preview]) if item == "-map")
        args[insert_at:insert_at] = session_audio_args(audio_target)
    return args


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
