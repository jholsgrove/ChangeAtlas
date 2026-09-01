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
    assert "/*__PALETTES__*/" not in html
    assert "/*__LOGO_LIGHT__*/" not in html
    assert "/*__LOGO_DARK__*/" not in html


def test_render_embeds_both_theme_palettes(tmp_path):
    vis = tmp_path / "vis.js"
    vis.write_text("", encoding="utf-8")
    html = render.render(payload(), TEMPLATE, vis)
    # Both themes injected for the in-report toggle; light tier colours differ
    # from dark so the toggle actually changes the graph.
    assert '"dark"' in html and '"light"' in html
    assert "#e0524a" in html   # dark changed fill
    assert "#c0392b" in html   # light changed fill


def test_render_embeds_logos_as_data_uris(tmp_path):
    vis = tmp_path / "vis.js"
    vis.write_text("", encoding="utf-8")
    html = render.render(payload(), TEMPLATE, vis)
    assert html.count("data:image/png;base64,") >= 2  # light + dark logo


def test_footer_links_to_github(tmp_path):
    vis = tmp_path / "vis.js"
    vis.write_text("", encoding="utf-8")
    html = render.render(payload(), TEMPLATE, vis)
    assert "https://github.com/jholsgrove/ChangeAtlas" in html


def test_render_escapes_script_close(tmp_path):
    vis = tmp_path / "vis.js"
    vis.write_text("", encoding="utf-8")
    html = render.render(payload(), TEMPLATE, vis)
    assert "</script> sneaky" not in html          # raw close tag must not survive
    assert "<\\/script> sneaky" in html


def test_output_self_contained(tmp_path):
    # Self-contained means the page fetches nothing to render: no external
    # scripts, styles, or images. Plain navigation anchors (the GitHub footer
    # link) are allowed — the browser loads nothing until clicked.
    vis = tmp_path / "vis.js"
    vis.write_text("", encoding="utf-8")
    html = render.render(payload(), TEMPLATE, vis)
    assert not re.search(r'src\s*=\s*["\']https?://', html)
    assert not re.search(r'<link[^>]+href\s*=\s*["\']https?://', html)
