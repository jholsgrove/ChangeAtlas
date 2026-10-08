from pathlib import Path

from changeatlas import heuristics, impact

HEUR = heuristics.load("dotnet", Path(__file__).resolve().parent.parent)

NODES = [
    {"id": "checkout-snmp-stack", "type": "subsystem", "repo": "checkout-service"},
    {"id": "checkout-core", "type": "subsystem", "repo": "checkout-service"},
    {"id": "checkout-wlc", "type": "subsystem", "repo": "checkout-service"},
    {"id": "checkout-service", "type": "repo", "repo": "checkout-service"},
    {"id": "shop-portal", "type": "service", "repo": "shop-web"},
]
EDGES = [
    {"from": "checkout-core", "to": "checkout-snmp-stack", "kind": "uses"},   # peripheral via incoming
    {"from": "checkout-snmp-stack", "to": "checkout-wlc", "kind": "uses"},    # peripheral via outgoing
    {"from": "checkout-service", "to": "checkout-snmp-stack", "kind": "contains"},
    {"from": "checkout-service", "to": "checkout-core", "kind": "contains"},
]
COMPONENTS = [
    {"id": "checkout-snmp-stack", "repo": "checkout-service", "globs": ["**/Snmp/**"]},
    {"id": "checkout-core", "repo": "checkout-service", "globs": ["**/Core/**"]},
    {"id": "checkout-service", "repo": "checkout-service", "globs": ["**"]},
]


def gathered(files, extra_prs=()):
    return {
        "release": "26.8",
        "work_items": [
            {"id": 43900, "type": "User Story", "title": "S", "url": "wi-url",
             "prs": [{"id": 13277, "title": "P", "repo": "Checkout.Service",
                      "url": "pr-url", "status": "completed", "files": list(files)}]
                    + list(extra_prs)},
        ],
    }


def test_file_classifiers():
    assert HEUR.is_dependency_file("/Directory.Packages.props")
    assert HEUR.is_dependency_file("/src/App/packages.config")
    assert HEUR.is_dependency_file("/src/App/App.csproj")
    assert HEUR.is_dependency_file("/Checkout/Checkout.dproj")
    assert not HEUR.is_dependency_file("/src/App/Program.cs")
    assert HEUR.is_test_file("/Checkout.Service.Tests/WalkerTests.cs")
    assert HEUR.is_test_file("/src/UnitTests/Foo.cs")
    assert HEUR.is_test_file("/src/Mocks/FakeClient.cs")
    assert not HEUR.is_test_file("/src/Snmp/Walker.cs")


def test_dependency_files_shade_nothing():
    out = impact.compute(
        gathered(["/Directory.Packages.props", "/src/Snmp/Snmp.csproj"]),
        COMPONENTS, NODES, EDGES, HEUR)
    assert out["changed"] == [] and out["touched"] == [] and out["test_only"] == []
    assert out["peripheral"] == []
    assert out["dependency_files_skipped"] == 2
    # dependency files never appear in the glob-gap reports either
    assert out["beyond_repo_files"] == [] and out["unmatched_files"] == []


def test_threshold_tiers_changed_vs_touched():
    out = impact.compute(
        gathered(["/src/Snmp/A.cs", "/src/Snmp/B.cs", "/src/Snmp/C.cs",
                  "/src/Core/Only.cs"]),
        COMPONENTS, NODES, EDGES, HEUR)
    assert out["changed"] == ["checkout-snmp-stack"]      # 3 prod files
    assert out["touched"] == ["checkout-core"]            # 1 prod file
    d = out["details"]["checkout-snmp-stack"]
    assert d["prodFiles"] == 3 and d["testFiles"] == 0


def test_custom_threshold():
    out = impact.compute(gathered(["/src/Snmp/A.cs"]), COMPONENTS, NODES, EDGES, HEUR,
                         changed_threshold=1)
    assert out["changed"] == ["checkout-snmp-stack"]
    assert out["touched"] == []


def test_test_files_never_shade_red():
    out = impact.compute(
        gathered(["/src/Snmp/Tests/WalkerTests.cs"]), COMPONENTS, NODES, EDGES, HEUR)
    assert out["changed"] == [] and out["touched"] == []
    assert out["test_only"] == ["checkout-snmp-stack"]
    d = out["details"]["checkout-snmp-stack"]
    assert d["prodFiles"] == 0 and d["testFiles"] == 1
    # test-only nodes do not radiate a peripheral ring
    assert out["peripheral"] == []


def test_mixed_prod_and_test_counts_prod_only_for_tier():
    out = impact.compute(
        gathered(["/src/Snmp/A.cs", "/src/Snmp/Tests/ATests.cs"]),
        COMPONENTS, NODES, EDGES, HEUR)
    assert out["touched"] == ["checkout-snmp-stack"]      # 1 prod file, tier ignores test
    d = out["details"]["checkout-snmp-stack"]
    assert d["prodFiles"] == 1 and d["testFiles"] == 1


