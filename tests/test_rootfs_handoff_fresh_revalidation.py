from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import tempfile

from kaliphonestudio.rootfs_handoff_fresh_revalidation import (
    RootfsHandoffFreshRevalidationError,
    build_rootfs_handoff_fresh_revalidation,
    load_rootfs_handoff_fresh_revalidation_evidence,
    write_rootfs_handoff_fresh_revalidation_evidence,
)


class RootfsHandoffFreshRevalidationTests(TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.old_discovery_digest = "1" * 64
        self.fresh_discovery_digest = "2" * 64
        self.report_digest = "3" * 64
        self.binding_digest = "4" * 64
        self.rootfs_digest = "5" * 64
        self.recovery_digest = "6" * 64
        self.report_size = 1234

        self.binding = SimpleNamespace(
            schema_version=1,
            decision="accepted_for_manual_trial",
            review_checks_complete=True,
            logical_target_identity_bound=True,
            fresh_device_revalidation_required=True,
            manual_trial_execution_required=True,
            profile_id="oneplus/avicii",
            device_serial="SERIAL-001",
            firmware_build="AC2003_11.F.19",
            firmware_fingerprint="oneplus/avicii/example",
            physical_storage_discovery_sha256=self.old_discovery_digest,
            candidate_partition_role="userdata",
            observed_kernel_name="sda18",
            observed_filesystem="f2fs",
            observed_encryption_state="unlocked",
            observed_free_bytes=32 * 1024 * 1024 * 1024,
            required_free_bytes=12 * 1024 * 1024 * 1024,
            staging_subpath="kaliphonestudio/rootfs-stage",
            rootfs_artifact_sha256=self.rootfs_digest,
            rootfs_artifact_size=8 * 1024 * 1024 * 1024,
            recovery_plan_sha256=self.recovery_digest,
            raw_device_path_bound=False,
            mount_target_bound=False,
            trial_execution_allowed=False,
            write_authorized=False,
            handoff_ready=False,
            persistent_write_performed=False,
            phone_storage_written=False,
            hardware_verified=False,
            beta_release_authorized=False,
            beta_gate_credit=False,
            evidence_sha256=lambda: self.binding_digest,
        )
        self.discovery = SimpleNamespace(
            profile_id="oneplus/avicii",
            device_serial="SERIAL-001",
            firmware_build="AC2003_11.F.19",
            firmware_fingerprint="oneplus/avicii/example",
            partition_hint="userdata",
            forbidden_partitions=("boot", "recovery", "super", "metadata"),
            discovery_report_sha256=self.report_digest,
            discovery_report_size=self.report_size,
            rootfs_artifact_sha256=self.rootfs_digest,
            rootfs_artifact_size=8 * 1024 * 1024 * 1024,
            recovery_plan_sha256=self.recovery_digest,
            discovery_ready_for_manual_review=True,
            target_selected=False,
            storage_path_bound=False,
            write_authorized=False,
            handoff_ready=False,
            storage_verified=False,
            recovery_verified=False,
            phone_storage_written=False,
            hardware_verified=False,
            beta_gate_credit=False,
            evidence_sha256=lambda: self.fresh_discovery_digest,
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
                    free_bytes=28 * 1024 * 1024 * 1024,
                    observed=True,
                ),
            ),
        )

        self.binding_path = self.root / "target-binding.json"
        self.discovery_path = self.root / "fresh-storage-discovery.json"
        self.report_path = self.root / "fresh-storage-report.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _patches(self):
        return (
            patch(
                "kaliphonestudio.rootfs_handoff_fresh_revalidation.load_rootfs_handoff_target_binding_evidence",
                return_value=self.binding,
            ),
            patch(
                "kaliphonestudio.rootfs_handoff_fresh_revalidation.validate_rootfs_handoff_target_binding_evidence",
                return_value=None,
            ),
            patch(
                "kaliphonestudio.rootfs_handoff_fresh_revalidation.load_physical_storage_discovery_evidence",
                return_value=self.discovery,
            ),
            patch(
                "kaliphonestudio.rootfs_handoff_fresh_revalidation.load_physical_storage_discovery_report",
                return_value=(self.report, self.report_digest, self.report_size),
            ),
        )

    def _build(self):
        patches = self._patches()
        with patches[0], patches[1], patches[2], patches[3]:
            return build_rootfs_handoff_fresh_revalidation(
                self.binding_path,
                self.discovery_path,
                self.report_path,
            )

    def test_success_revalidates_without_authorizing_trial_or_write(self) -> None:
        evidence = self._build()
        self.assertTrue(evidence.fresh_capture_chain_distinct)
        self.assertTrue(evidence.exact_logical_identity_matches)
        self.assertTrue(evidence.fresh_device_revalidated)
        self.assertTrue(evidence.ready_for_separate_manual_trial_authorization)
        self.assertTrue(evidence.manual_trial_authorization_required)
        self.assertFalse(evidence.raw_device_path_bound)
        self.assertFalse(evidence.mount_target_bound)
        self.assertFalse(evidence.trial_execution_allowed)
        self.assertFalse(evidence.write_authorized)
        self.assertFalse(evidence.phone_storage_written)
        self.assertFalse(evidence.hardware_verified)
        self.assertFalse(evidence.beta_release_authorized)
        self.assertFalse(evidence.beta_gate_credit)

    def test_original_discovery_reuse_is_rejected(self) -> None:
        self.fresh_discovery_digest = self.old_discovery_digest
        with self.assertRaisesRegex(RootfsHandoffFreshRevalidationError, "distinct physical storage discovery"):
            self._build()

    def test_firmware_drift_is_rejected(self) -> None:
        self.discovery.firmware_build = "AC2003_11.F.20"
        with self.assertRaisesRegex(RootfsHandoffFreshRevalidationError, "firmware build drifted"):
            self._build()

    def test_report_digest_drift_is_rejected(self) -> None:
        self.discovery.discovery_report_sha256 = "a" * 64
        with self.assertRaisesRegex(RootfsHandoffFreshRevalidationError, "detached from supplied report"):
            self._build()

    def test_kernel_identity_drift_is_rejected(self) -> None:
        self.report.filesystems = (
            SimpleNamespace(partition_role="userdata", kernel_name="sda19", filesystem="f2fs", observed=True),
        )
        self.report.block_devices = (
            SimpleNamespace(kernel_name="sda19", size_sectors=460000000, removable=False),
        )
        with self.assertRaisesRegex(RootfsHandoffFreshRevalidationError, "kernel identity drifted"):
            self._build()

    def test_locked_target_is_rejected(self) -> None:
        self.report.encryption = (
            SimpleNamespace(partition_role="userdata", state="locked", features=("fileencryption=ice",), observed=True),
        )
        with self.assertRaisesRegex(RootfsHandoffFreshRevalidationError, "encryption state drifted"):
            self._build()

    def test_insufficient_fresh_capacity_is_rejected(self) -> None:
        self.report.free_space = (
            SimpleNamespace(
                partition_role="userdata",
                total_bytes=220 * 1024 * 1024 * 1024,
                free_bytes=4 * 1024 * 1024 * 1024,
                observed=True,
            ),
        )
        with self.assertRaisesRegex(RootfsHandoffFreshRevalidationError, "below the accepted trial requirement"):
            self._build()

    def test_removable_target_is_rejected(self) -> None:
        self.report.block_devices = (
            SimpleNamespace(kernel_name="sda18", size_sectors=460000000, removable=True),
        )
        with self.assertRaisesRegex(RootfsHandoffFreshRevalidationError, "must not resolve to removable"):
            self._build()

    def test_evidence_round_trip_is_canonical_and_create_only(self) -> None:
        evidence = self._build()
        destination = self.root / "fresh-revalidation.json"
        digest = write_rootfs_handoff_fresh_revalidation_evidence(evidence, destination)
        self.assertEqual(digest, evidence.evidence_sha256())
        self.assertEqual(load_rootfs_handoff_fresh_revalidation_evidence(destination), evidence)
        with self.assertRaisesRegex(RootfsHandoffFreshRevalidationError, "refusing to overwrite"):
            write_rootfs_handoff_fresh_revalidation_evidence(evidence, destination)
