#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from kaliphonestudio.physical_bringup_dossier import load_physical_bringup_dossier_evidence
from kaliphonestudio.physical_bringup_dossier_review import (
    PhysicalBringupDossierReviewRecord,
    parse_physical_bringup_dossier_review_record,
)


def _write_new(path: Path, text: str) -> None:
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise ValueError(f"refusing to overwrite review template output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists() or temporary.is_symlink():
        raise ValueError(f"refusing stale review template temporary path: {temporary}")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a fail-closed physical dossier review template. "
            "The generated decision is rejected and every review check is false."
        )
    )
    parser.add_argument("--dossier", type=Path, required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--record-out", type=Path, required=True)
    parser.add_argument("--notes-out", type=Path, required=True)
    args = parser.parse_args()

    try:
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
        # Reparse the canonical representation so reviewer and policy constraints
        # are enforced before any template is written.
        import json
        parse_physical_bringup_dossier_review_record(json.loads(record.canonical_json()))
        notes = (
            "Physical bring-up dossier review notes\n"
            f"profile_id: {dossier.profile_id}\n"
            f"device_serial: {dossier.device_serial}\n"
            f"firmware_build: {dossier.firmware_build}\n\n"
            "Keep decision=rejected until every review check in the JSON record has been independently verified.\n"
            "Acceptance is only for a later separate strategy review; it does not select a target or authorize writes.\n"
        )
        _write_new(args.record_out, record.canonical_json())
        _write_new(args.notes_out, notes)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))

    print(f"review record template: {args.record_out}")
    print(f"review notes template: {args.notes_out}")
    print("decision=rejected target_selected=false write_authorized=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
