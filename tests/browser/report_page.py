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

    def lens_note(self) -> str:
        """The status sentence pinned to the map after a lens change (also the live region)."""
        self.page.wait_for_function(
            "s => document.querySelector(s).textContent !== ''", arg=S.LENS_NOTE)
        return self.page.locator(S.LENS_NOTE).inner_text()

    def lens_note_visible(self) -> bool:
        return self.page.locator(S.LENS_NOTE).is_visible()

    def lens_caption(self) -> str:
        return self.page.locator(S.LENS_CAPTION).inner_text()

    def lens_caption_visible(self) -> bool:
        return self.page.locator(S.LENS_CAPTION).is_visible()

    def lens_tooltip(self, label: str) -> str:
        return self.page.locator(S.LENS_BUTTON, has_text=label).first.get_attribute("title") or ""

    def untouched_count(self) -> int:
        return self.page.evaluate("counts.dimmed")

    def bubble_member_count(self) -> int:
        """Components inside the bubbles currently on the canvas."""
        return self.page.evaluate(
            "[...collapsed].reduce((n, k) => n + (membersOf[k] || []).length, 0)")

    def roll_up_visible(self) -> bool:
        return self.page.locator(S.ROLL_WRAP).is_visible()

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
        return self.page.evaluate("network.body.nodeIndices.length")

    def bubble_count(self) -> int:
        return self.page.evaluate(
            "network.body.nodeIndices.filter(id => network.isCluster(id)).length")

    def zoom_to(self, scale: float):
        """Zoom the canvas (like the wheel), keeping the first bubble in view."""
        self.page.evaluate("""scale => {
          const id = network.body.nodeIndices.find(i => network.isCluster(i) && !network.body.nodes[i].options.hidden);
          network.moveTo({ scale, position: network.getPositions([id])[id] });
        }""", scale)

    def scale(self) -> float:
        return self.page.evaluate("network.getScale()")

    def click_first_bubble(self):
        x, y = self.page.evaluate("""() => {
          const id = network.body.nodeIndices.find(i => network.isCluster(i) && !network.body.nodes[i].options.hidden);
          const d = network.canvasToDOM(network.getPositions([id])[id]);
          const r = document.querySelector('#graph canvas').getBoundingClientRect();
          return [r.left + d.x, r.top + d.y];
        }""")
        self.page.mouse.click(x, y)
        self.wait_settled()

    # ---- selection and hover spotlight ----

    def _dom_point_of(self, node_id: str) -> tuple:
        return tuple(self.page.evaluate("""id => {
          const d = network.canvasToDOM(network.getPositions([id])[id]);
          const r = document.querySelector('#graph canvas').getBoundingClientRect();
          return [r.left + d.x, r.top + d.y];
        }""", node_id))

    def unconnected_node_pair(self) -> tuple:
        """Two visible nodes with no edge between them (so one's spotlight excludes the other)."""
        return tuple(self.page.evaluate("""() => {
          const ids = network.body.nodeIndices.filter(i => !network.isCluster(i));
          for (const a of ids) {
            const near = new Set(network.getConnectedNodes(a));
            const b = ids.find(o => o !== a && !near.has(o));
            if (b) return [a, b];
          }
          return null;
        }"""))

    def click_node(self, node_id: str):
        x, y = self._dom_point_of(node_id)
        self.page.mouse.click(x, y)

    def hover_node(self, node_id: str):
        # A dot on the settled 100-repo map is ~3 px across on screen, and vis
        # only hit-tests on a mousemove against the last drawn frame, so a
        # single move at that size misses now and then on a slow CI runner.
        # Centre the node at 1:1 or better, let a frame paint, approach in two
        # moves.
        self.page.evaluate("""id => {
          const pos = network.getPositions([id])[id];
          network.moveTo({ position: pos, scale: Math.max(network.getScale(), 1) });
        }""", node_id)
        self.page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
        x, y = self._dom_point_of(node_id)
        self.page.mouse.move(x + 40, y + 40)
        self.page.mouse.move(x, y)
        self.page.wait_for_function(
            "id => network.body.nodes[id].hover === true", arg=node_id)

    def move_mouse_off_nodes(self):
        """Move the pointer to an empty spot on the canvas, so vis fires blurNode."""
        x, y = self.page.evaluate("""() => {
          const r = document.querySelector('#graph canvas').getBoundingClientRect();
          const pts = network.body.nodeIndices.map(i => network.canvasToDOM(network.getPositions([i])[i]));
          for (let y = 10; y < r.height; y += 15) for (let x = 10; x < r.width; x += 15) {
            if (pts.every(p => Math.hypot(p.x - x, p.y - y) > 60)) return [r.left + x, r.top + y];
          }
          return [r.left + 5, r.top + 5];
        }""")
        self.page.mouse.move(x, y)
        self.page.wait_for_function(
            "() => Object.values(network.body.nodes).every(n => n.hover !== true)")

    def node_opacity(self, node_id: str) -> float:
        return self.page.evaluate("id => network.body.nodes[id].options.opacity", node_id)

    def spotlit_residue(self) -> int:
        """Drawn nodes and bubbles faded below their resting opacity (a spotlight with no visible owner)."""
        return self.page.evaluate("""() => network.body.nodeIndices.filter(id => {
          const rest = network.isCluster(id) ? bubbleOpacity(id.slice(3)) : baseOpacity(id);
          return network.body.nodes[id].options.opacity < rest;
        }).length""")

    def click_untouched_bubble(self):
        """Open a bubble whose repo has nothing at all in the release."""
        x, y = self.page.evaluate("""() => {
          const k = [...collapsed].find(k => { const c = repoSummary(k); return c.changed + c.touched + c.testOnly + c.peripheral === 0; });
          const d = network.canvasToDOM(network.getPositions(['cl:' + k])['cl:' + k]);
          const r = document.querySelector('#graph canvas').getBoundingClientRect();
          return [r.left + d.x, r.top + d.y];
        }""")
        self.page.mouse.click(x, y)
        self.wait_settled()

    def selected_id(self):
        return self.page.evaluate("selected")

    def view_tooltip(self, name: str) -> str:
        return self.page.locator(S.VIEW_BUTTON.format(name=name)).get_attribute("title") or ""

    def reset_view(self):
        self.page.click(S.RESET)
        self.wait_settled()

    def toggle_legend_chip(self, label: str):
        self.page.locator("#legend .chip", has_text=label).first.click()

    def legend_entry_is_button(self, label: str) -> bool:
        """A clickable chip is a <button>; a key is a <span>."""
        return self.page.locator("#legend .chip", has_text=label).first.evaluate(
            "el => el.tagName === 'BUTTON'")

    def tiered_node_count(self) -> int:
        """Nodes with any release tier (everything that is not untouched)."""
        return self.page.evaluate("DATA.nodes.filter(n => stateOf(n.id) !== 'dimmed').length")

    def visible_ids(self) -> list:
        """Ids of everything vis is drawing at top level: nodes and bubbles, not hidden."""
        return self.page.evaluate("network.body.nodeIndices")

    def bounds_area(self, ids: list) -> float:
        """Area (canvas units²) of the bounding box round the given node/bubble ids."""
        return self.page.evaluate("""ids => {
          const pos = network.getPositions(ids);
          const xs = ids.map(i => pos[i].x), ys = ids.map(i => pos[i].y);
          return (Math.max(...xs) - Math.min(...xs)) * (Math.max(...ys) - Math.min(...ys));
        }""", ids)

    def children_in_physics(self) -> int:
        """Nodes inside a bubble that vis is still simulating (they should all be frozen)."""
        return self.page.evaluate(
            "Object.values(network.body.nodes).filter(n => n.options.physics"
            " && network.clustering.clusteredNodes[n.id]).length")

    # ---- responsiveness ----

    def start_measuring(self):
        """Count full graph re-indexes and main-thread blocking until stop_measuring().

        vis-network rebuilds edge, cluster, physics and index state on every
        `_dataChanged`; one rebuild is ~20 ms on the 1,500-node sample, so an
        action that emits once per bubble blocks the page for seconds.
        """
        self.page.evaluate("""() => {
          const em = network.body.emitter, orig = em.emit;
          window.__perf = { rebuilds: 0, blockedMs: 0, orig };
          em.emit = function (name) {
            if (name === '_dataChanged') window.__perf.rebuilds++;
            return orig.apply(this, arguments);
          };
          window.__perf.obs = new PerformanceObserver(list =>
            list.getEntries().forEach(e => { window.__perf.blockedMs += e.duration; }));
          window.__perf.obs.observe({ type: 'longtask' });
        }""")

    def stop_measuring(self) -> dict:
        """{'rebuilds': int, 'blockedMs': float} since start_measuring()."""
        self.page.wait_for_timeout(150)   # long-task entries are delivered asynchronously
        return self.page.evaluate("""() => {
          const p = window.__perf;
          p.obs.takeRecords().forEach(e => { p.blockedMs += e.duration; });
          p.obs.disconnect();
          network.body.emitter.emit = p.orig;
          delete window.__perf;
          return { rebuilds: p.rebuilds, blockedMs: Math.round(p.blockedMs) };
        }""")

    def ghosts_in_physics(self) -> int:
        """Hidden nodes/bubbles still in the simulation, plus live springs to them."""
        return self.page.evaluate("""() => {
          const hidden = id => network.body.nodes[id].options.hidden;
          const ghostNodes = Object.values(network.body.nodes).filter(n => n.options.hidden && n.options.physics);
          const ghostEdges = Object.values(network.body.edges).filter(e => e.options.physics && e.connected
            && network.body.nodes[e.fromId] && network.body.nodes[e.toId] && (hidden(e.fromId) || hidden(e.toId)));
          return ghostNodes.length + ghostEdges.length;
        }""")
