import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "run_one_app.sh"
CERT_SCRIPT = ROOT / "docker/docker-files/nginx/20-self-signed-cert.sh"
DOCKERFILE = ROOT / "docker/docker-files/nginx/Dockerfile.nginx"


def _run_launcher(
    tmp_path: Path,
    *args: str,
    dry_run: bool = False,
    prs_ip: str = "",
) -> subprocess.CompletedProcess[str]:
    env_file = tmp_path / "cont.env"
    env_file.write_text("NGINX_HOST=old\n", encoding="utf-8")
    env = os.environ.copy()
    env["PRS_CONT_ENV_FILE"] = str(env_file)
    env["PRS_LAUNCH_DRY_RUN"] = "1" if dry_run else "0"
    env["PRS_SSL"] = "false"
    env["PRS_IP"] = prs_ip
    return subprocess.run(
        ["bash", str(LAUNCHER), *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _san(cert: Path) -> str:
    result = subprocess.run(
        ["openssl", "x509", "-in", str(cert), "-noout", "-ext", "subjectAltName"],
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout


def test_launcher_warns_when_ip_is_missing(tmp_path: Path):
    env_file = tmp_path / "cont.env"
    before = "NGINX_HOST=old\n"
    env_file.write_text(before, encoding="utf-8")

    result = _run_launcher(tmp_path)

    assert result.returncode != 0
    assert "Предупреждение:" in result.stderr
    assert "PRS_IP" in result.stderr
    assert "--ip" in result.stderr
    assert env_file.read_text(encoding="utf-8") == before


def test_launcher_uses_prs_ip_from_env(tmp_path: Path):
    result = _run_launcher(tmp_path, dry_run=True, prs_ip="10.9.8.7")

    assert result.returncode == 0, result.stderr
    stored = (tmp_path / "cont.env").read_text(encoding="utf-8")
    assert "NGINX_TLS_IP=10.9.8.7" in stored


def test_cli_ip_overrides_prs_ip(tmp_path: Path):
    result = _run_launcher(tmp_path, "--ip", "10.1.2.3", dry_run=True, prs_ip="10.9.8.7")

    assert result.returncode == 0, result.stderr
    stored = (tmp_path / "cont.env").read_text(encoding="utf-8")
    assert "NGINX_TLS_IP=10.1.2.3" in stored
    assert "10.9.8.7" not in stored


def test_launcher_rejects_non_ipv4(tmp_path: Path):
    result = _run_launcher(tmp_path, "--ip", "not-an-ip")

    assert result.returncode != 0
    assert "IPv4" in result.stderr
    assert "NGINX_TLS_IP" not in (tmp_path / "cont.env").read_text(encoding="utf-8")


def test_launcher_stores_cli_ip_for_self_signed_https(tmp_path: Path):
    result = _run_launcher(tmp_path, "--ip", "10.1.2.3", "--ssl", "false", dry_run=True)

    assert result.returncode == 0, result.stderr
    assert "самоподписанный сертификат для 10.1.2.3" in result.stdout
    stored = (tmp_path / "cont.env").read_text(encoding="utf-8")
    assert "NGINX_TLS_IP=10.1.2.3" in stored


def test_prepared_certificate_mode_does_not_require_ip(tmp_path: Path):
    result = _run_launcher(tmp_path, "--ssl", "true", dry_run=True)

    assert result.returncode == 0, result.stderr
    assert "Предупреждение:" not in result.stderr
    assert "NGINX_TLS_IP" not in (tmp_path / "cont.env").read_text(encoding="utf-8")


def test_help_documents_ip_option():
    result = subprocess.run(
        ["bash", str(LAUNCHER), "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--ip ADDRESS" in result.stdout
    assert "PRS_IP" in result.stdout
    for dotenv in (ROOT / ".env", ROOT / ".env.example"):
        assert "PRS_IP=" in dotenv.read_text(encoding="utf-8")


def test_default_nginx_image_generates_cert_at_start():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert "192.168.1.50" not in dockerfile
    assert "20-self-signed-cert.sh" in dockerfile
    assert "NGINX_TLS_IP" in (ROOT / "docker/compose/docker-compose.nginx.one_app.yml").read_text(
        encoding="utf-8"
    )
    for packaging in (
        ROOT / "packaging/build_product_distribution.sh",
        ROOT / "packaging/build_dev_distribution.sh",
    ):
        assert "docker/docker-files/nginx/20-self-signed-cert.sh" in packaging.read_text(encoding="utf-8")


def test_self_signed_cert_uses_requested_ip(tmp_path: Path):
    openssl = shutil.which("openssl")
    if openssl is None:
        pytest.fail("openssl is required to check the self-signed certificate")

    env = os.environ.copy()
    env["NGINX_TLS_IP"] = "10.4.5.6"
    env["NGINX_HOST"] = "plant.local"
    env["NGINX_SSL_DIR"] = str(tmp_path)

    subprocess.run(["sh", str(CERT_SCRIPT)], env=env, check=True, capture_output=True, text=True)

    cert = tmp_path / "stand.crt"
    san = _san(cert)
    assert "IP Address:10.4.5.6" in san
    assert "IP Address:127.0.0.1" in san
    assert "DNS:localhost" in san
    assert "DNS:plant.local" in san
    assert "192.168.1.50" not in san

    subject = subprocess.run(
        ["openssl", "x509", "-in", str(cert), "-noout", "-subject", "-nameopt", "RFC2253"],
        text=True,
        capture_output=True,
        check=True,
    )
    assert "CN=10.4.5.6" in subject.stdout.replace(" ", "")

    first = cert.read_bytes()
    subprocess.run(["sh", str(CERT_SCRIPT)], env=env, check=True, capture_output=True, text=True)
    assert cert.read_bytes() == first

    env["NGINX_TLS_IP"] = "10.4.5.7"
    subprocess.run(["sh", str(CERT_SCRIPT)], env=env, check=True, capture_output=True, text=True)
    assert "IP Address:10.4.5.7" in _san(cert)
    assert cert.read_bytes() != first


def test_self_signed_cert_rejects_missing_ip(tmp_path: Path):
    env = os.environ.copy()
    env.pop("NGINX_TLS_IP", None)
    env["NGINX_SSL_DIR"] = str(tmp_path)

    result = subprocess.run(
        ["sh", str(CERT_SCRIPT)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "--ip" in result.stderr
    assert not (tmp_path / "stand.crt").exists()
