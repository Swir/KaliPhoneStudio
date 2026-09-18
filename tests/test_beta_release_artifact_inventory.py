from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import tempfile

from kaliphonestudio.beta_release_artifact_inventory import (
    BetaReleaseArtifactInventoryError,
    build_beta_release_artifact_inventory,
    load_beta_release_artifact_inventory,
    write_beta_release_artifact_inventory,
)


class _Evidence(SimpleNamespace):
    def evidence_sha256(self) -> str:
        return self._digest


class BetaReleaseArtifactInventoryTests(TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.commit = "a" * 40
        self.boot_bytes = b"reviewed-candidate-boot-image\n"
        self.rootfs_bytes = b"reviewed-kali-rootfs\n"
        self.boot_sha = sha256(self.boot_bytes).hexdigest()
        self.rootfs_sha = sha256(self.rootfs_bytes).hexdigest()

        self.candidate = _Evidence(
            _digest="1" * 64,
            profile_id="vendor/device",
            device_serial="SERIAL-001",
            firmware_build="firmware-build",
            firmware_fingerprint="firmware/fingerprint",
            boot_image_sha256=self.boot_sha,
            boot_image_size=len(self.boot_bytes),
            rootfs_artifact_sha256=self.rootfs_sha,
            kernel_image_sha256="2" * 64,
            dtb_sha256=None,
            dtbo_image_sha256=None,
        )
        self.audit = _Evidence(
            _digest="3" * 64,
            profile_id=self.candidate.profile_id,
            device_serial=self.candidate.device_serial,
            firmware_build=self.candidate.firmware_build,
            firmware_fingerprint=self.candidate.firmware_fingerprint,
            beta_required_tests_all_reviewed_pass=True,
            kali_early_userspace_signal_present=True,
        )
        self.strategy = _Evidence(
            _digest="4" * 64,
            profile_id=self.candidate.profile_id,
            device_serial=self.candidate.device_serial,
            firmware_build=self.candidate.firmware_build,
            firmware_fingerprint=self.candidate.firmware_fingerprint,
            physical_release_gate_audit_sha256=self.audit.evidence_sha256(),
            strategy_design_accepted=True,
            review_checks_complete=True,
            rootfs_artifact_sha256=self.rootfs_sha,
            rootfs_artifact_size=len(self.rootfs_bytes),
        )
        self.artifacts = self._write_required_artifacts()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write(self, name: str, data: bytes) -> Path:
        path = self.root / name
        path.write_bytes(data)
        return path

    def _write_required_artifacts(self) -> dict[str, Path]:
        return {
            "candidate_boot": self._write("candidate-boot.img", self.boot_bytes),
            "kali_rootfs": self._write("kali-rootfs.tar.zst", self.rootfs_bytes),
            "operator_instructions": self._write("INSTALL.txt", b"operator instructions\n"),
            "compatibility_matrix": self._write("COMPATIBILITY.json", b"{}\n"),
            "known_issues": self._write("KNOWN_ISSUES.txt", b"known issues\n"),
        }

    def _patch_sources(self):
        return (
            patch(
                "kaliphonestudio.beta_release_artifact_inventory._load_candidate_gate",
                return_value=(self.candidate, "5" * 64, 1),
            ),
            patch(
                "kaliphonestudio.beta_release_artifact_inventory.load_physical_release_gate_audit_evidence",
                return_value=self.audit,
            ),
            patch(
                "kaliphonestudio.beta_release_artifact_inventory.load_rootfs_handoff_strategy_review_evidence",
                return_value=self.strategy,
            ),
        )

    def _build(self, artifacts: dict[str, Path] | None = None):
        candidate_patch, audit_patch, strategy_patch = self._patch_sources()
        with candidate_patch, audit_patch, strategy_patch:
            return build_beta_release_artifact_inventory(
                self.root / "candidate.json",
                self.root / "audit.json",
                self.root / "strategy.json",
                self.commit,
                self.artifacts if artifacts is None else artifacts,
            )

    def test_builds_exact_non_authorizing_inventory(self) -> None:
        evidence = self._build()
        self.assertTrue(evidence.exact_files_verified)
        self.assertTrue(evidence.required_artifacts_present)
        self.assertTrue(evidence.ready_for_final_manual_release_review)
        self.assertTrue(evidence.manual_release_gate_review_required)
        self.assertFalse(evidence.release_publication_allowed)
        self.assertFalse(evidence.beta_release_authorized)
        self.assertFalse(evidence.hardware_verified)
        self.assertFalse(evidence.beta_gate_credit)
        self.assertEqual(
            [item.role for item in evidence.artifacts],
            sorted(self.artifacts),
        )

    def test_round_trip_is_canonical_and_immutable(self) -> None:
        evidence = self._build()
        destination = self.root / "inventory.json"
        digest = write_beta_release_artifact_inventory(evidence, destination)
        self.assertEqual(digest, evidence.evidence_sha256())
        loaded = load_beta_release_artifact_inventory(destination)
        self.assertEqual(loaded, evidence)
        with self.assertRaises(BetaReleaseArtifactInventoryError):
            write_beta_release_artifact_inventory(evidence, destination)

    def test_missing_required_role_fails_closed(self) -> None:
        artifacts = dict(self.artifacts)
        artifacts.pop("known_issues")
        with self.assertRaisesRegex(BetaReleaseArtifactInventoryError, "missing required roles"):
            self._build(artifacts)

    def test_candidate_boot_digest_mismatch_fails_closed(self) -> None:
        self.artifacts["candidate_boot"].write_bytes(b"changed boot\n")
        with self.assertRaisesRegex(BetaReleaseArtifactInventoryError, "candidate boot artifact differs"):
            self._build()

    def test_rootfs_digest_mismatch_fails_closed(self) -> None:
        self.artifacts["kali_rootfs"].write_bytes(b"changed rootfs\n")
        with self.assertRaisesRegex(BetaReleaseArtifactInventoryError, "Kali rootfs artifact digest differs"):
            self._build()

    def test_identity_drift_fails_closed(self) -> None:
        self.strategy.device_serial = "OTHER-SERIAL"
        with self.assertRaisesRegex(BetaReleaseArtifactInventoryError, "physical identity drifted"):
            self._build()

    def test_detached_strategy_audit_fails_closed(self) -> None:
        self.strategy.physical_release_gate_audit_sha256 = "f" * 64
        with self.assertRaisesRegex(BetaReleaseArtifactInventoryError, "detached from exact release-gate audit"):
            self._build()

    def test_unaccepted_strategy_fails_closed(self) -> None:
        self.strategy.strategy_design_accepted = False
        with self.assertRaisesRegex(BetaReleaseArtifactInventoryError, "accepted exact rootfs strategy"):
            self._build()

    def test_incomplete_beta_functional_coverage_fails_closed(self) -> None:
        self.audit.beta_required_tests_all_reviewed_pass = False
        with self.assertRaisesRegex(BetaReleaseArtifactInventoryError, "all Beta-required functional tests"):
            self._build()

    def test_missing_early_userspace_signal_fails_closed(self) -> None:
        self.audit.kali_early_userspace_signal_present = False
        with self.assertRaisesRegex(BetaReleaseArtifactInventoryError, "Kali early-userspace signal"):
            self._build()

    def test_invalid_commit_fails_before_evidence_loading(self) -> None:
        with patch(
            "kaliphonestudio.beta_release_artifact_inventory._load_candidate_gate"
        ) as candidate_loader:
            with self.assertRaisesRegex(BetaReleaseArtifactInventoryError, "source commit"):
                build_beta_release_artifact_inventory(
                    self.root / "candidate.json",
                    self.root / "audit.json",
                    self.root / "strategy.json",
                    "main",
                    self.artifacts,
                )
            candidate_loader.assert_not_called()

    def test_unknown_artifact_role_fails_closed(self) -> None:
        artifacts = dict(self.artifacts)
        artifacts["mystery_payload"] = self._write("mystery.bin", b"payload\n")
        with self.assertRaisesRegex(BetaReleaseArtifactInventoryError, "unsupported release artifact role"):
            self._build(artifacts)

    def test_duplicate_release_filename_fails_closed(self) -> None:
        same = self.artifacts["operator_instructions"]
        artifacts = dict(self.artifacts)
        artifacts["known_issues"] = same
        with self.assertRaisesRegex(BetaReleaseArtifactInventoryError, "filenames must be unique"):
            self._build(artifacts)

    def test_symlink_artifact_fails_closed(self) -> None:
        target = self._write("real-known-issues.txt", b"known issues\n")
        link = self.root / "linked-known-issues.txt"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable on this platform")
        artifacts = dict(self.artifacts)
        artifacts["known_issues"] = link
        with self.assertRaisesRegex(BetaReleaseArtifactInventoryError, "regular non-symlink"):
            self._build(artifacts)

    def test_optional_dtb_is_exactly_bound_when_candidate_requires_it(self) -> None:
        dtb = self._write("device.dtb", b"dtb-bytes\n")
        self.candidate.dtb_sha256 = sha256(dtb.read_bytes()).hexdigest()
        with self.assertRaisesRegex(BetaReleaseArtifactInventoryError, "DTB artifact is required"):
            self._build()
        artifacts = dict(self.artifacts)
        artifacts["dtb"] = dtb
        evidence = self._build(artifacts)
        self.assertIn("dtb", {item.role for item in evidence.artifacts})
