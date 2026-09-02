from pathlib import Path

import pytest

from changeatlas import heuristics

BASE = Path(__file__).resolve().parent.parent

def _dotnet():
    return heuristics.load("dotnet", BASE)

def test_dotnet_dependency_files():
    h = _dotnet()
    assert h.is_dependency_file("/src/Shop.Web/Shop.Web.csproj")
    assert h.is_dependency_file("/Directory.Packages.props")
    assert not h.is_dependency_file("/src/Shop.Web/Checkout.cs")

def test_dotnet_schema_evidence():
    h = _dotnet()
    assert h.is_schema_file("/src/Orders/Migrations/202608_AddCol.cs")
    assert h.is_schema_file("/db/patch.sql")
    assert h.is_schema_file("/src/Orders/Data/OrdersModelSnapshot.cs")
    assert not h.is_schema_file("/src/Orders.Tests/Migrations/MigrationsTest.cs")
    assert not h.is_schema_file("/src/Orders/OrderService.cs")

def test_generic_lockfiles_are_dependencies():
    h = heuristics.load("generic", BASE)
    for f in ("/package-lock.json", "/app/yarn.lock", "/poetry.lock",
              "/Cargo.lock", "/go.sum", "/pnpm-lock.yaml"):
        assert h.is_dependency_file(f), f

def test_test_markers():
    h = heuristics.load("generic", BASE)
    assert h.is_test_file("/src/tests/order_test.py")
    assert h.is_test_file("/src/Mocks/FakeGateway.cs")
    # Preserves ImpactMapper behaviour: substring-within-segment semantics
    assert h.is_test_file("/src/attestation/sign.py")

def test_load_by_explicit_path(tmp_path):
    p = tmp_path / "custom.json"
    p.write_text('{"dependency_basenames":["deps.lock"],"dependency_suffixes":[],'
                 '"test_markers":["spec"],"schema_suffixes":[".ddl"],'
                 '"schema_segments":[],"schema_basename_contains":[]}', encoding="utf-8")
    h = heuristics.load(str(p), BASE)
    assert h.is_dependency_file("/x/deps.lock")
    assert h.is_test_file("/x/spec_helpers/a.py") and h.is_schema_file("/x/a.ddl")

def test_bad_preset_raises():
    with pytest.raises(ValueError):
        heuristics.load("nonexistent-preset", BASE)
