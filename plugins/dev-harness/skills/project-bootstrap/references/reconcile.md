# Reconciliation and helper usage

The helper is a writer, not a semantic classifier. Codex infers the objective from user intent and repository evidence, reads the chosen stance, and inventories prior rules. Do not infer meaning from keyword deletion or file counts alone.

Run with Python 3.11+ (standard library only); `HELPER` below means this skill's absolute `scripts/bootstrap.py` path and `PROJECT` the selected project directory:

```text
python HELPER PROJECT --inspect
python HELPER PROJECT --profile software --dry-run
python HELPER PROJECT --profile software
```

Seed needs only the chosen profile. For Reconcile, add `--plan PATH` to dry-run and apply; keep the plan in a temporary directory outside the project. Maintain uses the configured profile automatically; pass a different profile only when the primary objective changed. An identical second run omits the plan and must report an empty `changed` list. Config with V1/no boundaries enters Reconcile. Newer versions, malformed boundaries, or unsafe output paths stop before writes.

## Semantic inventory

Read old AGENTS, relevant context/decisions/handoff, project structure, and only enough history to understand whether a rule still applies. Classify **every nonblank old AGENTS line**, including structural headings, in disjoint inclusive line ranges:

| Meaning | Action |
| --- | --- |
| Long-lived project fact or unique architecture/domain constraint | `invariant`: preserve outside managed sections |
| Generic guidance already covered by core/profile | `merge`: name the covering principle in the reason |
| Current architecture/stage fact | `context`: move to PROJECT_CONTEXT |
| Useful next-session state or task continuation | `handoff`: move to HANDOFF |
| Consequential choice and rationale | `decision`: move to DECISIONS |
| Obsolete task/phase instruction or valueless historical ceremony | `drop`: explain why it is obsolete or safely covered elsewhere |

Structural headings can be dropped with the reason that the three-layer structure replaces them. Preserve uncertain unique rules until evidence supports retirement. Reconcile mixed paragraphs by splitting them into smaller line ranges or supplying a faithful `text` rewrite that retains every meaningful constraint. Keep nested/path-scoped AGENTS intact; do not hoist their scope into global rules.

Each range requires a reason; preserved/moved text defaults to its exact original lines. `text` is an optional semantic rewrite, never a license to erase constraints. The plan's `agents_sha256` must equal inspect output, so a changed source invalidates the plan. Coverage proves consideration, not correctness: inspect the actual semantic diff.

Example legacy AGENTS:

```markdown
# Legacy guidance
- Verify proportionally to risk.
- manual > schedule > routine > idle.
- Core capability remains usable without AI, QQ, or cloud.
- Phase 6B2; tests 352/352 at the last handoff.
- Always produce three audit documents for every small UI edit.
```

Example plan (replace the hash with the actual inspect value):

```json
{
  "agents_sha256": "<actual source SHA256>",
  "rules": [
    {"start": 1, "end": 1, "action": "drop", "reason": "Structure replaced by three layers"},
    {"start": 2, "end": 2, "action": "merge", "reason": "Covered by common kernel risk-proportional verification"},
    {"start": 3, "end": 4, "action": "invariant", "reason": "Unique state priority and offline product constraints"},
    {"start": 5, "end": 5, "action": "handoff", "reason": "Historical continuation state, not a permanent rule"},
    {"start": 6, "end": 6, "action": "drop", "reason": "Obsolete UI audit ceremony conflicts with risk-proportional verification"}
  ]
}
```

The result retains both unique constraints below `## Project-specific invariants`; generic verification appears once in the managed kernel, and the old phase/test count becomes explicitly historical handoff material. A few newly extracted invariants can be added with `"invariants": [{"text": "...", "evidence": "observed source and reason this is stable"}]`. This also works for Seed; omit it when no facts are known.

## Existing context and Git metadata

The helper creates missing context/handoff/decision files from minimal assets and preserves existing bytes unless routing text into them. It suppresses exact duplicate imports and marks imported material as historical. When existing sections already express the same knowledge in other words, first merge the moved facts into the right sections semantically, preserving unrelated content; the plan's routed `text` should match the merged text, so no import is appended. Replace obsolete continuation state when appropriate rather than accumulating history. Do not label old progress as newly verified.

The helper mechanically updates only harness version/profile in an ordinary `[harness]` TOML table, validates that all other parsed values are unchanged, and preserves existing Git metadata/comments. Nonstandard dotted/inline harness tables need a narrow manual normalization first, preserving values. It never contacts a remote, initializes Git, changes origin, or commits. Remote verification, when actually needed, remains evidence-led and outside the writer.

Dry-run shows exactly the five-file differences and the rule dispositions. Applying completes all validation before writing, checks that source files are unchanged, and replaces each changed file atomically; it is not a cross-file transaction. Inspect only these changes and repeat the helper to confirm no-op behavior. Do not run the host project's suite.
