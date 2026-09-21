"""PySide6 physical-phone test wizard for KaliPhoneStudio.

The wizard is intentionally stage-gated. It can detect one reviewed Fastboot device,
capture a read-only physical baseline, prepare the exact offline candidate chain and
perform only the already-reviewed one-shot temporary boot after explicit confirmation.
Persistent flashing remains unavailable until the physical release gate is satisfied.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .physical_gui_bridge import (
    PhysicalGuiBridgeError,
    build_begin_session_args,
    build_prepare_candidate_args,
    build_temporary_boot_args,
    detect_single_fastboot_device,
    ensure_no_persistent_write_verbs,
    inspect_session_state,
    runtime_candidate_root,
    runtime_cli_invocation,
    runtime_extractor,
    runtime_fastboot_policy,
    suggested_fastboot,
)
from .profiles import ProfileError, discover_profiles


def create_physical_test_dialog(parent, devices_root: Path, initial_profile_id: str | None = None):
    from PySide6.QtCore import QProcess, Qt
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDialog,
        QFileDialog,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMessageBox,
        QPlainTextEdit,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )

    class PhysicalTestDialog(QDialog):
        def __init__(self) -> None:
            super().__init__(parent)
            self.setWindowTitle("KaliPhoneStudio — Physical phone test")
            self.resize(980, 820)
            self._devices_root = Path(devices_root)
            self._candidate_root = runtime_candidate_root()
            self._policy_path = runtime_fastboot_policy(self._candidate_root)
            self._cli_program, self._cli_prefix = runtime_cli_invocation(self._candidate_root)
            self._profiles = {}
            self._detected_serial: str | None = None
            self._process: QProcess | None = None
            self._pending_stage: str | None = None

            root = QVBoxLayout(self)
            root.setContentsMargins(16, 16, 16, 16)
            root.setSpacing(10)

            title = QLabel("Physical bring-up wizard")
            title.setStyleSheet("font-size: 20px; font-weight: 700; color: #62E5FF;")
            root.addWidget(title)

            safety = QLabel(
                "PHYSICAL TEST MODE — only reviewed read-only Fastboot capture, offline "
                "candidate preparation and explicitly confirmed temporary fastboot boot are exposed. "
                "Persistent flash/erase/slot changes remain locked."
            )
            safety.setWordWrap(True)
            safety.setStyleSheet(
                "padding: 10px; background: #07111C; border: 1px solid #0088FF; "
                "border-radius: 6px; font-weight: 600;"
            )
            root.addWidget(safety)

            host_group = QGroupBox("1. Detect phone and create read-only baseline")
            host_form = QFormLayout(host_group)

            self.profile = QComboBox()
            host_form.addRow("Device profile:", self.profile)

            self.fastboot = QLineEdit(suggested_fastboot())
            host_form.addRow("Reviewed fastboot.exe:", self._file_row(self.fastboot, self._browse_fastboot))

            self.detect_button = QPushButton("Detect Fastboot phone")
            self.detect_button.clicked.connect(self._detect_phone)
            host_form.addRow("", self.detect_button)

            self.device_status = QLabel("Not detected")
            self.device_status.setWordWrap(True)
            host_form.addRow("Detected device:", self.device_status)

            self.firmware_build = QLineEdit()
            self.firmware_build.setPlaceholderText("Exact OxygenOS build shown on the phone")
            host_form.addRow("Firmware build:", self.firmware_build)

            self.firmware_fingerprint = QLineEdit()
            self.firmware_fingerprint.setPlaceholderText("Exact full firmware fingerprint")
            host_form.addRow("Firmware fingerprint:", self.firmware_fingerprint)

            self.session_dir = QLineEdit()
            host_form.addRow("Fresh evidence session:", self._file_row(self.session_dir, self._choose_session_parent))

            self.baseline_button = QPushButton("Create read-only baseline")
            self.baseline_button.clicked.connect(self._start_baseline)
            host_form.addRow("", self.baseline_button)
            root.addWidget(host_group)

            candidate_group = QGroupBox("2. Exact OTA, boot identity and recovery readiness")
            candidate_form = QFormLayout(candidate_group)

            self.ota = QLineEdit()
            candidate_form.addRow("Matching OxygenOS OTA:", self._file_row(self.ota, lambda: self._browse_file(self.ota, "Select exact matching OxygenOS OTA")))

            self.extractor = QLineEdit()
            packaged_extractor = runtime_extractor(self._candidate_root)
            if packaged_extractor is not None:
                self.extractor.setText(str(packaged_extractor))
            candidate_form.addRow("Reviewed OTA extractor:", self._file_row(self.extractor, lambda: self._browse_file(self.extractor, "Select reviewed OTA extractor")))

            self.first_boot_manifest = QLineEdit()
            candidate_form.addRow("First-boot manifest:", self._file_row(self.first_boot_manifest, lambda: self._browse_file(self.first_boot_manifest, "Select exact first-boot manifest")))

            self.authority_bundle = QLineEdit()
            candidate_form.addRow("Authority bundle:", self._file_row(self.authority_bundle, lambda: self._browse_file(self.authority_bundle, "Select reviewed authority bundle")))

            self.boot_authorization = QLineEdit()
            candidate_form.addRow("Temporary-boot authorization:", self._file_row(self.boot_authorization, lambda: self._browse_file(self.boot_authorization, "Select temporary-boot authorization")))

            self.boot_plan = QLineEdit()
            candidate_form.addRow("Boot plan:", self._file_row(self.boot_plan, lambda: self._browse_file(self.boot_plan, "Select exact boot plan")))

            self.candidate_boot = QLineEdit()
            candidate_form.addRow("Candidate boot.img:", self._file_row(self.candidate_boot, lambda: self._browse_file(self.candidate_boot, "Select exact candidate boot.img")))

            self.candidate_dtbo = QLineEdit()
            candidate_form.addRow("Candidate dtbo.img:", self._file_row(self.candidate_dtbo, lambda: self._browse_file(self.candidate_dtbo, "Select exact candidate dtbo.img")))

            self.prepare_button = QPushButton("Prepare exact offline candidate + recovery readiness")
            self.prepare_button.clicked.connect(self._prepare_candidate)
            candidate_form.addRow("", self.prepare_button)
            root.addWidget(candidate_group)

            boot_group = QGroupBox("3. Recovery-gated temporary boot")
            boot_form = QFormLayout(boot_group)

            self.confirmation = QLineEdit()
            self.confirmation.setPlaceholderText("Type the exact profile confirmation token")
            boot_form.addRow("Confirmation:", self.confirmation)

            self.temporary_ack = QCheckBox(
                "I understand this performs one temporary fastboot boot and does not install permanently."
            )
            boot_form.addRow("", self.temporary_ack)

            self.boot_button = QPushButton("Run one-shot TEMPORARY boot")
            self.boot_button.clicked.connect(self._temporary_boot)
            boot_form.addRow("", self.boot_button)

            self.flash_locked = QPushButton("Persistent flash — LOCKED until physical Beta gate passes")
            self.flash_locked.setEnabled(False)
            boot_form.addRow("", self.flash_locked)
            root.addWidget(boot_group)

            status_row = QHBoxLayout()
            self.stage_status = QLabel("Stage: host preparation")
            self.stage_status.setStyleSheet("font-weight: 600; color: #62E5FF;")
            status_row.addWidget(self.stage_status, 1)
            refresh = QPushButton("Refresh evidence state")
            refresh.clicked.connect(self._refresh_state)
            status_row.addWidget(refresh)
            root.addLayout(status_row)

            self.log = QPlainTextEdit()
            self.log.setReadOnly(True)
            self.log.setMaximumBlockCount(3000)
            root.addWidget(self.log, 1)

            close = QPushButton("Close")
            close.clicked.connect(self.close)
            root.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)

            self._load_profiles(initial_profile_id)
            self._refresh_state()

        def _file_row(self, editor: QLineEdit, callback: Callable[[], None]) -> QWidget:
            widget = QWidget()
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(editor, 1)
            button = QPushButton("Browse…")
            button.clicked.connect(callback)
            layout.addWidget(button)
            return widget

        def _load_profiles(self, initial: str | None) -> None:
            try:
                profiles = discover_profiles(self._devices_root)
            except ProfileError as exc:
                QMessageBox.critical(self, "Profile validation failed", str(exc))
                return
            self._profiles = {profile.profile_id: profile for profile in profiles}
            self.profile.clear()
            for profile_id in sorted(self._profiles):
                profile = self._profiles[profile_id]
                self.profile.addItem(f"{profile.data['display_name']} — {profile_id}", profile_id)
            target = initial if initial in self._profiles else "oneplus/avicii"
            index = self.profile.findData(target)
            if index >= 0:
                self.profile.setCurrentIndex(index)

        def _selected_profile(self):
            profile_id = self.profile.currentData()
            if not profile_id or str(profile_id) not in self._profiles:
                raise PhysicalGuiBridgeError("select a validated device profile")
            return self._profiles[str(profile_id)]

        def _browse_fastboot(self) -> None:
            filename, _ = QFileDialog.getOpenFileName(
                self, "Select reviewed fastboot.exe", self.fastboot.text(), "Executables (*.exe);;All files (*)"
            )
            if filename:
                self.fastboot.setText(filename)
                self._detected_serial = None
                self.device_status.setText("Not detected after Fastboot path change")

        def _browse_file(self, editor: QLineEdit, title: str) -> None:
            filename, _ = QFileDialog.getOpenFileName(self, title, editor.text(), "All files (*)")
            if filename:
                editor.setText(filename)

        def _choose_session_parent(self) -> None:
            parent_dir = QFileDialog.getExistingDirectory(self, "Choose parent folder for a NEW test session")
            if not parent_dir:
                return
            parent_path = Path(parent_dir)
            base = parent_path / "kps-ac2003-first-test-01"
            candidate = base
            number = 1
            while candidate.exists():
                number += 1
                candidate = parent_path / f"kps-ac2003-first-test-{number:02d}"
            self.session_dir.setText(str(candidate))
            self._refresh_state()

        def _append_log(self, text: str) -> None:
            cleaned = text.rstrip()
            if cleaned:
                self.log.appendPlainText(cleaned)

        def _detect_phone(self) -> None:
            try:
                detection = detect_single_fastboot_device(
                    self.fastboot.text(),
                    policy_path=self._policy_path,
                )
            except PhysicalGuiBridgeError as exc:
                self._detected_serial = None
                self.device_status.setText(f"Detection refused: {exc}")
                QMessageBox.warning(self, "Fastboot detection refused", str(exc))
                return
            self._detected_serial = detection.serial
            self.fastboot.setText(str(detection.executable))
            self.device_status.setText(
                f"Serial {detection.serial} • Platform-Tools {detection.platform_tools_version} • "
                f"SHA-256 {detection.executable_sha256[:16]}…"
            )
            self._append_log(
                f"READ-ONLY DETECTION PASS: serial={detection.serial} "
                f"fastboot={detection.platform_tools_version}"
            )

        def _start_baseline(self) -> None:
            try:
                profile = self._selected_profile()
                if not self._detected_serial:
                    raise PhysicalGuiBridgeError("detect exactly one Fastboot phone first")
                args = build_begin_session_args(
                    profile_id=profile.profile_id,
                    confirmation_token=profile.confirmation_text,
                    serial=self._detected_serial,
                    firmware_build=self.firmware_build.text(),
                    firmware_fingerprint=self.firmware_fingerprint.text(),
                    fastboot=self.fastboot.text(),
                    policy_path=self._policy_path,
                    session_dir=self.session_dir.text(),
                )
                ensure_no_persistent_write_verbs(args)
            except (PhysicalGuiBridgeError, OSError) as exc:
                QMessageBox.warning(self, "Baseline refused", str(exc))
                return
            self._run_cli("read-only baseline", args)

        def _prepare_candidate(self) -> None:
            try:
                profile = self._selected_profile()
                state = inspect_session_state(self.session_dir.text())
                if not state.baseline_ready:
                    raise PhysicalGuiBridgeError("a complete read-only baseline session is required first")
                args = build_prepare_candidate_args(
                    profile_id=profile.profile_id,
                    session_dir=state.session_dir,
                    ota=self.ota.text(),
                    extractor=self.extractor.text(),
                    first_boot_manifest=self.first_boot_manifest.text(),
                    authority_bundle=self.authority_bundle.text(),
                    boot_authorization=self.boot_authorization.text(),
                    boot_plan=self.boot_plan.text(),
                    candidate_boot=self.candidate_boot.text(),
                    candidate_dtbo=self.candidate_dtbo.text(),
                    fastboot=self.fastboot.text(),
                )
                ensure_no_persistent_write_verbs(args)
            except (PhysicalGuiBridgeError, OSError) as exc:
                QMessageBox.warning(self, "Offline candidate preparation refused", str(exc))
                return
            self._run_cli("offline OTA/candidate/recovery preparation", args)

        def _temporary_boot(self) -> None:
            try:
                profile = self._selected_profile()
                if self.confirmation.text().strip() != profile.confirmation_text:
                    raise PhysicalGuiBridgeError(
                        f"type the exact confirmation token: {profile.confirmation_text}"
                    )
                if not self.temporary_ack.isChecked():
                    raise PhysicalGuiBridgeError("temporary-boot acknowledgement is required")
                state = inspect_session_state(self.session_dir.text())
                if not state.offline_candidate_ready:
                    raise PhysicalGuiBridgeError(
                        "offline candidate and recovery-readiness evidence are incomplete"
                    )
                args = build_temporary_boot_args(
                    profile_id=profile.profile_id,
                    confirmation_token=profile.confirmation_text,
                    session_dir=state.session_dir,
                    fastboot=self.fastboot.text(),
                    boot_image=self.candidate_boot.text(),
                )
                ensure_no_persistent_write_verbs(args)
            except (PhysicalGuiBridgeError, OSError) as exc:
                QMessageBox.warning(self, "Temporary boot refused", str(exc))
                return
            answer = QMessageBox.question(
                self,
                "Confirm one-shot temporary boot",
                "This will execute the reviewed one-shot fastboot boot path on the detected phone. "
                "It does not flash a partition. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            self._run_cli("one-shot temporary boot", args)

        def _run_cli(self, stage: str, args: tuple[str, ...]) -> None:
            if self._process is not None:
                QMessageBox.warning(self, "Operation already running", "Finish the current stage first.")
                return
            process = QProcess(self)
            process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
            process.setProgram(self._cli_program)
            process.setArguments([*self._cli_prefix, *args])
            process.readyReadStandardOutput.connect(
                lambda: self._append_log(bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace"))
            )
            process.finished.connect(self._process_finished)
            process.errorOccurred.connect(
                lambda error: self._append_log(f"PROCESS ERROR: {error}")
            )
            self._process = process
            self._pending_stage = stage
            self._set_busy(True)
            self._append_log(f"START: {stage}")
            process.start()

        def _process_finished(self, exit_code: int, _exit_status) -> None:
            stage = self._pending_stage or "operation"
            process = self._process
            if process is not None:
                remaining = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
                self._append_log(remaining)
                process.deleteLater()
            self._process = None
            self._pending_stage = None
            self._set_busy(False)
            if exit_code == 0:
                self._append_log(f"PASS: {stage}")
                self._refresh_state()
            else:
                self._append_log(f"REFUSED/FAILED: {stage} exit={exit_code}")
                QMessageBox.warning(
                    self,
                    "Physical stage did not pass",
                    f"{stage} exited with code {exit_code}. Review the log and do not bypass the gate.",
                )

        def _set_busy(self, busy: bool) -> None:
            for button in (self.detect_button, self.baseline_button, self.prepare_button, self.boot_button):
                button.setEnabled(not busy)

        def _refresh_state(self) -> None:
            text = self.session_dir.text().strip()
            if not text:
                self.stage_status.setText("Stage: host preparation")
                return
            try:
                state = inspect_session_state(text)
            except OSError:
                self.stage_status.setText("Stage: invalid session path")
                return
            if state.temporary_boot_recorded:
                self.stage_status.setText("Stage: temporary boot evidence recorded — continue physical review")
            elif state.offline_candidate_ready:
                self.stage_status.setText("Stage: recovery-ready candidate — temporary boot may be reviewed")
            elif state.baseline_ready:
                self.stage_status.setText("Stage: read-only baseline complete — exact OTA/candidate needed")
            else:
                self.stage_status.setText("Stage: fresh session not captured yet")

        def reject(self) -> None:
            if self._process is not None:
                QMessageBox.warning(
                    self,
                    "Operation running",
                    "Do not close the wizard while an evidence-producing stage is running.",
                )
                return
            super().reject()

    return PhysicalTestDialog()
