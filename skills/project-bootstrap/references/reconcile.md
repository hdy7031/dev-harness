# Reconcile plan/apply contract

Codex decides meaning; the standard-library helper checks mechanics. Plugin package `0.3.0`, plan protocol `1`, and Harness schema `2` are independent. Legacy AGENTS-only plans are rejected; regenerate them from current inspection.

## Inspect, plan, preview, apply

`HELPER` is this skill's absolute `scripts/bootstrap.py` path; `PROJECT` is the selected repository. Keep plan JSON outside the project, including outside all five outputs and their evidence sources.

```text
python HELPER PROJECT --inspect --read README.md --read planning/CONTEXT.md --read planning/DECISIONS.md
python HELPER PROJECT --plan PLAN.json --dry-run
python HELPER PROJECT --plan PLAN.json
python HELPER PROJECT
```

The last call is Maintain after a successful installation and must return `changed: []`. Seed/Maintain usage is in [SKILL.md](../SKILL.md); they need no migration inventory. Seed requires explicit `--mode seed`; missing Harness files never imply a semantically new project. A mature first installation can declare Reconcile with empty `rules` when AGENTS is absent. Maintain requires valid V2 metadata/profile and managed boundaries; it rejects reconciliation plans.

Inspect returns `install_state`, line inventory, `expected_before`, `read_set`, and absolute `pending_recovery` paths. It includes existing AGENTS in the read set; repeat `--read` for the other files Codex actually used. It does not discover dependencies or canonical authority. Paths must be normalized, project-relative, and contained. Output and canonical symlink/reparse ancestors and file-valued parents are rejected. Other read dependencies may resolve within the project, never outside it.

Every invocation, including inspect/dry-run, first acquires an OS lock keyed by the project's filesystem identity. Windows uses a global named mutex; POSIX uses `flock` on a persistent external `/tmp` inode. A competitor fails explicitly before recovery discovery or validation. The handle/descriptor remains held through apply, automatic rollback and cleanup. Process death releases it; a leftover unlocked POSIX inode is harmless. Recovery material still gates retries. Permission-denied or unavailable lock/storage operations fail closed. This serializes cooperating helpers on one host, not unrelated editors, network clients or manual recovery operations.

## Plan protocol 1 and decision read set

This example is structural: replace every hash and each absence claim with the actual inspect result, and supply project-specific evidence/reasons.

```json
{
  "protocol": 1,
  "mode": "reconcile",
  "mode_evidence": "Established application and knowledge ledger require reconciliation",
  "profile": "software",
  "profile_evidence": "User objective and README describe an offline product",
  "expected_before": {
    "AGENTS.md": "<SHA256 of exact original bytes>",
    "HANDOFF.md": null,
    "docs/PROJECT_CONTEXT.md": null,
    "docs/DECISIONS.md": null,
    ".harness/config.toml": null
  },
  "read_set": [
    {"path": "AGENTS.md", "sha256": "<SHA256>"},
    {"path": "README.md", "sha256": "<SHA256>"}
  ],
  "rules": [
    {"start": 1, "end": 1, "action": "drop", "reason": "Structural heading replaced by three layers"},
    {"start": 2, "end": 2, "action": "merge", "reason": "Covered by common kernel risk-proportional verification"},
    {"start": 3, "end": 3, "action": "invariant", "reason": "Unique stable offline delivery constraint"},
    {"start": 4, "end": 4, "action": "context", "reason": "Current architecture fact",
     "relocation_acknowledgement": "verbatim_safe"}
  ]
}
```

Mandatory top-level fields are those shown above. Optional fields are `invariants` and `canonical_sources`; unknown fields are rejected. A CLI mode/profile, if provided, must match the plan. Hashes are lowercase SHA256 of **exact bytes**, including BOM/newlines. Each read-set entry has exactly `path` and `sha256`, without duplicate paths. Dependencies must be existing regular files. AGENTS, when present, must be included. `expected_before` binds all five outputs: `null` means absent, distinct from a hash of an empty file.

Declare **every key project file actually used** to decide mode/profile, classification, invariants, context, decisions, drop/merge, canonical authority, already-preserved knowledge, or new evidence-backed rules. Include ordinary Harness destinations used in reasoning in `read_set` too; `expected_before` independently binds their bytes even if they were not semantic inputs. No filename-based dependency discovery occurs. A missing dependency is a caller contract violation the helper cannot detect. If an absence or directory inventory is decisive, document that limitation and re-inspect it before applying; protocol 1 binds files, not entire filesystem inventories.

