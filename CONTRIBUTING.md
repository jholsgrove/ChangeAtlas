# Contributing to ChangeAtlas

## The biggest gap: gatherers for other trackers

ChangeAtlas ships one gatherer, for Azure DevOps
(`changeatlas/gatherers/ado.py`), because that's the only tracker the
maintainer can actually test against. Jira, GitHub Issues, GitLab, Linear,
and everything else are explicitly invited — this is the single most
useful contribution you can make.

**You don't need to touch impact computation, rendering, or anything else**
— a gatherer is a self-contained module that produces
`out/release-<label>-data.json` in the contract documented at
[`docs/release-data-schema.md`](docs/release-data-schema.md). Everything
downstream reads that file and doesn't care how it was produced.

Use [`changeatlas/gatherers/ado.py`](changeatlas/gatherers/ado.py) as your
template. A contributed gatherer should follow the same shape:

- **Stdlib-only, or a clearly-optional extra.** `ado.py` uses only
  `urllib`/`json`/`base64` from the standard library — no new hard
  dependency for everyone who doesn't use your tracker. If your tracker's
  API genuinely needs a third-party client library, gate the import so the
  rest of ChangeAtlas still runs without it installed, and document the
  extra install step clearly.
- **An injected-fetch test seam.** All network I/O should go through one
  small function passed in as a parameter (`fetch(url) -> dict` in
  `ado.py`), never called directly — this is what lets tests run against a
  fake in-memory fetch instead of real network calls.
- **Tokens from environment variables only.** Never a CLI flag (shell
  history, process lists), never a config file. Follow `ado.py`'s
  pattern: read one clearly-named env var, raise a specific, catchable
  error (see `TokenMissingError`) with an actionable message when it's
  unset.
- **Tests with fake fetches.** Cover at minimum: the happy path end to end,
  an HTTP failure that should land in `skipped` rather than crash the run,
  and any tracker-specific edge case (pagination, batching limits, whatever
  your API imposes). See `tests/test_ado_gatherer.py` for the shape.
- **A `docs/tokens.md` scope entry.** Add a row to the scope matrix in
  [`docs/tokens.md`](docs/tokens.md#scope-matrix-future-gatherers) naming
  your env var and the minimal read-only scopes your gatherer needs.

If your tracker and your git host are different products (Jira + GitHub is
the classic case), your gatherer needs **two** credentials and two
authenticated clients — don't assume one token covers both. See the
"Jira-style" note in [`prompts/build-gatherer.md`](prompts/build-gatherer.md).

Not ready to write Python? [`prompts/build-gatherer.md`](prompts/build-gatherer.md)
is an AI prompt that produces a standalone script (any language) against
the same contract, for your own use — porting that into a proper
`changeatlas/gatherers/` module and PRing it back is exactly the
contribution described above.

## Dev basics

```sh
python -m pytest tests -v
```

No other setup — the test suite has no dependencies beyond `pytest` itself
and the standard library.

One optional extra: `tests/test_browser.py` drives the rendered report in
headless Chrome via Playwright (`pip install playwright`; it uses your
installed Chrome, no `playwright install` needed). Without Playwright those
tests skip and everything else still runs.

Browser tests are the exception, not the default. Template behaviour is
normally covered by string checks against the rendered HTML (see
`tests/test_template_a11y.py`); reach for a browser test only when the
behaviour lives in vis-network's canvas at runtime and a static check
genuinely can't see it. When you do add one, follow the page-object layout:
selectors in `tests/browser/selectors.py`, user-level actions in
`tests/browser/report_page.py`, and tests that talk only to the page
object.

The repo is a plain `changeatlas/` package plus `tests/`; there's no build
step. Run `python -m changeatlas --sample` after making changes to
sanity-check the whole pipeline end to end against the bundled fictional
dataset (see the README's Quickstart).

## AI-assisted onboarding

If you're setting ChangeAtlas up for your own system rather than
contributing code to ChangeAtlas itself, the `prompts/` directory contains
the AI-assisted path: `prompts/scan-system-map.md` builds your system
graph, `prompts/build-glob-map.md` builds the file-to-node mapping, and
`prompts/build-gatherer.md` writes a gatherer for your tracker. See the
README's **The method** section for how they fit together.
