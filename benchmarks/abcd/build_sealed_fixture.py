"""Build a sealed, model-only repository fixture for benchmark screening.

The builder intentionally uses ``git archive`` rather than copying a normal
clone.  The resulting workspace has no source repository object database,
remote, tag, or ref; it is initialized with one synthetic baseline commit.
Evaluator files and the benchmark dataset are never copied into the workspace.
Keep reports outside the workspace tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any, BinaryIO


FULL_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def _run_git(source: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", "core.quotePath=false", "-C", str(source), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _git_output(source: Path, *args: str) -> str:
    result = _run_git(source, *args)
    if result.returncode:
        detail = result.stderr.strip() or "git command failed"
        raise RuntimeError(f"git {' '.join(args)}: {detail}")
    return result.stdout.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_blob(source: Path, object_id: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(source), "cat-file", "blob", object_id],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip() or "git cat-file failed"
        raise RuntimeError(f"git cat-file blob {object_id}: {detail}")
    return result.stdout


def _safe_extract(archive: BinaryIO, destination: Path) -> None:
    """Extract a trusted git archive without allowing path traversal."""

    with tarfile.open(fileobj=archive, mode="r:") as tar:
        root = destination.resolve()
        for member in tar.getmembers():
            target = (destination / member.name).resolve()
            if os.path.commonpath((str(root), str(target))) != str(root):
                raise RuntimeError(f"archive member escapes workspace: {member.name!r}")
            if member.islnk():
                raise RuntimeError(f"archive hard links are not supported in sealed fixtures: {member.name!r}")
            if member.issym():
                # Never create a real link in the model workspace.  The link
                # target is restored from the source blob below and indexed
                # as mode 120000, preserving the exact Git tree safely.
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(member.linkname.encode("utf-8"))
                continue
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise RuntimeError(f"unsupported archive member: {member.name!r}")
            target.parent.mkdir(parents=True, exist_ok=True)
            extracted = tar.extractfile(member)
            if extracted is None:
                raise RuntimeError(f"could not read archive member: {member.name!r}")
            with target.open("wb") as output:
                shutil.copyfileobj(extracted, output)
            try:
                target.chmod(member.mode & 0o777)
            except OSError:
                pass


def build_fixture(
    *,
    source: Path,
    revision: str,
    issue_text: Path,
    dependency_reference: str,
    workspace: Path,
    report: Path | None,
) -> dict[str, Any]:
    source = source.resolve()
    issue_text = issue_text.resolve()
    workspace = workspace.resolve()
    if not source.is_dir():
        raise ValueError(f"repository source does not exist: {source}")
    if not issue_text.is_file():
        raise ValueError(f"issue text does not exist: {issue_text}")
    if not dependency_reference:
        raise ValueError("dependency reference must be non-empty")
    if not FULL_SHA_RE.fullmatch(revision):
        raise ValueError("revision must be a full 40-character commit id")
    if workspace.exists():
        raise ValueError(f"workspace already exists; refusing to overwrite: {workspace}")
    if workspace == source or source in workspace.parents:
        raise ValueError("workspace must not be inside the trusted source repository")

    if _git_output(source, "rev-parse", "--is-inside-work-tree") != "true":
        raise ValueError(f"not a git worktree: {source}")
    source_tree = _git_output(source, "rev-parse", f"{revision}^{{tree}}")
    _git_output(source, "cat-file", "-e", f"{revision}^{{commit}}")
    source_entries = _git_output(source, "ls-tree", "-r", "--full-tree", revision).splitlines()

    workspace.parent.mkdir(parents=True, exist_ok=True)
    workspace.mkdir()
    archive_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix="sealed-fixture-", suffix=".tar", delete=False) as temporary:
            archive_path = Path(temporary.name)
        with archive_path.open("wb") as archive:
            result = subprocess.run(
                [
                    "git",
                    "-c",
                    "core.autocrlf=false",
                    "-c",
                    "core.quotePath=false",
                    "-C",
                    str(source),
                    "archive",
                    "--format=tar",
                    revision,
                ],
                check=False,
                stdout=archive,
                stderr=subprocess.PIPE,
            )
        if result.returncode:
            detail = result.stderr.decode("utf-8", "replace").strip() or "git archive failed"
            raise RuntimeError(detail)
        with archive_path.open("rb") as archive:
            _safe_extract(archive, workspace)
        # git archive applies export-subst attributes and may normalize a
        # platform-sensitive byte stream.  Restore any differing blobs from
        # the exact source revision before constructing the synthetic tree.
        for entry in source_entries:
            mode, kind, object_id, path = entry.split(maxsplit=3)
            target = workspace / path
            if mode == "160000":
                continue
            blob = _git_blob(source, object_id)
            if not target.is_file() or _sha256(target) != hashlib.sha256(blob).hexdigest():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(blob)
    except Exception:
        shutil.rmtree(workspace, ignore_errors=True)
        raise
    finally:
        if archive_path is not None:
            archive_path.unlink(missing_ok=True)

    if (workspace / ".git").exists():
        shutil.rmtree(workspace / ".git", ignore_errors=True)
        raise RuntimeError("unexpected .git entry in archived source tree")

    init = subprocess.run(["git", "init", "--quiet", str(workspace)], check=False, capture_output=True, text=True)
    if init.returncode:
        shutil.rmtree(workspace, ignore_errors=True)
        raise RuntimeError(init.stderr.strip() or "git init failed")
    for key, value in (
        ("user.name", "Thaliris sealed fixture"),
        ("user.email", "sealed-fixture@invalid.local"),
        ("core.autocrlf", "false"),
        ("core.eol", "lf"),
        ("core.filemode", "true"),
    ):
        configured = subprocess.run(
            ["git", "-C", str(workspace), "config", key, value],
            check=False,
            capture_output=True,
            text=True,
        )
        if configured.returncode:
            shutil.rmtree(workspace, ignore_errors=True)
            raise RuntimeError(configured.stderr.strip() or f"git config {key} failed")
    # Hash the extracted bytes without platform filters.  The archive command
    # above is also forced to LF; local core.autocrlf/filemode settings must
    # not change the synthetic tree hash.
    added = subprocess.run(["git", "-C", str(workspace), "add", "--all", "--force"], check=False, capture_output=True, text=True)
    if added.returncode:
        shutil.rmtree(workspace, ignore_errors=True)
        raise RuntimeError(added.stderr.strip() or "git add failed")
    # A gitlink has no working-tree payload.  Symlinks are represented by a
    # regular file on Windows, then corrected to the source mode/object here.
    for entry in source_entries:
        mode, _kind, object_id, path = entry.split(maxsplit=3)
        if mode not in {"120000", "160000"}:
            continue
        indexed = subprocess.run(
            ["git", "-C", str(workspace), "update-index", "--add", "--cacheinfo", f"{mode},{object_id},{path}"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if indexed.returncode:
            shutil.rmtree(workspace, ignore_errors=True)
            raise RuntimeError(indexed.stderr.strip() or f"could not preserve special entry: {path}")
    for entry in source_entries:
        mode, _kind, _object_id, path = entry.split(maxsplit=3)
        if mode != "100755":
            continue
        executable = subprocess.run(
            ["git", "-C", str(workspace), "update-index", "--chmod=+x", "--", path],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if executable.returncode:
            shutil.rmtree(workspace, ignore_errors=True)
            raise RuntimeError(executable.stderr.strip() or f"could not preserve executable mode: {path}")
    synthetic_tree = _git_output(workspace, "write-tree")
    if synthetic_tree != source_tree:
        source_map = {
            entry.split(maxsplit=3)[3]: tuple(entry.split(maxsplit=3)[:3]) for entry in source_entries
        }
        index_map = {}
        for entry in _git_output(workspace, "ls-files", "--stage").splitlines():
            mode, object_id, _stage, path = entry.split(maxsplit=3)
            index_map[path] = (mode, "blob", object_id)
        mismatch = next(
            (
                (path, source_map.get(path), index_map.get(path))
                for path in sorted(set(source_map) | set(index_map))
                if source_map.get(path) != index_map.get(path)
            ),
            None,
        )
        shutil.rmtree(workspace, ignore_errors=True)
        raise RuntimeError(f"synthetic index tree does not match the requested source revision: expected {source_tree}, got {synthetic_tree}; first mismatch={mismatch}")
    committed = subprocess.run(
        ["git", "-C", str(workspace), "commit-tree", synthetic_tree, "-m", "sealed baseline"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if committed.returncode:
        shutil.rmtree(workspace, ignore_errors=True)
        raise RuntimeError(committed.stderr.strip() or "synthetic baseline commit failed")
    synthetic_commit = committed.stdout.strip()
    head_ref = _git_output(workspace, "symbolic-ref", "HEAD")
    updated = subprocess.run(
        ["git", "-C", str(workspace), "update-ref", head_ref, synthetic_commit],
        check=False,
        capture_output=True,
        text=True,
    )
    if updated.returncode:
        shutil.rmtree(workspace, ignore_errors=True)
        raise RuntimeError(updated.stderr.strip() or "could not point HEAD at synthetic baseline")
    # Windows cannot represent executable bits in the working tree reliably;
    # keep the exact 100755 modes in the synthetic tree but ignore mode-only
    # working-tree noise during the pre-model cleanliness gate.
    mode_configured = subprocess.run(
        ["git", "-C", str(workspace), "config", "core.filemode", "false"],
        check=False,
        capture_output=True,
        text=True,
    )
    if mode_configured.returncode:
        shutil.rmtree(workspace, ignore_errors=True)
        raise RuntimeError(mode_configured.stderr.strip() or "could not configure Windows filemode handling")

    result: dict[str, Any] = {
        "schema_version": 1,
        "fixture_kind": "sealed_model_workspace_v2",
        "repository_source": str(source),
        "exact_revision": revision,
        "source_tree": source_tree,
        "workspace": str(workspace),
        "synthetic_commit": synthetic_commit,
        "synthetic_tree": synthetic_tree,
        "issue_text": {
            "path": str(issue_text),
            "sha256": _sha256(issue_text),
            "copied_into_workspace": False,
        },
        "dependency_reference": dependency_reference,
        "preparation": {
            "source_materialization": "git archive exact revision",
            "original_git_removed": True,
            "synthetic_git_initialized": True,
            "synthetic_commit_count": 1,
            "evaluator_assets_copied": False,
            "benchmark_dataset_copied": False,
        },
        "runtime_controls": {
            "network_enforcement": "UNVERIFIED",
            "installation_enforcement": "UNVERIFIED",
            "protocol": "preinstalled dependencies; no network/install during model run",
        },
    }
    if report is not None:
        report = report.resolve()
        if report.is_relative_to(workspace):
            raise ValueError("report must be outside the model workspace")
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--issue-text", required=True, type=Path)
    parser.add_argument("--dependency-reference", required=True)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--report", type=Path, help="write operator report outside the workspace")
    args = parser.parse_args(argv)
    try:
        result = build_fixture(
            source=args.source,
            revision=args.revision,
            issue_text=args.issue_text,
            dependency_reference=args.dependency_reference,
            workspace=args.workspace,
            report=args.report,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
