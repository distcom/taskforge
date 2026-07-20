"""Plugin discovery, indexing, and assignment.

Scans configured plugin roots for PLUGIN.md manifests, builds a keyword-scored
index, and assigns best-fit plugins to work segments.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import PluginBinding, PluginInfo, WorkSegment

# ─── Configuration ─────────────────────────────────────────────────────────────

_ROOTS_FILE = "roots.json"
_GLOBAL_DIR = Path.home() / ".taskforge"


def resolve_plugin_roots(workspace: Path | None = None) -> list[Path]:
    """Resolve all configured plugin root directories (deduplicated, existing only).

    Lookup order:
      1. <workspace>/.taskforge/roots.json
      2. ~/.taskforge/roots.json
    """
    roots: list[Path] = []
    candidates: list[Path] = []
    if workspace:
        candidates.append(workspace / ".taskforge" / _ROOTS_FILE)
    candidates.append(_GLOBAL_DIR / _ROOTS_FILE)

    for cfg in candidates:
        if not cfg.is_file():
            continue
        try:
            entries = json.loads(cfg.read_text(encoding="utf-8"))
            if isinstance(entries, list):
                for raw in entries:
                    p = Path(str(raw)).expanduser().resolve()
                    if p.is_dir() and p not in roots:
                        roots.append(p)
        except (json.JSONDecodeError, OSError):
            continue
    return roots


# ─── Discovery ─────────────────────────────────────────────────────────────────


def scan_plugins(roots: list[Path]) -> list[PluginInfo]:
    """Walk plugin roots and parse PLUGIN.md manifests.

    A valid plugin directory contains a readable PLUGIN.md.
    First-found wins on name collision.
    """
    found: list[PluginInfo] = []
    seen: set[str] = set()

    for root in roots:
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue
            manifest = entry / "PLUGIN.md"
            if not manifest.is_file():
                continue
            info = _parse_manifest(manifest, entry)
            if info is None or info.display_name.lower() in seen:
                continue
            seen.add(info.display_name.lower())
            found.append(info)
    return found


def _parse_manifest(path: Path, plugin_dir: Path) -> PluginInfo | None:
    """Extract metadata from a PLUGIN.md frontmatter + heading fallback."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.strip():
        return None

    name = summary = use_case = limits = ""
    categories: list[str] = []

    fm = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if fm:
        block = fm.group(1)
        name = _field(block, "name")
        summary = _field(block, "description")
        use_case = _field(block, "use_case")
        limits = _field(block, "limits")
        raw_cats = _field(block, "categories")
        if raw_cats:
            categories = [c.strip() for c in raw_cats.split(",") if c.strip()]

    if not name:
        h = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        name = h.group(1).strip() if h else plugin_dir.name

    if not summary:
        for line in text.splitlines():
            s = line.strip()
            if s and not s.startswith("#") and not s.startswith("---"):
                summary = s[:200]
                break

    pid = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return PluginInfo(
        plugin_id=pid,
        display_name=name,
        summary=summary,
        manifest_path=str(path),
        categories=categories,
        use_case=use_case,
        limits=limits,
    )


def _field(block: str, key: str) -> str:
    m = re.search(rf"^{re.escape(key)}\s*:\s*(.+)$", block, re.MULTILINE | re.IGNORECASE)
    return m.group(1).strip().strip("\"'") if m else ""


# ─── Index ─────────────────────────────────────────────────────────────────────


class PluginIndex:
    """In-memory keyword-scored index over discovered plugins."""

    __slots__ = ("_map",)

    def __init__(self, plugins: list[PluginInfo] | None = None) -> None:
        self._map: dict[str, PluginInfo] = {}
        for p in plugins or []:
            self._map[p.plugin_id] = p

    @property
    def count(self) -> int:
        return len(self._map)

    def add(self, plugin: PluginInfo) -> None:
        self._map[plugin.plugin_id] = plugin

    def get(self, plugin_id: str) -> PluginInfo | None:
        return self._map.get(plugin_id)

    def query(self, text: str, *, limit: int = 8) -> list[PluginInfo]:
        """Rank plugins by keyword relevance to the query text."""
        kws = set(text.lower().split())
        if not kws:
            return list(self._map.values())[:limit]

        scored: list[tuple[float, PluginInfo]] = []
        for p in self._map.values():
            s = self._relevance(p, kws)
            if s > 0:
                scored.append((s, p))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [p for _, p in scored[:limit]]

    def _relevance(self, p: PluginInfo, kws: set[str]) -> float:
        score = 0.0
        name_tokens = set(p.display_name.lower().split())
        summary_tokens = set(p.summary.lower().split())
        cat_set = set(c.lower() for c in p.categories)
        use_tokens = set(p.use_case.lower().split())

        for kw in kws:
            if kw in name_tokens:
                score += 5.0
            if kw in cat_set:
                score += 3.5
            if kw in use_tokens:
                score += 2.0
            if kw in summary_tokens:
                score += 1.0
            if any(kw in t for t in name_tokens):
                score += 1.5
        return score

    def serialize(self) -> dict[str, Any]:
        return {pid: asdict(p) for pid, p in self._map.items()}

    @classmethod
    def restore(cls, data: dict[str, Any]) -> PluginIndex:
        return cls([PluginInfo(**v) for v in data.values()])


# ─── Assignment ────────────────────────────────────────────────────────────────


def assign_plugins(
    index: PluginIndex,
    segments: list[WorkSegment],
    *,
    max_per_segment: int = 3,
) -> list[PluginBinding]:
    """Match plugins to work segments by objective relevance."""
    bindings: list[PluginBinding] = []
    for seg in segments:
        candidates = index.query(seg.objective, limit=max_per_segment * 2)
        chosen = candidates[:max_per_segment]
        seg.plugin_candidates = [p.plugin_id for p in chosen]
        for p in chosen:
            bindings.append(PluginBinding(
                plugin_id=p.plugin_id,
                segment_ids=[seg.segment_id],
                duty=f"Deliver: {seg.objective}",
                rationale=p.summary[:120],
                entrypoint=p.manifest_path,
            ))
    return bindings
