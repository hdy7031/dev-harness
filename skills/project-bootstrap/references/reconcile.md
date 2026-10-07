# Evidence-backed knowledge plan / apply contract

Codex decides meaning; the standard-library helper checks mechanics. Plan Protocol **2** and Harness schema **2** are independent. Regenerate Protocol 1 plans; this change does not alter the generated Harness schema or transaction protocol.

## Inspect, synthesize, preview, apply

`HELPER` is the absolute `scripts/bootstrap.py` path; `PROJECT` is the selected directory. Keep plan JSON outside the project and its evidence sources.

```text
python HELPER PROJECT --inspect --read README.md --read src/backend.py --read docs/EXPERIMENT.md
python HELPER PROJECT --plan PLAN.json --dry-run
python HELPER PROJECT --plan PLAN.json
python HELPER PROJECT
```

Use one plan for **seed**, **reconcile** or **maintain**. Seed requires absent outputs; Reconcile is for mature/unmanaged projects, even with absent outputs; Maintain requires configured managed V2. No-plan Seed creates honest empty layers. No-plan Maintain updates managed core/profile while preserving all knowledge bytes. Identical output bytes produce `changed: []` and no timestamp changes.

Inspect returns `install_state`, old AGENTS `legacy_lines` and `unmanaged_lines` inventory (the latter includes exact line numbers outside managed spans for Maintain rewriting), `expected_before`, declared `read_set`, `state_root` and pending recovery. Include every actual decision file with `--read`: README, source, tests, ordinary/canonical docs, existing destinations and authority evidence. File hashes bind exact bytes, including BOM/newlines. Directory/absence inventories are not bound; re-inspect any decisive ones before apply. The helper neither discovers missing dependencies nor proves that the caller actually read a declared file.

## Plan Protocol 2

Mandatory fields for every supplied plan are `protocol`, `mode`, `mode_evidence`, `profile`, `profile_evidence`, `expected_before` and `read_set`. Optional fields are `rules`, `knowledge`, `invariants` and `canonical_sources`; unknown fields are rejected. CLI mode/profile must agree. `rules` is required for Reconcile and for a Maintain invariant-block replacement; empty is valid when no old guidance exists.

```json
{
  "protocol": 2,
  "mode": "seed",
  "mode_evidence": "New project with no previous guidance",
  "profile": "research",
  "profile_evidence": "README describes controlled OCR experiments",
  "expected_before": {
    "AGENTS.md": null,
    "HANDOFF.md": null,
    "docs/PROJECT_CONTEXT.md": null,
    "docs/DECISIONS.md": null,
    ".harness/config.toml": null
  },
  "read_set": [
    {"path": "README.md", "sha256": "<exact lowercase SHA256>"},
    {"path": "src/backend.py", "sha256": "<exact lowercase SHA256>"}
  ],
  "knowledge": [
    {
      "layer": "invariant",
      "text": "- Backends return Recognition(text, spans); the batch pipeline remains engine-independent.",
      "reason": "Public backend contract is stable across sessions",
      "evidence_paths": ["README.md", "src/backend.py"]
    },
    {
      "layer": "context",
      "text": "# Project Context\n\nControlled glyph fixtures exercise the pipeline. Real-engine recognition and real scans remain unverified; see [scope](../README.md).\n",
      "reason": "Preserve actual validation boundaries, not generic scaffold prose",
      "evidence_paths": ["README.md"]
    }
  ]
}
```

This is structural: substitute actual inspection hashes and project evidence. Each read-set entry has exactly normalized project-relative `path` and lowercase `sha256`; duplicate paths, missing/nonregular files and escapes are rejected. AGENTS, when present, must be declared. Bind all five `expected_before` states: `null` means absent, distinct from an empty file hash. Hash/output drift rejects with **STALE PLAN -> ZERO PROJECT WRITES**, before stage/backup payloads. Bindings are checked again during apply, including before AGENTS replacement.

### Caller-authored final knowledge

Each `knowledge` entry has exactly `layer`, nonempty `text`, nonempty `reason` and nonempty `evidence_paths` drawn from `read_set`. Supported layers are `invariant`, `context`, `decision`, `handoff`, at most one entry per layer. The model edits/compresses/groups all facts for that layer into its final text. The helper does not decide what to retain, classify, merge or deduplicate.

