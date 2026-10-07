"""Deterministic five-file writer; semantic/profile decisions belong to Codex."""

import argparse
import copy
import difflib
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import tomllib
import uuid

import file_security

SKILL = Path(__file__).resolve().parents[1]
FILES = ("AGENTS.md", "HANDOFF.md", "docs/PROJECT_CONTEXT.md",
         "docs/DECISIONS.md", ".harness/config.toml")
PROFILES = ("software", "research", "competition")
ROUTES = {"context": FILES[2], "handoff": FILES[1], "decision": FILES[3]}
PLAN_PROTOCOL = 1  # Independent of Harness schema 2.
RECOVERY_PREFIX = ".dev-harness-recovery-"


def project_path(root, value, output=False):
    if not isinstance(value, str) or not value or any(c in value for c in "\r\n`\x00:"):
        raise ValueError("Expected a safe project-relative path")
    path = Path(value.replace("\\", "/"))
    if path.is_absolute() or PureWindowsPath(value).drive or PureWindowsPath(value).root:
        raise ValueError("Path must be project-relative")
    if ".." in path.parts or not (root / path).resolve().is_relative_to(root):
        raise ValueError("Path resolves outside the project")
    target = root / path
    if output:
        for part in (target, *target.parents):
            if part == root:
                break
            if part.is_symlink() or (os.path.lexists(part) and getattr(part.lstat(), "st_file_attributes", 0) & 0x400):
                raise ValueError(f"Unsafe output path: {value}")
            if part != target and part.exists() and not part.is_dir():
                raise ValueError(f"Bad parent for output: {value}")
    if target.exists() and not target.is_file():
        raise ValueError(f"Expected regular file: {value}")
    return target


def digest(data):
    return hashlib.sha256(data).hexdigest()


def decode(data):
    return data.decode("utf-8-sig")


def encode(text, original=b""):
    newline = "\r\n" if b"\r\n" in original else "\n"
    data = text.replace("\r\n", "\n").replace("\n", newline).encode("utf-8")
    return (b"\xef\xbb\xbf" if original.startswith(b"\xef\xbb\xbf") else b"") + data


def encode_exact(text, original=b""):
    return (b"\xef\xbb\xbf" if original.startswith(b"\xef\xbb\xbf") else b"") + text.encode("utf-8")


def boundaries(text):
    spans = {}
    tokens = []
    for name in ("core", "profile"):
        start = f"<!-- dev-harness:{name}:start -->"
        end = f"<!-- dev-harness:{name}:end -->"
        tokens.extend((start, end))
        if start not in text and end not in text:
            continue
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError(f"Malformed {name} boundaries; preserve and repair first")
        a, b = text.index(start), text.index(end)
        if a >= b or text[a + len(start):b].strip().startswith("## Project-specific invariants"):
            raise ValueError(f"Invalid {name} section")
        spans[name] = (a, b + len(end))
    if "dev-harness:" in text:
        residue = text
        for token in tokens:
            residue = residue.replace(token, "")
        if "dev-harness:" in residue or len(spans) != 2:
            raise ValueError("Unknown or incomplete managed boundaries")
    if spans:
        if spans["core"][1] > spans["profile"][0]:
            raise ValueError("Overlapping or out-of-order managed sections")
        for a, b in spans.values():
            if "## Project-specific invariants" in text[a:b]:
                raise ValueError("Project invariants must remain outside managed sections")
    return spans


def read_project(root):
    before = {}
    for name in FILES:
        path = project_path(root, name, output=True)
        before[name] = path.read_bytes() if path.exists() else None
    return before


