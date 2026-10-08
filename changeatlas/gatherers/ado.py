"""ado.py — Azure DevOps REST gatherer. All I/O behind injected `fetch(url)->dict`."""
import base64
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone

TOKEN_ENV = "CHANGEATLAS_TOKEN"
_API = "api-version=7.1"
_TIMEOUT_SECS = 120
_BATCH = 200


class TokenMissingError(RuntimeError):
    pass


class AdoHttpError(RuntimeError):
    def __init__(self, status: int, url: str):
        super().__init__(f"HTTP {status} from {url}")
        self.status, self.url = status, url


class AdoConnectionError(RuntimeError):
    """DNS failure, connection refused, timeout, or a non-JSON response body.
    Carries the url and a reason string; never the token (the token only
    ever appears in the Authorization header, never in the url or in any
    exception message built here)."""
    def __init__(self, url: str, reason: str):
        super().__init__(f"could not reach {url}: {reason}")
        self.url, self.reason = url, reason


def default_fetch(url: str) -> dict:
    token = os.environ.get(TOKEN_ENV)
    if not token:
        raise TokenMissingError(TOKEN_ENV)
    auth = base64.b64encode(f":{token}".encode()).decode()
    req = urllib.request.Request(
        url, headers={"Authorization": f"Basic {auth}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECS) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        raise AdoHttpError(exc.code, url) from exc
    except urllib.error.URLError as exc:
        # DNS failure, connection refused, timeout, etc. -- HTTPError (a
        # URLError subclass) is caught above first, so this is the
        # never-got-a-response case.
        raise AdoConnectionError(url, str(exc.reason)) from exc
    except json.JSONDecodeError as exc:
        raise AdoConnectionError(url, f"invalid JSON response ({exc})") from exc


_PR_ARTIFACT_PREFIX = "vstfs:///Git/PullRequestId/"


def parse_artifact_url(url: str):
    from urllib.parse import unquote
    if not url.startswith(_PR_ARTIFACT_PREFIX):
        return None
    parts = unquote(url[len(_PR_ARTIFACT_PREFIX):]).split("/")
    if len(parts) != 3:
        return None
    proj_guid, repo_guid, pr_id = parts
    try:
        return proj_guid.lower(), repo_guid.lower(), int(pr_id)
    except ValueError:
        return None


def query_work_items(fetch, org: str, project: str, query_id: str) -> list:
    wiql = fetch(f"{org}/{project}/_apis/wit/wiql/{query_id}?{_API}")
    if "workItemRelations" in wiql:
        seen, ids = set(), []
        for rel in wiql["workItemRelations"]:
            wid = (rel.get("target") or {}).get("id")
            if wid is not None and wid not in seen:
                seen.add(wid)
                ids.append(wid)
    else:
        ids = [wi["id"] for wi in wiql.get("workItems", [])]
    return work_item_records(fetch, org, project, ids)


def work_item_records(fetch, org: str, project: str, ids: list) -> list:
    items = []
    for i in range(0, len(ids), _BATCH):
        chunk = ids[i:i + _BATCH]
        batch = fetch(f"{org}/_apis/wit/workitems?ids={','.join(map(str, chunk))}"
                      f"&fields=System.Title,System.WorkItemType&{_API}")
        for wi in batch.get("value", []):
            fields = wi.get("fields") or {}
            items.append({"id": wi["id"],
                          "type": fields.get("System.WorkItemType", ""),
                          "title": fields.get("System.Title", ""),
                          "url": f"{org}/{project}/_workitems/edit/{wi['id']}"})
    return items


def work_item_pr_ids(fetch, org: str, work_item_id: int) -> list:
    data = fetch(f"{org}/_apis/wit/workitems/{work_item_id}?$expand=relations&{_API}")
    seen, pairs = set(), []
    for rel in data.get("relations") or []:
        if rel.get("rel") != "ArtifactLink":
            continue
        parsed = parse_artifact_url(rel.get("url", ""))
        if not parsed:
            continue
        _, repo_guid, pr_id = parsed
        if (repo_guid, pr_id) not in seen:
            seen.add((repo_guid, pr_id))
            pairs.append((repo_guid, pr_id))
    return pairs


def repositories(fetch, org: str, project: str) -> dict:
    """repo guid (lowercase) -> {"name", "default_branch"} for enabled repos."""
    data = fetch(f"{org}/{project}/_apis/git/repositories?{_API}")
    return {r["id"].lower(): {"name": r["name"],
                              "default_branch": r.get("defaultBranch", "")
                              .removeprefix("refs/heads/") or "master"}
            for r in data.get("value", []) if not r.get("isDisabled")}


def repo_names(fetch, org: str, project: str) -> dict:
    return {g: r["name"] for g, r in repositories(fetch, org, project).items()}


# --- release-branch diff -----------------------------------------------------
# Repos that cut release/<version> branches ship exactly the diff between the
# previous release branch and this one; that diff is the truth for what ships.
# Old release branches get deleted, so a v<version> tag stands in for one.

_VERSION_RE = re.compile(r"^\d+(\.\d+)*$")
_MERGE_PR_RE = re.compile(r"^(?:Merged PR|Merge pull request) (\d+)")
_PAGE = 1000
# A direct (non-PR) commit this large is mechanical — a line-ending renormalize,
# a mass reformat — and must not shade every component it brushes.
_BULK_FILES = 500


def _version_key(label: str):
    return tuple(int(x) for x in label.split(".")) if _VERSION_RE.match(label) else None


def release_refs(fetch, org: str, project: str, repo_guid: str) -> dict:
    """version -> ref name: release/<v> branches, with v<v> tags filling in
    versions whose branch is gone."""
    base = f"{org}/{project}/_apis/git/repositories/{repo_guid}/refs"
    refs = {}
    for r in fetch(f"{base}?filter=tags/v&{_API}").get("value", []):
        v = r["name"].removeprefix("refs/tags/v")
        if _version_key(v):
            refs[v] = f"v{v}"
    for r in fetch(f"{base}?filter=heads/release/&{_API}").get("value", []):
        v = r["name"].removeprefix("refs/heads/release/")
        if _version_key(v):
            refs[v] = f"release/{v}"
    return refs


def ref_type(name: str) -> str:
    return "tag" if re.match(r"^v\d", name) else "branch"


def pick_branch_pair(refs: dict, release: str, default_branch: str):
    """(base, target, in_progress), or None when the repo has no release ref
    below `release` (or the label isn't a version). An uncut release diffs the
    default branch against the latest release ref."""
    rel = _version_key(release)
    lower = [v for v in refs if rel and _version_key(v) < rel]
    if not lower:
        return None
    base = refs[max(lower, key=_version_key)]
    if release in refs:
        return base, refs[release], False
    return base, default_branch, True


def branch_diff_files(fetch, org: str, project: str, repo: str, base: str, target: str) -> list:
    url = (f"{org}/{project}/_apis/git/repositories/{repo}/diffs/commits"
           f"?baseVersion={base}&baseVersionType={ref_type(base)}"
           f"&targetVersion={target}&targetVersionType={ref_type(target)}&$top={_PAGE}")
    paths, skip = [], 0
    while True:
        page = fetch(f"{url}&$skip={skip}&{_API}")
        changes = page.get("changes", [])
        for c in changes:
            item = c.get("item") or {}
            if item.get("path") and item.get("gitObjectType") != "tree":
                paths.append(item["path"])
        skip += len(changes)
        # A truncated page omits allChangesIncluded rather than sending false.
        if page.get("allChangesIncluded") or len(changes) < _PAGE:
            return paths


def branch_commits(fetch, org: str, project: str, repo: str, base: str, target: str):
    """(PR ids merged into `target` since `base`, read from merge-commit
    messages; bulk direct commits as {id, comment, files})."""
    url = (f"{org}/{project}/_apis/git/repositories/{repo}/commits"
           f"?searchCriteria.itemVersion.versionType={ref_type(base)}"
           f"&searchCriteria.itemVersion.version={base}"
           f"&searchCriteria.compareVersion.versionType={ref_type(target)}"
           f"&searchCriteria.compareVersion.version={target}&searchCriteria.$top={_PAGE}")
    ids, bulk, skip = [], [], 0
    while True:
        commits = fetch(f"{url}&searchCriteria.$skip={skip}&{_API}").get("value", [])
        for c in commits:
            m = _MERGE_PR_RE.match(c.get("comment", ""))
            if m:
                if int(m.group(1)) not in ids:
                    ids.append(int(m.group(1)))
            elif sum((c.get("changeCounts") or {}).values()) > _BULK_FILES:
                bulk.append({"id": c["commitId"],
                             "comment": c.get("comment", "").split("\n")[0],
                             "files": commit_files(fetch, org, project, repo, c["commitId"])})
        skip += len(commits)
        if len(commits) < _PAGE:
            return ids, bulk


def commit_files(fetch, org: str, project: str, repo: str, commit_id: str) -> list:
    url = f"{org}/{project}/_apis/git/repositories/{repo}/commits/{commit_id}/changes"
    paths, skip = [], 0
    while True:
        changes = fetch(f"{url}?top={_PAGE}&skip={skip}&{_API}").get("changes", [])
        for c in changes:
            item = c.get("item") or {}
            if item.get("path") and item.get("gitObjectType") != "tree":
                paths.append(item["path"])
        skip += len(changes)
        if len(changes) < _PAGE:
            return paths


def pr_work_item_ids(fetch, org: str, project: str, repo: str, pr_id: int) -> list:
    data = fetch(f"{org}/{project}/_apis/git/repositories/{repo}"
                 f"/pullRequests/{pr_id}/workitems?{_API}")
    return [int(w["id"]) for w in data.get("value", [])]


def pr_details(fetch, org: str, project: str, pr_id: int):
    pr = fetch(f"{org}/_apis/git/pullrequests/{pr_id}?{_API}")
    if pr.get("status") == "abandoned":
        return None
    repo = (pr.get("repository") or {}).get("name", "")
    return {"id": pr["pullRequestId"], "title": pr.get("title", ""), "repo": repo,
            "url": f"{org}/{project}/_git/{repo}/pullrequest/{pr['pullRequestId']}",
            "status": pr.get("status", "")}


def pr_changed_files(fetch, org: str, project: str, repo: str, pr_id: int) -> list:
    base = f"{org}/{project}/_apis/git/repositories/{repo}/pullRequests/{pr_id}"
    iterations = fetch(f"{base}/iterations?{_API}")
    iter_ids = [it["id"] for it in iterations["value"]]
    if not iter_ids:
        # No iterations at all (e.g. a PR created and never pushed to) --
        # nothing to report, not a max()-on-empty-sequence crash.
        return []
    max_iter = max(iter_ids)
    paths, skip = [], 0
    while True:
        # ADO caps a page at 100 entries and says where to resume via nextSkip.
        changes = fetch(f"{base}/iterations/{max_iter}/changes?$top={_PAGE}&$skip={skip}&{_API}")
        for entry in changes.get("changeEntries", []):
            item = entry.get("item") or {}
            path = item.get("path")
            if not path:
                continue
            obj_type = item.get("gitObjectType")
            if obj_type == "tree":
                continue
            if obj_type == "blob" or (obj_type is None and "." in path.split("/")[-1]):
                paths.append(path)
        if not changes.get("nextTop") or changes.get("nextSkip", 0) <= skip:
            return paths
        skip = changes["nextSkip"]


def gather_release(fetch, org: str, project: str, query_id: str, release: str) -> dict:
    work_items = query_work_items(fetch, org, project, query_id)
    repo_info = repositories(fetch, org, project)
    repos = {g: r["name"] for g, r in repo_info.items()}
    skipped, pr_cache = [], {}

    def fetch_pr(repo_guid, pr_id):
        if pr_id in pr_cache:
            return pr_cache[pr_id]
        repo = repos.get(repo_guid)
        details = None
        if not repo:
            skipped.append(f"PR {pr_id}: unknown repo guid {repo_guid}")
        else:
            try:
                details = pr_details(fetch, org, project, pr_id)
                if details is None:
                    skipped.append(f"PR {pr_id}: abandoned")
                else:
                    details["files"] = pr_changed_files(fetch, org, project, repo, pr_id)
            except AdoHttpError as exc:
                skipped.append(f"PR {pr_id}: ADO call failed ({exc.status})")
                details = None
        pr_cache[pr_id] = details
        return details

    for wi in work_items:
        wi["prs"] = [d for rg, pid in work_item_pr_ids(fetch, org, wi["id"])
                     if (d := fetch_pr(rg, pid))]

    branch_repos = _gather_branches(fetch, org, project, release, repo_info,
                                    work_items, fetch_pr, skipped)

    return {"release": release, "query": query_id,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "skipped": skipped, "work_items": work_items, "branch_repos": branch_repos}


def _gather_branches(fetch, org, project, release, repo_info, work_items, fetch_pr, skipped):
    """Per release-branch repo: the files that ship and the PRs that shipped
    them. Branch PRs join their work items; items the query didn't return are
    appended with in_query False, PRs with no work item go to unlinked_prs.
    Only repos a query PR touched are checked, so a project with many repos
    doesn't pay two ref lookups per repo the release never went near."""
    if not _version_key(release):
        return {}
    by_id = {wi["id"]: wi for wi in work_items}
    in_query = {pr["repo"] for wi in work_items for pr in wi["prs"]}
    outside: dict[int, list] = {}
    branch_repos = {}
    for guid, info in repo_info.items():
        repo = info["name"]
        if repo not in in_query:
            continue
        try:
            pair = pick_branch_pair(release_refs(fetch, org, project, guid),
                                    release, info["default_branch"])
            if not pair:
                continue
            base, target, in_progress = pair
            files = branch_diff_files(fetch, org, project, repo, base, target)
            pr_ids, bulk = branch_commits(fetch, org, project, repo, base, target)
            unlinked = []
            for pid in pr_ids:
                pr = fetch_pr(guid, pid)
                if not pr:
                    continue
                wi_ids = pr_work_item_ids(fetch, org, project, repo, pid)
                if not wi_ids:
                    unlinked.append(pr)
                for wid in wi_ids:
                    if wid in by_id:
                        if all(p["id"] != pid for p in by_id[wid]["prs"]):
                            by_id[wid]["prs"].append(pr)
                    else:
                        outside.setdefault(wid, []).append(pr)
        except AdoHttpError as exc:
            skipped.append(f"{repo}: release branch lookup failed ({exc.status})")
            continue
        branch_repos[repo] = {"base": base, "target": target, "in_progress": in_progress,
                              "files": files, "prs": pr_ids, "unlinked_prs": unlinked,
                              "bulk_commits": bulk}
    for wi in work_item_records(fetch, org, project, list(outside)):
        wi["in_query"] = False
        wi["prs"] = outside[wi["id"]]
        work_items.append(wi)
    return branch_repos