- `invariant` replaces the entire project-specific stable block, outside managed sections and ahead of core/profile in newly composed AGENTS. A Maintain replacement must inventory all old unmanaged AGENTS lines; managed spans are excluded from required coverage.
- Other entries replace the entire corresponding document, preserving original BOM/newline style. Existing destinations must belong to `read_set`. Explain preservation/retirement of their knowledge in `reason`; the helper cannot prove semantic losslessness.
- Omitted layers stay intact; absent layers use explicit empty states. An empty state is nonempty text explaining what is unknown or inactive, never a fabricated decision or continuation.
- A submitted final layer takes precedence over raw routed chunks for that layer. Do not submit competing rewrites. Review relocated references in the final destination.

For Seed, capture a few evidenced contracts and verification boundaries rather than filling every heading. For Reconcile, submit edited final layers, not template plus pasted old AGENTS. For Maintain, submit only layers with durable changes. A bug fix, a changed test total or a local setup path alone is insufficient. Detailed experiment results should remain in their existing source, reached through a short entrance or bridge.

The older `invariants` field still accepts `[{"text":"...", "evidence":"...", "evidence_paths":["README.md"]}]` for bound additive Seed/Reconcile constraints. Prefer `knowledge` for grouped/re-edited final blocks; Maintain rewriting requires an `invariant` knowledge entry. Every new invariant binds nonempty evidence in all modes.

## Old AGENTS inventory and relocation

Account for every nonblank old AGENTS line, including headings, with disjoint inclusive `start`/`end` ranges. Each rule requires `action` and a concrete `reason`. Optional fields are faithful `text`, `evidence_paths` from the read set and `relocation_acknowledgement`.

| Disposition | Action |
| --- | --- |
| Stable project contract retained in the final invariant block | `invariant` |
| Generic advice covered by core/profile | `merge`, naming the covering principle |
| Current facts / consequential rationale / active continuation | `context` / `decision` / `handoff` |
| Replaced heading, obsolete rule or knowledge already preserved in a bound source | `drop`, explaining its disposition |

Merge duplicate constraints, rewrite and reorganize by decision value without losing unique knowledge. Do not hoist nested/path-scoped AGENTS globally. The inventory establishes consideration, not semantic equivalence. Use final `knowledge` layers for semantic re-editing; if omitted, raw routed chunks are preserved by appending, without destination deduplication. This fallback is useful for explicit verbatim transfers, not the normal Reconcile result.

Every `context`/`decision`/`handoff` rule requires explicit nonempty relocation acknowledgement, even same-directory moves, plain references, fragments and absolute links. `rewritten` also requires rule `text`. The helper checks declarations, not Markdown correctness. Codex checks both route text and final synthesized references in their new document location.

## Canonical authority and bridges

Canonical authority requires explicit guidance or a stable workflow, including README/experiment documents that already own current facts or policy. Declare either role in any mode:

```json
{"canonical_sources": {
  "context": {"path": "planning/CONTEXT.md", "evidence": "Root guidance explicitly names this authority"},
  "decision": {"path": "docs/EXPERIMENT.md", "evidence": "Established experiment policy and rationale live here"}
}}
```

Each entry requires `path` and `evidence`; optional `replacement_acknowledgement` explains where existing destination knowledge survives when converting substantive text or retargeting a bridge. Such replacement also requires the destination in `read_set`. This is an explicit caller decision; the helper does not prove equivalence. Without it, substantive/different-target existing destinations fail closed. Exact same-target helper bridges retain original bytes, including BOM/CRLF.

Sources must be bound existing regular project files. Reject source identity with any Harness output, hardlinks and symlink/junction ancestors, including in-root aliases. Sources are never changed or copied. A canonical role conflicts with raw routing or synthesized knowledge for that role. An existing exact helper bridge cannot be overwritten by synthesized knowledge even if the caller omits the declaration. Follow its actual source before maintaining knowledge or composing a handoff.

