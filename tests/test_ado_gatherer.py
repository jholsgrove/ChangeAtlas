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
        if "/_apis/wit/wiql/" in url:
            return {"workItems": [{"id": 1}]}
        if "/_apis/wit/workitems?ids=1" in url:
            return {"value": [{"id": 1, "fields": {"System.Title": "S"}}]}
        if "workitems/1" in url:
            return {"relations": [{"rel": "ArtifactLink",
                    "url": "vstfs:///Git/PullRequestId/P%2FR1%2F10"}]}
        if "/refs?" in url:
            return {"value": []}
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
        if "/refs?" in url:
            return {"value": []}
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


# --- release-branch diff -------------------------------------------------------

def _refs(*versions):
    return {v: f"release/{v}" for v in versions}


def test_pick_branch_pair_highest_lower_version_as_base():
    assert ado.pick_branch_pair(_refs("26.8", "26.10", "26.9", "25.12"), "26.10", "master") ==         ("release/26.9", "release/26.10", False)


def test_pick_branch_pair_uncut_release_targets_default_branch():
    assert ado.pick_branch_pair(_refs("26.9", "26.10"), "26.11", "main") ==         ("release/26.10", "main", True)


def test_pick_branch_pair_none_without_lower_branch_or_version_label():
    assert ado.pick_branch_pair(_refs("26.10"), "26.10", "master") is None
    assert ado.pick_branch_pair({}, "26.10", "master") is None
    assert ado.pick_branch_pair(_refs("26.9"), "sample", "master") is None


def test_release_refs_branches_win_over_tags_and_tags_fill_deleted_branches():
    fetch = make_fetch({
        "/refs?filter=heads/release/": {"value": [
            {"name": "refs/heads/release/26.8"}, {"name": "refs/heads/release/26.9"},
            {"name": "refs/heads/release/hotfix-x"}]},
        "/refs?filter=tags/v": {"value": [
            {"name": "refs/tags/v26.7"}, {"name": "refs/tags/v26.8"},
            {"name": "refs/tags/vNext"}]}})
    assert ado.release_refs(fetch, ORG, PROJ, "R1") == {
        "26.7": "v26.7", "26.8": "release/26.8", "26.9": "release/26.9"}


def test_ref_type_tags_vs_branches():
    assert ado.ref_type("v26.7") == "tag"
    assert ado.ref_type("release/26.8") == "branch"
    assert ado.ref_type("master") == "branch"


def test_branch_diff_uses_tag_version_type_for_tag_base():
    fetch = make_fetch({"/diffs/commits?": {"allChangesIncluded": True, "changes": []},
                        "/commits?": {"value": []}})
    ado.branch_diff_files(fetch, ORG, PROJ, "R1", "v26.7", "release/26.8")
    ado.branch_commits(fetch, ORG, PROJ, "R1", "v26.7", "release/26.8")
    assert "baseVersion=v26.7&baseVersionType=tag" in fetch.calls[0]
    assert "targetVersionType=branch" in fetch.calls[0]
    assert "itemVersion.versionType=tag&searchCriteria.itemVersion.version=v26.7" in fetch.calls[1]


def test_branch_diff_files_pages_and_drops_trees(monkeypatch):
    monkeypatch.setattr(ado, "_PAGE", 2)
    pages = [
        {"allChangesIncluded": False, "changes": [
            {"item": {"path": "/src", "gitObjectType": "tree"}},
            {"item": {"path": "/src/a.pas", "gitObjectType": "blob"}}]},
        {"allChangesIncluded": True, "changes": [
            {"item": {"path": "/src/b.pas", "gitObjectType": "blob"}}]},
    ]
    calls = []
    def fetch(url):
        calls.append(url)
        return pages[len(calls) - 1]
    files = ado.branch_diff_files(fetch, ORG, PROJ, "R1", "release/26.9", "release/26.10")
    assert files == ["/src/a.pas", "/src/b.pas"]
    assert "baseVersion=release/26.9" in calls[0] and "targetVersion=release/26.10" in calls[0]
    assert "$skip=0" in calls[0] and "$skip=" in calls[1] and "$skip=0" not in calls[1]


