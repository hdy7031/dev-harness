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

- `$dev-harness:project-bootstrap` adapts project guidance to **software**, **research**, or **competition** priorities. It chooses **Seed** for new projects, **Reconcile** for mature projects, including first Harness installation, or **Maintain** for an initialized harness. Profiles express decision priorities rather than fixed workflows.
- `$dev-harness:project-handoff` refreshes `HANDOFF.md` for the next session.
- `$dev-harness:git-recovery` diagnoses and repairs common Git failures while preserving existing work.

Bootstrap V2 places repository-specific hard boundaries ahead of a short common kernel and profile stance in `AGENTS.md`. Seed, Reconcile and Maintain share an evidence-backed knowledge plan: Codex selects, edits and compresses stable contracts, current facts, consequential decisions and continuation; the helper validates bindings and writes the final layers. Reconcile can re-edit prior guidance, and Maintain changes only layers with durable new knowledge. No durable change remains `changed: []`.

Plan Protocol 2 binds the declared decision read set and all five output states in every mode: stale plans cause zero project writes. Every synthesized layer binds files actually read. Existing canonical Context/Decisions sources remain thin bridges; detailed README/experiment ledgers stay authoritative. Handoff replaces stale continuation without repeating stable knowledge. The helper performs no semantic classification or deduplication.

Each invocation holds an OS project lock through recovery checks, apply/rollback and cleanup. Routes require Codex's explicit relocation acknowledgement; the helper never infers knowledge equivalence from destination text.

Verified stages and original-byte recovery evidence use their own private permissions outside Git working trees; source permissions are private manifest data, never backup ACLs. Existing owner/group and equivalent DACL grants are proved before replacement, then installed with verified future-inheritance protection. Rollback requires complete supported-state ownership and preserves external ACL/ADS/metadata mutations with `rollback-incomplete`. Windows ADS and known unsupported metadata are rejected at preflight. Recovery covers main-stream bytes and supported access metadata, not complete filesystem metadata. Same-filesystem storage is required; unsupported permissions/storage fail closed. This remains an ordered recovery protocol without multi-file atomicity. See the [plan/apply contract](skills/project-bootstrap/references/reconcile.md).

State storage is selected automatically on the project's filesystem, outside any Git working tree. Existing same-volume storage is reused; non-system Windows volumes use a private project-identity container beside the project or a writable outer ancestor. Old recovery and permission drift still block retries.

The bootstrap helper requires **Python 3.11 or later** and uses only the standard library. Plugin package version `0.3.1`, Plan Protocol `2` and generated harness version `2` are separate version numbers.

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
