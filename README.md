# Dev Harness

A lightweight Codex plugin for adapting project guidance, preparing session handoffs, and recovering from Git failures. The repository root is the plugin root; there are exactly three skills and no MCP servers, hooks, or mandatory CI.

## Install

Clone the repository and register its local marketplace:

```powershell
git clone https://github.com/hdy7031/dev-harness.git
cd dev-harness
codex plugin marketplace add . --json
codex plugin add dev-harness@personal --json
```

The marketplace name is `personal`. If you already use that name for another marketplace, inspect your registration before replacing it. Existing Dev Harness users should refresh the same `dev-harness@personal` installation.

Codex loads the installed cache rather than the development directory. After an update, fully quit and reopen Codex Desktop, then start a fresh chat to pick up the changed skills.

## Use

- `$dev-harness:project-bootstrap` adapts project guidance to **software**, **research**, or **competition** priorities. It chooses **Seed** for new projects, **Reconcile** for existing guidance, or **Maintain** for an initialized harness. Profiles express decision priorities rather than fixed workflows.
- `$dev-harness:project-handoff` refreshes `HANDOFF.md` for the next session.
- `$dev-harness:git-recovery` diagnoses and repairs common Git failures while preserving existing work.

Bootstrap V2 composes `AGENTS.md` from a short common kernel, a profile stance, and repository-specific invariants. Managed boundaries allow common/profile updates while preserving unique project rules. Changing state belongs in `HANDOFF.md`, `docs/PROJECT_CONTEXT.md`, and `docs/DECISIONS.md`.

The bootstrap helper requires **Python 3.11 or later** and uses only the standard library. Plugin package version `0.2.1` and generated harness version `2` are separate version numbers.

## Layout

```text
.codex-plugin/plugin.json       Plugin identity and metadata
.agents/plugins/marketplace.json Local installation entry, pointing to ./
skills/project-bootstrap/       V2 guidance, profile assets, and helper
skills/project-handoff/         Session continuation
skills/git-recovery/            Safe Git diagnosis and recovery
```

## Develop

Edit the source in this repository, review the diff, validate JSON manifests and Skill frontmatter/resource paths, and reinstall with `codex plugin add dev-harness@personal --json`. Re-register the marketplace if the source directory moves. Restart Desktop and use a fresh chat to verify discovery.

Run the focused bootstrap behavior tests only when its implementation changes:

```powershell
python skills/project-bootstrap/scripts/test_bootstrap.py
```

## License

[MIT](LICENSE). Copyright (c) 2026 hdy7031.