def test_branch_commits_parses_both_merge_message_styles():
    fetch = make_fetch({"/commits?": {"count": 4, "value": [
        {"commitId": "c1", "comment": "Merged PR 13356: Fix ifAdminStatus"},
        {"commitId": "c2", "comment": "Merge pull request 13369 from users/x/y into master"},
        {"commitId": "c3", "comment": "WIP inner commit", "changeCounts": {"Edit": 3}},
        {"commitId": "c4", "comment": "Merged PR 13356: duplicate"}]}})
    pr_ids, bulk = ado.branch_commits(fetch, ORG, PROJ, "R1", "release/26.9", "release/26.10")
    assert (pr_ids, bulk) == ([13356, 13369], [])
    url = fetch.calls[0]
    assert "itemVersion.version=release/26.9" in url
    assert "compareVersion.version=release/26.10" in url


def _branch_fetch(extra=None):
    """Query returns story 1 (linked to PR 10). The poller repo cut release/2.0;
    its branch range holds PR 10 and PR 11 (linked to outside story 7) and
    PR 12 (no work item). shop-web has no release branches."""
    routes = {
        "/_apis/wit/wiql/": {"workItems": [{"id": 1}]},
        "/_apis/wit/workitems?ids=1&": {"value": [
            {"id": 1, "fields": {"System.WorkItemType": "User Story", "System.Title": "Q"}}]},
        "/_apis/wit/workitems?ids=7&": {"value": [
            {"id": 7, "fields": {"System.WorkItemType": "Bug", "System.Title": "Out"}}]},
        "/_apis/wit/workitems/1?": {"relations": [{"rel": "ArtifactLink",
            "url": "vstfs:///Git/PullRequestId/P%2Fr1%2F10"}]},
        "/_apis/git/repositories?": {"value": [
            {"id": "R1", "name": "Shop.Poller", "defaultBranch": "refs/heads/master"},
            {"id": "R2", "name": "shop-web", "defaultBranch": "refs/heads/main"}]},
        "/repositories/r1/refs?": {"value": [
            {"name": "refs/heads/release/1.9"}, {"name": "refs/heads/release/2.0"}]},
        "/repositories/r2/refs?": {"value": []},
        "/repositories/Shop.Poller/diffs/commits?": {"allChangesIncluded": True, "changes": [
            {"item": {"path": "/Poller/TaskPoll.pas", "gitObjectType": "blob"}},
            {"item": {"path": "/Poller/Snmp.pas", "gitObjectType": "blob"}},
            {"item": {"path": "/Poller/Direct.pas", "gitObjectType": "blob"}}]},
        "/repositories/Shop.Poller/commits?": {"value": [
            {"commitId": "m12", "comment": "Merged PR 12: build tweak"},
            {"commitId": "m11", "comment": "Merged PR 11: snmp fix"},
            {"commitId": "m10", "comment": "Merged PR 10: task fix"}]},
        "/pullRequests/10/workitems?": {"value": [{"id": "1"}]},
        "/pullRequests/11/workitems?": {"value": [{"id": "7"}]},
        "/pullRequests/12/workitems?": {"value": []},
    }
    for pid, path in ((10, "/Poller/TaskPoll.pas"), (11, "/Poller/Snmp.pas"),
                      (12, "/.teamcity/settings.kts")):
        routes[f"/_apis/git/pullrequests/{pid}?"] = {
            "pullRequestId": pid, "title": f"PR {pid}", "status": "completed",
            "repository": {"name": "Shop.Poller"}}
        routes[f"/pullRequests/{pid}/iterations?"] = {"value": [{"id": 1}]}
        routes[f"/pullRequests/{pid}/iterations/1/changes"] = {"changeEntries": [
            {"item": {"path": path, "gitObjectType": "blob"}}]}
    routes.update(extra or {})
    return make_fetch(routes)


def test_gather_release_adds_branch_diff_for_release_branch_repos():
    gathered = ado.gather_release(_branch_fetch(), ORG, PROJ, "q", "2.0")
    br = gathered["branch_repos"]
    assert list(br) == ["Shop.Poller"]                    # shop-web: query-only
    poller = br["Shop.Poller"]
    assert (poller["base"], poller["target"], poller["in_progress"]) ==         ("release/1.9", "release/2.0", False)
    assert poller["files"] == ["/Poller/TaskPoll.pas", "/Poller/Snmp.pas", "/Poller/Direct.pas"]
    assert poller["prs"] == [12, 11, 10]
    assert [p["id"] for p in poller["unlinked_prs"]] == [12]
    assert poller["bulk_commits"] == []
    by_id = {wi["id"]: wi for wi in gathered["work_items"]}
    assert [p["id"] for p in by_id[1]["prs"]] == [10]     # not duplicated
    assert "in_query" not in by_id[1]
    assert by_id[7]["in_query"] is False
    assert by_id[7]["type"] == "Bug"
    assert [p["id"] for p in by_id[7]["prs"]] == [11]


