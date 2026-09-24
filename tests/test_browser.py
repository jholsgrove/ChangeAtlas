"""Browser-driven checks for behaviour that only a real canvas can prove.

Most template behaviour is covered by string checks in test_template_a11y.py;
browser tests are the exception, reserved for things vis-network does at
runtime that static checks can't see. Currently two:

  * collapsing the side panel really resizes the graph canvas (vis-network
    only listens for *window* resize, so a missed setSize/redraw leaves a
    stale canvas that no static test would catch),
  * Export PNG really produces an opaque, canvas-sized image, and
  * lenses on the 100-repo sample: the default lens per view, Release only
    hiding and packing, a re-click closing hand-opened bubbles, and the
    lens row leaving the tab order in List view,
  * the hover spotlight yields back to the selected node once the pointer
    leaves (hoverNode/blurNode are vis canvas events),
  * the lens caption and the canvas note say what the active lens did, with
    counts taken from the clustered/hidden state vis actually holds,
  * bubble work on the 100-repo sample is batched: a hover, a lens change or
    a legend chip re-indexes the graph a handful of times, not once per
    bubble (vis-network's `_dataChanged` is a full O(nodes+edges) rebuild),
  * the release slider on the 100-repo sample re-shades the map, re-applies
    the lens, and drops a selection the new stop folds into a bubble (tier
    sets, clustering and selection are all canvas state), and keeps the
    reader's zoom across the move,
  * a report opened on its own (no releases.js beside it) shows no slider
    and throws no uncaught error,
  * a manifest entry whose sidecar 404s is dropped from the slider's stops
    rather than wedging it.

They drive headless Chrome via Playwright, through the ``ReportPage`` page
object (``tests/browser/report_page.py``); selectors live in
``tests/browser/selectors.py``. They are OPTIONAL: they skip when Playwright
isn't installed or Chrome can't be launched, so `pip install pytest` alone
still gives a green suite. CI installs Playwright and uses the runner's
bundled Chrome, so nothing is downloaded there either.
"""
import shutil
import struct
from pathlib import Path

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import Error as PlaywrightError  # noqa: E402
from playwright.sync_api import sync_playwright

from changeatlas.__main__ import main  # noqa: E402
from tests.browser.report_page import ReportPage  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
# The installed Chrome (nothing to download); skip if it isn't there.
CHANNEL = "chrome"
COLLAPSED_RAIL_MAX_WIDTH = 60


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        try:
            b = p.chromium.launch(channel=CHANNEL, headless=True)
        except PlaywrightError:
            pytest.skip("no headless Chrome available")
        yield b
        b.close()


@pytest.fixture(scope="module")
def shop_series_dir(tmp_path_factory):
    """Render the shop sample once; the out/sample series directory it produced
    (report + sidecars + manifest), reused by report_url and the standalone-
    report regression tests below."""
    base = tmp_path_factory.mktemp("report")
    (base / "sample").mkdir()
    for f in (BASE / "sample").iterdir():
        if f.is_file():
            (base / "sample" / f.name).write_bytes(f.read_bytes())
    assert main(["--sample", "--base-dir", str(base)]) == 0
    return base / "out" / "sample"


@pytest.fixture(scope="module")
def report_url(shop_series_dir):
    return (shop_series_dir / "impact-1.0.html").resolve().as_uri()


@pytest.fixture(scope="module")
def large_report_url(tmp_path_factory):
    import shutil
    base = tmp_path_factory.mktemp("large")
    shutil.copytree(BASE / "sample", base / "sample")
    assert main(["--sample", "large", "--base-dir", str(base)]) == 0
    return (base / "out" / "sample-large" / "impact-1.0.html").resolve().as_uri()


@pytest.fixture
def large_report(browser, large_report_url):
    """The 100-repo report, loaded fresh and settled."""
    r = ReportPage.open(browser, large_report_url)
    r.wait_settled()
    yield r
    r.close()


@pytest.fixture
def report(browser, report_url):
    """A freshly loaded report with no remembered UI state."""
    r = ReportPage.open(browser, report_url)
    yield r
    r.close()


def _png_size(raw):
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", raw[16:24])


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


