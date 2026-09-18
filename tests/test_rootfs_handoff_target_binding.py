from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import tempfile

from kaliphonestudio.rootfs_handoff_target_binding import (
    RootfsHandoffTargetBindingError,
    bind_rootfs_handoff_target_binding_review,
    load_rootfs_handoff_target_binding_evidence,
    parse_rootfs_handoff_target_binding_review_record,
    prepare_rootfs_handoff_target_binding_review_record,
    write_rootfs_handoff_target_binding_evidence,
)


class RootfsHandoffTargetBindingTests(TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.discovery_digest = "1" * 64
        self.report_digest = "2" * 64
        self.strategy_digest = "3" * 64
        self.release_audit_digest = "4" * 64
        self.rootfs_digest = "5" * 64
        self.recovery_digest = "6" * 64
        self.report_size = 777

        self.discovery = SimpleNamespace(
            profile_id="oneplus/avicii",
            device_serial="SERIAL-001",
            firmware_build="AC2003_11.F.19",
            firmware_fingerprint="oneplus/avicii/example",
            partition_hint="userdata",
            forbidden_partitions=("boot", "recovery", "super", "metadata"),
            expected_filesystems=("f2fs",),
            discovery_report_sha256=self.report_digest,
            discovery_report_size=self.report_size,
            rootfs_artifact_sha256=self.rootfs_digest,
            rootfs_artifact_size=8 * 1024 * 1024 * 1024,
            recovery_plan_sha256=self.recovery_digest,
            target_selected=False,
            storage_path_bound=False,
            write_authorized=False,
            handoff_ready=False,
            storage_verified=False,
            recovery_verified=False,
            phone_storage_written=False,
            hardware_verified=False,
            beta_gate_credit=False,
            evidence_sha256=lambda: self.discovery_digest,
        )
        self.strategy = SimpleNamespace(
            profile_id="oneplus/avicii",
            device_serial="SERIAL-001",
            firmware_build="AC2003_11.F.19",
            firmware_fingerprint="oneplus/avicii/example",
            candidate_partition_role="userdata",
            staging_subpath="kaliphonestudio/rootfs-stage",
            required_free_bytes=12 * 1024 * 1024 * 1024,
            rootfs_artifact_sha256=self.rootfs_digest,
            rootfs_artifact_size=8 * 1024 * 1024 * 1024,
            recovery_plan_sha256=self.recovery_digest,
            physical_storage_discovery_sha256=self.discovery_digest,
            physical_release_gate_audit_sha256=self.release_audit_digest,
            strategy_design_accepted=True,
            review_checks_complete=True,
            manual_target_binding_required=True,
            physical_gate_still_incomplete=True,
            target_selected=False,
            storage_path_bound=False,
            trial_execution_allowed=False,
            write_authorized=False,
            handoff_ready=False,
            persistent_write_performed=False,
            phone_storage_written=False,
            hardware_verified=False,
            beta_release_authorized=False,
            beta_gate_credit=False,
            evidence_sha256=lambda: self.strategy_digest,
        )
        self.report = SimpleNamespace(
            profile_id="oneplus/avicii",
            device_serial="SERIAL-001",
            block_devices=(SimpleNamespace(kernel_name="sda18", size_sectors=460000000, removable=False),),
            filesystems=(
                SimpleNamespace(partition_role="userdata", kernel_name="sda18", filesystem="f2fs", observed=True),
            ),
            encryption=(
                SimpleNamespace(partition_role="userdata", state="unlocked", features=("fileencryption=ice",), observed=True),
            ),
            free_space=(
                SimpleNamespace(
                    partition_role="userdata",
                    total_bytes=220 * 1024 * 1024 * 1024,
                    free_bytes=32 * 1024 * 1024 * 1024,
                    observed=True,
                ),
            ),
        )

        self.discovery_path = self.root / "storage-discovery.json"
        self.report_path = self.root / "storage-report.json"
        self.strategy_path = self.root / "strategy-review.json"
        self.record_path = self.root / "target-review-record.json"
        self.notes_path = self.root / "target-review-notes.txt"
        self.notes_path.write_text("Reviewed exact physical target identity and no-write boundary.\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _patch_upstream(self):
        return (
            patch(
                "kaliphonestudio.rootfs_handoff_target_binding.load_physical_storage_discovery_evidence",
                return_value=self.discovery,
            ),
            patch(
                "kaliphonestudio.rootfs_handoff_target_binding.load_physical_storage_discovery_report",
                return_value=(self.report, self.report_digest, self.report_size),
            ),
            patch(
                "kaliphonestudio.rootfs_handoff_target_binding.load_rootfs_handoff_strategy_review_evidence",
                return_value=self.strategy,
            ),
        )

    def _record(self, *, accepted: bool = True):
        patches = self._patch_upstream()
        with patches[0], patches[1], patches[2]:
            record = prepare_rootfs_handoff_target_binding_review_record(
                self.discovery_path,
                self.report_path,
                self.strategy_path,
                "reviewer01",
            )
        if accepted:
            record = replace(
                record,
                decision="accepted_for_manual_trial",
                exact_physical_chain_reviewed=True,
                exact_discovery_report_reviewed=True,
                logical_partition_identity_reviewed=True,
                filesystem_identity_reviewed=True,
                encryption_unlock_state_reviewed=True,
                capacity_reviewed=True,
                recovery_plan_reviewed=True,
                staging_subpath_reviewed=True,
                no_raw_device_path_reviewed=True,
                no_write_authorization_reviewed=True,
            )
        self.record_path.write_text(record.canonical_json(), encoding="utf-8", newline="\n")
        return record

    def _bind(self):
        patches = self._patch_upstream()
        with patches[0], patches[1], patches[2]:
            return bind_rootfs_handoff_target_binding_review(
                self.discovery_path,
                self.report_path,
                self.strategy_path,
                self.record_path,
                self.notes_path,
            )

    def test_accepted_review_binds_only_logical_identity(self) -> None:
        self._record()
        evidence = self._bind()
        self.assertTrue(evidence.review_checks_complete)
        self.assertTrue(evidence.logical_target_identity_bound)
        self.assertTrue(evidence.fresh_device_revalidation_required)
        self.assertTrue(evidence.manual_trial_execution_required)
        self.assertTrue(evidence.physical_gate_still_incomplete)
        self.assertFalse(evidence.raw_device_path_bound)
        self.assertFalse(evidence.mount_target_bound)
        self.assertFalse(evidence.trial_execution_allowed)
        self.assertFalse(evidence.write_authorized)
        self.assertFalse(evidence.phone_storage_written)
        self.assertFalse(evidence.hardware_verified)
        self.assertFalse(evidence.beta_release_authorized)
        self.assertFalse(evidence.beta_gate_credit)

    def test_rejected_record_remains_non_bound_and_non_authorizing(self) -> None:
        self._record(accepted=False)
        evidence = self._bind()
        self.assertEqual(evidence.decision, "rejected")
        self.assertFalse(evidence.review_checks_complete)
        self.assertFalse(evidence.logical_target_identity_bound)
        self.assertFalse(evidence.trial_execution_allowed)
        self.assertFalse(evidence.write_authorized)

    def test_accepted_record_requires_every_explicit_review_check(self) -> None:
        record = self._record()
        record = replace(record, capacity_reviewed=False)
        self.record_path.write_text(record.canonical_json(), encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(RootfsHandoffTargetBindingError, "every explicit review check"):
            self._bind()

    def test_report_digest_drift_fails_closed(self) -> None:
        self._record()
        self.report_digest = "a" * 64
        with self.assertRaisesRegex(RootfsHandoffTargetBindingError, "report bytes differ"):
            self._bind()

    def test_locked_encryption_fails_before_target_binding(self) -> None:
        self.report.encryption = (
            SimpleNamespace(partition_role="userdata", state="locked", features=("fileencryption=ice",), observed=True),
        )
        patches = self._patch_upstream()
        with patches[0], patches[1], patches[2], self.assertRaisesRegex(
            RootfsHandoffTargetBindingError, "unlocked or unencrypted"
        ):
            prepare_rootfs_handoff_target_binding_review_record(
                self.discovery_path,
                self.report_path,
                self.strategy_path,
                "reviewer01",
            )

    def test_insufficient_free_space_fails_closed(self) -> None:
        self.report.free_space = (
            SimpleNamespace(
                partition_role="userdata",
                total_bytes=220 * 1024 * 1024 * 1024,
                free_bytes=4 * 1024 * 1024 * 1024,
                observed=True,
            ),
        )
        patches = self._patch_upstream()
        with patches[0], patches[1], patches[2], self.assertRaisesRegex(
            RootfsHandoffTargetBindingError, "below the reviewed strategy requirement"
        ):
            prepare_rootfs_handoff_target_binding_review_record(
                self.discovery_path,
                self.report_path,
                self.strategy_path,
                "reviewer01",
            )

    def test_removable_block_target_is_rejected(self) -> None:
        self.report.block_devices = (
            SimpleNamespace(kernel_name="sda18", size_sectors=460000000, removable=True),
        )
        patches = self._patch_upstream()
        with patches[0], patches[1], patches[2], self.assertRaisesRegex(
            RootfsHandoffTargetBindingError, "must not resolve to removable storage"
        ):
            prepare_rootfs_handoff_target_binding_review_record(
                self.discovery_path,
                self.report_path,
                self.strategy_path,
                "reviewer01",
            )

    def test_record_identity_drift_fails_closed(self) -> None:
        record = self._record()
        record = replace(record, observed_kernel_name="sda17")
        self.record_path.write_text(record.canonical_json(), encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(RootfsHandoffTargetBindingError, "observed_kernel_name"):
            self._bind()

    def test_parser_rejects_raw_or_absolute_staging_paths(self) -> None:
        record = self._record(accepted=False)
        raw = {
            **record.__dict__,
            "staging_subpath": "/dev/block/sda18",
        }
        with self.assertRaisesRegex(RootfsHandoffTargetBindingError, "absolute/raw device path"):
            parse_rootfs_handoff_target_binding_review_record(raw)

    def test_evidence_round_trip_is_canonical_and_refuses_overwrite(self) -> None:
        self._record()
        evidence = self._bind()
        destination = self.root / "target-binding.json"
        digest = write_rootfs_handoff_target_binding_evidence(evidence, destination)
        self.assertEqual(digest, evidence.evidence_sha256())
        self.assertEqual(load_rootfs_handoff_target_binding_evidence(destination), evidence)
        with self.assertRaisesRegex(RootfsHandoffTargetBindingError, "refusing to overwrite"):
            write_rootfs_handoff_target_binding_evidence(evidence, destination)
