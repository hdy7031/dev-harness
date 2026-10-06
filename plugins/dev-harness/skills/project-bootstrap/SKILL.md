---
name: project-bootstrap
description: Seed, reconcile, or maintain a lightweight project harness with software, research, or competition priorities when asked to bootstrap or organize project guidance. Do not use for routine coding in an initialized project.
---

# Project bootstrap

Work in the selected project. Inspect its structure, user goal, existing guidance/context/decisions, and Git root, branch, HEAD, changes, and remotes if available. Bootstrap does not require creating a Git repository. Preserve existing work; never guess remote URLs.

Change only `AGENTS.md`, `HANDOFF.md`, `docs/PROJECT_CONTEXT.md`, `docs/DECISIONS.md`, and `.harness/config.toml`. Compose AGENTS from the short [common kernel](assets/core.md), one [profile stance](assets/profiles/), and project-specific invariants outside managed sections. Profiles guide decisions, not mandatory workflows. Do not introduce traits, phases, extra skills, MCP, hooks, CI, or host-project tests.

## Choose the stance and mode

Infer one primary profile from current user intent, project docs, and structure; the objective outweighs file counts. Product/app/src/frontend/backend/electron suggests **software**; experiments/notebooks/models/training/results/datasets suggests **research**; problem statements/attachments/submission/contest/deadline context suggests **competition**. `paper/` alone is ambiguous. Read only the selected profile asset. Preserve a valid configured profile unless evidence shows the objective changed. When ambiguity materially affects the stance, ask once: “What is the primary objective of this repository right now: product delivery, research evidence, or competition scoring?” Do independent inspection while awaiting the answer.

- **Seed:** A new/light project without harness or meaningful prior rules. Create the minimal five files, with few evidence-backed invariants; invent none. Use [assets/harness](assets/harness/) only for missing files.
- **Reconcile:** A mature project with existing rules/context but no managed V2 harness, including V1 upgrades. Read [reconciliation](references/reconcile.md). Inventory and semantically reorganize existing guidance instead of appending a template. Retain unique knowledge; account for every old rule.
- **Maintain:** A configured harness with valid managed sections. Update common/profile blocks and version only when needed; preserve all unmanaged text and existing context/handoff/decisions. A repeat invocation alone is no reason to rewrite files. Missing legacy boundaries require Reconcile; malformed boundaries require a narrow repair preserving their content before continuing.

## Apply the result

Use the standard-library Python 3.11+ helper [scripts/bootstrap.py](scripts/bootstrap.py); usage and plan format are in [references/reconcile.md](references/reconcile.md). Codex judges meaning and prepares the reconciliation plan; the helper checks coverage and performs deterministic writes. Inspect first, then apply once the semantic plan is complete. Seed can run without a plan; Maintain needs none. The helper refuses malformed boundaries, incomplete/stale plans, and newer harness versions before writing.

Keep only stable architecture/domain/data/product rules and long-lived constraints in project-specific invariants. Route current stage/architecture facts to `docs/PROJECT_CONTEXT.md`, next-session continuation to `HANDOFF.md`, and consequential decisions with rationale to `docs/DECISIONS.md`. Do not present historical test counts or phase status as current verified facts. Merge into existing destination sections without duplication or loss of unrelated content.

Config records `[harness]`, `version = 2`, and the primary `profile`. Preserve existing Git metadata exactly. Add an observed remote name or `git.verified_canonical_remote` only when local evidence and reachability justify it; leave suspicious/unreachable origin unchanged and explain uncertainty. The helper does not infer or change Git metadata.

## Verify and stop

Check only that the five files exist, meaningful prior rules survive in appropriate locations, generic guidance is not duplicated, managed boundaries are well formed, invariants remain outside them, a second identical run changes no bytes, and the diff contains only intended harness edits. Coverage checks establish that rules were considered; read the diff to verify semantic preservation. Report stance/mode, moved or retired rules and their reasons, and material uncertainty. Do not run the host project's suite or commit/push without authorization.
