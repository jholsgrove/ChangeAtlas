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
