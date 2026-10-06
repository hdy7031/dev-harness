"""Focused isolated checks; never execute the host project's tests."""

import contextlib
import copy
import io
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest

import bootstrap


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix="harness-v2-test-")
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name)

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="")

    def snapshot(self):
        return {path.relative_to(self.root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
                for path in self.root.rglob("*") if path.is_file()}

    def assert_layers(self, profile, invariants=()):
        agents = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        spans = bootstrap.boundaries(agents)
        self.assertEqual(set(spans), {"core", "profile"})
        project_start = agents.index("## Project-specific invariants")
        self.assertGreater(project_start, spans["profile"][1])
        for invariant in invariants:
            self.assertIn(invariant, agents[project_start:])
            self.assertNotIn(invariant, agents[:project_start])
        config = tomllib.loads((self.root / ".harness/config.toml").read_text())
        self.assertEqual(config["harness"], {"version": 2, "profile": profile})
        return agents, config

    def check_seed(self, profile):
        # Inputs remain untouched, including a file representing user work.
        before = self.snapshot()
        self.assertEqual(bootstrap.run(self.root, inspect_only=True)["mode"], "seed")
        with contextlib.redirect_stdout(io.StringIO()) as diff:
            preview = bootstrap.run(self.root, profile, dry_run=True)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(set(preview["changed"]), set(bootstrap.FILES))
        self.assertIn("dev-harness:core:start", diff.getvalue())
        result = bootstrap.run(self.root, profile)
        self.assertEqual(result["mode"], "seed")
        self.assertEqual(set(self.snapshot()) - set(before), set(bootstrap.FILES))
        for name, value in before.items():
            self.assertEqual(self.snapshot()[name], value)
        self.assert_layers(profile)

    def test_new_software_repo(self):
        self.write("package.json", '{"name":"desktop-product"}\n')
        self.write("src/app.ts", "// user work\n")
        self.check_seed("software")

    def test_new_research_repo(self):
        self.write("experiments/train.py", "# real experiment\n")
        self.write("notebooks/README.md", "Research question: document recovery.\n")
        self.check_seed("research")

    def test_new_competition_repo(self):
        self.write("problem/statement.md", "Competition: answer all MUST items by the deadline.\n")
        self.check_seed("competition")

    def test_mature_repo_reconcile(self):
        legacy = ("# Legacy guidance\r\n"
                  "- Verify proportionally to risk.\r\n"
                  "- Verify proportionally to risk.\r\n"
                  "- manual > schedule > routine > idle.\r\n"
                  "- Core capability remains usable without AI, QQ, or cloud.\r\n"
                  "- Phase 6B2; tests 352/352 at the last handoff.\r\n"
                  "- Current architecture: Electron desktop shell.\r\n"
                  "- Use SQLite for offline storage because transactions protect user edits.\r\n"
                  "- Always produce three audit documents for every small UI edit.\r\n")
        self.write("AGENTS.md", legacy)
        self.write("HANDOFF.md", "# Handoff\n\nKeep the user-selected packaging task.\n")
        self.write("docs/PROJECT_CONTEXT.md", "# Context\n\nExisting architecture notes.\n")
        self.write("docs/DECISIONS.md", "# Decisions\n\nExisting decision rationale.\n")
        git_data = ('[git]\r\nremote = "origin"\r\n'
                    'verified_canonical_remote = "https://example.invalid/team/product.git" # verified earlier\r\n'
                    'checked_at = 2026-09-28\r\n')
        self.write(".harness/config.toml", '# retain config comment\r\n[harness]\r\nversion = 1 # old version\r\nprofile = "generic"\r\n\r\n' + git_data)
        self.write("src/untouched.txt", "uncommitted user work\n")
        before = self.snapshot()
        info = bootstrap.run(self.root, inspect_only=True)
        self.assertEqual(info["mode"], "reconcile")
        plan = {"agents_sha256": info["agents_sha256"], "rules": [
            {"start": 1, "end": 1, "action": "drop", "reason": "Structure replaced"},
            {"start": 2, "end": 3, "action": "merge", "reason": "Kernel risk-proportional verification"},
            {"start": 4, "end": 5, "action": "invariant", "reason": "Unique product constraints"},
            {"start": 6, "end": 6, "action": "handoff", "reason": "Historical continuation state"},
            {"start": 7, "end": 7, "action": "context", "reason": "Current architecture fact"},
            {"start": 8, "end": 8, "action": "decision", "reason": "Choice and rationale"},
            {"start": 9, "end": 9, "action": "drop", "reason": "Obsolete audit ceremony"}]}
        for invalid in (None, {**plan, "rules": plan["rules"][:-1]},
                        {**plan, "agents_sha256": "stale"}):
            with self.assertRaises(ValueError):
                bootstrap.run(self.root, "software", invalid)
            self.assertEqual(self.snapshot(), before)
        with contextlib.redirect_stdout(io.StringIO()):
            bootstrap.run(self.root, "software", plan, dry_run=True)
        self.assertEqual(self.snapshot(), before)
        result = bootstrap.run(self.root, "software", plan)
        self.assertEqual(result["mode"], "reconcile")
        self.assertEqual(len(result["reconciliation"]), 7)
        agents, config = self.assert_layers("software", (
            "manual > schedule > routine > idle.", "Core capability remains usable without AI, QQ, or cloud."))
        self.assertNotIn("352/352", agents)
        self.assertNotIn("three audit documents", agents)
        self.assertNotIn("Verify proportionally to risk.", agents)
        self.assertIn("352/352", (self.root / "HANDOFF.md").read_text())
        self.assertIn("Historical source", (self.root / "HANDOFF.md").read_text())
        self.assertIn("Electron desktop shell", (self.root / "docs/PROJECT_CONTEXT.md").read_text())
        self.assertIn("transactions protect user edits", (self.root / "docs/DECISIONS.md").read_text())
        self.assertIn(git_data.encode(), (self.root / ".harness/config.toml").read_bytes())
        self.assertEqual(config["git"]["remote"], "origin")
        for name in bootstrap.FILES[1:4]:
            self.assertTrue((self.root / name).read_bytes().startswith(before[name][0]))
        self.assertEqual(self.snapshot()["src/untouched.txt"], before["src/untouched.txt"])
        snapshot = self.snapshot()
        self.assertEqual(bootstrap.run(self.root)["changed"], [])
        self.assertEqual(self.snapshot(), snapshot)

    def test_explicit_plan_drops_bootstrap_execution_state(self):
        architecture = "- Current architecture: Electron desktop shell."
        migration_lines = (
            "- Current harness worktree: C:/temp/foo.",
            "- Testing branch: test/harness-v2.",
            "- Backup branch: backup/pre-harness-v2.",
        )
        self.write("AGENTS.md", "\n".join((architecture, *migration_lines)) + "\n")
        info = bootstrap.run(self.root, inspect_only=True)
        # Codex supplies the semantic classification; the writer only applies it.
        plan = {"agents_sha256": info["agents_sha256"], "rules": [
            {"start": 1, "end": 1, "action": "context", "reason": "Current architecture fact"},
            {"start": 2, "end": 4, "action": "drop",
             "reason": "Bootstrap execution state, not durable project context"},
        ]}
        result = bootstrap.run(self.root, "software", plan)
        self.assertEqual(result["mode"], "reconcile")
        context = (self.root / "docs/PROJECT_CONTEXT.md").read_text(encoding="utf-8")
        self.assertIn(architecture, context)
        for name in bootstrap.FILES:
            content = (self.root / name).read_text(encoding="utf-8")
            for line in migration_lines:
                self.assertNotIn(line, content)
        snapshot = self.snapshot()
        self.assertEqual(bootstrap.run(self.root)["changed"], [])
        self.assertEqual(self.snapshot(), snapshot)

        # No keyword filtering: the helper honors context routing even for these lines.
        self.root = self.root / "explicit-context"
        self.root.mkdir()
        self.write("AGENTS.md", "\n".join(migration_lines) + "\n")
        info = bootstrap.run(self.root, inspect_only=True)
        plan = {"agents_sha256": info["agents_sha256"], "rules": [
            {"start": 1, "end": 3, "action": "context",
             "reason": "Writer contract check: classification is supplied by the caller"},
        ]}
        bootstrap.run(self.root, "software", plan)
        context = (self.root / "docs/PROJECT_CONTEXT.md").read_text(encoding="utf-8")
        for line in migration_lines:
            self.assertIn(line, context)

    def test_second_run_idempotency_and_managed_upgrade(self):
        for profile in bootstrap.PROFILES:
            root = self.root / profile
            root.mkdir()
            bootstrap.run(root, profile, {"invariants": [{"text": "- Original data stays read-only.", "evidence": "Observed project data policy"}]})
            before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in root.rglob("*") if path.is_file()}
            result = bootstrap.run(root)
            self.assertEqual(result["mode"], "maintain")
            self.assertEqual(result["changed"], [])
            self.assertEqual(before, {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in before})
            agents_path = root / "AGENTS.md"
            agents = agents_path.read_text()
            agents_path.write_bytes(b"\xef\xbb\xbf" + agents.replace("Prioritize real outcomes and value over process completeness.", "Old kernel guidance.").replace("\n", "\r\n").encode() + "\n## Extra project notes\n\nKeep this unique section.\n".encode())
            old = bootstrap.decode(agents_path.read_bytes())
            _, boundary_end = bootstrap.boundaries(old)["profile"]
            tail = old[boundary_end:]
            result = bootstrap.run(root)
            self.assertEqual(result["changed"], ["AGENTS.md"])
            new = bootstrap.decode(agents_path.read_bytes())
            self.assertEqual(new[bootstrap.boundaries(new)["profile"][1]:], tail)
            self.assertEqual(bootstrap.run(root)["changed"], [])
            # Profile switching updates only the stance/config and preserves unique text.
            switched = "competition" if profile != "competition" else "software"
            bootstrap.run(root, switched)
            new = bootstrap.decode(agents_path.read_bytes())
            self.assertEqual(new[bootstrap.boundaries(new)["profile"][1]:], tail)
            self.assertEqual(bootstrap.run(root)["changed"], [])
            agents_path.write_text(new.replace("<!-- dev-harness:core:end -->", ""))
            broken = {path: path.read_bytes() for path in before}
            with self.assertRaises(ValueError):
                bootstrap.run(root)
            self.assertEqual(broken, {path: path.read_bytes() for path in before})

    def canonical_mature_plan(self):
        self.write("AGENTS.md", (
            "# Established guidance\n"
            "- Current state canonical source: planning/CONTEXT.md.\n"
            "- Major decisions canonical source: planning/DECISIONS.md.\n"
            "- Raw inputs must remain read-only.\n"
            "- Current stage: RELEASE_CANDIDATE_42.\n"
            "- Chose SQLite in DECISION_19 because atomic writes preserve edits.\n"))
        self.write("planning/CONTEXT.md", "# Current state\r\n\r\nRELEASE_CANDIDATE_42; pending release audit.\r\n")
        self.write("planning/DECISIONS.md", "# Decision ledger\n\nDECISION_19: SQLite; atomic writes preserve edits.\n")
        info = bootstrap.run(self.root, inspect_only=True)
        return {"agents_sha256": info["agents_sha256"], "canonical_sources": {
            "context": {"path": "planning/CONTEXT.md",
                        "evidence": "Root AGENTS line 2 explicitly names the canonical current-state source."},
            "decision": {"path": "planning/DECISIONS.md",
                         "evidence": "Root AGENTS line 3 explicitly names the canonical major-decision source."},
        }, "rules": [
            {"start": 1, "end": 1, "action": "drop", "reason": "Structure replaced"},
            {"start": 2, "end": 4, "action": "invariant", "reason": "Stable source authority and data policy"},
            {"start": 5, "end": 5, "action": "drop",
             "reason": "already preserved in canonical source planning/CONTEXT.md"},
            {"start": 6, "end": 6, "action": "drop",
             "reason": "already preserved in canonical source planning/DECISIONS.md"},
        ]}

    def assert_rejected_without_writes(self, plan, message):
        before = self.snapshot()
        for dry_run in (True, False):
            with self.subTest(dry_run=dry_run), contextlib.redirect_stdout(io.StringIO()) as output:
                with self.assertRaisesRegex(ValueError, message):
                    bootstrap.run(self.root, "software", plan, dry_run=dry_run)
                self.assertEqual(output.getvalue(), "")
                self.assertEqual(self.snapshot(), before)

    def test_canonical_mature_repo_bridges_and_maintain(self):
        plan = self.canonical_mature_plan()
        before = self.snapshot()
        with contextlib.redirect_stdout(io.StringIO()) as diff:
            preview = bootstrap.run(self.root, "software", plan, dry_run=True)
        self.assertEqual(preview["mode"], "reconcile")
        self.assertEqual(self.snapshot(), before)
        additions = "\n".join(line for line in diff.getvalue().splitlines() if line.startswith("+"))
        self.assertNotIn("RELEASE_CANDIDATE_42", additions)
        self.assertNotIn("DECISION_19", additions)
        result = bootstrap.run(self.root, "software", plan)
        self.assertEqual(result["mode"], "reconcile")
        self.assertEqual(set(self.snapshot()) - set(before), set(bootstrap.FILES) - {"AGENTS.md"})
        for name in ("planning/CONTEXT.md", "planning/DECISIONS.md"):
            self.assertEqual(self.snapshot()[name], before[name])
        self.assert_layers("software", (
            "Current state canonical source: planning/CONTEXT.md.",
            "Major decisions canonical source: planning/DECISIONS.md.",
            "Raw inputs must remain read-only."))
        for action, name in (("context", "docs/PROJECT_CONTEXT.md"), ("decision", "docs/DECISIONS.md")):
            bridge = (self.root / name).read_text(encoding="utf-8")
            self.assertIn(plan["canonical_sources"][action]["path"], bridge)
            self.assertIn("Dev Harness compatibility bridge", bridge)
            self.assertIn("Read and update the canonical source", bridge)
            self.assertLess(len(bridge.split()), 65)
            for dynamic in ("RELEASE_CANDIDATE_42", "DECISION_19", "SQLite", "pending release audit"):
                self.assertNotIn(dynamic, bridge)
        snapshot = self.snapshot()
        self.assertEqual(bootstrap.run(self.root)["changed"], [])
        self.assertEqual(self.snapshot(), snapshot)
        # An independently updated ledger never triggers a summary or bridge rewrite.
        self.write("planning/CONTEXT.md", "# Current state\nRELEASED_43\n")
        self.write("planning/DECISIONS.md", "# Decisions\nDECISION_20: release approved.\n")
        snapshot = self.snapshot()
        self.assertEqual(bootstrap.run(self.root)["changed"], [])
        self.assertEqual(self.snapshot(), snapshot)

    def test_canonical_duplicate_routing_rejected(self):
        plan = self.canonical_mature_plan()
        for action, index in (("context", 2), ("decision", 3)):
            invalid = copy.deepcopy(plan)
            invalid["rules"][index]["action"] = action
            # Even empty routing text must not evade the declaration conflict.
            for content in ("Unique missing knowledge", ""):
                invalid["rules"][index]["text"] = content
                with self.subTest(action=action, content=content):
                    self.assert_rejected_without_writes(invalid, f"conflicts with action={action}")

    def test_canonical_invalid_sources_rejected(self):
        plan = self.canonical_mature_plan()
        invalid_entries = (
            ({"evidence": "Explicit authority"}, "project-relative path"),
            ({"path": "planning/MISSING.md", "evidence": "Explicit authority"}, "regular file"),
            ({"path": "../outside.md", "evidence": "Explicit authority"}, "outside the project"),
            ({"path": str(self.root / "planning/CONTEXT.md"), "evidence": "Explicit authority"}, "project-relative"),
            ({"path": "C:planning/CONTEXT.md", "evidence": "Explicit authority"}, "project-relative"),
            ({"path": "planning/CONTEXT.md"}, "project evidence"),
            ({"path": "planning/CONTEXT.md", "evidence": "  "}, "project evidence"),
            ({"path": "planning", "evidence": "Explicit authority"}, "regular file"),
            ({"path": "AGENTS.md", "evidence": "Explicit authority"}, "Harness output/bridge"),
        )
        for item, message in invalid_entries:
            invalid = copy.deepcopy(plan)
            invalid["canonical_sources"]["context"] = item
            with self.subTest(item=item):
                self.assert_rejected_without_writes(invalid, message)
        for declaration in (None, [], {"handoff": {"path": "HANDOFF.md", "evidence": "Not supported"}}):
            self.assert_rejected_without_writes({**plan, "canonical_sources": declaration}, "only context and decision")

    def test_canonical_bridge_cannot_point_to_itself(self):
        plan = self.canonical_mature_plan()
        for action in ("context", "decision"):
            self.write(bootstrap.ROUTES[action], "# Existing knowledge\nPreserve this file.\n")
            invalid = copy.deepcopy(plan)
            invalid["canonical_sources"] = {action: {
                "path": bootstrap.ROUTES[action], "evidence": "Declared, but circular"}}
            self.assert_rejected_without_writes(invalid, "Harness output/bridge")

    def test_canonical_existing_destinations_preserved_or_rejected(self):
        plan = self.canonical_mature_plan()
        for action in ("context", "decision"):
            name = bootstrap.ROUTES[action]
            # Reject substantive content, a bridge with extra facts, and another target.
            for content in ("# Existing knowledge\nKeep this unique fact.\n",
                            bootstrap.canonical_bridge(action, plan["canonical_sources"][action]["path"]) + "Extra fact.\n",
                            bootstrap.canonical_bridge(action, "planning/OTHER.md")):
                self.write(name, content)
                self.assert_rejected_without_writes(plan, "not the same canonical Harness bridge")
            # A known same-target bridge is accepted without changing BOM/CRLF bytes.
            bridge = bootstrap.canonical_bridge(action, plan["canonical_sources"][action]["path"])
            (self.root / name).write_bytes(b"\xef\xbb\xbf" + bridge.replace("\n", "\r\n").encode())
        before = self.snapshot()
        with contextlib.redirect_stdout(io.StringIO()):
            bootstrap.run(self.root, "software", plan, dry_run=True)
        self.assertEqual(self.snapshot(), before)
        result = bootstrap.run(self.root, "software", plan)
        for name in ("docs/PROJECT_CONTEXT.md", "docs/DECISIONS.md"):
            self.assertNotIn(name, result["changed"])
            self.assertEqual(self.snapshot()[name], before[name])

    def test_canonical_symlink_escape_rejected(self):
        plan = self.canonical_mature_plan()
        with tempfile.TemporaryDirectory(prefix="harness-canonical-outside-") as outside:
            external = Path(outside) / "ledger.md"
            external.write_bytes(b"External canonical content must remain untouched.\n")
            link = self.root / "planning/external.md"
            junction = None
            try:
                link.symlink_to(external)
            except (OSError, NotImplementedError):
                if os.name != "nt":
                    raise
                # Windows file symlinks may require privileges. A parent junction
                # exercises real link traversal without that privilege requirement.
                junction = self.root / "planning/external"
                subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), outside],
                               check=True, capture_output=True)
                link = junction / "ledger.md"
            try:
                plan["canonical_sources"]["context"]["path"] = link.relative_to(self.root).as_posix()
                self.assert_rejected_without_writes(plan, "outside the project")
                self.assertEqual(external.read_bytes(), b"External canonical content must remain untouched.\n")
            finally:
                if junction is not None:
                    junction.rmdir()  # Remove only the link, never the outside tree.
                else:
                    link.unlink()

    def test_canonical_field_is_reconcile_only(self):
        plan = {"canonical_sources": {}}
        self.assert_rejected_without_writes(plan, "only supported for Reconcile")
        bootstrap.run(self.root, "software")
        self.assert_rejected_without_writes(plan, "only supported for Reconcile")

    def test_single_canonical_role_leaves_other_routing_unchanged(self):
        plan = self.canonical_mature_plan()
        del plan["canonical_sources"]["decision"]
        plan["rules"][3]["action"] = "decision"
        plan["rules"][3]["reason"] = "No established decision source is declared by this plan"
        bootstrap.run(self.root, "software", plan)
        self.assertIn("compatibility bridge", (self.root / "docs/PROJECT_CONTEXT.md").read_text())
        self.assertIn("DECISION_19", (self.root / "docs/DECISIONS.md").read_text())

    def test_no_canonical_keyword_classifier(self):
        plan = self.canonical_mature_plan()
        del plan["canonical_sources"]
        # Even explicit canonical language/files do not make the writer discover sources.
        plan["rules"][1]["action"] = "context"
        plan["rules"][1]["reason"] = "Caller supplied routing, not a helper classification"
        plan["rules"][2]["action"] = "context"
        plan["rules"][3]["action"] = "decision"
        self.write("STATUS.md", "Canonical CONTEXT DECISIONS planning keywords alone are not evidence.\n")
        before = self.snapshot()
        bootstrap.run(self.root, "software", plan)
        context = (self.root / "docs/PROJECT_CONTEXT.md").read_text()
        decisions = (self.root / "docs/DECISIONS.md").read_text()
        for keyword in ("canonical", "CONTEXT", "DECISIONS", "planning"):
            self.assertIn(keyword, context)
        self.assertIn("RELEASE_CANDIDATE_42", context)
        self.assertIn("DECISION_19", decisions)
        self.assertNotIn("compatibility bridge", context + decisions)
        for name in ("planning/CONTEXT.md", "planning/DECISIONS.md", "STATUS.md"):
            self.assertEqual(self.snapshot()[name], before[name])


if __name__ == "__main__":
    unittest.main(verbosity=2)
