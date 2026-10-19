from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CI_REQUIREMENTS = ROOT / "requirements_make_docs.txt"


def test_ci_installs_runtime_packages_used_by_unit_tests():
    """GitHub Actions installs requirements_make_docs.txt, not requirements.txt."""
    text = CI_REQUIREMENTS.read_text(encoding="utf-8")
    assert "jsonatapy==2.1.0" in text
    assert "PyYAML==6.0.3" in text


def test_docs_publish_does_not_race_on_gh_pages():
    workflow = (ROOT / ".github/workflows/build_sphinx_docs.yml").read_text(encoding="utf-8")
    assert "group: gh-pages" in workflow
    assert "cancel-in-progress: false" in workflow
    fetch_at = workflow.index("refs/heads/gh-pages:refs/remotes/origin/gh-pages")
    publish_at = workflow.index("ghp-import -n -p -f docs/build")
    assert fetch_at < publish_at
    assert "max_attempts=5" in workflow
