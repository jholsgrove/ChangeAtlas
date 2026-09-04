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
                 'id="list-view"', 'role="group" aria-label="View"', 'id="lens-row"'):
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


# ---- collapsible side panel ----

def test_side_toggle_button_present_with_aria_wiring():
    html = _render()
    assert '<aside class="side" id="side"' in html
    assert 'id="side-toggle"' in html
    toggle = html[html.index('id="side-toggle"'):]
    toggle = toggle[:toggle.index(">")]
    assert 'aria-expanded="true"' in toggle
    assert 'aria-controls="side"' in toggle
    assert 'aria-label="Collapse panel"' in toggle

def test_side_collapsed_state_persisted_like_theme():
    html = _render()
    assert "SIDE_KEY = 'changeatlas-side'" in html
    assert "localStorage.setItem(SIDE_KEY" in html
    assert "localStorage.getItem(SIDE_KEY" in html

def test_side_toggle_resizes_graph_canvas():
    # vis-network only listens for *window* resize; a container-width change
    # must be pushed through explicitly or the canvas keeps its old size.
    html = _render()
    assert "network.setSize('100%', '100%')" in html
    assert "network.redraw()" in html

def test_collapsed_view_buttons_keep_full_label_in_dom():
    # Collapsed rail shows an abbreviation via CSS, but the real label stays
    # in the DOM (screen readers) - never swapped to a bare single letter.
    html = _render()
    for full, abbr in (("Impact", "I"), ("System", "S"), ("List", "L")):
        assert f'data-abbr="{abbr}"' in html
        assert f">{full}</button>" in html
    assert "attr(data-abbr)" in html


# ---- export PNG ----

def test_export_png_button_present():
    html = _render()
    assert 'id="export-png"' in html
    assert ">Export PNG<" in html

def test_export_png_paints_theme_background_before_graph():
    # The vis canvas is transparent; a bare toDataURL gives a see-through PNG.
    html = _render()
    fn = html[html.index("function exportPng"):]
    fn = fn[:fn.index("\n}\n")]
    assert "fillStyle = PALETTE.bg" in fn
    assert fn.index("fillRect") < fn.index("drawImage")
    assert "toDataURL('image/png')" in fn
    assert "a.download = 'impact-'" in fn

def test_export_png_disabled_in_list_view():
    html = _render()
    setview = html[html.index("function setView"):]
    setview = setview[:setview.index("\n}\n")]
    assert "getElementById('export-png').disabled = v === 'list'" in setview


def test_large_graph_perf_settings_are_threshold_gated():
    html = _render()
    assert "const LARGE = DATA.nodes.length > GROUP_THRESHOLD" in html
    assert "improvedLayout: !LARGE" in html
    assert "hideEdgesOnDrag: LARGE" in html and "hideEdgesOnZoom: LARGE" in html
    # physics is frozen after stabilisation only on large graphs
    assert "if (LARGE) network.setOptions({ physics: { enabled: false } })" in html


def test_layout_overlay_is_a_status_region():
    html = _render()
    assert 'id="layout-overlay"' in html
    assert 'role="status"' in html
    assert "<progress" in html


def test_lens_row_scaffolding_present():
    html = _render()
    assert 'id="lens-row"' in html
    assert 'class="views lenses" id="lens-row" role="group"' in html
    # both labels exist so a screen reader hears which set it is
    assert "'Impact lens'" in html and "'System lens'" in html
    # real buttons with pressed state, like the view row
    assert "b.setAttribute('aria-pressed', String(lens[currentView] === name))" in html
    # out of the DOM flow (and tab order) in List view and the collapsed rail
    assert "lensRow.hidden = !set" in html
    assert ".side.collapsed .lenses,.side.collapsed #lens-caption{display:none}" in html


def test_lens_table_has_exactly_the_five_lenses():
    html = _render()
    for row in (
        "release: { label: 'Release only', hide: true,  rule: 'evidence',",
        "context: { label: 'In context',   hide: false, rule: 'evidence',",
        "whole:   { label: 'Whole map',    hide: false, rule: 'none',",
        "repos:      { label: 'Repos',      hide: false, rule: 'all',",
        "components: { label: 'Components', hide: false, rule: 'none',",
    ):
        assert row in html
    assert html.count("hide: ") == 5


def test_lens_defaults_by_size_and_nothing_remembered():
    html = _render()
    assert "impact: LARGE ? 'context' : 'whole'" in html
    assert "system: LARGE ? 'repos' : 'components'" in html
    assert "changeatlas-group:" not in html


def test_old_toggles_are_gone():
    html = _render()
    for old in ('id="group-toggle"', 'id="hide-untouched"', 'id="collapse-untouched"',
                'id="expand-all"', 'id="group-tools"'):
        assert old not in html


