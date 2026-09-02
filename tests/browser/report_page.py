"""Page object for the rendered ChangeAtlas report.

Wraps a Playwright ``Page`` so tests read as user actions ("collapse the
panel", "export a PNG") rather than selector plumbing. All selectors come
from ``selectors.py``.
"""
import base64
from pathlib import Path

from playwright.sync_api import Browser, Page

from . import selectors as S

# Reads the pixel at (0,0) of an image given as a data URL -> [r, g, b, a].
_PIXEL_AT_ORIGIN = """
href => new Promise(done => {
  const img = new Image();
  img.onload = () => {
    const c = document.createElement('canvas');
    c.width = img.width; c.height = img.height;
    const ctx = c.getContext('2d');
    ctx.drawImage(img, 0, 0);
    done(Array.from(ctx.getImageData(0, 0, 1, 1).data));
  };
  img.src = href;
})
"""


class ReportPage:
    def __init__(self, page: Page):
        self.page = page

    @classmethod
    def open(cls, browser: Browser, url: str, viewport=(1400, 900)) -> "ReportPage":
        """Open the report in a fresh context (so localStorage starts empty)."""
        ctx = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]})
        page = ctx.new_page()
        page.goto(url)
        page.wait_for_selector(S.GRAPH_CANVAS)
        return cls(page)

    def close(self):
        self.page.context.close()

    def _width_of(self, selector: str) -> float:
        return self.page.evaluate(
            "s => document.querySelector(s).getBoundingClientRect().width", selector)

    # ---- side panel ----

    def toggle_side_panel(self):
        self.page.click(S.SIDE_TOGGLE)

    def side_panel_width(self) -> float:
        return self._width_of(S.SIDE_PANEL)

    def side_panel_expanded(self) -> bool:
        return self.page.locator(S.SIDE_TOGGLE).get_attribute("aria-expanded") == "true"

    # ---- graph ----

    def canvas_width(self) -> float:
        return self._width_of(S.GRAPH_CANVAS)

    def canvas_pixel_size(self) -> list:
        return self.page.evaluate(
            "s => { const c = document.querySelector(s); return [c.width, c.height]; }",
            S.GRAPH_CANVAS)

    def theme_background(self) -> str:
        return self.page.evaluate("PALETTE.bg")

    # ---- export ----

    def export_png(self) -> tuple:
        """Click Export PNG; return (suggested filename, PNG bytes)."""
        with self.page.expect_download() as dl:
            self.page.click(S.EXPORT_PNG)
        download = dl.value
        return download.suggested_filename, Path(download.path()).read_bytes()

    def pixel_at_origin(self, png_bytes: bytes) -> tuple:
        """Decode a PNG in the browser and return its (0,0) pixel as (r, g, b, a)."""
        data_url = "data:image/png;base64," + base64.b64encode(png_bytes).decode()
        return tuple(self.page.evaluate(_PIXEL_AT_ORIGIN, data_url))
