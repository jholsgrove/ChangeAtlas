"""Golden end-to-end test: the bundled fictional web-shop sample exercises
every impact tier under the default 'generic' heuristics preset and default
changed-threshold (3), with zero ADO access (cached data only). The sample
has three releases so the report has a slider to show.

Designed tier truth against sample/graph-data.json + sample/component-globs.json:

1.0 (fetched 2026-08-31)
  changed (1):    checkout-flow    — 3 prod files (>= threshold 3)
  touched (2):    pricing-engine   — 1 prod file
                  orders-db        — 1 schema (.sql) file counts as prod
                                      evidence for a database node
  test-only (1):  order-workflow   — only a test file matched
  peripheral (2): orders-api, web-api-client — non-repo neighbours of the
                  one changed node (checkout-flow)

1.1 (fetched 2026-09-07)
  changed (2):    pricing-engine, catalog-api — 3 prod files each
  touched (1):    catalog-db       — one migration (.sql)
  test-only (0)
  peripheral:     PERIPHERAL_1_1 below (non-repo, non-database neighbours of
                  the two changed nodes)

1.2 (fetched 2026-09-14)
  changed (2):    orders-api, invoice-generator — 3 prod files each
  touched (1):    checkout-flow    — 1 prod file
  test-only (1):  search-index     — only a test file matched
  peripheral:     PERIPHERAL_1_2 below
"""
import json
import re
from pathlib import Path

from changeatlas.__main__ import main

BASE = Path(__file__).resolve().parent.parent
SERIES = BASE / "out" / "sample"

PERIPHERAL_1_1 = {"storefront-ui"}
PERIPHERAL_1_2 = {"email-provider", "order-events", "web-api-client"}


def _payload(label):
    html = (SERIES / f"impact-{label}.html").read_text(encoding="utf-8")
    prefix = "const DATA = "
    start = html.index(prefix) + len(prefix)
    data, _ = json.JSONDecoder().raw_decode(html[start:])
    return html, data


def test_sample_end_to_end(capsys):
    rc = main(["--sample", "--base-dir", str(BASE)])
    assert rc == 0
    out = capsys.readouterr().out
    # One summary block per release, oldest fetch first.
    assert out.index("impact-1.0.html") < out.index("impact-1.1.html") < out.index("impact-1.2.html")

    html, data = _payload("1.0")
    assert re.search(r"1 changed · 2 touched · 1 test-only · 2 peripheral", out)
    assert data["impact"]["changed"] == ["checkout-flow"]
    assert sorted(data["impact"]["touched"]) == ["orders-db", "pricing-engine"]
    assert data["impact"]["testOnly"] == ["order-workflow"]
    assert sorted(data["impact"]["peripheral"]) == ["orders-api", "web-api-client"]
    assert "tracker.example" in html
    assert data["history"] is True

    _, data = _payload("1.1")
    assert sorted(data["impact"]["changed"]) == ["catalog-api", "pricing-engine"]
    assert data["impact"]["touched"] == ["catalog-db"]
    assert data["impact"]["testOnly"] == []
    assert set(data["impact"]["peripheral"]) == PERIPHERAL_1_1

    _, data = _payload("1.2")
    assert sorted(data["impact"]["changed"]) == ["invoice-generator", "orders-api"]
    assert data["impact"]["touched"] == ["checkout-flow"]
    assert data["impact"]["testOnly"] == ["search-index"]
    assert set(data["impact"]["peripheral"]) == PERIPHERAL_1_2


def test_sample_series_files():
    assert main(["--sample", "--base-dir", str(BASE)]) == 0
    manifest = (SERIES / "releases.js").read_text(encoding="utf-8")
    entries = json.loads(manifest[len("window.CHANGEATLAS_RELEASES = "):].rstrip(";\n"))
    assert [e["label"] for e in entries] == ["1.0", "1.1", "1.2"]
    for e in entries:
        assert e["report"] == f"impact-{e['label']}.html"
        assert (SERIES / e["history"]).exists()
    side = (SERIES / "impact-1.1.history.js").read_text(encoding="utf-8")
    assert '"pricing-engine"' in side and "tracker.example" not in side
