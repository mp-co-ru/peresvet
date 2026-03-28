#!/usr/bin/env python3
"""Fix Configurator.json HTML: unbreak attributes-form, move v2 panel below properties, tree lines CSS."""
import json
import re
from pathlib import Path

CFG = Path(__file__).resolve().parents[1] / "src/configurator_grafana/Configurator.json"


def extract_balanced_div(html: str, start: int) -> tuple[str, int, int]:
    """Return (block, start, end_exclusive) for outer div starting at start."""
    depth = 0
    pos = start
    while pos < len(html):
        if html.startswith("<div", pos):
            depth += 1
            pos = html.find(">", pos) + 1
            continue
        if html.startswith("</div>", pos):
            depth -= 1
            pos += 6
            if depth == 0:
                return html[start:pos], start, pos
            continue
        pos += 1
    raise ValueError("unbalanced div")


def main() -> None:
    data = json.loads(CFG.read_text(encoding="utf-8"))
    html = data["panels"][0]["options"]["html"]
    css = data["panels"][0]["options"]["css"]

    # 1) Remove erroneous </div> after connector block (was closing attributes-form early)
    old_err = (
        "\t\t\t</select>\n"
        "\t\t\t</div>\n\n"
        "\t\t\t</div>\n"
        '\t\t\t<div class="input-group mt-2" id="div-prsMethodAddress">'
    )
    new_err = (
        "\t\t\t</select>\n"
        "\t\t\t</div>\n\n"
        '\t\t\t<div class="input-group mt-2" id="div-prsMethodAddress">'
    )
    if old_err not in html:
        raise SystemExit("pattern (connector/method) not found — already fixed?")
    html = html.replace(old_err, new_err, 1)

    # 2) Extract and remove prs-ds-linked-tag-panel from top of right column
    needle = '<div id="prs-ds-linked-tag-panel"'
    ps = html.find(needle)
    if ps < 0:
        raise SystemExit("prs-ds-linked-tag-panel not found")
    block, _, end = extract_balanced_div(html, ps)
    html = html[:ps] + html[end:].lstrip("\n")

    panel_new = block.replace(
        'class="p-2 d-none flex-shrink-0 border-bottom"',
        'class="p-2 d-none flex-shrink-0 border-top mt-3 prs-linked-tag-panel"',
    )

    # 3) Insert panel after div-tagData (after </details>… closes inner structure)
    anchor = "</details>\n\t\t\t\t</div>\n\t\t\t</div>"
    ins = html.rfind(anchor)
    if ins < 0:
        raise SystemExit("tagData closing anchor not found")
    ins += len(anchor)
    html = html[:ins] + "\n\n\t\t\t" + panel_new + html[ins:]

    # 4) Remove runaway </div> sequences before end of document (if any)
    # Typical corruption: many </div> in a row before final wrappers
    tail = html[-3000:]
    if tail.count("</div>") > 25:
        # collapse 6+ consecutive closing-only lines to 4 (main-container depth)
        html = re.sub(
            r"(?:\s*</div>\s*){8,}(\s*</div>\s*</div>\s*</div>\s*</div>\s*</div>\s*$)",
            r"\1",
            html,
            count=1,
        )

    data["panels"][0]["options"]["html"] = html

    # 5) CSS: tree guides + replace thick tag borders with inset shadow (no clash with group border)
    old_tree = r"""#tree \.list-group-item\.prsTag\.prs-tag-tree-linked \{
  border-left: 3px solid var\(--ioterra-teal[^}]+\}
#tree \.list-group-item\.prsTag\.prs-tag-tree-unlinked \{
  border-left: 3px solid var\(--ioterra-rust[^}]+\}
"""
    css = re.sub(old_tree, "", css, count=1)

    css_add = """
/* Вертикальная направляющая дерева — одна линия на уровень вложенности */
#tree .list-group[role="group"] {
  border-left: 1px solid var(--prs-border, #dee2e6);
  margin-left: 0.35rem;
  padding-left: 0.2rem;
}
/* Подсказка привязки к БД — тонкая полоска, не конфликтует с линией группы */
#tree .list-group-item.prsTag.prs-tag-tree-linked,
#tree .list-group-item.prsTag.prs-tag-tree-unlinked {
  border-left: none !important;
  padding-left: 0.5rem;
}
#tree .list-group-item.prsTag.prs-tag-tree-linked {
  box-shadow: inset 3px 0 0 var(--ioterra-teal, #2c707f);
}
#tree .list-group-item.prsTag.prs-tag-tree-unlinked {
  box-shadow: inset 3px 0 0 rgba(163, 74, 40, 0.55);
}
/* Панель v2 привязки — под полями формы */
.prs-linked-tag-panel {
  max-width: 100%;
}
"""
    if "prs-linked-tag-panel" not in css or "box-shadow: inset 3px" not in css:
        css = css.rstrip() + css_add

    data["panels"][0]["options"]["css"] = css

    CFG.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("OK:", CFG)


if __name__ == "__main__":
    main()
