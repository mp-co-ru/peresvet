from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CI_REQUIREMENTS = ROOT / "requirements_make_docs.txt"


def test_ci_installs_runtime_packages_used_by_unit_tests():
    """GitHub Actions installs requirements_make_docs.txt, not requirements.txt."""
    text = CI_REQUIREMENTS.read_text(encoding="utf-8")
    assert "jsonatapy-2.2.14-" in text
    assert "PyYAML==6.0.3" in text


def test_app_image_uses_ubuntu_2604_and_python_314_wheels():
    dockerfile = (ROOT / "docker/docker-files/all/Dockerfile.one_app.uvicorn").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/test.yml").read_text(encoding="utf-8")
    assert "FROM ubuntu:26.04" in dockerfile
    assert "/opt/venv/lib/python3.14/site-packages" in dockerfile
    assert "cp314" in requirements
    assert "cp312" not in requirements
    assert 'python-version: "3.14"' in workflow


def test_docs_publish_does_not_race_on_gh_pages():
    workflow = (ROOT / ".github/workflows/build_sphinx_docs.yml").read_text(encoding="utf-8")
    assert "group: gh-pages" in workflow
    assert "cancel-in-progress: false" in workflow
    fetch_at = workflow.index("refs/heads/gh-pages:refs/remotes/origin/gh-pages")
    publish_at = workflow.index("ghp-import -n -p -f docs/build")
    assert fetch_at < publish_at
    assert "max_attempts=5" in workflow