def inspect(before):
    agents = decode(before[FILES[0]] or b"")
    spans = boundaries(agents)
    config = tomllib.loads(decode(before[FILES[4]] or b""))
    harness = config.get("harness", {})
    if not isinstance(harness, dict):
        raise ValueError("harness must be a TOML table")
    version = harness.get("version", 0)
    if type(version) is not int or version < 0 or version > 2:
        raise ValueError("Unsupported harness version; do not downgrade")
    if spans and version == 2 and harness.get("profile") in PROFILES:
        state = "managed-v2"
    elif any(before[name] is not None for name in FILES):
        state = "unmanaged/legacy"
    else:
        state = "absent"
    return {"install_state": state, "configured_profile": harness.get("profile"),
            "version": version, "agents_sha256": digest(before[FILES[0]] or b""),
            "legacy_lines": [] if spans else [
                {"line": i, "text": line} for i, line in enumerate(agents.splitlines(), 1)],
            "expected_before": {name: digest(data) if data is not None else None
                             for name, data in before.items()}}


def read_set(root, paths):
    result = []
    for value in paths:
        path = project_path(root, value)
        if not path.is_file():
            raise ValueError(f"Read-set dependency must exist and be a regular file: {value}")
        name = path.relative_to(root).as_posix()
        if name in {item["path"] for item in result}:
            raise ValueError(f"Duplicate read-set path: {name}")
        result.append({"path": name, "sha256": digest(path.read_bytes())})
    return result


def validate_plan(root, before, info, plan, mode, profile):
    if plan is not None and not isinstance(plan, dict):
        raise ValueError("Plan must be an object")
    if mode != "reconcile":
        return
    if plan is None or plan.get("protocol") != PLAN_PROTOCOL or type(plan.get("protocol")) is not int:
        raise ValueError("Reconcile requires plan protocol 1; regenerate legacy plans")
    allowed = {"protocol", "mode", "profile", "mode_evidence", "profile_evidence",
               "expected_before", "read_set", "rules", "invariants", "canonical_sources"}
    if set(plan) - allowed:
        raise ValueError(f"Unknown Reconcile plan fields: {sorted(set(plan) - allowed)}")
    if plan.get("mode") != mode or plan.get("profile") != profile:
        raise ValueError("Plan mode/profile must match the requested semantic intent")
    for key in ("mode_evidence", "profile_evidence"):
        if not isinstance(plan.get(key), str) or not plan[key].strip():
            raise ValueError(f"Reconcile requires {key}")
    expected = plan.get("expected_before")
    if not isinstance(expected, dict) or set(expected) != set(FILES):
        raise ValueError("Plan must bind expected-before for all five Harness outputs")
    if expected != info["expected_before"]:
        raise ValueError("STALE PLAN: Harness output changed; zero writes")
    entries = plan.get("read_set")
    if not isinstance(entries, list):
        raise ValueError("Plan requires an explicit decision read_set")
    paths = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
            raise ValueError("Read-set entries require path and SHA256")
        sha = entry["sha256"]
        if not isinstance(sha, str) or not re.fullmatch(r"[a-f0-9]{64}", sha):
            raise ValueError("Read-set SHA256 must be a lowercase hex digest")
        path = project_path(root, entry["path"])
        if path.relative_to(root).as_posix() != entry["path"]:
            raise ValueError("Read-set paths must use normalized project-relative spelling")
        if not path.is_file():
            raise ValueError(f"STALE PLAN: dependency disappeared: {entry['path']}; zero writes")
        paths.append(entry["path"])
    if before[FILES[0]] is not None and FILES[0] not in paths:
        raise ValueError("AGENTS must belong to the decision read set")
    if read_set(root, paths) != entries:
        raise ValueError("STALE PLAN: decision dependency changed; zero writes")


def evidence_paths(item, declared, required=False):
    paths = item.get("evidence_paths", [])
    if not isinstance(paths, list) or (required and not paths) or any(not isinstance(path, str) or path not in declared for path in paths):
        raise ValueError("evidence_paths must refer to declared decision read-set files")


def validate_bindings(root, before, plan, mode, applied=None, after=None):
    """One combined gate before any write; repeated before source removal."""
    current = read_project(root)
    expected = dict(before)
    for name in applied or ():
        expected[name] = after[name]
    if current != expected:
        raise ValueError("STALE PLAN: Harness output changed")
    if mode == "reconcile":
        for entry in plan["read_set"]:
            path = project_path(root, entry["path"])
            data = path.read_bytes() if path.is_file() else None
            sha = digest(expected[entry["path"]]) if entry["path"] in (applied or ()) else entry["sha256"]
            if data is None or digest(data) != sha:
                raise ValueError(f"STALE PLAN: dependency changed: {entry['path']}")