@pytest.fixture
def laptop_report(browser, report_url):
    """The report on a 1366x768 laptop screen, the commonest low-resolution size."""
    r = ReportPage.open(browser, report_url, viewport=(1366, 768))
    yield r
    r.close()


def test_selected_node_details_come_into_view_on_a_short_screen(laptop_report):
    # The panel's controls are ~700 px tall; below them the details used to be
    # squeezed to nothing and clipped, so a click looked like it did nothing.
    laptop_report.search_for(laptop_report.page.evaluate(
        "byId[DATA.impact.changed[0]].title"))
    laptop_report.page.wait_for_selector("#detail-close")
    assert laptop_report.top_of_in_view("#detail")


@pytest.mark.parametrize("size", [(1366, 768), (1280, 720), (1024, 768)])
def test_nothing_in_the_side_panel_is_out_of_reach_on_a_small_screen(browser, report_url, size):
    r = ReportPage.open(browser, report_url, viewport=size)
    try:
        for sel in ("#reset", "#export-obsidian", "#export-png", ".side footer a"):
            assert r.reachable(sel), sel
    finally:
        r.close()


def test_side_panel_narrows_on_a_narrow_screen(browser, report_url):
    r = ReportPage.open(browser, report_url, viewport=(1100, 800))
    try:
        assert r.side_panel_width() < 340
        # ...and the per-repo table still fits: long repo names wrap rather
        # than push the count columns off the panel's edge.
        r.page.evaluate("document.querySelector('#roll-body th, #roll-body td').textContent = 'Highlight.Authentication.Service.Host'")
        assert r.page.evaluate("(() => { const w = document.getElementById('roll-wrap'); return w.scrollWidth <= w.clientWidth; })()")
    finally:
        r.close()


def test_collapsing_side_panel_resizes_graph_canvas(report):
    side_before = report.side_panel_width()
    canvas_before = report.canvas_width()

    report.toggle_side_panel()
    assert report.side_panel_width() <= COLLAPSED_RAIL_MAX_WIDTH < side_before
    assert report.canvas_width() > canvas_before
    assert not report.side_panel_expanded()

    report.toggle_side_panel()
    assert report.side_panel_width() == side_before
    assert report.canvas_width() == canvas_before
    assert report.side_panel_expanded()


def test_export_png_downloads_opaque_image_of_the_canvas(report):
    name, raw = report.export_png()
    assert name == "impact-1.0.png"
    assert list(_png_size(raw)) == report.canvas_pixel_size()
    r, g, b, a = report.pixel_at_origin(raw)
    assert a == 255, "PNG background must be opaque, not transparent"
    assert (r, g, b) == _hex_to_rgb(report.theme_background())


def test_small_report_opens_on_whole_map(report):
    assert report.active_lens() == "Whole map"
    assert report.bubble_count() == 0


def test_large_report_opens_in_context_and_readable(large_report):
    total = large_report.total_node_count()
    assert total > 150
    assert large_report.active_lens() == "In context"
    bubbles = large_report.bubble_count()
    assert 80 <= bubbles <= 100, bubbles          # 100 repos, 6 with evidence stay open
    assert large_report.visible_node_count() < total / 4


def test_system_view_opens_on_repos_with_every_repo_a_bubble(large_report):
    large_report.switch_view("system")
    assert large_report.active_lens() == "Repos"
    assert large_report.bubble_count() == large_report.repo_count()
    large_report.choose_lens("Components")
    assert large_report.bubble_count() == 0


def test_each_view_remembers_its_own_lens(large_report):
    large_report.choose_lens("Release only")
    large_report.switch_view("system")
    assert large_report.active_lens() == "Repos"
    large_report.switch_view("impact")
    assert large_report.active_lens() == "Release only"


def test_clicking_a_bubble_opens_that_repo(large_report):
    before_nodes, before_bubbles = large_report.visible_node_count(), large_report.bubble_count()
    large_report.click_first_bubble()
    assert large_report.bubble_count() == before_bubbles - 1
    assert large_report.visible_node_count() > before_nodes


