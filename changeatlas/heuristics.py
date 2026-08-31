"""heuristics.py — configurable file-classification rules (dependency/test/schema)."""
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Heuristics:
    dependency_basenames: frozenset
    dependency_suffixes: tuple
    test_markers: tuple
    schema_suffixes: tuple
    schema_segments: frozenset
    schema_basename_contains: tuple

    def is_dependency_file(self, path: str) -> bool:
        base = path.lower().rsplit("/", 1)[-1]
        return base in self.dependency_basenames or base.endswith(self.dependency_suffixes)

    def is_test_file(self, path: str) -> bool:
        return any(m in seg for seg in path.lower().split("/") for m in self.test_markers)

    def is_schema_file(self, path: str) -> bool:
        if self.is_test_file(path):
            return False
        low = path.lower()
        segs = low.split("/")
        return (low.endswith(self.schema_suffixes)
                or any(s in self.schema_segments for s in segs)
                or any(m in segs[-1] for m in self.schema_basename_contains))


_FIELDS = ("dependency_basenames", "dependency_suffixes", "test_markers",
           "schema_suffixes", "schema_segments", "schema_basename_contains")


def load(name_or_path: str, base_dir) -> Heuristics:
    p = Path(name_or_path)
    if not p.suffix == ".json" or not p.exists():
        p = Path(base_dir) / "config" / "heuristics" / f"{name_or_path}.json"
    if not p.exists():
        raise ValueError(f"heuristics preset or file not found: {name_or_path!r} (looked at {p})")
    data = json.loads(p.read_text(encoding="utf-8"))
    missing = [f for f in _FIELDS if f not in data or not isinstance(data[f], list)]
    if missing:
        raise ValueError(f"{p}: heuristics file missing/invalid fields: {', '.join(missing)}")
    lower = {f: [str(x).lower() for x in data[f]] for f in _FIELDS}
    return Heuristics(
        dependency_basenames=frozenset(lower["dependency_basenames"]),
        dependency_suffixes=tuple(lower["dependency_suffixes"]),
        test_markers=tuple(lower["test_markers"]),
        schema_suffixes=tuple(lower["schema_suffixes"]),
        schema_segments=frozenset(lower["schema_segments"]),
        schema_basename_contains=tuple(lower["schema_basename_contains"]),
    )
