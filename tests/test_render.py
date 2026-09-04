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


def test_render_embeds_logos_as_svg_data_uris(tmp_path):
    vis = tmp_path / "vis.js"
    vis.write_text("", encoding="utf-8")
    html = render.render(payload(), TEMPLATE, vis)
    assert html.count("data:image/svg+xml;base64,") == 2  # light + dark logo
    assert "data:image/png" not in html


def test_sidebar_logo_is_cropped_to_the_globe(tmp_path):
    # The 36px sidebar icon shows only the globe: the wordmark is illegible at
    # that size and the title text beside it already names the tool.
    import base64
    vis = tmp_path / "vis.js"
    vis.write_text("", encoding="utf-8")
    html = render.render(payload(), TEMPLATE, vis)
    blobs = re.findall(r"data:image/svg\+xml;base64,([A-Za-z0-9+/=]+)", html)
    assert len(blobs) == 2
    for blob in blobs:
        svg = base64.b64decode(blob).decode("utf-8")
        assert f'viewBox="{render.GLOBE_VIEWBOX}"' in svg
        assert 'viewBox="0 0 1254 1254"' not in svg
        assert "<metadata>" not in svg


def test_favicon_is_the_globe_and_follows_the_theme(tmp_path):
    vis = tmp_path / "vis.js"
    vis.write_text("", encoding="utf-8")
    html = render.render(payload(), TEMPLATE, vis)
    assert '<link id="favicon" rel="icon" type="image/svg+xml"' in html
    # Swapped with the sidebar logo, so it is set from the same constants.
    assert "getElementById('favicon').href = t === 'light' ? LOGO_LIGHT : LOGO_DARK" in html


def test_logo_svgs_have_no_provenance_blob_or_background():
    for theme in ("light", "dark"):
        svg = (TEMPLATE.parent / f"logo-{theme}.svg").read_text(encoding="utf-8")
        assert "<metadata>" not in svg and "c2pa" not in svg
        assert 'width="1254" height="1254"' not in svg   # no full-bleed square
        assert 'viewBox="0 0 1254 1254"' in svg


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


def test_render_embeds_group_threshold(tmp_path):
    vis = tmp_path / "vis.js"
    vis.write_text("", encoding="utf-8")
    p = payload()
    p["groupThreshold"] = 42
    html = render.render(p, TEMPLATE, vis)
    assert '"groupThreshold": 42' in html