def update_config(original, profile):
    text = decode(original or b"")
    old = tomllib.loads(text)
    lines = text.splitlines(keepends=True)
    headers = list(re.finditer(r"^\s*\[harness\]\s*(?:#.*)?$", text, re.M))
    if not headers:
        if "harness" in old:
            raise ValueError("Use a standard [harness] table; preserve other TOML data")
        template = (SKILL / "assets/harness/.harness/config.toml").read_text(encoding="utf-8")
        result = text.rstrip("\r\n") + ("\n\n" if text else "") + template.replace("{{profile}}", profile)
    else:
        active, found = False, set()
        output = []
        values = {"version": "2", "profile": json.dumps(profile)}

        def add_missing():
            additions = [f"{key} = {value}\n" for key, value in values.items() if key not in found]
            if additions and output and not output[-1].endswith("\n"):
                output.append("\n")
            output.extend(additions)

        for line in lines:
            if re.match(r"^\s*\[", line):
                if active:
                    add_missing()
                active = bool(re.match(r"^\s*\[harness\]\s*(?:#.*)?$", line))
            if active:
                match = re.match(r'^(\s*)(version|profile)(\s*=\s*)([^\r\n]*)(\r?\n)?$', line)
                if match:
                    indent, key, sep, value, ending = match.groups()
                    # Restrict this mechanical patch to ordinary scalar keys.
                    if not re.fullmatch(r'(?:\d+|"[^"\n]*"|\x27[^\x27\n]*\x27)\s*(?:#.*)?', value):
                        raise ValueError(f"Unsupported {key} syntax; preserve and normalize first")
                    comment = re.search(r"\s+#.*$", value)
                    line = indent + key + sep + values[key] + (comment.group() if comment else "") + (ending or "\n")
                    found.add(key)
            output.append(line)
        if active:
            add_missing()
        result = "".join(output)
    expected = copy.deepcopy(old)
    expected.setdefault("harness", {}).update(version=2, profile=profile)
    if tomllib.loads(result) != expected:
        raise ValueError("Config update would alter unrelated metadata")
    # Keep original bytes, comments, spelling and timestamps on a semantic no-op.
    return original if old == expected else encode_exact(result, original or b"")


def reconcile(text, plan):
    lines = text.splitlines()
    accounted = set()
    invariants, routes, decisions = [], {name: [] for name in ROUTES}, []
    if not isinstance(plan.get("rules"), list):
        raise ValueError("Reconcile requires a rules list (empty for absent AGENTS)")
    for rule in plan["rules"]:
        if not isinstance(rule, dict):
            raise ValueError("Each rule must be an object")
        if set(rule) - {"start", "end", "action", "reason", "text", "relocation_acknowledgement", "evidence_paths"}:
            raise ValueError("Unknown rule fields")
        evidence_paths(rule, {entry["path"] for entry in plan["read_set"]})
        start, end = rule["start"], rule["end"]
        action, reason = rule["action"], rule.get("reason", "")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("Every range requires a semantic reason")
        if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(lines):
            raise ValueError("Rule range is outside the old AGENTS")
        covered = set(range(start, end + 1))
        if covered & accounted or not reason:
            raise ValueError("Every range must be disjoint and have a semantic reason")
        accounted.update(covered)
        original = "\n".join(lines[start - 1:end])
        body = rule.get("text", original)
        if not isinstance(body, str):
            raise ValueError("Rule text must be a string")
        body = body.replace("\r\n", "\n").strip("\n")
        if action == "invariant":
            invariants.append(body)
        elif action in ROUTES:
            acknowledgement = rule.get("relocation_acknowledgement")
            if not isinstance(acknowledgement, str) or not acknowledgement.strip():
                raise ValueError("Every route requires explicit relocation_acknowledgement")
            if acknowledgement == "rewritten" and "text" not in rule:
                raise ValueError("rewritten relocation requires plan text")
            routes[action].append(body)
        elif action not in ("merge", "drop"):
            raise ValueError(f"Unknown reconciliation action: {action}")
        if action not in ("merge", "drop") and not body.strip():
            raise ValueError("Preserved/moved rules cannot have empty text")
        decisions.append({"lines": [start, end], "action": action, "reason": reason})
    required = {i for i, line in enumerate(lines, 1) if line.strip()}
    if required - accounted:
        raise ValueError(f"Unaccounted old guidance lines: {sorted(required - accounted)}")
    return invariants, routes, decisions


