from __future__ import annotations

from unittest import TestCase
from unittest.mock import patch

from kaliphonestudio.operator_evidence_workspace import ALL_EVIDENCE_COMMANDS, main as workspace_main
from kaliphonestudio.operator_trial_evidence_cli import TRIAL_EVIDENCE_COMMANDS, _build_parser


class OperatorTrialEvidenceWorkspaceTests(TestCase):
    def test_trial_commands_are_exposed_once_in_unified_workspace(self) -> None:
        for command in TRIAL_EVIDENCE_COMMANDS:
            self.assertIn(command, ALL_EVIDENCE_COMMANDS)
            self.assertEqual(ALL_EVIDENCE_COMMANDS.count(command), 1)

    def test_workspace_routes_prepare_trial_authorization_to_trial_dispatcher(self) -> None:
        command = "prepare-rootfs-handoff-trial-authorization-review"
        with patch(
            "kaliphonestudio.operator_evidence_workspace.trial_evidence_main",
            return_value=17,
        ) as routed:
            self.assertEqual(workspace_main([command, "--help"]), 17)
        routed.assert_called_once_with([command, "--help"])

    def test_workspace_routes_bind_trial_authorization_to_trial_dispatcher(self) -> None:
        command = "bind-rootfs-handoff-trial-authorization-review"
        with patch(
            "kaliphonestudio.operator_evidence_workspace.trial_evidence_main",
            return_value=18,
        ) as routed:
            self.assertEqual(workspace_main([command, "--help"]), 18)
        routed.assert_called_once_with([command, "--help"])

    def test_workspace_routes_trial_plan_to_trial_dispatcher(self) -> None:
        command = "build-rootfs-handoff-trial-plan"
        with patch(
            "kaliphonestudio.operator_evidence_workspace.trial_evidence_main",
            return_value=20,
        ) as routed:
            self.assertEqual(workspace_main([command, "--help"]), 20)
        routed.assert_called_once_with([command, "--help"])

    def test_workspace_routes_trial_preflight_to_trial_dispatcher(self) -> None:
        command = "build-rootfs-handoff-trial-preflight"
        with patch(
            "kaliphonestudio.operator_evidence_workspace.trial_evidence_main",
            return_value=21,
        ) as routed:
            self.assertEqual(workspace_main([command, "--help"]), 21)
        routed.assert_called_once_with([command, "--help"])

    def test_existing_strategy_route_remains_unchanged(self) -> None:
        command = "build-rootfs-handoff-fresh-revalidation"
        with patch(
            "kaliphonestudio.operator_evidence_workspace.strategy_evidence_main",
            return_value=19,
        ) as routed:
            self.assertEqual(workspace_main([command, "--help"]), 19)
        routed.assert_called_once_with([command, "--help"])

    def test_trial_parser_requires_exact_inputs_for_prepare_bind_plan_and_preflight(self) -> None:
        parser = _build_parser()
        prepare = parser.parse_args(
            [
                "prepare-rootfs-handoff-trial-authorization-review",
                "--target-binding", "target.json",
                "--fresh-revalidation", "fresh.json",
                "--reviewer", "reviewer-1",
                "--record-out", "record.json",
                "--notes-out", "notes.txt",
            ]
        )
        self.assertEqual(prepare.evidence_command, TRIAL_EVIDENCE_COMMANDS[0])
        bind = parser.parse_args(
            [
                "bind-rootfs-handoff-trial-authorization-review",
                "--target-binding", "target.json",
                "--fresh-revalidation", "fresh.json",
                "--review-record", "record.json",
                "--review-notes", "notes.txt",
                "--out", "authorization.json",
            ]
        )
        self.assertEqual(bind.evidence_command, TRIAL_EVIDENCE_COMMANDS[1])
        plan = parser.parse_args(
            [
                "build-rootfs-handoff-trial-plan",
                "--trial-authorization", "authorization.json",
                "--target-binding", "target.json",
                "--fresh-revalidation", "fresh.json",
                "--out", "trial-plan.json",
            ]
        )
        self.assertEqual(plan.evidence_command, TRIAL_EVIDENCE_COMMANDS[2])
        preflight = parser.parse_args(
            [
                "build-rootfs-handoff-trial-preflight",
                "--trial-plan", "trial-plan.json",
                "--rootfs-artifact", "rootfs.tar.xz",
                "--out", "trial-preflight.json",
            ]
        )
        self.assertEqual(preflight.evidence_command, TRIAL_EVIDENCE_COMMANDS[3])
