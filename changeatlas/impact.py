"""impact.py — tiered impact sets and per-node story/PR panel payload.

Tiers (production files only decide the tier):
  changed   — >= changed_threshold production files matched the node
  touched   — 1..threshold-1 production files
  test_only — only test files matched the node
Repo-type nodes never enter a tier (their catch-all matches everything), and
edges involving them never spread the peripheral ring. Dependency-manifest
files (NuGet bumps, project files) are ignored entirely. Database-type nodes
shade only on schema evidence (migrations, .sql, model snapshots) and are
never peripheral.
"""
from . import mapping


def compute(gathered: dict, components: list, nodes: list, edges: list, heur,
            changed_threshold: int = 3) -> dict:
    repo_ids = {n["id"] for n in nodes if n["type"] == "repo"}
    db_ids = {n["id"] for n in nodes if n["type"] == "database"}
    prod_files: dict[str, set] = {}
    test_files: dict[str, set] = {}
    details: dict[str, dict] = {}
    beyond_repo_files: list[str] = []
    unmatched_files: list[str] = []
    seen_files: set[tuple] = set()
    dependency_skipped = 0

    for wi in gathered["work_items"]:
        story = {"id": wi["id"], "type": wi["type"], "title": wi["title"], "url": wi["url"]}
        for pr in wi["prs"]:
            repo_key = mapping.normalise_repo(pr["repo"])
            pr_rec = {"id": pr["id"], "title": pr["title"],
                      "repo": pr["repo"], "url": pr["url"]}
            for path in pr["files"]:
                file_key = (pr["repo"], path)
                first_sight = file_key not in seen_files
                seen_files.add(file_key)
                if heur.is_dependency_file(path):
                    if first_sight:
                        dependency_skipped += 1
                    continue
                ids, beyond = mapping.match_file(components, repo_key, path)
                if first_sight:
                    if not ids:
                        unmatched_files.append(f"{pr['repo']}:{path}")
                    elif not beyond:
                        beyond_repo_files.append(f"{pr['repo']}:{path}")
                bucket = test_files if heur.is_test_file(path) else prod_files
                for nid in ids:
                    if nid in repo_ids:
                        continue
                    # Database nodes take evidence only from schema changes
                    # (migrations, .sql, snapshots) — ordinary data-access
                    # code edits don't imply the database itself changed.
                    if nid in db_ids and not heur.is_schema_file(path):
                        continue
                    bucket.setdefault(nid, set()).add(file_key)
                    d = details.setdefault(nid, {"stories": {}, "prs": {}})
                    d["stories"][story["id"]] = story
                    d["prs"][pr_rec["id"]] = pr_rec

    changed = {n for n, f in prod_files.items() if len(f) >= changed_threshold}
    touched = {n for n, f in prod_files.items() if f and n not in changed}
    test_only = set(test_files) - changed - touched

    peripheral: set[str] = set()
    for e in edges:
        if e["from"] in repo_ids or e["to"] in repo_ids:
            continue
        if e["from"] in changed:
            peripheral.add(e["to"])
        if e["to"] in changed:
            peripheral.add(e["from"])
    # Databases only ever shade on schema evidence — a changed neighbour
    # does not make the database itself amber.
    peripheral -= changed | touched | test_only | db_ids

    return {
        "changed": sorted(changed),
        "touched": sorted(touched),
        "test_only": sorted(test_only),
        "peripheral": sorted(peripheral),
        "details": {
            nid: {"stories": [d["stories"][k] for k in sorted(d["stories"])],
                  "prs": [d["prs"][k] for k in sorted(d["prs"])],
                  "prodFiles": len(prod_files.get(nid, ())),
                  "testFiles": len(test_files.get(nid, ()))}
            for nid, d in details.items()
        },
        "beyond_repo_files": beyond_repo_files,
        "unmatched_files": unmatched_files,
        "dependency_files_skipped": dependency_skipped,
    }
