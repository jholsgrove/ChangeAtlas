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

def test_build_list_view_guards_missing_tier_keys():
    # Regression for fix round 1: buildListView() iterates all four tier keys
    # ("changed", "touched", "testOnly", "peripheral"), but a payload may
    # legally omit touched/testOnly -- see the sibling `DATA.impact.touched
    # || []` guard a few lines above buildListView() in template.html, and
    # the impact fixture in tests/test_render.py which only sets
    # changed/peripheral. Without a matching guard inside buildListView,
    # `for (const id of DATA.impact[key])` throws TypeError: not iterable
    # the first time List view opens on such a payload.
    #
    # We cannot execute the template's JS here (no browser), so the actual
    # gate is the string-level assertion below: the guarded expression must
    # be present verbatim in the shipped source, not the unguarded
    # `DATA.impact[key]`.
    html = _render()
    assert "DATA.impact[key] || []" in html

    # Kept honest: rendering a payload missing touched/testOnly already
    # succeeds at the Python/render.py level regardless of the JS guard --
    # render.render() only does string/JSON substitution, it never executes
    # the template's JS. This half is not the regression gate; it just
    # documents that render.render() itself has no opinion on the shape of
    # `impact` and won't mask the JS-side bug by raising first.
    payload = {"release": "1.0", "generated": "2026-08-31",
               "nodes": [{"id": "a", "title": "A", "type": "service", "repo": "r", "summary": "s", "tags": []}],
               "edges": [], "typeStyle": {}, "edgeLabel": {},
               "impact": {"changed": ["a"], "peripheral": []},  # touched/testOnly omitted
               "details": {"a": {"stories": [], "prs": [], "prodFiles": 3, "testFiles": 0}}}
    html2 = render.render(payload, PKG / "template.html", VIS)
    assert "DATA.impact[key] || []" in html2
