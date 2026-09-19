from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from kaliphonestudio import rootfs_handoff_fresh_revalidation as fresh_revalidation
from kaliphonestudio import rootfs_handoff_trial_plan as trial_plan
from kaliphonestudio import rootfs_handoff_trial_preflight as trial_preflight
from kaliphonestudio.stable_file import StableFileError


class StableTrialEvidenceReadTests(unittest.TestCase):
    def test_fresh_revalidation_loader_routes_through_stable_reader(self) -> None:
        with patch.object(
            fresh_revalidation,
            "read_stable_regular_file",
            side_effect=StableFileError("synthetic descriptor-bound refusal"),
        ) as stable_reader:
            with self.assertRaisesRegex(
                fresh_revalidation.RootfsHandoffFreshRevalidationError,
                "synthetic descriptor-bound refusal",
            ):
                fresh_revalidation.load_rootfs_handoff_fresh_revalidation_evidence(
                    Path("missing-fresh-revalidation.json")
                )

        stable_reader.assert_called_once_with(
            Path("missing-fresh-revalidation.json"),
            max_bytes=fresh_revalidation._MAX_EVIDENCE_BYTES,
            label="fresh target revalidation evidence",
        )

    def test_trial_plan_loader_routes_through_stable_reader(self) -> None:
        with patch.object(
            trial_plan,
            "read_stable_regular_file",
            side_effect=StableFileError("synthetic descriptor-bound refusal"),
        ) as stable_reader:
            with self.assertRaisesRegex(
                trial_plan.RootfsHandoffTrialPlanError,
                "synthetic descriptor-bound refusal",
            ):
                trial_plan.load_rootfs_handoff_trial_plan(Path("missing-plan.json"))

        stable_reader.assert_called_once_with(
            Path("missing-plan.json"),
            max_bytes=trial_plan._MAX_EVIDENCE_BYTES,
            label="trial plan",
        )

    def test_preflight_evidence_loader_routes_through_stable_reader(self) -> None:
        with patch.object(
            trial_preflight,
            "read_stable_regular_file",
            side_effect=StableFileError("synthetic descriptor-bound refusal"),
        ) as stable_reader:
            with self.assertRaisesRegex(
                trial_preflight.RootfsHandoffTrialPreflightError,
                "synthetic descriptor-bound refusal",
            ):
                trial_preflight.load_rootfs_handoff_trial_preflight_evidence(
                    Path("missing-preflight.json")
                )

        stable_reader.assert_called_once_with(
            Path("missing-preflight.json"),
            max_bytes=trial_preflight._MAX_EVIDENCE_BYTES,
            label="trial preflight evidence",
        )

    def test_domain_loaders_do_not_reintroduce_path_read_bytes(self) -> None:
        self.assertNotIn(
            "read_bytes",
            fresh_revalidation.load_rootfs_handoff_fresh_revalidation_evidence.__code__.co_names,
        )
        self.assertIn(
            "read_stable_regular_file",
            fresh_revalidation.load_rootfs_handoff_fresh_revalidation_evidence.__code__.co_names,
        )
        self.assertNotIn("read_bytes", trial_plan._read_exact.__code__.co_names)
        self.assertNotIn("read_bytes", trial_preflight._read_exact.__code__.co_names)
        self.assertIn("read_stable_regular_file", trial_plan._read_exact.__code__.co_names)
        self.assertIn("read_stable_regular_file", trial_preflight._read_exact.__code__.co_names)


if __name__ == "__main__":
    unittest.main()
