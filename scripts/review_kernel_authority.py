#!/usr/bin/env python3
"""Create and immediately re-verify a reviewed host-side kernel authority record.

This command never talks to a phone. It accepts only an already-successful strict
A/B kernel evidence chain plus explicit GitHub run/commit/artifact identity. The
operator must pass ``--reviewed`` deliberately. The resulting authority always
keeps ``hardware_verified=false`` and ``beta_gate_credit=false``.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaliphonestudio.kernel_authority import (  # noqa: E402
    build_reviewed_kernel_authority,
    load_and_verify_kernel_authority,
    write_kernel_authority,
)
from kaliphonestudio.kernel_build_binding import (  # noqa: E402
    KernelReproducibilityBindingEvidence,
    load_kernel_build_run_evidence,
    load_kernel_reproducibility_evidence,
)
from kaliphonestudio.kernel_contract import create_kernel_build_plan  # noqa: E402
from kaliphonestudio.kernel_toolchain import load_kernel_toolchain_lock  # noqa: E402
from kaliphonestudio.profiles import get_profile  # noqa: E402


def _load_binding(path: Path) -> KernelReproducibilityBindingEvidence:
    if path.is_symlink() or not path.is_file():
        raise ValueError("kernel reproducibility binding must be a regular non-symlink JSON file")
    raw = json.loads(path.read_text(encoding="utf-8"))
    expected = set(KernelReproducibilityBindingEvidence.__dataclass_fields__)
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ValueError("kernel reproducibility binding fields do not match schema")
    return KernelReproducibilityBindingEvidence(**raw)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--profile-id", required=True)
    p.add_argument("--devices-root", type=Path, default=ROOT / "devices")
    p.add_argument("--toolchain-lock", type=Path, default=ROOT / "tools" / "kernel-toolchain-lock.json")
    p.add_argument("--repro-evidence", type=Path, required=True)
    p.add_argument("--binding-evidence", type=Path, required=True)
    p.add_argument("--build-evidence-a", type=Path, required=True)
    p.add_argument("--build-evidence-b", type=Path, required=True)
    p.add_argument("--authority-name", required=True)
    p.add_argument("--authority-run-id", type=int, required=True)
    p.add_argument("--authority-commit", required=True)
    p.add_argument("--authority-artifact-id", type=int, required=True)
    p.add_argument("--reviewed", action="store_true", help="explicitly confirm completed evidence review")
    p.add_argument("--out", type=Path, required=True)
    return p


def main() -> int:
    args = parser().parse_args()
    if not args.reviewed:
        raise SystemExit("refusing kernel authority creation without explicit --reviewed")
    if args.out.exists():
        raise SystemExit(f"refusing to overwrite existing authority: {args.out}")

    profile = get_profile(args.devices_root, args.profile_id)
    plan = create_kernel_build_plan(profile)
    lock = load_kernel_toolchain_lock(args.toolchain_lock)
    reproducibility = load_kernel_reproducibility_evidence(args.repro_evidence)
    binding = _load_binding(args.binding_evidence)
    build_a = load_kernel_build_run_evidence(args.build_evidence_a)
    build_b = load_kernel_build_run_evidence(args.build_evidence_b)

    authority = build_reviewed_kernel_authority(
        authority_name=args.authority_name,
        authority_run_id=args.authority_run_id,
        authority_commit=args.authority_commit,
        authority_artifact_id=args.authority_artifact_id,
        plan=plan,
        lock=lock,
        reproducibility=reproducibility,
        binding=binding,
        build_a=build_a,
        build_b=build_b,
        reviewed=True,
    )
    digest = write_kernel_authority(authority, args.out)

    verified = load_and_verify_kernel_authority(
        args.out,
        plan,
        lock,
        args.repro_evidence,
        args.binding_evidence,
        args.build_evidence_a,
        args.build_evidence_b,
    )
    if verified.authority_sha256() != digest:
        raise SystemExit("kernel authority round-trip digest mismatch")

    print(json.dumps({
        "authority_name": verified.authority_name,
        "authority_sha256": digest,
        "authority_run_id": verified.authority_run_id,
        "authority_commit": verified.authority_commit,
        "authority_artifact_id": verified.authority_artifact_id,
        "profile_id": verified.profile_id,
        "image_sha256": verified.image_sha256,
        "image_size": verified.image_size,
        "strict_byte_identical": verified.strict_byte_identical,
        "distinct_build_roots_verified": verified.distinct_build_roots_verified,
        "reviewed": verified.reviewed,
        "hardware_verified": verified.hardware_verified,
        "beta_gate_credit": verified.beta_gate_credit,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
