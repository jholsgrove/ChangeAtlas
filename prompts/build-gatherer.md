# Prompt: build a gatherer for your tracker (`release-<label>-data.json`)

## How to use this

ChangeAtlas ships with a gatherer for Azure DevOps (`changeatlas/gatherers/
ado.py`). If you use a different tracker — Jira, GitHub Issues, GitLab,
Linear, or anything else — you don't need to touch ChangeAtlas itself:
write a small standalone script that produces the same JSON file ADO's
gatherer produces, and everything downstream (impact computation, the
rendered map) works unchanged.

Point your AI agent at your tracker's API docs (and your git host's API
docs, if they're different products) and paste the prompt below with the
placeholders filled in.

**Fill in before pasting:** your tracker's name/API, your git host's
name/API, and how a release's work items are identified in your tracker
(a saved filter/JQL query, a label, a fix-version field, a milestone,
whatever it is).

**What you get out:** a script that writes `out/release-<label>-data.json`
in the exact shape ChangeAtlas's `impact.py` expects. Run it *before*
running `python -m changeatlas` — ChangeAtlas picks up
`out/release-<label>-data.json` automatically whenever that file already
exists, so a fresh run of your script is how you refresh it. Once the file
is there, render it with just:

```
python -m changeatlas --release <label> --graph-data /path/to/graph-data.json
```

No `--query`, `--org`, `--project`, or ADO token needed — ChangeAtlas only
asks for those when it actually has to fetch (no cache file found, or you
pass `--refresh`), and a hand-built cache means it never does. **Don't
pass `--refresh`** with a custom gatherer, though: that flag tells
ChangeAtlas to ignore the cache and fetch from Azure DevOps itself instead
— not what you want here. To refresh the data, just re-run your own script
before re-running `changeatlas`.

Once `docs/release-data-schema.md` exists in this repo, treat it as the
canonical version of the contract below — this prompt inlines the same
contract so it's usable standalone, but the doc is the one to re-check if
the two ever disagree.

---

## The prompt

````markdown
You are writing a **release-data gatherer**: a standalone script, in
whatever language you're most productive in, that queries my issue
tracker for a release's work items, follows each one's links to its pull
requests, fetches each pull request's changed file paths, and writes the
result as a single JSON file in the exact contract below. ChangeAtlas (a
separate, already-built tool) reads that file to compute which parts of my
system a release touched — you are not modifying ChangeAtlas, only
producing its input.

## My tracker and git host

- Issue tracker: [TRACKER-NAME, e.g. Jira / GitHub Issues / Linear] —
  API docs: [URL]
- Git host (where pull requests live — may be the same product as the
  tracker, or a different one): [GIT-HOST-NAME, e.g. GitHub / GitLab /
  Bitbucket] — API docs: [URL]
- How a release's work items are identified: [e.g. "all issues with label
  release-26.8", "all issues with fixVersion = 26.8", "a saved JQL/filter
  I'll give you the query for", "all issues in milestone 26.8"] —
  [PASTE THE ACTUAL QUERY / LABEL / FILTER / FIELD NAME HERE]
- How a work item links to its pull request(s): [e.g. "PR description
  contains 'Fixes PROJ-123'", "a tracker-side 'linked PRs' field", "PR
  branch name contains the issue key"] — describe how to reliably
  discover this link via the API, not by scraping free text if you can
  help it.

## Target output contract

Write **exactly** this shape to `out/release-<label>-data.json`, where
`<label>` is the release label I give you when I run the script (e.g.
`out/release-26.8-data.json` for release `26.8`):

```json
{
  "release": "26.8",
  "query": "<the query/filter/label identifier you used, or 'manual'>",
  "fetched_at": "2026-08-31T12:00:00+00:00",
  "skipped": [
    "PR 42: unknown repo abc123",
    "PR 51: ADO call failed (500)"
  ],
  "work_items": [
    {
      "id": 101,
      "type": "User Story",
      "title": "Coupon codes at checkout",
      "url": "https://tracker.example/browse/PROJ-101",
      "prs": [
        {
          "id": 11,
          "title": "Add coupon form and validation",
          "repo": "shop-web",
          "url": "https://git.example/shop-web/pull/11",
          "files": [
            "/src/checkout/CouponForm.tsx",
            "/src/checkout/CouponApi.ts"
          ]
        }
      ]
    }
  ]
}
```

Field by field:

- `release` (string) — the release label, exactly as passed in.
- `query` (string) — a human-readable identifier for whatever selected
  these work items (a query id, a filter name, a label) — or the literal
  string `"manual"` if there wasn't one. This is display-only.
- `fetched_at` (string) — ISO 8601 UTC timestamp of when you ran the
  fetch, e.g. produced by your language's equivalent of
  `datetime.now(timezone.utc).isoformat(timespec="seconds")`.
- `skipped` (array of strings) — one human-readable line per PR (or work
  item) you couldn't fully process and why (a PR whose repo you couldn't
  resolve, an API call that failed, a PR that turned out to be closed
  without merging). Empty array if nothing was skipped. These strings are
  printed as-is in ChangeAtlas's console output, so make them useful on
  their own.
