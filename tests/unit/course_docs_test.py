"""Пример с лампочкой снят, базовый курс вынесен в репозиторий курсов."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COURSE_REPO = "https://github.com/mp-co-ru/prs-peresvet-courses/tree/main/01.base"


def test_bulb_example_is_removed_from_the_manual():
    index = (ROOT / "docs/source/index.rst").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "examples/examples" not in index
    assert "examples/examples.html" not in readme
    assert not (ROOT / "docs/source/examples/examples.rst").exists()
    assert not (ROOT / "docs/source/examples.rst").exists()


def test_base_course_is_not_published_inside_the_manual():
    conf = (ROOT / "docs/source/conf.py").read_text(encoding="utf-8")
    index = (ROOT / "docs/source/index.rst").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    configurator = (ROOT / "docs/source/configurator/configurator.rst").read_text(encoding="utf-8")
    grafana = (ROOT / "docs/source/grafana/grafana_integration.rst").read_text(encoding="utf-8")
    assert "html_extra_path" not in conf
    assert not (ROOT / "docs/source/_extra").exists()
    assert "course/index.html" not in index
    for text in (index, readme, configurator, grafana):
        assert COURSE_REPO in text