def canonical_bridge(action, path):
    if action == "context":
        title, statement, content = "Project Context", "Canonical current project state is maintained in:", "dynamic project state"
    else:
        title, statement, content = "Decisions", "Canonical project decisions and rationale are maintained in:", "the decision ledger"
    return (f"# {title}\n\n{statement}\n\n`{path}`\n\n"
            "This file is a Dev Harness compatibility bridge. Read and update the canonical "
            f"source rather than duplicating {content} here.\n")


def validate_canonical_sources(root, before, info, plan):
    if plan is None or "canonical_sources" not in plan:
        return {}
    if info["mode"] != "reconcile":
        raise ValueError("canonical_sources is only supported for Reconcile")
    declared = plan["canonical_sources"]
    if not isinstance(declared, dict) or set(declared) - {"context", "decision"}:
        raise ValueError("canonical_sources accepts only context and decision entries")
    sources = {}
    for action, item in declared.items():
        if not isinstance(item, dict):
            raise ValueError(f"Canonical {action} requires path and evidence")
        if set(item) - {"path", "evidence"}:
            raise ValueError(f"Unknown canonical {action} fields")
        value, evidence = item.get("path"), item.get("evidence")
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Canonical {action} requires a project-relative path")
        if not isinstance(evidence, str) or not evidence.strip():
            raise ValueError(f"Canonical {action} requires concrete project evidence")
        target = project_path(root, value, output=True)  # Reject symlink/reparse aliases, even in-root.
        path = target.relative_to(root)
        resolved = target.resolve()
        if not resolved.is_file():
            raise ValueError(f"Canonical {action} source must exist and be a regular file")
        # A canonical store must not be one of the files this writer may change.
        if resolved in {(root / name).resolve() for name in FILES} or any(
                (root / name).exists() and os.path.samefile(target, root / name) for name in FILES):
            raise ValueError(f"Canonical {action} source cannot be a Harness output/bridge")
        if target.stat().st_nlink != 1:
            raise ValueError(f"Canonical {action} source cannot be a hardlink alias")
        if path.as_posix() not in {item["path"] for item in plan["read_set"]}:
            raise ValueError(f"Canonical {action} source must belong to the decision read set")
        if any(rule.get("action") == action for rule in plan.get("rules", [])):
            raise ValueError(f"Canonical {action} source conflicts with action={action}; "
                             "resolve semantic uncertainty and update the canonical source first")
        sources[action] = path.as_posix()
        destination = ROUTES[action]
        existing = before[destination]
        if existing is not None and decode(existing).replace("\r\n", "\n") != canonical_bridge(action, sources[action]):
            raise ValueError(f"Existing {destination} is not the same canonical Harness bridge; "
                             "preserve its content and resolve semantic uncertainty first")
    return sources