def test_repo_nodes_excluded_and_peripheral_from_changed_only():
    out = impact.compute(
        gathered(["/src/Snmp/A.cs", "/src/Snmp/B.cs", "/src/Snmp/C.cs"]),
        COMPONENTS, NODES, EDGES, HEUR)
    # repo node matched the catch-all but never enters a tier
    assert "checkout-service" not in out["changed"] + out["touched"] + out["test_only"]
    # peripheral = 1-hop of changed via non-repo edges: checkout-core (in), checkout-wlc (out);
    # the repo 'contains' edges must not contribute
    assert out["peripheral"] == ["checkout-core", "checkout-wlc"]
    assert "checkout-service" not in out["peripheral"]


def test_touched_nodes_do_not_radiate_peripheral():
    out = impact.compute(gathered(["/src/Snmp/A.cs"]), COMPONENTS, NODES, EDGES, HEUR)
    assert out["touched"] == ["checkout-snmp-stack"]
    assert out["peripheral"] == []


def test_details_deduped_across_prs():
    extra = [{"id": 13278, "title": "P2", "repo": "Checkout.Service",
              "url": "pr-url2", "status": "completed",
              "files": ["/src/Snmp/Other.cs"]}]
    out = impact.compute(
        gathered(["/src/Snmp/Walker.cs", "/src/Snmp/B.cs"], extra_prs=extra),
        COMPONENTS, NODES, EDGES, HEUR)
    d = out["details"]["checkout-snmp-stack"]
    assert [p["id"] for p in d["prs"]] == [13277, 13278]
    assert [s["id"] for s in d["stories"]] == [43900]
    assert len([p for p in d["prs"] if p["id"] == 13277]) == 1
    assert d["prodFiles"] == 3


def test_beyond_repo_and_unmatched_reporting():
    g = gathered(["/tools/Build.ps1"])
    g["work_items"].append(
        {"id": 5, "type": "Bug", "title": "x", "url": "u",
         "prs": [{"id": 9, "title": "t", "repo": "Unknown.Repo", "url": "u",
                  "status": "completed", "files": ["/a.cs"]}]})
    out = impact.compute(g, COMPONENTS, NODES, EDGES, HEUR)
    assert "Checkout.Service:/tools/Build.ps1" in out["beyond_repo_files"]
    assert "Unknown.Repo:/a.cs" in out["unmatched_files"]


DB_NODES = NODES + [
    {"id": "checkout-db", "type": "database", "repo": "checkout-service"},
]
DB_EDGES = EDGES + [
    {"from": "checkout-snmp-stack", "to": "checkout-db", "kind": "sql"},
]
DB_COMPONENTS = COMPONENTS + [
    {"id": "checkout-db", "repo": "checkout-service", "globs": ["**/Data/**", "**/DB_*.sql"]},
]


def test_is_schema_file():
    assert HEUR.is_schema_file("/Scripts/DB_Shop.42.sql")
    assert HEUR.is_schema_file("/Shop.Domain/Migrations/20260801_Add.cs")
    assert HEUR.is_schema_file("/App/SqlFiles/create.txt")
    assert HEUR.is_schema_file("/Data/ShopModelSnapshot.cs")
    assert not HEUR.is_schema_file("/Data/DeviceRepository.cs")
    assert not HEUR.is_schema_file("/Tests/Integration/MigrationsTest.cs")


def test_database_node_ignores_non_schema_files():
    out = impact.compute(
        gathered(["/src/Data/DeviceRepository.cs", "/src/Data/Queries.cs",
                  "/src/Data/Mapper.cs"]),
        DB_COMPONENTS, DB_NODES, DB_EDGES, HEUR)
    assert "checkout-db" not in out["changed"] + out["touched"] + out["test_only"]


def test_database_node_shades_on_schema_files():
    out = impact.compute(
        gathered(["/src/Data/DB_Checkout.1.sql"]), DB_COMPONENTS, DB_NODES, DB_EDGES, HEUR)
    assert out["touched"] == ["checkout-db"]
    out = impact.compute(
        gathered(["/src/Data/DB_A.sql", "/src/Data/DB_B.sql", "/src/Data/DB_C.sql"]),
        DB_COMPONENTS, DB_NODES, DB_EDGES, HEUR)
    assert "checkout-db" in out["changed"]


def test_database_node_never_peripheral():
    out = impact.compute(
        gathered(["/src/Snmp/A.cs", "/src/Snmp/B.cs", "/src/Snmp/C.cs"]),
        DB_COMPONENTS, DB_NODES, DB_EDGES, HEUR)
    assert "checkout-snmp-stack" in out["changed"]
    assert "checkout-db" not in out["peripheral"]


def test_database_schema_test_files_dont_shade():
    out = impact.compute(
        gathered(["/Tests/Integration/MigrationsTest.cs"]),
        DB_COMPONENTS, DB_NODES, DB_EDGES, HEUR)
    assert "checkout-db" not in out["changed"] + out["touched"] + out["test_only"]


