"""Разговор в динамик камеры протоколом iCSee, порт 34567.

Это не второй RTSP-сеанс: картинку по-прежнему держит один ffmpeg.
Звук с микрофона браузера приходит сюда уже как G.711 A-law, 8000 Гц.
"""

from __future__ import annotations

import json
import re
import socket
import struct
import threading
from hashlib import md5
from urllib.parse import unquote, urlsplit

from src.services.video.camera import CameraConfig

_TALK_PORT = 34567
_LOGIN = 1000
_TALK_CLAIM = 1434
_TALK_START = 1430
_TALK_DATA = 1432
_FRAME = 320
_ALAW_SILENCE = 0xD5
_PATH_LOGIN = re.compile(r"user=([^_]+)_password=(.+?)_channel=")
_SOFIA = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

_busy: set[str] = set()
_busy_guard = threading.Lock()


class CameraTalkError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def talk_reject_message(ret) -> str:
    if ret == 203:
        return (
            "Камера не приняла пароль разговора. "
            "В конфигурации коннектора укажите onvifUser и onvifPassword: "
            "это логин iCSee, не пароль из адреса RTSP."
        )
    if ret in (205, 206):
        return "Камера временно заблокировала вход. Подождите или перезагрузите её."
    return "Камера не приняла разговор."


def sofia_hash(password: str) -> str:
    """Свёртка пароля, которую ждёт прошивка iCSee. Сам пароль в пакет не входит."""
    digest = md5(password.encode("utf-8")).digest()
    return "".join(_SOFIA[(digest[i] + digest[i + 1]) % 62] for i in range(0, 16, 2))


def talk_credentials(camera: CameraConfig) -> tuple[str, str] | None:
    if camera.onvif_user and camera.onvif_password:
        return camera.onvif_user, camera.onvif_password
    parts = urlsplit(camera.rtsp_url)
    if parts.username:
        return unquote(parts.username), unquote(parts.password or "")
    match = _PATH_LOGIN.search(parts.path)
    if not match:
        return None
    return match.group(1), match.group(2)


def claim_talk(connector_id: str) -> bool:
    with _busy_guard:
        if connector_id in _busy:
            return False
        _busy.add(connector_id)
        return True


def release_talk(connector_id: str) -> None:
    with _busy_guard:
        _busy.discard(connector_id)


def talk_packet(command: int, payload: bytes, session: int = 0, sequence: int = 0) -> bytes:
    header = bytearray(20)
    header[0] = 255
    struct.pack_into("<I", header, 4, session)
    struct.pack_into("<I", header, 8, sequence)
    struct.pack_into("<H", header, 14, command)
    struct.pack_into("<I", header, 16, len(payload))
    return bytes(header) + payload


def pcma_frame(payload: bytes) -> bytes:
    chunk = payload[:_FRAME]
    if len(chunk) < _FRAME:
        chunk = chunk + bytes([_ALAW_SILENCE]) * (_FRAME - len(chunk))
    head = bytearray(8)
    head[2] = 1
    head[3] = 0xFA
    head[4] = 14
    head[5] = 2
    struct.pack_into("<H", head, 6, _FRAME)
    return bytes(head) + chunk


class CameraTalk:
    def __init__(self, host: str, user: str, password: str, port: int = _TALK_PORT):
        self._host = host
        self._user = user
        self._password = password
        self._port = port
        self._sock: socket.socket | None = None
        self._session = 0
        self._seq = 0
        self._pending = bytearray()
        self._lock = threading.Lock()
        self._closed = False
        self._drain: threading.Thread | None = None

    def start(self) -> None:
        try:
            self._sock = socket.create_connection((self._host, self._port), timeout=5)
            self._sock.settimeout(5)
        except OSError as ex:
            raise CameraTalkError("Камера не открыла канал разговора.") from ex
        login = json.dumps({
            "EncryptType": "MD5",
            "LoginType": "DVRIP-Web",
            "PassWord": sofia_hash(self._password),
            "UserName": self._user,
        }, separators=(",", ":")) + "\n\x00"
        self._write(_LOGIN, login.encode("utf-8"))
        self._read_ok()
        self._talk("Claim", _TALK_CLAIM)
        self._talk("Start", _TALK_START)
        self._drain = threading.Thread(target=self._discard_replies, daemon=True)
        self._drain.start()

    def write_pcma(self, data: bytes) -> None:
        if not data or self._closed:
            return
        with self._lock:
            self._pending.extend(data)
            while len(self._pending) >= _FRAME:
                frame = bytes(self._pending[:_FRAME])
                del self._pending[:_FRAME]
                self._write(_TALK_DATA, pcma_frame(frame))

    def close(self) -> None:
        self._closed = True
        sock = self._sock
        self._sock = None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()

    def _talk(self, action: str, command: int) -> None:
        body = (
            '{"Name":"OPTalk","SessionID":"0x%08X","OPTalk":{"Action":"%s",'
            '"AudioFormat":{"EncodeType":"G711_ALAW"}}}\n\x00'
        ) % (self._session, action)
        self._write(command, body.encode("utf-8"))
        if action == "Claim":
            self._read_ok()

    def _write(self, command: int, payload: bytes) -> None:
        packet = talk_packet(command, payload, self._session, self._seq)
        self._seq += 1
        sock = self._sock
        if sock is None:
            raise CameraTalkError("Канал разговора уже закрыт.")
        try:
            sock.sendall(packet)
        except OSError as ex:
            raise CameraTalkError("Камера оборвала разговор.") from ex

    def _read_exact(self, size: int) -> bytes:
        sock = self._sock
        if sock is None:
            raise CameraTalkError("Канал разговора уже закрыт.")
        buf = bytearray()
        while len(buf) < size:
            try:
                chunk = sock.recv(size - len(buf))
            except socket.timeout as ex:
                raise CameraTalkError("Камера не ответила на разговор.") from ex
            except OSError as ex:
                raise CameraTalkError("Камера оборвала разговор.") from ex
            if not chunk:
                raise CameraTalkError("Камера закрыла разговор.")
            buf.extend(chunk)
        return bytes(buf)

    def _read_chunk(self) -> bytes:
        header = self._read_exact(20)
        if header[0] != 255:
            raise CameraTalkError("Камера ответила не тем протоколом.")
        self._session = struct.unpack_from("<I", header, 4)[0]
        size = struct.unpack_from("<I", header, 16)[0]
        if size > 1_000_000:
            raise CameraTalkError("Камера прислала слишком большой ответ.")
        return self._read_exact(size)

    def _read_ok(self) -> None:
        raw = self._read_chunk()
        body = raw[:-2] if raw.endswith(b"\x00") else raw.rstrip(b"\x00\n")
        try:
            parsed = json.loads(body.decode("utf-8", "replace"))
        except json.JSONDecodeError as ex:
            raise CameraTalkError("Камера не приняла разговор.") from ex
        ret = parsed.get("Ret")
        if ret not in (100, 515):
            raise CameraTalkError(talk_reject_message(ret))

    def _discard_replies(self) -> None:
        sock = self._sock
        if sock is None:
            return
        try:
            sock.settimeout(1)
        except OSError:
            return
        while not self._closed:
            try:
                if not sock.recv(4096):
                    return
            except socket.timeout:
                continue
            except OSError:
                return