def test_reclicking_the_active_lens_closes_hand_opened_bubbles(large_report):
    before = large_report.bubble_count()
    large_report.click_first_bubble()
    assert large_report.bubble_count() == before - 1
    large_report.choose_lens("In context")
    assert large_report.bubble_count() == before


def test_release_only_hides_untouched_and_packs_the_survivors(large_report):
    total_nodes, before_bubbles = large_report.visible_node_count(), large_report.bubble_count()
    large_report.choose_lens("Release only")
    assert large_report.visible_node_count() < total_nodes
    # every bubble with nothing in the release goes; peripheral bubbles stay
    assert 0 < large_report.bubble_count() < before_bubbles / 4
    survivors = large_report.visible_ids()
    compact = large_report.bounds_area(survivors)
    large_report.choose_lens("In context")          # untouched back in: the map spreads out again
    assert large_report.bubble_count() == before_bubbles
    # Spreads back to about its opening footprint. (It used to more than double:
    # 1,400 nodes inside bubbles were re-entering physics and pushing the
    # bubbles apart, with half of them overlapping. Those stay frozen now.)
    # The layout is unseeded, so the ratio wanders: 0.51-0.68 over 16 local
    # loads, 0.75 once on CI. The regression this guards is a ratio under 0.5,
    # so 0.85 keeps a clear margin on both sides.
    assert compact < large_report.bounds_area(survivors) * 0.85


def test_opening_a_bubble_on_release_only_leaves_no_ghosts_in_physics(large_report):
    # vis turns physics back on for everything a cluster releases, which would
    # quietly re-introduce ghosts after any bubble opens while hiding.
    large_report.choose_lens("Release only")
    assert large_report.ghosts_in_physics() == 0
    large_report.click_first_bubble()
    assert large_report.ghosts_in_physics() == 0


def test_whole_map_shows_every_node(large_report):
    total = large_report.total_node_count()
    large_report.choose_lens("Whole map")
    assert large_report.bubble_count() == 0
    assert large_report.visible_node_count() == total


def test_lens_row_is_gone_in_list_view(large_report):
    assert large_report.lens_row_visible()
    large_report.switch_view("list")
    assert not large_report.lens_row_visible()
    assert large_report.lens_row_removed_from_flow()


def test_roll_up_table_is_gone_in_list_and_system_views(large_report):
    assert large_report.roll_up_visible()
    large_report.switch_view("list")
    assert not large_report.roll_up_visible()
    large_report.switch_view("system")
    assert not large_report.roll_up_visible()
    large_report.switch_view("impact")
    assert large_report.roll_up_visible()


def test_lens_note_reports_what_release_only_did(report):
    total, tiered = report.total_node_count(), report.tiered_node_count()
    report.choose_lens("Release only")
    assert report.lens_note() == (
        f"Release only. {tiered} components in this release shown, {total - tiered} untouched hidden.")
    assert report.lens_note_visible()


def test_lens_note_reports_whole_map_and_the_untouched_toggle(report):
    total, untouched = report.total_node_count(), report.untouched_count()
    assert report.lens_note() == f"Whole map. All {total} components, {untouched} untouched faded."
    report.toggle_legend_chip("Untouched")
    assert report.lens_note() == (
        f"Whole map. {total - untouched} components shown, {untouched} untouched hidden.")
    report.toggle_legend_chip("Untouched")
    assert report.lens_note() == f"Whole map. All {total} components, {untouched} untouched faded."


def test_lens_note_counts_the_bubbles_in_context(large_report):
    bubbles, inside = large_report.bubble_count(), large_report.bubble_member_count()
    assert large_report.lens_note() == (
        f"In context. {bubbles} repos with nothing in this release collapsed into bubbles, "
        f"{inside} components inside.")
    large_report.switch_view("system")
    assert large_report.lens_note() == (
        f"Repos. {large_report.repo_count()} repos as bubbles. Click one to open it.")


def test_lens_note_is_gone_in_list_view(report):
    assert report.lens_note_visible()
    report.switch_view("list")
    assert not report.lens_note_visible()


