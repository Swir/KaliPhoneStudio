"""One-command host-only preparation of a reviewed physical test candidate.

This module intentionally stops before temporary boot.  It composes the existing
fail-closed host-side stages that an operator otherwise has to run one by one:

* exact local OTA -> stock boot extraction/provenance;
* physical baseline -> exact stock baseline binding;
* exact reviewed first-boot candidate binding;
* local stock/candidate boot identity binding;
* serial-bound temporary-boot offer preparation; and
* physical recovery-readiness preparation.

The command never invokes Fastboot/ADB, never boots/reboots a phone, never changes
a slot and never writes phone storage.  It consumes the read-only baseline already
captured by ``begin-physical-test-session`` and creates a final exact-file manifest
that can be reviewed before the separate, explicit one-shot temporary-boot command.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Callable, Sequence

from .physical_boot_identity_operator import main as bind_physical_boot_identity_main
from .physical_candidate_operator import (
    bind_physical_candidate_main,
    prepare_temporary_boot_offer_main,
)
from .physical_recovery_operator import main as build_physical_recovery_readiness_main
from .stable_file import StableFileError, hash_stable_regular_file, read_stable_regular_file
from .stock_baseline_ingress import bind_physical_stock_main
from .stock_ota_pipeline import main as extract_stock_boot_from_ota_main


SESSION_MANIFEST_NAME = "physical-first-test-session.json"
PREPARATION_MANIFEST_NAME = "physical-candidate-offline-preparation.json"
_MAX_JSON_BYTES = 4 * 1024 * 1024
_MAX_ARTIFACT_BYTES = 16 * 1024 * 1024 * 1024


class PhysicalCandidatePreparationError(RuntimeError):
    """Raised when host-only candidate preparation cannot remain fail closed."""


@dataclass(frozen=True)
class PhysicalCandidateOfflinePreparation:
    schema_version: int
    profile_id: str
    device_serial: str
    firmware_build: str
    firmware_fingerprint: str
    session_manifest_sha256: str
    ota_sha256: str
    first_boot_manifest_sha256: str
    authority_bundle_sha256: str
    boot_authorization_sha256: str
    boot_plan_sha256: str
    candidate_boot_sha256: str
    candidate_dtbo_sha256: str | None
    fastboot_executable_sha256: str
    physical_stock_baseline_sha256: str
    physical_candidate_gate_sha256: str
    physical_boot_identity_sha256: str
    temporary_boot_offer_sha256: str
    physical_recovery_readiness_sha256: str
    host_pipeline_complete: bool
    ready_for_temporary_boot_safety_review: bool
    physical_interaction_performed_by_this_command: bool
    external_device_command_executed: bool
    temporary_boot_executed: bool
    persistent_write_authorized: bool
    phone_storage_written: bool
    hardware_verified: bool
    beta_release_authorized: bool
    beta_gate_credit: bool

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")) + "\n"

    def evidence_sha256(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


def _load_session_manifest(path: Path) -> tuple[dict[str, object], str]:
    try:
        raw, identity = read_stable_regular_file(
            Path(path),
            max_bytes=_MAX_JSON_BYTES,
            label="physical first-test session manifest",
        )
    except StableFileError as exc:
        raise PhysicalCandidatePreparationError(str(exc)) from exc
    try:
        data = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PhysicalCandidatePreparationError("physical first-test session manifest is not strict UTF-8 JSON") from exc
    if not isinstance(data, dict):
        raise PhysicalCandidatePreparationError("physical first-test session manifest must contain one JSON object")
    required_text = ("profile_id", "device_serial", "firmware_build", "firmware_fingerprint")
    for key in required_text:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise PhysicalCandidatePreparationError(f"physical first-test session manifest has invalid {key}")
    if data.get("confirmation_token_verified") is not True:
        raise PhysicalCandidatePreparationError("physical first-test session confirmation token was not verified")
    if data.get("read_only_baseline_only") is not True:
        raise PhysicalCandidatePreparationError("physical first-test session is not a read-only baseline")
    for forbidden in (
        "temporary_boot_performed",
        "persistent_write_authorized",
        "phone_storage_written",
        "hardware_verified",
        "beta_gate_credit",
    ):
        if data.get(forbidden) is not False:
            raise PhysicalCandidatePreparationError(f"physical first-test session has unsafe {forbidden} state")
    return data, identity.sha256


def _require_regular(path: Path, label: str, *, max_bytes: int = _MAX_ARTIFACT_BYTES) -> str:
    try:
        identity = hash_stable_regular_file(Path(path), max_bytes=max_bytes, label=label)
    except StableFileError as exc:
        raise PhysicalCandidatePreparationError(str(exc)) from exc
    return identity.sha256


def _require_fresh_output(path: Path, label: str) -> None:
    candidate = Path(path)
    if candidate.exists() or candidate.is_symlink():
        raise PhysicalCandidatePreparationError(f"refusing to overwrite {label}: {candidate}")
    temporary = candidate.with_name(candidate.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise PhysicalCandidatePreparationError(f"refusing stale {label} temporary path: {temporary}")


def _invoke_stage(label: str, function: Callable[[Sequence[str] | None], int], argv: list[str]) -> None:
    """Run one already-tested host stage and normalize argparse refusals."""
    try:
        result = function(argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 2
        raise PhysicalCandidatePreparationError(f"{label} refused with exit code {code}") from exc
    if result != 0:
        raise PhysicalCandidatePreparationError(f"{label} refused with exit code {result}")


def _write_manifest(evidence: PhysicalCandidateOfflinePreparation, destination: Path) -> str:
    destination = Path(destination)
    _require_fresh_output(destination, "offline candidate preparation manifest")
    payload = evidence.canonical_json().encode("utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as handle:
            handle.write(payload)
    except OSError as exc:
        raise PhysicalCandidatePreparationError(f"cannot write offline candidate preparation manifest: {exc}") from exc
    return sha256(payload).hexdigest()


def prepare_physical_candidate_offline(
    *,
    profile_id: str,
    session_dir: Path,
    devices_root: Path,
    ota: Path,
    extractor: Path,
    extractor_platform: str,
    first_boot_manifest: Path,
    authority_bundle: Path,
    boot_authorization: Path,
    boot_plan: Path,
    candidate_boot: Path,
    candidate_dtbo: Path | None,
    fastboot_executable: Path,
) -> tuple[PhysicalCandidateOfflinePreparation, str]:
    """Compose the existing offline candidate-preparation stages into one exact flow."""
    session = Path(session_dir)
    if session.is_symlink() or not session.is_dir():
        raise PhysicalCandidatePreparationError("session directory must be the existing non-symlink first-test session")

    session_manifest = session / SESSION_MANIFEST_NAME
    session_data, session_manifest_sha = _load_session_manifest(session_manifest)
    if session_data["profile_id"] != profile_id:
        raise PhysicalCandidatePreparationError("selected profile does not match physical first-test session")

    baseline = session / "fastboot" / "fastboot-baseline.json"
    capture = session / "fastboot" / "fastboot-capture-bundle.json"
    fastboot_tool = session / "fastboot" / "fastboot-tool.json"
    for path, label in (
        (baseline, "Fastboot baseline evidence"),
        (capture, "Fastboot capture bundle"),
        (fastboot_tool, "Fastboot tool evidence"),
    ):
        _require_regular(path, label, max_bytes=_MAX_JSON_BYTES)

    # Hash every operator-supplied source before producing any new evidence.  The
    # downstream stages then independently re-validate the exact typed contents.
    source_hashes = {
        "ota": _require_regular(ota, "exact matching OTA"),
        "first_boot_manifest": _require_regular(first_boot_manifest, "first-boot manifest", max_bytes=_MAX_JSON_BYTES),
        "authority_bundle": _require_regular(authority_bundle, "authority bundle", max_bytes=_MAX_JSON_BYTES),
        "boot_authorization": _require_regular(boot_authorization, "temporary-boot authorization", max_bytes=_MAX_JSON_BYTES),
        "boot_plan": _require_regular(boot_plan, "boot build plan", max_bytes=_MAX_JSON_BYTES),
        "candidate_boot": _require_regular(candidate_boot, "candidate boot image"),
        "fastboot_executable": _require_regular(fastboot_executable, "reviewed Fastboot executable"),
    }
    candidate_dtbo_sha: str | None = None
    if candidate_dtbo is not None:
        candidate_dtbo_sha = _require_regular(candidate_dtbo, "candidate DTBO image")

    stock_dir = session / "stock"
    stock_boot = stock_dir / "partitions" / "boot.img"
    stock_provenance = stock_dir / "stock-provenance.json"
    physical_stock = session / "physical-stock-baseline.json"
    physical_candidate = session / "physical-candidate-gate.json"
    boot_identity = session / "physical-boot-identity.json"
    temporary_offer = session / "temporary-boot-offer.json"
    recovery_readiness = session / "physical-recovery-readiness.json"
    final_manifest = session / PREPARATION_MANIFEST_NAME

    # Refuse mixed/reused sessions before running the first potentially expensive
    # host stage.  stock_dir is create-only in the OTA pipeline itself.
    for path, label in (
        (physical_stock, "physical stock baseline"),
        (physical_candidate, "physical candidate gate"),
        (boot_identity, "physical boot identity"),
        (temporary_offer, "temporary boot offer"),
        (recovery_readiness, "physical recovery readiness"),
        (final_manifest, "offline candidate preparation manifest"),
    ):
        _require_fresh_output(path, label)
    if stock_dir.exists() or stock_dir.is_symlink():
        raise PhysicalCandidatePreparationError(f"refusing to reuse stock preparation directory: {stock_dir}")

    common_profile = ["--profile-id", profile_id, "--devices-root", str(devices_root)]

    _invoke_stage(
        "stock OTA extraction",
        extract_stock_boot_from_ota_main,
        common_profile
        + [
            "--ota", str(ota),
            "--extractor", str(extractor),
            "--extractor-platform", extractor_platform,
            "--out-dir", str(stock_dir),
        ],
    )
    _invoke_stage(
        "physical stock baseline binding",
        bind_physical_stock_main,
        common_profile
        + [
            "--baseline-evidence", str(baseline),
            "--capture-evidence", str(capture),
            "--stock-provenance", str(stock_provenance),
            "--out", str(physical_stock),
        ],
    )
    _invoke_stage(
        "physical candidate binding",
        bind_physical_candidate_main,
        common_profile
        + [
            "--physical-baseline", str(physical_stock),
            "--first-boot-manifest", str(first_boot_manifest),
            "--authority-bundle", str(authority_bundle),
            "--boot-authorization", str(boot_authorization),
            "--boot-plan", str(boot_plan),
            "--out", str(physical_candidate),
        ],
    )

    boot_identity_args = common_profile + [
        "--physical-baseline", str(physical_stock),
        "--physical-candidate-gate", str(physical_candidate),
        "--stock-provenance", str(stock_provenance),
        "--boot-plan", str(boot_plan),
        "--stock-boot", str(stock_boot),
        "--candidate-boot", str(candidate_boot),
    ]
    if candidate_dtbo is not None:
        boot_identity_args += ["--candidate-dtbo", str(candidate_dtbo)]
    boot_identity_args += ["--out", str(boot_identity)]
    _invoke_stage("physical boot identity binding", bind_physical_boot_identity_main, boot_identity_args)

    _invoke_stage(
        "temporary boot offer preparation",
        prepare_temporary_boot_offer_main,
        common_profile
        + [
            "--physical-candidate-gate", str(physical_candidate),
            "--capture-bundle", str(capture),
            "--fastboot-tool-evidence", str(fastboot_tool),
            "--fastboot-executable", str(fastboot_executable),
            "--boot-image", str(candidate_boot),
            "--out", str(temporary_offer),
        ],
    )
    _invoke_stage(
        "physical recovery readiness",
        build_physical_recovery_readiness_main,
        common_profile
        + [
            "--baseline-evidence", str(baseline),
            "--physical-baseline", str(physical_stock),
            "--boot-identity-binding", str(boot_identity),
            "--stock-boot", str(stock_boot),
            "--out", str(recovery_readiness),
        ],
    )

    # Re-hash the five generated safety outputs after all stages completed.  This
    # manifest is review material only; temporary boot remains a separate command.
    output_hashes = {
        "physical_stock": _require_regular(physical_stock, "physical stock baseline", max_bytes=_MAX_JSON_BYTES),
        "physical_candidate": _require_regular(physical_candidate, "physical candidate gate", max_bytes=_MAX_JSON_BYTES),
        "boot_identity": _require_regular(boot_identity, "physical boot identity", max_bytes=_MAX_JSON_BYTES),
        "temporary_offer": _require_regular(temporary_offer, "temporary boot offer", max_bytes=_MAX_JSON_BYTES),
        "recovery_readiness": _require_regular(recovery_readiness, "physical recovery readiness", max_bytes=_MAX_JSON_BYTES),
    }

    evidence = PhysicalCandidateOfflinePreparation(
        schema_version=1,
        profile_id=profile_id,
        device_serial=str(session_data["device_serial"]),
        firmware_build=str(session_data["firmware_build"]),
        firmware_fingerprint=str(session_data["firmware_fingerprint"]),
        session_manifest_sha256=session_manifest_sha,
        ota_sha256=source_hashes["ota"],
        first_boot_manifest_sha256=source_hashes["first_boot_manifest"],
        authority_bundle_sha256=source_hashes["authority_bundle"],
        boot_authorization_sha256=source_hashes["boot_authorization"],
        boot_plan_sha256=source_hashes["boot_plan"],
        candidate_boot_sha256=source_hashes["candidate_boot"],
        candidate_dtbo_sha256=candidate_dtbo_sha,
        fastboot_executable_sha256=source_hashes["fastboot_executable"],
        physical_stock_baseline_sha256=output_hashes["physical_stock"],
        physical_candidate_gate_sha256=output_hashes["physical_candidate"],
        physical_boot_identity_sha256=output_hashes["boot_identity"],
        temporary_boot_offer_sha256=output_hashes["temporary_offer"],
        physical_recovery_readiness_sha256=output_hashes["recovery_readiness"],
        host_pipeline_complete=True,
        ready_for_temporary_boot_safety_review=True,
        physical_interaction_performed_by_this_command=False,
        external_device_command_executed=False,
        temporary_boot_executed=False,
        persistent_write_authorized=False,
        phone_storage_written=False,
        hardware_verified=False,
        beta_release_authorized=False,
        beta_gate_credit=False,
    )
    digest = _write_manifest(evidence, final_manifest)
    return evidence, digest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="KaliPhoneStudio prepare-physical-candidate-offline",
        description=(
            "Compose the exact host-only AC2003 candidate preparation chain after a read-only first-test session. "
            "No Fastboot/ADB command, temporary boot, slot change or phone-storage write is performed."
        ),
    )
    parser.add_argument("--profile-id", required=True)
    parser.add_argument(
        "--devices-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "devices",
    )
    parser.add_argument("--session-dir", type=Path, required=True)
    parser.add_argument("--ota", type=Path, required=True)
    parser.add_argument("--extractor", type=Path, required=True)
    parser.add_argument("--extractor-platform", required=True)
    parser.add_argument("--first-boot-manifest", type=Path, required=True)
    parser.add_argument("--authority-bundle", type=Path, required=True)
    parser.add_argument("--boot-authorization", type=Path, required=True)
    parser.add_argument("--boot-plan", type=Path, required=True)
    parser.add_argument("--candidate-boot", type=Path, required=True)
    parser.add_argument("--candidate-dtbo", type=Path)
    parser.add_argument("--fastboot-executable", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        evidence, digest = prepare_physical_candidate_offline(
            profile_id=args.profile_id,
            session_dir=args.session_dir,
            devices_root=args.devices_root,
            ota=args.ota,
            extractor=args.extractor,
            extractor_platform=args.extractor_platform,
            first_boot_manifest=args.first_boot_manifest,
            authority_bundle=args.authority_bundle,
            boot_authorization=args.boot_authorization,
            boot_plan=args.boot_plan,
            candidate_boot=args.candidate_boot,
            candidate_dtbo=args.candidate_dtbo,
            fastboot_executable=args.fastboot_executable,
        )
    except (PhysicalCandidatePreparationError, StableFileError, OSError, ValueError) as exc:
        parser.exit(2, f"offline candidate preparation refused: {exc}\n")

    print(evidence.canonical_json(), end="")
    print(f"offline candidate preparation sha256={digest}")
    print("temporary_boot_executed=false")
    print("persistent_write_authorized=false")
    print("phone_storage_written=false")
    print("hardware/Beta credit=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