- `work_items` (array) — one entry per work item in the release:
  - `id` (number) — the tracker's work item/issue id or number.
  - `type` (string) — the tracker's work item type (`"User Story"`,
    `"Bug"`, `"Task"`, whatever your tracker calls it). Display-only.
  - `title` (string) — the work item's title.
  - `url` (string) — a link straight to the work item in your tracker.
  - `prs` (array) — one entry per pull request linked to this work item
    that actually merged (skip abandoned/closed-without-merging PRs —
    record why in `skipped` instead of including them here):
    - `id` (number) — the PR number/id.
    - `title` (string) — the PR title.
    - `repo` (string) — the repo name as your git host reports it (don't
      pre-normalise it — ChangeAtlas lowercases it and replaces `.` with
      `-` itself when matching against the component map).
    - `url` (string) — a link straight to the PR.
    - `files` (array of strings) — every file the PR changed (added,
      modified, or deleted — not renamed-only or directory entries),
      as a path **relative to the repo root, with a leading `/`** (e.g.
      `/src/checkout/CouponForm.tsx`, not `src/checkout/CouponForm.tsx`
      or an absolute filesystem path). Use the PR's final/latest revision,
      not an intermediate one.

If a work item has no linked PRs at all, still include it with `"prs": []`
— ChangeAtlas reports those separately as "no code change" and that's a
meaningful, correct thing to be able to see.

## The flow to implement

1. Query the tracker for the release's work items (using whatever
   query/filter/label mechanism I described above) and pull their id,
   type, and title.
2. For each work item, find its linked pull request(s) via the tracker's
   or git host's API (however that link is discoverable per the notes
   above) — get each PR's id, title, source repo, and URL.
3. For each pull request, fetch its list of changed files at its latest
   revision, normalised to repo-root-relative paths with a leading `/`.
4. Assemble everything into the JSON shape above and write it to
   `out/release-<label>-data.json`.
5. Anything that fails partway (an unresolvable repo, a dead API call, a
   PR you can't fetch) should not crash the whole run — catch it, append
   a line to `skipped`, and keep going.

## If your tracker and git host are different products (Jira-style)

If work items live in one product (e.g. Jira) and pull requests live in a
different one (e.g. GitHub), you need **two separate credentials** — one
for the tracker's API, one for the git host's API — and two separate
authenticated clients. Don't assume a single token works for both, even if
both happen to be OAuth apps in the same company's SSO.

## Reference implementation

`changeatlas/gatherers/ado.py` in this repo is the gatherer ChangeAtlas
ships for Azure DevOps (where the tracker and git host are the same
product, so it only needs one credential). Read it for the general shape
worth copying, even in a different language:

- All network I/O goes through one small `fetch(url) -> dict` function,
  injected as a parameter rather than called directly — this is what lets
  its tests run with a fake in-memory `fetch` and no real network. Do the
  equivalent in your language (an injected client/fetch function, not
  hardcoded calls), even if you don't write tests for your one-off script.
- It builds the output in stages that mirror the contract: list work
  items, then each work item's linked PR ids, then each PR's details, then
  each PR's changed files — and assembles them into the same `work_items`
  → `prs` → `files` nesting as the contract above.
- It reads its credential from a single environment variable
  (`CHANGEATLAS_TOKEN`) and raises a clear, specific error if that
  variable is unset, rather than failing deep inside an HTTP call.
- Failures for an individual PR (unknown repo, HTTP error, abandoned PR)
  are caught per-PR, appended to `skipped`, and don't stop the rest of the
  run.

## Credentials

Read every credential your script needs from **environment variables
only** — never hardcode a token, never accept one as a command-line
argument (it'll end up in shell history), and never write one to a config
file. Pick clear, script-specific environment variable names (e.g.
`RELEASEGATHERER_JIRA_TOKEN`, `RELEASEGATHERER_GITHUB_TOKEN`) and fail
fast with a clear message naming the variable if it's missing, the same
way `changeatlas/gatherers/ado.py` fails fast on a missing
`CHANGEATLAS_TOKEN`.
````
