"""Browser-driven checks for behaviour that only a real canvas can prove.

Most template behaviour is covered by string checks in test_template_a11y.py;
browser tests are the exception, reserved for things vis-network does at
runtime that static checks can't see. Currently two:

  * collapsing the side panel really resizes the graph canvas (vis-network
    only listens for *window* resize, so a missed setSize/redraw leaves a
    stale canvas that no static test would catch), and
  * Export PNG really produces an opaque, canvas-sized image.

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
from playwright.sync_api import Error as PlaywrightError, sync_playwright  # noqa: E402

from changeatlas.__main__ import main                                     # noqa: E402
from tests.browser.report_page import ReportPage                          # noqa: E402

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
        (base / "sample" / f.name).write_bytes(f.read_bytes())
    assert main(["--sample", "--base-dir", str(base)]) == 0
    return (base / "out" / "impact-sample.html").resolve().as_uri()


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