def test_lens_caption_follows_the_active_lens_and_matches_the_tooltips(report):
    assert report.lens_caption() == report.lens_tooltip("Whole map")
    whole = report.lens_caption()
    report.choose_lens("Release only")
    assert report.lens_caption() == report.lens_tooltip("Release only") != whole
    assert "hidden" in report.lens_caption()
    report.switch_view("list")
    assert not report.lens_caption_visible()


def test_whole_map_untouched_chip_hides_and_shows_untouched(report):
    # The small sample opens on Whole map, the one lens where the Untouched
    # entry is a toggle. Hiding removes the nodes (and packs the rest); the
    # lens indicator does not move.
    total, tiered = report.total_node_count(), report.tiered_node_count()
    assert report.legend_entry_is_button("Untouched")
    report.toggle_legend_chip("Untouched")
    assert report.visible_node_count() == tiered
    assert report.active_lens() == "Whole map"
    report.toggle_legend_chip("Untouched")
    assert report.visible_node_count() == total


def test_untouched_chip_is_a_key_outside_whole_map(large_report):
    assert large_report.active_lens() == "In context"
    assert not large_report.legend_entry_is_button("Untouched")
    large_report.choose_lens("Whole map")
    assert large_report.legend_entry_is_button("Untouched")
    large_report.choose_lens("Release only")
    assert not large_report.legend_entry_is_button("Untouched")


def test_peripheral_pill_turns_amber_bubbles_plain(large_report):
    assert large_report.amber_bubble_count() > 0
    large_report.toggle_legend_chip("Peripheral")
    assert large_report.amber_bubble_count() == 0
    large_report.toggle_legend_chip("Peripheral")
    assert large_report.amber_bubble_count() > 0


def test_hover_spotlight_yields_back_to_the_selected_node(report):
    # Click a node, hover a node it is not connected to, move away: the
    # selection must be lit again and the hovered node must recede.
    report.switch_view("system")
    a, b = report.unconnected_node_pair()
    report.click_node(a)
    assert report.selected_id() == a
    assert report.node_opacity(a) == 1
    report.hover_node(b)
    assert report.node_opacity(b) == 1          # hover spotlight while pointing
    report.move_mouse_off_nodes()
    assert report.node_opacity(a) == 1, "selected node went dark after hovering elsewhere"
    assert report.node_opacity(b) < 1, "hovered node stayed lit after the pointer left"


def test_reset_keeps_the_chosen_lens_and_closes_hand_opened_bubbles(report):
    # Small map: the System default is Components, so a Reset that fell back
    # to the default would silently leave the Repos lens the reader chose.
    report.switch_view("system")
    report.choose_lens("Repos")
    repos = report.repo_count()
    assert report.bubble_count() == repos
    report.click_first_bubble()
    assert report.bubble_count() == repos - 1
    report.reset_view()
    assert report.active_lens() == "Repos"
    assert report.bubble_count() == repos


def test_view_buttons_keep_their_tooltips_expanded_and_collapsed(report):
    # The collapsed rail rewrites these titles (one-letter buttons need the
    # name); the expanded panel must still explain what each view shows.
    expanded = {n: report.view_tooltip(n) for n in ("impact", "system", "list")}
    assert all(len(t) > 20 for t in expanded.values()), expanded
    report.toggle_side_panel()
    assert report.view_tooltip("impact").startswith("Impact")
    assert expanded["impact"] in report.view_tooltip("impact")
    report.toggle_side_panel()
    assert report.view_tooltip("impact") == expanded["impact"]


# A "rebuild" is one vis-network `_dataChanged`: ~20 ms on the 100-repo sample.
# Before batching, every bubble cost one per action (94 bubbles => ~1.9 s).
MAX_REBUILDS_PER_ACTION = 8
MAX_BLOCKED_MS = 500
# A lens change also re-clusters 94 repos and re-lays the map out: ~250 ms on
# a laptop, up to ~800 ms on shared CI runners (5.8 s before batching).
MAX_BLOCKED_MS_RELAYOUT = 2000


