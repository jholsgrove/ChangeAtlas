# Prompt: build the system map (`graph-data.json`)

## How to use this

Run this once per system (or once per major re-architecture) — not per
release. Point your own AI coding agent (Claude Code, Cursor, Copilot Chat,
whatever you use) at checkouts of your repos and paste the prompt below into
it, with the bracketed placeholders filled in first.

**Fill in before pasting:**
- The list of repos to scan, each with a one-line description and its local
  path.
- The "facts to take as given" section — the things you already know about
  your system's databases, queues, and known cross-repo calls that scanning
  code can't reliably discover.

**What you get out:** a `graph-data.json` file (see the worked example at
`sample/graph-data.json` in this repo) plus a short report the agent prints
after generating it — node/edge counts and its 10 least-confident nodes, so
you know exactly what to spot-check before trusting the map.

Once you have `graph-data.json`, curate it by hand: fix any wrong guesses,
delete anything the report flagged as low-confidence and wrong, add
anything the agent missed. This file is checked in and read-only at
runtime — ChangeAtlas never regenerates it for you.

---

## The prompt

````markdown
You are building a **system map** for ChangeAtlas: a JSON graph of the
components in my system and the dependencies between them. This map is
built once and curated by hand — it is not regenerated per release, so
accuracy matters more than speed. Read this whole prompt before starting.

## Repos to scan

For each repo below, clone or open it locally and scan it.

| Repo (graph `repo` key) | Local path | One-line description |
|---|---|---|
| [REPO-NAME-1] | [/path/to/repo-1] | [what this repo is for] |
| [REPO-NAME-2] | [/path/to/repo-2] | [what this repo is for] |
| [REPO-NAME-3] | [/path/to/repo-3] | [what this repo is for] |

(Add or remove rows as needed. The `repo` key you use here must be the
lowercased repo name with any `.` replaced by `-` — e.g. a repo cloned as
`Shop.Web` becomes the key `shop-web`. This is the same normalisation
ChangeAtlas applies to pull-request repo names when it matches changed
files, so getting it right here matters.)

## Facts to take as given (seeded backbone)

The facts below are things I already know about this system. **Take them as
given — do not try to (re)discover or second-guess them by scanning code,
and do not infer additional facts of the same kind beyond what's listed
here.** Use them to seed the corresponding nodes and edges; only the rest of
the graph should come from your own scanning.

- **Databases and their owning repo:**
  - [DATABASE-NAME] — owned by [REPO-NAME] — [one sentence: what it stores]
  - [add more rows, or write "none" if there are none]
- **Message queues / topics / event buses:**
  - [QUEUE-OR-TOPIC-NAME] — published by [REPO-OR-COMPONENT], consumed by
    [REPO-OR-COMPONENT] — [one sentence: what flows through it]
  - [add more rows, or write "none" if there are none]
