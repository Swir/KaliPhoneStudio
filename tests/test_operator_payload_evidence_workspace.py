from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from kaliphonestudio.operator_evidence_workspace import ALL_EVIDENCE_COMMANDS, main as workspace_main
from kaliphonestudio.operator_payload_evidence_cli import (
    PAYLOAD_EVIDENCE_COMMANDS,
    _build_parser,
    _run,
)


class OperatorPayloadEvidenceWorkspaceTests(TestCase):
    def test_payload_command_is_exposed_once_in_unified_workspace(self) -> None:
        command = PAYLOAD_EVIDENCE_COMMANDS[0]
        self.assertIn(command, ALL_EVIDENCE_COMMANDS)
        self.assertEqual(ALL_EVIDENCE_COMMANDS.count(command), 1)

    def test_workspace_routes_payload_manifest_to_payload_dispatcher(self) -> None:
        command = PAYLOAD_EVIDENCE_COMMANDS[0]
        with patch(
            "kaliphonestudio.operator_evidence_workspace.payload_evidence_main",
            return_value=23,
        ) as routed:
            self.assertEqual(workspace_main([command, "--help"]), 23)
        routed.assert_called_once_with([command, "--help"])

    def test_workspace_routes_json_prefixed_payload_command(self) -> None:
        command = PAYLOAD_EVIDENCE_COMMANDS[0]
        with patch(
            "kaliphonestudio.operator_evidence_workspace.payload_evidence_main",
            return_value=24,
        ) as routed:
            self.assertEqual(workspace_main(["--json", command, "--help"]), 24)
        routed.assert_called_once_with(["--json", command, "--help"])

    def test_payload_parser_requires_exact_gate_rootfs_and_output(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(
            [
                PAYLOAD_EVIDENCE_COMMANDS[0],
                "--execution-gate", "execution-gate.json",
                "--rootfs-artifact", "rootfs.tar.xz",
                "--out", "payload-manifest.json",
            ]
        )
        self.assertEqual(args.evidence_command, PAYLOAD_EVIDENCE_COMMANDS[0])
        self.assertEqual(str(args.execution_gate), "execution-gate.json")
        self.assertEqual(str(args.rootfs_artifact), "rootfs.tar.xz")
        self.assertEqual(str(args.out), "payload-manifest.json")

    def test_payload_result_preserves_non_writing_boundary(self) -> None:
        evidence = SimpleNamespace(
            profile_id="oneplus/avicii",
            device_serial="SERIAL-TEST",
            execution_gate_sha256="1" * 64,
            rootfs_artifact_sha256="2" * 64,
            entry_count=42,
            regular_payload_bytes=123456,
            minimum_required_free_bytes=67108864 + 123456,
            reviewed_required_free_bytes=128 * 1024 * 1024,
            observed_free_bytes=256 * 1024 * 1024,
            entries_sha256="3" * 64,
            exact_execution_gate_bound=True,
            exact_rootfs_bytes_verified=True,
            deterministic_write_scope_manifested=True,
            expanded_capacity_requirement_satisfied=True,
            interactive_writer_still_required=True,
            explicit_operator_confirmation_still_required=True,
            write_scope_confirmation_still_required=True,
        )
        args = SimpleNamespace(
            evidence_command=PAYLOAD_EVIDENCE_COMMANDS[0],
            execution_gate="execution-gate.json",
            rootfs_artifact="rootfs.tar.xz",
            out="payload-manifest.json",
        )
        with patch(
            "kaliphonestudio.operator_payload_evidence_cli.build_rootfs_handoff_trial_payload_manifest",
            return_value=evidence,
        ) as build, patch(
            "kaliphonestudio.operator_payload_evidence_cli.write_rootfs_handoff_trial_payload_evidence",
            return_value="4" * 64,
        ) as write:
            result = _run(args)

        build.assert_called_once_with("execution-gate.json", "rootfs.tar.xz")
        write.assert_called_once_with(evidence, "payload-manifest.json")
        self.assertTrue(result["deterministic_write_scope_manifested"])
        self.assertTrue(result["interactive_writer_still_required"])
        for key in (
            "physical_interaction_performed",
            "external_device_command_executed",
            "raw_device_path_bound",
            "mount_target_bound",
            "trial_execution_allowed",
            "persistent_write_authorized",
            "persistent_write_performed",
            "phone_storage_written",
            "storage_verified",
            "recovery_verified",
            "hardware_verified",
            "beta_release_authorized",
            "beta_gate_credit",
        ):
            self.assertFalse(result[key], key)
