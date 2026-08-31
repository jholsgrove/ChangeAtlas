import urllib.error

import pytest
from changeatlas.gatherers import ado

ORG = "https://dev.azure.com/exampleorg"
PROJ = "Shop"

def make_fetch(routes):
    calls = []
    def fetch(url):
        calls.append(url)
        for frag, resp in routes.items():
            if frag in url:
                return resp
        raise AssertionError(f"unexpected url: {url}")
    fetch.calls = calls
    return fetch

def test_query_work_items_flat_wiql_batches_fields():
    fetch = make_fetch({
        "/_apis/wit/wiql/abc-123": {"workItems": [{"id": 1}, {"id": 2}]},
        "/_apis/wit/workitems?ids=1,2": {"value": [
            {"id": 1, "fields": {"System.WorkItemType": "User Story", "System.Title": "Checkout"}},
            {"id": 2, "fields": {"System.WorkItemType": "Bug", "System.Title": "Fix tax"}}]},
    })
    items = ado.query_work_items(fetch, ORG, PROJ, "abc-123")
    assert [i["id"] for i in items] == [1, 2]
    assert items[0]["url"] == f"{ORG}/{PROJ}/_workitems/edit/1"
    assert items[1]["type"] == "Bug"

def test_query_work_items_tree_wiql_uses_targets():
    fetch = make_fetch({
        "/_apis/wit/wiql/abc-123": {"workItemRelations": [
            {"target": {"id": 5}}, {"target": {"id": 5}}, {"target": {"id": 6}}]},
        "/_apis/wit/workitems?ids=5,6": {"value": [
            {"id": 5, "fields": {}}, {"id": 6, "fields": {}}]},
    })
    assert [i["id"] for i in ado.query_work_items(fetch, ORG, PROJ, "abc-123")] == [5, 6]

def test_work_item_pr_ids_parses_artifact_links():
    fetch = make_fetch({"workitems/7": {"relations": [
        {"rel": "ArtifactLink",
         "url": "vstfs:///Git/PullRequestId/AAAA%2FBBBB%2F42"},
        {"rel": "ArtifactLink",
         "url": "vstfs:///Git/PullRequestId/AAAA%2FBBBB%2F42"},
        {"rel": "System.LinkTypes.Hierarchy-Forward", "url": "x"}]}})
    assert ado.work_item_pr_ids(fetch, ORG, 7) == [("bbbb", 42)]

def test_pr_details_none_when_abandoned():
    fetch = make_fetch({"/_apis/git/pullrequests/9": {
        "pullRequestId": 9, "status": "abandoned", "repository": {"name": "shop-web"}}})
    assert ado.pr_details(fetch, ORG, PROJ, 9) is None

def test_pr_changed_files_latest_iteration_blobs_only():
    fetch = make_fetch({
        "/pullRequests/9/iterations?": {"value": [{"id": 1}, {"id": 3}, {"id": 2}]},
        "/iterations/3/changes": {"changeEntries": [
            {"item": {"path": "/src/a.cs", "gitObjectType": "blob"}},
            {"item": {"path": "/src", "gitObjectType": "tree"}},
            {"item": {"path": "/src/b.cs"}}]},
    })
    files = ado.pr_changed_files(fetch, ORG, PROJ, "shop-web", 9)
    assert files == ["/src/a.cs", "/src/b.cs"]
    assert any("/iterations/3/changes" in u for u in fetch.calls)

def test_gather_release_skips_failing_pr_and_reports():
    def fetch(url):
        if "/_apis/wit/wiql/" in url: return {"workItems": [{"id": 1}]}
        if "/_apis/wit/workitems?ids=1" in url:
            return {"value": [{"id": 1, "fields": {"System.Title": "S"}}]}
        if "workitems/1" in url:
            return {"relations": [{"rel": "ArtifactLink",
                    "url": "vstfs:///Git/PullRequestId/P%2FR1%2F10"}]}
        if "/_apis/git/repositories" in url:
            return {"value": [{"id": "R1", "name": "shop-web", "isDisabled": False}]}
        if "/_apis/git/pullrequests/10" in url:
            raise ado.AdoHttpError(500, url)
        raise AssertionError(url)
    gathered = ado.gather_release(fetch, ORG, PROJ, "q", "1.0")
    assert gathered["work_items"][0]["prs"] == []
    assert any("PR 10" in s for s in gathered["skipped"])

