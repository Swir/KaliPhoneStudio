"""Late-stage offline evidence commands for the shared operator workspace.

These commands consume already captured/reviewed files only. They never invoke
ADB/Fastboot, never communicate with a phone, never select a storage target and
never authorize a persistent write or Beta release. The module exists separately
from the earlier evidence stages to keep the host CLI maintainable while the
root ``KaliPhoneStudio evidence`` namespace remains one operator workflow.
"""
from __future__ import annotations

import argparse
from dataclasses import fields
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any, Sequence, TypeVar

from .physical_boot_observation import PhysicalBootObservationEvidence
from .physical_bringup_dossier import (
    build_physical_bringup_dossier,
    load_physical_bringup_dossier_evidence,
    write_physical_bringup_dossier_evidence,
)
from .physical_bringup_dossier_review import (
    PhysicalBringupDossierReviewRecord,
    bind_physical_bringup_dossier_review,
    load_physical_bringup_dossier_review_record,
    load_physical_bringup_dossier_verification_for_review,
    parse_physical_bringup_dossier_review_record,
    read_physical_bringup_dossier_review_notes,
    write_physical_bringup_dossier_review_evidence,
)
from .physical_bringup_dossier_verify import (
    verify_physical_bringup_dossier_files,
    write_physical_bringup_dossier_verification_evidence,
)
from .physical_bringup_session import (
    bind_physical_bringup_session,
    load_physical_bringup_session_evidence,
    write_physical_bringup_session_evidence,
)
from .physical_candidate_gate import PhysicalCandidateGateEvidence
from .physical_kali_early_userspace import (
    PhysicalKaliEarlyUserspaceEvidence,
    validate_physical_kali_early_userspace_evidence,
)
from .physical_release_gate_audit import (
    build_physical_release_gate_audit_from_files,
    write_physical_release_gate_audit_evidence,
)
from .physical_rescue_diagnostics import (
    load_physical_boot_observation_for_diagnostics,
    load_physical_rescue_diagnostics_evidence,
)
from .physical_rescue_functional_probes import load_physical_rescue_functional_probe_evidence
from .physical_storage_discovery import load_physical_storage_discovery_evidence
from .physical_storage_review import load_physical_storage_review_evidence


T = TypeVar("T")
_MAX_SIMPLE_EVIDENCE_BYTES = 4 * 1024 * 1024

LATE_EVIDENCE_COMMANDS = (
    "bind-bringup-session",
    "build-bringup-dossier",
    "verify-bringup-dossier",
    "prepare-bringup-dossier-review",
    "bind-bringup-dossier-review",
    "build-release-gate-audit",
)


def _add_output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="New output path; existing files are never overwritten.",
    )


