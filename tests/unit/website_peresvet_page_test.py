from pathlib import Path

PAGE = Path(__file__).resolve().parents[2] / "website" / "peresvet"


def test_peresvet_card_keeps_public_links_and_assets():
    html = (PAGE / "index.html").read_text(encoding="utf-8")
    for url in (
        "https://github.com/mp-co-ru/peresvet",
        "https://github.com/mp-co-ru/peresvet/releases",
        "https://mp-co-ru.github.io/peresvet/",
        "https://mp-co-ru.github.io/peresvet/installation.html",
        "https://github.com/mp-co-ru/peresvet_examples",
        "https://ioterra.ru/ioterra_oee",
        "mailto:info@ioterra.ru",
    ):
        assert url in html
    assert "form1334222151" not in html
    assert "peresvet-based" not in html
    css = (PAGE / "styles-3d.css").read_text(encoding="utf-8")
    assert "#4c2c2c" in css
    assert "#fb6b3b" in css
    assert "#105060" not in css
    for name in (
        "styles-3d.css",
        "logo.svg",
        "illustrations/model.svg",
        "illustrations/tags.svg",
        "illustrations/action.svg",
    ):
        assert (PAGE / name).is_file()
    assert not (PAGE / "peresvet-based-wide.svg").exists()
