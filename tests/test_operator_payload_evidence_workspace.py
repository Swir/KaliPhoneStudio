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
    def test_payload_commands_are_exposed_once_in_unified_workspace(self) -> None:
        for command in PAYLOAD_EVIDENCE_COMMANDS:
            self.assertIn(command, ALL_EVIDENCE_COMMANDS)
            self.assertEqual(ALL_EVIDENCE_COMMANDS.count(command), 1)

    def test_workspace_routes_each_payload_command_to_payload_dispatcher(self) -> None:
        for index, command in enumerate(PAYLOAD_EVIDENCE_COMMANDS, 23):
            with self.subTest(command=command), patch(
                "kaliphonestudio.operator_evidence_workspace.payload_evidence_main",
                return_value=index,
            ) as routed:
                self.assertEqual(workspace_main([command, "--help"]), index)
            routed.assert_called_once_with([command, "--help"])

    def test_workspace_routes_json_prefixed_payload_command(self) -> None:
        command = PAYLOAD_EVIDENCE_COMMANDS[-1]
        with patch(
            "kaliphonestudio.operator_evidence_workspace.payload_evidence_main",
            return_value=24,
        ) as routed:
            self.assertEqual(workspace_main(["--json", command, "--help"]), 24)
        routed.assert_called_once_with(["--json", command, "--help"])

    def test_payload_parser_requires_exact_inputs_for_each_stage(self) -> None:
        parser = _build_parser()
        payload = parser.parse_args([
            PAYLOAD_EVIDENCE_COMMANDS[0], "--execution-gate", "gate.json",
            "--rootfs-artifact", "rootfs.tar.xz", "--out", "payload.json",
        ])
        self.assertEqual(str(payload.execution_gate), "gate.json")
        metadata = parser.parse_args([
            PAYLOAD_EVIDENCE_COMMANDS[1], "--payload-manifest", "payload.json",
            "--rootfs-artifact", "rootfs.tar.xz", "--out", "metadata.json",
        ])
        self.assertEqual(str(metadata.payload_manifest), "payload.json")
        archive = parser.parse_args([
            PAYLOAD_EVIDENCE_COMMANDS[2], "--metadata-manifest", "metadata.json",
            "--rootfs-artifact", "rootfs.tar.xz", "--out", "archive-safety.json",
        ])
        self.assertEqual(str(archive.metadata_manifest), "metadata.json")

    def test_payload_result_preserves_non_writing_boundary(self) -> None:
        evidence = SimpleNamespace(
            profile_id="oneplus/avicii", device_serial="SERIAL-TEST",
            execution_gate_sha256="1" * 64, rootfs_artifact_sha256="2" * 64,
            entry_count=42, regular_payload_bytes=123456,
            minimum_required_free_bytes=67108864 + 123456,
            reviewed_required_free_bytes=128 * 1024 * 1024,
            observed_free_bytes=256 * 1024 * 1024, entries_sha256="3" * 64,
            exact_execution_gate_bound=True, exact_rootfs_bytes_verified=True,
            deterministic_write_scope_manifested=True, expanded_capacity_requirement_satisfied=True,
            interactive_writer_still_required=True,
            explicit_operator_confirmation_still_required=True,
            write_scope_confirmation_still_required=True,
        )
        args = SimpleNamespace(
            evidence_command=PAYLOAD_EVIDENCE_COMMANDS[0], execution_gate="gate.json",
            rootfs_artifact="rootfs.tar.xz", out="payload.json",
        )
        with patch(
            "kaliphonestudio.operator_payload_evidence_cli.build_rootfs_handoff_trial_payload_manifest",
            return_value=evidence,
        ), patch(
            "kaliphonestudio.operator_payload_evidence_cli.write_rootfs_handoff_trial_payload_evidence",
            return_value="4" * 64,
        ):
            result = _run(args)
        self.assertTrue(result["deterministic_write_scope_manifested"])
        self._assert_non_writing(result)

    def test_metadata_result_preserves_non_writing_boundary(self) -> None:
        evidence = SimpleNamespace(
            profile_id="oneplus/avicii", device_serial="SERIAL-TEST",
            payload_manifest_sha256="1" * 64, execution_gate_sha256="2" * 64,
            rootfs_artifact_sha256="3" * 64, entry_count=42,
            metadata_entries_sha256="4" * 64, pax_header_count=7,
            security_metadata_entry_count=2, exact_payload_manifest_bound=True,
            exact_rootfs_bytes_verified=True, posix_ownership_manifested=True,
            pax_metadata_manifested=True, interactive_writer_still_required=True,
            explicit_operator_confirmation_still_required=True,
            write_scope_confirmation_still_required=True,
        )
        args = SimpleNamespace(
            evidence_command=PAYLOAD_EVIDENCE_COMMANDS[1], payload_manifest="payload.json",
            rootfs_artifact="rootfs.tar.xz", out="metadata.json",
        )
        with patch(
            "kaliphonestudio.operator_payload_evidence_cli.build_rootfs_handoff_trial_metadata_manifest",
            return_value=evidence,
        ), patch(
            "kaliphonestudio.operator_payload_evidence_cli.write_rootfs_handoff_trial_metadata_evidence",
            return_value="5" * 64,
        ):
            result = _run(args)
        self.assertTrue(result["posix_ownership_manifested"])
        self._assert_non_writing(result)

    def test_archive_safety_result_preserves_non_writing_boundary(self) -> None:
        evidence = SimpleNamespace(
            profile_id="oneplus/avicii", device_serial="SERIAL-TEST",
            metadata_manifest_sha256="1" * 64, payload_manifest_sha256="2" * 64,
            rootfs_artifact_sha256="3" * 64, entry_count=42,
            symlink_count=3, absolute_symlink_count=1, relative_symlink_count=2,
            hardlink_count=1, exact_metadata_manifest_bound=True,
            exact_rootfs_bytes_verified=True, normalized_paths_unique=True,
            path_namespace_safe=True, link_targets_namespace_safe=True,
            no_link_ancestor_pivots=True, hardlink_targets_resolved=True,
            special_members_rejected=True,
        )
        args = SimpleNamespace(
            evidence_command=PAYLOAD_EVIDENCE_COMMANDS[2], metadata_manifest="metadata.json",
            rootfs_artifact="rootfs.tar.xz", out="archive-safety.json",
        )
        with patch(
            "kaliphonestudio.operator_payload_evidence_cli.build_rootfs_handoff_trial_archive_safety_evidence",
            return_value=evidence,
        ), patch(
            "kaliphonestudio.operator_payload_evidence_cli.write_rootfs_handoff_trial_archive_safety_evidence",
            return_value="6" * 64,
        ):
            result = _run(args)
        self.assertTrue(result["no_link_ancestor_pivots"])
        self.assertTrue(result["hardlink_targets_resolved"])
        self._assert_non_writing(result)

    def _assert_non_writing(self, result: dict[str, object]) -> None:
        for key in (
            "physical_interaction_performed", "external_device_command_executed",
            "raw_device_path_bound", "mount_target_bound", "extraction_performed",
            "trial_execution_allowed", "persistent_write_authorized",
            "persistent_write_performed", "phone_storage_written", "storage_verified",
            "recovery_verified", "hardware_verified", "beta_release_authorized", "beta_gate_credit",
        ):
            self.assertFalse(result[key], key)
