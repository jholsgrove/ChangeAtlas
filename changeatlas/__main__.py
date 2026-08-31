"""ChangeAtlas CLI — release impact map from an ADO shared query."""
import argparse
import json
import platform
import re
import sys
from datetime import date
from pathlib import Path

from . import anonymize, heuristics, impact, mapping, palette, render
from .gatherers import ado

_GUID_RE = re.compile(
    r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
)

PKG_DIR = Path(__file__).resolve().parent          # .../ChangeAtlas/changeatlas
BASE_DIR = PKG_DIR.parent                          # .../ChangeAtlas

TYPE_STYLE = {
    "repo": ("Repo", palette.TYPE_COLORS["repo"]),
    "subsystem": ("Subsystem", palette.TYPE_COLORS["subsystem"]),
    "project": ("Project", palette.TYPE_COLORS["project"]),
    "service": ("Service", palette.TYPE_COLORS["service"]),
    "contract": ("Contract", palette.TYPE_COLORS["contract"]),
    "driver": ("Driver", palette.TYPE_COLORS["driver"]),
    "database": ("Database", palette.TYPE_COLORS["database"]),
    "messaging": ("Messaging", palette.TYPE_COLORS["messaging"]),
    "feature": ("Feature", palette.TYPE_COLORS["feature"]),
    "external": ("External", palette.TYPE_COLORS["external"]),
}
EDGE_LABEL = {
    "contains": "contains", "nuget": "NuGet", "http": "HTTP", "sql": "SQL",
    "bus": "publishes", "consumes": "consumes", "project-ref": "project-ref",
    "owns": "owns", "uses": "uses",
}


def parse_query_id(value: str) -> str:
    """Extract the query GUID from a shared-query URL or a bare GUID string."""
    m = _GUID_RE.search(value)
    if not m:
        raise ValueError(
            f"Could not find a query GUID in {value!r}. Pass the shared-query "
            "URL (…/_queries/query/<guid>/) or the GUID itself."
        )
    return m.group(1).lower()


