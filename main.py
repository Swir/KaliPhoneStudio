from __future__ import annotations

import sys
from typing import Sequence

from kaliphonestudio.app import main as app_main
from kaliphonestudio.exact_bound_temporary_boot_operator import (
    execute_temporary_boot_once_main,
    prepare_temporary_boot_offer_main,
)
from kaliphonestudio.operator_evidence_workspace import main as operator_evidence_main
from kaliphonestudio.physical_candidate_operator import bind_physical_candidate_main
from kaliphonestudio.physical_fastboot_capture import main as physical_capture_main
from kaliphonestudio.profile_registry_audit import main as profile_registry_audit_main
from kaliphonestudio.stock_baseline_ingress import (
    bind_physical_stock_main,
    prepare_stock_provenance_main,
)

PHYSICAL_FASTBOOT_CAPTURE_COMMAND = "capture-fastboot-baseline"
PREPARE_STOCK_PROVENANCE_COMMAND = "prepare-stock-provenance"
BIND_PHYSICAL_STOCK_BASELINE_COMMAND = "bind-physical-stock-baseline"
BIND_PHYSICAL_CANDIDATE_COMMAND = "bind-physical-candidate-gate"
PREPARE_TEMPORARY_BOOT_OFFER_COMMAND = "prepare-temporary-boot-offer"
EXECUTE_TEMPORARY_BOOT_ONCE_COMMAND = "execute-temporary-boot-once"
EVIDENCE_WORKSPACE_COMMAND = "evidence"
PROFILE_REGISTRY_AUDIT_COMMAND = "audit-profile-registry"


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == PHYSICAL_FASTBOOT_CAPTURE_COMMAND:
        return physical_capture_main(args[1:])
    if args and args[0] == PREPARE_STOCK_PROVENANCE_COMMAND:
        return prepare_stock_provenance_main(args[1:])
    if args and args[0] == BIND_PHYSICAL_STOCK_BASELINE_COMMAND:
        return bind_physical_stock_main(args[1:])
    if args and args[0] == BIND_PHYSICAL_CANDIDATE_COMMAND:
        return bind_physical_candidate_main(args[1:])
    if args and args[0] == PREPARE_TEMPORARY_BOOT_OFFER_COMMAND:
        return prepare_temporary_boot_offer_main(args[1:])
    if args and args[0] == EXECUTE_TEMPORARY_BOOT_ONCE_COMMAND:
        return execute_temporary_boot_once_main(args[1:])
    if args and args[0] == EVIDENCE_WORKSPACE_COMMAND:
        return operator_evidence_main(args[1:])
    if args and args[0] == PROFILE_REGISTRY_AUDIT_COMMAND:
        return profile_registry_audit_main(args[1:])
    return app_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
