import re
from pathlib import Path

from changeatlas import render

TEMPLATE = Path(__file__).resolve().parents[1] / "changeatlas" / "template.html"


def payload():
    return {
        "release": "26.8", "generated": "2026-08-28",
        "nodes": [{"id": "a", "title": "A </script> sneaky", "type": "subsystem",
                   "repo": "atlas", "summary": "s", "tags": []}],
        "edges": [],
        "typeStyle": {"subsystem": {"label": "Subsystem", "color": "#4a9eea"}},
        "edgeLabel": {},
        "impact": {"changed": ["a"], "peripheral": []},
        "details": {"a": {"stories": [], "prs": []}},
    }


def test_render_embeds_everything(tmp_path):
    vis = tmp_path / "vis.js"
    vis.write_text("var vis = {};", encoding="utf-8")
    html = render.render(payload(), TEMPLATE, vis)
    assert "Release 26.8 — ChangeAtlas" in html
    assert "var vis = {};" in html
    assert '"changed": ["a"]'.replace(" ", "") in html.replace(" ", "")
    # tokens all consumed
    assert "/*__DATA__*/" not in html
    assert "/*__VISLIB__*/" not in html
    assert "/*__TITLE__*/" not in html
    assert "/*__PALETTE__*/" not in html


def test_render_escapes_script_close(tmp_path):
    vis = tmp_path / "vis.js"
    vis.write_text("", encoding="utf-8")
    html = render.render(payload(), TEMPLATE, vis)
    assert "</script> sneaky" not in html          # raw close tag must not survive
    assert "<\\/script> sneaky" in html


def test_output_self_contained(tmp_path):
    vis = tmp_path / "vis.js"
    vis.write_text("", encoding="utf-8")
    html = render.render(payload(), TEMPLATE, vis)
    assert not re.search(r'(src|href)\s*=\s*["\']https?://', html)
