#!/usr/bin/env python3
"""Build one canonical Phosh-capable ARM64 rootfs candidate from the pinned upstream checkout."""
from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kaliphonestudio.phosh import PhoshError, evaluate_phosh_package_manifest, load_phosh_source_lock, verify_phosh_source_tree  # noqa: E402
from kaliphonestudio.phosh_build import (  # noqa: E402
    PhoshBuildError, create_phosh_rootfs_build_evidence, create_phosh_rootfs_build_plan,
    load_phosh_rootfs_build_contract, render_family_supplement_recipe, write_phosh_rootfs_build_evidence,
)
from kaliphonestudio.rootfs import package_manifest_from_rootfs  # noqa: E402
from kaliphonestudio.rootfs_canonical import canonicalize_rootfs_archive, write_canonicalization_evidence  # noqa: E402

_STAGE_RECIPE_NAME = ".kaliphonestudio-phosh-qcom-stage.yaml"
_MIN_ARTIFACT_BYTES = 64 * 1024 * 1024


def _git_output(checkout: Path, *args: str) -> str:
    try:
        result = subprocess.run(["git", "-C", str(checkout), *args], check=True, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        raise PhoshBuildError(f"cannot inspect Phosh source checkout: {exc}") from exc
    return result.stdout.strip()


def _run(argv: tuple[str, ...], checkout: Path, timeout: int, label: str) -> None:
    try:
        subprocess.run(list(argv), cwd=checkout, check=True, shell=False, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        raise PhoshBuildError(f"{label} failed: {exc}") from exc


def _require_fresh_artifact(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise PhoshBuildError(f"{label} was not produced as a regular file")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise PhoshBuildError(f"cannot inspect {label}: {exc}") from exc
    if size < _MIN_ARTIFACT_BYTES:
        raise PhoshBuildError(f"{label} is unexpectedly small: {size} bytes")
    return path


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Build one host-only Phosh ARM64 rootfs candidate. This does not create a reviewed reproducibility authority and grants no hardware/Beta credit.")
    result.add_argument("--lock", type=Path, default=Path("tools/phosh-source-lock.json"))
    result.add_argument("--build-contract", type=Path, default=Path("tools/phosh-rootfs-build-contract.json"))
    result.add_argument("--checkout", type=Path, required=True)
    result.add_argument("--out", type=Path, required=True)
    result.add_argument("--package-manifest", type=Path, required=True)
    result.add_argument("--build-evidence", type=Path, required=True)
    result.add_argument("--canonicalization-evidence", type=Path)
    result.add_argument("--timeout", type=int, default=7200)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.timeout <= 0:
        raise PhoshBuildError("Phosh rootfs build timeout must be positive")
    source_lock = load_phosh_source_lock(args.lock)
    contract = load_phosh_rootfs_build_contract(args.build_contract, source_lock)
    checkout = args.checkout.resolve()
    if checkout.is_symlink() or not checkout.is_dir():
        raise PhoshBuildError("Phosh source checkout must be a real directory")
    head = _git_output(checkout, "rev-parse", "HEAD")
    if head != source_lock.upstream_commit:
        raise PhoshBuildError(f"Phosh source checkout is not the locked commit: {head}")
    if _git_output(checkout, "status", "--porcelain", "--untracked-files=no"):
        raise PhoshBuildError("Phosh source checkout has tracked modifications")
    verify_phosh_source_tree(source_lock, checkout)
    debos = shutil.which("debos")
    if not debos or not Path(debos).resolve().is_file():
        raise PhoshBuildError("required host tool is missing: debos")
    plan = create_phosh_rootfs_build_plan(source_lock, contract)

    generic = checkout / contract.generic_artifact
    staged = checkout / contract.staged_artifact
    stage_recipe = checkout / _STAGE_RECIPE_NAME
    for candidate, label in ((generic, "generic Phosh rootfs artifact"), (staged, "staged Phosh rootfs artifact"), (stage_recipe, "generated Phosh stage recipe")):
        if candidate.exists() or candidate.is_symlink():
            raise PhoshBuildError(f"refusing stale/pre-existing {label}: {candidate}")
    if args.out.exists() or args.out.is_symlink():
        raise PhoshBuildError("refusing to overwrite Phosh rootfs output")
    if args.package_manifest.exists() or args.package_manifest.is_symlink():
        raise PhoshBuildError("refusing to overwrite Phosh package manifest")
    if args.build_evidence.exists() or args.build_evidence.is_symlink():
        raise PhoshBuildError("refusing to overwrite Phosh build evidence")
    if args.canonicalization_evidence is not None and (args.canonicalization_evidence.exists() or args.canonicalization_evidence.is_symlink()):
        raise PhoshBuildError("refusing to overwrite Phosh canonicalization evidence")

    recipe = render_family_supplement_recipe(source_lock, contract)
    if sha256(recipe).hexdigest() != plan.stage_recipe_sha256:
        raise PhoshBuildError("generated Phosh family-stage recipe is not deterministic")
    stage_recipe.write_bytes(recipe)
    try:
        _run(plan.base_argv, checkout, args.timeout, "locked NetHunter Pro Phosh base build")
        _require_fresh_artifact(generic, "generic Phosh rootfs artifact")
        _run(plan.stage_argv, checkout, args.timeout, "locked QCOM Phosh userspace supplement stage")
        _require_fresh_artifact(staged, "staged Phosh rootfs artifact")
    finally:
        try:
            if stage_recipe.is_file() and stage_recipe.read_bytes() == recipe:
                stage_recipe.unlink()
        except OSError:
            pass

    canonical = canonicalize_rootfs_archive(staged, args.out)
    package_manifest, package_count = package_manifest_from_rootfs(args.out)
    package_digest = sha256(package_manifest).hexdigest()
    package_evidence = evaluate_phosh_package_manifest(source_lock, package_manifest, rootfs_artifact_sha256=canonical.output_sha256)
    if not package_evidence.host_userspace_package_contract_satisfied:
        args.out.unlink(missing_ok=True)
        missing = ", ".join(package_evidence.missing_packages)
        raise PhoshBuildError(f"built rootfs is missing locked Phosh packages: {missing}")
    args.package_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.package_manifest.write_bytes(package_manifest)
    evidence = create_phosh_rootfs_build_evidence(plan, artifact_sha256=canonical.output_sha256, artifact_size=canonical.output_size, package_manifest_sha256=package_digest, package_count=package_count, phosh_package_contract_satisfied=True)
    evidence_sha = write_phosh_rootfs_build_evidence(evidence, args.build_evidence)
    if args.canonicalization_evidence is not None:
        canonical_sha = write_canonicalization_evidence(canonical, args.canonicalization_evidence)
        print(f"canonicalization_evidence_sha256={canonical_sha}")
    print(f"upstream_commit={source_lock.upstream_commit}")
    print(f"build_contract_sha256={contract.contract_sha256()}")
    print(f"build_plan_sha256={evidence.build_plan_sha256}")
    print(f"artifact_sha256={canonical.output_sha256}")
    print(f"artifact_size={canonical.output_size}")
    print(f"package_manifest_sha256={package_digest}")
    print(f"package_count={package_count}")
    print("phosh_package_contract_satisfied=true")
    print("reproducibility_authority=false")
    print("hardware_verified=false")
    print("beta_gate_credit=false")
    print(f"build_evidence_sha256={evidence_sha}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PhoshBuildError, PhoshError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
