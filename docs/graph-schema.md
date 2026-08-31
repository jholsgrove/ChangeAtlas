# Graph schema (`graph-data.json`)

`graph-data.json` is the system map: a JSON graph of the components in your
system and the dependencies between them. It's built **once** (and curated
by hand afterwards) by your own AI agent, using `prompts/scan-system-map.md`
— see that file for the full build prompt and grounding rules.

**ChangeAtlas reads this file read-only.** It never writes to it, never
regenerates it, and never infers new nodes or edges into it at runtime. If
the map is wrong or stale, the fix is to re-run (or hand-edit) the prompt's
output, not to expect ChangeAtlas to correct it for you.

## Shape

```json
{
  "nodes": [ /* node objects */ ],
  "edges": [ /* edge objects */ ]
}
```

## Node

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

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Unique, kebab-case, across the whole graph. Referenced by edges (`from`/`to`) and by `config/component-globs.json` entries. |
| `title` | string | Short human-readable name, shown on the rendered map. |
| `type` | enum | One of: `repo`, `subsystem`, `project`, `service`, `contract`, `driver`, `database`, `messaging`, `feature`, `external`. Drives the node's colour on the canvas (`changeatlas/palette.py`'s `TYPE_COLORS`) and its label in the legend. |
| `repo` | string | The repo key this node belongs to — lowercased repo name with `.` replaced by `-` (e.g. a repo named `Shop.Web` is the key `shop-web`). For a `messaging` node not owned by one repo, use `cross`; for an `external` node, use `external`. |
| `summary` | string | 1–3 sentences describing the node, grounded in something actually observed while scanning — shown in the details panel when the node is selected. |
| `tags` | array of strings | Free-text tags; at minimum the repo key and the type. |

### `type` enum meanings

- `repo` — the repository itself. Every repo gets exactly one, plus a
  `contains` edge to each of its internal nodes. Repo nodes never enter an
  impact tier (their catch-all glob matches everything) and edges touching
  them never spread the peripheral ring — see `docs/release-data-schema.md`
  and the tier semantics table in `README.md`.
- `subsystem` — a grouping of related functionality bigger than a single
  feature or service, smaller than a whole repo.
- `project` — an internal project/module/library within a repo.
- `service` — a runnable service or API.
- `contract` — a shared interface/schema/API contract.
- `driver` — an integration adapter for a specific external system.
- `database` — a datastore. Shades only on schema evidence (migrations,
  `.sql` files, model snapshots) — ordinary data-access code changes don't
  imply the database itself changed, and a database node is never marked
  peripheral even when a directly-connected node changes.
- `messaging` — a queue, topic, or event bus.
- `feature` — a user-facing feature or flow.
- `external` — a third-party system outside your own repos.

## Edge

```json
{ "from": "checkout-flow", "to": "orders-api", "kind": "http" }
```

Optionally with a `note`:

```json
{ "from": "invoice-generator", "to": "email-provider", "kind": "uses",
  "note": "sends transactional emails via the provider's REST API" }
```

| Field | Type | Meaning |
|---|---|---|
| `from`, `to` | string | Node `id`s. Both must exist in `nodes` — dangling edges are a bug in the graph, not something ChangeAtlas tolerates. |
| `kind` | enum | One of: `contains`, `nuget`, `http`, `sql`, `bus`, `consumes`, `project-ref`, `owns`, `uses`. Drives the edge label shown on the canvas (`EDGE_LABEL` in `changeatlas/__main__.py`). |
| `note` | string, optional | Short free-text clarification, shown alongside the edge label when present. |

### `kind` enum meanings

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

## Worked example (5 nodes)

A slice of `sample/graph-data.json` — a repo, one of its features, the
service that feature calls, and the database and external system behind
that service:

```json
{
  "nodes": [
    { "id": "shop-web", "title": "Shop Web", "type": "repo", "repo": "shop-web",
      "summary": "The customer-facing storefront: browsing, checkout, and account management.",
      "tags": ["shop-web", "repo"] },
    { "id": "checkout-flow", "title": "Checkout Flow", "type": "feature", "repo": "shop-web",
      "summary": "The multi-step checkout experience, from cart to order confirmation.",
      "tags": ["shop-web", "feature"] },
    { "id": "orders-api", "title": "Orders API", "type": "service", "repo": "shop-orders",
      "summary": "Public HTTP service for creating and querying customer orders.",
      "tags": ["shop-orders", "service"] },
    { "id": "orders-db", "title": "Orders Database", "type": "database", "repo": "shop-orders",
      "summary": "Relational store of orders, line items, and payment records.",
      "tags": ["shop-orders", "database"] },
    { "id": "stripe", "title": "Stripe", "type": "external", "repo": "external",
      "summary": "Third-party payment processor used for card authorization and capture.",
      "tags": ["external", "external"] }
  ],
  "edges": [
    { "from": "shop-web", "to": "checkout-flow", "kind": "contains" },
    { "from": "checkout-flow", "to": "orders-api", "kind": "http" },
    { "from": "orders-api", "to": "orders-db", "kind": "sql" },
    { "from": "orders-api", "to": "stripe", "kind": "uses" }
  ]
}
```

For the full 20-node, 3-repo fictional system this is drawn from, see
`sample/graph-data.json` — it's what `python -m changeatlas --sample`
renders.

## Building your own

Use `prompts/scan-system-map.md` to have your own AI agent produce this
file from your real repos, then hand-curate it. Once you have it, use
`prompts/build-glob-map.md` to produce the companion
`config/component-globs.json`, which maps changed file paths onto these
node `id`s — validate that mapping with:

```
python -m changeatlas --check-map --graph-data /path/to/graph-data.json
```