def prepare(before, info, profile, plan, canonical_sources=None):
    after = dict(before)
    old_agents = decode(before[FILES[0]] or b"")
    spans = boundaries(old_agents)
    core = (SKILL / "assets/core.md").read_text(encoding="utf-8").strip()
    stance = (SKILL / f"assets/profiles/{profile}.md").read_text(encoding="utf-8").strip()
    routes, decisions = {name: [] for name in ROUTES}, []
    if info["mode"] == "maintain":
        if plan is not None:
            raise ValueError("Maintain preserves unmanaged content; omit the reconciliation plan")
        # Reverse order makes offsets stable and leaves every unmanaged character untouched.
        agents = old_agents
        newline = "\r\n" if b"\r\n" in (before[FILES[0]] or b"") else "\n"
        for name, content in (("profile", stance), ("core", core)):
            a, b = spans[name]
            replacement = f"<!-- dev-harness:{name}:start -->\n{content}\n<!-- dev-harness:{name}:end -->".replace("\n", newline)
            agents = agents[:a] + replacement + agents[b:]
    else:
        if spans:
            raise ValueError("Managed guidance without metadata: restore metadata without rebuilding unique content")
        if info["mode"] == "reconcile":
            if plan is None:
                raise ValueError("Reconcile requires an explicit semantic plan")
            invariants, routes, decisions = reconcile(old_agents, plan)
        else:
            invariants = []
        items = (plan or {}).get("invariants", [])
        if not isinstance(items, list):
            raise ValueError("invariants must be a list")
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("text"), str) or not isinstance(item.get("evidence"), str) or not item["text"].strip() or not item["evidence"].strip():
                raise ValueError("New invariants require text and concrete project evidence")
            if set(item) - {"text", "evidence", "evidence_paths"}:
                raise ValueError("Unknown invariant fields")
            if info["mode"] == "reconcile":
                evidence_paths(item, {entry["path"] for entry in plan["read_set"]}, required=True)
            invariants.append(item["text"].strip())
        agents = (SKILL / "assets/harness/AGENTS.md").read_text(encoding="utf-8")
        agents = agents.replace("{{core}}", core).replace("{{profile}}", stance).replace("{{invariants}}", "\n\n" + "\n\n".join(invariants) if invariants else "")
    boundaries(agents)
    after[FILES[0]] = (encode_exact if info["mode"] == "maintain" else encode)(agents, before[FILES[0]] or b"")
    for action, path in (canonical_sources or {}).items():
        name = ROUTES[action]
        if after[name] is None:
            after[name] = encode(canonical_bridge(action, path))
    for name in FILES[1:4]:
        if after[name] is None:
            after[name] = (SKILL / "assets/harness" / name).read_bytes()
    for action, chunks in routes.items():
        name = ROUTES[action]
        if chunks:
            # Preserve every existing byte; normalize only the appended material.
            suffix = "\n\n## Imported from prior AGENTS\n\nHistorical source; verify current status before relying on it.\n\n" + "\n\n".join(chunks) + "\n"
            after[name] += encode(suffix, after[name]).removeprefix(b"\xef\xbb\xbf")
    after[FILES[4]] = update_config(before[FILES[4]], profile)
    return after, decisions


class ApplyError(OSError):
    def __init__(self, recovery, state, cause, rollback_errors=()):
        self.recovery, self.state, self.rollback_errors = recovery, state, list(rollback_errors)
        super().__init__(f"Apply failed ({state}): {cause}; recovery evidence: {recovery}. "
                         + ("Rollback blockers: " + "; ".join(rollback_errors) + ". " if rollback_errors else "") +
                         "Review originals/manifest before retrying; do not delete unresolved backups.")


def durable_write(path, data):
    # Callers create and verify the empty file's access metadata before payload.
    with path.open("r+b") as stream:
        if stream.read(1):
            raise OSError(f"Expected empty secured artifact: {path}")
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    if path.read_bytes() != data:
        raise OSError(f"Staged-byte verification failed: {path}")


