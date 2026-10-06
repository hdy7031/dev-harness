---
name: git-recovery
description: Diagnose and repair failed Git push, fetch, or pull; wrong or changed origin; GitHub repository-not-found, authentication, DNS, proxy, or TLS errors; non-fast-forward, divergence, or detached HEAD. Do not use for ordinary Git operations that work normally.
---

# Git recovery

Start from the failing Git command and its actual error. Inspect the repository root, `git status`, branch and HEAD, recent commits, `git remote -v` (and `git remote get-url origin` when present), relevant proxy configuration, and `.harness/config.toml`. When possible, fetch safely to compare local and remote branch state. Preserve uncommitted work. Classify the root cause before changing configuration; use [failure classes](references/failure-classes.md) when the error is ambiguous. Browser or Codex connectivity does not prove Git for Windows connectivity.

If `.harness/config.toml` records `git.verified_canonical_remote`, compare it with origin and report any difference. Restore that URL only after confirming the mismatch caused the failure. Without a verified URL, use trusted local repository evidence only when sufficient; ask for the GitHub URL if it is truly needed. Never invent one.

Fix the cause with the smallest safe change. For proxy errors, inspect the actual proxy and listening state; prefer command-scoped checks to permanent configuration changes. For non-fast-forward or divergence, fetch and compare branches before integrating.

Do not default to `reset --hard`, `clean`, force push, destructive rebase, disabling SSL verification, hosts-file edits, credential deletion, or overwriting local work. A single failed command does not justify persistent proxy or TLS changes. Before an action that could alter history or discard work, stop and explain its specific risk.

Verify only what the repair affects: the remote URL if changed, `ls-remote` or a safe fetch for connectivity, branch relationship after synchronization, and intact worktree state. Do not run unrelated project tests.
