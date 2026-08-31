import json

import pytest

from changeatlas import mapping

COMPONENTS = [
    {"id": "poller-snmp-stack", "repo": "highlight-poller",
     "globs": ["**/Snmp/**", "**/SnmpTrap*"]},
    {"id": "poller-core", "repo": "highlight-poller", "globs": ["**/Core/**"]},
    {"id": "highlight-poller", "repo": "highlight-poller", "globs": ["**"]},
    {"id": "driver-meraki", "repo": "highlight-driver",
     "globs": ["**/Highlight.Driver.Meraki/**"]},
]


def test_normalise_repo():
    assert mapping.normalise_repo("Highlight.Poller") == "highlight-poller"
    assert mapping.normalise_repo("Highlight") == "highlight"


def test_match_file_specific_and_catchall():
    ids, beyond = mapping.match_file(COMPONENTS, "highlight-poller", "/src/Snmp/Walker.cs")
    assert set(ids) == {"poller-snmp-stack", "highlight-poller"}
    assert beyond is True


def test_match_file_catchall_only():
    ids, beyond = mapping.match_file(COMPONENTS, "highlight-poller", "/tools/Build.ps1")
    assert ids == ["highlight-poller"]
    assert beyond is False


def test_match_file_repo_scoped():
    ids, _ = mapping.match_file(COMPONENTS, "highlight-driver", "/Snmp/x.cs")
    assert ids == []  # driver repo has no snmp component and no catch-all here


def test_match_file_case_insensitive_and_root_level():
    ids, _ = mapping.match_file(COMPONENTS, "highlight-poller", "SNMP/walker.CS")
    assert "poller-snmp-stack" in ids


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
        {"id": "poller-snmp-stack", "type": "subsystem", "repo": "highlight-poller"},
        {"id": "poller-core", "type": "subsystem", "repo": "highlight-poller"},
        {"id": "highlight-poller", "type": "repo", "repo": "highlight-poller"},
        {"id": "driver-meraki", "type": "driver", "repo": "highlight-driver"},
        {"id": "poller-wlc", "type": "subsystem", "repo": "highlight-poller"},  # unmapped
        {"id": "messenger-datadog", "type": "external", "repo": "highlight-messenger"},
    ]
    errors, warnings = mapping.check_map(COMPONENTS, nodes)
    assert errors == []
    assert any("poller-wlc" in w for w in warnings)
    assert not any("messenger-datadog" in w for w in warnings)

    errors, _ = mapping.check_map(
        COMPONENTS + [{"id": "ghost", "repo": "highlight-poller", "globs": ["**"]}], nodes)
    assert any("ghost" in e for e in errors)
