from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import tempfile

from kaliphonestudio.rootfs_handoff_trial_authorization import (
    RootfsHandoffTrialAuthorizationError,
    bind_rootfs_handoff_trial_authorization_review,
    load_rootfs_handoff_trial_authorization_evidence,
    prepare_rootfs_handoff_trial_authorization_review_record,
    write_rootfs_handoff_trial_authorization_evidence,
)


class RootfsHandoffTrialAuthorizationTests(TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.binding_digest = "1" * 64
        self.revalidation_digest = "2" * 64
        self.rootfs_digest = "3" * 64
        self.recovery_digest = "4" * 64

        self.binding = SimpleNamespace(
            schema_version=1,
            decision="accepted_for_manual_trial",
            logical_target_identity_bound=True,
            profile_id="oneplus/avicii",
            device_serial="SERIAL-001",
            firmware_build="AC2003_11.F.19",
            firmware_fingerprint="oneplus/avicii/example",
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
            evidence_sha256=lambda: self.binding_digest,
        )
        self.revalidation = SimpleNamespace(
            schema_version=1,
            fresh_device_revalidated=True,
            ready_for_separate_manual_trial_authorization=True,
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
            raw_device_path_bound=False,
            mount_target_bound=False,
            trial_execution_allowed=False,
            write_authorized=False,
            handoff_ready=False,
            persistent_write_performed=False,
            phone_storage_written=False,
            storage_verified=False,
            recovery_verified=False,
            hardware_verified=False,
            beta_release_authorized=False,
            beta_gate_credit=False,
            evidence_sha256=lambda: self.revalidation_digest,
        )
        self.binding_path = self.root / "target-binding.json"
        self.revalidation_path = self.root / "fresh-revalidation.json"
        self.record_path = self.root / "trial-auth-review.json"
        self.notes_path = self.root / "trial-auth-notes.txt"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _patches(self):
        return (
            patch(
                "kaliphonestudio.rootfs_handoff_trial_authorization.load_rootfs_handoff_target_binding_evidence",
                return_value=self.binding,
            ),
            patch(
                "kaliphonestudio.rootfs_handoff_trial_authorization.validate_rootfs_handoff_target_binding_evidence",
                return_value=None,
            ),
            patch(
                "kaliphonestudio.rootfs_handoff_trial_authorization.load_rootfs_handoff_fresh_revalidation_evidence",
                return_value=self.revalidation,
            ),
            patch(
                "kaliphonestudio.rootfs_handoff_trial_authorization.validate_rootfs_handoff_fresh_revalidation_evidence",
                return_value=None,
            ),
        )

    def _template(self):
        patches = self._patches()
        with patches[0], patches[1], patches[2], patches[3]:
            return prepare_rootfs_handoff_trial_authorization_review_record(
                self.binding_path,
                self.revalidation_path,
                "reviewer-1",
            )

    def _accepted_record(self):
        record = self._template()
        flags = {
            "exact_target_binding_reviewed": True,
            "exact_fresh_revalidation_reviewed": True,
            "logical_identity_reviewed": True,
            "filesystem_encryption_capacity_reviewed": True,
            "rootfs_identity_reviewed": True,
            "recovery_plan_reviewed": True,
            "staging_subpath_reviewed": True,
            "rollback_limitations_reviewed": True,
            "explicit_operator_interaction_reviewed": True,
            "no_automatic_execution_reviewed": True,
            "no_raw_path_in_evidence_reviewed": True,
            "no_persistent_write_authorization_reviewed": True,
        }
        return replace(
            record,
            decision="accepted_for_interactive_execution_boundary",
            **flags,
        )

    def _write_review(self, record) -> None:
        self.record_path.write_text(record.canonical_json(), encoding="utf-8", newline="\n")
        self.notes_path.write_text(
            "Reviewed exact fresh target identity, rollback limits and interactive-only execution boundary.\n",
            encoding="utf-8",
            newline="\n",
        )

    def _bind(self):
        patches = self._patches()
        with patches[0], patches[1], patches[2], patches[3]:
            return bind_rootfs_handoff_trial_authorization_review(
                self.binding_path,
                self.revalidation_path,
                self.record_path,
                self.notes_path,
            )

    def test_template_is_rejected_and_non_executing(self) -> None:
        record = self._template()
        self.assertEqual(record.decision, "rejected")
        self.assertFalse(record.trial_execution_allowed)
        self.assertFalse(record.persistent_write_authorized)
        self.assertFalse(record.raw_device_path_bound)
        self.assertFalse(record.mount_target_bound)

    def test_accepted_review_only_opens_later_interactive_execution_boundary(self) -> None:
        self._write_review(self._accepted_record())
        evidence = self._bind()
        self.assertTrue(evidence.review_checks_complete)
        self.assertTrue(evidence.manual_trial_authorization_accepted)
        self.assertTrue(evidence.ready_for_interactive_trial_execution_boundary)
        self.assertTrue(evidence.live_device_recheck_required_at_execution)
        self.assertTrue(evidence.explicit_operator_confirmation_required_at_execution)
        self.assertTrue(evidence.execution_boundary_required)
        self.assertFalse(evidence.raw_device_path_bound)
        self.assertFalse(evidence.mount_target_bound)
        self.assertFalse(evidence.trial_execution_allowed)
        self.assertFalse(evidence.persistent_write_authorized)
        self.assertFalse(evidence.phone_storage_written)
        self.assertFalse(evidence.hardware_verified)
        self.assertFalse(evidence.beta_release_authorized)
        self.assertFalse(evidence.beta_gate_credit)

    def test_accepted_decision_with_missing_review_check_fails_closed(self) -> None:
        record = replace(
            self._accepted_record(),
            rollback_limitations_reviewed=False,
        )
        self._write_review(record)
        with self.assertRaisesRegex(RootfsHandoffTrialAuthorizationError, "every review check"):
            self._bind()

    def test_detached_fresh_revalidation_is_rejected(self) -> None:
        self.revalidation.target_binding_sha256 = "a" * 64
        with self.assertRaisesRegex(RootfsHandoffTrialAuthorizationError, "detached"):
            self._template()

    def test_identity_drift_is_rejected(self) -> None:
        self.revalidation.observed_filesystem = "ext4"
        with self.assertRaisesRegex(RootfsHandoffTrialAuthorizationError, "filesystem drifted"):
            self._template()

    def test_invalid_fresh_capacity_is_rejected(self) -> None:
        self.revalidation.observed_free_bytes = 4 * 1024 * 1024 * 1024
        with self.assertRaisesRegex(RootfsHandoffTrialAuthorizationError, "capacity"):
            self._template()

    def test_record_drift_from_exact_chain_is_rejected(self) -> None:
        record = replace(self._accepted_record(), staging_subpath="other/stage")
        self._write_review(record)
        with self.assertRaisesRegex(RootfsHandoffTrialAuthorizationError, "staging_subpath drifted"):
            self._bind()

    def test_evidence_round_trip_is_canonical_and_create_only(self) -> None:
        self._write_review(self._accepted_record())
        evidence = self._bind()
        destination = self.root / "trial-authorization.json"
        digest = write_rootfs_handoff_trial_authorization_evidence(evidence, destination)
        self.assertEqual(digest, evidence.evidence_sha256())
        self.assertEqual(load_rootfs_handoff_trial_authorization_evidence(destination), evidence)
        with self.assertRaisesRegex(RootfsHandoffTrialAuthorizationError, "refusing to overwrite"):
            write_rootfs_handoff_trial_authorization_evidence(evidence, destination)
