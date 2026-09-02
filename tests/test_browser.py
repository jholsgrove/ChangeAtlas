"""Browser-driven checks for behaviour that only a real canvas can prove.

Most template behaviour is covered by string checks in test_template_a11y.py;
browser tests are the exception, reserved for things vis-network does at
runtime that static checks can't see. Currently two:

  * collapsing the side panel really resizes the graph canvas (vis-network
    only listens for *window* resize, so a missed setSize/redraw leaves a
    stale canvas that no static test would catch),
  * Export PNG really produces an opaque, canvas-sized image, and
  * grouped mode on the 100-repo sample: bubbles exist, open on click, and
    Hide untouched / the grouping toggle change what vis actually draws.

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


def test_small_report_opens_flat(report):
    assert not report.grouping_on()
    assert report.bubble_count() == 0


def test_large_report_opens_grouped_and_readable(large_report):
    total = large_report.total_node_count()
    assert total > 150
    assert large_report.grouping_on()
    bubbles = large_report.bubble_count()
    assert 80 <= bubbles <= 100, bubbles          # 100 repos, 6 with evidence stay open
    assert large_report.visible_node_count() < total / 4


def test_clicking_a_bubble_opens_that_repo(large_report):
    before_nodes, before_bubbles = large_report.visible_node_count(), large_report.bubble_count()
    large_report.click_first_bubble()
    assert large_report.bubble_count() == before_bubbles - 1
    assert large_report.visible_node_count() > before_nodes


def test_hide_untouched_removes_nodes_and_plain_bubbles(large_report):
    before_nodes, before_bubbles = large_report.visible_node_count(), large_report.visible_bubble_count()
    large_report.toggle_hide_untouched()
    assert large_report.visible_node_count() < before_nodes
    # every bubble with nothing in the release goes; peripheral bubbles stay
    assert 0 < large_report.visible_bubble_count() < before_bubbles / 4
    large_report.toggle_hide_untouched()
    assert large_report.visible_bubble_count() == before_bubbles


def test_grouping_toggle_off_shows_every_node(large_report):
    total = large_report.total_node_count()
    large_report.toggle_grouping()
    assert not large_report.grouping_on()
    assert large_report.bubble_count() == 0
    assert large_report.visible_node_count() == total


def test_untouched_pill_fades_bubbles_in_grouped_mode(large_report):
    assert set(large_report.bubble_opacities()) == {1}
    large_report.toggle_legend_chip("Untouched")
    ops = large_report.bubble_opacities()
    # plain bubbles fade like filtered untouched nodes; peripheral bubbles stay lit
    assert ops.count(0.12) > ops.count(1) > 0
    large_report.toggle_legend_chip("Untouched")
    assert set(large_report.bubble_opacities()) == {1}
