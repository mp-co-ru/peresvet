import sys
import tempfile
from pathlib import Path


# Ensure repository root is on sys.path so `import src...` works
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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
    ):
        return _orig(
            cls,
            level=level,
            file_name=_pytest_log_file_path(),
            retention=retention,
            rotation=rotation,
        )

    PrsLogger.make_logger = classmethod(_wrapped)  # type: ignore[method-assign]


_patch_prs_logger_for_tests()