def main(argv=None, fetch=ado.default_fetch) -> int:
    ap = argparse.ArgumentParser(
        prog="changeatlas", description="Release impact map from an ADO shared query.")
    ap.add_argument("--query", help="shared-query URL or GUID")
    ap.add_argument("--release", help="release label, e.g. 1.0")
    ap.add_argument("--refresh", action="store_true", help="re-fetch from ADO, ignore cache")
    ap.add_argument("--check-map", action="store_true",
                    help="validate the component map and exit")
    ap.add_argument("--org", default=None, help="ADO org URL, e.g. https://dev.azure.com/<org>")
    ap.add_argument("--project", default=None, help="ADO project name")
    ap.add_argument("--graph-data", default=None,
                    help="path to graph-data.json (required unless --sample)")
    ap.add_argument("--base-dir", default=str(BASE_DIR),
                    help="folder holding config/ and out/ (tests override)")
    ap.add_argument("--vis", default=str(BASE_DIR / "vendor" / "vis-network.min.js"))
    ap.add_argument("--changed-threshold", type=int, default=3,
                    help="production files needed for full 'changed' shading "
                         "(fewer = pale 'touched'); default 3")
    ap.add_argument("--heuristics", default="generic",
                    help="heuristics preset name (config/heuristics/<name>.json) "
                         "or a path to a heuristics JSON file; default 'generic'")
    ap.add_argument("--anonymize", action="store_true",
                    help="demo-safe output: generic node/story/PR names, dead "
                         "ADO links; writes impact-{release}-anon.html")
    ap.add_argument("--sample", action="store_true",
                    help="use the bundled fictional sample dataset (no ADO needed)")
    args = ap.parse_args(argv)

    base = Path(args.base_dir)

    if args.sample:
        graph_path = base / "sample" / "graph-data.json"
        map_path = base / "sample" / "component-globs.json"
        cache_path = base / "sample" / "release-1.0-data.json"
        release = "1.0"
        out_path = base / "out" / "impact-sample.html"
    else:
        if not args.graph_data:
            print("--graph-data is required (or use --sample)", file=sys.stderr)
            return 2
        graph_path = Path(args.graph_data)
        map_path = base / "config" / "component-globs.json"
        release = args.release
        out_path = None      # computed later, once we know we're actually rendering

    if not graph_path.exists():
        print(f"graph data not found: {graph_path}", file=sys.stderr)
        return 1
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    try:
        components = mapping.load_map(map_path)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    errors, warnings = mapping.check_map(components, graph["nodes"])
    if args.check_map:
        for line in errors + warnings:
            print(line)
        print("errors: %d, warnings: %d%s" % (len(errors), len(warnings),
                                              "" if errors or warnings else " — clean"))
        return 1 if errors else 0
    if errors:
        print("component map errors (run --check-map):", *errors, sep="\n  ", file=sys.stderr)
        return 1

    if not args.sample:
        if not args.query or not release:
            print("--query and --release are required (or use --check-map / --sample)",
                  file=sys.stderr)
            return 2
        try:
            query_id = parse_query_id(args.query)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 1
        cache_path = base / "out" / f"release-{release}-data.json"
        use_cache = cache_path.exists() and not args.refresh
    else:
        # --sample never touches ADO: the bundled cache is always used.
        use_cache = True

    if use_cache:
        print(f"Using cached ADO data: {cache_path} (--refresh to re-fetch)")
        gathered = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        if not args.org or not args.project:
            print("--org and --project are required to fetch from ADO "
                  "(or use --sample / a cache file)", file=sys.stderr)
            return 2
        try:
            gathered = ado.gather_release(fetch, args.org, args.project, query_id, release)
        except ado.TokenMissingError:
            ps = '$env:CHANGEATLAS_TOKEN = "<your-pat>"'
            sh = 'export CHANGEATLAS_TOKEN="<your-pat>"'
            cmd = ps if platform.system() == "Windows" else sh
            print(f"No PAT found. Set the {ado.TOKEN_ENV} environment variable, e.g.\n"
                  f"  {cmd}\nSee docs/tokens.md for scopes and persistent setup.",
                  file=sys.stderr)
            return 1
        except ado.AdoHttpError as exc:
            hint = {401: "token invalid or expired — see docs/tokens.md",
                    403: "token lacks scopes (needs Work Items Read + Code Read)",
                    404: "org/project/query id not found — check the URL you passed"}
            print(f"ADO fetch failed: {exc} ({hint.get(exc.status, 'unexpected HTTP status')})",
                  file=sys.stderr)
            return 1
        if not gathered["work_items"]:
            print("Query returned no work items — nothing to map.", file=sys.stderr)
            return 1
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(gathered, indent=1), encoding="utf-8")

    try:
        heur = heuristics.load(args.heuristics, base)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    result = impact.compute(gathered, components, graph["nodes"], graph["edges"], heur,
                            changed_threshold=args.changed_threshold)

    payload = {
        "release": release,
        "generated": date.today().isoformat(),
        "nodes": graph["nodes"], "edges": graph["edges"],
        "typeStyle": {t: {"label": l, "color": c} for t, (l, c) in TYPE_STYLE.items()},
        "edgeLabel": EDGE_LABEL,
        "impact": {"changed": result["changed"], "touched": result["touched"],
                   "testOnly": result["test_only"], "peripheral": result["peripheral"]},
        "details": result["details"],
    }
    if args.anonymize:
        payload = anonymize.anonymize_payload(payload)

    if args.sample:
        final_out = out_path
    else:
        suffix = "-anon" if args.anonymize else ""
        final_out = base / "out" / f"impact-{release}{suffix}.html"
    final_out.parent.mkdir(parents=True, exist_ok=True)
    final_out.write_text(render.render(payload, PKG_DIR / "template.html", args.vis),
                         encoding="utf-8")

    untouched = len(graph["nodes"]) - sum(
        len(result[k]) for k in ("changed", "touched", "test_only", "peripheral"))
    print(f"Wrote {final_out}")
    print(f"{len(result['changed'])} changed · {len(result['touched'])} touched · "
          f"{len(result['test_only'])} test-only · {len(result['peripheral'])} peripheral · "
          f"{untouched} untouched")
    if result["dependency_files_skipped"]:
        print(f"{result['dependency_files_skipped']} dependency/NuGet manifest file(s) ignored")
    no_code = [wi for wi in gathered["work_items"] if not wi["prs"]]
    if no_code:
        print(f"{len(no_code)} work item(s) with no linked PRs (no code change):")
        for wi in no_code:
            print(f"  #{wi['id']} {wi['title']}")
    for note in gathered.get("skipped", []):
        print(f"  skipped: {note}")
    if result["unmatched_files"]:
        print("Unmatched files (unknown repo or no glob at all):")
        for f in result["unmatched_files"]:
            print(f"  {f}")
    if result["beyond_repo_files"]:
        print("Unmapped beyond repo (extend config/component-globs.json):")
        for f in result["beyond_repo_files"]:
            print(f"  {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
