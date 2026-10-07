---
name: project-handoff
description: Create or update a repository's HANDOFF.md when a session is ending, the user requests a handoff, or context must be prepared for a new Codex conversation. Do not use for routine progress notes.
---

# Project handoff

Work in the selected repository. Read `AGENTS.md`, existing `HANDOFF.md`, relevant Context/Decisions, Git status and recent work. Follow canonical bridges to their actual sources before judging current state. Use repository and session evidence to distinguish completion from old plans or claims.

Write the current goal, minimum continuation state, blocker, next concrete action and a few pitfalls that still affect it. Reference README/Context/Decisions for stable architecture, policy, validation and rationale instead of explaining them again. Git identifiers, test totals, hashes, implementation details and failed attempts belong here only when needed to choose or execute the next action. Mark uncertainty plainly. If no continuation exists, say “No active handoff” instead of leaving blank headings.

Rewrite from the current continuation; replace stale state each time. Do not accumulate completed rounds or keep an old detail merely because it was once useful. For each paragraph, ask whether removing it would change the recipient's next action; otherwise remove it or replace it with a source reference. Consume canonical ledgers but do not copy them into HANDOFF. Compression serves correct action, not a byte target. Do not run project tests solely to write the handoff.

Inspect the diff and actual final file against current evidence. Confirm a fresh reader can identify the blocker and first concrete action without repeating completed exploration, stale directions are gone, and repeated refreshes have not accumulated history. Stop when accurate and scoped.
