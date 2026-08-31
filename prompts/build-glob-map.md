# Prompt: build the component glob map (`config/component-globs.json`)

## How to use this

Run this once, right after you have a `graph-data.json` you're reasonably
happy with (see `prompts/scan-system-map.md`). Point your AI agent at
`graph-data.json` and at working clones of the repos it references, and
paste the prompt below with the placeholders filled in.

**Fill in before pasting:** the path to your `graph-data.json` and the list
of repo clones (same repos as the system-map step).

**What you get out:** a `config/component-globs.json` file (see the worked
example at `sample/component-globs.json` in this repo) that tells
ChangeAtlas which changed file paths belong to which graph node. Save it to
`config/component-globs.json` inside your ChangeAtlas checkout — that's the
default path the tool reads.

Don't aim for perfection on the first pass — see "rough is fine" at the
bottom of the prompt. Validate it, fix the errors it reports, and let real
releases refine the rest over time.

---

## The prompt

````markdown
You are building a **component glob map** for ChangeAtlas: a JSON file
that maps changed file paths in a pull request to the node(s) in my system
map (`graph-data.json`) that they belong to. This lets ChangeAtlas shade
the right boxes on the map when it sees which files a release actually
touched.

## Inputs

- The system map: [/path/to/graph-data.json]
- Local clones of the repos it references, so you can see real folder
  layouts:
  - [REPO-NAME-1] — [/path/to/repo-1]
  - [REPO-NAME-2] — [/path/to/repo-2]
  - [REPO-NAME-3] — [/path/to/repo-3]

Read `graph-data.json` first. For every node whose `type` is not `repo` or
`external`, you need to figure out which real folder(s)/file(s) in its
`repo` clone correspond to it, based on the node's `title`, `summary`, and
`repo`, plus whatever you can see in the actual repo layout (source
folders, project boundaries, naming conventions).

## Output format

Write the result to `config/component-globs.json`:

```json
{
  "components": [
    { "id": "shop-web", "repo": "shop-web", "globs": ["**"] },
    { "id": "checkout-flow", "repo": "shop-web", "globs": ["**/src/checkout/**"] }
  ]
}
```

Each entry:
- `id` — must match a node `id` in `graph-data.json` exactly.
- `repo` — the repo key this glob applies to.
- `globs` — an array of one or more glob patterns, matched against the
  changed file's path within that repo.

## Rules

- **Every glob must start with `**`.** ChangeAtlas rejects any glob that
  doesn't (`--check-map` will report it as an error) — this keeps
  matching anchor-independent of where the repo happens to be checked out.
- **Know the matching semantics** (they're simpler than most glob
  dialects): matching is **case-insensitive**; `*` **crosses `/`** (so `**`
  and `*` behave the same — the `**` prefix is a readability convention the
  validator enforces); and the changed path is matched with a leading `/`
  prepended, so `**/TopLevelFolder/**` matches files in a repo-root folder.
  A node may have only **one** entry — duplicate `id`s are rejected — so
  all of a node's globs live in that one entry's array, and a node cannot
  have entries under two different `repo` keys.
- **Anchor globs to a project-folder name segment, not a guessed path.**
  Prefer `**/Shop.Payments*/**` over `**/src/services/Shop.Payments/**`
  unless you have verified where the folder actually lives — project
  folders move, and a stale parent path silently un-maps the whole
  component. Only include parent segments when you need them to
  disambiguate two similarly-named folders.
- **The `repo` key is the lowercased repo name with every `.` replaced by
  `-`.** This must exactly match the `repo` key used in `graph-data.json`
  and the key ChangeAtlas derives from each pull request's repo name at
  match time — e.g. a repo named `Shop.Web` is the key `shop-web`. Get this
  wrong and every file in that repo will silently fail to match anything.