def test_gather_release_uncut_release_diffs_default_branch():
    fetch = _branch_fetch({"/repositories/r1/refs?": {"value": [
        {"name": "refs/heads/release/1.9"}]}})
    poller = ado.gather_release(fetch, ORG, PROJ, "q", "2.0")["branch_repos"]["Shop.Poller"]
    assert (poller["base"], poller["target"], poller["in_progress"]) ==         ("release/1.9", "master", True)


def test_gather_release_checks_refs_only_for_repos_the_query_touched():
    fetch = _branch_fetch()
    ado.gather_release(fetch, ORG, PROJ, "q", "2.0")
    assert any("/repositories/r1/refs?" in u for u in fetch.calls)
    assert not any("/repositories/r2/refs?" in u for u in fetch.calls)


def test_gather_release_skips_branches_for_non_version_release_label():
    fetch = _branch_fetch()
    gathered = ado.gather_release(fetch, ORG, PROJ, "q", "Sprint 42")
    assert gathered["branch_repos"] == {}
    assert not any("/refs?" in u for u in fetch.calls)


def test_branch_diff_files_keeps_paging_when_flag_absent(monkeypatch):
    # ADO omits allChangesIncluded on a truncated page instead of sending false.
    monkeypatch.setattr(ado, "_PAGE", 2)
    def blob(path):
        return {"item": {"path": path, "gitObjectType": "blob"}}
    pages = [{"changes": [blob("/a"), blob("/b")]},
             {"allChangesIncluded": True, "changes": [blob("/c")]}]
    calls = []
    def fetch(url):
        calls.append(url)
        return pages[len(calls) - 1]
    assert ado.branch_diff_files(fetch, ORG, PROJ, "R1", "release/1", "release/2") == \
        ["/a", "/b", "/c"]


def test_pr_changed_files_follows_next_skip_past_the_100_cap():
    def blob(path):
        return {"item": {"path": path, "gitObjectType": "blob"}}
    calls = []
    def fetch(url):
        calls.append(url)
        if url.endswith("/iterations?api-version=7.1"):
            return {"value": [{"id": 2}]}
        if "$skip=0" in url:
            return {"changeEntries": [blob("/a.cs"), blob("/b.cs")], "nextSkip": 2, "nextTop": 2}
        if "$skip=2" in url:
            return {"changeEntries": [blob("/c.cs")], "nextSkip": 0, "nextTop": 0}
        raise AssertionError(url)
    assert ado.pr_changed_files(fetch, ORG, PROJ, "shop-web", 9) == ["/a.cs", "/b.cs", "/c.cs"]


def test_branch_commits_flags_large_direct_commits_as_bulk(monkeypatch):
    monkeypatch.setattr(ado, "_BULK_FILES", 3)
    fetch = make_fetch({
        "/commits/big1/changes?": {"changes": [
            {"item": {"path": "/a.cs", "gitObjectType": "blob"}},
            {"item": {"path": "/src", "gitObjectType": "tree"}},
            {"item": {"path": "/b.cs", "gitObjectType": "blob"}}]},
        "/commits?": {"value": [
            {"commitId": "big1", "comment": "Renormalize\n\nline endings",
             "changeCounts": {"Add": 0, "Edit": 4, "Delete": 0}},
            {"commitId": "small", "comment": "hotfix", "changeCounts": {"Edit": 2}},
            {"commitId": "pr", "comment": "Merged PR 5: huge", "changeCounts": {"Edit": 99}}]}})
    pr_ids, bulk = ado.branch_commits(fetch, ORG, PROJ, "R1", "release/1", "release/2")
    assert pr_ids == [5]
    assert bulk == [{"id": "big1", "comment": "Renormalize", "files": ["/a.cs", "/b.cs"]}]


def test_commit_files_pages(monkeypatch):
    monkeypatch.setattr(ado, "_PAGE", 2)
    def blob(path):
        return {"item": {"path": path, "gitObjectType": "blob"}}
    pages = {"skip=0": {"changes": [blob("/a"), blob("/b")]},
             "skip=2": {"changes": [blob("/c")]}}
    def fetch(url):
        return next(v for k, v in pages.items() if k in url)
    assert ado.commit_files(fetch, ORG, PROJ, "R1", "c1") == ["/a", "/b", "/c"]
