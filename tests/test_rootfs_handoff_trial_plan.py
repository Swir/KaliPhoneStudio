from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import tempfile

from kaliphonestudio.rootfs_handoff_trial_plan import (
    RootfsHandoffTrialPlanError,
    build_rootfs_handoff_trial_plan,
    load_rootfs_handoff_trial_plan,
    write_rootfs_handoff_trial_plan,
)


class RootfsHandoffTrialPlanTests(TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.binding_digest = "1" * 64
        self.revalidation_digest = "2" * 64
        self.authorization_digest = "5" * 64
        self.rootfs_digest = "3" * 64
        self.recovery_digest = "4" * 64

        self.binding = SimpleNamespace(
            schema_version=1,
            profile_id="oneplus/avicii",
            device_serial="SERIAL-001",
            firmware_build="AC2003_11.F.19",
            firmware_fingerprint="oneplus/avicii/example",
            candidate_partition_role="userdata",
            observed_kernel_name="sda18",
            observed_filesystem="f2fs",
            required_free_bytes=12 * 1024 * 1024 * 1024,
            staging_subpath="kaliphonestudio/rootfs-stage",
            rootfs_artifact_sha256=self.rootfs_digest,
            rootfs_artifact_size=8 * 1024 * 1024 * 1024,
            recovery_plan_sha256=self.recovery_digest,
            evidence_sha256=lambda: self.binding_digest,
        )
        self.revalidation = SimpleNamespace(
            schema_version=1,
            target_binding_sha256=self.binding_digest,
            profile_id="oneplus/avicii",
            device_serial="SERIAL-001",
            firmware_build="AC2003_11.F.19",
            firmware_fingerprint="oneplus/avicii/example",
            candidate_partition_role="userdata",
            observed_kernel_name="sda18",
            observed_filesystem="f2fs",
            observed_encryption_state="unlocked",
            observed_free_bytes=28 * 1024 * 1024 * 1024,
            required_free_bytes=12 * 1024 * 1024 * 1024,
            staging_subpath="kaliphonestudio/rootfs-stage",
            rootfs_artifact_sha256=self.rootfs_digest,
            rootfs_artifact_size=8 * 1024 * 1024 * 1024,
            recovery_plan_sha256=self.recovery_digest,
            evidence_sha256=lambda: self.revalidation_digest,
        )
        self.authorization = SimpleNamespace(
            schema_version=1,
            profile_id="oneplus/avicii",
            device_serial="SERIAL-001",
            firmware_build="AC2003_11.F.19",
            firmware_fingerprint="oneplus/avicii/example",
            target_binding_sha256=self.binding_digest,
            fresh_revalidation_sha256=self.revalidation_digest,
            candidate_partition_role="userdata",
            observed_kernel_name="sda18",
            observed_filesystem="f2fs",
            observed_encryption_state="unlocked",
            observed_free_bytes=28 * 1024 * 1024 * 1024,
            required_free_bytes=12 * 1024 * 1024 * 1024,
            staging_subpath="kaliphonestudio/rootfs-stage",
            rootfs_artifact_sha256=self.rootfs_digest,
            rootfs_artifact_size=8 * 1024 * 1024 * 1024,
            recovery_plan_sha256=self.recovery_digest,
            manual_trial_authorization_accepted=True,
            ready_for_interactive_trial_execution_boundary=True,
            live_device_recheck_required_at_execution=True,
            explicit_operator_confirmation_required_at_execution=True,
            execution_boundary_required=True,
            physical_gate_still_incomplete=True,
            raw_device_path_bound=False,
            mount_target_bound=False,
            trial_execution_allowed=False,
            persistent_write_authorized=False,
            handoff_ready=False,
            persistent_write_performed=False,
            phone_storage_written=False,
            storage_verified=False,
            recovery_verified=False,
            hardware_verified=False,
            beta_release_authorized=False,
            beta_gate_credit=False,
            evidence_sha256=lambda: self.authorization_digest,
        )
        self.authorization_path = self.root / "authorization.json"
        self.binding_path = self.root / "binding.json"
        self.revalidation_path = self.root / "revalidation.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _patches(self):
        return (
            patch(
                "kaliphonestudio.rootfs_handoff_trial_plan.load_rootfs_handoff_trial_authorization_evidence",
                return_value=self.authorization,
            ),
            patch(
                "kaliphonestudio.rootfs_handoff_trial_plan.validate_rootfs_handoff_trial_authorization_evidence",
                return_value=None,
            ),
            patch(
                "kaliphonestudio.rootfs_handoff_trial_plan.load_rootfs_handoff_target_binding_evidence",
                return_value=self.binding,
            ),
            patch(
                "kaliphonestudio.rootfs_handoff_trial_plan.validate_rootfs_handoff_target_binding_evidence",
                return_value=None,
            ),
            patch(
                "kaliphonestudio.rootfs_handoff_trial_plan.load_rootfs_handoff_fresh_revalidation_evidence",
                return_value=self.revalidation,
            ),
            patch(
                "kaliphonestudio.rootfs_handoff_trial_plan.validate_rootfs_handoff_fresh_revalidation_evidence",
                return_value=None,
            ),
        )

    def _build(self):
        patches = self._patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            return build_rootfs_handoff_trial_plan(
                self.authorization_path,
                self.binding_path,
                self.revalidation_path,
            )

    def test_accepted_chain_builds_non_executing_plan(self) -> None:
        plan = self._build()
        self.assertTrue(plan.exact_authorization_chain_bound)
        self.assertTrue(plan.plan_ready_for_later_interactive_executor)
        self.assertTrue(plan.live_device_identity_recheck_required)
        self.assertTrue(plan.explicit_operator_confirmation_required)
        self.assertTrue(plan.write_scope_confirmation_required)
        self.assertFalse(plan.raw_device_path_bound)
        self.assertFalse(plan.mount_target_bound)
        self.assertFalse(plan.trial_execution_allowed)
        self.assertFalse(plan.persistent_write_authorized)
        self.assertFalse(plan.phone_storage_written)
        self.assertFalse(plan.hardware_verified)
        self.assertFalse(plan.beta_release_authorized)
        self.assertFalse(plan.beta_gate_credit)

    def test_rejected_authorization_fails_closed(self) -> None:
        self.authorization.manual_trial_authorization_accepted = False
        with self.assertRaisesRegex(RootfsHandoffTrialPlanError, "manual_trial_authorization_accepted"):
            self._build()

    def test_detached_authorization_fails_closed(self) -> None:
        self.authorization.target_binding_sha256 = "a" * 64
        with self.assertRaisesRegex(RootfsHandoffTrialPlanError, "detached"):
            self._build()

    def test_identity_drift_fails_closed(self) -> None:
        self.authorization.observed_filesystem = "ext4"
        with self.assertRaisesRegex(RootfsHandoffTrialPlanError, "filesystem drifted"):
            self._build()

    def test_authorization_that_grants_write_is_rejected(self) -> None:
        self.authorization.persistent_write_authorized = True
        with self.assertRaisesRegex(RootfsHandoffTrialPlanError, "persistent_write_authorized=false"):
            self._build()

    def test_plan_round_trip_is_canonical_and_create_only(self) -> None:
        plan = self._build()
        destination = self.root / "trial-plan.json"
        digest = write_rootfs_handoff_trial_plan(plan, destination)
        self.assertEqual(digest, plan.evidence_sha256())
        self.assertEqual(load_rootfs_handoff_trial_plan(destination), plan)
        with self.assertRaisesRegex(RootfsHandoffTrialPlanError, "refusing to overwrite"):
            write_rootfs_handoff_trial_plan(plan, destination)

    def test_symlink_plan_is_rejected_when_supported(self) -> None:
        plan = self._build()
        destination = self.root / "trial-plan.json"
        write_rootfs_handoff_trial_plan(plan, destination)
        link = self.root / "trial-plan-link.json"
        try:
            link.symlink_to(destination)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation is unavailable on this host")
        with self.assertRaisesRegex(RootfsHandoffTrialPlanError, "regular non-symlink"):
            load_rootfs_handoff_trial_plan(link)

    def test_tampered_plan_safety_flag_is_rejected(self) -> None:
        plan = replace(self._build(), trial_execution_allowed=True)
        destination = self.root / "tampered.json"
        destination.write_text(plan.canonical_json(), encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(RootfsHandoffTrialPlanError, "trial_execution_allowed=false"):
            load_rootfs_handoff_trial_plan(destination)
