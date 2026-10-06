"""Focused isolated checks; never execute the host project's tests."""

import contextlib
import io
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
