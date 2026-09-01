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

def test_main_landmark_contains_page_content():
    # Axe: "document should have one main landmark" and "all page content
    # should be contained by landmarks". The graph and its list-view
    # equivalent are the primary content (<main>); the sidebar is <aside>.
    html = _render()
    assert "<main" in html
    main_open = html.index("<main")
    main_close = html.index("</main>")
    assert main_open < html.index('id="graph"') < main_close
    assert main_open < html.index('id="list-view"') < main_close
    assert not (main_open < html.index("<aside") < main_close)


def test_view_control_scaffolding_present():
    html = _render()
    for frag in ('id="view-impact"', 'id="view-system"', 'id="view-list"',
                 'id="list-view"', 'role="group" aria-label="View"'):
        assert frag in html

def test_system_view_wiring_present():
    html = _render()
    assert "systemNodeVisual" in html and "impactNodeVisual" in html
    assert "setView('system')" in html or 'setView("system")' in html
    # System view derives node colours from the payload's typeStyle map.
    assert "TS[n.type]" in html

def test_tier_labels_in_legend():
    html = _render()
    for label in ("Changed", "Touched", "Test-only", "Peripheral"):
        assert label in html

def test_borderdashes_used_by_canvas():
    assert "borderDashes" in _render()

def test_shape_properties_never_explicit_undefined():
    # Regression: an explicit `shapeProperties: undefined` on dimmed nodes
    # clobbers vis-network's default options object and crashes node
    # rendering (blank map, edges only). Every node must pass a real object.
    html = _render()
    assert "shapeProperties: { borderDashes: tier ? tier.borderDashes : false }" in html
    assert "shapeProperties: tier ?" not in html

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


def test_theme_toggle_scaffolding_present():
    html = _render()
    assert 'id="theme-toggle"' in html
    assert 'aria-pressed' in html
    # Default theme follows the OS; explicit choice persists per viewer.
    assert "prefers-color-scheme" in html
    assert "localStorage" in html


def test_theme_recolours_graph_from_palette():
    html = _render()
    # The template must read chrome colours from the active theme palette,
    # not hard-code them (they differ per theme and are WCAG-gated in
    # tests/test_palette.py).
    assert "PALETTES" in html
    for frag in ("dimmed", "edge_affected", "edge_dim", "edge_system",
                 "badge_text", "type_colors"):
        assert frag in html, frag


def test_logo_present_and_decorative():
    html = _render()
    assert 'id="logo"' in html
    assert 'alt=""' in html   # decorative: the title text names the tool


def test_footer_github_link():
    html = _render()
    assert "<footer" in html
    assert 'href="https://github.com/jholsgrove/ChangeAtlas"' in html
    assert 'rel="noopener"' in html


def test_legend_chips_are_toggleable_buttons():
    html = _render()
    # Chips are real <button>s with a visible + accessible pressed state.
    assert "document.createElement('button')" in html
    assert "chip.setAttribute('aria-pressed'" in html
    assert "chip.classList.add('off')" in html


def test_legend_filters_dim_rather_than_hide():
    html = _render()
    # Toggling a pill sends that tier/type to the dimmed treatment — nodes are
    # never removed from the graph.
    assert "filteredTiers" in html and "filteredTypes" in html
    # Impact node fills key off the filtered ("effective") state...
    assert "PALETTE.tiers[effectiveState(n.id)]" in html
    # ...and edges into a filtered node drop to the dim colour too.
    assert "effectiveState(id) !== 'dimmed'" in html


def test_reset_clears_legend_filters():
    html = _render()
    assert "filteredTiers.clear()" in html
    assert "filteredTypes.clear()" in html


def test_filtered_untouched_fades_further():
    # The Untouched tier is already dimmed, so filtering it drops those nodes
    # to the spotlight background opacity instead (decluttering).
    html = _render()
    assert "filteredTiers.has('dimmed') ? 0.12 : 0.35" in html


def test_system_view_filters_types():
    html = _render()
    # System-view pills dim their node type in place...
    assert "filteredTypes.has(n.type) ? PALETTE.dimmed : typeColor(n.type)" in html
    # ...and edges touching a filtered type drop to the dim colour.
    assert "!filteredTypes.has(byId[e.from].type) && !filteredTypes.has(byId[e.to].type)" in html


def test_filter_toggle_preserves_selection_spotlight():
    html = _render()
    assert "if (selected) spotlight(neighbours(selected))" in html


def test_unknown_node_type_falls_back_to_neutral_badge():
    # STRONGLY RECOMMENDED 7: TS[n.type] may be undefined for a node type not
    # present in the payload's typeStyle map -- showNode must not throw.
    html = _render()
    assert 'TS[n.type] || { label: n.type, color: \'#8a949e\' }' in html
