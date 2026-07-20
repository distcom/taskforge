"""Tests for plugin discovery, indexing, and assignment."""

from pathlib import Path

import pytest

from taskforge.models import WorkSegment
from taskforge.plugins import PluginIndex, assign_plugins, scan_plugins


@pytest.fixture
def plugin_root(tmp_path: Path) -> Path:
    """Create a temp plugin root with sample plugins."""
    p1 = tmp_path / "code-review"
    p1.mkdir()
    (p1 / "PLUGIN.md").write_text(
        "---\nname: code-review\ndescription: Automated code review with static analysis\n"
        "categories: review, quality, static-analysis\nuse_case: Review pull requests and code changes\n---\n"
        "# Code Review Plugin\nPerforms automated code review.\n", encoding="utf-8",
    )
    p2 = tmp_path / "data-pipeline"
    p2.mkdir()
    (p2 / "PLUGIN.md").write_text(
        "---\nname: data-pipeline\ndescription: ETL data pipeline builder with validation\n"
        "categories: data, etl, pipeline\nuse_case: Build and validate data transformation pipelines\n---\n"
        "# Data Pipeline Plugin\nBuilds ETL pipelines.\n", encoding="utf-8",
    )
    (tmp_path / "no-manifest").mkdir()
    return tmp_path


class TestScanPlugins:
    def test_finds_valid_plugins(self, plugin_root: Path):
        plugins = scan_plugins([plugin_root])
        assert len(plugins) == 2
        names = {p.display_name for p in plugins}
        assert "code-review" in names
        assert "data-pipeline" in names

    def test_skips_missing_manifest(self, plugin_root: Path):
        plugins = scan_plugins([plugin_root])
        assert all(p.display_name != "no-manifest" for p in plugins)

    def test_nonexistent_root(self):
        assert scan_plugins([Path("/no/such/path")]) == []

    def test_dedup_first_wins(self, tmp_path: Path):
        r1 = tmp_path / "r1" / "dup"
        r1.mkdir(parents=True)
        (r1 / "PLUGIN.md").write_text("---\nname: dup\ndescription: First\n---\n")
        r2 = tmp_path / "r2" / "dup"
        r2.mkdir(parents=True)
        (r2 / "PLUGIN.md").write_text("---\nname: dup\ndescription: Second\n---\n")
        plugins = scan_plugins([tmp_path / "r1", tmp_path / "r2"])
        assert len(plugins) == 1
        assert plugins[0].summary == "First"


class TestPluginIndex:
    def test_query_relevance(self, plugin_root: Path):
        idx = PluginIndex(scan_plugins([plugin_root]))
        results = idx.query("code review static analysis")
        assert results[0].display_name == "code-review"

    def test_query_data(self, plugin_root: Path):
        idx = PluginIndex(scan_plugins([plugin_root]))
        results = idx.query("ETL data transformation")
        assert results[0].display_name == "data-pipeline"

    def test_empty_query(self, plugin_root: Path):
        idx = PluginIndex(scan_plugins([plugin_root]))
        assert len(idx.query("")) == 2

    def test_serialize_roundtrip(self, plugin_root: Path):
        idx = PluginIndex(scan_plugins([plugin_root]))
        restored = PluginIndex.restore(idx.serialize())
        assert restored.count == idx.count


class TestAssignment:
    def test_assigns_plugins(self, plugin_root: Path):
        idx = PluginIndex(scan_plugins([plugin_root]))
        segments = [
            WorkSegment(segment_id="s1", objective="Review code changes for quality"),
            WorkSegment(segment_id="s2", objective="Build ETL data pipeline"),
        ]
        bindings = assign_plugins(idx, segments)
        assert len(bindings) >= 2
        s1 = [b for b in bindings if "s1" in b.segment_ids]
        assert any(b.plugin_id == "code-review" for b in s1)

    def test_updates_candidates(self, plugin_root: Path):
        idx = PluginIndex(scan_plugins([plugin_root]))
        segments = [WorkSegment(segment_id="s1", objective="code review")]
        assign_plugins(idx, segments)
        assert len(segments[0].plugin_candidates) > 0