def apply_outputs(root, before, after, changed, plan, mode, state_home, fault=None):
    """Staged, ordered replacements with recovery; NOT a multi-file atomic transaction."""
    def checkpoint(phase, name):
        if fault:
            fault(phase, name)

    validate_bindings(root, before, plan, mode)  # Zero writes before this gate.
    if not changed:
        return
    # All known unsupported metadata fails before any project/recovery payload write.
    metadata = {name: file_security.metadata(root / name) for name in FILES if before[name] is not None}
    if state_home.stat().st_dev != root.stat().st_dev:
        raise ValueError("Recovery/staging storage must share the project's filesystem; zero target writes")
    original_states = {name: file_security.file_state(root / name) for name in FILES}
    # Prove the promised target permissions/protection with EMPTY probes before
    # writing any recovery bytes or changing a destination.
    for name in changed:
        if name in metadata:
            file_security.prove_replacement_metadata(state_home / ("probe-" + uuid.uuid4().hex), metadata[name])
    recovery = state_home / (RECOVERY_PREFIX + uuid.uuid4().hex)
    file_security.private_directory(recovery)
    order = [name for name in changed if name != FILES[0]] + ([FILES[0]] if FILES[0] in changed else [])
    staged, stage_metadata, touched, intended_states, committed_states, rename_states = {}, {}, [], {}, {}, {}
    manifest = {"protocol": PLAN_PROTOCOL, "project": str(root), "state": "preparing", "order": order,
                "before": {name: digest(data) if data is not None else None for name, data in before.items()},
                "after": {name: digest(after[name]) for name in FILES},
                "originals": {name: f"original-{i}.bin" if before[name] is not None else None
                              for i, name in enumerate(FILES)}, "staged": {},
                "original_metadata": {name: file_security.metadata_record(value) for name, value in metadata.items()},
                "original_states": original_states, "intended_states": intended_states,
                "committed_states": committed_states, "rename_states": rename_states}

    def journal(state, **details):
        manifest.update(state=state, **details)
        checkpoint("journal", state)
        temporary = recovery / "manifest.next"
        temporary.unlink(missing_ok=True)
        file_security.secure_file(temporary)
        durable_write(temporary, (json.dumps(manifest, indent=2) + "\n").encode())
        os.replace(temporary, recovery / "manifest.json")

    def restore(name):
        path = project_path(root, name, output=True)
        checkpoint("rollback", name)
        current = file_security.file_state(path)
        if current == original_states[name]:
            return
        # An ambiguous replace error can happen after the rename. Only the
        # fully precomputed intended state is eligible when no commit was read.
        owned = committed_states.get(name, intended_states.get(name))
        if name not in committed_states and current == rename_states.get(name):
            owned = rename_states[name]  # Rename happened; access installation did not.
        drift = file_security.state_drift(current, owned)
        if drift:
            raise OSError(f"External mutation prevents rollback: {name}; state drift: {', '.join(drift)}")
        if before[name] is None:
            drift = file_security.state_drift(file_security.file_state(path), owned)
            if drift:
                raise OSError(f"External mutation prevents rollback: {name}; state drift: {', '.join(drift)}")
            path.unlink()
        else:
            original = (recovery / manifest["originals"][name]).read_bytes()
            if original != before[name]:
                raise OSError(f"Original-byte recovery artifact is invalid: {name}")
            temporary = recovery / ("rollback-" + uuid.uuid4().hex)
            try:
                file_security.secure_file(temporary)
                durable_write(temporary, original)
                drift = file_security.state_drift(file_security.file_state(path), owned)
                if drift:
                    raise OSError(f"External mutation prevents rollback: {name}; state drift: {', '.join(drift)}")
                os.replace(temporary, path)
                file_security.apply_metadata(path, metadata[name])
                if os.name == "nt":
                    file_security.checked(file_security.set_attributes(str(path), original_states[name]["attributes"]))
                file_security.verify_metadata(path, metadata[name])
            finally:
                temporary.unlink(missing_ok=True)
        if file_security.file_state(path) != original_states[name]:
            raise OSError(f"Rollback verification failed: {name}")

    committed = False
    try:
        journal("preparing")
        # AGENTS original is backed up first, before any target can be replaced.
        for name in FILES:
            if before[name] is not None:
                checkpoint("backup", name)
                file_security.secure_file(recovery / manifest["originals"][name])
                durable_write(recovery / manifest["originals"][name], before[name])
        for name in order:
            path = project_path(root, name, output=True)
            checkpoint("mkdir", name)
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = recovery / ("stage-" + uuid.uuid4().hex)
            staged[name] = temporary
            manifest["staged"][name] = temporary.name
            # Persist the path before creating a stage so a crash can be investigated.
            journal("preparing")
            checkpoint("stage", name)
            file_security.secure_file(temporary)
            stage_metadata[name] = file_security.metadata(temporary)
            durable_write(temporary, after[name])
            rename_states[name] = file_security.file_state(temporary)
            intended_states[name] = dict(rename_states[name])
            if name in metadata:
                intended_states[name].update(file_security.access_state(metadata[name], protect=True if os.name == "nt" else None))
        journal("ready")
        validate_bindings(root, before, plan, mode)
        for name in order:
            checkpoint("stage-verify", name)
            if staged[name].read_bytes() != after[name]:
                raise OSError(f"Stage changed before apply: {name}")
            file_security.verify_metadata(staged[name], stage_metadata[name])
            if name in metadata:
                file_security.verify_metadata(root / name, metadata[name])
        for name in order:
            # In particular, all preservation destinations must still hold final
            # bytes before the knowledge-removal source is replaced.
            validate_bindings(root, before, plan, mode, touched, after)
            if name in metadata:
                file_security.verify_metadata(root / name, metadata[name])
            file_security.verify_metadata(staged[name], stage_metadata[name])
            if staged[name].read_bytes() != after[name]:
                raise OSError(f"Stage changed before replacement: {name}")
            checkpoint("replace", name)
            touched.append(name)  # Include ambiguous replace failures in recovery.
            os.replace(staged[name], project_path(root, name, output=True))
            if name in metadata:
                file_security.apply_metadata(root / name, metadata[name], protect=True if os.name == "nt" else None)
            observed = file_security.file_state(root / name)
            drift = file_security.state_drift(observed, intended_states[name])
            if drift:
                raise OSError(f"Applied state verification failed: {name}; state drift: {', '.join(drift)}")
            committed_states[name] = observed
            journal("applying")
            checkpoint("verify", name)
            if (root / name).read_bytes() != after[name]:
                raise OSError(f"Applied-byte verification failed: {name}")
        validate_bindings(root, before, plan, mode, touched, after)
        journal("committed")
        committed = True
    except BaseException as exc:
        errors = []
        source_restored = True
        if FILES[0] in touched:
            try:
                restore(FILES[0])
            except Exception as failure:
                source_restored = False
                errors.append(str(failure))
        else:
            try:
                source = project_path(root, FILES[0], output=True)
                if file_security.file_state(source) != original_states[FILES[0]]:
                    raise OSError("Concurrent source modification; keep preservation destinations")
            except Exception as failure:
                source_restored = False
                errors.append(str(failure))
        # Never undo preservation destinations while source restoration is uncertain.
        if source_restored:
            for name in reversed(touched):
                if name == FILES[0]:
                    continue
                try:
                    restore(name)
                except Exception as failure:
                    errors.append(str(failure))
        state = "rollback-incomplete" if errors else "rolled-back"
        try:
            journal(state, error=str(exc), rollback_errors=errors)
        except Exception as failure:
            errors.append(f"Recovery journal update failed: {failure}")
            state = "recovery-required"
        raise ApplyError(recovery, state, exc, errors) from exc
    finally:
        for temporary in staged.values():
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass  # Manifest names it; originals are retained on failure.
    if committed:
        # A cleanup failure leaves committed outputs and remaining evidence intact.
        try:
            checkpoint("cleanup", "committed")
            for path in recovery.iterdir():
                path.unlink()
            recovery.rmdir()
        except OSError as exc:
            raise ApplyError(recovery, "committed-cleanup-required", exc) from exc


