---
name: project-handoff
description: Create or update a repository's HANDOFF.md when a session is ending, the user requests a handoff, or context must be prepared for a new Codex conversation. Do not use for routine progress notes.
---

# Project handoff

Work in the selected repository. Read `AGENTS.md`, the existing `HANDOFF.md` if present, relevant project context and decisions, Git status, current branch and HEAD, and recent work. Use repository and session evidence to distinguish completed work from plans or claims in an older handoff.

Write only what a fresh session needs to continue: the current goal, verified completed work, branch/HEAD/worktree state, blockers or unfinished work, important architecture and project constraints, decisions not to reverse casually, concrete pitfalls already encountered, and the next highest-value action. Mark material uncertainty plainly; do not invent completed work or project facts.

Replace stale current-state sections instead of appending another historical layer. Retain older information only when it still affects the next action. Keep the file concise, without a full history, excessive checklists, or duplicated `AGENTS.md` rules. Do not run project tests solely to write the handoff.

Verify by inspecting the `HANDOFF.md` diff and comparing its claims with the current repository state. Stop when the handoff is accurate and the diff contains only the intended update.
