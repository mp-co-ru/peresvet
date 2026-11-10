"""Ядро nginx не зависит от сервисов, которых может не быть у заказчика."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CORE_SERVERS = (
    "config/nginx/no_ssl/default.conf.no_ssl.template",
    "config/nginx/ssl/default.conf.ssl",
    "config/nginx/ssl/default.conf.ssl_letsencrypt.template",
    "src/services/one_app/nginx/no_ssl/default.conf.no_ssl.template",
)

NGINX_COMPOSE = (
    "docker/compose/docker-compose.nginx.one_app.yml",
    "docker/compose/docker-compose.nginx.one_app.ssl.yml",
    "docker/compose/docker-compose.nginx.one_app_ssl_letsencrypt.yml",
)

LOCATION_TEMPLATES = (
    "config/nginx/peresvet/locations/peresvet.locations.conf.template",
    "src/services/one_app/nginx/peresvet/locations/peresvet.locations.conf.template",
)

OPTIONAL_MOUNT = "../../config/nginx/optional:/etc/nginx/conf.d/optional:ro"


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_core_nginx_does_not_name_the_recognition_service():
    for path in LOCATION_TEMPLATES + CORE_SERVERS:
        text = _text(path)
        assert "prs-methods-video" not in text, path
        assert "/v1/vision/overlay" not in text, path


def test_optional_routes_are_included_and_mounted():
    for path in CORE_SERVERS:
        assert "include conf.d/optional/*.conf;" in _text(path), path
    for path in NGINX_COMPOSE:
        assert OPTIONAL_MOUNT in _text(path), path
    placeholder = _text("config/nginx/optional/00-empty.conf")
    assert placeholder.strip().startswith("#")
    assert "prs-methods-video" not in placeholder


def test_docs_describe_both_optional_launch_procedures():
    installation = _text("docs/source/installation.rst")
    readme = _text("README.md")
    mcp = _text("docs/source/mcp.rst")
    assert ".. _optional-own-port:" in installation
    assert ".. _optional-via-nginx:" in installation
    assert "--mcp-peresvet true" in installation
    assert "--mcp-grafana true" in installation
    assert "https://<хост>/mcp/peresvet" in installation
    assert "https://<хост>/mcp/grafana" in installation
    assert "config/nginx/optional/<сервис>.conf" in installation
    assert "prs-methods-video" in installation
    assert "peresvet-product-*.tar.gz" in installation
    assert "https://<хост>/mcp/peresvet" in readme
    assert "https://<хост>/mcp/peresvet" in mcp
    assert "https://grafana.com/docs/grafana/latest/administration/service-accounts/" in mcp
    assert ":ref:`optional-via-nginx`" in mcp
    secrets = _text("docker/compose/.cont_one_app.secrets.env.example")
    assert "GRAFANA_SERVICE_ACCOUNT_TOKEN=" in secrets
    assert "https://grafana.com/docs/grafana/latest/administration/service-accounts/" in secrets
    assert "PRS_MCP_PERESVET" in mcp
    for name in (
        "docker/compose/docker-compose.mcp.peresvet.yml",
        "docker/compose/docker-compose.mcp.grafana.yml",
    ):
        assert "\n    ports:" not in _text(name), name


def _launch(script: str, tmp_path: Path, *args: str, **env_extra: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PRS_LAUNCH_DRY_RUN"] = "1"
    env["PRS_SSL"] = "true"
    env["PRS_IP"] = ""
    env["PRS_MCP_PERESVET"] = "false"
    env["PRS_MCP_GRAFANA"] = "false"
    env["PRS_CONT_ENV_FILE"] = str(tmp_path / "cont.env")
    env["PRS_NGINX_OPTIONAL_DIR"] = str(tmp_path / "optional")
    env.update(env_extra)
    (tmp_path / "cont.env").write_text("NGINX_HOST=old\n", encoding="utf-8")
    return subprocess.run(
        ["bash", str(ROOT / script), *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_mcp_flags_default_to_false_and_publish_routes_only_when_enabled(tmp_path: Path):
    result = _launch("run_one_app.sh", tmp_path, "--ssl", "true")
    assert result.returncode == 0, result.stderr
    assert "mcp-peresvet=false" in result.stdout
    assert "mcp-grafana=false" in result.stdout
    assert "mcp-compose:" in result.stdout
    assert "docker-compose.mcp" not in result.stdout.split("mcp-compose:", 1)[1]
    assert not (tmp_path / "optional" / "mcp-peresvet.conf").exists()
    assert not (tmp_path / "optional" / "mcp-grafana.conf").exists()

    enabled = _launch(
        "run_one_app.sh",
        tmp_path,
        "--ssl",
        "true",
        "--mcp-peresvet",
        "true",
        "--mcp-grafana",
        "false",
    )
    assert enabled.returncode == 0, enabled.stderr
    assert "mcp-peresvet=true" in enabled.stdout
    assert "mcp-grafana=false" in enabled.stdout
    assert "docker-compose.mcp.peresvet.yml" in enabled.stdout
    assert "docker-compose.mcp.grafana.yml" not in enabled.stdout
    route = (tmp_path / "optional" / "mcp-peresvet.conf").read_text(encoding="utf-8")
    assert "set $mcp_peresvet mcp_peresvet;" in route
    assert "proxy_pass http://$mcp_peresvet:8000/mcp$is_args$args;" in route
    assert not (tmp_path / "optional" / "mcp-grafana.conf").exists()

    for script in (
        "run_one_app_dev.sh",
        "run_one_app_dev_no_build.sh",
        "run_one_app_ssl_letsencrypt.sh",
    ):
        dev = _launch(script, tmp_path, "--mcp-grafana", "true")
        assert dev.returncode == 0, (script, dev.stderr)
        assert "mcp-grafana=true" in dev.stdout
        assert "mcp-peresvet=false" in dev.stdout
        assert "docker-compose.mcp.grafana.yml" in dev.stdout

    for dotenv in (".env", ".env.example"):
        text = _text(dotenv)
        assert "PRS_MCP_PERESVET=false" in text
        assert "PRS_MCP_GRAFANA=false" in text
    image = "grafana/mcp-grafana:1.3.0"
    assert image in _text("docker/compose/docker-compose.mcp.grafana.yml")
    assert image in _text("packaging/mcp_launch.sh")
    for packaging in (
        "packaging/build_product_distribution.sh",
        "packaging/build_dev_distribution.sh",
    ):
        text = _text(packaging)
        assert '"config/nginx/mcp"' in text
        assert "docker-compose.mcp.peresvet.yml" in text
        assert "mcp_launch.sh" in text


def test_product_archive_ships_the_hook_without_recognition():
    for path in (
        "packaging/build_product_distribution.sh",
        "packaging/build_dev_distribution.sh",
    ):
        text = _text(path)
        assert '"config/nginx/optional"' in text, path
        assert '"config/nginx/mcp"' in text, path
    launcher = _text("run_one_app.sh")
    assert "prs-methods-video" not in launcher
    assert "docker-compose.video.yml" in launcher
