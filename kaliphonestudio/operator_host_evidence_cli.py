"""Host-only provenance commands for the unified operator evidence workspace.

These commands consume already reviewed local evidence files. They perform no
ADB/Fastboot/subprocess/device I/O, select no storage path, authorize no write
and cannot promote hardware support or Beta readiness.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from .phosh_candidate_binding import (
    PhoshCandidateBindingError,
    build_phosh_candidate_binding_from_paths,
    write_phosh_candidate_binding,
)


HOST_EVIDENCE_COMMANDS = ("bind-phosh-candidate",)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="KaliPhoneStudio evidence",
        description=(
            "Offline host provenance evidence. These commands do not connect to a phone, "
            "do not run adb/fastboot, do not select storage targets and grant no hardware/Beta credit."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable safety/result summary.")
    sub = parser.add_subparsers(dest="evidence_command", required=True)

    phosh = sub.add_parser(
        "bind-phosh-candidate",
        help="Cross-bind reviewed Phosh/rootfs provenance to one exact reviewed first-boot candidate.",
        description=(
            "Offline-only: require one exact canonical first-boot authority bundle and one exact canonical "
            "Phosh/rootfs authority binding to share the same reviewed rootfs authority and artifact. "
            "Success authorizes only later physical Phosh validation; it grants no display/touch/hardware/Beta credit."
        ),
    )
    phosh.add_argument("--candidate-authority-bundle", type=Path, required=True)
    phosh.add_argument("--phosh-rootfs-binding", type=Path, required=True)
    phosh.add_argument("--out", type=Path, required=True, help="New output path; existing files are never overwritten.")
    return parser


def _safe_result(command: str, output: Path, digest: str, *, profile_id: str) -> dict[str, object]:
    return {
        "command": command,
        "path": str(output),
        "sha256": digest,
        "profile_id": profile_id,
        "physical_interaction_performed": False,
        "external_device_command_executed": False,
        "storage_target_selected": False,
        "persistent_write_authorized": False,
        "phone_storage_written": False,
        "display_verified": False,
        "touch_verified": False,
        "hardware_verified": False,
        "beta_release_authorized": False,
        "beta_gate_credit": False,
        "ready_for_physical_phosh_validation": True,
    }


def _emit(result: dict[str, object], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    print(f"evidence workflow: {result['command']}")
    print(f"output: {result['path']}")
    print(f"sha256: {result['sha256']}")
    print(f"profile_id: {result['profile_id']}")
    print("physical interaction/device command: no")
    print("storage target/persistent write: no")
    print("display/touch/hardware/Beta credit: no")
    print("ready for later physical Phosh validation: yes")


def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.evidence_command != "bind-phosh-candidate":
        raise PhoshCandidateBindingError(f"unsupported host evidence command: {args.evidence_command}")
    evidence = build_phosh_candidate_binding_from_paths(
        args.candidate_authority_bundle,
        args.phosh_rootfs_binding,
    )
    digest = write_phosh_candidate_binding(evidence, args.out)
    return _safe_result(
        args.evidence_command,
        args.out,
        digest,
        profile_id=evidence.profile_id,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        result = _run(args)
    except (PhoshCandidateBindingError, OSError) as exc:
        print(f"Evidence workflow error: {exc}", file=sys.stderr)
        return 2
    _emit(result, as_json=args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
