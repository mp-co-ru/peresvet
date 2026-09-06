import sys
import tempfile
import types
from pathlib import Path


# Ensure repository root is on sys.path so `import src...` works
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _patch_optional_dependency_stubs() -> None:
    try:
        from aio_pika import connect_robust  # noqa: F401
    except Exception:
        aio_pika_stub = sys.modules.get("aio_pika") or types.ModuleType("aio_pika")
        aio_pika_abc_stub = sys.modules.get("aio_pika.abc") or types.ModuleType("aio_pika.abc")

        async def _connect_robust(*_args, **_kwargs):
            return None

        for name in (
            "AbstractIncomingMessage",
            "AbstractRobustConnection",
            "AbstractRobustChannel",
            "AbstractRobustExchange",
            "AbstractRobustQueue",
        ):
            setattr(aio_pika_abc_stub, name, object)
        aio_pika_stub.connect_robust = _connect_robust
        aio_pika_stub.abc = aio_pika_abc_stub
        sys.modules["aio_pika"] = aio_pika_stub
        sys.modules["aio_pika.abc"] = aio_pika_abc_stub

    try:
        import ldap.filter  # noqa: F401
    except Exception:
        ldap_stub = sys.modules.get("ldap") or types.ModuleType("ldap")
        ldap_filter_stub = types.ModuleType("ldap.filter")
        ldap_filter_stub.escape_filter_chars = lambda value: str(value)
        ldap_stub.filter = ldap_filter_stub
        sys.modules["ldap"] = ldap_stub
        sys.modules["ldap.filter"] = ldap_filter_stub

# Импорт сервисов (например tags_app_api_svc) сразу создаёт loguru file sink на log/peresvet.log.
# В .venv/CI каталог log/ может быть только для чтения — перенаправляем файл лога в $TMPDIR.
def _pytest_log_file_path() -> str:
    d = Path(tempfile.gettempdir()) / "peresvet_pytest_logs"
    d.mkdir(parents=True, exist_ok=True)
    return str(d / "peresvet.log")


def _patch_prs_logger_for_tests() -> None:
    from src.common.logger import PrsLogger

    _orig = PrsLogger.__dict__["make_logger"].__func__

    def _wrapped(
        cls,
        level: str = "CRITICAL",
        file_name: str = "log/peresvet.log",
        retention: str = "1 months",
        rotation: str = "20 days",
        service_name: str = "",
        **kwargs,
    ):
        return _orig(
            cls,
            level=level,
            file_name=_pytest_log_file_path(),
            retention=retention,
            rotation=rotation,
            service_name=service_name,
            **kwargs,
        )

    PrsLogger.make_logger = classmethod(_wrapped)  # type: ignore[method-assign]


_patch_optional_dependency_stubs()
_patch_prs_logger_for_tests()

