"""Golden end-to-end test: the bundled fictional web-shop sample exercises
every impact tier under the default 'generic' heuristics preset and default
changed-threshold (3), with zero ADO access (cached data only).

Designed tier truth for sample/release-1.0-data.json against
sample/graph-data.json + sample/component-globs.json:
  changed (1):    checkout-flow    — 3 prod files (>= threshold 3)
  touched (2):    pricing-engine   — 1 prod file
                  orders-db        — 1 schema (.sql) file counts as prod
                                      evidence for a database node
  test-only (1):  order-workflow   — only a test file matched
  peripheral (2): orders-api, web-api-client — non-repo neighbours of the
                  one changed node (checkout-flow) via the http and
                  project-ref edges
"""
import json
import re
from pathlib import Path

from changeatlas.__main__ import main

BASE = Path(__file__).resolve().parent.parent


def test_sample_end_to_end(capsys):
    rc = main(["--sample", "--base-dir", str(BASE)])
    assert rc == 0

    html = (BASE / "out" / "impact-sample.html").read_text(encoding="utf-8")
    out = capsys.readouterr().out

    # Tier counts: designed truth per the controller ruling (not the brief's
    # original "1 touched" snippet) — orders-db is a second touched node
    # because a single schema-evidence file counts as prod evidence for a
    # database node.
    assert re.search(r"1 changed", out)
    assert re.search(r"2 touched", out)
    assert re.search(r"1 test-only", out)
    # MUST-FIX 10: the peripheral count is also part of the designed tier
    # truth (orders-api, web-api-client) -- assert it, not just presence.
    assert re.search(r"2 peripheral", out)

    # All three tiered nodes reach the rendered payload.
    assert "checkout-flow" in html
    assert "pricing-engine" in html
    assert "orders-db" in html

    # MUST-FIX 10: a vacuous "orders-db" in html substring check would pass
    # even if orders-db were wired into the wrong tier (or just sitting in
    # the untouched node list). Parse the embedded DATA payload out of the
    # rendered HTML and confirm orders-db is actually in impact.touched.
    prefix = "const DATA = "
    start = html.index(prefix) + len(prefix)
    data, _ = json.JSONDecoder().raw_decode(html[start:])
    assert "orders-db" in data["impact"]["touched"]
    assert "checkout-flow" in data["impact"]["changed"]

    # Demo-safe, non-real tracker domain used throughout the sample data.
    assert "tracker.example" in html

    # The package-lock.json in PR 11 is a dependency-manifest skip.
    assert "1 dependency/NuGet manifest file(s) ignored" in out or "dependency" in out
