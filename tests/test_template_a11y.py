from pathlib import Path
from changeatlas import render

PKG = Path(__file__).resolve().parent.parent / "changeatlas"
VIS = Path(__file__).resolve().parent.parent / "vendor" / "vis-network.min.js"

def _render():
    payload = {"release": "1.0", "generated": "2026-08-31",
               "nodes": [{"id": "a", "title": "A", "type": "service", "repo": "r", "summary": "s", "tags": []}],
               "edges": [], "typeStyle": {}, "edgeLabel": {},
               "impact": {"changed": ["a"], "touched": [], "testOnly": [], "peripheral": []},
               "details": {"a": {"stories": [], "prs": [], "prodFiles": 3, "testFiles": 0}}}
    return render.render(payload, PKG / "template.html", VIS)

def test_lang_attribute():
    assert 'lang="en"' in _render()

def test_list_view_scaffolding_present():
    html = _render()
    assert 'id="view-toggle"' in html and 'id="list-view"' in html

def test_tier_labels_in_legend():
    html = _render()
    for label in ("Changed", "Touched", "Test-only", "Peripheral"):
        assert label in html

def test_borderdashes_used_by_canvas():
    assert "borderDashes" in _render()
