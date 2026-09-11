import json
from pathlib import Path

from changeatlas import history


def _cache(dir_: Path, label: str, fetched_at: str, files=("/src/checkout/A.ts",)):
    dir_.mkdir(parents=True, exist_ok=True)
    data = {"release": label, "query": "q", "fetched_at": fetched_at, "skipped": [],
            "work_items": [{"id": 1, "type": "Bug", "title": "t", "url": "u",
                            "prs": [{"id": 2, "title": "p", "repo": "shop-web", "url": "u",
                                     "status": "completed", "files": list(files)}]}]}
    p = dir_ / f"release-{label}-data.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_discover_orders_by_fetched_at_not_label(tmp_path):
    _cache(tmp_path, "26.10", "2026-01-05T00:00:00Z")   # older fetch, "bigger" label
    _cache(tmp_path, "26.9", "2026-03-01T00:00:00Z")
    _cache(tmp_path, "26.8", "2026-02-01T00:00:00Z")
    releases, warnings = history.discover(tmp_path)
    assert [r.label for r in releases] == ["26.10", "26.8", "26.9"]
    assert warnings == []


def test_discover_skips_unreadable_cache_with_warning(tmp_path):
    _cache(tmp_path, "1.0", "2026-01-01T00:00:00Z")
    (tmp_path / "release-bad-data.json").write_text("{not json", encoding="utf-8")
    releases, warnings = history.discover(tmp_path)
    assert [r.label for r in releases] == ["1.0"]
    assert len(warnings) == 1 and "release-bad-data.json" in warnings[0]


def test_discover_ignores_non_release_files_and_missing_dir(tmp_path):
    _cache(tmp_path, "1.0", "2026-01-01T00:00:00Z")
    (tmp_path / "impact-1.0.html").write_text("<html>", encoding="utf-8")
    releases, _ = history.discover(tmp_path)
    assert [r.label for r in releases] == ["1.0"]
    assert history.discover(tmp_path / "nope") == ([], [])


def test_discover_orders_by_instant_not_string_across_offsets(tmp_path):
    # ISO 8601 only sorts lexicographically when every value shares the same
    # form and offset. 'b' and 'c' are the same UTC instant (2026-02-28T23:00Z),
    # both earlier than 'a' (2026-03-01T00:00Z) -- but a naive string sort of
    # the raw text orders them "c", "a", "b" (it thinks 'a' is earlier than
    # 'b' because "00:00:00Z" < "01:00:00+02:00" lexically). The instant-based
    # sort must put 'a' last.
    _cache(tmp_path, "a", "2026-03-01T00:00:00Z")
    _cache(tmp_path, "b", "2026-03-01T01:00:00+02:00")   # == 2026-02-28T23:00:00Z
    _cache(tmp_path, "c", "2026-02-28T23:00:00+00:00")   # same instant as b
    releases, warnings = history.discover(tmp_path)
    labels = [r.label for r in releases]
    assert labels[-1] == "a"                    # latest instant sorts last
    assert set(labels[:-1]) == {"b", "c"}        # both equal-and-earlier instants sort first
    assert warnings == []


def test_discover_skips_unsafe_release_label_with_warning(tmp_path):
    # The label comes from the JSON body, not the filename (see history.py's
    # module docstring on _CACHE_RE), so a hand-built cache can disagree: the
    # file matches the naming convention but the body's "release" is unsafe
    # to use as a filename.
    _cache(tmp_path, "1.0", "2026-01-01T00:00:00Z")
    bad = tmp_path / "release-evil-data.json"
    bad.write_text(json.dumps({"release": "../evil", "fetched_at": "2026-01-02T00:00:00Z"}),
                   encoding="utf-8")
    releases, warnings = history.discover(tmp_path)
    assert [r.label for r in releases] == ["1.0"]
    assert len(warnings) == 1 and bad.name in warnings[0]


GRAPH = {"nodes": [
    {"id": "shop-web", "title": "Shop Web", "type": "repo", "repo": "shop-web", "summary": "s", "tags": []},
    {"id": "checkout-flow", "title": "Checkout", "type": "feature", "repo": "shop-web", "summary": "s", "tags": []},
    {"id": "orders-api", "title": "Orders", "type": "service", "repo": "shop-web", "summary": "s", "tags": []},
], "edges": [
    {"from": "shop-web", "to": "checkout-flow", "kind": "contains"},
    {"from": "checkout-flow", "to": "orders-api", "kind": "http"},
]}
COMPONENTS = [
    {"id": "shop-web", "repo": "shop-web", "globs": ["**"]},
    {"id": "checkout-flow", "repo": "shop-web", "globs": ["**/checkout/**"]},
    {"id": "orders-api", "repo": "shop-web", "globs": ["**/orders/**"]},
]


class _Heur:
    def is_dependency_file(self, p): return p.endswith("package-lock.json")
    def is_test_file(self, p): return "/tests/" in p or ".test." in p
    def is_schema_file(self, p): return p.endswith(".sql")


def _load_components():
    import json as _json
    import tempfile

    from changeatlas import mapping

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "component-globs.json"
        p.write_text(_json.dumps({"components": COMPONENTS}), encoding="utf-8")
        return mapping.load_map(p)


