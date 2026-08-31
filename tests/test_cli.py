import json
import platform

import pytest

from changeatlas.__main__ import main, parse_query_id
from changeatlas import __main__ as cli
from changeatlas.gatherers import ado

GUID = "7035aa61-d5f3-4016-b3e7-19807d14932b"
ORG = "https://dev.azure.com/exampleorg"
PROJ = "Shop"


def test_full_query_url():
    url = f"{ORG}/{PROJ}/_queries/query/{GUID}/"
    assert parse_query_id(url) == GUID


def test_url_without_trailing_slash():
    url = f"{ORG}/{PROJ}/_queries/query/{GUID}"
    assert parse_query_id(url) == GUID


def test_query_edit_url():
    url = f"{ORG}/{PROJ}/_queries/query-edit/{GUID}/"
    assert parse_query_id(url) == GUID


def test_bare_guid():
    assert parse_query_id(GUID) == GUID


def test_uppercase_guid_normalised():
    assert parse_query_id(GUID.upper()) == GUID


def test_garbage_raises():
    with pytest.raises(ValueError):
        parse_query_id(f"{ORG}/{PROJ}/_boards/")
    with pytest.raises(ValueError):
        parse_query_id("not a guid at all")


GRAPH = {"nodes": [
    {"id": "checkout-flow", "title": "Checkout", "type": "feature",
     "repo": "shop-web", "summary": "s", "tags": []},
    {"id": "shop-web", "title": "Shop Web", "type": "repo",
     "repo": "shop-web", "summary": "s", "tags": []},
],
    "edges": [{"from": "shop-web", "to": "checkout-flow", "kind": "contains"}]}

GLOBS = {"components": [
    {"id": "checkout-flow", "repo": "shop-web", "globs": ["**/checkout/**"]},
    {"id": "shop-web", "repo": "shop-web", "globs": ["**"]},
]}

# Minimal generic-preset heuristics fixture, self-contained (independent of
# the repo's real config/heuristics/generic.json) but schema-complete.
HEURISTICS = {
    "dependency_basenames": ["package-lock.json", "yarn.lock"],
    "dependency_suffixes": [".nuspec"],
    "test_markers": ["test", "spec"],
    "schema_suffixes": [".sql"],
    "schema_segments": ["migrations"],
    "schema_basename_contains": ["schema"],
}

CACHE = {
    "release": "1.0", "query": "q", "fetched_at": "t", "skipped": [],
    "work_items": [{"id": 1, "type": "Bug", "title": "T", "url": "u",
                    "prs": [{"id": 2, "title": "p", "repo": "Shop.Web",
                             "url": "u", "status": "completed",
                             "files": ["/checkout/Form.tsx", "/checkout/Api.ts",
                                       "/checkout/Totals.tsx",
                                       "/package-lock.json"]}]},
                   {"id": 7, "type": "Task", "title": "Docs only", "url": "u2",
                    "prs": []}],
}


def setup_dirs(tmp_path):
    (tmp_path / "config" / "heuristics").mkdir(parents=True)
    (tmp_path / "out").mkdir()
    (tmp_path / "config" / "component-globs.json").write_text(
        json.dumps(GLOBS), encoding="utf-8")
    (tmp_path / "config" / "heuristics" / "generic.json").write_text(
        json.dumps(HEURISTICS), encoding="utf-8")
    (tmp_path / "graph-data.json").write_text(json.dumps(GRAPH), encoding="utf-8")
    (tmp_path / "vis.js").write_text("var vis;", encoding="utf-8")
    return tmp_path


def base_args(root):
    return ["--query", GUID, "--release", "1.0",
            "--graph-data", str(root / "graph-data.json"),
            "--base-dir", str(root), "--vis", str(root / "vis.js"),
            "--org", ORG, "--project", PROJ]


def make_project(tmp_path):
    """Build a minimal on-disk project (graph/map/heuristics/vis, no cache) and
    the matching CLI args list — the shared fixture reused by every CLI test."""
    root = setup_dirs(tmp_path)
    return root, base_args(root)


def test_main_uses_cache_and_renders(tmp_path, capsys):
    root, args = make_project(tmp_path)
    (root / "out" / "release-1.0-data.json").write_text(json.dumps(CACHE), encoding="utf-8")

    def forbidden_fetch(url):
        raise AssertionError("fetch must not be called when cache exists")

    rc = cli.main(args, fetch=forbidden_fetch)
    assert rc == 0
    html = (root / "out" / "impact-1.0.html").read_text(encoding="utf-8")
    assert "Release 1.0 — ChangeAtlas" in html
    out = capsys.readouterr().out
    assert "impact-1.0.html" in out
    # 3 prod files -> changed; repo node excluded from tiers despite catch-all
    assert "1 changed" in out and "0 touched" in out and "0 test-only" in out
    assert "1 dependency/NuGet manifest file(s) ignored" in out
    assert "no code change" in out
    assert "#7 Docs only" in out
    assert '"touched"' in html and '"testOnly"' in html  # payload carries the new tiers