def test_apply_lens_is_a_clean_reapply():
    html = _render()
    i = html.index("function applyLens(name)")
    body = html[i:i + 900]
    assert "hideUntouched = L.hide;" in body
    assert "applyGrouping();" in body            # discards manual opens, collapses per rule
    assert "buildLegend();" in body              # the Untouched entry is a toggle only on Whole map
    assert "settleCanvas('Showing ' + L.label);" in body


def test_settle_canvas_is_the_shared_tail():
    # Lens changes and the Untouched toggle both end the same way: ghosts out
    # of (or back into) physics, bubbles restyled, survivors packed when
    # hiding, then settle and frame what is left.
    html = _render()
    k = html.index("function settleCanvas(label)")
    tail = html[k:k + 700]
    for frag in ("applyGhostPhysics();", "restyleBubbles();", "if (hideUntouched) compactSurvivors();",
                 "fitVisibleWhenSettled();", "resettle(120, label + '…');"):
        assert frag in tail, frag


def test_lens_note_is_the_visible_live_region():
    # The canvas note is what sighted readers see AND what assistive tech
    # hears after a lens change: one sentence, one live region, no separate
    # visually-hidden announcer. It sits over the map (inside <main>) and is
    # drawn in full text colour on the panel surface, not faded.
    html = _render()
    assert 'id="lens-note" role="status" aria-live="polite"' in html
    assert 'id="lens-status"' not in html
    assert html.index("<main") < html.index('id="lens-note"') < html.index("</main>")
    assert "#lens-note{" in html
    css = html[html.index("#lens-note{"):html.index("}", html.index("#lens-note{"))]
    assert "color:var(--fg)" in css and "background:var(--panel)" in css
    assert "opacity" not in css


def test_lens_note_describes_what_the_lens_did():
    html = _render()
    assert "function describeLens()" in html
    assert "lensNote.textContent = describeLens()" in html
    for frag in ("' in this release shown, '", "' untouched hidden.'",
                 "' with nothing in this release collapsed into bubbles, '", "' inside.'",
                 "' untouched faded.'", "' as bubbles. Click one to open it.'",
                 "lensNote.textContent = describeLens();   // the note has no settle to wait for at bootstrap"):
        assert frag in html, frag


def test_view_buttons_have_tooltips():
    html = _render()
    for frag in (
        'id="view-impact" title="',
        'id="view-system" title="',
        'id="view-list" title="',
    ):
        assert frag in html, frag


def test_lens_caption_and_tooltips_come_from_the_lens_table():
    html = _render()
    assert html.count("desc: '") == 5
    assert 'class="hint" id="lens-caption"' in html
    assert "b.title = set[name].desc" in html
    assert "lensCaption.textContent = " in html
    # gone with the row in List view and the collapsed rail
    assert "lensCaption.hidden = !set" in html
    assert ".side.collapsed .lenses,.side.collapsed #lens-caption{display:none}" in html


def test_lens_row_and_status_live_outside_the_heading():
    # A heading takes its accessible name from its content; a live region or
    # a row of buttons inside <h1> would rename the page heading on every click.
    html = _render()
    h1_close = html.index("</h1>")
    assert html.index('id="lens-row"') > h1_close
    assert html.index('id="lens-caption"') > h1_close
    assert html.index('id="lens-row"') < html.index('id="search"')


def test_grouping_rule_comes_from_the_lens():
    html = _render()
    i = html.index("function applyGrouping()")
    body = html[i:i + 600]
    assert "const L = currentLens();" in body
    assert "if (L && L.rule !== 'none')" in body
    assert "if (L.rule === 'all' || !hasEvidence(k)) want.add(k);" in body


def test_hidden_bubbles_leave_physics_and_ghosts_are_reapplied_on_resettle():
    html = _render()
    i = html.index("function applyGhostPhysics()")
    assert "physics: !gone(n.id)" in html[i:i + 400]
    assert "physics: edgePhysics(e)" in html[i:i + 900]
    b = html[html.index("function bubbleStyle(key)"):html.index("function bubbleOpacity")]
    assert "hidden: hideUntouched && !tiered" in b
    assert "physics: !(hideUntouched && !tiered)" in b
    j = html.index("function resettle(iterations, message)")
    assert "if (hideUntouched) applyGhostPhysics();" in html[j:j + 200]


def test_reset_reapplies_the_current_lens_not_the_default():
    # Reset cleans up inside the lens the reader chose (selection, filters,
    # hand-opened bubbles, the Untouched refinement); it never changes lens.
    html = _render()
    i = html.index("document.getElementById('reset').onclick")
    body = html[i:i + 900]
    assert "filteredTiers.clear()" in body and "filteredTypes.clear()" in body
    assert "DEFAULT_LENS" not in body
    assert "if (currentView !== 'list') applyLens(lens[currentView]);" in body


def test_view_switch_applies_that_views_lens():
    html = _render()
    i = html.index("function setView(v)")
    body = html[i:i + 900]
    assert "buildLensRow();" in body
    assert "if (v !== 'list') applyLens(lens[v]);" in body