def _compute(gathered):
    return history.sidecar(gathered, _load_components(), GRAPH["nodes"], GRAPH["edges"], _Heur(), 3)


def test_sidecar_has_tiers_and_counts_only():
    gathered = json.loads(_cache(Path(__import__("tempfile").mkdtemp()), "1.0", "2026-01-01T00:00:00Z",
                          files=("/src/checkout/A.ts", "/src/checkout/B.ts", "/src/checkout/C.ts",
                                 "/src/checkout/tests/A.test.ts")).read_text(encoding="utf-8"))
    side = _compute(gathered)
    assert set(side) == {"impact", "counts"}
    assert set(side["impact"]) == {"changed", "touched", "testOnly", "peripheral"}
    assert side["impact"]["changed"] == ["checkout-flow"]
    assert side["impact"]["peripheral"] == ["orders-api"]
    assert side["counts"] == {"checkout-flow": {"prodFiles": 3, "testFiles": 1}}
    blob = json.dumps(side)
    for secret in ("tracker", "title", "url", "stories", "prs", "https://"):
        assert secret not in blob, secret


def test_write_series_caps_at_five_most_recent_and_writes_manifest(tmp_path):
    out = tmp_path / "out"
    for i in range(7):   # labels 1.0 .. 1.6, fetched a day apart
        _cache(out, f"1.{i}", f"2026-01-0{i + 1}T00:00:00Z")
    (out / "impact-1.6.html").write_text("<html>", encoding="utf-8")   # only the newest has a report
    releases, _ = history.discover(out)
    warnings = history.write_series(out, releases, _compute)
    assert warnings == []
    manifest = (out / "releases.js").read_text(encoding="utf-8")
    assert manifest.startswith("window.CHANGEATLAS_RELEASES = ")
    entries = json.loads(manifest[len("window.CHANGEATLAS_RELEASES = "):].rstrip(";\n"))
    assert [e["label"] for e in entries] == ["1.2", "1.3", "1.4", "1.5", "1.6"]
    assert entries[-1] == {"label": "1.6", "fetchedAt": "2026-01-07T00:00:00Z",
                           "history": "impact-1.6.history.js", "report": "impact-1.6.html"}
    assert entries[0]["report"] is None
    for e in entries:
        assert (out / e["history"]).exists()
    assert not (out / "impact-1.0.history.js").exists()
    assert not (out / "impact-1.1.history.js").exists()


def test_sidecar_file_is_a_script_that_registers_its_label(tmp_path):
    out = tmp_path / "out"
    _cache(out, "26.8", "2026-02-01T00:00:00Z")
    releases, _ = history.discover(out)
    history.write_series(out, releases, _compute)
    js = (out / "impact-26.8.history.js").read_text(encoding="utf-8")
    assert js.startswith("window.CHANGEATLAS_HISTORY = window.CHANGEATLAS_HISTORY || {};\n")
    assert 'window.CHANGEATLAS_HISTORY["26.8"] = ' in js
    assert "</" not in js.replace("<\\/", "")   # never terminates a script block if inlined


def test_write_series_with_one_release_still_writes_manifest(tmp_path):
    out = tmp_path / "out"
    _cache(out, "1.0", "2026-01-01T00:00:00Z")
    releases, _ = history.discover(out)
    history.write_series(out, releases, _compute)
    entries = json.loads((out / "releases.js").read_text(encoding="utf-8")
                         [len("window.CHANGEATLAS_RELEASES = "):].rstrip(";\n"))
    assert len(entries) == 1


def test_write_series_writes_latest_stub_pointing_at_newest_report(tmp_path):
    out = tmp_path / "out"
    _cache(out, "26.10", "2026-01-05T00:00:00Z")   # older fetch, "bigger" label
    _cache(out, "26.9", "2026-03-01T00:00:00Z")
    for label in ("26.10", "26.9"):
        (out / f"impact-{label}.html").write_text("<html>", encoding="utf-8")
    releases, _ = history.discover(out)
    history.write_series(out, releases, _compute)
    stub = (out / history.LATEST_NAME).read_text(encoding="utf-8")
    assert 'content="0; url=impact-26.9.html"' in stub
    assert 'href="impact-26.9.html"' in stub
    assert "26.10" not in stub


def test_latest_stub_skips_a_newest_release_with_no_report(tmp_path):
    out = tmp_path / "out"
    _cache(out, "1.0", "2026-01-01T00:00:00Z")
    _cache(out, "1.1", "2026-01-02T00:00:00Z")     # cache only, never rendered
    (out / "impact-1.0.html").write_text("<html>", encoding="utf-8")
    releases, _ = history.discover(out)
    history.write_series(out, releases, _compute)
    assert 'url=impact-1.0.html"' in (out / history.LATEST_NAME).read_text(encoding="utf-8")


def test_latest_stub_is_removed_when_no_release_has_a_report(tmp_path):
    out = tmp_path / "out"
    _cache(out, "1.0", "2026-01-01T00:00:00Z")
    out.mkdir(exist_ok=True)
    (out / history.LATEST_NAME).write_text("stale", encoding="utf-8")
    releases, _ = history.discover(out)
    history.write_series(out, releases, _compute)
    assert not (out / history.LATEST_NAME).exists()

