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


def test_detail_panel_escapes_payload_fields():
    # Final-review MUST-FIX 1: n.summary, edge notes, n.repo, and otherId (in
    # data-id attributes) must all be run through esc() in showNode()/row(),
    # matching buildListView's existing escapeHtml discipline.
    html = _render()
    assert "esc(n.summary)" in html
    assert "esc(note)" in html
    assert "esc(n.repo)" in html
    assert 'esc(otherId)' in html


def test_safe_url_helper_present_and_used():
    # Final-review MUST-FIX 1: a safeUrl(u) helper that only ever returns a
    # http(s) URL verbatim (else "#"), applied to every href built from a
    # payload URL in both showNode and buildListView.
    html = _render()
    assert "function safeUrl(u)" in html
    assert "^https?:\\/\\/" in html
    # showNode's story/PR hrefs go through safeUrl (and are attribute-escaped).
    assert "esc(safeUrl(s.url))" in html
    assert "esc(safeUrl(p.url))" in html
    # buildListView's links() helper also goes through safeUrl.
    assert "escapeHtml(safeUrl(x.url))" in html


def test_unknown_node_type_falls_back_to_neutral_badge():
    # STRONGLY RECOMMENDED 7: TS[n.type] may be undefined for a node type not
    # present in the payload's typeStyle map -- showNode must not throw.
    html = _render()
    assert 'TS[n.type] || { label: n.type, color: \'#8a949e\' }' in html
