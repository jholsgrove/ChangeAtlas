import json

from changeatlas import anonymize

PAYLOAD = {
    "release": "26.8", "generated": "2026-08-28",
    "nodes": [
        {"id": "auth-microservice", "title": "Authentication Service", "type": "subsystem",
         "repo": "service-core", "summary": "Handles user authentication and session management.", "tags": ["x"]},
        {"id": "service-core", "title": "Core Service", "type": "repo",
         "repo": "service-core", "summary": "Core service infrastructure.", "tags": []},
        {"id": "shop-checkout", "title": "Checkout Flow", "type": "service",
         "repo": "shop-web", "summary": "Shopping and checkout platform.", "tags": []},
        {"id": "message-bus", "title": "Message Bus", "type": "messaging",
         "repo": "cross", "summary": "Message distribution layer.", "tags": []},
    ],
    "edges": [
        {"from": "service-core", "to": "auth-microservice", "kind": "contains",
         "note": "internal dependency"},
        {"from": "shop-checkout", "to": "message-bus", "kind": "bus"},
    ],
    "typeStyle": {"subsystem": {"label": "Subsystem", "color": "#4a9eea"},
                  "repo": {"label": "Repo", "color": "#e0533d"},
                  "service": {"label": "Service", "color": "#2db37c"},
                  "messaging": {"label": "Messaging", "color": "#e6c34a"}},
    "edgeLabel": {"contains": "contains", "bus": "publishes"},
    "impact": {"changed": ["auth-microservice"], "touched": ["shop-checkout"],
               "testOnly": [], "peripheral": ["message-bus"]},
    "details": {
        "auth-microservice": {
            "stories": [{"id": 43900, "type": "User Story",
                         "title": "Login flow improvement", "url": "https://dev.azure.com/x"}],
            "prs": [{"id": 13277, "title": "Refactor auth handler", "repo": "Core Service",
                     "url": "https://dev.azure.com/x/pr"}],
            "prodFiles": 3, "testFiles": 1},
        "shop-checkout": {
            "stories": [{"id": 43900, "type": "User Story",
                         "title": "Login flow improvement", "url": "https://dev.azure.com/x"}],
            "prs": [{"id": 13299, "title": "Update checkout UI", "repo": "Shop Web",
                     "url": "https://dev.azure.com/x/pr2"}],
            "prodFiles": 1, "testFiles": 0},
    },
}

SECRETS = ["auth-microservice", "Authentication Service", "Handles user authentication",
           "Core Service", "Checkout Flow", "Login flow improvement",
           "Refactor auth handler", "Update checkout UI", "dev.azure.com", "43900", "13277",
           "internal dependency", "service-core"]


def test_no_original_identifiers_survive():
    out = anonymize.anonymize_payload(json.loads(json.dumps(PAYLOAD)))
    blob = json.dumps(out)
    for s in SECRETS:
        assert s not in blob, s


def test_topology_and_tiers_preserved():
    out = anonymize.anonymize_payload(json.loads(json.dumps(PAYLOAD)))
    assert len(out["nodes"]) == 4 and len(out["edges"]) == 2
    assert len(out["impact"]["changed"]) == 1
    assert len(out["impact"]["touched"]) == 1
    assert len(out["impact"]["peripheral"]) == 1
    node_ids = {n["id"] for n in out["nodes"]}
    for e in out["edges"]:
        assert e["from"] in node_ids and e["to"] in node_ids
        assert "note" not in e
    for lst in out["impact"].values():
        assert set(lst) <= node_ids
    assert set(out["details"]) <= node_ids


def test_details_anonymised_but_counts_kept():
    out = anonymize.anonymize_payload(json.loads(json.dumps(PAYLOAD)))
    changed_id = out["impact"]["changed"][0]
    d = out["details"][changed_id]
    assert d["prodFiles"] == 3 and d["testFiles"] == 1
    assert d["stories"][0]["type"] == "User Story"
    # same story referenced from two nodes keeps one consistent fake identity
    other_id = out["impact"]["touched"][0]
    assert out["details"][other_id]["stories"][0]["id"] == d["stories"][0]["id"]


def test_fake_urls_look_real_but_use_reserved_domain():
    out = anonymize.anonymize_payload(json.loads(json.dumps(PAYLOAD)))
    changed_id = out["impact"]["changed"][0]
    d = out["details"][changed_id]
    s, p = d["stories"][0], d["prs"][0]
    assert s["url"] == f"https://dev.azure.example/demo-org/Platform/_workitems/edit/{s['id']}"
    slug = p["repo"].lower().replace(" ", "-")   # "Repo A" -> "repo-a"
    assert p["url"] == (f"https://dev.azure.example/demo-org/Platform/_git/{slug}"
                        f"/pullrequest/{p['id']}")
    # ADO-shaped, but never the real domain
    assert "dev.azure.com" not in s["url"] + p["url"]


def test_node_titles_generic_and_repo_labels_mapped():
    out = anonymize.anonymize_payload(json.loads(json.dumps(PAYLOAD)))
    titles = [n["title"] for n in out["nodes"]]
    assert any(t.startswith("Repo ") for t in titles)        # repo node
    assert any(t.startswith("Subsystem ") for t in titles)
    repos = {n["repo"] for n in out["nodes"]}
    assert all(r.startswith("Repo ") or r == "Shared" for r in repos)
