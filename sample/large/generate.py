"""generate.py — writes the fictional 100-repo sample (sample/large/).

Run:  python sample/large/generate.py

It is the ONLY writer of graph-data.json, component-globs.json,
release-1.0-data.json and expected-tiers.json in this directory. Output is
deterministic (fixed seed) so tests/test_sample_large.py can regenerate into
a temp dir and diff against the checked-in files.

The world: a retail platform, 20 product domains x 5 repo roles = 100 repos,
8-20 components each. One release (1.0) lands in six repos and is designed
to exercise every tier rule:
  * 3+ prod files                      -> changed
  * 1 prod file                        -> touched
  * test file only                     -> test-only
  * database + .sql migration          -> touched   (Checkout.Api's database)
  * database + data-access edits only  -> untouched (Identity.Api's database)
  * packages.lock.json                 -> ignored   (Notifications.Worker PR)
  * a changed contract in Inventory.Contracts spreads peripheral into
    Inventory.Api and Fulfilment.Worker, which have no PRs of their own.
"""
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEED = 20260902
TRACKER = "https://tracker.example"

DOMAINS = ["Billing", "Catalog", "Checkout", "Identity", "Inventory", "Shipping",
           "Payments", "Notifications", "Search", "Reporting", "Analytics", "Pricing",
           "Promotions", "Reviews", "Support", "Fulfilment", "Returns", "Tax", "Fraud",
           "Loyalty"]
# Role -> member types, assigned round-robin so every repo's composition is
# a function of its member count only.
ROLES = {
    "Api": ["service", "project", "database", "contract", "subsystem", "feature"],
    "Web": ["feature", "project", "subsystem", "service", "feature"],
    "Worker": ["subsystem", "project", "messaging", "database", "driver", "service"],
    "Gateway": ["service", "contract", "driver", "project", "driver"],
    "Contracts": ["contract", "project", "messaging", "contract"],
}
# Names must not contain "test", "spec" or "mock": the generic heuristics
# preset's test markers match substrings of path segments.
NAMES = {
    "subsystem": ["Core", "Orchestration", "Admin Console", "Rules Engine", "Sync",
                  "Import Pipeline"],
    "project": ["Domain Model", "Data Access", "Common", "Validation", "Mappers",
                "Client Sdk"],
    "service": ["Public API", "Internal API", "Scheduler", "Webhook Receiver",
                "Health Endpoint"],
    "contract": ["Events Schema", "REST Contract", "Message Contracts", "Query Contract"],
    "feature": ["Dashboard", "Bulk Edit", "Export", "Audit Trail", "Onboarding Flow",
                "Settings"],
    "database": ["Database", "Read Model", "Archive Store"],
    "messaging": ["Events Topic", "Command Queue", "Dead-letter Queue"],
    "driver": ["Connector", "Adapter", "Sync Client"],
}
TYPE_LABEL = {"repo": "Repository", "subsystem": "Subsystem", "project": "Project",
              "service": "Service", "contract": "Contract", "driver": "Driver",
              "database": "Database", "messaging": "Messaging", "feature": "Feature",
              "external": "External system"}
EXTERNALS = ["Stripe", "SendGrid", "Datadog", "Azure Storage", "Azure Key Vault",
             "Auth0", "Twilio", "Elasticsearch", "Redis Cache", "Salesforce",
             "Google Maps", "Slack", "PagerDuty", "Segment", "Zendesk"]
CROSS = [("platform-event-bus", "Platform Event Bus"),
         ("audit-log-stream", "Audit Log Stream")]
FORBIDDEN = ("test", "spec", "mock")


def slug(s):
    return s.lower().replace(".", "-").replace(" ", "-")


def first_of_type(repos, by_id, key, t):
    for m in repos[key]:
        if by_id[m]["type"] == t:
            return m
    raise AssertionError(f"{key} has no {t} member")