def test_gather_release_caches_pr_across_work_items():
    # Two different work items link to the SAME PR -> pr_details/pr_changed_files
    # must be fetched only once (gather_release's pr_cache), and both work items
    # still carry the (shared) PR object.
    REPO_GUID, PR_ID = "aaa1", 42
    calls = []
    def fetch(url):
        calls.append(url)
        if "/_apis/wit/wiql/" in url:
            return {"workItems": [{"id": 1}, {"id": 2}]}
        if "/_apis/wit/workitems?ids=1,2" in url:
            return {"value": [
                {"id": 1, "fields": {"System.WorkItemType": "User Story", "System.Title": "A"}},
                {"id": 2, "fields": {"System.WorkItemType": "Bug", "System.Title": "B"}}]}
        if "/_apis/wit/workitems/1?" in url:
            return {"relations": [{"rel": "ArtifactLink",
                    "url": f"vstfs:///Git/PullRequestId/P%2F{REPO_GUID}%2F{PR_ID}"}]}
        if "/_apis/wit/workitems/2?" in url:
            return {"relations": [{"rel": "ArtifactLink",
                    "url": f"vstfs:///Git/PullRequestId/P%2F{REPO_GUID}%2F{PR_ID}"}]}
        if "/_apis/git/repositories?" in url:
            return {"value": [{"id": REPO_GUID.upper(), "name": "shop-web", "isDisabled": False}]}
        if f"/_apis/git/pullrequests/{PR_ID}?" in url:
            return {"pullRequestId": PR_ID, "title": "Checkout fix", "status": "completed",
                    "repository": {"name": "shop-web"}}
        if f"/pullRequests/{PR_ID}/iterations?" in url:
            return {"value": [{"id": 1}]}
        if "/iterations/1/changes" in url:
            return {"changeEntries": [{"item": {"path": "/src/a.cs", "gitObjectType": "blob"}}]}
        raise AssertionError(f"unexpected url: {url}")

    gathered = ado.gather_release(fetch, ORG, PROJ, "q", "1.0")
    wi1, wi2 = gathered["work_items"]
    assert wi1["prs"][0]["id"] == PR_ID
    assert wi2["prs"][0]["id"] == PR_ID
    pr_detail_hits = [u for u in calls if f"/_apis/git/pullrequests/{PR_ID}?" in u]
    assert len(pr_detail_hits) == 1        # fetched once despite two links

def test_gather_release_unknown_repo_guid_skipped():
    def fetch(url):
        if "/_apis/wit/wiql/" in url:
            return {"workItems": [{"id": 1}]}
        if "/_apis/wit/workitems?ids=1" in url:
            return {"value": [{"id": 1, "fields": {"System.WorkItemType": "Bug", "System.Title": "t"}}]}
        if "/_apis/wit/workitems/1?" in url:
            return {"relations": [{"rel": "ArtifactLink",
                    "url": "vstfs:///Git/PullRequestId/P%2Fzzz9%2F55"}]}
        if "/_apis/git/repositories?" in url:
            return {"value": []}
        raise AssertionError(f"unexpected url: {url}")

    gathered = ado.gather_release(fetch, ORG, PROJ, "q", "1.0")
    assert gathered["work_items"][0]["prs"] == []
    assert any("unknown repo guid" in s for s in gathered["skipped"])

def test_default_fetch_requires_token(monkeypatch):
    monkeypatch.delenv(ado.TOKEN_ENV, raising=False)
    with pytest.raises(ado.TokenMissingError):
        ado.default_fetch("https://example.invalid/x")


def test_default_fetch_url_error_maps_to_connection_error(monkeypatch):
    """MUST-FIX 3: DNS failure / connection refused / timeout out of
    urlopen() must map to AdoConnectionError, carrying the url and reason
    but never the token."""
    monkeypatch.setenv(ado.TOKEN_ENV, "super-secret-pat-value")

    def fake_urlopen(req, timeout=None):
        raise urllib.error.URLError("Name or service not known")

    monkeypatch.setattr(ado.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(ado.AdoConnectionError) as exc_info:
        ado.default_fetch("https://dev.azure.com/exampleorg/_apis/wit/wiql/q")

    exc = exc_info.value
    assert exc.url == "https://dev.azure.com/exampleorg/_apis/wit/wiql/q"
    assert "Name or service not known" in exc.reason
    assert "super-secret-pat-value" not in str(exc)


def test_pr_changed_files_empty_iterations_returns_empty_list():
    """STRONGLY RECOMMENDED 8: an empty iterations list must return [] instead
    of raising ValueError out of max() on an empty sequence."""
    fetch = make_fetch({"/pullRequests/9/iterations?": {"value": []}})
    assert ado.pr_changed_files(fetch, ORG, PROJ, "shop-web", 9) == []