# --- release-branch diff -------------------------------------------------------

def _pr(pid, files, repo="Checkout.Service"):
    return {"id": pid, "title": f"P{pid}", "repo": repo, "url": f"pr-{pid}",
            "status": "completed", "files": list(files)}


def branch_gathered(branch_files, branch_prs, query_prs, outside_prs=(), unlinked=()):
    wis = [{"id": 1, "type": "User Story", "title": "Q", "url": "wi-1",
            "prs": list(query_prs)}]
    if outside_prs:
        wis.append({"id": 7, "type": "Bug", "title": "Out", "url": "wi-7",
                    "in_query": False, "prs": list(outside_prs)})
    return {"release": "2.0", "work_items": wis, "branch_repos": {"Checkout.Service": {
        "base": "release/1.9", "target": "release/2.0", "in_progress": False,
        "files": list(branch_files), "prs": list(branch_prs),
        "unlinked_prs": list(unlinked)}}}


def test_branch_repo_shades_from_outside_query_story():
    g = branch_gathered(
        ["/Snmp/A.cs", "/Snmp/B.cs", "/Snmp/C.cs"], [11],
        query_prs=[], outside_prs=[_pr(11, ["/Snmp/A.cs", "/Snmp/B.cs", "/Snmp/C.cs"])])
    r = impact.compute(g, COMPONENTS, NODES, EDGES, HEUR)
    assert r["changed"] == ["checkout-snmp-stack"]
    stories = r["details"]["checkout-snmp-stack"]["stories"]
    assert stories == [{"id": 7, "type": "Bug", "title": "Out",
                        "url": "wi-7", "inQuery": False}]


def test_branch_repo_pr_not_on_branch_is_reported_not_shaded():
    g = branch_gathered(["/Core/X.cs"], [10],
                        query_prs=[_pr(10, ["/Core/X.cs"]), _pr(99, ["/Snmp/A.cs"])])
    r = impact.compute(g, COMPONENTS, NODES, EDGES, HEUR)
    assert r["touched"] == ["checkout-core"]
    assert "checkout-snmp-stack" not in r["details"]
    assert [p["id"] for p in r["not_on_branch"]] == [99]
    assert "inQuery" not in r["details"]["checkout-core"]["stories"][0]


def test_branch_repo_ignores_pr_files_not_in_diff():
    # PR 10 touched Snmp/A.cs, but a later PR reverted it: not in what ships.
    g = branch_gathered(["/Core/X.cs"], [10],
                        query_prs=[_pr(10, ["/Core/X.cs", "/Snmp/A.cs"])])
    r = impact.compute(g, COMPONENTS, NODES, EDGES, HEUR)
    assert "checkout-snmp-stack" not in r["details"]


def test_branch_diff_files_without_pr_count_as_direct_commits():
    g = branch_gathered(["/Core/X.cs", "/Snmp/A.cs"], [12], query_prs=[],
                        unlinked=[_pr(12, ["/Core/X.cs"])])
    r = impact.compute(g, COMPONENTS, NODES, EDGES, HEUR)
    assert r["touched"] == ["checkout-core", "checkout-snmp-stack"]
    assert [p["id"] for p in r["details"]["checkout-core"]["prs"]] == [12]
    assert r["details"]["checkout-core"]["stories"] == []
    snmp = r["details"]["checkout-snmp-stack"]
    assert (snmp["stories"], snmp["prs"], snmp["prodFiles"]) == ([], [], 1)
    assert r["direct_files"] == ["Checkout.Service:/Snmp/A.cs"]


def test_non_branch_repo_still_uses_query_prs():
    g = branch_gathered([], [], query_prs=[_pr(20, ["/src/Portal.cs"], repo="shop-web")])
    comps = COMPONENTS + [{"id": "shop-portal", "repo": "shop-web", "globs": ["**/src/**"]}]
    r = impact.compute(g, comps, NODES, EDGES, HEUR)
    assert r["touched"] == ["shop-portal"]
    assert r["not_on_branch"] == []


def test_bulk_commit_files_are_not_credited_as_direct():
    g = branch_gathered(["/Core/X.cs", "/Snmp/A.cs"], [10], query_prs=[_pr(10, ["/Core/X.cs"])])
    g["branch_repos"]["Checkout.Service"]["bulk_commits"] = [
        {"id": "d413", "comment": "Renormalize", "files": ["/Snmp/A.cs", "/Core/X.cs"]}]
    r = impact.compute(g, COMPONENTS, NODES, EDGES, HEUR)
    assert r["touched"] == ["checkout-core"]          # PR credit survives the bulk commit
    assert "checkout-snmp-stack" not in r["details"]
    assert r["direct_files"] == []
    assert r["bulk_skipped"] == [{"repo": "Checkout.Service", "id": "d413",
                                  "comment": "Renormalize", "files": 1}]