def run(root, profile=None, plan=None, inspect_only=False, dry_run=False,
        mode=None, read_paths=(), fault=None):
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Selected project must be a directory")
    # Lock precedes recovery discovery, inspection, dependency validation and all writes.
    with file_security.project_lock(root):
        state_home = file_security.storage(root)
        return _run_locked(root, profile, plan, inspect_only, dry_run, mode, read_paths, fault, state_home)


def _run_locked(root, profile, plan, inspect_only, dry_run, mode, read_paths, fault, state_home):
    pending = sorted(str(path) for base in (root, state_home) for path in base.glob(RECOVERY_PREFIX + "*"))
    if pending and not inspect_only:
        raise ValueError(f"Unresolved recovery evidence; inspect/review before retrying: {pending}")
    try:
        before = read_project(root)
        info = inspect(before)
    except (ValueError, OSError) as exc:
        if inspect_only and pending:
            return {"pending_recovery": pending, "inspection_error": str(exc)}
        raise
    if inspect_only:
        paths = ([FILES[0]] if before[FILES[0]] is not None else []) + list(read_paths)
        info["read_set"] = read_set(root, list(dict.fromkeys(paths)))
        info["pending_recovery"] = pending
        return info
    if plan is not None and not isinstance(plan, dict):
        raise ValueError("Plan must be an object")
    planned_mode = (plan or {}).get("mode")
    if mode and planned_mode and mode != planned_mode:
        raise ValueError("Plan mode conflicts with requested mode")
    mode = mode or planned_mode or ("maintain" if info["install_state"] == "managed-v2" else None)
    if mode not in ("seed", "reconcile", "maintain"):
        raise ValueError("Explicit semantic --mode seed or evidence-backed Reconcile plan required")
    if mode == "seed" and info["install_state"] != "absent":
        raise ValueError("Seed requires absent Harness outputs; use Reconcile to preserve prior content")
    if mode == "maintain" and info["install_state"] != "managed-v2":
        raise ValueError("Maintain requires valid managed-v2 configuration")
    if mode == "reconcile" and info["install_state"] == "managed-v2":
        raise ValueError("Configured managed-v2 Harness uses Maintain")
    info["mode"] = mode
    if profile and (plan or {}).get("profile") and profile != plan["profile"]:
        raise ValueError("Plan profile conflicts with requested profile")
    profile = profile or (plan or {}).get("profile") or info["configured_profile"]
    if profile not in PROFILES:
        raise ValueError("Choose one evidence-backed primary profile: software, research, competition")
    validate_plan(root, before, info, plan, mode, profile)
    sources = validate_canonical_sources(root, before, info, plan)
    after, decisions = prepare(before, info, profile, plan, sources)
    changed = [name for name in FILES if before[name] != after[name]]
    validate_bindings(root, before, plan, mode)
    if dry_run:
        for name in changed:
            print("".join(difflib.unified_diff(decode(before[name] or b"").splitlines(True),
                                            decode(after[name]).splitlines(True),
                                            fromfile=name, tofile=name)), end="")
    else:
        apply_outputs(root, before, after, changed, plan, mode, state_home, fault)
    return {"mode": mode, "install_state": info["install_state"], "profile": profile, "dry_run": dry_run,
            "changed": changed, "reconciliation": decisions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--profile", choices=PROFILES)
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--mode", choices=("seed", "reconcile", "maintain"))
    parser.add_argument("--read", action="append", default=[], help="Explicit decision dependency to hash during inspect")
    parser.add_argument("--test-fault", help=argparse.SUPPRESS)
    parser.add_argument("--test-crash", help=argparse.SUPPRESS)
    parser.add_argument("--test-pause", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        plan = json.loads(args.plan.read_text(encoding="utf-8-sig")) if args.plan else None
        def fault(phase, name):
            point = f"{phase}:{name}"
            if point == args.test_pause:
                print("TEST_PAUSED", flush=True)
                input()  # Parent test controls the competing process window.
            if point == args.test_crash:
                os._exit(91)  # Isolated CLI crash regression only.
            if point == args.test_fault:
                raise OSError(f"Injected write failure: {point}")
        print(json.dumps(run(args.root, args.profile, plan, args.inspect, args.dry_run,
                             args.mode, args.read, fault), ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f"bootstrap: {exc}\n")


if __name__ == "__main__":
    main()