- **Give every repo a catch-all entry first**, matching the repo's own
  `type: "repo"` node id, with `"globs": ["**"]`. This is what lets a
  change shade at least the repo node even before you've mapped its finer
  detail, and it's why the catch-all itself never counts as "beyond repo"
  (see below).
- **Then add one entry per non-repo node** (services, features, projects,
  drivers, databases, etc.) with a glob or globs scoped to that node's real
  folder(s). A node can have more than one glob if its code isn't in one
  contiguous folder.
- You do not need an entry for `type: "external"` nodes — they never
  receive changed files directly.

## Validate it

Once you've written `config/component-globs.json`, validate it by running
this from the ChangeAtlas checkout (fill in the actual path to your
`graph-data.json`):

```
python -m changeatlas --check-map --graph-data /path/to/graph-data.json
```

If your `config/component-globs.json` lives somewhere other than the
`config/` folder next to the `changeatlas` package (for example, if you
keep it in a separate project folder), pass that folder's parent with
`--base-dir`:

```
python -m changeatlas --check-map --graph-data /path/to/graph-data.json --base-dir /path/to/that/folder
```

There are two things it can report, and they look different:

- **Structural problems in the JSON itself** — a missing `id` or `repo`, a
  duplicate `id`, empty `globs`, or a glob that doesn't start with `**` —
  fail immediately with a single message listing every such problem, and
  the command exits before it even gets to compare against the graph. Fix
  everything the message lists and re-run.
- Once the file is structurally valid, it's compared against
  `graph-data.json` and prints every remaining problem, one per line, then
  a summary like `errors: 0, warnings: 2`. Here, **errors** are map entries
  whose `id` doesn't exist as a node in `graph-data.json` at all — fix
  every one of these, the tool refuses to run a real release until they're
  gone (exit code is 1 whenever there's at least one). **Warnings** are
  graph nodes that have no map entry at all — they'll only ever shade
  their repo node instead of themselves — worth looking at, but they don't
  block anything (exit code is 0 if there are zero errors, even with
  warnings present).

## Audit it against the working tree

`--check-map` validates structure, but it cannot tell you whether your
globs actually claim the files they should. You already have local clones,
so audit the whole tree now instead of waiting for releases to surface
gaps one PR at a time: run every git-tracked file through the real matcher
and see what only hits the repo catch-all. From the ChangeAtlas checkout:

```python
import subprocess, collections, sys
sys.path.insert(0, ".")
from changeatlas import mapping

comps = mapping.load_map("config/component-globs.json")
repos = {  # repo key -> local clone path (same repos as the map)
    "shop-web": "/path/to/Shop.Web",
}
for key, clone in repos.items():
    files = subprocess.run(["git", "-C", clone, "ls-files"],
                           capture_output=True, text=True).stdout.splitlines()
    missed = [p for p in files if not mapping.match_file(comps, key, p)[1]]
    groups = collections.Counter("/".join(p.split("/")[:2]) for p in missed)
    print(f"{key}: {len(files) - len(missed)}/{len(files)} mapped beyond repo")
    for g, c in groups.most_common(15):
        print(f"  {c:5d}  {g}")
```

Every large group in that output is either a component your globs missed
(a project folder in an unexpected location, a content directory like a
`wwwroot/` or help-pages tree), a node the graph itself is missing, or
something genuinely fine at repo level (dotfiles, solution files, vendored
dependencies, deployment infra). Fix the first two kinds; leave the third.
A healthy map lands roughly 85–95% mapped-beyond-repo per repo — if a repo
is far below that, a whole area is missing.

## Rough is fine

You do not need to get every glob perfectly scoped on this pass — the
audit above catches the big gaps, and once you're running real releases
through ChangeAtlas, its normal console output includes an "Unmapped
beyond repo" section listing every changed file that matched a node's
catch-all but no finer glob. That's your per-run signal for exactly where
`config/component-globs.json` needs a new or wider pattern — let real
usage refine the long tail instead of trying to guess every folder
boundary up front.
````
