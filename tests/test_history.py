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