Before recovery payloads, stages or project writes, apply rechecks the entire declared read set and all five output states. Drift gives **STALE PLAN -> STOP WITH ZERO PROJECT WRITES**, including no stage/backup payloads. Inspect/preview may create the OS lock and an empty private external storage container. Additional gates check dependencies and already-applied outputs, particularly before AGENTS removal. The OS lock prevents another helper from entering those gates concurrently; external writers remain outside its protection.

## Semantic inventory and routing

Read relevant rules/context/decisions/handoff and enough history to determine current meaning. Account for **every nonblank old AGENTS line**, including headings, with disjoint inclusive `start`/`end` ranges. Each rule requires `action` and a nonempty `reason`. Every `context`/`handoff`/`decision` rule also requires a nonempty `relocation_acknowledgement`. Optional fields are faithful `text` and `evidence_paths` (each path must be in the read set).

| Meaning | Action |
| --- | --- |
| Unique long-lived architecture/domain/data/product constraint | `invariant`, outside managed sections |
| Generic guidance covered by core/profile | `merge`, name the covering principle |
| Current project fact affecting future development | `context`, unless canonical source declared |
| Useful next-session continuation | `handoff` |
| Consequential choice and rationale | `decision`, unless canonical source declared |
| Obsolete instruction, replaced heading, or safely preserved knowledge | `drop`, explain the evidence and disposition |

Preserve uncertain unique knowledge; coverage is not semantic equivalence. Split mixed paragraphs or provide a faithful rewrite retaining every constraint. Nested/path-scoped AGENTS remain intact; do not hoist their rules globally. Keep historical phase/test counts explicitly historical. Bootstrap execution branch/HEAD/worktree/backup/push traces belong in the current report; use HANDOFF only when needed for unfinished continuation. Persistent project constraints, architecture, entry points, freezes, or evidence-verified canonical remotes may be current context.

New invariants use `"invariants": [{"text": "...", "evidence": "Why this is stable", "evidence_paths": ["README.md"]}]`. Reconcile requires nonempty bound evidence paths. Seed may use text/evidence alone, or omit the list when no facts are known.

### No helper knowledge equivalence

Ordinary destinations retain every existing byte and append **every planned route**, even if the same words already appear there or two planned chunks match. The helper does no substring, block, Markdown, fuzzy, quote/code/comment or invariant-content deduplication. An occasional duplicate is safer than suppressing the only formal source.

Codex may instead choose `drop` with an explicit already-preserved reason, include the preservation destination in `read_set`, and optionally cite it in `evidence_paths`. This is Codex's semantic decision; the helper does not prove equivalence. If a destination needs an authorized semantic merge first, perform it outside this migration and regenerate all bindings before applying.

### Routed references

All cross-document routes need relocation review, **including AGENTS -> HANDOFF in the same directory**, fragments, absolute links, plain prose and reference-style definitions. Codex checks the destination interpretation and declares `relocation_acknowledgement`, for example `verbatim_safe` or `rewritten`; a concrete explanatory string remains supported. `rewritten` requires plan `text`, which the helper uses. Missing/blank declarations are rejected without attempting to parse links, paths or Markdown. For example:

```json
{"start": 4, "end": 4, "action": "context", "reason": "Retain schema reference",
 "text": "[v2](../schemas/v2.json)",
 "relocation_acknowledgement": "rewritten"}
```

An acknowledgement alone requires Codex to check that unchanged references remain valid. Fragments may need an explicit document target; a moved reference-style use may need its definition moved or inlined. The helper checks declarations, not semantic correctness. Bind the files used for that judgment. Protocol 1 retains the existing string field and `text` representation; this unpublished contract tightens the acknowledgement requirement without introducing a new wire format.

## Canonical Context / Decisions

Authority requires explicit project guidance or a stable established workflow; finding STATUS/CONTEXT/ADR filenames is insufficient. Declare either role independently:

```json
{"canonical_sources": {
  "context": {"path": "planning/CONTEXT.md", "evidence": "Root AGENTS explicitly prescribes this authority"},
  "decision": {"path": "planning/DECISIONS.md", "evidence": "Established project workflow uses this ledger"}
}}
```

