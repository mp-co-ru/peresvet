from datetime import datetime
from types import SimpleNamespace

from src.common.logger import PrsLogBuffer, PrsLogger


def test_log_buffer_append_tail_clear():
    PrsLogBuffer._entries.clear()
    PrsLogBuffer._clear_after_seq_by_service.clear()
    PrsLogBuffer._seq = 0
    PrsLogBuffer.append_from_record(
        {
            "message": "tags_app :: hello",
            "level": SimpleNamespace(name="INFO"),
            "time": datetime(2026, 1, 1),
            "extra": {},
        }
    )
    PrsLogBuffer.append_from_record(
        {
            "message": "methods_app: other",
            "level": SimpleNamespace(name="ERROR"),
            "time": None,
            "extra": {"service": "methods_app"},
        }
    )
    all_logs = PrsLogBuffer.tail(limit=10)
    assert len(all_logs) == 2
    tagged = PrsLogBuffer.tail(services=["tags_app"])
    assert tagged[0]["service"] == "tags_app"
    cleared = PrsLogBuffer.clear(services=["tags_app"])
    assert cleared == 1
    assert PrsLogBuffer.tail(services=["tags_app"]) == []
    rest = PrsLogBuffer.tail()
    assert any(e["service"] == "methods_app" for e in rest)
    n = PrsLogBuffer.clear()
    assert n >= 1
    assert PrsLogBuffer.tail() == []


def test_load_logging_config(tmp_path):
    p = tmp_path / "log.json"
    p.write_text('{"level": "INFO"}', encoding="utf-8")
    assert PrsLogger.load_logging_config(str(p)) == {"level": "INFO"}
    assert PrsLogBuffer._service_from_message("plain") == ""
    assert PrsLogBuffer._matches_service({"message": "s :: x", "service": "other"}, "s") is True