def test_main_no_query_needed_when_cache_exists(tmp_path, monkeypatch):
    """A hand-built release-data.json (e.g. from a custom gatherer, see
    prompts/build-gatherer.md) must render with only --release + --graph-data
    (+ --base-dir) — no --query, no --org/--project, and no ADO token."""
    monkeypatch.delenv(ado.TOKEN_ENV, raising=False)
    root = setup_dirs(tmp_path)
    (root / "out" / "release-1.0-data.json").write_text(json.dumps(CACHE), encoding="utf-8")

    def forbidden_fetch(url):
        raise AssertionError("fetch must not be called when cache exists and --query is absent")

    args = ["--release", "1.0", "--graph-data", str(root / "graph-data.json"),
            "--base-dir", str(root), "--vis", str(root / "vis.js")]
    rc = cli.main(args, fetch=forbidden_fetch)
    assert rc == 0
    assert (root / "out" / "impact-1.0.html").exists()


def test_main_refresh_triggers_fetch(tmp_path):
    root, args = make_project(tmp_path)
    (root / "out" / "release-1.0-data.json").write_text(json.dumps(CACHE), encoding="utf-8")
    calls = []

    def fake_fetch(url):
        calls.append(url)
        if "/_apis/wit/wiql/" in url:
            return {"workItems": []}
        if "/_apis/git/repositories" in url:
            return {"value": []}
        raise AssertionError(f"unexpected url: {url}")

    rc = cli.main(args + ["--refresh"], fetch=fake_fetch)
    assert rc == 1          # empty query result aborts
    assert calls            # fetch was invoked


def test_main_check_map(tmp_path, capsys):
    root, _ = make_project(tmp_path)
    rc = cli.main(["--check-map", "--graph-data", str(root / "graph-data.json"),
                   "--base-dir", str(root)], fetch=None)
    assert rc == 0
    assert "clean" in capsys.readouterr().out.lower()


def test_main_unmapped_reporting(tmp_path, capsys):
    root, args = make_project(tmp_path)
    cache = json.loads(json.dumps(CACHE))
    cache["work_items"][0]["prs"][0]["files"].append("/tools/build.ps1")
    (root / "out" / "release-1.0-data.json").write_text(json.dumps(cache), encoding="utf-8")
    rc = cli.main(args, fetch=None)
    assert rc == 0
    out = capsys.readouterr().out
    assert "beyond repo" in out and "/tools/build.ps1" in out


# --- new tests (Task 8 brief) -----------------------------------------

def test_graph_data_required(tmp_path, capsys):
    rc = main(["--query", "abc", "--release", "1.0"])   # no --graph-data, no --sample
    assert rc == 2 or rc == 1
    err = capsys.readouterr().err
    assert "--graph-data is required" in err


def test_query_required_message_when_fetch_needed(tmp_path, capsys):
    """No cache and no --query: --org/--project/token are never even reached —
    the error names the missing flag and why (no cache found)."""
    root = setup_dirs(tmp_path)   # no cache file written -> a fetch would be needed
    args = ["--release", "1.0", "--graph-data", str(root / "graph-data.json"),
            "--base-dir", str(root), "--vis", str(root / "vis.js")]

    def forbidden_fetch(url):
        raise AssertionError("fetch must not be attempted without a resolvable --query")

    rc = cli.main(args, fetch=forbidden_fetch)
    assert rc == 2
    err = capsys.readouterr().err
    assert "--query is required to fetch" in err
    assert "no cache found at" in err


def test_missing_token_message_names_env_var_and_os_command(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv(ado.TOKEN_ENV, raising=False)
    root, args = make_project(tmp_path)   # no cache file written -> a fetch is needed
    rc = main(args)   # default fetch=ado.default_fetch
    assert rc == 1
    out = capsys.readouterr().err
    assert "CHANGEATLAS_TOKEN" in out
    expected = "$env:CHANGEATLAS_TOKEN" if platform.system() == "Windows" else "export CHANGEATLAS_TOKEN"
    assert expected in out


def test_http_401_maps_to_token_hint(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv(ado.TOKEN_ENV, "x")
    root, args = make_project(tmp_path)   # no cache file written -> a fetch is needed

    def fetch(url):
        raise ado.AdoHttpError(401, url)

    rc = main(args + ["--refresh"], fetch=fetch)
    assert rc == 1
    assert "token invalid or expired" in capsys.readouterr().err


def test_component_map_missing_gives_friendly_message_no_traceback(tmp_path, capsys):
    """MUST-FIX 2: a nonexistent/unreadable component-globs path must not
    surface a raw traceback -- friendly stderr message + rc 1."""
    (tmp_path / "graph-data.json").write_text(json.dumps(GRAPH), encoding="utf-8")
    # No config/component-globs.json written at all under this base-dir.
    args = ["--check-map", "--graph-data", str(tmp_path / "graph-data.json"),
            "--base-dir", str(tmp_path)]
    rc = main(args, fetch=None)
    assert rc == 1
    err = capsys.readouterr().err
    assert "component map not found/unreadable at" in err
    assert "prompts/build-glob-map.md" in err
    assert "Traceback" not in err


def test_ado_connection_error_maps_to_actionable_message(tmp_path, capsys, monkeypatch):
    """MUST-FIX 3: AdoConnectionError (DNS/refused/timeout/bad JSON) must map
    to an actionable stderr message naming the unreachable host, rc 1."""
    monkeypatch.setenv(ado.TOKEN_ENV, "x")
    root, args = make_project(tmp_path)   # no cache file written -> a fetch is needed

    def fetch(url):
        raise ado.AdoConnectionError(url, "Name or service not known")

    rc = main(args + ["--refresh"], fetch=fetch)
    assert rc == 1
    err = capsys.readouterr().err
    assert "could not reach" in err
    assert "check --org / network" in err