Each entry has exactly `path`/`evidence`. The source must be an existing regular project file and belong to `read_set`. Containment and `os.path.samefile` checks reject identity with **any existing Harness output**, regardless of path spelling. Canonical symlink/junction ancestors and all hardlink aliases are rejected, preventing self-bridges. Its exact bytes are hashed, never modified or copied into the bridge. The corresponding Harness doc directs sessions to read/update that source. Bind files used to establish its authority too.

If old knowledge is already present there, use `drop` with reason `already preserved in canonical source <path>` and optionally bound `evidence_paths`. This is Codex's semantic judgment, not helper deduplication. Unique missing knowledge blocks apply: update the ledger first outside bootstrap's write scope, then regenerate the plan. A declared canonical role combined with that same routing action is rejected, even with empty text.

Create a bridge only when absent; an existing same-target exact helper bridge accepts BOM/CRLF and remains byte-for-byte intact. Substantive content, extra facts, or another bridge target blocks apply. Resolve that uncertainty without overwriting it. Undeclared roles retain ordinary routing. Maintain preserves bridges without rediscovering authority or rewriting summaries when ledgers change.

## Staged writes and recovery

All structural, path, coverage, canonical, relocation, config, dependency and output-state checks complete before recovery payloads or project writes. Compute final bytes for every output first. The write protocol then:

1. Preflight supported access metadata for all existing outputs and verify same-filesystem storage. Before any payload or target write, use empty external probes to prove that existing owner/group and equivalent DACL grants can be installed with inheritance protection. Create a private external `.dev-harness-recovery-<id>` directory and manifest. Back up original **main-stream bytes** of existing outputs, AGENTS first; flush/fsync and verify each artifact. Store original access descriptors/protection and observed states as private manifest data, never as backup permissions.
2. Stage every changed final output in that external directory. Create and verify empty artifacts' permissions before writing payloads; flush/fsync and verify bytes. Persist stage basenames in the manifest. Validate **all** stage bytes/access metadata and recheck preconditions before any replacement.
3. Replace non-AGENTS outputs first, install the proven target access metadata after rename, and read-verify the complete supported state including protection. Persist each helper-committed state before the next output. Recheck dependencies and preservation destinations before replacing AGENTS **last**. Each replacement uses `os.replace`; there is no cross-file atomicity.
4. On handled failure, restore AGENTS first if touched. Only after verifying its restoration may destinations roll back. If source restoration fails, or an untouched source has concurrently changed, retain all applied destinations. Restore only a file whose complete current fingerprint matches the helper-committed state; unchanged complete originals require no restoration. Bytes alone never establish ownership. External drift retains the current file and private evidence, reports the differing fields, and marks `rollback-incomplete`. Retain originals and explicit recovery state on every failure, even a complete rollback.
5. After all outputs verify, mark committed and remove temporary artifacts. A cleanup failure reports committed outputs with recovery evidence; it does not undo preserved knowledge.

Failure may leave duplication; the protocol must not remove a source before preservation targets hold verified final bytes. Abrupt termination retains already-created manifests/original-byte artifacts instead of relying on Python exception handling; early preparation may be incomplete while the source is still untouched. Inspect lists pending recovery, with an inspection error if current outputs are malformed; **all further apply/dry-run calls refuse to proceed** until it is reviewed. No automatic replay or destructive recovery command exists.

Recovery locations are fixed by project filesystem identity: Windows uses the OS ProgramData folder; POSIX uses `/tmp`. Each project directory has a current-user-only protected Windows DACL or POSIX owner/mode `0700`. Existing storage with unexpected permissions/owner is rejected, including access by another user; it cannot silently fork recovery state. Paths do not depend on `TMP/TEMP/TMPDIR`. The helper refuses runtime storage inside any containing Git working tree or the selected project. Backups and stages therefore cannot appear in ordinary project `git add --all`. Successful cleanup deletes their payload directory; an empty private project container may remain. Inspect also gates any legacy root recovery directories.

For recovery, inspect the reported absolute directory and manifest `project`, `before`/`after`, `originals`, `staged`, `original_metadata`, `original_states`, `rename_states`, `intended_states`, `committed_states` and state against actual files. Stage basenames are relative to that directory. Hash-check originals before restoration; restore the source with its supported access metadata before removing duplicated knowledge. Windows descriptors are hex-encoded recovery data (owner/group/DACL/protection); POSIX access records contain owner/group/mode. A crash between rename and access installation leaves a private target: inspect its full state against the persisted private rename state and intended installed state. An ambiguous replace error may be rolled back only when its full state equals one of those precomputed states; never adopt a drifted file as committed. Review concurrent edits and retain unresolved backups. Manual restoration/cleanup must also hold `file_security.project_lock(root)`; it is not an automatic replay command. Once fully restored or knowingly accepted, delete only reviewed artifacts, inspect, and make a fresh plan. Never delete evidence merely to unblock a retry.

