# Release-data schema (`out/release-<label>-data.json`)

This file is the contract for a single release's tracker data: which work
items are in the release, which pull requests each one links to, and which
files each pull request changed. **This file is how any non-Azure-DevOps
tracker integrates with ChangeAtlas** — produce it however you like (a
one-off script, a manual export, ChangeAtlas's own built-in Azure DevOps
gatherer) and everything downstream — impact computation, the rendered map
— works unchanged.

## Shape

```json
{
  "release": "1.0",
  "query": "<id or 'manual'>",
  "fetched_at": "<iso8601>",
  "skipped": [],
  "work_items": [
    {
      "id": 101,
      "type": "User Story",
      "title": "…",
      "url": "https://…",
      "prs": [
        {
          "id": 11,
          "title": "…",
          "repo": "shop-web",
          "url": "https://…",
          "files": ["/src/checkout/CouponForm.tsx"]
        }
      ]
    }
  ]
}
```

## Field-by-field

| Field | Type | Meaning |
|---|---|---|
| `release` | string | The release label, exactly as passed to `--release`. |
| `query` | string | A human-readable identifier for whatever selected these work items — a query id, a filter name, a label — or the literal string `"manual"` if there wasn't one. Display-only. |
| `fetched_at` | string | ISO 8601 timestamp of when the data was fetched. |
| `skipped` | array of strings | One human-readable line per PR (or work item) that couldn't be fully processed, and why — an unresolvable repo, a failed API call, a PR that turned out closed without merging. Empty array if nothing was skipped. Printed as-is in ChangeAtlas's console output. |
| `work_items` | array | One entry per work item in the release. |
| `work_items[].id` | number | The tracker's work item/issue id. |
| `work_items[].type` | string | The tracker's work item type (`"User Story"`, `"Bug"`, `"Task"`, …). Display-only. |
| `work_items[].title` | string | The work item's title. |
| `work_items[].url` | string | Link straight to the work item in your tracker. |
| `work_items[].prs` | array | One entry per pull request linked to this work item that actually merged. Skip abandoned/closed-without-merging PRs and record why in `skipped` instead. May be empty (`[]`) — a work item with no linked PRs is valid and is reported separately by ChangeAtlas as "no code change". |
| `prs[].id` | number | The PR number/id. |
| `prs[].title` | string | The PR title. |
| `prs[].repo` | string | The repo name as your git host reports it — **don't pre-normalise it**. ChangeAtlas lowercases it and replaces `.` with `-` itself when matching against `config/component-globs.json`. |
| `prs[].url` | string | Link straight to the PR. |
| `prs[].files` | array of strings | Every file the PR changed (added, modified, or deleted — not renamed-only or directory entries) at its latest revision, as a path **relative to the repo root, with a leading `/`** — e.g. `/src/checkout/CouponForm.tsx`, not `src/checkout/CouponForm.tsx` and not an absolute filesystem path. |

## How ChangeAtlas uses this file

If `out/release-<label>-data.json` already exists, ChangeAtlas uses it as
is — no fetch happens. Pass `--refresh` to force a re-fetch via the
built-in Azure DevOps gatherer, ignoring the existing cache.

**`--query` is only required when a fetch is actually about to happen** —
no cache file found, or `--refresh` passed. It is not needed at all when a
cache file already exists at `out/release-<label>-data.json`, whether that
cache came from ChangeAtlas's own Azure DevOps gatherer on a previous run
or from a hand-built gatherer for a different tracker.

## Other trackers

Any tracker can be supported without touching ChangeAtlas itself: write a
standalone script (any language) that produces this exact file at
`out/release-<label>-data.json`, then render it with:

```
python -m changeatlas --release <label> --graph-data /path/to/graph-data.json
```

No `--query`, `--org`, `--project`, or token needed — ChangeAtlas only asks
for those when it has to fetch, and a hand-built cache means it never does.
Don't pass `--refresh` here, since that flag forces the built-in Azure
DevOps fetch path instead of reading your cache.

Use `prompts/build-gatherer.md` to have your own AI agent write that script
against your tracker's API (and your git host's API, if it's a different
product — see the "two credentials" note in that prompt for Jira-style
setups). `changeatlas/gatherers/ado.py` is the reference implementation:
read it for the shape worth copying — an injected `fetch(url) -> dict` seam
for testability, staged assembly (work items → linked PR ids → PR details →
changed files), a token read from a single environment variable, and
per-PR failure handling that appends to `skipped` instead of crashing the
whole run.

## Worked example

`sample/release-1.0-data.json` — the fictional data rendered by
`python -m changeatlas --sample` — is a complete, minimal example: three
work items, four PRs across three repos, one dependency-manifest file
(correctly ignored by impact computation), one schema-evidence file
(`.sql`, which does count as evidence for the database node it maps to),
and one test-only file.
