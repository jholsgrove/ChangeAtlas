"""The bundled 100-repo sample: generator determinism and golden tier truth.

The generator designs the release (which members get 3 prod files, 1 prod
file, a test file only, a migration, a data-access-only edit, a manifest
bump) and writes that design to expected-tiers.json. ChangeAtlas's own
impact computation must reproduce it exactly for changed/touched/test-only
and must include the designed cross-repo peripheral spread.
"""
import json
import re
import sys
from pathlib import Path

from changeatlas.__main__ import main

BASE = Path(__file__).resolve().parent.parent
LARGE = BASE / "sample" / "large"
FILES = ("graph-data.json", "component-globs.json", "release-1.0-data.json",
         "expected-tiers.json")


def _load_generator():
    sys.path.insert(0, str(LARGE))
    try:
        import generate
        return generate
    finally:
        sys.path.pop(0)


def test_generator_is_deterministic_and_matches_checked_in_files(tmp_path):
    gen = _load_generator()
    gen.write_all(tmp_path)
    for name in FILES:
        assert (tmp_path / name).read_text(encoding="utf-8") == \
            (LARGE / name).read_text(encoding="utf-8"), name


def test_large_sample_shape():
    graph = json.loads((LARGE / "graph-data.json").read_text(encoding="utf-8"))
    repos = [n for n in graph["nodes"] if n["type"] == "repo"]
    assert len(repos) == 100
    assert 1200 <= len(graph["nodes"]) <= 1700
    ids = {n["id"] for n in graph["nodes"]}
    assert len(ids) == len(graph["nodes"])
    for e in graph["edges"]:
        assert e["from"] in ids and e["to"] in ids
    for n in graph["nodes"]:
        assert set(n) == {"id", "title", "type", "repo", "summary", "tags"}, n["id"]
    total = sum((LARGE / f).stat().st_size for f in FILES)
    assert total <= 1_000_000, total


def test_large_sample_check_map_is_clean(capsys):
    rc = main(["--check-map", "--sample", "large", "--base-dir", str(BASE)])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "clean" in out


def test_large_sample_golden_tiers(capsys):
    rc = main(["--sample", "large", "--base-dir", str(BASE)])
    assert rc == 0
    out = capsys.readouterr().out
    html = (BASE / "out" / "impact-sample-large.html").read_text(encoding="utf-8")
    assert len(html) <= 3_000_000

    prefix = "const DATA = "
    start = html.index(prefix) + len(prefix)
    data, _ = json.JSONDecoder().raw_decode(html[start:])
    expected = json.loads((LARGE / "expected-tiers.json").read_text(encoding="utf-8"))

    assert sorted(data["impact"]["changed"]) == sorted(expected["changed"])
    assert sorted(data["impact"]["touched"]) == sorted(expected["touched"])
    assert sorted(data["impact"]["testOnly"]) == sorted(expected["testOnly"])
    assert set(expected["peripheralIncludes"]) <= set(data["impact"]["peripheral"])
    tiered = set(data["impact"]["changed"]) | set(data["impact"]["touched"]) \
        | set(data["impact"]["testOnly"]) | set(data["impact"]["peripheral"])
    for db in expected["untouchedDatabases"]:
        assert db not in tiered, db

    assert data["groupThreshold"] == 150
    assert "tracker.example" in html
    assert re.search(r"\d+ dependency/NuGet manifest file\(s\) ignored", out)
    assert "work item(s) with no linked PRs" in out
    assert "Unmatched files" not in out
