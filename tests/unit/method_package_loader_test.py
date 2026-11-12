"""Сервис methods не читает пакеты с диска и не создаёт их при старте."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_methods_service_does_not_load_packages_from_disk():
    service = (ROOT / "src/services/methods/model_crud/methods_model_crud_svc.py").read_text(encoding="utf-8")
    assert "seed_method_packages" not in service
    assert "method_package_loader" not in service
    assert "PRS_METHOD_PACKAGES_DIR" not in service
    assert not (ROOT / "src/services/methods/model_crud/method_package_loader.py").exists()
    assert not (ROOT / "docker/compose/docker-compose.method-packages.yml").exists()
    dockerfile = (ROOT / "docker/docker-files/all/Dockerfile.one_app.uvicorn").read_text(encoding="utf-8")
    assert "methods/packages" not in dockerfile
    for name in (
        "packaging/build_product_distribution.sh",
        "packaging/build_dev_distribution.sh",
        "packaging/mcp_launch.sh",
        "run_one_app.sh",
        ".env.example",
    ):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "methods/packages" not in text
        assert "PRS_METHOD_PACKAGES_DIR" not in text
        assert "docker-compose.method-packages.yml" not in text
