"""Focused isolated checks; never execute the host project's tests."""

import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest import mock

import bootstrap
import file_security


def windows_sddl(text):
    s = file_security
    sd, size = s.P(), s.W.DWORD()
    s.checked(s.from_sddl(text, 1, s.C.byref(sd), s.C.byref(size)))
    try:
        return s.C.string_at(sd, size.value)
    finally:
        s.local_free(sd)


def windows_open(path, directory=False, share=7):
    s = file_security
    create = s.api(s.kernel, "CreateFileW", [s.W.LPCWSTR, s.W.DWORD, s.W.DWORD, s.P,
                   s.W.DWORD, s.W.DWORD, s.W.HANDLE], s.W.HANDLE)
    handle = create(str(path), 1, share, None, 3, 0x02000000 if directory else 0, None)
    return handle, s.C.get_last_error()


@contextlib.contextmanager
def everyone_restricted_token():
    """Real access check: restrict the second token pass to Everyone only.

    Source Everyone grants must still succeed; a current-user-only payload must
    fail, even with a known full path and traversal bypass privilege.
    """
    s = file_security
    class SidAttributes(s.C.Structure):
        _fields_ = [("sid", s.P), ("attributes", s.W.DWORD)]
    create = s.api(s.advapi, "CreateRestrictedToken", [s.W.HANDLE, s.W.DWORD, s.W.DWORD, s.P,
                   s.W.DWORD, s.P, s.W.DWORD, s.P, s.P])
    impersonate = s.api(s.advapi, "ImpersonateLoggedOnUser", [s.W.HANDLE])
    revert = s.api(s.advapi, "RevertToSelf", [])
    token, restricted = s.W.HANDLE(), s.W.HANDLE()
    sd = s.C.create_string_buffer(windows_sddl("D:(A;;GR;;;WD)"))
    present, defaulted, dacl = s.W.BOOL(), s.W.BOOL(), s.P()
    s.checked(s.get_dacl(sd, s.C.byref(present), s.C.byref(dacl), s.C.byref(defaulted)))
    everyone = SidAttributes(dacl.value + 16, 0)  # ACL header + ACCESS_ALLOWED_ACE SID offset.
    s.checked(s.open_token(s.process_handle(), 0xB, s.C.byref(token)))
    try:
        s.checked(create(token, 1, 0, None, 0, None, 1, s.C.byref(everyone), s.C.byref(restricted)))
        s.checked(impersonate(restricted))
        try:
            yield
        finally:
            s.checked(revert())
    finally:
        if restricted:
            s.close_handle(restricted)
        s.close_handle(token)


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix="harness-v2-test-")
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name)
        self.addCleanup(self.clean_state)

    def clean_state(self):
        import shutil
        for project in (Path(self.workspace.name), *Path(self.workspace.name).rglob("*")):
            if project.is_dir():
                state = file_security.storage(project, create=False)
                if state.exists():
                    shutil.rmtree(state)

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="")

    def snapshot(self):
        return {path.relative_to(self.root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
                for path in self.root.rglob("*") if path.is_file()}

    def bind(self, plan, read_paths=()):
        plan = copy.deepcopy(plan)
        for rule in plan.get("rules", []):
            if rule.get("action") in bootstrap.ROUTES:
                rule.setdefault("relocation_acknowledgement", "verbatim_safe")
        paths = list(read_paths) + [entry["path"] for entry in plan.get("canonical_sources", {}).values()]
        info = bootstrap.run(self.root, inspect_only=True, read_paths=paths)
        return {**plan, "protocol": 1, "mode": "reconcile", "profile": "software",
                "mode_evidence": "Existing project knowledge requires semantic reconciliation",
                "profile_evidence": "Observed software project objective",
                "expected_before": info["expected_before"], "read_set": info["read_set"]}

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
        self.assertEqual(bootstrap.run(self.root, inspect_only=True)["install_state"], "absent")
        with contextlib.redirect_stdout(io.StringIO()) as diff:
            preview = bootstrap.run(self.root, profile, dry_run=True, mode="seed")
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(set(preview["changed"]), set(bootstrap.FILES))
        self.assertIn("dev-harness:core:start", diff.getvalue())
        result = bootstrap.run(self.root, profile, mode="seed")
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
        self.assertEqual(info["install_state"], "unmanaged/legacy")
        plan = {"rules": [
            {"start": 1, "end": 1, "action": "drop", "reason": "Structure replaced"},
            {"start": 2, "end": 3, "action": "merge", "reason": "Kernel risk-proportional verification"},
            {"start": 4, "end": 5, "action": "invariant", "reason": "Unique product constraints"},
            {"start": 6, "end": 6, "action": "handoff", "reason": "Historical continuation state"},
            {"start": 7, "end": 7, "action": "context", "reason": "Current architecture fact"},
            {"start": 8, "end": 8, "action": "decision", "reason": "Choice and rationale"},
            {"start": 9, "end": 9, "action": "drop", "reason": "Obsolete audit ceremony"}]}
        plan = self.bind(plan)
        for invalid in (None, {**plan, "rules": plan["rules"][:-1]},
                        {**plan, "expected_before": {**plan["expected_before"], "AGENTS.md": "stale"}}):
            with self.assertRaises(ValueError):
                bootstrap.run(self.root, "software", invalid)
            self.assertEqual(self.snapshot(), before)
        with contextlib.redirect_stdout(io.StringIO()):
            bootstrap.run(self.root, "software", plan, dry_run=True)
        self.assertEqual(self.snapshot(), before)
        plan = self.bind(plan)
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
        plan = {"rules": [
            {"start": 1, "end": 1, "action": "context", "reason": "Current architecture fact"},
            {"start": 2, "end": 4, "action": "drop",
             "reason": "Bootstrap execution state, not durable project context"},
        ]}
        plan = self.bind(plan)
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
        plan = {"rules": [
            {"start": 1, "end": 3, "action": "context",
             "reason": "Writer contract check: classification is supplied by the caller"},
        ]}
        plan["rules"][0]["relocation_acknowledgement"] = "These explicitly routed execution paths are project-root references, not Markdown links."
        bootstrap.run(self.root, "software", self.bind(plan))
        context = (self.root / "docs/PROJECT_CONTEXT.md").read_text(encoding="utf-8")
        for line in migration_lines:
            self.assertIn(line, context)

    def test_second_run_idempotency_and_managed_upgrade(self):
        for profile in bootstrap.PROFILES:
            root = self.root / profile
            root.mkdir()
            bootstrap.run(root, profile, {"invariants": [{"text": "- Original data stays read-only.", "evidence": "Observed project data policy"}]}, mode="seed")
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
        return self.bind({"canonical_sources": {
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
        ]})

    def assert_rejected_without_writes(self, plan, message):
        # Fixture changes to destinations happen before constructing this preview.
        if plan.get("mode") == "reconcile":
            plan = {**plan, "expected_before": bootstrap.run(self.root, inspect_only=True)["expected_before"]}
        before = self.snapshot()
        for dry_run in (True, False):
            with self.subTest(dry_run=dry_run), contextlib.redirect_stdout(io.StringIO()) as output:
                with self.assertRaisesRegex(ValueError, message):
                    bootstrap.run(self.root, "software", plan, dry_run=dry_run,
                                  mode="seed" if "mode" not in plan and not (self.root / "AGENTS.md").exists() else None)
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
        plan = {**plan, "expected_before": bootstrap.run(self.root, inspect_only=True)["expected_before"]}
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
        bootstrap.run(self.root, "software", mode="seed")
        self.assert_rejected_without_writes(plan, "only supported for Reconcile")

    def test_single_canonical_role_leaves_other_routing_unchanged(self):
        plan = self.canonical_mature_plan()
        del plan["canonical_sources"]["decision"]
        plan["rules"][3]["action"] = "decision"
        plan["rules"][3]["reason"] = "No established decision source is declared by this plan"
        plan["rules"][3]["relocation_acknowledgement"] = "verbatim_safe"
        bootstrap.run(self.root, "software", plan)
        self.assertIn("compatibility bridge", (self.root / "docs/PROJECT_CONTEXT.md").read_text())
        self.assertIn("DECISION_19", (self.root / "docs/DECISIONS.md").read_text())

    def test_no_canonical_keyword_classifier(self):
        plan = self.canonical_mature_plan()
        del plan["canonical_sources"]
        # Even explicit canonical language/files do not make the writer discover sources.
        plan["rules"][1]["action"] = "context"
        plan["rules"][1]["reason"] = "Caller supplied routing, not a helper classification"
        plan["rules"][1]["relocation_acknowledgement"] = "These ledger paths remain project-root authority references."
        plan["rules"][2]["action"] = "context"
        plan["rules"][3]["action"] = "decision"
        for rule in plan["rules"]:
            if rule["action"] in bootstrap.ROUTES:
                rule.setdefault("relocation_acknowledgement", "verbatim_safe")
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

    def routed_fixture(self):
        self.write("AGENTS.md", "Context fact: OFFLINE_42\nDecision fact: SQLITE_19\nHandoff fact: RELEASE_43\nStable rule: INPUTS_READ_ONLY\n")
        for name in bootstrap.FILES[1:4]:
            self.write(name, "# Existing knowledge\n\nKeep all prior destination bytes.\n")
        self.write(".harness/config.toml", '[harness]\nversion = 1\nprofile = "generic"\n\n[git]\nremote = "origin"\n')
        return self.bind({"rules": [
            {"start": i, "end": i, "action": action, "reason": "Explicit knowledge disposition"}
            for i, action in enumerate(("context", "decision", "handoff", "invariant"), 1)]})

    def cli(self, *arguments):
        return subprocess.run([sys.executable, str(Path(bootstrap.__file__).resolve()), str(self.root), *arguments],
                              capture_output=True, text=True, encoding="utf-8",
                              env={**os.environ, "PYTHONIOENCODING": "utf-8"})

    def cli_plan(self, reads=()):
        arguments = [argument for path in reads for argument in ("--read", path)]
        result = self.cli("--inspect", *arguments)
        self.assertEqual(result.returncode, 0, result.stderr)
        info = json.loads(result.stdout)
        plan = {"protocol": 1, "mode": "reconcile", "mode_evidence": "Existing ledger and software need reconciliation",
                "profile": "software", "profile_evidence": "Observed software objective",
                "read_set": info["read_set"], "expected_before": info["expected_before"],
                "rules": [{"start": 1, "end": 1, "action": "context", "reason": "Retain current project fact",
                           "relocation_acknowledgement": "verbatim_safe"}]}
        plan_path = Path(self.workspace.name) / ("plan-" + self.root.name + ".json")
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        return plan_path

    def test_every_write_checkpoint_preserves_knowledge(self):
        # Enumerate the actual successful writer trace, then fail EACH event once.
        base = self.root
        self.root = base / "trace"
        self.root.mkdir()
        trace = []
        plan = self.routed_fixture()
        bootstrap.run(self.root, plan=plan, fault=lambda phase, name: trace.append((phase, name)))
        self.assertEqual([name for phase, name in trace if phase == "replace"][-1], "AGENTS.md")
        self.assertTrue(all(phase in {event[0] for event in trace}
                            for phase in ("backup", "stage", "replace", "verify", "journal", "mkdir", "cleanup")))
        for index, event in enumerate(trace):
            with self.subTest(event=index, phase=event):
                self.root = base / f"fault-{index}"
                self.root.mkdir()
                plan = self.routed_fixture()
                before = {name: (self.root / name).read_bytes() for name in bootstrap.FILES}
                seen = []
                def fault(phase, name):
                    seen.append((phase, name))
                    if len(seen) - 1 == index:
                        raise PermissionError("Simulated target lock / interrupted write")
                with self.assertRaises(bootstrap.ApplyError) as failure:
                    bootstrap.run(self.root, plan=plan, fault=fault)
                error = failure.exception
                self.assertTrue(error.recovery.is_dir())
                source = (self.root / "AGENTS.md").read_bytes()
                if event[0] != "cleanup":
                    self.assertEqual(source, before["AGENTS.md"])
                    for name in bootstrap.FILES:
                        self.assertEqual((self.root / name).read_bytes(), before[name])
                else:
                    # Committed cleanup failures retain the successfully routed facts.
                    for action, fact in (("context", b"OFFLINE_42"), ("decision", b"SQLITE_19"), ("handoff", b"RELEASE_43")):
                        self.assertIn(fact, (self.root / bootstrap.ROUTES[action]).read_bytes())
                self.assertTrue(bootstrap.run(self.root, inspect_only=True)["pending_recovery"])
                with self.assertRaisesRegex(ValueError, "Unresolved recovery"):
                    bootstrap.run(self.root, plan=plan)
        # A changing trace changes the number of actual fault positions automatically.
        print(f"\nWrite interruption checkpoints verified: {len(trace)}", file=sys.stderr)

    def test_failed_source_rollback_keeps_all_preservation_destinations(self):
        plan = self.routed_fixture()
        original = (self.root / "AGENTS.md").read_bytes()
        def fault(phase, name):
            if (phase, name) in (("verify", "AGENTS.md"), ("rollback", "AGENTS.md")):
                raise PermissionError("Source lock after replacement")
        with self.assertRaises(bootstrap.ApplyError) as failure:
            bootstrap.run(self.root, plan=plan, fault=fault)
        error = failure.exception
        self.assertEqual(error.state, "rollback-incomplete")
        manifest = json.loads((error.recovery / "manifest.json").read_text())
        self.assertEqual((error.recovery / manifest["originals"]["AGENTS.md"]).read_bytes(), original)
        self.assertTrue(manifest["rollback_errors"])
        for action, fact in (("context", "OFFLINE_42"), ("decision", "SQLITE_19"), ("handoff", "RELEASE_43")):
            self.assertIn(fact, (self.root / bootstrap.ROUTES[action]).read_text())

    def test_failed_destination_rollback_retains_original_source_and_backups(self):
        plan = self.routed_fixture()
        source = (self.root / "AGENTS.md").read_bytes()
        def fault(phase, name):
            if (phase, name) in (("replace", "AGENTS.md"), ("rollback", "HANDOFF.md")):
                raise OSError("Injected rollback failure")
        with self.assertRaises(bootstrap.ApplyError) as failure:
            bootstrap.run(self.root, plan=plan, fault=fault)
        self.assertEqual(failure.exception.state, "rollback-incomplete")
        self.assertEqual((self.root / "AGENTS.md").read_bytes(), source)
        self.assertIn("RELEASE_43", (self.root / "HANDOFF.md").read_text())
        self.assertTrue((failure.exception.recovery / "original-0.bin").is_file())

    def test_partial_write_at_each_durable_write_position_preserves_source(self):
        base = self.root
        self.root = base / "durable-trace"
        self.root.mkdir()
        plan = self.routed_fixture()
        writer = bootstrap.durable_write
        trace = []
        def record(path, data):
            trace.append(path.name)
            writer(path, data)
        with mock.patch.object(bootstrap, "durable_write", side_effect=record):
            bootstrap.run(self.root, plan=plan)
        for index in range(len(trace)):
            with self.subTest(write=index, target=trace[index]):
                self.root = base / f"partial-{index}"
                self.root.mkdir()
                plan = self.routed_fixture()
                source = (self.root / "AGENTS.md").read_bytes()
                calls = []
                def interrupt(path, data):
                    calls.append(path)
                    if len(calls) - 1 == index:
                        path.write_bytes(data[:len(data) // 2])
                        raise OSError("Partial write / flush interruption")
                    writer(path, data)
                with mock.patch.object(bootstrap, "durable_write", side_effect=interrupt):
                    with self.assertRaises(bootstrap.ApplyError) as failure:
                        bootstrap.run(self.root, plan=plan)
                self.assertEqual((self.root / "AGENTS.md").read_bytes(), source)
                self.assertTrue(failure.exception.recovery.is_dir())
        print(f"\nPartial durable-write positions verified: {len(trace)}", file=sys.stderr)

    def test_ambiguous_replace_error_after_replacement_rolls_back_safely(self):
        plan = self.routed_fixture()
        before = {name: (self.root / name).read_bytes() for name in bootstrap.FILES}
        replace = bootstrap.os.replace
        failed = []
        def interrupt(source, destination):
            replace(source, destination)
            if Path(destination) == self.root / "AGENTS.md" and not failed:
                failed.append(True)
                raise OSError("Interrupted just after committed source replace")
        with mock.patch.object(bootstrap.os, "replace", side_effect=interrupt):
            with self.assertRaises(bootstrap.ApplyError):
                bootstrap.run(self.root, plan=plan)
        for name in bootstrap.FILES:
            self.assertEqual((self.root / name).read_bytes(), before[name])

    def test_concurrent_source_edit_prevents_destination_rollback(self):
        plan = self.routed_fixture()
        original = (self.root / "AGENTS.md").read_bytes()
        def edit(phase, name):
            if (phase, name) == ("verify", ".harness/config.toml"):
                self.write("AGENTS.md", "Another session replaced source guidance\n")
        with self.assertRaises(bootstrap.ApplyError) as failure:
            bootstrap.run(self.root, plan=plan, fault=edit)
        self.assertEqual(failure.exception.state, "rollback-incomplete")
        self.assertEqual((self.root / "AGENTS.md").read_text(), "Another session replaced source guidance\n")
        self.assertEqual((failure.exception.recovery / "original-0.bin").read_bytes(), original)
        for action, fact in (("context", "OFFLINE_42"), ("decision", "SQLITE_19"), ("handoff", "RELEASE_43")):
            self.assertIn(fact, (self.root / bootstrap.ROUTES[action]).read_text())

    def test_recovery_remains_discoverable_with_malformed_current_outputs(self):
        plan = self.routed_fixture()
        def interrupt(phase, name):
            if (phase, name) == ("stage", "HANDOFF.md"):
                raise OSError("Interrupted stage")
        with self.assertRaises(bootstrap.ApplyError):
            bootstrap.run(self.root, plan=plan, fault=interrupt)
        self.write(".harness/config.toml", "[invalid TOML\n")
        result = self.cli("--inspect")
        self.assertEqual(result.returncode, 0, result.stderr)
        info = json.loads(result.stdout)
        self.assertTrue(info["pending_recovery"])
        self.assertTrue(info["inspection_error"])
        with self.assertRaisesRegex(ValueError, "Unresolved recovery"):
            bootstrap.run(self.root, plan=plan)

    def test_interruption_during_stage_corruption_cannot_remove_source(self):
        plan = self.routed_fixture()
        before = (self.root / "AGENTS.md").read_bytes()
        def fault(phase, name):
            if (phase, name) == ("journal", "ready"):
                recovery = next(file_security.storage(self.root).glob(bootstrap.RECOVERY_PREFIX + "*"))
                stage = next(recovery.glob("stage-*"))
                stage.write_bytes(b"corrupted stage")
        with self.assertRaises(bootstrap.ApplyError):
            bootstrap.run(self.root, plan=plan, fault=fault)
        self.assertEqual((self.root / "AGENTS.md").read_bytes(), before)

    def test_stale_every_harness_output_rejects_zero_writes(self):
        base = self.root
        for name in bootstrap.FILES:
            with self.subTest(output=name):
                self.root = base / name.replace("/", "_").replace(".", "_")
                self.root.mkdir()
                plan = self.routed_fixture()
                with contextlib.redirect_stdout(io.StringIO()):
                    bootstrap.run(self.root, plan=plan, dry_run=True)
                path = self.root / name
                path.write_bytes(path.read_bytes() + b"\n# Concurrent edit\n")
                before = self.snapshot()
                for dry_run in (False, True):
                    with self.assertRaisesRegex(ValueError, "STALE PLAN"):
                        bootstrap.run(self.root, plan=plan, dry_run=dry_run)
                    self.assertEqual(self.snapshot(), before)
                    self.assertFalse(list(self.root.glob(bootstrap.RECOVERY_PREFIX + "*")))

    def test_stale_canonical_and_other_evidence_reject_zero_writes(self):
        base = self.root
        for name in ("planning/CONTEXT.md", "planning/DECISIONS.md", "policy/input.txt"):
            with self.subTest(dependency=name):
                self.root = base / name.replace("/", "_")
                self.root.mkdir()
                plan = self.canonical_mature_plan()
                self.write("policy/input.txt", "Observed data policy\n")
                plan = self.bind(plan, ("policy/input.txt",))
                with contextlib.redirect_stdout(io.StringIO()):
                    bootstrap.run(self.root, plan=plan, dry_run=True)
                self.write(name, "Changed after preview\n")
                before = self.snapshot()
                with self.assertRaisesRegex(ValueError, "STALE PLAN"):
                    bootstrap.run(self.root, plan=plan)
                self.assertEqual(self.snapshot(), before)
                self.assertFalse(list(self.root.glob(bootstrap.RECOVERY_PREFIX + "*")))

    def test_read_set_and_expected_before_are_mandatory(self):
        plan = self.routed_fixture()
        before = self.snapshot()
        malformed = (None, [], {}, {**plan, "protocol": 0}, {**plan, "read_set": []},
                     {**plan, "read_set": plan["read_set"] * 2}, {**plan, "read_set": [{"path": "AGENTS.md", "sha256": "x"}]},
                     {**plan, "expected_before": {"AGENTS.md": plan["expected_before"]["AGENTS.md"]}},
                     {**plan, "mode_evidence": ""}, {**plan, "profile_evidence": ""}, {**plan, "rules": None},
                     {**plan, "unknown_routing": {}}, {**plan, "protocol": True})
        for invalid in malformed:
            with self.subTest(plan=invalid), self.assertRaises((ValueError, TypeError)):
                bootstrap.run(self.root, plan=invalid, mode="reconcile")
            self.assertEqual(self.snapshot(), before)

    def test_canonical_sources_require_read_set_membership(self):
        plan = self.canonical_mature_plan()
        plan["read_set"] = [entry for entry in plan["read_set"] if entry["path"] == "AGENTS.md"]
        self.assert_rejected_without_writes(plan, "must belong to the decision read set")

    def test_absent_output_becoming_empty_file_is_stale(self):
        self.write("AGENTS.md", "Retain source fact\n")
        plan = self.bind({"rules": [{"start": 1, "end": 1, "action": "context", "reason": "Retain project fact"}]})
        with contextlib.redirect_stdout(io.StringIO()):
            bootstrap.run(self.root, plan=plan, dry_run=True)
        self.write("docs/PROJECT_CONTEXT.md", "")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "STALE PLAN"):
            bootstrap.run(self.root, plan=plan)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(list(self.root.glob(bootstrap.RECOVERY_PREFIX + "*")))

    def test_unsafe_read_set_dependency_rejected_without_writes(self):
        plan = self.routed_fixture()
        before = self.snapshot()
        for path in ("../outside.md", str(self.root / "AGENTS.md"), "C:AGENTS.md", "AGENTS.md:stream"):
            invalid = {**plan, "read_set": [*plan["read_set"], {"path": path, "sha256": "0" * 64}]}
            with self.subTest(path=path), self.assertRaises(ValueError):
                bootstrap.run(self.root, plan=invalid)
            self.assertEqual(self.snapshot(), before)

    def test_deleted_dependency_rejected_with_zero_writes(self):
        plan = self.routed_fixture()
        self.write("policy.md", "Evidence\n")
        plan = self.bind(plan, ("policy.md",))
        with contextlib.redirect_stdout(io.StringIO()):
            bootstrap.run(self.root, plan=plan, dry_run=True)
        (self.root / "policy.md").unlink()
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "STALE PLAN"):
            bootstrap.run(self.root, plan=plan)
        self.assertEqual(self.snapshot(), before)

    def test_evidence_backed_new_invariants_require_bound_evidence(self):
        plan = self.routed_fixture()
        self.write("policy.md", "Long-lived input policy\n")
        item = {"text": "Stable evidence-backed rule", "evidence": "Observed policy", "evidence_paths": ["policy.md"]}
        self.assert_rejected_without_writes({**plan, "invariants": [item]}, "evidence_paths")
        plan = self.bind({**plan, "invariants": [item]}, ("policy.md",))
        bootstrap.run(self.root, plan=plan)
        self.assertIn(item["text"], (self.root / "AGENTS.md").read_text())

    def test_route_never_suppressed_by_destination_body(self):
        base = self.root
        cases = (
            ("Retry budget: 30", True),
            ("> Retry budget: 3", True),
            ('"Retry budget: 3"', True),
            ("<!-- Retry budget: 3 -->", True),
            ("<!--\n\nRetry budget: 3\n\n-->", True),
            ("<!-- closed --> <!--\n\nRetry budget: 3\n\n-->", True),
            ("<blockquote>\n\nRetry budget: 3\n\n</blockquote>", True),
            ("```text\n\nRetry budget: 3\n\n```", True),
            ("Retry budget: 3, per worker", True),
            ("Retry budget: 3", True),
            ("Retry budget: 3\r\nTimeout: 10", True),
        )
        for index, (existing, imported) in enumerate(cases):
            with self.subTest(existing=existing):
                self.root = base / f"dedup-{index}"
                self.root.mkdir()
                chunk = "Retry budget: 3\nTimeout: 10" if "Timeout" in existing else "Retry budget: 3"
                self.write("AGENTS.md", chunk + "\n")
                self.write("docs/PROJECT_CONTEXT.md", "# Context\r\n\r\n" + existing + "\r\n")
                destination = (self.root / "docs/PROJECT_CONTEXT.md").read_bytes()
                plan = self.bind({"rules": [{"start": 1, "end": len(chunk.splitlines()), "action": "context", "reason": "Exact fact preservation"}]})
                bootstrap.run(self.root, plan=plan)
                result = (self.root / "docs/PROJECT_CONTEXT.md").read_bytes()
                self.assertTrue(result.startswith(destination))
                self.assertEqual(b"Imported from prior AGENTS" in result, imported)
                if imported:
                    self.assertIn(chunk.replace("\n", "\r\n").encode(), result[len(destination):])
                else:
                    self.assertEqual(result, destination)

    def test_mature_first_install_can_explicitly_reconcile(self):
        self.write("src/app.py", "# Established application\n")
        self.write("README.md", "Mature offline application; authority is planning/CONTEXT.md\n")
        self.write("planning/CONTEXT.md", "# Existing ledger\nCurrent release state\n")
        info = bootstrap.run(self.root, inspect_only=True)
        self.assertEqual(info["install_state"], "absent")
        self.assertNotIn("mode", info)
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "Explicit semantic"):
            bootstrap.run(self.root, "software")
        self.assertEqual(self.snapshot(), before)
        plan = self.bind({"rules": [], "canonical_sources": {"context": {
            "path": "planning/CONTEXT.md", "evidence": "README explicitly establishes authority"}},
            "invariants": [{"text": "Preserve offline delivery", "evidence": "Documented delivery objective",
                            "evidence_paths": ["README.md", "src/app.py"]}]}, ("README.md", "src/app.py"))
        result = bootstrap.run(self.root, plan=plan)
        self.assertEqual((result["mode"], result["install_state"]), ("reconcile", "absent"))
        for name, data in before.items():
            self.assertEqual(self.snapshot()[name], data)
        self.assertIn("compatibility bridge", (self.root / "docs/PROJECT_CONTEXT.md").read_text())
        self.assertEqual(bootstrap.run(self.root)["changed"], [])

    def test_markdown_relocation_requires_acknowledgement_and_rewrite(self):
        base = self.root
        for index, text in enumerate(("[v2](schemas/v2.json)", "[v2]: schemas/v2.json", "<img src=\"schemas/v2.png\">",
                                     "Read `schemas/v2.json`", "Read schemas/v2.json", "![v2](./schemas/v2.png)")):
            with self.subTest(text=text):
                self.root = base / f"relative-{index}"
                self.root.mkdir()
                self.write("AGENTS.md", text + "\n")
                self.write("schemas/v2.json", "{}\n")
                plan = self.bind({"rules": [{"start": 1, "end": 1, "action": "context", "reason": "Preserve schema reference"}]})
                del plan["rules"][0]["relocation_acknowledgement"]
                self.assert_rejected_without_writes(plan, "relocation_acknowledgement")
                plan["rules"][0].update(text=text.replace("schemas/", "../schemas/"),
                                         relocation_acknowledgement="Rebased root schema references relative to docs/, retaining their targets")
                bootstrap.run(self.root, plan=plan)
                destination = (self.root / "docs/PROJECT_CONTEXT.md").read_text()
                self.assertIn("../schemas/v2", destination)
                self.assertNotIn("](schemas/v2.json)", destination)
                self.assertEqual((self.root / "docs" / "../schemas/v2.json").resolve(), self.root / "schemas/v2.json")

    def test_reference_style_use_cannot_silently_lose_its_definition(self):
        self.write("AGENTS.md", "Schema is [v2][schema].\n[schema]: schemas/v2.json\n")
        plan = self.bind({"rules": [
            {"start": 1, "end": 1, "action": "context", "reason": "Retain schema knowledge"},
            {"start": 2, "end": 2, "action": "invariant", "reason": "Retain original definition"}]})
        del plan["rules"][0]["relocation_acknowledgement"]
        self.assert_rejected_without_writes(plan, "relocation_acknowledgement")
        plan["rules"][0].update(text="Schema is [v2](../schemas/v2.json).",
                                relocation_acknowledgement="Made reference explicit and rebased it to preserve root schema target")
        bootstrap.run(self.root, plan=plan)
        self.assertIn("](../schemas/v2.json)", (self.root / "docs/PROJECT_CONTEXT.md").read_text())

    def test_same_directory_handoff_and_absolute_links_require_relocation(self):
        self.write("AGENTS.md", "[v2](schemas/v2.json)\n[web](https://example.invalid/api/v2)\n")
        plan = self.bind({"rules": [
            {"start": 1, "end": 1, "action": "handoff", "reason": "Same-directory continuation"},
            {"start": 2, "end": 2, "action": "context", "reason": "Absolute external link"}]})
        for rule in plan["rules"]:
            del rule["relocation_acknowledgement"]
        self.assert_rejected_without_writes(plan, "relocation_acknowledgement")
        for rule in plan["rules"]:
            rule["relocation_acknowledgement"] = "verbatim_safe"
        bootstrap.run(self.root, plan=plan)
        self.assertIn("](schemas/v2.json)", (self.root / "HANDOFF.md").read_text())

    def test_bad_parent_rejected_before_any_write(self):
        plan = self.routed_fixture()
        for name in ("docs/PROJECT_CONTEXT.md", "docs/DECISIONS.md"):
            (self.root / name).unlink()
        (self.root / "docs").rmdir()
        self.write("docs", "A file is not an output parent\n")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "Bad parent"):
            bootstrap.run(self.root, plan=plan)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(list(self.root.glob(bootstrap.RECOVERY_PREFIX + "*")))

    def test_output_symlink_escape_rejected_before_writes(self):
        plan = self.routed_fixture()
        (self.root / "docs/PROJECT_CONTEXT.md").unlink()
        (self.root / "docs/DECISIONS.md").unlink()
        (self.root / "docs").rmdir()
        with tempfile.TemporaryDirectory(prefix="harness-output-outside-") as outside:
            external = Path(outside)
            (external / "PROJECT_CONTEXT.md").write_bytes(b"Protected external content\n")
            link = self.root / "docs"
            try:
                link.symlink_to(external, target_is_directory=True)
            except (OSError, NotImplementedError):
                if os.name != "nt":
                    raise
                subprocess.run(["cmd", "/c", "mklink", "/J", str(link), outside], check=True, capture_output=True)
            try:
                with self.assertRaisesRegex(ValueError, "outside the project|Unsafe output"):
                    bootstrap.run(self.root, plan=plan)
                self.assertEqual((external / "PROJECT_CONTEXT.md").read_bytes(), b"Protected external content\n")
            finally:
                link.rmdir() if os.name == "nt" else link.unlink()

    def test_cli_inspect_plan_preview_mutation_apply_zero_writes(self):
        self.write("AGENTS.md", "Retain this source fact\n")
        self.write("evidence/policy.md", "Evidence used in semantic choice\n")
        plan = self.cli_plan(("evidence/policy.md",))
        before = self.snapshot()
        preview = self.cli("--plan", str(plan), "--dry-run")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertEqual(self.snapshot(), before)
        self.write("evidence/policy.md", "Concurrent policy change\n")
        before = self.snapshot()
        result = self.cli("--plan", str(plan))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(list(self.root.glob(bootstrap.RECOVERY_PREFIX + "*")))

    def test_cli_inspect_plan_preview_write_failure_preserves_source(self):
        self.write("AGENTS.md", "Retain this source fact\n")
        plan = self.cli_plan()
        self.assertEqual(self.cli("--plan", str(plan), "--dry-run").returncode, 0)
        source = (self.root / "AGENTS.md").read_bytes()
        result = self.cli("--plan", str(plan), "--test-fault", "replace:docs/PROJECT_CONTEXT.md")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual((self.root / "AGENTS.md").read_bytes(), source)
        pending = json.loads(self.cli("--inspect").stdout)["pending_recovery"]
        self.assertEqual(len(pending), 1)
        manifest = json.loads((Path(pending[0]) / "manifest.json").read_text())
        self.assertEqual(manifest["state"], "rolled-back")
        self.assertEqual((Path(pending[0]) / manifest["originals"]["AGENTS.md"]).read_bytes(), source)

    def test_cli_hard_crash_keeps_source_or_preserved_destination_and_originals(self):
        base = self.root
        for point in ("replace:AGENTS.md", "verify:AGENTS.md"):
            with self.subTest(crash=point):
                self.root = base / point.split(":")[0]
                self.root.mkdir()
                self.write("AGENTS.md", "Retain this source fact\n")
                source = (self.root / "AGENTS.md").read_bytes()
                plan = self.cli_plan()
                result = self.cli("--plan", str(plan), "--test-crash", point)
                self.assertEqual(result.returncode, 91, result.stderr)
                source_survived = (self.root / "AGENTS.md").read_bytes() == source
                destination = (self.root / "docs/PROJECT_CONTEXT.md").read_bytes()
                self.assertTrue(source_survived or b"Retain this source fact" in destination)
                pending = json.loads(self.cli("--inspect").stdout)["pending_recovery"]
                recovery = Path(pending[0])
                manifest = json.loads((recovery / "manifest.json").read_text())
                self.assertEqual((recovery / manifest["originals"]["AGENTS.md"]).read_bytes(), source)
                self.assertEqual(self.cli("--plan", str(plan)).returncode, 2)

    @unittest.skipUnless(os.name == "nt", "Real Windows deny-delete lock")
    def test_cli_windows_target_lock_preserves_source(self):
        import ctypes
        from ctypes import wintypes
        self.write("AGENTS.md", "Retain this source fact\n")
        self.write("docs/PROJECT_CONTEXT.md", "# Current context\n")
        plan = self.cli_plan()
        self.assertEqual(self.cli("--plan", str(plan), "--dry-run").returncode, 0)
        source = (self.root / "AGENTS.md").read_bytes()
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                      wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.CreateFileW(str(self.root / "docs/PROJECT_CONTEXT.md"), 0x80000000, 3, None, 3, 0, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value, ctypes.get_last_error())
        try:
            result = self.cli("--plan", str(plan))
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual((self.root / "AGENTS.md").read_bytes(), source)
            self.assertIn("Retain this source fact", source.decode())
            self.assertTrue(bootstrap.run(self.root, inspect_only=True)["pending_recovery"])
        finally:
            kernel.CloseHandle(handle)

    def test_harness_navigation_and_schema_unchanged(self):
        bootstrap.run(self.root, "software", mode="seed")
        agents = (self.root / "AGENTS.md").read_text()
        for path in ("HANDOFF.md", "docs/PROJECT_CONTEXT.md", "docs/DECISIONS.md"):
            self.assertIn(path, agents)
        self.assertIn("Follow canonical bridges", agents)
        self.assert_layers("software")

    def launch(self, *arguments):
        child = subprocess.Popen([sys.executable, str(Path(bootstrap.__file__).resolve()), str(self.root), *arguments],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        def cleanup():
            if child.poll() is None:
                child.kill()
            child.communicate()
        self.addCleanup(cleanup)
        return child

    def await_pause(self, child):
        import concurrent.futures
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            line = pool.submit(child.stdout.readline).result(timeout=15)
            self.assertEqual(line.strip(), "TEST_PAUSED", line)
        except BaseException:
            child.kill()
            raise
        finally:
            pool.shutdown(wait=True)

    def test_two_process_same_initial_bytes_cannot_overwrite_committed_handoff(self):
        base = self.root
        for phase in ("replace:HANDOFF.md", "cleanup:committed"):
            with self.subTest(window=phase):
                self.root = base / phase.split(":")[0]
                self.root.mkdir()
                plan_a = self.routed_fixture()
                plan_b = copy.deepcopy(plan_a)
                plan_b["rules"][2]["text"] = "OLD_HELPER_B_MUST_NOT_OVERWRITE_A"
                self.assertEqual(plan_a["expected_before"], plan_b["expected_before"])
                paths = [base / f"{self.root.name}-{n}.json" for n in ("A", "B")]
                for plan, plan_path in zip((plan_a, plan_b), paths):
                    plan_path.write_text(json.dumps(plan), encoding="utf-8")
                a = self.launch("--plan", str(paths[0]), "--test-pause", phase)
                self.await_pause(a)
                during = self.snapshot()
                b = self.launch("--plan", str(paths[1]))
                stdout, stderr = b.communicate(timeout=15)
                self.assertEqual(b.returncode, 2, (stdout, stderr))
                self.assertIn("execution lock held", stderr)
                self.assertEqual(self.snapshot(), during)
                stdout, stderr = a.communicate(input="resume\n", timeout=15)
                self.assertEqual(a.returncode, 0, stderr)
                committed = self.snapshot()
                self.assertIn(b"RELEASE_43", committed["HANDOFF.md"][0])
                self.assertNotIn(b"OLD_HELPER_B", committed["HANDOFF.md"][0])
                retry = self.cli("--plan", str(paths[1]))
                self.assertEqual(retry.returncode, 2, retry.stderr)
                self.assertEqual(self.snapshot(), committed)
                self.assertFalse(bootstrap.run(self.root, inspect_only=True)["pending_recovery"])

    def test_process_death_releases_lock_and_preserves_recovery_gate(self):
        self.write("AGENTS.md", "Crash source remains authoritative\n")
        plan = self.cli_plan()
        a = self.launch("--plan", str(plan), "--test-pause", "journal:preparing")
        self.await_pause(a)
        a.kill()
        a.communicate(timeout=15)
        inspection = self.cli("--inspect")
        self.assertEqual(inspection.returncode, 0, inspection.stderr)
        self.assertTrue(json.loads(inspection.stdout)["pending_recovery"])
        retry = self.cli("--plan", str(plan))
        self.assertEqual(retry.returncode, 2)
        self.assertIn("Unresolved recovery", retry.stderr)

    def test_recovery_namespace_does_not_change_with_temp_environment(self):
        self.write("AGENTS.md", "Preserve source through environment changes\n")
        plan = self.cli_plan()
        crashed = self.cli("--plan", str(plan), "--test-crash", "verify:AGENTS.md")
        self.assertEqual(crashed.returncode, 91, crashed.stderr)
        pending = bootstrap.run(self.root, inspect_only=True)["pending_recovery"]
        before = self.snapshot()
        with mock.patch.dict(os.environ, {"TMP": str(self.root), "TEMP": str(self.root), "TMPDIR": str(self.root)}):
            inspected = self.cli("--inspect")
            self.assertEqual(inspected.returncode, 0, inspected.stderr)
            self.assertEqual(json.loads(inspected.stdout)["pending_recovery"], pending)
            retry = self.cli("--plan", str(plan))
            self.assertEqual(retry.returncode, 2)
            self.assertIn("Unresolved recovery", retry.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_private_storage_permission_drift_refuses_before_protocol(self):
        plan = self.routed_fixture()
        state = file_security.storage(self.root)
        before = self.snapshot()
        try:
            if os.name == "nt":
                file_security.put_dacl(state, file_security.descriptor(self.root))
            else:
                state.chmod(0o755)
            with self.assertRaisesRegex(ValueError, "Private recovery storage"):
                bootstrap.run(self.root, plan=plan)
            self.assertEqual(self.snapshot(), before)
            self.assertFalse(list(state.iterdir()))
        finally:
            if os.name == "nt":
                file_security.put_dacl(state, file_security.private_descriptor())
            else:
                state.chmod(0o700)

    def test_markdown_examples_never_suppress_formal_source(self):
        base = self.root
        cases = (
            "```text\n``` invalid closing fence\n\nRetry budget: 3\n\n```\n",
            "<!-- unclosed HTML comment\n\nRetry budget: 3\n",
            "> quoted example\n> Retry budget: 3\n",
            "    Retry budget: 3\n",
        )
        for index, example in enumerate(cases):
            with self.subTest(example=index):
                self.root = base / str(index)
                self.root.mkdir()
                self.write("AGENTS.md", "Retry budget: 3\n")
                self.write("docs/PROJECT_CONTEXT.md", "# Context\n\n" + example)
                original = (self.root / "docs/PROJECT_CONTEXT.md").read_bytes()
                plan = self.bind({"rules": [{"start": 1, "end": 1, "action": "context", "reason": "Unique formal source"}]})
                bootstrap.run(self.root, plan=plan)
                current = (self.root / "docs/PROJECT_CONTEXT.md").read_bytes()
                self.assertEqual(current[:len(original)], original)
                self.assertIn(b"\n\nRetry budget: 3\n", current[len(original):])

    def test_explicit_drop_uses_bound_destination_and_stale_destination_refuses(self):
        self.write("AGENTS.md", "Retry budget: 3\n")
        self.write("HANDOFF.md", "# Formal policy\n\nRetry budget: 3\n")
        plan = self.bind({"rules": [{"start": 1, "end": 1, "action": "drop",
                                  "reason": "Already preserved in HANDOFF formal policy",
                                  "evidence_paths": ["HANDOFF.md"]}]}, ("HANDOFF.md",))
        self.write("HANDOFF.md", "Concurrent changed policy\n")
        self.assert_rejected_without_writes(plan, "STALE PLAN")
        self.write("HANDOFF.md", "# Formal policy\n\nRetry budget: 3\n")
        before = (self.root / "HANDOFF.md").read_bytes()
        bootstrap.run(self.root, plan=plan)
        self.assertEqual((self.root / "HANDOFF.md").read_bytes(), before)

    def test_all_route_actions_require_relocation_even_same_directory_fragment(self):
        base = self.root
        for index, (action, text) in enumerate((
                (action, text) for action in bootstrap.ROUTES for text in (
                    "[Offline policy](#offline)", "[Schema](schemas/v2.json)", "[Offline policy][offline]"))):
            with self.subTest(action=action, text=text):
                self.root = base / str(index)
                self.root.mkdir()
                self.write("AGENTS.md", text + "\n[offline]: #offline\n")
                plan = self.bind({"rules": [
                    {"start": 1, "end": 1, "action": action, "reason": "Retain reference"},
                    {"start": 2, "end": 2, "action": "invariant", "reason": "Definition remains in AGENTS"}]})
                del plan["rules"][0]["relocation_acknowledgement"]
                self.assert_rejected_without_writes(plan, "relocation_acknowledgement")
                plan["rules"][0].update(relocation_acknowledgement="rewritten")
                self.assert_rejected_without_writes(plan, "requires plan text")
                plan["rules"][0]["text"] = "[Offline policy](AGENTS.md#offline)"
                bootstrap.run(self.root, plan=plan)
                self.assertIn("AGENTS.md#offline", (self.root / bootstrap.ROUTES[action]).read_text())

    def test_hardlink_canonical_alias_to_each_output_is_rejected(self):
        base = self.root
        for index, output in enumerate(bootstrap.FILES):
            with self.subTest(output=output):
                self.root = base / str(index)
                self.root.mkdir()
                self.write("AGENTS.md", "Original policy\n")
                if output != "AGENTS.md":
                    self.write(output, '[harness]\nversion = 1\n' if output.endswith("toml") else "Original destination\n")
                source = self.root / "canonical.md"
                os.link(self.root / output, source)
                self.assertTrue(os.path.samefile(source, self.root / output))
                plan = self.bind({"canonical_sources": {"context": {"path": "canonical.md", "evidence": "Explicit authority"}},
                                  "rules": [{"start": 1, "end": 1, "action": "drop", "reason": "Preserved by source"}]})
                self.assert_rejected_without_writes(plan, "Harness output/bridge")

    def test_in_root_canonical_symlink_or_junction_alias_rejected(self):
        self.write("AGENTS.md", "Original policy\n")
        self.write("ledger/source.md", "Canonical knowledge\n")
        alias = self.root / "alias"
        try:
            alias.symlink_to(self.root / "ledger", target_is_directory=True)
        except (OSError, NotImplementedError):
            if os.name != "nt":
                raise
            subprocess.run(["cmd", "/c", "mklink", "/J", str(alias), str(self.root / "ledger")], check=True, capture_output=True)
        try:
            plan = self.bind({"canonical_sources": {"context": {"path": "alias/source.md", "evidence": "Explicit authority"}},
                              "rules": [{"start": 1, "end": 1, "action": "drop", "reason": "Preserved by source"}]})
            self.assert_rejected_without_writes(plan, "Unsafe output")
        finally:
            alias.rmdir() if os.name == "nt" else alias.unlink()

    def test_canonical_hardlink_to_non_output_also_refuses(self):
        self.write("AGENTS.md", "Original policy\n")
        self.write("ledger.md", "Canonical knowledge\n")
        os.link(self.root / "ledger.md", self.root / "alias.md")
        plan = self.bind({"canonical_sources": {"context": {"path": "alias.md", "evidence": "Explicit authority"}},
                          "rules": [{"start": 1, "end": 1, "action": "drop", "reason": "Already preserved"}]})
        self.assert_rejected_without_writes(plan, "hardlink alias")

    @unittest.skipUnless(os.name == "nt", "Real Windows restrictive DACL")
    def test_windows_restrictive_acl_preserved_on_apply_and_rollback(self):
        base = self.root
        for fail in (False, True):
            with self.subTest(rollback=fail):
                self.root = base / str(fail)
                self.root.mkdir()
                plan = self.routed_fixture()
                target = self.root / "HANDOFF.md"
                file_security.put_dacl(target, file_security.private_descriptor())
                initial = file_security.security_parts(file_security.descriptor(target))
                self.assertNotEqual(initial[3], file_security.security_parts(file_security.descriptor(self.root))[3])
                def fault(phase, name):
                    if fail and (phase, name) == ("verify", "HANDOFF.md"):
                        raise OSError("Trigger restrictive destination rollback")
                if fail:
                    with self.assertRaises(bootstrap.ApplyError):
                        bootstrap.run(self.root, plan=plan, fault=fault)
                else:
                    bootstrap.run(self.root, plan=plan)
                self.assertEqual(file_security.security_parts(file_security.descriptor(target)), initial)
                observed = subprocess.run(["icacls", str(target)], capture_output=True, text=True)
                self.assertEqual(observed.returncode, 0, observed.stderr)
                self.assertNotIn("Everyone:", observed.stdout)

    @unittest.skipUnless(os.name == "nt", "Real Windows recovery DACL")
    def test_windows_failed_recovery_backup_not_more_public_than_source(self):
        plan = self.routed_fixture()
        source = self.root / "AGENTS.md"
        file_security.put_dacl(source, file_security.private_descriptor())
        original = file_security.security_parts(file_security.descriptor(source))
        def fault(phase, name):
            if (phase, name) in (("verify", "AGENTS.md"), ("rollback", "AGENTS.md")):
                raise OSError("Retain failed recovery raw originals")
        with self.assertRaises(bootstrap.ApplyError) as failed:
            bootstrap.run(self.root, plan=plan, fault=fault)
        recovery = failed.exception.recovery
        self.assertFalse(recovery.is_relative_to(self.root))
        backup = recovery / "original-0.bin"
        self.assertEqual(file_security.security_parts(file_security.descriptor(backup)), original)
        self.assertEqual(file_security.security_parts(file_security.descriptor(source)), original)
        file_security.private_directory(recovery)  # Validate root security independently of payload ACL.

    def assert_everyone_access(self, path, allowed, directory=False):
        with everyone_restricted_token():
            handle, error = windows_open(path, directory)
            if handle != file_security.P(-1).value:
                file_security.close_handle(handle)
        if allowed:
            self.assertNotEqual(handle, file_security.P(-1).value, (str(path), error))
        else:
            self.assertEqual(handle, file_security.P(-1).value, str(path))
            self.assertEqual(error, 5, (str(path), error))  # ERROR_ACCESS_DENIED, not missing path.

    @unittest.skipUnless(os.name == "nt", "Real Windows restricted-token known-path access")
    def test_windows_public_source_private_known_path_backup_and_all_payloads(self):
        plan = self.routed_fixture()
        source = self.root / "AGENTS.md"
        file_security.put_dacl(source, windows_sddl(f"D:P(A;;FA;;;{file_security.user_sid()})(A;;GR;;;WD)"))
        original = source.read_bytes()
        original_metadata = file_security.descriptor(source)
        self.assert_everyone_access(source, True)  # Positive control for the actual token.
        checked_stages = []
        def fault(phase, name):
            if (phase, name) == ("stage-verify", "HANDOFF.md"):
                recovery = next(file_security.storage(self.root).glob(bootstrap.RECOVERY_PREFIX + "*"))
                self.assert_everyone_access(recovery, False, directory=True)
                for payload in recovery.iterdir():
                    self.assert_everyone_access(payload.resolve(), False)
                    payload.read_bytes()  # Recovery subject can read every internal artifact.
                    checked_stages.append(payload.name)
                raise OSError("Keep private recovery evidence")
        with self.assertRaises(bootstrap.ApplyError) as failed:
            bootstrap.run(self.root, plan=plan, fault=fault)
        recovery = failed.exception.recovery
        backup = (recovery / "original-0.bin").resolve()
        self.assert_everyone_access(recovery, False, directory=True)
        self.assert_everyone_access(recovery / "manifest.json", False)
        self.assert_everyone_access(backup, False)
        self.assertEqual(backup.read_bytes(), original)
        manifest = json.loads((recovery / "manifest.json").read_text())
        self.assertEqual(manifest["original_metadata"]["AGENTS.md"]["windows_descriptor"], original_metadata.hex())
        self.assertTrue(any(name.startswith("stage-") for name in checked_stages))
        self.assertEqual(source.read_bytes(), original)
        self.assert_everyone_access(source, True)

    def metadata_mutation_then_real_replace_failure(self, mutation, field):
        plan = self.routed_fixture()
        target = self.root / "HANDOFF.md"
        file_security.put_dacl(target, windows_sddl(f"D:P(A;;FA;;;{file_security.user_sid()})(A;;GR;;;WD)"))
        self.assert_everyone_access(target, True)
        before = target.read_bytes()
        lock, error = windows_open(self.root / "docs/PROJECT_CONTEXT.md", share=3)  # Deny FILE_SHARE_DELETE.
        self.assertNotEqual(lock, file_security.P(-1).value, error)
        observed = {}
        def fault(phase, name):
            if (phase, name) == ("verify", "HANDOFF.md"):
                observed["committed"] = file_security.file_state(target)
                # A separate real process mutates only metadata/ADS after apply.
                result = subprocess.run([sys.executable, "-c", mutation, str(target),
                                         str(Path(file_security.__file__).parent)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                observed["external"] = file_security.file_state(target)
                self.assertEqual(observed["committed"]["main_sha256"], observed["external"]["main_sha256"])
        try:
            with self.assertRaises(bootstrap.ApplyError) as failed:
                bootstrap.run(self.root, plan=plan, fault=fault)
        finally:
            file_security.close_handle(lock)
        failure = failed.exception
        self.assertEqual(failure.state, "rollback-incomplete")
        self.assertIsInstance(failure.__cause__, PermissionError)  # Actual later os.replace sharing violation.
        self.assertIn(failure.__cause__.winerror, (5, 32))
        self.assertNotEqual(target.read_bytes(), before)
        self.assertEqual(file_security.file_state(target), observed["external"])
        manifest = json.loads((failure.recovery / "manifest.json").read_text())
        self.assertEqual(manifest["state"], "rollback-incomplete")
        self.assertEqual(manifest["committed_states"]["HANDOFF.md"], observed["committed"])
        self.assertIn(field, "\n".join(manifest["rollback_errors"]))
        self.assertIn(field, str(failure))
        self.assertEqual((failure.recovery / manifest["originals"]["HANDOFF.md"]).read_bytes(), before)
        return target

    @unittest.skipUnless(os.name == "nt", "Real external ACL tightening + later deny-delete replace failure")
    def test_windows_acl_tightening_during_apply_blocks_rollback(self):
        target = self.metadata_mutation_then_real_replace_failure(
            "import sys; sys.path.insert(0,sys.argv[2]); import file_security as s; "
            "s.put_dacl(sys.argv[1],s.private_descriptor(False))", "dacl")
        self.assert_everyone_access(target, False)

    @unittest.skipUnless(os.name == "nt", "Real external ADS creation + later deny-delete replace failure")
    def test_windows_ads_created_during_apply_blocks_rollback(self):
        target = self.metadata_mutation_then_real_replace_failure(
            "import sys; from pathlib import Path; Path(sys.argv[1]+':external-stream').write_bytes(b'EXTERNAL_ADS_93')", "ads")
        self.assertEqual(Path(str(target) + ":external-stream").read_bytes(), b"EXTERNAL_ADS_93")

    @unittest.skipUnless(os.name == "nt", "Real protection-only metadata drift")
    def test_windows_protection_drift_blocks_rollback(self):
        target = self.metadata_mutation_then_real_replace_failure(
            "import sys; sys.path.insert(0,sys.argv[2]); import file_security as s; "
            "s.put_dacl(sys.argv[1],s.descriptor(sys.argv[1]),False)", "dacl_protected")
        self.assertFalse(file_security.security_parts(file_security.descriptor(target))[4])

    @unittest.skipUnless(os.name == "nt", "Real external group change")
    def test_windows_group_drift_blocks_rollback(self):
        self.metadata_mutation_then_real_replace_failure(
            "import sys; sys.path.insert(0,sys.argv[2]); import file_security as s; "
            "sd,size=s.P(),s.W.DWORD(); s.checked(s.from_sddl('G:WD',1,s.C.byref(sd),s.C.byref(size))); "
            "s.checked(s.set_security(sys.argv[1],2,sd)); s.local_free(sd)", "group")

    @unittest.skipUnless(os.name == "nt", "Real external unsupported attribute change")
    def test_windows_attribute_drift_blocks_rollback(self):
        target = self.metadata_mutation_then_real_replace_failure(
            "import sys; sys.path.insert(0,sys.argv[2]); import file_security as s; "
            "s.checked(s.set_attributes(sys.argv[1],0x22))", "attributes")
        self.assertTrue(target.stat().st_file_attributes & 2)

    @unittest.skipUnless(os.name == "nt", "Real future parent DACL propagation")
    def test_windows_reconcile_protects_existing_dacl_from_future_parent_inheritance(self):
        sid = file_security.user_sid()
        file_security.put_dacl(self.root, windows_sddl(f"D:P(A;OICI;FA;;;{sid})"))
        plan = self.routed_fixture()
        target = self.root / "HANDOFF.md"
        initial = file_security.security_parts(file_security.descriptor(target))
        self.assertFalse(initial[4])
        control = self.root / "unprotected-control.txt"
        control.write_bytes(b"Parent propagation positive control")
        bootstrap.run(self.root, plan=plan)
        actual = file_security.security_parts(file_security.descriptor(target))
        self.assertEqual(actual[:4], initial[:4])
        self.assertTrue(actual[4])
        file_security.put_dacl(self.root, windows_sddl(f"D:P(A;OICI;FA;;;{sid})(A;OICI;GR;;;WD)"))
        self.assertEqual(file_security.security_parts(file_security.descriptor(target)), actual)
        self.assert_everyone_access(target, False)
        self.assert_everyone_access(control, True)
        self.assertEqual(bootstrap.run(self.root)["changed"], [])

    @unittest.skipUnless(os.name == "nt", "Real Seed private DACL inheritance control")
    def test_windows_seed_remains_private_after_parent_grant(self):
        sid = file_security.user_sid()
        file_security.put_dacl(self.root, windows_sddl(f"D:P(A;OICI;FA;;;{sid})"))
        bootstrap.run(self.root, "software", mode="seed")
        for name in bootstrap.FILES:
            self.assertTrue(file_security.security_parts(file_security.descriptor(self.root / name))[4])
        file_security.put_dacl(self.root, windows_sddl(f"D:P(A;OICI;FA;;;{sid})(A;OICI;GR;;;WD)"))
        for name in bootstrap.FILES:
            self.assert_everyone_access(self.root / name, False)

    @unittest.skipUnless(os.name == "nt", "Windows protection preflight fail closed")
    def test_windows_unprovable_protection_refuses_before_payload_or_project_write(self):
        plan = self.routed_fixture()
        before = self.snapshot()
        put = file_security.put_dacl
        calls = {}
        def leave_unprotected(path, sd, protected=True):
            calls[str(path)] = calls.get(str(path), 0) + 1
            put(path, sd, False if Path(path).name.startswith("probe-") and calls[str(path)] > 1 else protected)
        with mock.patch.object(file_security, "put_dacl", side_effect=leave_unprotected):
            with self.assertRaisesRegex(OSError, "metadata changed"):
                bootstrap.run(self.root, plan=plan)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(list(file_security.storage(self.root).iterdir()), [])

    @unittest.skipUnless(os.name == "nt", "Real NTFS alternate data stream")
    def test_ntfs_ads_refuses_before_any_project_or_recovery_payload_write(self):
        plan = self.routed_fixture()
        target = self.root / "HANDOFF.md"
        ads = Path(str(target) + ":harness-secret")
        ads.write_bytes(b"ADS must survive")
        self.assertEqual(ads.read_bytes(), b"ADS must survive")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "alternate data stream"):
            bootstrap.run(self.root, plan=plan)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(ads.read_bytes(), b"ADS must survive")
        self.assertFalse(bootstrap.run(self.root, inspect_only=True)["pending_recovery"])

    @unittest.skipUnless(os.name == "nt", "Real Windows mandatory integrity label")
    def test_windows_explicit_integrity_label_refused_before_write(self):
        plan = self.routed_fixture()
        target = self.root / "HANDOFF.md"
        result = subprocess.run(["icacls", str(target), "/setintegritylevel", "L"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "integrity label"):
            bootstrap.run(self.root, plan=plan)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(bootstrap.run(self.root, inspect_only=True)["pending_recovery"])

    def test_failure_and_crash_recovery_raw_bytes_invisible_to_git_add_all(self):
        base = self.root
        for crash in (False, True):
            with self.subTest(crash=crash):
                self.root = base / str(crash)
                self.root.mkdir()
                subprocess.run(["git", "init", "--quiet", str(self.root)], check=True, capture_output=True)
                self.write("AGENTS.md", "RAW_ORIGINAL_CONFIDENTIAL_62\n")
                plan = self.cli_plan()
                failure = self.cli("--plan", str(plan), "--test-crash" if crash else "--test-fault", "verify:AGENTS.md")
                self.assertEqual(failure.returncode, 91 if crash else 2, failure.stderr)
                pending = bootstrap.run(self.root, inspect_only=True)["pending_recovery"]
                self.assertEqual(len(pending), 1)
                recovery = Path(pending[0])
                self.assertFalse(recovery.is_relative_to(self.root))
                self.assertEqual((recovery / "original-0.bin").read_bytes(), b"RAW_ORIGINAL_CONFIDENTIAL_62\n")
                dry_run = subprocess.run(["git", "-C", str(self.root), "add", "--dry-run", "--all"], capture_output=True, text=True)
                self.assertEqual(dry_run.returncode, 0, dry_run.stderr)
                self.assertNotIn(bootstrap.RECOVERY_PREFIX, dry_run.stdout)
                self.assertNotIn("original-", dry_run.stdout)
                self.assertNotIn("stage-", dry_run.stdout)
                visible = {p.relative_to(self.root).as_posix() for p in self.root.rglob("*")
                           if p.is_file() and ".git" not in p.relative_to(self.root).parts}
                self.assertEqual(visible, set(bootstrap.FILES) if crash else {"AGENTS.md"})

    @unittest.skipUnless(os.name == "posix", "POSIX mode/xattr boundary")
    def test_posix_restrictive_mode_preserved_and_xattr_refused(self):
        plan = self.routed_fixture()
        target = self.root / "HANDOFF.md"
        target.chmod(0o600)
        bootstrap.run(self.root, plan=plan)
        self.assertEqual(target.stat().st_mode & 0o7777, 0o600)
        os.setxattr(target, "user.harness", b"Extended metadata")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "extended metadata"):
            bootstrap.run(self.root, profile="research")
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