def test_hovering_on_the_large_map_does_not_rebuild_once_per_bubble(large_report):
    a, b = large_report.unconnected_node_pair()
    assert large_report.bubble_count() > MAX_REBUILDS_PER_ACTION
    large_report.start_measuring()
    large_report.hover_node(a)
    large_report.move_mouse_off_nodes()
    m = large_report.stop_measuring()
    assert m["rebuilds"] <= MAX_REBUILDS_PER_ACTION, m
    assert m["blockedMs"] < MAX_BLOCKED_MS, m


def test_lens_change_on_the_large_map_reclusters_in_a_few_rebuilds(large_report):
    large_report.choose_lens("Whole map")
    large_report.start_measuring()
    large_report.choose_lens("In context")     # 94 repos collapse again
    m = large_report.stop_measuring()
    assert large_report.bubble_count() > MAX_REBUILDS_PER_ACTION
    assert m["rebuilds"] <= MAX_REBUILDS_PER_ACTION, m
    assert m["blockedMs"] < MAX_BLOCKED_MS_RELAYOUT, m


def test_legend_chip_on_the_large_map_restyles_bubbles_in_one_rebuild(large_report):
    assert large_report.bubble_count() > MAX_REBUILDS_PER_ACTION
    large_report.start_measuring()
    large_report.toggle_legend_chip("Peripheral")
    m = large_report.stop_measuring()
    assert large_report.amber_bubble_count() == 0      # the chip still does its job
    assert m["rebuilds"] <= MAX_REBUILDS_PER_ACTION, m
    assert m["blockedMs"] < MAX_BLOCKED_MS, m


def test_lens_change_leaves_nodes_inside_bubbles_out_of_physics(large_report):
    # applyGhostPhysics re-enables physics on every unhidden node; the ones
    # inside a bubble must stay frozen or the settle simulates the whole map.
    assert large_report.children_in_physics() == 0
    large_report.choose_lens("Whole map")
    large_report.choose_lens("In context")
    assert large_report.children_in_physics() == 0
    large_report.choose_lens("Release only")
    assert large_report.children_in_physics() == 0


def test_opening_a_bubble_keeps_the_readers_zoom(large_report):
    # vis refits the whole map after every stabilize() unless told not to;
    # the resettle that follows a bubble opening must not throw the zoom away.
    large_report.zoom_to(2.5)
    assert large_report.scale() == 2.5
    large_report.click_first_bubble()
    assert large_report.scale() == pytest.approx(2.5), "zoom was reset when a bubble opened"


def test_opening_a_bubble_on_release_only_does_not_fade_the_release(large_report):
    # The bubble's repo node is untouched, so it is hidden on this lens: selecting
    # it would spotlight a node nobody can see and fade everything else to grey.
    large_report.choose_lens("Release only")
    large_report.click_first_bubble()
    assert large_report.spotlit_residue() == 0, "release nodes faded behind a hidden selection"
    assert large_report.selected_id() is None


def test_lens_change_drops_a_selection_it_hides(large_report):
    large_report.click_untouched_bubble()             # selects the repo node it opened
    assert large_report.selected_id() is not None
    large_report.choose_lens("Release only")          # that repo node is now hidden
    assert large_report.selected_id() is None
    assert large_report.spotlit_residue() == 0, "release nodes faded behind a hidden selection"


def test_release_slider_reshades_reapplies_the_lens_and_drops_a_hidden_selection(large_report):
    large_report.wait_slider()
    assert large_report.slider_visible()
    assert large_report.slider_stops() == ["1.0", "1.1", "1.2", "1.3", "1.4"]
    assert large_report.shown_release() == "1.0"           # fixture opens impact-1.0.html
    bubbles_at_1_0 = large_report.bubble_count()

    # A node changed at 1.4 sits inside a bubble at 1.0 (its repo has nothing in 1.0).
    target = large_report.node_changed_at_but_absent_now("1.4")
    assert target is not None

    # Zoom is kept across a slider move: setRelease re-applies the lens with
    # keepView so the whole-map refit is skipped (spec: "Zoom is kept").
    large_report.zoom_to(2.5)
    assert large_report.scale() == pytest.approx(2.5)

    large_report.slide_to("1.4")
    assert large_report.scale() == pytest.approx(2.5, abs=1e-6), "slider move discarded the reader's zoom"
    assert large_report.shown_release() == "1.4"
    assert "Release 1.4" in large_report.slider_caption()
    assert large_report.tier_of(target) == "changed"
    # In context re-applied: a different set of repos has evidence now.
    assert large_report.bubble_count() > 0
    assert "Showing release 1.4" in large_report.page.locator("#stats").inner_text()

    # Select that node, then scrub back: at 1.0 its repo collapses, so the
    # selection must go rather than spotlight a node nobody can see.
    large_report.page.evaluate("id => { network.selectNodes([id]); showNode(id); }", target)
    assert large_report.selected_id() == target
    large_report.slide_to("1.0")
    assert large_report.tier_of(target) == "dimmed"
    assert large_report.selected_id() is None
    assert large_report.spotlit_residue() == 0
    assert large_report.bubble_count() == bubbles_at_1_0


