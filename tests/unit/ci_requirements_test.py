from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CI_REQUIREMENTS = ROOT / "requirements_make_docs.txt"


def test_ci_installs_runtime_packages_used_by_unit_tests():
    """GitHub Actions installs requirements_make_docs.txt, not requirements.txt."""
    text = CI_REQUIREMENTS.read_text(encoding="utf-8")
    assert "jsonatapy==2.1.0" in text
    assert "PyYAML==6.0.3" in text
