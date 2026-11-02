"""Режет элементарный поток H.264 на кадры по разделителям AUD.

ffmpeg для живого WebRTC ставит AUD перед каждым кадром
(``x264-params aud=1``). Кадр — байты от одного AUD до следующего.
SPS и PPS перед первым AUD входят в этот кадр.
"""

from __future__ import annotations


def _aud_starts(buf: bytearray | bytes) -> list[int]:
    starts: list[int] = []
    index = 0
    while True:
        found = buf.find(b"\x00\x00\x01", index)
        if found < 0:
            return starts
        nal = found + 3
        if nal < len(buf) and (buf[nal] & 0x1F) == 9:
            start = found - 1 if found > 0 and buf[found - 1] == 0 else found
            starts.append(start)
        index = found + 3


def pop_access_units(buffer: bytearray, chunk: bytes) -> list[bytes]:
    """Достаёт целые кадры. Неполный хвост остаётся в buffer."""
    if chunk:
        buffer.extend(chunk)
    units: list[bytes] = []
    while True:
        starts = _aud_starts(buffer)
        if len(starts) < 2:
            return units
        end = starts[1]
        if end <= 0:
            return units
        units.append(bytes(buffer[:end]))
        del buffer[:end]
