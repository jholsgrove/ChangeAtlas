"""anonymize.py — demo-safe anonymization: generic node/story/PR names, dead
links on reserved .example TLD, topology/types/tiers/change-sizes preserved."""
import string

from . import mapping

_GENERIC_SUMMARY = ("Sample {label} node — illustrative placeholder only. "
                    "Belongs to {home}; connects to related components in the map.")

# ADO-shaped demo URLs on the RFC 2606-reserved .example TLD: they read as
# real links on hover but can never resolve to (or leak) a real organisation.
_FAKE_ORG = "https://dev.azure.example/demo-org/Platform"


def anonymize_payload(payload: dict) -> dict:
    nodes = payload["nodes"]
    edges = payload["edges"]
    type_style = payload["typeStyle"]

    letters = iter(string.ascii_uppercase)
    repo_map: dict[str, str] = {}
    for n in nodes:
        r = n.get("repo") or ""
        if r and r not in repo_map:
            repo_map[r] = "Shared" if r == "cross" else f"Repo {next(letters)}"

    id_map = {n["id"]: f"n{i + 1}" for i, n in enumerate(nodes)}
    label_of = lambda t: type_style.get(t, {}).get("label", t.title())

    counters: dict[str, int] = {}
    new_nodes = []
    for n in nodes:
        label = label_of(n["type"])
        if n["type"] == "repo":
            title = repo_map.get(n.get("repo", ""), "Repo ?")
        else:
            counters[n["type"]] = counters.get(n["type"], 0) + 1
            title = f"{label} {counters[n['type']]}"
        repo = repo_map.get(n.get("repo", ""), "")
        new_nodes.append({
            "id": id_map[n["id"]], "title": title, "type": n["type"], "repo": repo,
            "summary": _GENERIC_SUMMARY.format(label=label.lower(),
                                               home=repo or "the platform"),
            "tags": [n["type"]],
        })

    new_edges = [{"from": id_map[e["from"]], "to": id_map[e["to"]],
                  "kind": e["kind"]} for e in edges]

    story_map: dict[int, int] = {}
    pr_map: dict[int, int] = {}
    new_details = {}
    for nid, d in payload.get("details", {}).items():
        stories = []
        for s in d.get("stories", []):
            fake = story_map.setdefault(s["id"], len(story_map) + 1)
            stories.append({"id": fake, "type": s.get("type", ""),
                            "title": f"{s.get('type') or 'Work item'} {fake}",
                            "url": f"{_FAKE_ORG}/_workitems/edit/{fake}"})
        prs = []
        for p in d.get("prs", []):
            fake = pr_map.setdefault(p["id"], len(pr_map) + 1)
            repo_key = mapping.normalise_repo(p.get("repo", ""))
            repo_label = repo_map.get(repo_key, "Other repo")
            slug = repo_label.lower().replace(" ", "-")
            prs.append({"id": fake, "title": f"Pull request {fake}",
                        "repo": repo_label,
                        "url": f"{_FAKE_ORG}/_git/{slug}/pullrequest/{fake}"})
        new_details[id_map[nid]] = {"stories": stories, "prs": prs,
                                    "prodFiles": d.get("prodFiles", 0),
                                    "testFiles": d.get("testFiles", 0)}

    return {
        "release": payload["release"],
        "generated": payload["generated"],
        "nodes": new_nodes,
        "edges": new_edges,
        "typeStyle": type_style,
        "edgeLabel": payload["edgeLabel"],
        "impact": {k: [id_map[i] for i in v]
                   for k, v in payload["impact"].items()},
        "details": new_details,
    }
