"""ado.py — Azure DevOps REST gatherer. All I/O behind injected `fetch(url)->dict`."""
import base64
import json
import os
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


def repo_names(fetch, org: str, project: str) -> dict:
    data = fetch(f"{org}/{project}/_apis/git/repositories?{_API}")
    return {r["id"].lower(): r["name"]
            for r in data.get("value", []) if not r.get("isDisabled")}


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
    changes = fetch(f"{base}/iterations/{max_iter}/changes?{_API}")
    paths = []
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
    return paths


def gather_release(fetch, org: str, project: str, query_id: str, release: str) -> dict:
    work_items = query_work_items(fetch, org, project, query_id)
    repos = repo_names(fetch, org, project)
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

    return {"release": release, "query": query_id,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "skipped": skipped, "work_items": work_items}