### File security and metadata limits

Every manifest, original-byte backup, stage, rollback payload and metadata record uses recovery storage's own private permissions, including when the source grants Everyone read access. Source DACLs are never applied to backup or staged payloads. On Windows, create/verify protected current-user-only file DACLs before writing payloads; on POSIX, payloads remain `0600` in private storage. Known absolute backup paths are covered by actual restricted-token opens, not directory obscurity.

For Windows existing destinations, preflight empty probes must reproduce owner/group and equivalent current grants with a protected DACL. Owner/group that cannot be reproduced or an unverifiable DACL/protection state stops before payload or target writes. After rename, `SetNamedSecurityInfoW` with `DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION` installs the saved DACL; inherited ACE provenance is cleared without changing current grants. Re-read owner/group, normalized ordered ACEs, DACL presence and `SE_DACL_PROTECTED`; checking ACE lists alone is insufficient. Future parent grants must not propagate. Rollback restores the saved original protection state, rather than always protecting it. New installed files remain private/protected. On POSIX, preserve supported owner/group/mode after rename; unsupported owners, special mode bits, file flags and xattrs (including extended ACLs) are rejected.

Rollback fingerprints contain main-stream SHA256, owner, group, normalized DACL and presence, DACL protection, Windows attributes, hardlink count, detected ADS names/sizes and integrity-label indicators (or POSIX mode/flags/xattrs). ADS and other unsupported indicators are observed without migrating them: any newly detected stream or metadata drift prevents restoration, including when main-stream bytes are unchanged. The manifest and error report name the differing fields. This detects drift within the supported boundary; it is not a complete filesystem snapshot.

Existing Windows ADS, explicit mandatory integrity labels, nonordinary attributes and hardlinked outputs are rejected during preflight. A missing/unsupported stream/security API also fails closed. The supported preservation scope is main-stream bytes plus the access metadata above. It does **not** promise timestamps, file identity, audit SACLs or all filesystem metadata. Raw backups are not complete file images. Unknown metadata outside this scope remains unsupported. Same-filesystem storage is mandatory for ordered `os.replace`; cross-volume projects/storage refuse before project writes. Storage loss/deletion by the OS or an external actor is outside crash-recovery guarantees.

Guarantees assume ordinary readable/writable storage and no adversarial concurrent mutation between final checks and filesystem operations. File fsync and ordered replace do **not** prove power-loss durability of directory metadata across all filesystems or filesystem-level multi-file atomicity. Disk/hardware corruption, external deletions, full Markdown semantics, omitted dependencies, and semantic misclassification are outside the mechanical guarantee. Original-byte artifacts and failure reports make those boundaries visible.

Config updates only ordinary `[harness]` version/profile scalars and validates that all other parsed values survive; Git metadata/comments remain intact. Nonstandard dotted/inline harness tables require narrow normalization preserving values first. The helper never contacts remotes, initializes Git, changes origins, or commits.

## Focused verification

Run `python scripts/test_bootstrap.py` from this skill, or its absolute path. Retain Seed/Profile, Reconcile, Maintain, canonical, boundary/config/execution-state and stale-binding regressions. Cover actual two-process competition, lock-owner death, Markdown/example routes, all-route relocation, hardlink/junction identity, restrictive Windows ACLs, restricted-token directory/manifest/known-path public-source backup access, external ACL tightening/ADS/protection/group/attribute drift followed by a real deny-delete replace failure, future parent inheritance with an unprotected positive control, Seed confidentiality, protection preflight failure, real ADS/integrity labels, Git dry-run after failure/crash, and every dynamically enumerated write checkpoint/partial-write position. Platform-only tests explicitly skip elsewhere. Private `--test-fault` / `--test-crash` / `--test-pause PHASE:NAME` flags are isolated test seams; pause uses stdin to schedule the competing process.

Review the semantic diff and five-file project scope, then repeat Maintain for idempotence. Review external recovery evidence if present. Do not run the host project's suite.
