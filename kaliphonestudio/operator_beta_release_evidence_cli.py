"""Offline Beta release-preparation commands for the unified evidence workspace.

These commands only bind and re-verify already reviewed local evidence/artifacts.
They never contact a phone, invoke ADB/Fastboot, publish a GitHub release, select a
storage target, authorize persistent writes, promote hardware support, or grant
Beta credit.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from .beta_release_artifact_inventory import (
    build_beta_release_artifact_inventory,
    write_beta_release_artifact_inventory,
)
from .beta_release_review_manifest import (
    build_beta_release_review_manifest,
    write_beta_release_review_manifest_bundle,
)


BETA_RELEASE_EVIDENCE_COMMANDS = (
    "build-beta-artifact-inventory",
    "build-beta-review-manifest",
)


def _artifact(value: str) -> tuple[str, Path]:
    role, separator, raw_path = value.partition("=")
    if not separator or not role or not raw_path:
        raise argparse.ArgumentTypeError("artifact must use ROLE=PATH")
    return role, Path(raw_path)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="KaliPhoneStudio evidence",
        description=(
            "Offline Beta release-preparation workspace. It reuses exact reviewed physical evidence and local "
            "release files, performs no phone/network/publication action, and never grants Beta authorization."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable safety/result summary.")
    sub = parser.add_subparsers(dest="evidence_command", required=True)

    inventory = sub.add_parser(
        BETA_RELEASE_EVIDENCE_COMMANDS[0],
        help="Hash exact reviewed-candidate release files into a non-authorizing artifact inventory.",
        description=(
            "Offline-only: bind one exact physical candidate/release audit/rootfs strategy review to exact local "
            "release artifacts. Passing this stage only makes the set eligible for final manual release review."
        ),
    )
    inventory.add_argument("--candidate-gate", type=Path, required=True)
    inventory.add_argument("--release-gate-audit", type=Path, required=True)
    inventory.add_argument("--strategy-review", type=Path, required=True)
    inventory.add_argument("--source-commit", required=True)
    inventory.add_argument(
        "--artifact",
        action="append",
        type=_artifact,
        required=True,
        metavar="ROLE=PATH",
        help="Repeat once per release artifact role.",
    )
    inventory.add_argument("--out", type=Path, required=True)

    manifest = sub.add_parser(
        BETA_RELEASE_EVIDENCE_COMMANDS[1],
        help="Reverify the exact inventory and emit deterministic review manifest plus SHA256SUMS.",
        description=(
            "Offline-only: re-hash every inventoried release file from one directory and create a deterministic "
            "manifest/SHA256SUMS pair. A successful result still requires final manual release-gate review."
        ),
    )
    manifest.add_argument("--inventory", type=Path, required=True)
    manifest.add_argument("--release-dir", type=Path, required=True)
    manifest.add_argument("--version", required=True)
    manifest.add_argument("--manifest-out", type=Path, required=True)
    manifest.add_argument("--checksums-out", type=Path, required=True)

    return parser


def _safe_result(command: str, path: Path, digest: str, **extra: object) -> dict[str, object]:
    result: dict[str, object] = {
        "command": command,
        "path": str(path),
        "sha256": digest,
        "physical_interaction_performed": False,
        "external_device_command_executed": False,
        "network_action_performed": False,
        "release_publication_performed": False,
        "storage_target_selected": False,
        "persistent_write_authorized": False,
        "phone_storage_written": False,
        "hardware_verified": False,
        "release_publication_allowed": False,
        "beta_release_authorized": False,
        "beta_gate_credit": False,
    }
    result.update(extra)
    return result


def _emit(result: dict[str, object], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    print(f"evidence workflow: {result['command']}")
    print(f"output: {result['path']}")
    print(f"sha256: {result['sha256']}")
    print("physical interaction/device command: no")
    print("network/release publication: no")
    print("storage target/persistent write: no")
    print("hardware/Beta authorization: no")
    hidden = {
        "command",
        "path",
        "sha256",
        "physical_interaction_performed",
        "external_device_command_executed",
        "network_action_performed",
        "release_publication_performed",
        "storage_target_selected",
        "persistent_write_authorized",
        "phone_storage_written",
        "hardware_verified",
        "release_publication_allowed",
        "beta_release_authorized",
        "beta_gate_credit",
    }
    for key, value in result.items():
        if key not in hidden:
            print(f"{key}: {value}")


def _run(args: argparse.Namespace) -> dict[str, object]:
    command = args.evidence_command

    if command == BETA_RELEASE_EVIDENCE_COMMANDS[0]:
        artifacts: dict[str, Path] = {}
        for role, path in args.artifact:
            if role in artifacts:
                raise ValueError(f"duplicate --artifact role: {role}")
            artifacts[role] = path
        evidence = build_beta_release_artifact_inventory(
            args.candidate_gate,
            args.release_gate_audit,
            args.strategy_review,
            args.source_commit,
            artifacts,
        )
        digest = write_beta_release_artifact_inventory(evidence, args.out)
        return _safe_result(
            command,
            args.out,
            digest,
            profile_id=evidence.profile_id,
            device_serial=evidence.device_serial,
            source_commit=evidence.source_commit,
            artifact_count=len(evidence.artifacts),
            required_artifacts_present=evidence.required_artifacts_present,
            ready_for_final_manual_release_review=evidence.ready_for_final_manual_release_review,
            manual_release_gate_review_required=evidence.manual_release_gate_review_required,
        )

    if command == BETA_RELEASE_EVIDENCE_COMMANDS[1]:
        if args.manifest_out == args.checksums_out:
            raise ValueError("manifest and SHA256SUMS outputs must be different files")
        for destination in (args.manifest_out, args.checksums_out):
            if destination.exists() or destination.is_symlink():
                raise ValueError(f"refusing to overwrite existing output: {destination}")
        evidence, checksums = build_beta_release_review_manifest(
            args.inventory,
            args.release_dir,
            args.version,
        )
        digest = write_beta_release_review_manifest_bundle(
            evidence,
            checksums,
            args.manifest_out,
            args.checksums_out,
        )
        return _safe_result(
            command,
            args.manifest_out,
            digest,
            profile_id=evidence.profile_id,
            device_serial=evidence.device_serial,
            source_commit=evidence.source_commit,
            version=evidence.version,
            artifact_count=evidence.artifact_count,
            checksums_path=str(args.checksums_out),
            sha256sums_sha256=evidence.sha256sums_sha256,
            exact_artifacts_reverified=evidence.exact_artifacts_reverified,
            final_manual_release_gate_review_required=evidence.final_manual_release_gate_review_required,
        )

    raise ValueError(f"unsupported Beta release evidence command: {command}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        result = _run(args)
    except (ValueError, OSError) as exc:
        print(f"Evidence workflow error: {exc}", file=sys.stderr)
        return 2
    _emit(result, as_json=args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