def _role_file(value: str) -> tuple[str, Path]:
    role, sep, raw_path = value.partition("=")
    if not sep or not role or not raw_path:
        raise argparse.ArgumentTypeError("expected ROLE=PATH")
    if any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789_" for ch in role):
        raise argparse.ArgumentTypeError("ROLE must use lowercase letters, digits or underscore")
    return role, Path(raw_path)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="KaliPhoneStudio evidence",
        description=(
            "Offline exact-file bring-up/dossier/release-audit workspace. These commands perform no phone I/O, "
            "run no adb/fastboot command, select no storage target and grant no hardware/Beta credit."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable safety/result summary.")
    sub = parser.add_subparsers(dest="evidence_command", required=True)

    session = sub.add_parser(
        "bind-bringup-session",
        help="Cross-bind exact candidate/rescue/storage evidence into one non-release physical session.",
        description=(
            "Offline-only: bind already captured exact candidate, boot, rescue and accepted storage-review evidence. "
            "No target is selected and no persistent write is authorized."
        ),
    )
    session.add_argument("--candidate-gate", type=Path, required=True)
    session.add_argument("--boot-observation", type=Path, required=True)
    session.add_argument("--rescue-diagnostics", type=Path, required=True)
    session.add_argument("--functional-probes", type=Path, required=True)
    session.add_argument("--storage-discovery", type=Path, required=True)
    session.add_argument("--storage-review", type=Path, required=True)
    session.add_argument("--kali-early-userspace", type=Path, default=None)
    _add_output(session)

    dossier = sub.add_parser(
        "build-bringup-dossier",
        help="Freeze one exact physical session plus every bound source byte into a dossier.",
        description=(
            "Offline-only exact-file audit. The command verifies the supplied evidence/raw files against the session "
            "and cannot select a target, write phone storage or grant release credit."
        ),
    )
    dossier.add_argument("--session", type=Path, required=True)
    dossier.add_argument("--candidate-gate", type=Path, required=True)
    dossier.add_argument("--boot-observation", type=Path, required=True)
    dossier.add_argument("--rescue-diagnostics", type=Path, required=True)
    dossier.add_argument("--functional-probes", type=Path, required=True)
    dossier.add_argument("--storage-discovery", type=Path, required=True)
    dossier.add_argument("--storage-review", type=Path, required=True)
    dossier.add_argument("--rescue-transcript", type=Path, required=True)
    dossier.add_argument("--storage-discovery-report", type=Path, required=True)
    dossier.add_argument("--recovery-plan", type=Path, required=True)
    dossier.add_argument("--storage-review-record", type=Path, required=True)
    dossier.add_argument("--storage-review-notes", type=Path, required=True)
    dossier.add_argument("--kali-early-userspace-evidence", type=Path, default=None)
    dossier.add_argument("--kali-early-userspace-transcript", type=Path, default=None)
    dossier.add_argument("--rootfs-artifact", type=Path, default=None)
    _add_output(dossier)

    verify = sub.add_parser(
        "verify-bringup-dossier",
        help="Reverify every exact file named by a dossier after transfer/archive.",
        description=(
            "Offline-only: repeat --file ROLE=PATH exactly once for every role recorded in the dossier. "
            "Reverification grants no hardware/Beta credit."
        ),
    )
    verify.add_argument("--dossier", type=Path, required=True)
    verify.add_argument(
        "--file",
        action="append",
        type=_role_file,
        required=True,
        metavar="ROLE=PATH",
        help="Repeat exactly once for every role recorded in the dossier.",
    )
    _add_output(verify)

    review_template = sub.add_parser(
        "prepare-bringup-dossier-review",
        help="Create rejected-by-default dossier review record and notes templates.",
        description=(
            "Offline-only: both outputs are created together and start fail-closed. Acceptance is only eligible for "
            "later strategy review; it never selects a target or authorizes writes."
        ),
    )
    review_template.add_argument("--dossier", type=Path, required=True)
    review_template.add_argument("--reviewer", required=True)
    review_template.add_argument("--record-out", type=Path, required=True)
    review_template.add_argument("--notes-out", type=Path, required=True)

    review_bind = sub.add_parser(
        "bind-bringup-dossier-review",
        help="Bind exact dossier, independent reverification, manual record and notes into review evidence.",
        description=(
            "Offline-only manual review binding. Even an accepted dossier remains input for a later separate "
            "strategy/release review and grants no hardware/Beta credit."
        ),
    )
    review_bind.add_argument("--dossier", type=Path, required=True)
    review_bind.add_argument("--verification", type=Path, required=True)
    review_bind.add_argument("--review-record", type=Path, required=True)
    review_bind.add_argument("--review-notes", type=Path, required=True)
    _add_output(review_bind)

    audit = sub.add_parser(
        "build-release-gate-audit",
        help="Cross-bind accepted bring-up dossier/review with the exact functional-result campaign.",
        description=(
            "Offline-only cross-campaign audit for later manual release-gate review. Even complete reviewed-pass "
            "coverage never authorizes Beta and never writes to the phone."
        ),
    )
    audit.add_argument("--dossier", type=Path, required=True)
    audit.add_argument("--dossier-verification", type=Path, required=True)
    audit.add_argument("--dossier-review", type=Path, required=True)
    audit.add_argument("--functional-result-bundle", type=Path, required=True)
    audit.add_argument("--test-plan", type=Path, required=True)
    audit.add_argument("--test-plan-review", type=Path, required=True)
    _add_output(audit)

    return parser


def _safe_result(command: str, destination: Path, digest: str, **extra: object) -> dict[str, object]:
    result: dict[str, object] = {
        "command": command,
        "path": str(destination),
        "sha256": digest,
        "physical_interaction_performed": False,
        "external_device_command_executed": False,
        "storage_target_selected": False,
        "persistent_write_authorized": False,
        "phone_storage_written": False,
        "hardware_verified": False,
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
    print("storage target/persistent write: no")
    print("hardware/Beta authorization: no")
    for key, value in result.items():
        if key in {
            "command",
            "path",
            "sha256",
            "physical_interaction_performed",
            "external_device_command_executed",
            "storage_target_selected",
            "persistent_write_authorized",
            "phone_storage_written",
            "hardware_verified",
            "beta_release_authorized",
            "beta_gate_credit",
        }:
            continue
        print(f"{key}: {value}")


def _load_simple_dataclass(path: Path, cls: type[T], label: str) -> T:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"{label} must be a regular non-symlink file")
    before = source.stat()
    raw = source.read_bytes()
    after = source.stat()
    if before.st_size <= 0 or before.st_size > _MAX_SIMPLE_EVIDENCE_BYTES or len(raw) != before.st_size:
        raise ValueError(f"{label} size is outside the safety limit")
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ValueError(f"{label} changed while being read")
    try:
        value: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc
    expected = {item.name for item in fields(cls)}
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label} fields do not match expected schema")
    try:
        return cls(**value)
    except TypeError as exc:
        raise ValueError(f"{label} types are invalid") from exc


