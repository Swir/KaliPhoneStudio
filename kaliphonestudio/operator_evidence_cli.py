"""Shared offline evidence-workflow CLI for source and frozen host builds.

This module deliberately contains no ADB/Fastboot/subprocess/device-I/O path. It
consolidates exact-file rescue, survey-review, storage-review and functional-test
planning/result operations that previously required separate helper scripts.
Every operation consumes already captured evidence/files and preserves the
underlying fail-closed contracts; it cannot select a storage target, authorize a
persistent write, promote hardware support or grant Beta credit.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from typing import Sequence

from .physical_hardware_result_bundle import (
    build_physical_hardware_result_bundle_from_files,
    write_physical_hardware_result_bundle_evidence,
)
from .physical_campaign_admission import load_current_physical_campaign_observation
from .physical_hardware_review import (
    make_rejected_hardware_review_record,
    review_current_physical_hardware_survey_files,
    write_physical_hardware_review_evidence,
)
from .physical_hardware_survey import (
    load_physical_hardware_survey_evidence,
    record_physical_hardware_survey,
    write_physical_hardware_survey_evidence,
)
from .physical_hardware_test_observation import (
    bind_current_physical_hardware_test_observation_from_files,
    load_physical_hardware_test_observation_evidence,
    make_current_inconclusive_physical_hardware_test_observation_record,
    write_physical_hardware_test_observation_evidence,
)
from .physical_hardware_test_plan import (
    build_current_physical_hardware_test_plan_from_files,
    load_physical_hardware_test_plan,
    write_physical_hardware_test_plan,
)
from .physical_hardware_test_plan_review import (
    bind_current_physical_hardware_test_plan_review_from_files,
    load_physical_hardware_test_plan_review_evidence,
    make_rejected_physical_hardware_test_plan_review_record,
    write_physical_hardware_test_plan_review_evidence,
)
from .physical_hardware_test_review import (
    bind_physical_hardware_test_review_from_files,
    make_rejected_physical_hardware_test_review_record,
    write_physical_hardware_test_review_evidence,
)
from .physical_hardware_test_summary import (
    build_physical_hardware_test_summary_from_files,
    write_physical_hardware_test_summary_evidence,
)
from .physical_rescue_diagnostics import (
    load_physical_boot_observation_for_diagnostics,
    load_physical_rescue_diagnostics_evidence,
    record_physical_rescue_diagnostics,
    write_physical_rescue_diagnostics_evidence,
)
from .physical_storage_review import (
    PhysicalStorageReviewError,
    load_discovery_for_review,
    record_physical_storage_review,
    write_physical_storage_review_evidence,
)
from .profiles import get_profile


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEVICES_ROOT = REPO_ROOT / "devices"
_SAFE_REVIEWER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+-]{0,127}$")

EVIDENCE_COMMANDS = (
    "record-rescue-diagnostics",
    "record-hardware-survey",
    "prepare-hardware-survey-review",
    "bind-hardware-survey-review",
    "prepare-storage-review",
    "bind-storage-review",
    "build-functional-test-plan",
    "prepare-functional-test-plan-review",
    "bind-functional-test-plan-review",
    "prepare-functional-test-observation",
    "bind-functional-test-observation",
    "prepare-functional-test-result-review",
    "bind-functional-test-result-review",
    "summarize-functional-test-results",
    "build-functional-result-bundle",
)


def _add_output(parser: argparse.ArgumentParser, flag: str = "--out") -> None:
    parser.add_argument(flag, type=Path, required=True, help="New output path; existing files are never overwritten.")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="KaliPhoneStudio evidence",
        description=(
            "Offline exact-file evidence workspace. These commands do not connect to a phone, "
            "do not run adb/fastboot, do not select storage targets and grant no hardware/Beta credit."
        ),
    )
    parser.add_argument(
        "--devices-root",
        type=Path,
        default=DEFAULT_DEVICES_ROOT,
        help="Path containing devices/<vendor>/<codename>/profile.json.",
    )
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable safety/result summary.")
    sub = parser.add_subparsers(dest="evidence_command", required=True)

    rescue = sub.add_parser(
        "record-rescue-diagnostics",
        help="Bind bounded read-only rescue diagnostics to an existing physical boot observation/transcript.",
        description=(
            "Offline-only: parse the already captured rescue transcript and bind its bounded diagnostic block "
            "to one exact physical boot observation. No device command is executed."
        ),
    )
    rescue.add_argument("--profile-id", required=True)
    rescue.add_argument("--observation-evidence", type=Path, required=True)
    rescue.add_argument("--console-transcript", type=Path, required=True)
    _add_output(rescue)

    survey = sub.add_parser(
        "record-hardware-survey",
        help="Bind bounded hardware-presence markers from an existing rescue transcript.",
        description=(
            "Offline-only: bind bounded hardware-presence markers to exact rescue evidence. Presence is context, "
            "not functionality; no subsystem is activated."
        ),
    )
    survey.add_argument("--profile-id", required=True)
    survey.add_argument("--observation-evidence", type=Path, required=True)
    survey.add_argument("--rescue-diagnostics-evidence", type=Path, required=True)
    survey.add_argument("--console-transcript", type=Path, required=True)
    _add_output(survey)

    survey_template = sub.add_parser(
        "prepare-hardware-survey-review",
        help="Create a rejected-by-default manual survey-review record.",
    )
    survey_template.add_argument("--survey-evidence", type=Path, required=True)
    survey_template.add_argument("--reviewer", required=True)
    _add_output(survey_template)

    survey_review = sub.add_parser(
        "bind-hardware-survey-review",
        help="Bind an exact manual survey review to exact survey/notes bytes.",
    )
    survey_review.add_argument("--boot-observation", type=Path, required=True)
    survey_review.add_argument("--survey-evidence", type=Path, required=True)
    survey_review.add_argument("--review-record", type=Path, required=True)
    survey_review.add_argument("--review-notes", type=Path, required=True)
    _add_output(survey_review)

    storage_template = sub.add_parser(
        "prepare-storage-review",
        help="Create a rejected-by-default review record for existing physical storage-discovery evidence.",
        description=(
            "Offline-only: prepare a manual storage-review template. It cannot select a /dev path or authorize writes."
        ),
    )
    storage_template.add_argument("--discovery-evidence", type=Path, required=True)
    storage_template.add_argument("--reviewer", required=True)
    _add_output(storage_template)

    storage_review = sub.add_parser(
        "bind-storage-review",
        help="Bind exact storage discovery, review record and notes into immutable review evidence.",
        description=(
            "Offline-only: bind manual storage review evidence. Even accepted review only permits later strategy design; "
            "it does not select a target or authorize a write."
        ),
    )
    storage_review.add_argument("--discovery-evidence", type=Path, required=True)
    storage_review.add_argument("--review-record", type=Path, required=True)
    storage_review.add_argument("--review-notes", type=Path, required=True)
    _add_output(storage_review)

    plan = sub.add_parser(
        "build-functional-test-plan",
        help="Build a pending-only functional hardware test plan from accepted survey-review evidence.",
        description=(
            "Offline-only: build the profile-driven pending test plan. This is a checklist, not hardware verification."
        ),
    )
    plan.add_argument("--profile-id", required=True)
    plan.add_argument("--boot-observation", type=Path, required=True)
    plan.add_argument("--hardware-review-evidence", type=Path, required=True)
    _add_output(plan)

    plan_template = sub.add_parser(
        "prepare-functional-test-plan-review",
        help="Create a rejected-by-default independent review record for an exact test-plan file.",
    )
    plan_template.add_argument("--test-plan", type=Path, required=True)
    plan_template.add_argument("--reviewer", required=True)
    _add_output(plan_template)

    plan_review = sub.add_parser(
        "bind-functional-test-plan-review",
        help="Bind canonical test-plan bytes, manual review record and notes into immutable review evidence.",
    )
    plan_review.add_argument("--boot-observation", type=Path, required=True)
    plan_review.add_argument("--test-plan", type=Path, required=True)
    plan_review.add_argument("--review-record", type=Path, required=True)
    plan_review.add_argument("--review-notes", type=Path, required=True)
    _add_output(plan_review)

    observation_template = sub.add_parser(
        "prepare-functional-test-observation",
        help="Create an inconclusive/not-executed template for one exact reviewed physical functional test.",
        description=(
            "Offline-only: requires the exact accepted plan-review evidence before creating a template. "
            "The template starts not executed/inconclusive and grants no hardware/Beta credit."
        ),
    )
    observation_template.add_argument("--boot-observation", type=Path, required=True)
    observation_template.add_argument("--test-plan", type=Path, required=True)
    observation_template.add_argument("--test-plan-review-evidence", type=Path, required=True)
    observation_template.add_argument("--test-id", required=True)
    observation_template.add_argument("--operator", required=True)
    _add_output(observation_template)

    observation_bind = sub.add_parser(
        "bind-functional-test-observation",
        help="Bind one operator record/notes set to the exact accepted physical functional-test plan.",
        description=(
            "Offline-only evidence binding. The operator record must describe an already performed physical test; "
            "this command itself performs no phone I/O and cannot promote hardware/Beta status."
        ),
    )
    observation_bind.add_argument("--boot-observation", type=Path, required=True)
    observation_bind.add_argument("--test-plan", type=Path, required=True)
    observation_bind.add_argument("--test-plan-review-evidence", type=Path, required=True)
    observation_bind.add_argument("--test-id", required=True)
    observation_bind.add_argument("--observation-record", type=Path, required=True)
    observation_bind.add_argument("--observation-notes", type=Path, required=True)
    _add_output(observation_bind)

    result_review_template = sub.add_parser(
        "prepare-functional-test-result-review",
        help="Create a rejected-by-default independent review template for one exact observation evidence file.",
        description=(
            "Offline-only: prepares manual result review. A later accepted review is test-level evidence only "
            "and never authorizes project support or Beta release."
        ),
    )
    result_review_template.add_argument("--boot-observation", type=Path, required=True)
    result_review_template.add_argument("--observation-evidence", type=Path, required=True)
    result_review_template.add_argument("--reviewer", required=True)
    _add_output(result_review_template)

    result_review_bind = sub.add_parser(
        "bind-functional-test-result-review",
        help="Bind an exact observation, review record and review notes into immutable result-review evidence.",
        description=(
            "Offline-only: binds a manual reviewed pass/fail/inconclusive decision for one exact observation. "
            "Project support/hardware/Beta promotion remains forbidden."
        ),
    )
    result_review_bind.add_argument("--boot-observation", type=Path, required=True)
    result_review_bind.add_argument("--observation-evidence", type=Path, required=True)
    result_review_bind.add_argument("--review-record", type=Path, required=True)
    result_review_bind.add_argument("--review-notes", type=Path, required=True)
    _add_output(result_review_bind)

    result_summary = sub.add_parser(
        "summarize-functional-test-results",
        help="Build an exact-plan aggregate status summary from independent result-review evidence.",
        description=(
            "Offline-only: summarizes exact reviewed test statuses. Complete reviewed-pass coverage is still "
            "release-gate input only and grants no hardware/Beta credit."
        ),
    )
    result_summary.add_argument("--test-plan", type=Path, required=True)
    result_summary.add_argument("--review-evidence", type=Path, action="append", default=[])
    _add_output(result_summary)

    result_bundle = sub.add_parser(
        "build-functional-result-bundle",
        help="Freeze exact plan/review/observations/result-reviews/summary into one audit bundle.",
        description=(
            "Offline-only: cross-binds the complete exact-file functional campaign. Even complete Beta-required "
            "reviewed-pass coverage remains manual release-gate input and grants no hardware/Beta credit."
        ),
    )
    result_bundle.add_argument("--test-plan", type=Path, required=True)
    result_bundle.add_argument("--test-plan-review-evidence", type=Path, required=True)
    result_bundle.add_argument("--observation-evidence", type=Path, action="append", default=[])
    result_bundle.add_argument("--review-evidence", type=Path, action="append", default=[])
    result_bundle.add_argument("--summary-evidence", type=Path, required=True)
    _add_output(result_bundle)

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
    print("hardware/Beta credit: no")
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
            "beta_gate_credit",
        }:
            continue
        print(f"{key}: {value}")


def _write_text_exclusive(destination: Path, payload: str) -> str:
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"refusing to overwrite existing output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
    return sha256(destination.read_bytes()).hexdigest()


def _prepare_storage_review(discovery_path: Path, reviewer: str, destination: Path) -> tuple[str, object]:
    if not _SAFE_REVIEWER_RE.fullmatch(reviewer):
        raise PhysicalStorageReviewError("reviewer must be a safe identifier using letters, numbers, . _ @ + or -")
    discovery = load_discovery_for_review(discovery_path)
    template = {
        "schema_version": 1,
        "profile_id": discovery.profile_id,
        "device_serial": discovery.device_serial,
        "review_policy": "manual-physical-storage-review-v1",
        "reviewer": reviewer,
        "decision": "rejected",
        "physical_context_reviewed": False,
        "topology_reviewed": False,
        "filesystem_reviewed": False,
        "encryption_reviewed": False,
        "free_space_reviewed": False,
        "recovery_plan_reviewed": False,
        "evidence_chain_reviewed": False,
        "target_selected": False,
        "storage_path_bound": False,
        "write_authorized": False,
    }
    payload = json.dumps(template, indent=2, sort_keys=True) + "\n"
    return _write_text_exclusive(destination, payload), discovery


def _run(args: argparse.Namespace) -> dict[str, object]:
    command = args.evidence_command
    if command == "record-rescue-diagnostics":
        profile = get_profile(args.devices_root, args.profile_id)
        observation = load_physical_boot_observation_for_diagnostics(args.observation_evidence)
        evidence = record_physical_rescue_diagnostics(profile, observation, args.console_transcript)
        digest = write_physical_rescue_diagnostics_evidence(evidence, args.out)
        return _safe_result(
            command,
            args.out,
            digest,
            profile_id=evidence.profile_id,
            device_serial=evidence.device_serial,
            diagnostic_record_count=evidence.diagnostic_record_count,
            manual_review_required=evidence.manual_review_required,
        )

    if command == "record-hardware-survey":
        profile = get_profile(args.devices_root, args.profile_id)
        observation = load_physical_boot_observation_for_diagnostics(args.observation_evidence)
        diagnostics = load_physical_rescue_diagnostics_evidence(args.rescue_diagnostics_evidence)
        evidence = record_physical_hardware_survey(profile, observation, diagnostics, args.console_transcript)
        digest = write_physical_hardware_survey_evidence(evidence, args.out)
        return _safe_result(
            command,
            args.out,
            digest,
            profile_id=evidence.profile_id,
            device_serial=evidence.device_serial,
            survey_recorded=evidence.hardware_survey_recorded,
            manual_review_required=evidence.manual_review_required,
        )

    if command == "prepare-hardware-survey-review":
        survey = load_physical_hardware_survey_evidence(args.survey_evidence)
        record = make_rejected_hardware_review_record(survey, args.reviewer)
        digest = _write_text_exclusive(args.out, record.canonical_json())
        return _safe_result(
            command,
            args.out,
            digest,
            profile_id=survey.profile_id,
            device_serial=survey.device_serial,
            decision="rejected",
            template_only=True,
        )

    if command == "bind-hardware-survey-review":
        observation = load_current_physical_campaign_observation(args.boot_observation)
        evidence = review_current_physical_hardware_survey_files(
            observation,
            args.survey_evidence,
            args.review_record,
            args.review_notes,
        )
        digest = write_physical_hardware_review_evidence(evidence, args.out)
        return _safe_result(
            command,
            args.out,
            digest,
            profile_id=evidence.profile_id,
            device_serial=evidence.device_serial,
            decision=evidence.decision,
            accepted_as_context=evidence.accepted_as_context,
        )

    if command == "prepare-storage-review":
        digest, discovery = _prepare_storage_review(args.discovery_evidence, args.reviewer, args.out)
        return _safe_result(
            command,
            args.out,
            digest,
            profile_id=discovery.profile_id,
            device_serial=discovery.device_serial,
            decision="rejected",
            template_only=True,
        )

    if command == "bind-storage-review":
        discovery = load_discovery_for_review(args.discovery_evidence)
        evidence = record_physical_storage_review(discovery, args.review_record, args.review_notes)
        digest = write_physical_storage_review_evidence(evidence, args.out)
        return _safe_result(
            command,
            args.out,
            digest,
            profile_id=evidence.profile_id,
            device_serial=evidence.device_serial,
            decision=evidence.decision,
            accepted_for_strategy_design=evidence.accepted_for_strategy_design,
        )

    if command == "build-functional-test-plan":
        profile = get_profile(args.devices_root, args.profile_id)
        observation = load_current_physical_campaign_observation(args.boot_observation)
        plan = build_current_physical_hardware_test_plan_from_files(
            profile, observation, args.hardware_review_evidence
        )
        digest = write_physical_hardware_test_plan(plan, args.out)
        return _safe_result(
            command,
            args.out,
            digest,
            profile_id=plan.profile_id,
            device_serial=plan.device_serial,
            test_count=plan.test_count,
            beta_required_test_count=plan.beta_required_test_count,
            plan_ready_for_physical_execution=plan.plan_ready_for_physical_execution,
            all_test_statuses="pending",
        )

    if command == "prepare-functional-test-plan-review":
        plan = load_physical_hardware_test_plan(args.test_plan)
        record = make_rejected_physical_hardware_test_plan_review_record(plan, args.reviewer)
        digest = _write_text_exclusive(args.out, record.canonical_json())
        return _safe_result(
            command,
            args.out,
            digest,
            profile_id=plan.profile_id,
            device_serial=plan.device_serial,
            decision="rejected",
            template_only=True,
        )

    if command == "bind-functional-test-plan-review":
        observation = load_current_physical_campaign_observation(args.boot_observation)
        evidence = bind_current_physical_hardware_test_plan_review_from_files(
            observation,
            args.test_plan,
            args.review_record,
            args.review_notes,
        )
        digest = write_physical_hardware_test_plan_review_evidence(evidence, args.out)
        return _safe_result(
            command,
            args.out,
            digest,
            profile_id=evidence.profile_id,
            device_serial=evidence.device_serial,
            decision=evidence.decision,
            accepted_for_physical_execution=evidence.accepted_for_physical_execution,
        )

    if command == "prepare-functional-test-observation":
        observation = load_current_physical_campaign_observation(args.boot_observation)
        plan = load_physical_hardware_test_plan(args.test_plan)
        plan_review = load_physical_hardware_test_plan_review_evidence(args.test_plan_review_evidence)
        record = make_current_inconclusive_physical_hardware_test_observation_record(
            observation,
            plan,
            plan_review,
            args.test_id,
            args.operator,
        )
        digest = _write_text_exclusive(args.out, record.canonical_json())
        return _safe_result(
            command,
            args.out,
            digest,
            profile_id=record.profile_id,
            device_serial=record.device_serial,
            test_id=record.test_id,
            outcome=record.outcome,
            physical_test_executed=record.physical_test_executed,
            template_only=True,
        )

    if command == "bind-functional-test-observation":
        observation = load_current_physical_campaign_observation(args.boot_observation)
        evidence = bind_current_physical_hardware_test_observation_from_files(
            observation,
            args.test_plan,
            args.test_plan_review_evidence,
            args.test_id,
            args.observation_record,
            args.observation_notes,
        )
        digest = write_physical_hardware_test_observation_evidence(evidence, args.out)
        return _safe_result(
            command,
            args.out,
            digest,
            profile_id=evidence.profile_id,
            device_serial=evidence.device_serial,
            test_id=evidence.test_id,
            outcome=evidence.outcome,
            evidence_physical_test_executed=evidence.physical_test_executed,
            manual_review_required=evidence.manual_review_required,
        )

    if command == "prepare-functional-test-result-review":
        boot_observation = load_current_physical_campaign_observation(args.boot_observation)
        observation = load_physical_hardware_test_observation_evidence(args.observation_evidence)
        record = make_current_rejected_physical_hardware_test_review_record(
            boot_observation, observation, args.reviewer
        )
        digest = _write_text_exclusive(args.out, record.canonical_json())
        return _safe_result(
            command,
            args.out,
            digest,
            profile_id=observation.profile_id,
            device_serial=observation.device_serial,
            test_id=observation.test_id,
            decision="rejected",
            template_only=True,
        )

    if command == "bind-functional-test-result-review":
        boot_observation = load_current_physical_campaign_observation(args.boot_observation)
        evidence = bind_current_physical_hardware_test_review_from_files(
            boot_observation,
            args.observation_evidence,
            args.review_record,
            args.review_notes,
        )
        digest = write_physical_hardware_test_review_evidence(evidence, args.out)
        return _safe_result(
            command,
            args.out,
            digest,
            profile_id=evidence.profile_id,
            device_serial=evidence.device_serial,
            test_id=evidence.test_id,
            decision=evidence.decision,
            reviewed_result=evidence.reviewed_result,
            accepted_for_functional_status=evidence.accepted_for_functional_status,
            manual_release_gate_review_required=evidence.manual_release_gate_review_required,
        )

    if command == "summarize-functional-test-results":
        summary = build_physical_hardware_test_summary_from_files(
            args.test_plan,
            args.review_evidence,
        )
        digest = write_physical_hardware_test_summary_evidence(summary, args.out)
        return _safe_result(
            command,
            args.out,
            digest,
            profile_id=summary.profile_id,
            device_serial=summary.device_serial,
            reviewed_pass_count=summary.reviewed_pass_count,
            test_count=summary.test_count,
            beta_required_reviewed_pass_count=summary.beta_required_reviewed_pass_count,
            beta_required_test_count=summary.beta_required_test_count,
            beta_required_tests_all_reviewed_pass=summary.beta_required_tests_all_reviewed_pass,
            manual_release_gate_review_required=True,
        )

    if command == "build-functional-result-bundle":
        bundle = build_physical_hardware_result_bundle_from_files(
            args.test_plan,
            args.test_plan_review_evidence,
            args.observation_evidence,
            args.review_evidence,
            args.summary_evidence,
        )
        digest = write_physical_hardware_result_bundle_evidence(bundle, args.out)
        return _safe_result(
            command,
            args.out,
            digest,
            profile_id=bundle.profile_id,
            device_serial=bundle.device_serial,
            observation_count=bundle.observation_count,
            result_review_count=bundle.result_review_count,
            beta_required_reviewed_pass_count=bundle.beta_required_reviewed_pass_count,
            beta_required_test_count=bundle.beta_required_test_count,
            beta_required_tests_all_reviewed_pass=bundle.beta_required_tests_all_reviewed_pass,
            manual_release_gate_review_required=True,
        )

    raise ValueError(f"unsupported evidence command: {command}")


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
