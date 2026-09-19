from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from unittest import TestCase
import tempfile

from kaliphonestudio.rootfs_handoff_trial_plan import (
    RootfsHandoffTrialPlan,
    write_rootfs_handoff_trial_plan,
)
from kaliphonestudio.rootfs_handoff_trial_preflight import (
    RootfsHandoffTrialPreflightError,
    build_rootfs_handoff_trial_preflight,
    load_rootfs_handoff_trial_preflight_evidence,
    write_rootfs_handoff_trial_preflight_evidence,
)


class RootfsHandoffTrialPreflightTests(TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.rootfs_bytes = (b"kali-rootfs-preflight\n" * 4096) + b"EOF\n"
        self.rootfs_path = self.root / "kali-rootfs.tar.xz"
        self.rootfs_path.write_bytes(self.rootfs_bytes)
        self.rootfs_sha = sha256(self.rootfs_bytes).hexdigest()
        self.plan = RootfsHandoffTrialPlan(
            schema_version=1,
            plan_policy="rootfs-handoff-interactive-trial-plan-v1",
            profile_id="oneplus/avicii",
            device_serial="SERIAL-001",
            firmware_build="AC2003_11.F.19",
            firmware_fingerprint="oneplus/avicii/example",
            trial_authorization_sha256="1" * 64,
            target_binding_sha256="2" * 64,
            fresh_revalidation_sha256="3" * 64,
            candidate_partition_role="userdata",
            observed_kernel_name="sda18",
            observed_filesystem="f2fs",
            observed_encryption_state="unlocked",
            observed_free_bytes=32 * 1024 * 1024 * 1024,
            required_free_bytes=12 * 1024 * 1024 * 1024,
            staging_subpath="kaliphonestudio/rootfs-stage",
            rootfs_artifact_sha256=self.rootfs_sha,
            rootfs_artifact_size=len(self.rootfs_bytes),
            recovery_plan_sha256="4" * 64,
            exact_authorization_chain_bound=True,
            live_device_identity_recheck_required=True,
            live_firmware_recheck_required=True,
            live_target_identity_recheck_required=True,
            live_filesystem_encryption_capacity_recheck_required=True,
            rootfs_local_hash_recheck_required=True,
            recovery_readiness_recheck_required=True,
            explicit_operator_confirmation_required=True,
            write_scope_confirmation_required=True,
            plan_ready_for_later_interactive_executor=True,
            physical_gate_still_incomplete=True,
            raw_device_path_bound=False,
            mount_target_bound=False,
            trial_execution_allowed=False,
            persistent_write_authorized=False,
            persistent_write_performed=False,
            phone_storage_written=False,
            storage_verified=False,
            recovery_verified=False,
            hardware_verified=False,
            beta_release_authorized=False,
            beta_gate_credit=False,
        )
        self.plan_path = self.root / "trial-plan.json"
        write_rootfs_handoff_trial_plan(self.plan, self.plan_path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_exact_local_rootfs_builds_non_executing_preflight(self) -> None:
        evidence = build_rootfs_handoff_trial_preflight(self.plan_path, self.rootfs_path)
        self.assertEqual(evidence.trial_plan_sha256, self.plan.evidence_sha256())
        self.assertEqual(evidence.rootfs_artifact_sha256, self.rootfs_sha)
        self.assertEqual(evidence.rootfs_artifact_size, len(self.rootfs_bytes))
        self.assertTrue(evidence.local_rootfs_exact_bytes_verified)
        self.assertTrue(evidence.live_device_identity_recheck_required)
        self.assertTrue(evidence.recovery_readiness_recheck_required)
        self.assertTrue(evidence.interactive_executor_still_required)
        self.assertFalse(evidence.physical_interaction_performed)
        self.assertFalse(evidence.external_device_command_executed)
        self.assertFalse(evidence.raw_device_path_bound)
        self.assertFalse(evidence.mount_target_bound)
        self.assertFalse(evidence.trial_execution_allowed)
        self.assertFalse(evidence.persistent_write_authorized)
        self.assertFalse(evidence.phone_storage_written)
        self.assertFalse(evidence.hardware_verified)
        self.assertFalse(evidence.beta_release_authorized)
        self.assertFalse(evidence.beta_gate_credit)

    def test_wrong_local_rootfs_size_fails_closed(self) -> None:
        self.rootfs_path.write_bytes(self.rootfs_bytes + b"drift")
        with self.assertRaisesRegex(RootfsHandoffTrialPreflightError, "size differs"):
            build_rootfs_handoff_trial_preflight(self.plan_path, self.rootfs_path)

    def test_wrong_local_rootfs_hash_fails_closed(self) -> None:
        changed = bytearray(self.rootfs_bytes)
        changed[-1] ^= 1
        self.rootfs_path.write_bytes(bytes(changed))
        with self.assertRaisesRegex(RootfsHandoffTrialPreflightError, "SHA-256 differs"):
            build_rootfs_handoff_trial_preflight(self.plan_path, self.rootfs_path)

    def test_plan_that_grants_execution_is_rejected(self) -> None:
        unsafe = replace(self.plan, trial_execution_allowed=True)
        unsafe_path = self.root / "unsafe-plan.json"
        unsafe_path.write_text(unsafe.canonical_json(), encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(RootfsHandoffTrialPreflightError, "trial_execution_allowed=false"):
            build_rootfs_handoff_trial_preflight(unsafe_path, self.rootfs_path)

    def test_preflight_round_trip_is_canonical_and_create_only(self) -> None:
        evidence = build_rootfs_handoff_trial_preflight(self.plan_path, self.rootfs_path)
        destination = self.root / "preflight.json"
        digest = write_rootfs_handoff_trial_preflight_evidence(evidence, destination)
        self.assertEqual(digest, evidence.evidence_sha256())
        self.assertEqual(load_rootfs_handoff_trial_preflight_evidence(destination), evidence)
        with self.assertRaisesRegex(RootfsHandoffTrialPreflightError, "refusing to overwrite"):
            write_rootfs_handoff_trial_preflight_evidence(evidence, destination)

    def test_tampered_preflight_write_flag_is_rejected(self) -> None:
        evidence = replace(
            build_rootfs_handoff_trial_preflight(self.plan_path, self.rootfs_path),
            persistent_write_authorized=True,
        )
        destination = self.root / "tampered-preflight.json"
        destination.write_text(evidence.canonical_json(), encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(RootfsHandoffTrialPreflightError, "persistent_write_authorized=false"):
            load_rootfs_handoff_trial_preflight_evidence(destination)

    def test_symlink_rootfs_is_rejected_when_supported(self) -> None:
        link = self.root / "rootfs-link.tar.xz"
        try:
            link.symlink_to(self.rootfs_path)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation is unavailable on this host")
        with self.assertRaisesRegex(RootfsHandoffTrialPreflightError, "regular non-symlink"):
            build_rootfs_handoff_trial_preflight(self.plan_path, link)
