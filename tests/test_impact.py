from pathlib import Path
from changeatlas import impact, heuristics

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