def build_graph(rng):
    """Return (nodes, edges, repos, segments): repos maps repo key -> ordered
    member ids; segments maps member id -> its src/<segment>/ folder name."""
    nodes, edges, repos, segments = [], [], {}, {}
    for ext in EXTERNALS:
        nodes.append({"id": f"ext-{slug(ext)}", "title": ext, "type": "external",
                      "repo": "external",
                      "summary": f"{ext}: third-party service outside our repos.",
                      "tags": ["external"]})
    for cid, ctitle in CROSS:
        nodes.append({"id": cid, "title": ctitle, "type": "messaging", "repo": "cross",
                      "summary": f"{ctitle}: shared topic consumed across repos.",
                      "tags": ["cross", "messaging"]})
    by_id = {n["id"]: n for n in nodes}
    for dom in DOMAINS:
        for role, types in ROLES.items():
            title = f"{dom}.{role}"
            key = slug(title)
            repo_node = {"id": key, "title": title, "type": "repo", "repo": key,
                         "summary": f"Repository {title}: the {dom.lower()} domain's "
                                    f"{role.lower()} code.",
                         "tags": [key, "repo"]}
            nodes.append(repo_node)
            by_id[key] = repo_node
            count = rng.randint(8, 20)
            members, seen_types = [], {}
            for i in range(count):
                t = types[i % len(types)]
                k = seen_types.get(t, 0)
                seen_types[t] = k + 1
                pool = NAMES[t]
                name = pool[k % len(pool)]
                if k >= len(pool):
                    name = f"{name} {k // len(pool) + 1}"
                seg = slug(name)
                assert not any(f in seg for f in FORBIDDEN), seg
                mid = f"{key}-{i}"
                node = {"id": mid, "title": f"{dom} {name}", "type": t, "repo": key,
                        "summary": f"{TYPE_LABEL[t]} in {title}, under src/{seg}/.",
                        "tags": [key, t]}
                nodes.append(node)
                by_id[mid] = node
                segments[mid] = seg
                members.append(mid)
                edges.append({"from": key, "to": mid, "kind": "contains"})
            repos[key] = members
            # Internal wiring: a spanning tree plus a few extra 'uses' edges.
            for i in range(1, len(members)):
                to = members[rng.randrange(i)]
                tt = by_id[to]["type"]
                kind = "sql" if tt == "database" else "bus" if tt == "messaging" else "project-ref"
                edges.append({"from": members[i], "to": to, "kind": kind})
            for _ in range(len(members) // 3):
                a, b = rng.choice(members), rng.choice(members)
                if a != b:
                    edges.append({"from": a, "to": b, "kind": "uses"})
            for mid in members:
                if by_id[mid]["type"] == "driver":
                    edges.append({"from": mid, "to": f"ext-{slug(rng.choice(EXTERNALS))}",
                                  "kind": "http"})
                if by_id[mid]["type"] == "messaging" and rng.random() < 0.3:
                    edges.append({"from": mid, "to": rng.choice(CROSS)[0], "kind": "bus"})
    # Cross-repo dependencies: mostly within a domain, some across.
    keys = list(repos)
    for key in keys:
        dom = key.split("-")[0]
        same = [k for k in keys if k != key and k.startswith(dom + "-")]
        for _ in range(rng.randint(1, 3)):
            target = rng.choice(same) if same and rng.random() < 0.6 else rng.choice(keys)
            if target == key:
                continue
            src = [m for m in repos[key]
                   if by_id[m]["type"] in ("service", "project", "subsystem", "feature")]
            dst = [m for m in repos[target]
                   if by_id[m]["type"] in ("service", "contract", "messaging")]
            if not src or not dst:
                continue
            a, b = rng.choice(src), rng.choice(dst)
            kind = {"messaging": "bus", "contract": "nuget"}.get(by_id[b]["type"], "http")
            edges.append({"from": a, "to": b, "kind": kind})
    # Designed cross-repo spread: two repos with no PRs consume the contract
    # that the release changes (see build_release).
    contract = first_of_type(repos, by_id, "inventory-contracts", "contract")
    edges.append({"from": first_of_type(repos, by_id, "inventory-api", "service"),
                  "to": contract, "kind": "nuget"})
    edges.append({"from": first_of_type(repos, by_id, "fulfilment-worker", "subsystem"),
                  "to": contract, "kind": "nuget"})
    dedupe_titles(nodes)
    return nodes, edges, repos, segments


def dedupe_titles(nodes):
    """Same title in two repos of one domain -> append each repo's role."""
    by_title = {}
    for n in nodes:
        by_title.setdefault(n["title"], []).append(n)
    for group in by_title.values():
        if len(group) > 1 and all(n["type"] != "repo" for n in group):
            for n in group:
                role = n["repo"].split("-", 1)[-1].capitalize()
                n["title"] = f"{n['title']} ({role})"


def build_globs(nodes, segments):
    comps = []
    for n in nodes:
        if n["type"] == "repo":
            comps.append({"id": n["id"], "repo": n["repo"], "globs": ["**"]})
        elif n["id"] in segments:
            seg = segments[n["id"]]
            comps.append({"id": n["id"], "repo": n["repo"],
                          "globs": [f"**/src/{seg}/**", f"**/tests/{seg}/**"]})
        elif n["repo"] == "cross":
            # Owned by no repo: an entry keeps --check-map clean, and no PR
            # ever reports the repo "cross", so it can never match a file.
            comps.append({"id": n["id"], "repo": "cross", "globs": [f"**/{n['id']}/**"]})
    return {"components": comps}


def build_release(nodes, repos, segments):
    """Hand-designed release: returns (release_data, expected_tiers)."""
    by_id = {n["id"]: n for n in nodes}
    changed, touched, test_only, periph, untouched_db = [], [], [], [], []
    stories = []
    counter = {"pr": 500, "story": 41200}

    def pr(key, title, files):
        counter["pr"] += 1
        return {"id": counter["pr"], "title": title, "repo": by_id[key]["title"],
                "url": f"{TRACKER}/{key}/pullrequest/{counter['pr']}",
                "status": "completed", "files": files}

    def story(title, prs, kind="User Story"):
        counter["story"] += 1
        stories.append({"id": counter["story"], "type": kind, "title": title,
                        "url": f"{TRACKER}/workitems/{counter['story']}", "prs": prs})

    def prod(m, n):
        return [f"/src/{segments[m]}/{cls}.cs" for cls in
                ("Handler", "Validator", "Mapper", "Options", "Extensions")[:n]]

    def test(m):
        return [f"/tests/{segments[m]}/HandlerTests.cs"]

    # Checkout.Api: 4 changed, 1 touched, 1 test-only, database via migration.
    k = "checkout-api"
    non_db = [m for m in repos[k] if by_id[m]["type"] != "database"]
    db = first_of_type(repos, by_id, k, "database")
    changed += non_db[:4]
    touched += [non_db[4], db]
    test_only.append(non_db[5])
    story("Express checkout for returning customers", [
        pr(k, "Express checkout endpoint and validation",
           prod(non_db[0], 3) + prod(non_db[1], 3)),
        pr(k, "Order totals recalculation", prod(non_db[2], 3)),
    ])
    story("Checkout database: index on order lookups", [
        pr(k, "Add order lookup index",
           [f"/src/{segments[db]}/migrations/0042_order_lookup_index.sql"]),
    ])
    story("Checkout API hardening", [
        pr(k, "Harden request handling", prod(non_db[3], 3) + prod(non_db[4], 1)),
        pr(k, "Regression tests for totals", test(non_db[5])),
    ], kind="Bug")

    # Checkout.Web: 3 changed, 2 touched.
    k = "checkout-web"
    ms = repos[k]
    changed += ms[:3]
    touched += ms[3:5]
    story("Express checkout UI", [
        pr(k, "Express checkout screens", prod(ms[0], 3) + prod(ms[1], 3)),
        pr(k, "Order summary polish", prod(ms[2], 3) + prod(ms[3], 1)),
    ])
    story("Checkout accessibility fixes",
          [pr(k, "Focus order on payment step", prod(ms[4], 1))], kind="Bug")

    # Payments.Gateway: 3 changed, 1 touched, 1 test-only.
    k = "payments-gateway"
    ms = repos[k]
    changed += ms[:3]
    touched.append(ms[3])
    test_only.append(ms[4])
    story("Support wallet payments", [
        pr(k, "Wallet payment adapter", prod(ms[0], 3) + prod(ms[1], 3)),
        pr(k, "Gateway routing for wallets", prod(ms[2], 3) + prod(ms[3], 1)),
        pr(k, "Contract tests for wallet flows", test(ms[4])),
    ])

    # Identity.Api: 2 changed, 2 touched; database gets data-access edits only.
    k = "identity-api"
    non_db = [m for m in repos[k] if by_id[m]["type"] != "database"]
    db = first_of_type(repos, by_id, k, "database")
    changed += non_db[:2]
    touched += non_db[2:4]
    untouched_db.append(db)
    story("Passkey sign-in", [
        pr(k, "Passkey registration and login", prod(non_db[0], 3) + prod(non_db[1], 3)),
        pr(k, "Session claims for passkeys", prod(non_db[2], 1) + prod(non_db[3], 1)),
        pr(k, "Repository query tidy-up",
           [f"/src/{segments[db]}/UserRepository.cs"]),   # data access, not schema
    ])

    # Notifications.Worker: 1 changed, 1 touched, manifest bump ignored.
    k = "notifications-worker"
    ms = repos[k]
    changed.append(ms[0])
    touched.append(ms[1])
    story("Checkout confirmation emails", [
        pr(k, "Confirmation email template and sender",
           prod(ms[0], 3) + prod(ms[1], 1) + ["/packages.lock.json"]),
    ])

    # Inventory.Contracts: 1 changed contract -> peripheral spread.
    k = "inventory-contracts"
    contract = first_of_type(repos, by_id, k, "contract")
    changed.append(contract)
    periph += [first_of_type(repos, by_id, "inventory-api", "service"),
               first_of_type(repos, by_id, "fulfilment-worker", "subsystem")]
    story("Reserve stock at express checkout", [
        pr(k, "Add reservation fields to stock contract", prod(contract, 3)),
    ])

    # Work items with no code change.
    story("Release notes for 1.0", [], kind="Task")
    story("Runbook update: wallet payments", [], kind="Task")

    release = {"release": "1.0", "query": "release-1.0",
               "fetched_at": "2026-09-02T09:00:00Z", "skipped": [], "work_items": stories}
    expected = {"changed": sorted(changed), "touched": sorted(touched),
                "testOnly": sorted(test_only), "peripheralIncludes": sorted(periph),
                "untouchedDatabases": sorted(untouched_db)}
    return release, expected


def write_all(out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    nodes, edges, repos, segments = build_graph(rng)
    globs = build_globs(nodes, segments)
    release, expected = build_release(nodes, repos, segments)
    dump(out_dir / "graph-data.json", {"nodes": nodes, "edges": edges})
    dump(out_dir / "component-globs.json", globs)
    dump(out_dir / "release-1.0-data.json", release)
    dump(out_dir / "expected-tiers.json", expected)
    return expected


def dump(path, obj):
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    exp = write_all(HERE)
    print(f"wrote {HERE}: {len(exp['changed'])} changed, {len(exp['touched'])} touched, "
          f"{len(exp['testOnly'])} test-only designed")
