#!/usr/bin/env python3
"""Audit the non-writing rootfs interactive execution-gate contract."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("kaliphonestudio/rootfs_handoff_trial_execution_gate.py")
DOC = Path("docs/ROOTFS_HANDOFF_TRIAL_EXECUTION_GATE.md")
TEST = Path("tests/test_rootfs_handoff_trial_execution_gate.py")
EXPECTED_POLICY = "rootfs-handoff-interactive-execution-gate-v1"
REQUIRED_TRUE = {
    "exact_trial_plan_bound",
    "exact_preflight_bound",
    "authorized_revalidation_bound",
    "distinct_execution_capture_bound",
    "live_device_identity_revalidated",
    "live_firmware_revalidated",
    "live_target_identity_revalidated",
    "live_filesystem_encryption_capacity_revalidated",
    "local_rootfs_exact_bytes_verified",
    "recovery_plan_identity_revalidated",
    "execution_gate_passed",
    "explicit_operator_confirmation_required",
    "write_scope_confirmation_required",
    "raw_device_path_resolution_required",
    "interactive_writer_required",
    "physical_gate_still_incomplete",
}
REQUIRED_FORBIDDEN = {
    "physical_interaction_performed",
    "external_device_command_executed",
    "raw_device_path_bound",
    "mount_target_bound",
    "trial_execution_allowed",
    "persistent_write_authorized",
    "persistent_write_performed",
    "phone_storage_written",
    "storage_verified",
    "recovery_verified",
    "hardware_verified",
    "beta_release_authorized",
    "beta_gate_credit",
}
DOC_MARKERS = (
    "rootfs-handoff-interactive-execution-gate-v1",
    "second distinct",
    "trial_execution_allowed=false",
    "persistent_write_authorized=false",
    "beta_gate_credit=false",
)


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _literal_assignments(tree: ast.Module) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        try:
            values[node.targets[0].id] = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            continue
    return values


def _execution_primitives(tree: ast.Module) -> list[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".", 1)[0] == "subprocess":
                    found.add(f"import:{alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.split(".", 1)[0] == "subprocess":
                found.add(f"import-from:{module}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            owner = node.func.value
            if isinstance(owner, ast.Name) and owner.id == "os" and node.func.attr in {"system", "popen"}:
                found.add(f"call:os.{node.func.attr}")
            if isinstance(owner, ast.Name) and owner.id == "subprocess":
                found.add(f"call:subprocess.{node.func.attr}")
    return sorted(found)


def _stable_reader_issues(tree: ast.Module) -> list[str]:
    imported: set[str] = set()
    read_exact: ast.FunctionDef | None = None
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module == "stable_file":
            imported.update(alias.name for alias in node.names)
        if isinstance(node, ast.FunctionDef) and node.name == "_read_exact":
            read_exact = node
    issues: list[str] = []
    for name in ("StableFileError", "read_stable_regular_file"):
        if name not in imported:
            issues.append(f"missing stable_file import: {name}")
    if read_exact is None:
        issues.append("missing _read_exact boundary")
        return issues
    stable_calls = 0
    direct_reads = 0
    for node in ast.walk(read_exact):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "read_stable_regular_file":
            stable_calls += 1
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"read_bytes", "read_text", "open"}:
            direct_reads += 1
    if stable_calls != 1:
        issues.append(f"_read_exact must call read_stable_regular_file exactly once, got {stable_calls}")
    if direct_reads:
        issues.append("_read_exact contains direct path read/open operations")
    return issues


def audit(root: Path = ROOT) -> dict[str, Any]:
    paths = [root / SOURCE, root / DOC, root / TEST]
    missing = [path.relative_to(root).as_posix() for path in paths if not path.is_file()]
    failures: list[str] = []
    if missing:
        failures.append("missing required files: " + ", ".join(missing))
        return {"schema": "rootfs-trial-execution-gate-audit-v1", "status": "FAIL", "failures": failures}

    tree = _tree(root / SOURCE)
    assignments = _literal_assignments(tree)
    policy = assignments.get("_POLICY")
    required_true = set(assignments.get("_REQUIRED_TRUE_FLAGS", ()))
    forbidden = set(assignments.get("_FORBIDDEN_FLAGS", ()))
    missing_true = sorted(REQUIRED_TRUE - required_true)
    missing_forbidden = sorted(REQUIRED_FORBIDDEN - forbidden)
    execution_primitives = _execution_primitives(tree)
    stable_reader_issues = _stable_reader_issues(tree)
    doc_text = (root / DOC).read_text(encoding="utf-8")
    missing_doc_markers = [marker for marker in DOC_MARKERS if marker not in doc_text]

    if policy != EXPECTED_POLICY:
        failures.append(f"policy drift: expected {EXPECTED_POLICY!r}, got {policy!r}")
    if missing_true:
        failures.append("missing required true flags: " + ", ".join(missing_true))
    if missing_forbidden:
        failures.append("missing required fail-closed flags: " + ", ".join(missing_forbidden))
    if execution_primitives:
        failures.append("execution primitives found: " + ", ".join(execution_primitives))
    if stable_reader_issues:
        failures.extend(stable_reader_issues)
    if missing_doc_markers:
        failures.append("documentation markers missing: " + ", ".join(missing_doc_markers))

    return {
        "schema": "rootfs-trial-execution-gate-audit-v1",
        "status": "PASS" if not failures else "FAIL",
        "policy": policy,
        "required_true_count": len(required_true),
        "forbidden_flag_count": len(forbidden),
        "missing_required_true": missing_true,
        "missing_required_forbidden": missing_forbidden,
        "execution_primitives": execution_primitives,
        "stable_reader_issues": stable_reader_issues,
        "missing_doc_markers": missing_doc_markers,
        "physical_interaction_performed": False,
        "persistent_write_authorized": False,
        "phone_storage_written": False,
        "hardware_verified": False,
        "beta_release_authorized": False,
        "beta_gate_credit": False,
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = audit(args.root.resolve())
    if args.json:
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    else:
        print(f"rootfs trial execution-gate audit: {report['status']}")
        for failure in report.get("failures", []):
            print(f"ERROR: {failure}", file=sys.stderr)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
