"""Управление камерой по ONVIF: поворот, наклон, зум, дом и параметры изображения.

Сеанс RTSP при этом не открывается второй раз. Хост берётся из rtspUrl,
порт по умолчанию 8899. Логин нужен только если камера его требует.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import re
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from src.services.video.camera import CameraConfig

_PTZ_NS = "http://www.onvif.org/ver20/ptz/wsdl"
_SCHEMA_NS = "http://www.onvif.org/ver10/schema"
_DEVICE_NS = "http://www.onvif.org/ver10/device/wsdl"
_MEDIA_NS = "http://www.onvif.org/ver10/media/wsdl"
_IMAGING_NS = "http://www.onvif.org/ver20/imaging/wsdl"

_NUMBER_TAGS = {
    "brightness": "Brightness",
    "contrast": "Contrast",
    "saturation": "ColorSaturation",
    "sharpness": "Sharpness",
}
_MODE_TAGS = {
    "backlight": "BacklightCompensation",
    "wideDynamicRange": "WideDynamicRange",
    "irCut": "IrCutFilter",
    "whiteBalance": "WhiteBalance",
}

_profiles: dict[tuple, str] = {}
_ptz_paths: dict[tuple, str] = {}
_source_tokens: dict[tuple, str] = {}
_image_options: dict[tuple, dict] = {}
_tracks: dict[tuple, "_Track"] = {}
_track_guard = threading.Lock()


class _Track:
    """Камера не сообщает положение, поэтому путь копится из посланных скоростей."""

    def __init__(self) -> None:
        self.pan = 0.0
        self.tilt = 0.0
        self.zoom = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.vz = 0.0
        self.started: float | None = None
        self.cancel = threading.Event()

    def settle(self, now: float | None = None) -> None:
        if self.started is None:
            return
        elapsed = max(0.0, (now if now is not None else time.monotonic()) - self.started)
        self.pan += self.vx * elapsed
        self.tilt += self.vy * elapsed
        self.zoom += self.vz * elapsed
        self.started = None
        self.vx = self.vy = self.vz = 0.0

    def begin(self, pan: float, tilt: float, zoom: float) -> None:
        self.settle()
        self.cancel.clear()
        self.vx, self.vy, self.vz = pan, tilt, zoom
        self.started = time.monotonic()


def _track_for(camera: CameraConfig) -> _Track:
    key = _cache_key(camera)
    with _track_guard:
        track = _tracks.get(key)
        if track is None:
            track = _Track()
            _tracks[key] = track
        return track


class OnvifError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def password_digest(nonce: bytes, created: str, password: str) -> str:
    raw = nonce + created.encode("utf-8") + password.encode("utf-8")
    return base64.b64encode(hashlib.sha1(raw).digest()).decode("ascii")


def _axis(value, low: float = -1.0, high: float = 1.0) -> float:
    try:
        number = float(0 if value is None else value)
    except (TypeError, ValueError) as ex:
        raise OnvifError("Направление задаётся числом от -1 до 1.") from ex
    return max(low, min(high, number))


def _security_header(user: str | None, password: str | None) -> str:
    if not user:
        return ""
    nonce = os.urandom(16)
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    digest = password_digest(nonce, created, password or "")
    nonce_b64 = base64.b64encode(nonce).decode("ascii")
    return (
        "<s:Header><Security xmlns="
        '"http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">'
        "<UsernameToken>"
        f"<Username>{escape(user)}</Username>"
        '<Password Type="http://docs.oasis-open.org/wss/2004/01/'
        'oasis-200401-wss-username-token-profile-1.0#PasswordDigest">'
        f"{digest}</Password>"
        '<Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/'
        'oasis-200401-wss-soap-message-security-1.0#Base64Binary">'
        f"{nonce_b64}</Nonce>"
        '<Created xmlns="http://docs.oasis-open.org/wss/2004/01/'
        f'oasis-200401-wss-wssecurity-utility-1.0.xsd">{created}</Created>'
        "</UsernameToken></Security></s:Header>"
    )


def soap_envelope(body: str, user: str | None = None, password: str | None = None) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
        f"{_security_header(user, password)}"
        f"<s:Body>{body}</s:Body></s:Envelope>"
    )


def _fault_message(text: str) -> str | None:
    if "Fault" not in text:
        return None
    match = re.search(r"<(?:\w+:)?Text[^>]*>([^<]+)", text)
    if match and match.group(1).strip():
        return match.group(1).strip()
    return "Камера отклонила команду OnVif."


def _post(url: str, payload: str, action: str, timeout: float = 5) -> str:
    request = urllib.request.Request(url, data=payload.encode("utf-8"), method="POST")
    request.add_header(
        "Content-Type",
        f'application/soap+xml; charset=utf-8; action="{action}"',
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as ex:
        text = ex.read().decode("utf-8", "replace")
        fault = _fault_message(text)
        raise OnvifError(fault or "Камера не приняла команду OnVif.") from ex
    except urllib.error.URLError as ex:
        raise OnvifError("Камера не отвечает по OnVif.") from ex
    fault = _fault_message(text)
    if fault:
        raise OnvifError(fault)
    return text


def _cache_key(camera: CameraConfig) -> tuple:
    return (camera.onvif_host, camera.onvif_port, camera.onvif_user or "")


def _device_url(camera: CameraConfig) -> str:
    return f"http://{camera.onvif_host}:{camera.onvif_port}/onvif/device_service"


def _call(camera: CameraConfig, url: str, action: str, body: str) -> str:
    payload = soap_envelope(body, camera.onvif_user, camera.onvif_password)
    return _post(url, payload, action)


def _ptz_url(camera: CameraConfig) -> str:
    key = _cache_key(camera)
    cached = _ptz_paths.get(key)
    if cached:
        return cached
    text = _call(
        camera,
        _device_url(camera),
        f"{_DEVICE_NS}/GetCapabilities",
        f'<GetCapabilities xmlns="{_DEVICE_NS}"><Category>All</Category></GetCapabilities>',
    )
    match = re.search(r"(https?://[^<]*ptz_service)", text)
    url = match.group(1) if match else (
        f"http://{camera.onvif_host}:{camera.onvif_port}/onvif/ptz_service"
    )
    _ptz_paths[key] = url
    return url


def _media_url(camera: CameraConfig) -> str:
    return f"http://{camera.onvif_host}:{camera.onvif_port}/onvif/media_service"


def profile_token_from_profiles(text: str) -> str:
    for match in re.finditer(
        r"Profiles\b[^>]*\btoken=\"([^\"]+)\"([\s\S]*?)</[^>]*Profiles>",
        text,
    ):
        if "PTZ" in match.group(2):
            return match.group(1)
    raise OnvifError("У камеры нет профиля OnVif с поворотом.")


def _profile_token(camera: CameraConfig) -> str:
    key = _cache_key(camera)
    cached = _profiles.get(key)
    if cached:
        return cached
    text = _call(
        camera,
        _media_url(camera),
        f"{_MEDIA_NS}/GetProfiles",
        f'<GetProfiles xmlns="{_MEDIA_NS}"/>',
    )
    token = profile_token_from_profiles(text)
    _profiles[key] = token
    return token


def _velocity(pan: float, tilt: float, zoom: float, *, continuous: bool) -> str:
    if continuous:
        pan_space = "http://www.onvif.org/ver10/tptz/PanTiltSpaces/VelocityGenericSpace"
        zoom_space = "http://www.onvif.org/ver10/tptz/ZoomSpaces/VelocityGenericSpace"
    else:
        pan_space = "http://www.onvif.org/ver10/tptz/PanTiltSpaces/TranslationGenericSpace"
        zoom_space = "http://www.onvif.org/ver10/tptz/ZoomSpaces/TranslationGenericSpace"
    return (
        f'<PanTilt x="{pan:.4f}" y="{tilt:.4f}" space="{pan_space}" xmlns="{_SCHEMA_NS}"/>'
        f'<Zoom x="{zoom:.4f}" space="{zoom_space}" xmlns="{_SCHEMA_NS}"/>'
    )


def _move_body(token: str, tag: str, pan: float, tilt: float, zoom: float, timeout_s: int = 8) -> str:
    inner = "Velocity" if tag == "ContinuousMove" else "Translation"
    timeout = f"<Timeout>PT{max(1, int(timeout_s))}S</Timeout>" if tag == "ContinuousMove" else ""
    return (
        f'<{tag} xmlns="{_PTZ_NS}">'
        f"<ProfileToken>{escape(token)}</ProfileToken>"
        f"<{inner}>{_velocity(pan, tilt, zoom, continuous=tag == 'ContinuousMove')}</{inner}>"
        f"{timeout}</{tag}>"
    )


def camera_status(camera: CameraConfig) -> dict:
    token = _profile_token(camera)
    text = _call(
        camera,
        _ptz_url(camera),
        f"{_PTZ_NS}/GetStatus",
        f'<GetStatus xmlns="{_PTZ_NS}"><ProfileToken>{escape(token)}</ProfileToken></GetStatus>',
    )
    pan_tilt = re.search(
        r"PanTilt[^>]*\bx=\"([^\"]+)\"[^>]*\by=\"([^\"]+)\"",
        text,
    )
    zoom = re.search(r"Zoom[^>]*\bx=\"([^\"]+)\"", text)
    presets = _presets(camera, token)
    return {
        "profile": token,
        "pan": float(pan_tilt.group(1)) if pan_tilt else None,
        "tilt": float(pan_tilt.group(2)) if pan_tilt else None,
        "zoom": float(zoom.group(1)) if zoom else None,
        "presets": presets,
    }


def _presets(camera: CameraConfig, token: str) -> list[dict]:
    text = _call(
        camera,
        _ptz_url(camera),
        f"{_PTZ_NS}/GetPresets",
        f'<GetPresets xmlns="{_PTZ_NS}"><ProfileToken>{escape(token)}</ProfileToken></GetPresets>',
    )
    found = []
    for match in re.finditer(
        r"Preset\b[^>]*\btoken=\"([^\"]+)\"[^>]*>[\s\S]*?<(?:\w+:)?Name>([^<]*)</",
        text,
    ):
        found.append({"token": match.group(1), "name": match.group(2)})
    return found


def continuous_move(
    camera: CameraConfig,
    pan: float,
    tilt: float,
    zoom: float,
    timeout_s: int = 8,
) -> None:
    pan, tilt, zoom = _axis(pan), _axis(tilt), _axis(zoom)
    _track_for(camera).begin(pan, tilt, zoom)
    token = _profile_token(camera)
    _call(
        camera,
        _ptz_url(camera),
        f"{_PTZ_NS}/ContinuousMove",
        _move_body(token, "ContinuousMove", pan, tilt, zoom, timeout_s=timeout_s),
    )


def relative_move(camera: CameraConfig, pan: float, tilt: float, zoom: float) -> None:
    pan, tilt, zoom = _axis(pan), _axis(tilt), _axis(zoom)
    token = _profile_token(camera)
    _call(
        camera,
        _ptz_url(camera),
        f"{_PTZ_NS}/RelativeMove",
        _move_body(token, "RelativeMove", pan, tilt, zoom),
    )
    track = _track_for(camera)
    track.settle()
    track.pan += pan
    track.tilt += tilt
    track.zoom += zoom


def stop_move(camera: CameraConfig) -> None:
    track = _track_for(camera)
    track.cancel.set()
    track.settle()
    token = _profile_token(camera)
    _call(
        camera,
        _ptz_url(camera),
        f"{_PTZ_NS}/Stop",
        (
            f'<Stop xmlns="{_PTZ_NS}"><ProfileToken>{escape(token)}</ProfileToken>'
            "<PanTilt>true</PanTilt><Zoom>true</Zoom></Stop>"
        ),
    )


def zoom_pulse(camera: CameraConfig, direction: float, seconds: float = 0.9) -> None:
    """«Ближе» и «Дальше»: у этой камеры зум берёт только RelativeMove, не скорость."""
    step = 1.0 if _axis(direction) >= 0 else -1.0
    relative_move(camera, 0, 0, step)


def goto_home(camera: CameraConfig) -> None:
    track = _track_for(camera)
    stop_move(camera)
    zoom_left = track.zoom
    track.zoom = 0.0
    while abs(zoom_left) >= 0.5 and not track.cancel.is_set():
        step = -1.0 if zoom_left > 0 else 1.0
        token = _profile_token(camera)
        _call(
            camera,
            _ptz_url(camera),
            f"{_PTZ_NS}/RelativeMove",
            _move_body(token, "RelativeMove", 0, 0, step),
        )
        zoom_left += step
    span = max(abs(track.pan), abs(track.tilt))
    if span >= 0.2:
        seconds = min(8.0, span / 0.8)
        back_pan = max(-1.0, min(1.0, -track.pan / seconds))
        back_tilt = max(-1.0, min(1.0, -track.tilt / seconds))
        track.cancel.clear()
        continuous_move(camera, back_pan, back_tilt, 0, timeout_s=max(1, int(round(seconds))))
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if track.cancel.is_set():
                break
            time.sleep(0.05)
        stop_move(camera)
        track.pan = track.tilt = track.zoom = 0.0
    token = _profile_token(camera)
    _call(
        camera,
        _ptz_url(camera),
        f"{_PTZ_NS}/GotoHomePosition",
        f'<GotoHomePosition xmlns="{_PTZ_NS}"><ProfileToken>{escape(token)}</ProfileToken></GotoHomePosition>',
    )


def goto_preset(camera: CameraConfig, token_or_name: str) -> None:
    profile = _profile_token(camera)
    preset = token_or_name.strip()
    for item in _presets(camera, profile):
        if preset in (item["token"], item["name"]):
            preset = item["token"]
            break
    _call(
        camera,
        _ptz_url(camera),
        f"{_PTZ_NS}/GotoPreset",
        (
            f'<GotoPreset xmlns="{_PTZ_NS}"><ProfileToken>{escape(profile)}</ProfileToken>'
            f"<PresetToken>{escape(preset)}</PresetToken></GotoPreset>"
        ),
    )


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _named_child(parent: ET.Element, name: str) -> ET.Element | None:
    for child in list(parent):
        if _local_name(child.tag) == name:
            return child
    return None


def _named_children(parent: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in list(parent) if _local_name(child.tag) == name]


def _element_text(element: ET.Element | None) -> str:
    if element is None or element.text is None:
        return ""
    return element.text.strip()


def _find_local(root: ET.Element, name: str) -> ET.Element | None:
    for element in root.iter():
        if _local_name(element.tag) == name:
            return element
    return None


def imaging_settings_from_xml(text: str) -> dict:
    settings = _find_local(ET.fromstring(text), "ImagingSettings")
    if settings is None:
        raise OnvifError("Камера не сообщила параметры изображения.")
    found: dict = {}
    for key, tag in _NUMBER_TAGS.items():
        node = _named_child(settings, tag)
        raw = _element_text(node)
        if raw:
            found[key] = float(raw)
    for key, tag in _MODE_TAGS.items():
        node = _named_child(settings, tag)
        if node is None:
            continue
        if key == "irCut":
            raw = _element_text(node)
        else:
            raw = _element_text(_named_child(node, "Mode"))
        if raw:
            found[key] = raw
    return found


def imaging_options_from_xml(text: str) -> dict:
    options = _find_local(ET.fromstring(text), "ImagingOptions")
    if options is None:
        raise OnvifError("Камера не сообщила диапазоны изображения.")
    found: dict = {}
    for key, tag in _NUMBER_TAGS.items():
        node = _named_child(options, tag)
        if node is None:
            continue
        low = _element_text(_named_child(node, "Min"))
        high = _element_text(_named_child(node, "Max"))
        if low and high:
            found[key] = {"min": float(low), "max": float(high)}
    modes = [_element_text(item) for item in _named_children(options, "IrCutFilterModes")]
    modes = [item for item in modes if item]
    if modes:
        found["irCut"] = {"choices": modes}
    for key, tag in (
        ("backlight", "BacklightCompensation"),
        ("wideDynamicRange", "WideDynamicRange"),
        ("whiteBalance", "WhiteBalance"),
    ):
        node = _named_child(options, tag)
        if node is None:
            continue
        choices = [_element_text(item) for item in _named_children(node, "Mode")]
        choices = [item for item in choices if item]
        if choices:
            found[key] = {"choices": choices}
    return found


def _image_number(value, low: float, high: float) -> float:
    if isinstance(value, bool) or value is None:
        raise OnvifError("Параметр изображения задаётся числом.")
    try:
        number = float(value)
    except (TypeError, ValueError) as ex:
        raise OnvifError("Параметр изображения задаётся числом.") from ex
    return max(low, min(high, number))


def imaging_settings_body(token: str, values: dict, options: dict | None = None) -> str:
    options = options or {}
    parts: list[str] = []
    for key, tag in _NUMBER_TAGS.items():
        if key not in values:
            continue
        bounds = options.get(key) or {"min": 0.0, "max": 100.0}
        number = _image_number(values[key], float(bounds["min"]), float(bounds["max"]))
        parts.append(f"<tt:{tag}>{number:.1f}</tt:{tag}>")
    builders = {
        "backlight": lambda mode: (
            f"<tt:BacklightCompensation><tt:Mode>{escape(mode)}</tt:Mode></tt:BacklightCompensation>"
        ),
        "wideDynamicRange": lambda mode: (
            f"<tt:WideDynamicRange><tt:Mode>{escape(mode)}</tt:Mode></tt:WideDynamicRange>"
        ),
        "irCut": lambda mode: f"<tt:IrCutFilter>{escape(mode)}</tt:IrCutFilter>",
        "whiteBalance": lambda mode: (
            f"<tt:WhiteBalance><tt:Mode>{escape(mode)}</tt:Mode></tt:WhiteBalance>"
        ),
    }
    for key, builder in builders.items():
        if key not in values:
            continue
        mode = str(values[key]).strip()
        choices = (options.get(key) or {}).get("choices")
        if choices and mode not in choices:
            raise OnvifError("Камера не принимает такое значение.")
        parts.append(builder(mode))
    if not parts:
        raise OnvifError("Не задан параметр изображения.")
    return (
        f'<SetImagingSettings xmlns="{_IMAGING_NS}">'
        f"<VideoSourceToken>{escape(token)}</VideoSourceToken>"
        f"<ImagingSettings>{''.join(parts)}</ImagingSettings>"
        "<ForcePersistence>true</ForcePersistence></SetImagingSettings>"
    )


def _imaging_url(camera: CameraConfig) -> str:
    return f"http://{camera.onvif_host}:{camera.onvif_port}/onvif/image_service"


def _source_token(camera: CameraConfig) -> str:
    key = _cache_key(camera)
    cached = _source_tokens.get(key)
    if cached:
        return cached
    text = _call(
        camera,
        _media_url(camera),
        f"{_MEDIA_NS}/GetVideoSources",
        f'<GetVideoSources xmlns="{_MEDIA_NS}"/>',
    )
    match = re.search(r'VideoSources\b[^>]*\btoken="([^"]+)"', text)
    if not match:
        raise OnvifError("У камеры нет источника изображения.")
    _source_tokens[key] = match.group(1)
    return match.group(1)


def _imaging_options(camera: CameraConfig) -> dict:
    key = _cache_key(camera)
    cached = _image_options.get(key)
    if cached is not None:
        return cached
    token = _source_token(camera)
    text = _call(
        camera,
        _imaging_url(camera),
        f"{_IMAGING_NS}/GetOptions",
        (
            f'<GetOptions xmlns="{_IMAGING_NS}">'
            f"<VideoSourceToken>{escape(token)}</VideoSourceToken></GetOptions>"
        ),
    )
    parsed = imaging_options_from_xml(text)
    _image_options[key] = parsed
    return parsed


def imaging_status(camera: CameraConfig) -> dict:
    token = _source_token(camera)
    text = _call(
        camera,
        _imaging_url(camera),
        f"{_IMAGING_NS}/GetImagingSettings",
        (
            f'<GetImagingSettings xmlns="{_IMAGING_NS}">'
            f"<VideoSourceToken>{escape(token)}</VideoSourceToken></GetImagingSettings>"
        ),
    )
    return {"imaging": imaging_settings_from_xml(text), "options": _imaging_options(camera)}


def apply_imaging(camera: CameraConfig, command: dict) -> dict:
    values = {}
    for key in (*_NUMBER_TAGS, *_MODE_TAGS):
        if key in command and command[key] not in (None, ""):
            values[key] = command[key]
    options = _imaging_options(camera)
    _call(
        camera,
        _imaging_url(camera),
        f"{_IMAGING_NS}/SetImagingSettings",
        imaging_settings_body(_source_token(camera), values, options),
    )
    return imaging_status(camera)


async def perform_ptz(camera: CameraConfig, command: dict) -> dict:
    action = str(command.get("action") or "status").strip().lower()

    def _run() -> dict:
        if action == "status":
            return camera_status(camera)
        if action == "image":
            return imaging_status(camera)
        if action == "image_set":
            return apply_imaging(camera, command)
        if action == "move":
            continuous_move(camera, command.get("pan"), command.get("tilt"), command.get("zoom"))
        elif action == "step":
            relative_move(camera, command.get("pan"), command.get("tilt"), command.get("zoom"))
        elif action == "pulse":
            zoom_pulse(camera, command.get("zoom"))
        elif action == "stop":
            stop_move(camera)
        elif action == "home":
            goto_home(camera)
        elif action == "preset":
            token = str(command.get("token") or command.get("preset") or "").strip()
            if not token:
                raise OnvifError("Для перехода к пресету нужно его имя.")
            goto_preset(camera, token)
        else:
            raise OnvifError("Неизвестная команда камеры.")
        return {"ok": True, "action": action}

    return await asyncio.to_thread(_run)
