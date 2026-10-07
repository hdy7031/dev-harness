---
name: project-bootstrap
description: Seed, reconcile, or maintain a lightweight project harness with software, research, or competition priorities when asked to bootstrap or organize project guidance. Do not use for routine coding in an initialized project.
---

# Project bootstrap

Work in the selected project. Inspect its structure, user goal, existing guidance/context/decisions, and Git root, branch, HEAD, changes, and remotes if available. Preserve existing work; do not create a repository or guess remote URLs.

The durable project write scope is `AGENTS.md`, `HANDOFF.md`, `docs/PROJECT_CONTEXT.md`, `docs/DECISIONS.md`, and `.harness/config.toml`. Compose AGENTS from the short [common kernel](assets/core.md), one [profile stance](assets/profiles/), and stable project-specific invariants outside managed sections. OS locks and private staging/recovery storage stay outside Git working trees. Do not introduce traits, phases, extra skills, MCP, hooks, CI, or host-project tests.

## Choose stance and semantic mode

Infer one primary profile from user intent and project evidence; the objective outweighs file counts. Product/app/frontend/backend/electron suggests **software**; experiments/models/results/datasets suggests **research**; problem statements/submission/contest/deadline context suggests **competition**. `paper/` alone is ambiguous. Read only the selected profile. Preserve a valid configured profile unless the objective changed. If ambiguity materially affects the stance, ask once about the primary objective while continuing independent inspection.

Use the standard-library Python 3.11+ [helper](scripts/bootstrap.py). `HELPER` means its absolute path; `PROJECT` means the selected project directory:

```text
python HELPER PROJECT --inspect
```

Inspect reports mechanical `install_state` (`absent`, `unmanaged/legacy`, `managed-v2`), never semantic newness. Codex chooses:

- **Seed:** New/light project without meaningful prior rules or a Harness. Explicitly run `--mode seed --profile software --dry-run`, review, then repeat without `--dry-run`. Use missing-file [assets](assets/harness/); invent no invariants. End with the checks below.
- **Maintain:** Valid configured V2 with managed sections. Run `--dry-run`, review, then apply if needed. The configured profile is the default; change it only when the objective changed. Preserve all unmanaged text and existing knowledge bytes. An identical invocation is a no-op. End with the checks below.
- **Reconcile:** Mature project with existing rules/context but no valid managed V2, including a first installation with all five outputs absent. Read the full [Reconcile contract](references/reconcile.md), inventory prior knowledge, and submit an evidence-backed plan. Do not substitute Seed because the Harness is absent.

Every helper invocation holds a project-level OS lock from before inspection/recovery checks through rollback and cleanup; competing helpers fail explicitly. Process death releases the lock, while retained recovery still blocks further apply. Malformed boundaries, newer schemas, stale plans, unsafe paths, and unresolved recovery evidence stop before target writes. Missing legacy boundaries require Reconcile; repair malformed boundaries narrowly while preserving their contents before continuing.

## Knowledge and configuration boundaries

Codex owns semantic mode/profile, rule classification, canonical authority, evidence interpretation, and reference relocation. Bind all decision inputs in the declared read set and all five output states. Every cross-document route needs an explicit relocation acknowledgement, including same-directory moves. The helper executes routes without knowledge-equivalence or destination-body deduplication; already-preserved knowledge needs an explicit `drop` reason and bound destination. It cannot prove semantic preservation or discover an omitted dependency.

Keep stable architecture/domain/data/product constraints in invariants. Route continuation to HANDOFF, current project facts to PROJECT_CONTEXT, and consequential choices with rationale to DECISIONS. Read Decisions when history matters; follow canonical bridges to their named sources. Do not present historical progress/test counts as current verification, or store bootstrap execution branch/HEAD/worktree/backup traces as durable project facts.

Preserve established canonical Context/Decisions sources supported by explicit guidance or a stable workflow; filenames alone do not establish authority. Harness docs serve as thin bridges. Unique knowledge missing from a canonical source blocks Reconcile until that source is updated outside bootstrap's five-file scope. The full contract covers existing destinations and relocation acknowledgements.

Config keeps Harness `version = 2` and the chosen profile. Preserve existing Git metadata/comments exactly. Add observed remote metadata only with local evidence and reachability; leave suspicious/unreachable origins unchanged and report uncertainty. The helper never discovers or changes Git metadata.

The [contract](references/reconcile.md) defines the file-security boundary: existing access permissions are checked before replacement, raw backups remain private and outside Git, and unsupported ADS/extended metadata fail closed. Recovery preserves main-stream bytes and supported access metadata, not every filesystem property. Storage must support the lock, permissions and same-filesystem rename.

## Verify and stop

Check the five files, managed boundaries, invariants outside them, preservation of meaningful prior knowledge, and only intended edits. Read the semantic diff: coverage establishes consideration, not correctness. Repeat without a Reconcile plan to confirm `changed: []`. Report stance/mode, routed/retired knowledge and reasons, uncertainty, and any recovery state. Do not run the host project's suite or commit/push without authorization.
