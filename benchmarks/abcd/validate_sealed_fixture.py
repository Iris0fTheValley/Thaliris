"""Validate a sealed model workspace before benchmark model execution.

The command is deliberately fail-closed.  It emits exactly one top-level
status, ``SEALED_PASS`` or ``FIXTURE_NOT_SEALED``, and exits non-zero for the
latter.  Filesystem checks cover the workspace and a caller-selected
dedicated run root.  A normal Windows process still has no OS sandbox, so the
report explicitly records that global absolute-path access is unverified.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable


ZERO_SHA = "0" * 40
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DEFAULT_GOLD_COMMIT = "2349c84b5489bb792edbedc81acfaf9bf2488ce0"


class ScanLimitExceeded(RuntimeError):
    """Raised when a parent scan would walk an unbounded host tree."""


def _git(workspace: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(workspace), *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            ["git", "-C", str(workspace), *args],
            124,
            stdout="",
            stderr="git command timed out after 15s",
        )


def _git_value(workspace: Path, *args: str) -> tuple[bool, str]:
    result = _git(workspace, *args)
    return result.returncode == 0, result.stdout.strip()


def _check(name: str, status: str, value: Any, detail: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"status": status, "value": value}
    if detail:
        result["detail"] = detail
    return result


def _is_suspicious_name(name: str) -> bool:
    name = name.lower()
    if name in {
        "test.patch",
        "test_patch",
        "gold.patch",
        "gold.diff",
        "solution.patch",
        "solution.diff",
        "swe-live-lite.parquet",
    }:
        return True
    if name.endswith((".patch", ".diff", ".parquet")):
        return True
    if name.endswith(".jsonl") and any(token in name for token in ("run", "session", "screen", "result", "answer", "patch", "model", "sol", "luna")):
        return True
    return any(token in name for token in ("test_patch", "test-patch", "all_hints", "hints_text", "gold_patch", "prior_run"))


def _is_suspicious_file(path: Path, tracked_files: set[str] | None = None, workspace: Path | None = None) -> bool:
    if tracked_files and workspace is not None:
        try:
            relative = path.resolve().relative_to(workspace.resolve()).as_posix()
        except ValueError:
            relative = ""
        # Repositories may legitimately version fixture files ending in
        # .diff.  Exact-tree and clean-status checks still protect against
        # added or modified evaluator patches; only known baseline paths get
        # this narrow exemption.
        if relative in tracked_files and path.suffix.lower() == ".diff":
            return False
    return _is_suspicious_name(path.name)


def _is_suspicious_directory(path: Path) -> bool:
    name = path.name.lower()
    return name in {"evaluator", "evaluation", "screening", "artifacts", "model-workspace", "model_workspace"} or name.endswith(("-eval", "_eval"))


def _iter_files(root: Path, *, max_files: int) -> Iterable[Path]:
    if not root.exists():
        return
    if root.is_file():
        yield root
        return
    seen = 0
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        for directory in directories:
            candidate = Path(current) / directory
            if _is_suspicious_directory(candidate):
                yield candidate
        directories[:] = [
            directory
            for directory in directories
            if directory not in {".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "node_modules"}
        ]
        for filename in files:
            seen += 1
            if seen > max_files:
                raise ScanLimitExceeded(f"scan exceeded max_files={max_files}: {root}")
            yield Path(current) / filename


def _reachable_objects(workspace: Path) -> tuple[set[str], str | None]:
    ok, output = _git_value(workspace, "rev-list", "--objects", "--all")
    if not ok:
        return set(), "git rev-list --objects --all failed"
    objects = {line.split()[0] for line in output.splitlines() if line.split() and SHA_RE.match(line.split()[0])}
    ok, head = _git_value(workspace, "rev-parse", "HEAD")
    if ok and SHA_RE.match(head):
        objects.add(head)
    return objects, None


def _all_objects(workspace: Path) -> tuple[set[str], str | None]:
    try:
        result = subprocess.run(
            ["git", "-C", str(workspace), "cat-file", "--batch-all-objects", "--batch-check"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return set(), "git cat-file --batch-all-objects timed out after 15s"
    if result.returncode:
        return set(), "git cat-file --batch-all-objects failed"
    objects = {line.split()[0] for line in result.stdout.splitlines() if line.split() and SHA_RE.match(line.split()[0])}
    return objects, None


def _reflog_state(workspace: Path, head: str) -> tuple[str, list[str]]:
    logs = workspace / ".git" / "logs"
    if not logs.exists():
        return "PASS", []
    unexpected: list[str] = []
    for path in logs.rglob("*"):
        if not path.is_file():
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            fields = line.split()
            if len(fields) < 2:
                unexpected.append(f"{path}:{line_number}: malformed reflog entry")
                continue
            old, new = fields[0].lower(), fields[1].lower()
            if new != head.lower() or old not in {ZERO_SHA, head.lower()}:
                unexpected.append(f"{path}:{line_number}: {old} -> {new}")
    return ("PASS" if not unexpected else "FAIL"), unexpected


def _ancestor_scope(workspace: Path, scan_root: Path) -> tuple[bool, list[Path], str | None]:
    workspace = workspace.resolve()
    scan_root = scan_root.resolve()
    if scan_root != workspace and scan_root not in workspace.parents:
        return False, [], "scan root must be the workspace or an ancestor"
    roots: list[Path] = [workspace]
    if scan_root != workspace:
        roots.append(scan_root)
    return True, roots, None


def validate_fixture(
    *,
    workspace: Path,
    source: Path,
    revision: str,
    dependency_reference: str,
    baseline_status: str,
    known_gold_commit: str,
    scan_root: Path,
    forbidden_roots: list[Path],
    evaluator_path: Path | None,
    max_scan_files: int,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    source = source.resolve()
    scan_root = scan_root.resolve()
    checks: dict[str, Any] = {}

    if not workspace.is_dir():
        return {
            "status": "FIXTURE_NOT_SEALED",
            "workspace": str(workspace),
            "checks": {"workspace_exists": _check("workspace_exists", "FAIL", False)},
        }

    revision_ok = bool(re.fullmatch(r"[0-9a-fA-F]{40}", revision))
    checks["revision_format"] = _check("revision_format", "PASS" if revision_ok else "FAIL", revision)
    source_ok, source_tree = _git_value(source, "rev-parse", f"{revision}^{{tree}}") if revision_ok else (False, "")
    workspace_ok, workspace_tree = _git_value(workspace, "rev-parse", "HEAD^{tree}")
    checks["exact_source_tree"] = _check(
        "exact_source_tree",
        "PASS" if source_ok and workspace_ok and source_tree == workspace_tree else "FAIL",
        {"expected": source_tree if source_ok else None, "actual": workspace_tree if workspace_ok else None},
    )

    head_ok, head = _git_value(workspace, "rev-parse", "HEAD")
    commit_ok, commit_count = _git_value(workspace, "rev-list", "--all", "--count")
    parent_ok, parents = _git_value(workspace, "rev-list", "--all", "--parents")
    status_ok, porcelain = _git_value(workspace, "status", "--porcelain", "--untracked-files=all")
    checks["synthetic_commit"] = _check(
        "synthetic_commit",
        "PASS" if head_ok and commit_ok and commit_count == "1" and parent_ok and len(parents.split()) == 1 else "FAIL",
        {
            "head": head if head_ok else None,
            "commit_count": commit_count if commit_ok else None,
            "parent_line_count": len(parents.splitlines()) if parent_ok else None,
            "parents_sample": parents.splitlines()[:5] if parent_ok else None,
        },
    )
    checks["working_tree_clean"] = _check("working_tree_clean", "PASS" if status_ok and not porcelain else "FAIL", porcelain)

    remote_ok, remotes = _git_value(workspace, "remote")
    remote_v_ok, remote_v = _git_value(workspace, "remote", "-v")
    remote_ref_ok, remote_refs = _git_value(workspace, "for-each-ref", "refs/remotes", "--format=%(refname)")
    tag_ok, tags = _git_value(workspace, "tag", "--list")
    branches_ok, branches = _git_value(workspace, "branch", "--all", "--format=%(refname)")
    checks["remote_count"] = _check("remote_count", "PASS" if remote_ok and not remotes else "FAIL", len(remotes.splitlines()) if remote_ok else None)
    checks["remote_verbose"] = _check("remote_verbose", "PASS" if remote_v_ok and not remote_v else "FAIL", remote_v)
    checks["remote_ref_count"] = _check("remote_ref_count", "PASS" if remote_ref_ok and not remote_refs else "FAIL", len(remote_refs.splitlines()) if remote_ref_ok else None)
    checks["tag_count"] = _check("tag_count", "PASS" if tag_ok and not tags else "FAIL", len(tags.splitlines()) if tag_ok else None)
    branch_lines = branches.splitlines() if branches_ok else []
    checks["branch_refs"] = _check(
        "branch_refs",
        "PASS" if branches_ok and all(not line.startswith("refs/remotes/") for line in branch_lines) else "FAIL",
        {"count": len(branch_lines), "remote_sample": [line for line in branch_lines if line.startswith("refs/remotes/")][:20]},
    )

    reflog_status, reflog_entries = _reflog_state(workspace, head if head_ok else "")
    checks["reflog_state"] = _check("reflog_state", reflog_status, reflog_entries)

    git_isolation_ok = (
        head_ok
        and commit_ok
        and commit_count == "1"
        and parent_ok
        and len(parents.split()) == 1
        and remote_ok
        and not remotes
        and remote_v_ok
        and not remote_v
        and remote_ref_ok
        and not remote_refs
        and tag_ok
        and not tags
        and branches_ok
        and all(not line.startswith("refs/remotes/") for line in branch_lines)
        and reflog_status == "PASS"
    )
    if git_isolation_ok:
        reachable, reachable_error = _reachable_objects(workspace)
        all_objects, all_objects_error = _all_objects(workspace)
        unexpected = sorted(all_objects - reachable) if not reachable_error and not all_objects_error else []
        checks["unexpected_git_objects"] = _check(
            "unexpected_git_objects",
            "PASS" if not reachable_error and not all_objects_error and not unexpected else "FAIL",
            unexpected[:20],
            reachable_error or all_objects_error,
        )
    else:
        checks["unexpected_git_objects"] = _check(
            "unexpected_git_objects",
            "FAIL",
            "SKIPPED_AFTER_GIT_ISOLATION_FAILURE",
            "basic Git isolation already failed; object scan is intentionally fail-closed",
        )
    gold_result = _git(workspace, "cat-file", "-e", known_gold_commit)
    checks["known_gold_commit_unavailable"] = _check(
        "known_gold_commit_unavailable",
        "PASS" if gold_result.returncode != 0 else "FAIL",
        known_gold_commit,
        "git cat-file -e returned success" if gold_result.returncode == 0 else None,
    )

    scope_ok, roots, scope_error = _ancestor_scope(workspace, scan_root)
    findings: list[str] = []
    scan_error: str | None = None
    tracked_files = set(_git_value(workspace, "ls-files")[1].splitlines())
    if scope_ok:
        seen: set[str] = set()
        try:
            for root in roots:
                for path in _iter_files(root, max_files=max_scan_files):
                    resolved = str(path.resolve())
                    if resolved in seen:
                        continue
                    seen.add(resolved)
                    if _is_suspicious_file(path, tracked_files=tracked_files, workspace=workspace):
                        findings.append(resolved)
        except ScanLimitExceeded as error:
            scan_error = str(error)
    checks["filesystem_parent_traversal"] = _check(
        "filesystem_parent_traversal",
        "PASS" if scope_ok and not findings and scan_error is None else "FAIL",
        {"scan_root": str(scan_root), "suspicious_files": findings[:50], "scan_error": scan_error},
        scope_error or scan_error,
    )

    separate: list[dict[str, Any]] = []
    for forbidden in forbidden_roots:
        resolved = forbidden.resolve()
        inside_scope = resolved == scan_root or scan_root in resolved.parents or resolved == workspace or workspace in resolved.parents
        separate.append({"path": str(resolved), "status": "FAIL" if inside_scope else "PASS", "exists": resolved.exists()})
    checks["evaluator_assets_separate"] = _check(
        "evaluator_assets_separate",
        "PASS" if all(item["status"] == "PASS" for item in separate) else "FAIL",
        separate,
        "separate paths are not OS-inaccessible; global absolute-path access remains unverified",
    )
    if evaluator_path is not None:
        evaluator_path = evaluator_path.resolve()
        checks["evaluator_absent_pre_model"] = _check(
            "evaluator_absent_pre_model",
            "PASS" if not evaluator_path.exists() else "FAIL",
            str(evaluator_path),
        )
    else:
        checks["evaluator_absent_pre_model"] = _check("evaluator_absent_pre_model", "FAIL", None, "evaluator path is required for the pre-model gate")

    dependency_path = Path(dependency_reference)
    dependency_ready = dependency_path.exists() if dependency_path.drive or dependency_path.is_absolute() else False
    checks["environment_ready"] = _check(
        "environment_ready",
        "PASS" if dependency_ready and baseline_status == "PASS" else "FAIL",
        {"dependency_reference": dependency_reference, "dependency_exists": dependency_ready, "baseline_status": baseline_status},
        None if dependency_ready and baseline_status == "PASS" else "dependency path and externally verified baseline PASS are required",
    )
    checks["network_enforcement"] = _check("network_enforcement", "UNVERIFIED", "protocol_only")
    checks["installation_enforcement"] = _check("installation_enforcement", "UNVERIFIED", "protocol_only")
    checks["global_os_sandbox"] = _check("global_os_sandbox", "UNVERIFIED", "ordinary process; no OS sandbox asserted")

    required = [item for item in checks.values() if item["status"] in {"PASS", "FAIL"}]
    overall = "SEALED_PASS" if required and all(item["status"] == "PASS" for item in required) else "FIXTURE_NOT_SEALED"
    return {
        "status": overall,
        "schema_version": 1,
        "fixture_kind": "sealed_model_workspace_v2",
        "workspace": str(workspace),
        "source": str(source),
        "revision": revision,
        "known_gold_commit": known_gold_commit,
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--dependency-reference", required=True)
    parser.add_argument("--baseline-status", required=True, choices=("PASS", "FAIL", "UNVERIFIED"))
    parser.add_argument("--known-gold-commit", default=DEFAULT_GOLD_COMMIT)
    parser.add_argument("--scan-root", required=True, type=Path)
    parser.add_argument("--forbidden-root", action="append", default=[], type=Path)
    parser.add_argument("--evaluator-path", required=True, type=Path)
    parser.add_argument("--max-scan-files", type=int, default=10000)
    parser.add_argument("--output", type=Path, help="write the gate report outside the model workspace")
    args = parser.parse_args(argv)
    result = validate_fixture(
        workspace=args.workspace,
        source=args.source,
        revision=args.revision,
        dependency_reference=args.dependency_reference,
        baseline_status=args.baseline_status,
        known_gold_commit=args.known_gold_commit,
        scan_root=args.scan_root,
        forbidden_roots=args.forbidden_root,
        evaluator_path=args.evaluator_path,
        max_scan_files=args.max_scan_files,
    )
    payload = json.dumps(result, indent=2) + "\n"
    if args.output:
        output = args.output.resolve()
        if output.is_relative_to(args.workspace.resolve()):
            print("error: gate report must be outside model workspace", file=sys.stderr)
            return 2
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result["status"] == "SEALED_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
