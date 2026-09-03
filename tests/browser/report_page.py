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

    # ---- lenses ----

    def wait_settled(self):
        """Wait for the large-graph layout overlay to clear (no-op on small graphs)."""
        self.page.wait_for_function(
            "s => document.querySelector(s).hidden", arg=S.LAYOUT_OVERLAY, timeout=60_000)

    def switch_view(self, name: str):
        """Click the Impact / System / List view button and wait for the layout."""
        self.page.click(S.VIEW_BUTTON.format(name=name))
        self.wait_settled()

    def choose_lens(self, label: str):
        """Click a lens by its visible label (e.g. 'Release only') and wait for the layout."""
        self.page.locator(S.LENS_BUTTON, has_text=label).first.click()
        self.wait_settled()

    def active_lens(self) -> str:
        return self.page.locator(S.LENS_BUTTON + '[aria-pressed="true"]').first.inner_text()

    def lens_row_visible(self) -> bool:
        return self.page.locator(S.LENS_ROW).is_visible()

    def lens_row_removed_from_flow(self) -> bool:
        """The row carries the `hidden` attribute (out of the DOM flow and tab order), not just display:none."""
        return self.page.evaluate("s => document.querySelector(s).hidden", S.LENS_ROW)

    def lens_status(self) -> str:
        return self.page.locator("#lens-status").inner_text()

    def repo_count(self) -> int:
        return self.page.evaluate("Object.keys(membersOf).length")

    def amber_bubble_count(self) -> int:
        """Bubbles drawn with the peripheral tier's thicker dashed ring."""
        return self.page.evaluate(
            "network.body.nodeIndices.filter(id => network.isCluster(id)"
            " && network.body.nodes[id].options.borderWidth === 2).length")

    def total_node_count(self) -> int:
        return self.page.evaluate("DATA.nodes.length")

    def visible_node_count(self) -> int:
        """Nodes vis is actually drawing: not inside a bubble, not hidden."""
        return self.page.evaluate(
            "network.body.nodeIndices.filter(id => !network.body.nodes[id].options.hidden).length")

    def bubble_count(self) -> int:
        return self.page.evaluate(
            "network.body.nodeIndices.filter(id => network.isCluster(id)).length")

    def visible_bubble_count(self) -> int:
        return self.page.evaluate(
            "network.body.nodeIndices.filter(id => network.isCluster(id)"
            " && !network.body.nodes[id].options.hidden).length")

    def click_first_bubble(self):
        x, y = self.page.evaluate("""() => {
          const id = network.body.nodeIndices.find(i => network.isCluster(i) && !network.body.nodes[i].options.hidden);
          const d = network.canvasToDOM(network.getPositions([id])[id]);
          const r = document.querySelector('#graph canvas').getBoundingClientRect();
          return [r.left + d.x, r.top + d.y];
        }""")
        self.page.mouse.click(x, y)
        self.wait_settled()

    def toggle_legend_chip(self, label: str):
        self.page.locator("#legend .chip", has_text=label).first.click()

    def bubble_opacities(self) -> list:
        return self.page.evaluate(
            "network.body.nodeIndices.filter(id => network.isCluster(id))"
            ".map(id => network.body.nodes[id].options.opacity)")

    def visible_ids(self) -> list:
        """Ids of everything vis is drawing at top level: nodes and bubbles, not hidden."""
        return self.page.evaluate(
            "network.body.nodeIndices.filter(id => !network.body.nodes[id].options.hidden)")

    def bounds_area(self, ids: list) -> float:
        """Area (canvas units²) of the bounding box round the given node/bubble ids."""
        return self.page.evaluate("""ids => {
          const pos = network.getPositions(ids);
          const xs = ids.map(i => pos[i].x), ys = ids.map(i => pos[i].y);
          return (Math.max(...xs) - Math.min(...xs)) * (Math.max(...ys) - Math.min(...ys));
        }""", ids)

    def ghosts_in_physics(self) -> int:
        """Hidden nodes/bubbles still in the simulation, plus live springs to them."""
        return self.page.evaluate("""() => {
          const hidden = id => network.body.nodes[id].options.hidden;
          const ghostNodes = network.body.nodeIndices.filter(id => hidden(id) && network.body.nodes[id].options.physics);
          const ghostEdges = Object.values(network.body.edges).filter(e => e.options.physics && e.connected
            && network.body.nodes[e.fromId] && network.body.nodes[e.toId] && (hidden(e.fromId) || hidden(e.toId)));
          return ghostNodes.length + ghostEdges.length;
        }""")
