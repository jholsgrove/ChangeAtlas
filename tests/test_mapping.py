import json

import pytest

from changeatlas import mapping

COMPONENTS = [
    {"id": "web-auth-stack", "repo": "shop-web",
     "globs": ["**/Auth/**", "**/AuthTrap*"]},
    {"id": "web-core", "repo": "shop-web", "globs": ["**/API/**"]},
    {"id": "shop-web", "repo": "shop-web", "globs": ["**"]},
    {"id": "pricing-provider", "repo": "pricing-engine",
     "globs": ["**/Pricing.Engine.Provider/**"]},
]


def test_normalise_repo():
    assert mapping.normalise_repo("Shop.Web") == "shop-web"
    assert mapping.normalise_repo("Shop") == "shop"


def test_match_file_specific_and_catchall():
    ids, beyond = mapping.match_file(COMPONENTS, "shop-web", "/src/Auth/Walker.cs")
    assert set(ids) == {"web-auth-stack", "shop-web"}
    assert beyond is True


def test_match_file_catchall_only():
    ids, beyond = mapping.match_file(COMPONENTS, "shop-web", "/tools/Build.ps1")
    assert ids == ["shop-web"]
    assert beyond is False


def test_match_file_repo_scoped():
    ids, _ = mapping.match_file(COMPONENTS, "pricing-engine", "/Auth/x.cs")
    assert ids == []  # pricing-engine repo has no auth component and no catch-all here


def test_match_file_case_insensitive_and_root_level():
    ids, _ = mapping.match_file(COMPONENTS, "shop-web", "AUTH/walker.CS")
    assert "web-auth-stack" in ids


def test_load_map_valid(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"components": COMPONENTS}), encoding="utf-8")
    assert mapping.load_map(p) == COMPONENTS


def test_load_map_reports_all_errors(tmp_path):
    bad = {"components": [
        {"id": "a", "repo": "r", "globs": []},              # empty globs
        {"id": "a", "repo": "r", "globs": ["**"]},          # duplicate id
        {"repo": "r", "globs": ["**"]},                     # missing id
        {"id": "b", "repo": "r", "globs": ["src/*"]},       # glob must start with **
    ]}
    p = tmp_path / "m.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        mapping.load_map(p)
    msg = str(exc.value)
    assert "empty globs" in msg and "duplicate id" in msg
    assert "missing id" in msg and "must start with '**'" in msg


def test_check_map():
    nodes = [
        {"id": "web-auth-stack", "type": "subsystem", "repo": "shop-web"},
        {"id": "web-core", "type": "subsystem", "repo": "shop-web"},
        {"id": "shop-web", "type": "repo", "repo": "shop-web"},
        {"id": "pricing-provider", "type": "driver", "repo": "pricing-engine"},
        {"id": "web-cache", "type": "subsystem", "repo": "shop-web"},  # unmapped
        {"id": "notification-datadog", "type": "external", "repo": "notification-service"},
    ]
    errors, warnings = mapping.check_map(COMPONENTS, nodes)
    assert errors == []
    assert any("web-cache" in w for w in warnings)
    assert not any("notification-datadog" in w for w in warnings)

    errors, _ = mapping.check_map(
        COMPONENTS + [{"id": "ghost", "repo": "shop-web", "globs": ["**"]}], nodes)
    assert any("ghost" in e for e in errors)
