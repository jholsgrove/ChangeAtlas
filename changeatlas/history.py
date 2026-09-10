"""history.py — the release slider's files on disk.

A *series* is one directory of reports. Beside each `impact-<label>.html`
the render leaves a small sidecar (`impact-<label>.history.js`: the four tier
lists and per-node file counts, node ids only) and rewrites one manifest
(`releases.js`) listing the five most recent releases by fetch date. The
report loads both with plain <script src> tags, which work from file://
where fetch and iframes do not.

Sidecars are recomputed on every render against the *current* atlas and
globs: impact.compute is a pure function of one cached release-data file
plus the graph, so an atlas change never leaves stale ids behind.
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path

from . import impact

HISTORY_LIMIT = 5
MANIFEST_NAME = "releases.js"
_CACHE_RE = re.compile(r"^release-(.+)-data\.json$")


@dataclass(frozen=True)
class Release:
    label: str
    fetched_at: str
    path: Path


def discover(cache_dir: Path) -> tuple[list[Release], list[str]]:
    """Every release-*-data.json in cache_dir, oldest fetch first.

    Returns (releases, warnings). An unreadable or shapeless file becomes a
    warning line rather than an exception: one bad cache must never stop the
    requested render.
    """
    cache_dir = Path(cache_dir)
    if not cache_dir.is_dir():
        return [], []
    releases, warnings = [], []
    for p in sorted(cache_dir.iterdir()):
        if not p.is_file() or not _CACHE_RE.match(p.name):
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            label = str(data["release"])
            fetched_at = str(data["fetched_at"])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            warnings.append(f"history: skipped {p.name} ({exc.__class__.__name__}: {exc})")
            continue
        releases.append(Release(label=label, fetched_at=fetched_at, path=p))
    releases.sort(key=lambda r: (r.fetched_at, r.label))
    return releases, warnings


def sidecar_name(label: str) -> str:
    return f"impact-{label}.history.js"


def report_name(label: str) -> str:
    return f"impact-{label}.html"


def sidecar(gathered: dict, components: list, nodes: list, edges: list, heur,
            changed_threshold: int = 3) -> dict:
    """Tier lists and per-node file counts for one release. Node ids only."""
    r = impact.compute(gathered, components, nodes, edges, heur,
                       changed_threshold=changed_threshold)
    return {
        "impact": {"changed": r["changed"], "touched": r["touched"],
                   "testOnly": r["test_only"], "peripheral": r["peripheral"]},
        "counts": {nid: {"prodFiles": d["prodFiles"], "testFiles": d["testFiles"]}
                   for nid, d in sorted(r["details"].items())},
    }


def _js(value) -> str:
    # '<\/' keeps a stray '</script>' inert should anyone inline this file.
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def write_series(out_dir: Path, releases: list[Release], compute) -> list[str]:
    """Write sidecars for the HISTORY_LIMIT most recent releases and the manifest.

    `compute(gathered) -> sidecar dict` is supplied by the caller so this
    module never needs the graph, globs or heuristics itself.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    window = releases[-HISTORY_LIMIT:]
    entries, warnings = [], []
    for rel in window:
        try:
            gathered = json.loads(rel.path.read_text(encoding="utf-8"))
            side = compute(gathered)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            warnings.append(f"history: skipped {rel.path.name} ({exc.__class__.__name__}: {exc})")
            continue
        (out_dir / sidecar_name(rel.label)).write_text(
            "window.CHANGEATLAS_HISTORY = window.CHANGEATLAS_HISTORY || {};\n"
            f"window.CHANGEATLAS_HISTORY[{_js(rel.label)}] = {_js(side)};\n",
            encoding="utf-8")
        report = report_name(rel.label)
        entries.append({"label": rel.label, "fetchedAt": rel.fetched_at,
                        "history": sidecar_name(rel.label),
                        "report": report if (out_dir / report).exists() else None})
    (out_dir / MANIFEST_NAME).write_text(
        f"window.CHANGEATLAS_RELEASES = {_js(entries)};\n", encoding="utf-8")
    return warnings
