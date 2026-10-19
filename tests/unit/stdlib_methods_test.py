import asyncio
import importlib.util
from pathlib import Path


def _worker():
    path = Path(__file__).resolve().parents[2] / "methods" / "packages" / "stdlib" / "worker.py"
    spec = importlib.util.spec_from_file_location("prs_stdlib_worker", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.rpc.project == "methods_app"
    return module


def test_stdlib_arithmetic_accepts_numbers_and_legacy_envelopes():
    worker = _worker()
    envelope = {"data": [{"data": [[10, 2, None]]}]}
    assert asyncio.run(worker.add(1, 2)) == 3
    assert asyncio.run(worker.add(envelope, 3)) == 5
    assert asyncio.run(worker.sub(5, envelope)) == 3
    assert asyncio.run(worker.mul(3, 4)) == 12
    assert asyncio.run(worker.div(4, 2)) == 2


def test_stdlib_arithmetic_none_non_numeric_and_division_by_zero_are_errors():
    worker = _worker()
    for name in ("add", "sub", "mul", "div"):
        result = asyncio.run(getattr(worker, name)(None, 1))
        assert "error" in result
        result = asyncio.run(getattr(worker, name)("нет", 1))
        assert "error" in result
    zero = asyncio.run(worker.div(1, 0))
    assert zero["error"] == "деление на ноль"
    missing = asyncio.run(worker.add({"data": [{"data": [[1, None, None]]}]}, 1))
    assert "error" in missing
