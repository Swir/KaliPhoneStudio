from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from unittest import TestCase
import tempfile

from kaliphonestudio.beta_release_artifact_inventory import (
    BetaReleaseArtifactInventoryEvidence,
    ReleaseArtifactEntry,
)
from kaliphonestudio.beta_release_review_manifest import (
    BetaReleaseReviewManifestError,
    build_beta_release_review_manifest,
    build_sha256sums_text,
    load_beta_release_review_manifest,
    write_beta_release_review_manifest_bundle,
)


class BetaReleaseReviewManifestTests(TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.release = self.root / "release"
        self.release.mkdir()
        files = {
            "candidate_boot": ("candidate-boot.img", b"boot\n"),
            "kali_rootfs": ("kali-rootfs.tar.zst", b"rootfs\n"),
            "operator_instructions": ("INSTALL.txt", b"install\n"),
            "compatibility_matrix": ("COMPATIBILITY.json", b"{}\n"),
            "known_issues": ("KNOWN_ISSUES.txt", b"issues\n"),
        }
        entries: list[ReleaseArtifactEntry] = []
        for role, (filename, data) in files.items():
            path = self.release / filename
            path.write_bytes(data)
            entries.append(
                ReleaseArtifactEntry(
                    role=role,
                    filename=filename,
                    size=len(data),
                    sha256=sha256(data).hexdigest(),
                )
            )
        self.inventory = BetaReleaseArtifactInventoryEvidence(
            schema_version=1,
            inventory_policy="beta-release-artifact-inventory-v1",
            profile_id="oneplus/avicii",
            device_serial="SERIAL-001",
            firmware_build="AC2003_11.F.19",
            firmware_fingerprint="oneplus/avicii/example",
            source_commit="a" * 40,
            physical_candidate_gate_sha256="1" * 64,
            physical_release_gate_audit_sha256="2" * 64,
            rootfs_handoff_strategy_review_sha256="3" * 64,
            artifacts=tuple(sorted(entries, key=lambda item: item.role)),
            exact_files_verified=True,
            required_artifacts_present=True,
            beta_required_tests_all_reviewed_pass=True,
            kali_early_userspace_signal_present=True,
            ready_for_final_manual_release_review=True,
            manual_release_gate_review_required=True,
            release_publication_allowed=False,
            beta_release_authorized=False,
            hardware_verified=False,
            beta_gate_credit=False,
        )
        self.inventory_path = self.root / "inventory.json"
        self.inventory_path.write_text(self.inventory.canonical_json(), encoding="utf-8", newline="\n")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _build(self):
        return build_beta_release_review_manifest(self.inventory_path, self.release, "0.6.67-beta.1")

    def test_builds_exact_non_authorizing_review_manifest(self) -> None:
        evidence, checksums = self._build()
        self.assertTrue(evidence.exact_artifacts_reverified)
        self.assertTrue(evidence.inventory_ready_for_final_manual_release_review)
        self.assertTrue(evidence.final_manual_release_gate_review_required)
        self.assertFalse(evidence.release_publication_allowed)
        self.assertFalse(evidence.beta_release_authorized)
        self.assertFalse(evidence.hardware_verified)
        self.assertFalse(evidence.beta_gate_credit)
        self.assertEqual(evidence.artifact_count, len(self.inventory.artifacts))
        self.assertEqual(sha256(checksums.encode()).hexdigest(), evidence.sha256sums_sha256)

    def test_sha256sums_is_deterministic_and_filename_sorted(self) -> None:
        evidence, checksums = self._build()
        expected_names = sorted(item.filename for item in evidence.artifacts)
        actual_names = [line.split("  ", 1)[1] for line in checksums.splitlines()]
        self.assertEqual(actual_names, expected_names)
        self.assertEqual(checksums, build_sha256sums_text(tuple(reversed(evidence.artifacts))))

    def test_round_trip_bundle_is_canonical_and_no_overwrite(self) -> None:
        evidence, checksums = self._build()
        manifest = self.root / "review-manifest.json"
        sums = self.root / "SHA256SUMS"
        digest = write_beta_release_review_manifest_bundle(evidence, checksums, manifest, sums)
        self.assertEqual(digest, evidence.evidence_sha256())
        self.assertEqual(load_beta_release_review_manifest(manifest), evidence)
        self.assertEqual(sums.read_text(encoding="utf-8"), checksums)
        with self.assertRaisesRegex(BetaReleaseReviewManifestError, "refusing to overwrite"):
            write_beta_release_review_manifest_bundle(evidence, checksums, manifest, self.root / "other-sums")

    def test_artifact_content_drift_fails_closed(self) -> None:
        (self.release / "candidate-boot.img").write_bytes(b"drift\n")
        with self.assertRaisesRegex(BetaReleaseReviewManifestError, "differs from exact artifact inventory"):
            self._build()

    def test_missing_artifact_fails_closed(self) -> None:
        (self.release / "KNOWN_ISSUES.txt").unlink()
        with self.assertRaisesRegex(BetaReleaseReviewManifestError, "regular non-symlink"):
            self._build()

    def test_symlink_artifact_fails_closed(self) -> None:
        target = self.release / "KNOWN_ISSUES.txt"
        link = self.release / "KNOWN_ISSUES.link"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        entries = tuple(
            replace(item, filename="KNOWN_ISSUES.link") if item.role == "known_issues" else item
            for item in self.inventory.artifacts
        )
        inventory = replace(self.inventory, artifacts=entries)
        self.inventory_path.write_text(inventory.canonical_json(), encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(BetaReleaseReviewManifestError, "regular non-symlink"):
            self._build()

    def test_checksum_filename_injection_is_rejected(self) -> None:
        entries = tuple(
            replace(item, filename="KNOWN_ISSUES.txt\nfeedface  injected.bin") if item.role == "known_issues" else item
            for item in self.inventory.artifacts
        )
        inventory = replace(self.inventory, artifacts=entries)
        self.inventory_path.write_text(inventory.canonical_json(), encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(BetaReleaseReviewManifestError, "safe ASCII basename"):
            self._build()

    def test_non_review_ready_inventory_fails_closed(self) -> None:
        inventory = replace(
            self.inventory,
            exact_files_verified=False,
            ready_for_final_manual_release_review=False,
        )
        self.inventory_path.write_text(inventory.canonical_json(), encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(BetaReleaseReviewManifestError, "not ready for final manual release review"):
            self._build()

    def test_unsafe_version_fails_before_file_reverification(self) -> None:
        with self.assertRaisesRegex(BetaReleaseReviewManifestError, "version"):
            build_beta_release_review_manifest(self.inventory_path, self.release, "beta/latest")