def test_roll_up_shows_in_every_impact_lens():
    html = _render()
    assert 'id="roll-wrap"' in html
    i = html.index("function buildRoll()")
    assert "document.getElementById('roll-wrap').hidden = currentView !== 'impact';" in html[i:i + 700]
    j = html.index("function setView(v)")
    assert "document.getElementById('roll-wrap').hidden = v !== 'impact';" in html[j:j + 900]


def test_grouping_uses_native_clustering_keyed_by_repo():
    html = _render()
    assert "network.cluster({" in html
    assert "joinCondition: o => o.repoKey === key" in html
    # Batched: neither call re-indexes the graph by itself (refreshData=false);
    # the caller re-indexes once per batch.
    assert "network.openCluster('cl:' + key, undefined, false)" in html
    assert "  }, false);\n  collapsed.add(key);" in html
    # externals and cross-repo messaging never collapse
    assert "n.repo !== 'external' && n.repo !== 'cross'" in html


def test_peripheral_bubbles_not_colour_alone():
    html = _render()
    assert "borderDashes: periph ? PALETTE.tiers.peripheral.borderDashes : false" in html
    assert "' peripheral · '" in html


def test_search_and_links_open_collapsed_repo_first():
    html = _render()
    assert "if (key && collapsed.has(key)) { expandRepo(key); resettle(60); }" in html


def test_roll_up_tables_present_and_accessible():
    html = _render()
    assert 'id="roll-body"' in html and 'id="roll-more"' in html
    assert 'id="list-repos"' in html and 'id="list-repos-body"' in html
    # both roll-up tables have a caption and column scopes like the component table
    assert html.count("<caption>") >= 3
    assert html.count('scope="col">Repo</th>') == 2


def test_roll_up_rows_only_for_impacted_repos_sorted_by_impact():
    html = _render()
    assert "r.c.changed + r.c.touched + r.c.testOnly + r.c.peripheral > 0" in html
    assert "(b.c.changed - a.c.changed) || (b.c.touched - a.c.touched)" in html


def test_roll_up_row_click_focuses_repo():
    html = _render()
    assert "tr.onclick = () => focusRepo(r.key)" in html
    # List view rows are plain (non-canvas equivalent), panel rows are clickable
    assert 'fillRollBody(document.getElementById("list-repos-body"), rollRows(), false)' in html


def test_untouched_legend_entry_is_a_toggle_only_on_whole_map():
    # Whole map is the one lens that shows untouched nodes flat, so it is the
    # one place the Untouched entry hides and shows them. On Release only they
    # are already gone; on In context hiding them would just be Release only.
    html = _render()
    assert "const untouchedToggleable = () => currentView === 'impact' && lens.impact === 'whole'" in html
    j = html.index("function buildLegend()")
    body = html[j:j + 900]
    assert "else if (untouchedToggleable()) legendChip(IMPACT[k].color, text, hideUntouched, toggleUntouched);" in body
    assert "else legendKey(IMPACT[k].color, text);" in body
    i = html.index("function legendKey(color, text)")
    assert "document.createElement('span')" in html[i:i + 300]
    assert "el.className = 'chip key'" in html[i:i + 300]
    assert ".chip.key{cursor:default;border-style:dashed;color:var(--muted)}" in html


def test_legend_is_first_built_after_the_lens_state_exists():
    # Regression: buildLegend() reads lens.impact via untouchedToggleable(); an
    # early call before `const lens` threw a TDZ ReferenceError and killed the page.
    html = _render()
    first_build = html.index("\nbuildLegend();")
    assert html.index("const lens = {") < first_build
    assert html.index("const untouchedToggleable") < first_build


def test_untouched_toggle_flips_hide_and_settles():
    html = _render()
    i = html.index("function toggleUntouched()")
    body = html[i:i + 300]
    assert "hideUntouched = !hideUntouched;" in body
    assert "buildLegend();" in body
    assert "settleCanvas(hideUntouched ? 'Untouched hidden' : 'Untouched shown');" in body


def test_untouched_fade_filter_is_gone():
    html = _render()
    assert "filteredTiers.has('dimmed')" not in html


def test_bubbles_follow_legend_filters():
    # Regression: legend pills only updated the node DataSet, so in grouped
    # mode the bubbles (the untouched mass, and the amber peripheral ones)
    # ignored Untouched/Peripheral filters and System-view type filters.
    html = _render()
    assert "c.peripheral > 0 && !filteredTiers.has('peripheral')" in html
    assert "filteredTypes.has('repo')" in html


def test_spotlight_includes_bubbles():
    html = _render()
    i = html.index("function spotlight(keep)")
    j = html.index("function clearSpotlight()")
    spot = html[i:j]
    assert "setBubble(key, { opacity: keep.has('cl:' + key) ? 1 : 0.12 })" in spot
    assert "setBubble(key, { opacity: bubbleOpacity(key) })" in html[j:j + 600]
