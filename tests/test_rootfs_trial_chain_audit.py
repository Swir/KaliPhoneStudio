from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = ROOT / "tools" / "audit_rootfs_trial_chain.py"


def _load_audit_module():
    spec = importlib.util.spec_from_file_location("audit_rootfs_trial_chain", AUDIT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load rootfs trial-chain audit module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


AUDIT = _load_audit_module()


class RootfsTrialChainAuditTests(unittest.TestCase):
    def test_repository_contract_passes(self) -> None:
        report = AUDIT.audit(ROOT)
        self.assertEqual("PASS", report["status"], report["failures"])
        self.assertEqual(3, len(report["contracts"]))
        self.assertTrue(all(item["status"] == "PASS" for item in report["contracts"]))
        self.assertTrue(all(not item["execution_primitives"] for item in report["contracts"]))
        plan = next(item for item in report["contracts"] if item["name"] == "interactive-trial-plan")
        preflight = next(item for item in report["contracts"] if item["name"] == "local-rootfs-preflight")
        self.assertEqual(["kaliphonestudio/stable_file.py"], plan["dependencies"])
        self.assertEqual(["kaliphonestudio/stable_file.py"], preflight["dependencies"])
        self.assertEqual([], plan["stable_reader_issues"])
        self.assertEqual([], preflight["stable_reader_issues"])
        self.assertFalse(report["physical_interaction_performed"])
        self.assertFalse(report["external_device_command_executed"])
        self.assertFalse(report["persistent_write_authorized"])
        self.assertFalse(report["phone_storage_written"])
        self.assertFalse(report["hardware_verified"])
        self.assertFalse(report["beta_release_authorized"])
        self.assertFalse(report["beta_gate_credit"])

    def test_json_cli_is_deterministic_and_machine_readable(self) -> None:
        command = [sys.executable, str(AUDIT_PATH), "--json"]
        first = subprocess.run(command, cwd=ROOT, check=False, capture_output=True, text=True)
        second = subprocess.run(command, cwd=ROOT, check=False, capture_output=True, text=True)
        self.assertEqual(0, first.returncode, first.stderr)
        self.assertEqual(0, second.returncode, second.stderr)
        self.assertEqual(first.stdout, second.stdout)
        report = json.loads(first.stdout)
        self.assertEqual("rootfs-trial-chain-audit-v1", report["schema"])
        self.assertEqual("PASS", report["status"])

    def _copy_contract_tree(self, destination: Path) -> None:
        copied: set[Path] = set()
        for contract in AUDIT.CONTRACTS:
            relative_paths = [Path(contract[key]) for key in ("source", "doc", "test")]
            relative_paths.extend(Path(value) for value in contract.get("dependencies", ()))
            for relative in relative_paths:
                if relative in copied:
                    continue
                copied.add(relative)
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, target)

    def test_policy_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            self._copy_contract_tree(tree)
            source = tree / "kaliphonestudio/rootfs_handoff_trial_plan.py"
            text = source.read_text(encoding="utf-8")
            text = text.replace(
                'rootfs-handoff-interactive-trial-plan-v1',
                'rootfs-handoff-interactive-trial-plan-v2-unreviewed',
                1,
            )
            source.write_text(text, encoding="utf-8")
            report = AUDIT.audit(tree)
            self.assertEqual("FAIL", report["status"])
            self.assertTrue(any("policy drift" in failure for failure in report["failures"]))

    def test_removed_beta_fail_closed_flag_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            self._copy_contract_tree(tree)
            source = tree / "kaliphonestudio/rootfs_handoff_trial_preflight.py"
            text = source.read_text(encoding="utf-8")
            marker = "_FORBIDDEN_PREFLIGHT_FLAGS = ("
            self.assertIn(marker, text)
            prefix, suffix = text.split(marker, 1)
            needle = '    "beta_gate_credit",\n'
            self.assertIn(needle, suffix)
            source.write_text(
                prefix + marker + suffix.replace(needle, "", 1),
                encoding="utf-8",
            )
            report = AUDIT.audit(tree)
            self.assertEqual("FAIL", report["status"])
            self.assertTrue(any("missing fail-closed flags" in failure for failure in report["failures"]))

    def test_execution_primitive_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            self._copy_contract_tree(tree)
            source = tree / "kaliphonestudio/rootfs_handoff_trial_authorization.py"
            text = source.read_text(encoding="utf-8")
            future = "from __future__ import annotations\n"
            self.assertIn(future, text)
            source.write_text(
                text.replace(future, future + "import subprocess\n", 1),
                encoding="utf-8",
            )
            report = AUDIT.audit(tree)
            self.assertEqual("FAIL", report["status"])
            self.assertTrue(any("execution primitives" in failure for failure in report["failures"]))

    def test_execution_primitive_in_safety_dependency_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            self._copy_contract_tree(tree)
            dependency = tree / "kaliphonestudio/stable_file.py"
            text = dependency.read_text(encoding="utf-8")
            future = "from __future__ import annotations\n"
            self.assertIn(future, text)
            dependency.write_text(
                text.replace(future, future + "import subprocess\n", 1),
                encoding="utf-8",
            )
            report = AUDIT.audit(tree)
            self.assertEqual("FAIL", report["status"])
            self.assertTrue(any("execution primitives" in failure for failure in report["failures"]))
            preflight = next(item for item in report["contracts"] if item["name"] == "local-rootfs-preflight")
            self.assertTrue(any("stable_file.py:import:subprocess" in hit for hit in preflight["execution_primitives"]))

    def test_stable_reader_regression_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            self._copy_contract_tree(tree)
            source = tree / "kaliphonestudio/rootfs_handoff_trial_plan.py"
            text = source.read_text(encoding="utf-8")
            needle = "raw, _identity = read_stable_regular_file("
            self.assertIn(needle, text)
            source.write_text(
                text.replace(needle, "raw = Path(path).read_bytes()\n        _identity = read_stable_regular_file(", 1),
                encoding="utf-8",
            )
            report = AUDIT.audit(tree)
            self.assertEqual("FAIL", report["status"])
            self.assertTrue(any("descriptor-bound stable reader drift" in failure for failure in report["failures"]))

    def test_documentation_safety_marker_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            self._copy_contract_tree(tree)
            doc = tree / "docs/ROOTFS_HANDOFF_TRIAL_PREFLIGHT.md"
            text = doc.read_text(encoding="utf-8")
            self.assertIn("interactive_executor_still_required=true", text)
            doc.write_text(
                text.replace("interactive_executor_still_required=true", "interactive executor required", 1),
                encoding="utf-8",
            )
            report = AUDIT.audit(tree)
            self.assertEqual("FAIL", report["status"])
            self.assertTrue(any("documentation safety markers drifted" in failure for failure in report["failures"]))


if __name__ == "__main__":
    unittest.main()