Use `drop` with an explicit already-preserved reason for old knowledge in the canonical source; bind that source. Unique missing knowledge blocks replacement until the source is updated outside this helper's five-file scope and bindings are regenerated. When a ledger changes, the bridge stays intact; update continuation only if the next action changes. A no-plan Maintain never rediscovers authority or copies ledger contents.

## Staged writes and recovery

All structural, path, coverage, canonical, relocation, config, dependency and output-state checks complete before recovery payloads or project writes. Compute final bytes for every output first. The write protocol then:

1. Preflight supported access metadata for all existing outputs and verify same-filesystem storage. Before any payload or target write, use empty external probes to prove that existing owner/group and equivalent DACL grants can be installed with inheritance protection. Create a private external `.dev-harness-recovery-<id>` directory and manifest. Back up original **main-stream bytes** of existing outputs, AGENTS first; flush/fsync and verify each artifact. Store original access descriptors/protection and observed states as private manifest data, never as backup permissions.
2. Stage every changed final output in that external directory. Create and verify empty artifacts' permissions before writing payloads; flush/fsync and verify bytes. Persist stage basenames in the manifest. Validate **all** stage bytes/access metadata and recheck preconditions before any replacement.
3. Replace non-AGENTS outputs first, install the proven target access metadata after rename, and read-verify the complete supported state including protection. Persist each helper-committed state before the next output. Recheck dependencies and preservation destinations before replacing AGENTS **last**. Each replacement uses `os.replace`; there is no cross-file atomicity.
4. On handled failure, restore AGENTS first if touched. Only after verifying its restoration may destinations roll back. If source restoration fails, or an untouched source has concurrently changed, retain all applied destinations. Restore only a file whose complete current fingerprint matches the helper-committed state; unchanged complete originals require no restoration. Bytes alone never establish ownership. External drift retains the current file and private evidence, reports the differing fields, and marks `rollback-incomplete`. Retain originals and explicit recovery state on every failure, even a complete rollback.
5. After all outputs verify, mark committed and remove temporary artifacts. A cleanup failure reports committed outputs with recovery evidence; it does not undo preserved knowledge.

Failure may leave duplication; the protocol must not remove a source before preservation targets hold verified final bytes. Abrupt termination retains already-created manifests/original-byte artifacts instead of relying on Python exception handling; early preparation may be incomplete while the source is still untouched. Inspect lists pending recovery, with an inspection error if current outputs are malformed; **all further apply/dry-run calls refuse to proceed** until it is reviewed. No automatic replay or destructive recovery command exists.

Recovery locations are keyed by project filesystem identity. Preserve the existing ProgramData (Windows) or `/tmp` (POSIX) container when it shares the project filesystem. Otherwise choose a private sibling container at the nearest project ancestor outside any containing Git tree, on the same filesystem; try further same-filesystem ancestors if creation is denied. Reuse an existing candidate before creating one, reject multiple state roots or unexpected permissions, and never bypass old nonempty cross-volume recovery. An unwritable candidate with no container may fall back; an existing unverifiable container fails closed. Inspect reports the selected absolute `state_root`. Each project directory has a current-user-only protected Windows DACL or POSIX owner/mode `0700`. Existing storage with unexpected permissions/owner is rejected, including access by another user; it cannot silently fork recovery state. Paths do not depend on `TMP/TEMP/TMPDIR`. The helper refuses runtime storage inside any containing Git working tree or the selected project. Backups and stages therefore cannot appear in ordinary project `git add --all`. Successful cleanup deletes their payload directory; an empty private project container may remain. Inspect also gates any legacy root recovery directories.

For recovery, inspect the reported absolute directory and manifest `project`, `before`/`after`, `originals`, `staged`, `original_metadata`, `original_states`, `rename_states`, `intended_states`, `committed_states` and state against actual files. Stage basenames are relative to that directory. Hash-check originals before restoration; restore the source with its supported access metadata before removing duplicated knowledge. Windows descriptors are hex-encoded recovery data (owner/group/DACL/protection); POSIX access records contain owner/group/mode. A crash between rename and access installation leaves a private target: inspect its full state against the persisted private rename state and intended installed state. An ambiguous replace error may be rolled back only when its full state equals one of those precomputed states; never adopt a drifted file as committed. Review concurrent edits and retain unresolved backups. Manual restoration/cleanup must also hold `file_security.project_lock(root)`; it is not an automatic replay command. Once fully restored or knowingly accepted, delete only reviewed artifacts, inspect, and make a fresh plan. Never delete evidence merely to unblock a retry.

