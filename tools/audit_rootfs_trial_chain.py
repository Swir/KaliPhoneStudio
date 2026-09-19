#!/usr/bin/env python3
"""Deterministically audit the offline rootfs trial-chain safety contract.

This checker intentionally parses source instead of importing execution modules. It
verifies that the three host-side gates between fresh target revalidation and any
future interactive executor still advertise the reviewed policies, carry all
required fail-closed flags, and remain free of process-execution primitives. It
performs no device I/O and grants no hardware or Beta credit.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

CONTRACTS: tuple[dict[str, Any], ...] = (
    {
        "name": "manual-trial-authorization",
        "source": "kaliphonestudio/rootfs_handoff_trial_authorization.py",
        "policy_attr": "_POLICY",
        "policy": "rootfs-handoff-manual-trial-authorization-v1",
        "forbidden_attr": "_FORBIDDEN_EVIDENCE_FLAGS",
        "required_forbidden": (
            "raw_device_path_bound",
            "mount_target_bound",
            "trial_execution_allowed",
            "persistent_write_authorized",
            "phone_storage_written",
            "storage_verified",
            "recovery_verified",
            "hardware_verified",
            "beta_release_authorized",
            "beta_gate_credit",
        ),
        "required_attr": "_REVIEW_FLAGS",
        "required_true": (
            "explicit_operator_interaction_reviewed",
            "no_automatic_execution_reviewed",
            "no_raw_path_in_evidence_reviewed",
            "no_persistent_write_authorization_reviewed",
        ),
        "doc": "docs/ROOTFS_HANDOFF_TRIAL_AUTHORIZATION.md",
        "doc_markers": (
            "offline, non-executing",
            "trial_execution_allowed=false",
            "persistent_write_authorized=false",
            "beta_gate_credit=false",
        ),
        "test": "tests/test_rootfs_handoff_trial_authorization.py",
    },
    {
        "name": "interactive-trial-plan",
        "source": "kaliphonestudio/rootfs_handoff_trial_plan.py",
        "policy_attr": "_POLICY",
        "policy": "rootfs-handoff-interactive-trial-plan-v1",
        "forbidden_attr": "_PLAN_FORBIDDEN",
        "required_forbidden": (
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
        ),
        "required_attr": "_PLAN_REQUIRED_TRUE",
        "required_true": (
            "live_device_identity_recheck_required",
            "live_firmware_recheck_required",
            "live_target_identity_recheck_required",
            "rootfs_local_hash_recheck_required",
            "recovery_readiness_recheck_required",
            "explicit_operator_confirmation_required",
            "write_scope_confirmation_required",
            "physical_gate_still_incomplete",
        ),
        "doc": "docs/ROOTFS_HANDOFF_TRIAL_PLAN.md",
        "doc_markers": (
            "rootfs-handoff-interactive-trial-plan-v1",
            "offline, non-executing",
            "plan_ready_for_later_interactive_executor=true",
            "Beta gate credit",
        ),
        "test": "tests/test_rootfs_handoff_trial_plan.py",
    },
    {
        "name": "local-rootfs-preflight",
        "source": "kaliphonestudio/rootfs_handoff_trial_preflight.py",
        "policy_attr": "_POLICY",
        "policy": "rootfs-handoff-local-rootfs-preflight-v1",
        "forbidden_attr": "_FORBIDDEN_PREFLIGHT_FLAGS",
        "required_forbidden": (
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
        ),
        "required_attr": "_REQUIRED_PREFLIGHT_FLAGS",
        "required_true": (
            "exact_trial_plan_bound",
            "local_rootfs_exact_bytes_verified",
            "live_device_identity_recheck_required",
            "live_firmware_recheck_required",
            "live_target_identity_recheck_required",
            "recovery_readiness_recheck_required",
            "explicit_operator_confirmation_required",
            "write_scope_confirmation_required",
            "interactive_executor_still_required",
            "physical_gate_still_incomplete",
        ),
        "doc": "docs/ROOTFS_HANDOFF_TRIAL_PREFLIGHT.md",
        "doc_markers": (
            "rootfs-handoff-local-rootfs-preflight-v1",
            "interactive_executor_still_required=true",
            "physical_gate_still_incomplete=true",
            "beta_gate_credit",
        ),
        "test": "tests/test_rootfs_handoff_trial_preflight.py",
    },
)


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _literal_assignments(path: Path) -> dict[str, Any]:
    tree = _parse(path)
    values: dict[str, Any] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        try:
            values[target.id] = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            continue
    return values


def _execution_primitives(path: Path) -> list[str]:
    """Return forbidden process-execution imports/calls in an offline boundary."""
    tree = _parse(path)
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
            if isinstance(owner, ast.Name):
                if owner.id == "os" and node.func.attr in {"system", "popen"}:
                    found.add(f"call:os.{node.func.attr}")
                if owner.id == "subprocess":
                    found.add(f"call:subprocess.{node.func.attr}")
    return sorted(found)


def audit(root: Path = ROOT) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    failures: list[str] = []

    for contract in CONTRACTS:
        source = root / contract["source"]
        doc = root / contract["doc"]
        test = root / contract["test"]
        item: dict[str, Any] = {
            "name": contract["name"],
            "source": contract["source"],
            "doc": contract["doc"],
            "test": contract["test"],
            "expected_policy": contract["policy"],
        }

        missing = [str(p.relative_to(root)) for p in (source, doc, test) if not p.is_file()]
        if missing:
            item["status"] = "FAIL"
            item["missing"] = missing
            failures.append(f"{contract['name']}: missing {', '.join(missing)}")
            results.append(item)
            continue

        assignments = _literal_assignments(source)
        actual_policy = assignments.get(contract["policy_attr"])
        forbidden = set(assignments.get(contract["forbidden_attr"], ()))
        required_true = set(assignments.get(contract["required_attr"], ()))
        missing_forbidden = sorted(set(contract["required_forbidden"]) - forbidden)
        missing_required = sorted(set(contract["required_true"]) - required_true)
        execution_primitives = _execution_primitives(source)
        doc_text = doc.read_text(encoding="utf-8")
        missing_doc_markers = [marker for marker in contract["doc_markers"] if marker not in doc_text]

        item.update(
            {
                "policy": actual_policy,
                "forbidden_flag_count": len(forbidden),
                "required_flag_count": len(required_true),
                "missing_forbidden_flags": missing_forbidden,
                "missing_required_flags": missing_required,
                "execution_primitives": execution_primitives,
                "missing_doc_markers": missing_doc_markers,
            }
        )

        if actual_policy != contract["policy"]:
            failures.append(
                f"{contract['name']}: policy drift: expected {contract['policy']!r}, got {actual_policy!r}"
            )
        if missing_forbidden:
            failures.append(f"{contract['name']}: missing fail-closed flags: {', '.join(missing_forbidden)}")
        if missing_required:
            failures.append(f"{contract['name']}: missing recheck/boundary flags: {', '.join(missing_required)}")
        if execution_primitives:
            failures.append(
                f"{contract['name']}: offline boundary contains execution primitives: {', '.join(execution_primitives)}"
            )
        if missing_doc_markers:
            failures.append(f"{contract['name']}: documentation safety markers drifted")

        item["status"] = "PASS" if not any(
            (
                actual_policy != contract["policy"],
                missing_forbidden,
                missing_required,
                execution_primitives,
                missing_doc_markers,
            )
        ) else "FAIL"
        results.append(item)

    report = {
        "schema": "rootfs-trial-chain-audit-v1",
        "status": "PASS" if not failures else "FAIL",
        "contracts": results,
        "failures": failures,
        "physical_interaction_performed": False,
        "external_device_command_executed": False,
        "persistent_write_authorized": False,
        "phone_storage_written": False,
        "hardware_verified": False,
        "beta_release_authorized": False,
        "beta_gate_credit": False,
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root to audit")
    parser.add_argument("--json", action="store_true", help="emit canonical machine-readable JSON")
    args = parser.parse_args(argv)

    report = audit(args.root.resolve())
    if args.json:
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    else:
        print(f"rootfs trial-chain audit: {report['status']}")
        for item in report["contracts"]:
            print(f"- {item['name']}: {item['status']} ({item.get('policy') or item['expected_policy']})")
        for failure in report["failures"]:
            print(f"ERROR: {failure}", file=sys.stderr)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