def test_lone_report_has_no_slider_and_no_errors(browser, shop_series_dir, tmp_path_factory):
    # The most common real-world path: a report emailed or copied on its own,
    # with no releases.js beside it. The <script src> 404s (a network error,
    # not a JS exception); the slider must stay hidden and nothing must throw.
    lone_dir = tmp_path_factory.mktemp("lone")
    shutil.copy(shop_series_dir / "impact-1.2.html", lone_dir / "impact-1.2.html")
    url = (lone_dir / "impact-1.2.html").resolve().as_uri()

    r = ReportPage.open(browser, url)
    try:
        assert not r.slider_visible()
        assert r.page.evaluate("STOPS.length") == 0
        assert r.page_errors() == []
    finally:
        r.close()


def test_missing_sidecar_is_dropped_from_the_stops(browser, shop_series_dir, tmp_path_factory):
    # A manifest entry whose sidecar file is missing (a stale or hand-edited
    # out/ folder) must be dropped from the slider's stops, not wedge init.
    series_dir = tmp_path_factory.mktemp("series")
    for f in shop_series_dir.iterdir():
        if f.is_file():
            shutil.copy(f, series_dir / f.name)
    (series_dir / "impact-1.1.history.js").unlink()
    url = (series_dir / "impact-1.2.html").resolve().as_uri()

    r = ReportPage.open(browser, url)
    try:
        r.wait_slider()
        assert r.slider_stops() == ["1.0", "1.2"]
        assert r.page_errors() == []
    finally:
        r.close()


# ---- History view: the fold across the series' stops ----

def test_history_view_appears_with_the_series_and_shades_by_frequency(report):
    # The shop series has three releases: two components changed in two of
    # them, seven in one (tests/test_sample_golden.py has the tier truth).
    report.wait_history()
    assert report.history_button_visible()
    assert report.history_stop_count() == 3
    assert report.freq_of("checkout-flow") == 2      # changed 1.0, touched 1.2
    assert report.freq_of("pricing-engine") == 2     # touched 1.0, changed 1.1
    assert report.freq_of("orders-api") == 1         # peripheral 1.0 does not count; changed 1.2
    assert report.freq_of("storefront-ui") == 0      # peripheral only

    report.switch_view("history")
    assert not report.slider_visible(), "History is the fold across the stops; no scrubber"
    assert report.active_lens() == "Whole map"       # small map: same default as Impact
    assert "Last 3 releases" in report.stats()
    assert "2 hot" in report.stats()
    # One hue, bucket = count; the border thickens with it (not colour alone).
    assert report.node_fill("checkout-flow") == report.history_fill(2)
    assert report.node_border_width("checkout-flow") == 2
    assert report.node_fill("orders-api") == report.history_fill(1)
    assert report.node_border_width("orders-api") == 1
    assert report.node_fill("storefront-ui") == report.dimmed_fill()
    chips = report.legend_texts()
    assert any(c.startswith("In 3 of 3 (0)") for c in chips)
    assert any(c.startswith("In 2 of 3 (2)") for c in chips)
    assert any(c.startswith("In 1 of 3 (7)") for c in chips)
    assert any(c.startswith("Never (") for c in chips)
    assert report.legend_entry_is_button("In 2 of 3")
    assert report.legend_entry_is_button("Never")     # a toggle on Whole map, like Untouched
    assert report.page_errors() == []


