"""Подмена адреса в SDP: браузер должен стучаться туда, откуда открыта страница."""

from __future__ import annotations


def host_from_header(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if text.startswith("["):
        end = text.find("]")
        return text[1:end] if end > 1 else ""
    if text.count(":") == 1:
        return text.split(":", 1)[0]
    return text


_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def advertise_sdp(sdp: str, host: str) -> str:
    """Меняет IP в candidate на адрес, с которого пришёл запрос страницы.

    Страница на 127.0.0.1 открыта через TCP-туннель. UDP-кандидат туда не
    доходит, и браузер долго ждёт его, прежде чем взять TCP. Для локального
    адреса UDP-кандидаты убираются.
    """
    host = (host or "").strip()
    if not host or not sdp:
        return sdp
    newline = "\r\n" if "\r\n" in sdp else "\n"
    lines = sdp.splitlines()
    rewritten: list[str] = []
    for line in lines:
        if line.startswith("a=candidate:"):
            parts = line.split(" ")
            if host in _LOOPBACK and len(parts) >= 3 and parts[2].lower() == "udp":
                continue
            if len(parts) >= 6:
                parts[4] = host
                line = " ".join(parts)
        rewritten.append(line)
    text = newline.join(rewritten)
    if sdp.endswith(("\r\n", "\n")):
        text += newline
    return text
