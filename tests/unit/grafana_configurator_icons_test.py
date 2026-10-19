import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = ROOT / "src/grafana/configurator/Configurator.json"

# Glyphs previously drawn with font fallbacks. They render differently
# per installed font, so the dashboard must not depend on them.
FONT_GLYPHS = (
    "\\229E",  # object
    "\\1F3F7",  # tag
    "\\221E",  # connector
    "\\231A",  # schedule
    "\\237E",  # alert
    "\\2325",  # method
    "\\232B",  # trash
    "\\2913",  # download
    "\\2714",  # check
    "\\25B6",  # play
    "\\23F8",  # pause
    "\\21BB",  # rotate
    "\\228C",  # storage
    "\\2298",  # unlinked
    "\\26A1",  # no data source
)


def _css_and_js():
    options = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))["panels"][0]["options"]
    return options["css"], options["onRender"]


def test_tree_and_action_icons_are_inline_svg():
    css, javascript = _css_and_js()

    for glyph in FONT_GLYPHS:
        assert glyph not in css
    assert "Segoe UI Symbol" not in css
    assert "Noto Sans Symbols2" not in css
    # Icon pictures are declared on the elements. :root variables do not
    # apply inside the htmlgraphics shadow tree, so they cannot be used.
    assert "--prs-tree-rollup-strip-width:3.35rem}" in css
    # The status marks sit next to the node icon. A reserved 3.35rem column
    # and the extra child indent both opened a large gap.
    assert ">.prs-tree-rollup-strip{display:inline-flex;align-items:center;justify-content:flex-start;gap:3px;margin-right:.24rem;vertical-align:middle;box-sizing:border-box;flex:0 0 auto;width:auto;min-width:0;max-width:none}" in css
    assert ">.prs-tree-rollup-strip--spacer{flex:0 0 0;width:0;min-width:0;max-width:0;margin:0;padding:0;overflow:hidden}" in css
    assert "spacer-after-indicator-extra,1.35rem)" not in css
    assert "prs-tree-rollup-strip--s.prs-tree-rollup-strip--d .prs-tree-rollup-dot--storage+.prs-tree-rollup-dot--nods{margin-left:.45rem}" in css
    assert "#tree .list-group-item[role=treeitem] .prs-tree-rollup-dot--storage+.prs-tree-rollup-dot--nods{margin-left:.45rem}" not in css
    assert 'opacity="0.4"' not in javascript
    assert 'stroke="currentColor" stroke-width="1.35" stroke-linejoin="round"/>' in javascript
    assert "padding:1px 4px" not in css
    assert "prs-tree-rollup-dot--storage{background:rgba(255,192,203,.72);padding:0;width:1.05rem;height:1.05rem;min-width:1.05rem;max-width:1.05rem;" in css
    assert '<rect x="2.15" y="2.15" width="11.7" height="11.7"' not in javascript
    assert '"fa-angle-down"' not in javascript.split("prsIconOrder=")[1].split("];")[0]
    assert "#tree .list-group-item[role=treeitem]>.state-icon svg{display:none!important}" in css
    assert "var(--prs-icon-" not in css

    for selector in (
        ".fa-solid.fa-object-group{--prs-icon:url('data:image/svg+xml,",
        ".fa-solid.fa-tag{--prs-icon:url('data:image/svg+xml,",
        ".fa-solid.fa-link{--prs-icon:url('data:image/svg+xml,",
        ".fa-solid.fa-clock{--prs-icon:url('data:image/svg+xml,",
        ".fa-solid.fa-bell{--prs-icon:url('data:image/svg+xml,",
        ".fa-solid.fa-file-code{--prs-icon:url('data:image/svg+xml,",
        ".fa-solid.fa-database{--prs-icon:url('data:image/svg+xml,",
        ".fa-solid.fa-magnifying-glass{--prs-icon:url('data:image/svg+xml,",
        ".fa.fa-angle-right{--prs-icon:url('data:image/svg+xml,",
        ".fa.fa-angle-down{--prs-icon:url('data:image/svg+xml,",
        ".fas.fa-check-circle{--prs-icon:url('data:image/svg+xml,",
        ".prs-tree-rollup-dot--inactive{--prs-icon:url('data:image/svg+xml,",
        ".prs-tree-rollup-dot--storage{--prs-icon:url('data:image/svg+xml,",
        ".prs-tree-rollup-dot--nods{--prs-icon:url('data:image/svg+xml,",
        "background-image:url('data:image/svg+xml,",
    ):
        assert selector in css

    assert "mask-image:var(--prs-icon)" in css
    assert "-webkit-mask-image:var(--prs-icon)" in css

    # Icons are drawn as SVG inside the icon element. The panel shadow tree
    # does not apply mask images reliably, so a stylesheet glyph is not enough.
    assert "prsInstallIcons(t)" in javascript
    assert "if(node.querySelectorAll)node.querySelectorAll('i')" in javascript
    assert "data-prs-icon" in javascript
    assert 'stroke="currentColor"' in javascript
    assert "content:none!important" in css
    assert 'item-icon fa-solid fa-tag' in javascript
    assert 'expandIcon:"fa fa-angle-down fa-fw"' in javascript
    assert "fa-solid fa-play" in javascript
    assert "fa-solid fa-pause" in javascript

    # Field help stays the drawn circled "i", not a font dingbat.
    assert "i.fa-solid.fa-circle-info{box-sizing:border-box" in css
    assert '.fa-solid.fa-circle-info::before{content:"i"' in css