def test_history_hotspot_table_and_panel_rows(report):
    report.wait_history()
    report.switch_view("history")
    assert report.roll_up_visible()
    assert report.roll_caption() == "Hotspots across the last 3 releases"
    assert report.roll_titles(), "hotspot table has rows"
    # The panel lists every stop that changed the node, newest first, and
    # links to the sibling report for the stops that are not this one.
    report.select_node("checkout-flow")
    text = report.detail_text()
    assert "Changed in 2 of the last 3 releases" in text
    assert text.index("Release 1.2") < text.index("Release 1.0")
    links = report.detail_links()
    assert "impact-1.2.html" in links
    assert "impact-1.0.html" not in links             # the 1.0 row: this page is that report
    assert "Stories in this release" not in text     # per-release sections belong to Impact view


def test_history_hot_only_keeps_only_the_hot(report):
    report.wait_history()
    report.switch_view("history")
    report.choose_lens("Hot only")
    assert report.visible_node_count() == report.hot_node_count() == 2
    assert report.ghosts_in_physics() == 0
    assert "2 components hot in the last 3 releases shown" in report.lens_note()
    assert not report.legend_entry_is_button("Never"), "Hot only already hides the never-changed"
    report.choose_lens("Whole map")
    assert report.visible_node_count() == report.total_node_count()


def test_history_never_chip_hides_and_shows_the_never_changed_on_whole_map(report):
    # The analogue of Impact view's Untouched chip: a toggle on Whole map only,
    # and it hides just the never-changed, not the once-changed.
    report.wait_history()
    report.switch_view("history")
    assert report.active_lens() == "Whole map"
    assert report.legend_entry_is_button("Never")
    total, never = report.total_node_count(), report.page.evaluate("histSummary().never")
    report.toggle_legend_chip("Never")
    report.wait_settled()
    assert report.visible_node_count() == total - never == 9     # 2 hot + 7 once
    assert report.ghosts_in_physics() == 0
    assert f"{never} never changed hidden" in report.lens_note()
    report.toggle_legend_chip("Never")
    report.wait_settled()
    assert report.visible_node_count() == total


def test_history_export_carries_change_history_and_a_hotspots_note(report):
    import io
    import zipfile
    report.wait_history()
    report.switch_view("history")
    name, raw = report.export_obsidian()
    assert name == "impact-1.0-vault.zip"
    z = zipfile.ZipFile(io.BytesIO(raw))
    names = z.namelist()
    assert "Hotspots (last 3 releases).md" in names
    hotspots = z.read("Hotspots (last 3 releases).md").decode("utf-8")
    assert "| Repo | Hot | Once | Peak |" in hotspots
    assert "### Changed in 2 of 3" in hotspots
    checkout = next(n for n in names if n.startswith("Components/") and "heckout" in n)
    note = z.read(checkout).decode("utf-8")
    assert "changed-in: 2 of 3" in note
    assert "## Change history" in note
    assert "- Release 1.2: Touched" in note


def test_lone_report_has_no_history_button(browser, shop_series_dir, tmp_path_factory):
    lone_dir = tmp_path_factory.mktemp("lone-history")
    shutil.copy(shop_series_dir / "impact-1.2.html", lone_dir / "impact-1.2.html")
    r = ReportPage.open(browser, (lone_dir / "impact-1.2.html").resolve().as_uri())
    try:
        assert not r.history_button_visible()
        assert r.page.evaluate("HISTORY") is None
        assert r.page_errors() == []
    finally:
        r.close()


def test_large_history_opens_in_context_and_hot_only_leaves_no_ghosts(large_report):
    large_report.wait_history()
    assert large_report.history_stop_count() == 5
    large_report.switch_view("history")
    assert large_report.active_lens() == "In context"
    assert large_report.bubble_count() > 0
    assert "with no hot component collapsed into bubbles" in large_report.lens_note()
    hot = large_report.hot_node_count()
    assert hot > 0
    large_report.choose_lens("Hot only")
    assert large_report.visible_node_count() == hot
    assert large_report.ghosts_in_physics() == 0
    assert large_report.children_in_physics() == 0
    assert large_report.page_errors() == []