def _write_pair_exclusive(record_path: Path, record_text: str, notes_path: Path, notes_text: str) -> tuple[str, str]:
    record_path = Path(record_path)
    notes_path = Path(notes_path)
    if record_path == notes_path:
        raise ValueError("review record and notes outputs must be different files")
    for destination in (record_path, notes_path):
        if destination.exists() or destination.is_symlink():
            raise ValueError(f"refusing to overwrite existing output: {destination}")
    created: list[Path] = []
    try:
        for destination, text in ((record_path, record_text), (notes_path, notes_text)):
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
            created.append(destination)
    except OSError:
        for destination in created:
            try:
                destination.unlink()
            except OSError:
                pass
        raise
    return (
        sha256(record_path.read_bytes()).hexdigest(),
        sha256(notes_path.read_bytes()).hexdigest(),
    )


def _run(args: argparse.Namespace) -> dict[str, object]:
    command = args.evidence_command

    if command == "bind-bringup-session":
        gate = _load_simple_dataclass(args.candidate_gate, PhysicalCandidateGateEvidence, "physical candidate gate")
        observation: PhysicalBootObservationEvidence = load_physical_boot_observation_for_diagnostics(args.boot_observation)
        diagnostics = load_physical_rescue_diagnostics_evidence(args.rescue_diagnostics)
        functional = load_physical_rescue_functional_probe_evidence(args.functional_probes)
        discovery = load_physical_storage_discovery_evidence(args.storage_discovery)
        review = load_physical_storage_review_evidence(args.storage_review)
        early = None
        if args.kali_early_userspace is not None:
            early = _load_simple_dataclass(
                args.kali_early_userspace,
                PhysicalKaliEarlyUserspaceEvidence,
                "physical Kali early-userspace evidence",
            )
            validate_physical_kali_early_userspace_evidence(early)
        evidence = bind_physical_bringup_session(
            gate,
            observation,
            diagnostics,
            functional,
            discovery,
            review,
            early_userspace=early,
        )
        digest = write_physical_bringup_session_evidence(evidence, args.out)
        return _safe_result(
            command,
            args.out,
            digest,
            profile_id=evidence.profile_id,
            device_serial=evidence.device_serial,
            kali_early_userspace_signal_present=evidence.kali_early_userspace_signal_present,
            manual_review_required=evidence.manual_review_required,
        )

    if command == "build-bringup-dossier":
        if (args.kali_early_userspace_evidence is None) != (args.kali_early_userspace_transcript is None):
            raise ValueError("Kali early-userspace evidence and transcript must be supplied together")
        evidence_files = {
            "physical_candidate_gate": args.candidate_gate,
            "physical_boot_observation": args.boot_observation,
            "rescue_diagnostics": args.rescue_diagnostics,
            "rescue_functional_probe": args.functional_probes,
            "physical_storage_discovery": args.storage_discovery,
            "physical_storage_review": args.storage_review,
        }
        raw_files = {
            "rescue_transcript": args.rescue_transcript,
            "storage_discovery_report": args.storage_discovery_report,
            "recovery_plan": args.recovery_plan,
            "storage_review_record": args.storage_review_record,
            "storage_review_notes": args.storage_review_notes,
        }
        if args.kali_early_userspace_evidence is not None:
            evidence_files["kali_early_userspace_evidence"] = args.kali_early_userspace_evidence
            raw_files["kali_early_userspace_transcript"] = args.kali_early_userspace_transcript
        session = load_physical_bringup_session_evidence(args.session)
        dossier = build_physical_bringup_dossier(
            session,
            session_file=args.session,
            evidence_files=evidence_files,
            raw_files=raw_files,
            rootfs_artifact=args.rootfs_artifact,
        )
        digest = write_physical_bringup_dossier_evidence(dossier, args.out)
        return _safe_result(
            command,
            args.out,
            digest,
            profile_id=dossier.profile_id,
            device_serial=dossier.device_serial,
            supplied_file_count=dossier.supplied_file_count,
            rootfs_artifact_file_verified=dossier.rootfs_artifact_file_verified,
            manual_review_required=True,
        )

    if command == "verify-bringup-dossier":
        role_files: dict[str, Path] = {}
        for role, path in args.file:
            if role in role_files:
                raise ValueError(f"duplicate --file role: {role}")
            role_files[role] = path
        dossier = load_physical_bringup_dossier_evidence(args.dossier)
        evidence = verify_physical_bringup_dossier_files(
            dossier,
            dossier_file=args.dossier,
            role_files=role_files,
        )
        digest = write_physical_bringup_dossier_verification_evidence(evidence, args.out)
        return _safe_result(
            command,
            args.out,
            digest,
            profile_id=evidence.profile_id,
            device_serial=evidence.device_serial,
            verified_role_count=evidence.verified_role_count,
            verified_byte_count=evidence.verified_byte_count,
            manual_review_required=True,
        )

    if command == "prepare-bringup-dossier-review":
        dossier = load_physical_bringup_dossier_evidence(args.dossier)
        record = PhysicalBringupDossierReviewRecord(
            schema_version=1,
            review_policy="manual-physical-bringup-dossier-review-v1",
            profile_id=dossier.profile_id,
            device_serial=dossier.device_serial,
            reviewer=args.reviewer,
            decision="rejected",
            physical_identity_reviewed=False,
            firmware_stock_boot_reviewed=False,
            candidate_authority_chain_reviewed=False,
            rescue_evidence_chain_reviewed=False,
            storage_review_chain_reviewed=False,
            exact_file_set_reviewed=False,
            recovery_plan_reviewed=False,
            target_selected=False,
            storage_path_bound=False,
            write_authorized=False,
        )
        parse_physical_bringup_dossier_review_record(json.loads(record.canonical_json()))
        notes = (
            "Physical bring-up dossier review notes\n"
            f"profile_id: {dossier.profile_id}\n"
            f"device_serial: {dossier.device_serial}\n"
            f"firmware_build: {dossier.firmware_build}\n\n"
            "Keep decision=rejected until every review check in the JSON record has been independently verified.\n"
            "Acceptance is only for a later separate strategy/release review; it does not select a target or authorize writes.\n"
        )
        record_digest, notes_digest = _write_pair_exclusive(
            args.record_out,
            record.canonical_json(),
            args.notes_out,
            notes,
        )
        return _safe_result(
            command,
            args.record_out,
            record_digest,
            profile_id=dossier.profile_id,
            device_serial=dossier.device_serial,
            decision="rejected",
            template_only=True,
            notes_path=str(args.notes_out),
            notes_sha256=notes_digest,
        )

    if command == "bind-bringup-dossier-review":
        dossier = load_physical_bringup_dossier_evidence(args.dossier)
        verification = load_physical_bringup_dossier_verification_for_review(args.verification)
        review, record_sha256, record_size = load_physical_bringup_dossier_review_record(args.review_record)
        notes_sha256, notes_size = read_physical_bringup_dossier_review_notes(args.review_notes)
        evidence = bind_physical_bringup_dossier_review(
            dossier,
            verification,
            review,
            review_record_sha256=record_sha256,
            review_record_size=record_size,
            review_notes_sha256=notes_sha256,
            review_notes_size=notes_size,
        )
        digest = write_physical_bringup_dossier_review_evidence(evidence, args.out)
        return _safe_result(
            command,
            args.out,
            digest,
            profile_id=evidence.profile_id,
            device_serial=evidence.device_serial,
            decision=evidence.decision,
            accepted_for_strategy_review=evidence.accepted_for_strategy_review,
            separate_strategy_review_required=evidence.separate_strategy_review_required,
        )

    if command == "build-release-gate-audit":
        evidence = build_physical_release_gate_audit_from_files(
            args.dossier,
            args.dossier_verification,
            args.dossier_review,
            args.functional_result_bundle,
            args.test_plan,
            args.test_plan_review,
        )
        digest = write_physical_release_gate_audit_evidence(evidence, args.out)
        return _safe_result(
            command,
            args.out,
            digest,
            profile_id=evidence.profile_id,
            device_serial=evidence.device_serial,
            cross_campaign_context_verified=evidence.cross_campaign_context_verified,
            beta_required_tests_all_reviewed_pass=evidence.beta_required_tests_all_reviewed_pass,
            kali_early_userspace_signal_present=evidence.kali_early_userspace_signal_present,
            manual_release_gate_review_required=evidence.manual_release_gate_review_required,
            physical_gate_still_incomplete=evidence.physical_gate_still_incomplete,
        )

    raise ValueError(f"unsupported late evidence command: {command}")


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
