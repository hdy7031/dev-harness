"""Deterministic five-file writer; semantic/profile decisions belong to Codex."""

import argparse
import copy
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import tomllib

SKILL = Path(__file__).resolve().parents[1]
FILES = ("AGENTS.md", "HANDOFF.md", "docs/PROJECT_CONTEXT.md",
         "docs/DECISIONS.md", ".harness/config.toml")
PROFILES = ("software", "research", "competition")
ROUTES = {"context": FILES[2], "handoff": FILES[1], "decision": FILES[3]}


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
        path = root / name
        # Resolve every output before reading/writing; never follow links outside the project.
        if not path.resolve().is_relative_to(root) or path.is_symlink():
            raise ValueError(f"Unsafe output path: {name}")
        if path.exists() and not path.is_file():
            raise ValueError(f"Expected file: {name}")
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
    if spans and version:
        mode = "maintain"
    elif any((before[name] or b"").strip() for name in FILES):
        mode = "reconcile"
    else:
        mode = "seed"
    return {"mode": mode, "configured_profile": harness.get("profile"),
            "version": version, "agents_sha256": digest(before[FILES[0]] or b""),
            "legacy_lines": [] if spans else [
                {"line": i, "text": line} for i, line in enumerate(agents.splitlines(), 1)],
            "files_sha256": {name: digest(data) if data is not None else None
                             for name, data in before.items()}}


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


def reconcile(text, plan, sha):
    if plan.get("agents_sha256") != sha:
        raise ValueError("Missing/stale AGENTS hash; inspect again before reconciling")
    lines = text.splitlines()
    accounted = set()
    invariants, routes, decisions = [], {name: [] for name in ROUTES}, []
    for rule in plan.get("rules", []):
        start, end = rule["start"], rule["end"]
        action, reason = rule["action"], rule.get("reason", "").strip()
        if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(lines):
            raise ValueError("Rule range is outside the old AGENTS")
        covered = set(range(start, end + 1))
        if covered & accounted or not reason:
            raise ValueError("Every range must be disjoint and have a semantic reason")
        accounted.update(covered)
        body = rule.get("text", "\n".join(lines[start - 1:end])).strip()
        if action == "invariant":
            invariants.append(body)
        elif action in ROUTES:
            routes[action].append(body)
        elif action not in ("merge", "drop"):
            raise ValueError(f"Unknown reconciliation action: {action}")
        if action not in ("merge", "drop") and not body:
            raise ValueError("Preserved/moved rules cannot have empty text")
        decisions.append({"lines": [start, end], "action": action, "reason": reason})
    required = {i for i, line in enumerate(lines, 1) if line.strip()}
    if required - accounted:
        raise ValueError(f"Unaccounted old guidance lines: {sorted(required - accounted)}")
    return invariants, routes, decisions


def prepare(before, info, profile, plan):
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
            invariants, routes, decisions = reconcile(old_agents, plan, info["agents_sha256"])
        else:
            invariants = []
        for item in (plan or {}).get("invariants", []):
            if not item.get("text", "").strip() or not item.get("evidence", "").strip():
                raise ValueError("New invariants require text and concrete project evidence")
            invariants.append(item["text"].strip())
        unique = list(dict.fromkeys(invariants))
        agents = (SKILL / "assets/harness/AGENTS.md").read_text(encoding="utf-8")
        agents = agents.replace("{{core}}", core).replace("{{profile}}", stance).replace("{{invariants}}", "\n\n" + "\n\n".join(unique) if unique else "")
    boundaries(agents)
    after[FILES[0]] = (encode_exact if info["mode"] == "maintain" else encode)(agents, before[FILES[0]] or b"")
    for name in FILES[1:4]:
        if after[name] is None:
            after[name] = (SKILL / "assets/harness" / name).read_bytes()
    for action, chunks in routes.items():
        name = ROUTES[action]
        destination = decode(after[name])
        missing = [chunk for chunk in dict.fromkeys(chunks) if chunk not in destination]
        if missing:
            destination = destination.rstrip() + "\n\n## Imported from prior AGENTS\n\nHistorical source; verify current status before relying on it.\n\n" + "\n\n".join(missing) + "\n"
            after[name] = encode(destination, after[name])
    after[FILES[4]] = update_config(before[FILES[4]], profile)
    return after, decisions


def run(root, profile=None, plan=None, inspect_only=False, dry_run=False):
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Selected project must be a directory")
    before = read_project(root)
    info = inspect(before)
    if inspect_only:
        return info
    profile = profile or info["configured_profile"]
    if profile not in PROFILES:
        raise ValueError("Choose one evidence-backed primary profile: software, research, competition")
    after, decisions = prepare(before, info, profile, plan)
    changed = [name for name in FILES if before[name] != after[name]]
    if dry_run:
        for name in changed:
            print("".join(difflib.unified_diff(decode(before[name] or b"").splitlines(True),
                                            decode(after[name]).splitlines(True),
                                            fromfile=name, tofile=name)), end="")
    else:
        if read_project(root) != before:
            raise ValueError("Project changed while planning; inspect again")
        for name in changed:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(after[name])
            try:
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
    return {"mode": info["mode"], "profile": profile, "dry_run": dry_run,
            "changed": changed, "reconciliation": decisions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--profile", choices=PROFILES)
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--plan", type=Path)
    args = parser.parse_args()
    try:
        plan = json.loads(args.plan.read_text(encoding="utf-8-sig")) if args.plan else None
        print(json.dumps(run(args.root, args.profile, plan, args.inspect, args.dry_run), ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f"bootstrap: {exc}\n")


if __name__ == "__main__":
    main()
