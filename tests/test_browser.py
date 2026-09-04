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
    bubble (vis-network's `_dataChanged` is a full O(nodes+edges) rebuild).

They drive headless Chrome via Playwright, through the ``ReportPage`` page
object (``tests/browser/report_page.py``); selectors live in
``tests/browser/selectors.py``. They are OPTIONAL: they skip when Playwright
isn't installed or Chrome can't be launched, so `pip install pytest` alone
still gives a green suite. CI installs Playwright and uses the runner's
bundled Chrome, so nothing is downloaded there either.
"""
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
def report_url(tmp_path_factory):
    base = tmp_path_factory.mktemp("report")
    (base / "sample").mkdir()
    for f in (BASE / "sample").iterdir():
        if f.is_file():
            (base / "sample" / f.name).write_bytes(f.read_bytes())
    assert main(["--sample", "--base-dir", str(base)]) == 0
    return (base / "out" / "impact-sample.html").resolve().as_uri()


@pytest.fixture(scope="module")
def large_report_url(tmp_path_factory):
    import shutil
    base = tmp_path_factory.mktemp("large")
    shutil.copytree(BASE / "sample", base / "sample")
    assert main(["--sample", "large", "--base-dir", str(base)]) == 0
    return (base / "out" / "impact-sample-large.html").resolve().as_uri()


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
    assert compact < large_report.bounds_area(survivors) * 0.75


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
    assert m["blockedMs"] < MAX_BLOCKED_MS, m


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
