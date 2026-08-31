"""mapping.py — component glob map: (repo, changed path) -> graph node ids."""
import fnmatch
import json
from pathlib import Path

CATCH_ALL = "**"


def normalise_repo(name: str) -> str:
    """ADO repo name -> graph-data repo key: lowercase, '.' -> '-'."""
    return name.lower().replace(".", "-")


def load_map(path) -> list:
    """Load and validate config/component-globs.json; raise ValueError on any problem."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    components = data.get("components")
    errors = []
    if not isinstance(components, list):
        raise ValueError(f"{path}: 'components' must be a list")
    seen = set()
    for i, c in enumerate(components):
        label = c.get("id") or f"components[{i}]"
        if not c.get("id"):
            errors.append(f"{label}: missing id")
        elif c["id"] in seen:
            errors.append(f"{c['id']}: duplicate id")
        else:
            seen.add(c["id"])
        if not c.get("repo"):
            errors.append(f"{label}: missing repo")
        globs = c.get("globs")
        if not globs:
            errors.append(f"{label}: empty globs")
        else:
            for g in globs:
                if not g.startswith("**"):
                    errors.append(f"{label}: glob {g!r} must start with '**'")
    if errors:
        raise ValueError(f"{path}: invalid component map:\n  " + "\n  ".join(errors))
    return components


def check_map(components: list, nodes: list) -> tuple:
    """(errors, warnings) reconciling the map against graph-data nodes."""
    node_ids = {n["id"] for n in nodes}
    errors = [f"map id {c['id']!r} does not exist in graph-data.json"
              for c in components if c["id"] not in node_ids]
    mapped = {c["id"] for c in components}
    warnings = [
        f"node {n['id']!r} ({n['type']}) has no map entry — its changes will "
        "only shade the repo node"
        for n in nodes
        if n["type"] not in ("external", "repo") and n["id"] not in mapped
    ]
    return errors, warnings


def _glob_matches(glob: str, path_lower: str) -> bool:
    # fnmatch '*' crosses '/', so '**' -> '*' gives the intended semantics.
    return fnmatch.fnmatchcase(path_lower, glob.lower().replace("**", "*"))


def match_file(components: list, repo_key: str, path: str) -> tuple:
    """(matched node ids, beyond_repo). beyond_repo: a non-catch-all glob hit."""
    path_lower = "/" + path.lower().lstrip("/")
    ids, beyond = [], False
    for c in components:
        if c["repo"] != repo_key:
            continue
        for g in c["globs"]:
            if _glob_matches(g, path_lower):
                ids.append(c["id"])
                if g != CATCH_ALL:
                    beyond = True
                break
    return ids, beyond
