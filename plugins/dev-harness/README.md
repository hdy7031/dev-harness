# dev-harness

A small Codex plugin for setting up a repository harness, preparing a handoff, and recovering from Git failures. Stable project rules belong in the repository; task prompts can focus on the current work.

## Install locally

From the directory containing `.agents/plugins/marketplace.json`, run:

```powershell
codex plugin marketplace add .
codex plugin add dev-harness@personal
```

Start a new Codex chat to use the installed skills.

## Use

- `$dev-harness:project-bootstrap` — initialize or update a minimal repository harness.
- `$dev-harness:project-handoff` — refresh `HANDOFF.md` at a session or phase boundary.
- `$dev-harness:git-recovery` — diagnose and repair common Git failures safely.

## Develop

Edit the three `skills/*/SKILL.md` files as needed. Validate the plugin and changed skills with the bundled creator validators, then reinstall locally to test in a new chat.
