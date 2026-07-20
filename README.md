# TaskForge

**High-performance task orchestration engine for AI agents.**

TaskForge decomposes complex objectives into governed pipeline stages, coordinates
plugin execution, enforces delivery verification, and supports full session resumability —
all with zero external dependencies (pure Python 3.10+ stdlib).

---

## Pipeline Stages

Every task flows through six deterministic stages:

| # | Stage | Purpose |
|---|-------|---------|
| 1 | **VALIDATE** | Parse and normalize the incoming objective |
| 2 | **CLARIFY** | Extract intent, outputs, and constraints |
| 3 | **FREEZE** | Seal the requirement document (approval gate) |
| 4 | **STRATEGIZE** | Build an execution plan with work segments (approval gate) |
| 5 | **EXECUTE** | Run work units respecting dependency topology |
| 6 | **FINALIZE** | Verify delivery against acceptance criteria (approval gate) |

Approval gates halt the pipeline until explicit user consent is provided.

---

## Key Features

- **Governed pipeline** — deterministic stage machine with approval gates
- **Plugin discovery** — scan filesystem roots for `PLUGIN.md` manifests
- **Keyword-scored matching** — relevance-ranked plugin-to-segment assignment
- **Dependency-aware execution** — sequential or parallel wave topology
- **Delivery verification** — six structured acceptance checks
- **Session persistence** — full JSON serialization for resume from any point
- **Zero dependencies** — pure stdlib, installs anywhere Python 3.10+ runs

---

## Installation

```bash
pip install -e ".[dev]"
```

---

## CLI Usage

```bash
# Start a new task session
taskforge run "Build a REST API with authentication"

# Check session status
taskforge status <session-id>

# List all sessions
taskforge sessions

# Run delivery verification
taskforge verify <session-id>

# List discovered plugins
taskforge plugins
```

All commands accept `--workspace <path>` to set the project root and `--json` for
machine-readable output.

---

## Plugin System

Plugins are discovered from directories listed in `~/.taskforge/roots.json` (global)
or `<workspace>/.taskforge/roots.json` (project-local):

```json
{
  "roots": ["/path/to/plugins"]
}
```

Each plugin lives in its own folder with a `PLUGIN.md` manifest:

```markdown
---
name: my-plugin
description: What the plugin does
categories: tag1, tag2
use_case: When to use this plugin
---

# My Plugin

Detailed instructions for the AI agent...
```

---

## Architecture

```
src/taskforge/
├── __init__.py      # Package metadata
├── models.py        # Domain models (stages, sessions, plans, units)
├── engine.py        # Pipeline state machine with gate enforcement
├── plugins.py       # Plugin discovery, indexing, and assignment
├── strategy.py      # Intent extraction, requirement sealing, plan building
├── runner.py        # Dependency-aware execution coordinator
├── verify.py        # Six-check delivery verification
├── vault.py         # Session persistence (JSON serialization)
└── cli.py           # Command-line interface
```

---

## Running Tests

```bash
pytest
```

---

## License

MIT — see [LICENSE](LICENSE).
