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

def test_default_fetch_requires_token(monkeypatch):
    monkeypatch.delenv(ado.TOKEN_ENV, raising=False)
    with pytest.raises(ado.TokenMissingError):
        ado.default_fetch("https://example.invalid/x")