- **Known cross-repo calls** (HTTP/RPC calls between repos that you know
  happen but that may not be obvious from either side's code alone):
  - [REPO-OR-COMPONENT-A] calls [REPO-OR-COMPONENT-B] — [one sentence: why]
  - [add more rows, or write "none" if there are none]
- **Anything else you should treat as ground truth** (external services,
  known ownership boundaries, deliberately-undocumented integrations):
  - [FACT]
  - [add more rows, or write "none" if there are none]

## How to scan: plumbing, not code

For each repo, scan the **plumbing**, not the business logic. You are
looking for structure, not reading every file. Concretely, look at:

- Solution/project/package manifest files (`.sln`, `.csproj`, `package.json`,
  `pyproject.toml`, `go.mod`, `pom.xml`, etc.) to find the projects/modules
  that make up the repo and how they reference each other.
- Package/library references between projects, and to shared internal
  packages, to find `project-ref` and `nuget`-style dependency edges.
- Entrypoints (`Program.cs`/`Main`, `manage.py`, `main.go`, web framework
  route/controller registration, Dockerfiles, deployment manifests) to find
  the services and where they're exposed.
- Dependency-injection / service registration code (`Startup.cs`,
  `Program.cs` DI containers, DI modules) to find what's wired to what.
- Database and queue configuration (connection strings, ORM context/model
  registrations, migration folders, queue/topic client setup) to confirm
  and extend the seeded backbone above — never to override it.

Do **not** read through business-logic method bodies, do **not** try to
model individual classes, and do **not** try to capture every internal
function call. If you find yourself about to add a node for a single class
or method, stop — that's too fine-grained for this map.

## Node schema

Every node is a JSON object:

```json
{
  "id": "checkout-flow",
  "title": "Checkout Flow",
  "type": "feature",
  "repo": "shop-web",
  "summary": "The multi-step checkout experience, from cart to order confirmation.",
  "tags": ["shop-web", "feature"]
}
```

- `id` — kebab-case, unique across the whole graph.
- `title` — short human-readable name.
- `type` — one of: `repo` | `subsystem` | `project` | `service` |
  `contract` | `driver` | `database` | `messaging` | `feature` | `external`.
- `repo` — the repo key this node belongs to (see the table above); for
  `messaging` nodes that don't belong to one repo, use `cross`; for
  `external` nodes, use `external`.
- `summary` — 1 to 3 sentences, and every sentence must be grounded in
  something you actually saw while scanning (a file, a config entry, a
  registration) — not a guess at what the component probably does.
- `tags` — a small array of free-text tags; at minimum include the repo key
  and the type.

Every repo gets exactly one `type: "repo"` node representing the repo
itself, in addition to its internal nodes.

## Edge schema

Every edge is a JSON object:

```json
{ "from": "checkout-flow", "to": "orders-api", "kind": "http" }
```

Optionally add a `note` field (a short free-text string) when the reason
for the edge isn't obvious from the two node titles.

- `from`, `to` — node `id`s. Both must exist in your `nodes` array.
- `kind` — one of: `contains` | `nuget` | `http` | `sql` | `bus` |
  `consumes` | `project-ref` | `owns` | `uses`.
  - `contains` — a repo node containing one of its internal nodes.
  - `nuget` — a package/library dependency edge.
  - `http` — a synchronous HTTP/RPC call.
  - `sql` — direct database access.
  - `bus` — publishes to a messaging node.
  - `consumes` — consumes from a messaging node.
  - `project-ref` — an in-repo project/module reference.
  - `owns` — a repo or service owning a database (used alongside `sql` for
    the node that actually issues queries).
  - `uses` — a catch-all for a dependency that doesn't fit the other kinds
    (e.g. calling out to an external service).
- `note?` — optional short free-text clarification.

## Sizing: how many nodes

Aim for **8 to 20 nodes per repo** (the repo node itself plus its internal
nodes). Think of it this way: **one box per thing you'd mention in a test
plan, not a class diagram.** If you wouldn't write a line like "regression-
test the X area" about it, it's too small to be its own node — fold it into
a bigger one or leave it out. If a repo is trivially small (a single
library with no internal structure worth naming), it's fine for it to have
just its one repo node and nothing else.

## Grounding rules — read this twice

- **Never invent a component.** If you're not confident something exists,
  leave it out rather than guess. It's far better to under-map than to add
  a node nobody can verify.
- **Drop dangling edges.** Every edge's `from` and `to` must reference a
  node that actually exists in your `nodes` array. If you found evidence of
  a dependency but can't identify (or aren't confident enough to name) the
  node on the other end, drop the edge rather than invent a placeholder
  node for it.
- **Every repo needs a `contains` edge to each of its internal nodes.** A
  node with `repo: "shop-web"` that isn't reachable from the `shop-web`
  repo node via a `contains` edge is a bug in the graph — check every
  internal node has one.
- Everything else in the graph (outside the seeded backbone) must be
  something you actually observed while scanning — cite it to yourself
  before you write it down.

## Output

Write the result to `graph-data.json`:

```json
{
  "nodes": [ /* node objects as above */ ],
  "edges": [ /* edge objects as above */ ]
}
```

Then print a short report:

1. Total node count and total edge count, broken down by `type` and `kind`
   respectively.
2. Your **10 least-confident nodes** — the ones you're least sure are
   correctly scoped, correctly typed, or correctly summarised — with one
   short reason each, so I know exactly what to check by hand before I
   trust this map.
````
