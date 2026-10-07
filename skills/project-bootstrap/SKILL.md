---
name: project-bootstrap
description: Seed, reconcile, or maintain a lightweight project harness with software, research, or competition priorities when asked to bootstrap or organize project guidance. Do not use for routine coding in an initialized project.
---

# Project bootstrap

Work in the selected project. Inspect its objective, structure, existing guidance/knowledge and Git root, branch, HEAD, changes and remotes. Preserve existing work; do not create a repository or guess remote URLs.

The durable write scope is `AGENTS.md`, `HANDOFF.md`, `docs/PROJECT_CONTEXT.md`, `docs/DECISIONS.md` and `.harness/config.toml`. AGENTS places project-specific invariants first, outside managed [core](assets/core.md) and [profile](assets/profiles/) sections. Locks and private staging/recovery stay outside Git working trees. Do not introduce phases, traits, extra profiles/skills, MCP, hooks, CI or host-project tests.

## Choose stance and mode

Infer one profile from the objective and evidence: **software** for product delivery, **research** for scientific evidence, **competition** for scored deliverables under a deadline. `paper/` alone is ambiguous. Read only the selected profile; preserve a valid configured profile unless the objective changed. Ask only if ambiguity materially changes the stance.

Use the standard-library Python 3.11+ [helper](scripts/bootstrap.py). `HELPER` and `PROJECT` are their absolute paths:

```text
python HELPER PROJECT --inspect --read README.md --read src/relevant.py
```

Inspect reports mechanical `install_state`, never semantic newness. Codex chooses:

- **Seed:** New/light project without meaningful prior guidance. Read README, relevant source/tests and ordinary docs; synthesize real knowledge through the plan below. No-plan `--mode seed --profile software` is for genuinely unevidenced projects; the [assets](assets/harness/) then state honest empty layers.
- **Reconcile:** Mature project with prior guidance/knowledge but no valid V2, including first installation with all five outputs absent. Inventory and re-edit knowledge by decision value; absence of Harness alone does not justify Seed.
- **Maintain:** Valid configured V2. Compare current evidence with existing knowledge, following bridges. No durable change means omit the plan and preserve knowledge bytes. A consequential fact, boundary, choice or continuation change means submit a plan for only the affected layers.

## One evidence-backed knowledge plan

Read the [plan/apply contract](references/reconcile.md) when making knowledge changes in any mode. Bind every actual decision input with `--read` and all five output states. Submit `knowledge` entries containing `layer`, final `text`, `reason` and nonempty `evidence_paths` from that read set. One entry replaces one complete layer: the stable invariant block or an entire Context/Decisions/Handoff document. Omitted layers remain intact. Preview `--plan PLAN --dry-run`, review final files, then apply the same plan.

Codex decides what matters, its layer, authority, compression and organization. The helper checks declared evidence, SHA/expected-before, coverage, relocation declarations and safe writes. It does not classify, deduplicate, discover omitted dependencies or prove semantic preservation.

- **AGENTS invariants:** Long-lived architecture/domain/data/product contracts. Put the most consequential hard boundaries first, ahead of generic guidance.
- **Context:** Current facts, stage, actual verification and material unverified limits. Reference stable README/experiment evidence when it already owns these facts.
- **Decisions:** Consequential choices and evidenced rationale. Do not invent reasons from implementation alone.
- **Handoff:** Active goal, blocker and next concrete action. Keep only details needed to continue; reference stable knowledge elsewhere.

Seed extracts a small amount of project-specific knowledge from files actually read. Do not fill every layer by invention. If evidence establishes no decision or continuation, say so explicitly, e.g. “No consequential decisions have been established” or “No active handoff”.

Reconcile is semantic re-editing: merge duplicates, rewrite/reorder, regroup and rename headings, retire generic advice covered by core/profile, and move dynamic facts out of AGENTS. Account for every nonblank old AGENTS line using `rules`, explaining where each meaningful constraint survives. Supply final `knowledge` text for routed layers instead of appending migration blocks. Bind existing destinations before replacement; review preservation, not merely coverage. Nested/path-scoped AGENTS remain intact.

Maintain makes the smallest durable refresh. Completed real-engine validation, changed backend boundaries, an evidenced experiment policy or new continuation may require Context/Decisions/Handoff updates or new source entrances. Ordinary bug fixes and test-total changes alone remain a no-op. Pending verification, current experiment settings and next-stage goals are dynamic, not invariants. Local install paths, PATH operations, one-off logs and test totals usually stay in original execution evidence.

Every cross-document route needs relocation acknowledgement, including same-directory moves. Check final references relative to their destination. Old AGENTS wording is evidence, not a required output format.

## Authority and operational boundaries

Preserve canonical Context/Decisions sources established by explicit project guidance or a stable workflow; filenames alone do not establish authority. Follow bridges to the actual sources before judging current knowledge, including during Maintain. Use short entrances or bridges instead of copying ledgers or detailed experiment reports. New authority can be declared in any mode. Replacing substantive content with a bridge requires a bound destination and explicit knowledge-disposition acknowledgement. Missing unique knowledge blocks replacement until the canonical source is updated outside this five-file helper. Never synthesize a second ledger over an existing bridge.

Config stays at Harness `version = 2`; plugin and Plan Protocol versions are independent. Preserve unrelated Git metadata/comments. Add observed canonical remote metadata only with local evidence and reachability; leave uncertain origins unchanged. The helper never contacts or changes Git remotes.

Every invocation holds an OS project lock through validation, apply/rollback and cleanup. Stale bindings, malformed boundaries, newer schemas, unsafe paths and unresolved recovery stop before target writes. Private recovery/staging must share the project's filesystem and stay outside Git; storage selection and existing access permissions use the same contract. Recovery covers main-stream bytes and supported access metadata, not every filesystem property. Preserve recovery evidence for review; never delete it just to unblock a retry.

## Verify and stop

Read all five final files and the semantic diff: useful specific knowledge, honest empty states, stable/dynamic separation, readable hierarchy, preserved constraints, valid references and no second fact source. Repeat without the plan to confirm `changed: []`. Report profile/mode, changed layers, retired knowledge and reasons, uncertainty and recovery state. Do not run the host project's suite or commit/push without authorization.