### File security and metadata limits

Every manifest, original-byte backup, stage, rollback payload and metadata record uses recovery storage's own private permissions, including when the source grants Everyone read access. Source DACLs are never applied to backup or staged payloads. On Windows, create/verify protected current-user-only file DACLs before writing payloads; on POSIX, payloads remain `0600` in private storage. Known absolute backup paths are covered by actual restricted-token opens, not directory obscurity.

For Windows existing destinations, preflight empty probes must reproduce owner/group and equivalent current grants with a protected DACL. Owner/group that cannot be reproduced or an unverifiable DACL/protection state stops before payload or target writes. After rename, `SetNamedSecurityInfoW` with `DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION` installs the saved DACL; inherited ACE provenance is cleared without changing current grants. Re-read owner/group, normalized ordered ACEs, DACL presence and `SE_DACL_PROTECTED`; checking ACE lists alone is insufficient. Future parent grants must not propagate. Rollback restores the saved original protection state, rather than always protecting it. New installed files remain private/protected. On POSIX, preserve supported owner/group/mode after rename; unsupported owners, special mode bits, file flags and xattrs (including extended ACLs) are rejected.

Rollback fingerprints contain main-stream SHA256, owner, group, normalized DACL and presence, DACL protection, Windows attributes, hardlink count, detected ADS names/sizes and integrity-label indicators (or POSIX mode/flags/xattrs). ADS and other unsupported indicators are observed without migrating them: any newly detected stream or metadata drift prevents restoration, including when main-stream bytes are unchanged. The manifest and error report name the differing fields. This detects drift within the supported boundary; it is not a complete filesystem snapshot.

Existing Windows ADS, explicit mandatory integrity labels, nonordinary attributes and hardlinked outputs are rejected during preflight. A missing/unsupported stream/security API also fails closed. The supported preservation scope is main-stream bytes plus the access metadata above. It does **not** promise timestamps, file identity, audit SACLs or all filesystem metadata. Raw backups are not complete file images. Unknown metadata outside this scope remains unsupported. Same-filesystem storage is mandatory for ordered `os.replace`; an unavailable same-filesystem location refuses before project writes. Storage loss/deletion by the OS or an external actor is outside crash-recovery guarantees.

Guarantees assume ordinary readable/writable storage and no adversarial concurrent mutation between final checks and filesystem operations. File fsync and ordered replace do **not** prove power-loss durability of directory metadata across all filesystems or filesystem-level multi-file atomicity. Disk/hardware corruption, external deletions, full Markdown semantics, omitted dependencies, and semantic misclassification are outside the mechanical guarantee. Original-byte artifacts and failure reports make those boundaries visible.

Config updates only ordinary `[harness]` version/profile scalars and validates that all other parsed values survive; Git metadata/comments remain intact. Nonstandard dotted/inline harness tables require narrow normalization preserving values first. The helper never contacts remotes, initializes Git, changes origins, or commits.

## Focused verification

Run `python scripts/test_bootstrap.py` from this skill, or its absolute path. Retain Seed/Profile, Reconcile, Maintain, canonical, boundary/config/execution-state and stale-binding regressions. Cover actual two-process competition, lock-owner death, Markdown/example routes, all-route relocation, hardlink/junction identity, restrictive Windows ACLs, restricted-token directory/manifest/known-path public-source backup access, external ACL tightening/ADS/protection/group/attribute drift followed by a real deny-delete replace failure, future parent inheritance with an unprotected positive control, Seed confidentiality, protection preflight failure, real ADS/integrity labels, Git dry-run after failure/crash, and every dynamically enumerated write checkpoint/partial-write position. Platform-only tests explicitly skip elsewhere. Private `--test-fault` / `--test-crash` / `--test-pause PHASE:NAME` flags are isolated test seams; pause uses stdin to schedule the competing process.

Review the semantic diff and five-file project scope, then repeat Maintain for idempotence. Review external recovery evidence if present. Do not run the host project's suite.
