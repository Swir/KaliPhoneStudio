"""KaliPhoneStudio application entrypoint and safe host operator workspace.

The default GUI remains offline: it performs no ADB/Fastboot calls and exposes no
destructive operation.  It can browse profiles, run read-only host diagnostics,
show profile-driven recovery guidance and export a redacted support bundle.
Dedicated evidence/physical tools retain their own explicit safety boundaries.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sys
from typing import Sequence

from . import __version__
from .operator_diagnostics import (
    OperatorDiagnosticsError,
    build_diagnostic_report,
    build_operator_bundle,
    build_recovery_guide,
    format_diagnostic_report,
    format_recovery_guide,
    write_operator_bundle,
)
from .profiles import DeviceProfile, ProfileError, discover_profiles, get_profile


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEVICES_ROOT = REPO_ROOT / "devices"


@dataclass(frozen=True)
class ProfileSummary:
    profile_id: str
    display_name: str
    model: str
    codename: str
    arch: str
    soc: str
    boot_header_version: int
    ramdisk_compression: str
    ab_device: bool
    avb_enabled: bool
    confirmation_text: str
    source_count: int
    host_test_count: int
    hardware_beta_test_count: int

    @classmethod
    def from_profile(cls, profile: DeviceProfile) -> "ProfileSummary":
        data = profile.data
        boot = data["boot"]
        tests = data["test_contract"]
        return cls(
            profile_id=profile.profile_id,
            display_name=str(data["display_name"]),
            model=str(data["model"]),
            codename=str(data["codename"]),
            arch=str(data["arch"]),
            soc=str(data["soc"]),
            boot_header_version=int(boot["header_version"]),
            ramdisk_compression=str(boot["ramdisk_compression"]),
            ab_device=bool(data["ab_device"]),
            avb_enabled=bool(data["avb_enabled"]),
            confirmation_text=str(data["confirmation_text"]),
            source_count=len(data["sources"]),
            host_test_count=len(tests["host"]),
            hardware_beta_test_count=len(tests["hardware_beta"]),
        )


def load_profile_catalog(devices_root: Path = DEFAULT_DEVICES_ROOT) -> list[ProfileSummary]:
    """Return validated profile summaries in deterministic profile-id order."""
    profiles = discover_profiles(Path(devices_root))
    return sorted((ProfileSummary.from_profile(p) for p in profiles), key=lambda p: p.profile_id)


def _profile_details(profile: DeviceProfile) -> str:
    data = profile.data
    boot = data["boot"]
    kernel = data["kernel"]
    sources = "\n".join(
        f"  - {item['name']}\n    {item['url']}@{item['commit']}" for item in data["sources"]
    )
    recovery = "\n".join(f"  - {item}" for item in data["recovery_notes"])
    host_tests = "\n".join(f"  - {item}" for item in data["test_contract"]["host"])
    hardware_tests = "\n".join(f"  - {item}" for item in data["test_contract"]["hardware_beta"])
    return (
        f"Profile: {profile.profile_id}\n"
        f"Device: {data['display_name']} ({data['model']})\n"
        f"Codename / board: {data['codename']} / {data['board']}\n"
        f"Architecture / SoC: {data['arch']} / {data['soc']}\n"
        f"A/B device: {'yes' if data['ab_device'] else 'no'}\n"
        f"AVB enabled: {'yes' if data['avb_enabled'] else 'no'}\n"
        f"Boot image: header v{boot['header_version']}, page {boot['page_size']} B, "
        f"ramdisk={boot['ramdisk_compression']}\n"
        f"Kernel baseline: {kernel['source_name']}\n"
        f"Expected kernel version: {kernel['expected_version']}\n"
        f"Confirmation token: {profile.confirmation_text}\n\n"
        "Pinned sources:\n"
        f"{sources}\n\n"
        "Host contract:\n"
        f"{host_tests}\n\n"
        "Hardware Beta contract (NOT satisfied by profile presence):\n"
        f"{hardware_tests}\n\n"
        "Recovery notes:\n"
        f"{recovery}"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="KaliPhoneStudio",
        description="Safe multi-device Kali Linux phone-porting studio.",
    )
    parser.add_argument(
        "--devices-root",
        type=Path,
        default=DEFAULT_DEVICES_ROOT,
        help="Path containing devices/<vendor>/<codename>/profile.json profiles.",
    )
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--list-profiles", action="store_true", help="List validated profiles and exit.")
    actions.add_argument(
        "--doctor",
        action="store_true",
        help="Run safe offline host diagnostics; never executes adb/fastboot.",
    )
    actions.add_argument(
        "--recovery-guide",
        action="store_true",
        help="Show profile-driven non-executing recovery guidance (requires --profile-id).",
    )
    actions.add_argument(
        "--export-diagnostics",
        type=Path,
        metavar="PATH",
        help="Write a deterministic redacted offline diagnostics bundle to PATH.",
    )
    actions.add_argument("--gui", action="store_true", help="Launch the offline PySide6 operator workspace.")
    parser.add_argument(
        "--profile-id",
        help="Profile to inspect, or profile context for --doctor/--recovery-guide/--export-diagnostics/--gui.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON for supported CLI output.")
    parser.add_argument("--version", action="version", version=f"KaliPhoneStudio {__version__}")
    return parser


def _print_profiles(devices_root: Path, *, as_json: bool) -> int:
    catalog = load_profile_catalog(devices_root)
    if as_json:
        print(json.dumps([asdict(item) for item in catalog], indent=2, sort_keys=True))
    else:
        if not catalog:
            print("No validated device profiles found.")
            return 1
        for item in catalog:
            print(f"{item.profile_id}\t{item.display_name}\t{item.arch}\t{item.soc}")
    return 0


def _print_profile(devices_root: Path, profile_id: str, *, as_json: bool) -> int:
    profile = get_profile(devices_root, profile_id)
    if as_json:
        payload = {
            "summary": asdict(ProfileSummary.from_profile(profile)),
            "profile": profile.data,
            "hardware_verified": False,
            "beta_gate_credit": False,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(_profile_details(profile))
    return 0


def _run_doctor(devices_root: Path, profile_id: str | None, *, as_json: bool) -> int:
    report = build_diagnostic_report(
        repo_root=REPO_ROOT,
        devices_root=devices_root,
        profile_id=profile_id,
    )
    if as_json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(format_diagnostic_report(report))
    return 0 if report.offline_review_ready else 2


def _print_recovery_guide(devices_root: Path, profile_id: str | None, *, as_json: bool) -> int:
    if not profile_id:
        print("--recovery-guide requires --profile-id", file=sys.stderr)
        return 2
    profile = get_profile(devices_root, profile_id)
    guide = build_recovery_guide(profile)
    if as_json:
        print(json.dumps(guide.to_dict(), indent=2, sort_keys=True))
    else:
        print(format_recovery_guide(guide))
    return 0


def _export_diagnostics(
    devices_root: Path,
    profile_id: str | None,
    destination: Path,
    *,
    as_json: bool,
) -> int:
    report = build_diagnostic_report(
        repo_root=REPO_ROOT,
        devices_root=devices_root,
        profile_id=profile_id,
    )
    guide = build_recovery_guide(get_profile(devices_root, profile_id)) if profile_id else None
    bundle = build_operator_bundle(report, guide)
    digest = write_operator_bundle(destination, bundle)
    result = {
        "path": str(destination),
        "sha256": digest,
        "offline_review_ready": report.offline_review_ready,
        "hardware_verified": False,
        "beta_gate_credit": False,
    }
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"Wrote offline diagnostics bundle: {destination}")
        print(f"SHA-256: {digest}")
        print("Physical interaction performed: no")
        print("Hardware/Beta credit granted: no")
    return 0 if report.offline_review_ready else 2


def _run_gui(devices_root: Path, initial_profile_id: str | None = None) -> int:
    # Lazy import keeps the core/CLI testable on minimal CI hosts where PySide6
    # is intentionally not installed by tests.yml.
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import (
            QApplication,
            QComboBox,
            QFileDialog,
            QFrame,
            QHBoxLayout,
            QLabel,
            QMainWindow,
            QMessageBox,
            QPushButton,
            QPlainTextEdit,
            QVBoxLayout,
            QWidget,
        )
    except ImportError:
        print(
            "PySide6 is required for the GUI. Install project requirements with "
            "'python -m pip install -r requirements.txt'.",
            file=sys.stderr,
        )
        return 2

    class OfflineOperatorWindow(QMainWindow):
        def __init__(self, root: Path, initial: str | None) -> None:
            super().__init__()
            self._root = Path(root)
            self._initial = initial
            self._profiles: dict[str, DeviceProfile] = {}
            self.setWindowTitle(f"KaliPhoneStudio {__version__} — Safe Operator Workspace")
            self.resize(1120, 760)
            icon_path = REPO_ROOT / "assets" / "app_icon.svg"
            if icon_path.is_file():
                self.setWindowIcon(QIcon(str(icon_path)))

            self.setStyleSheet(
                "QMainWindow, QWidget { background: #02050A; color: #F4FAFF; }"
                "QLabel { color: #F4FAFF; }"
                "QComboBox, QPlainTextEdit { background: #07111C; color: #F4FAFF; "
                "border: 1px solid #17435B; border-radius: 6px; padding: 6px; }"
                "QPushButton { background: #07111C; color: #62E5FF; border: 1px solid #0088FF; "
                "border-radius: 6px; padding: 7px 12px; font-weight: 600; }"
                "QPushButton:hover { background: #0A1A2B; border-color: #62E5FF; }"
                "QFrame[frameShape=\"4\"] { color: #17435B; }"
            )

            central = QWidget(self)
            layout = QVBoxLayout(central)
            layout.setContentsMargins(18, 18, 18, 12)
            layout.setSpacing(10)

            title = QLabel("KaliPhoneStudio — Safe Operator Workspace")
            title.setStyleSheet("font-size: 22px; font-weight: 700; color: #62E5FF;")
            layout.addWidget(title)

            subtitle = QLabel(
                "Profile browser • offline host doctor • redacted diagnostics export • recovery guidance"
            )
            subtitle.setStyleSheet("color: #8DA8B8;")
            layout.addWidget(subtitle)

            safety = QLabel(
                "SAFE OFFLINE MODE — this window never executes adb/fastboot and cannot flash a phone. "
                "A listed profile, green host diagnostics or exported bundle is not proof of hardware support."
            )
            safety.setWordWrap(True)
            safety.setStyleSheet(
                "padding: 11px; background: #07111C; border: 1px solid #0088FF; "
                "border-radius: 7px; font-weight: 600; color: #F4FAFF;"
            )
            layout.addWidget(safety)

            controls = QHBoxLayout()
            controls.addWidget(QLabel("Device profile:"))
            self.selector = QComboBox()
            self.selector.setMinimumWidth(390)
            controls.addWidget(self.selector, 1)
            refresh = QPushButton("Refresh profiles")
            refresh.clicked.connect(self.reload_profiles)
            controls.addWidget(refresh)
            layout.addLayout(controls)

            actions = QHBoxLayout()
            show_profile = QPushButton("Profile")
            show_profile.clicked.connect(self._show_selected)
            actions.addWidget(show_profile)
            show_doctor = QPushButton("Offline doctor")
            show_doctor.clicked.connect(self._show_doctor)
            actions.addWidget(show_doctor)
            show_recovery = QPushButton("Recovery guide")
            show_recovery.clicked.connect(self._show_recovery)
            actions.addWidget(show_recovery)
            export = QPushButton("Export diagnostics…")
            export.clicked.connect(self._export_bundle)
            actions.addWidget(export)
            physical = QPushButton("Physical phone test…")
            physical.clicked.connect(self._open_physical_wizard)
            physical.setStyleSheet(
                "QPushButton { background: #082034; color: #F4FAFF; border: 1px solid #62E5FF; "
                "border-radius: 6px; padding: 7px 12px; font-weight: 700; }"
            )
            actions.addWidget(physical)
            actions.addStretch(1)
            layout.addLayout(actions)

            divider = QFrame()
            divider.setFrameShape(QFrame.Shape.HLine)
            layout.addWidget(divider)

            self.details = QPlainTextEdit()
            self.details.setReadOnly(True)
            self.details.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
            layout.addWidget(self.details, 1)

            footer = QLabel("by Swir — github.com/Swir/KaliPhoneStudio — hardware support remains release-gated")
            footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
            footer.setStyleSheet("padding: 6px; color: #8DA8B8;")
            layout.addWidget(footer)

            self.setCentralWidget(central)
            self.selector.currentIndexChanged.connect(self._show_selected)
            self.reload_profiles()

        def _selected_profile_id(self) -> str | None:
            profile_id = self.selector.currentData()
            return str(profile_id) if profile_id else None

        def reload_profiles(self) -> None:
            try:
                profiles = discover_profiles(self._root)
            except ProfileError as exc:
                QMessageBox.critical(self, "Profile validation failed", str(exc))
                return
            previous = self.selector.currentData() or self._initial
            self._profiles = {item.profile_id: item for item in profiles}
            self.selector.blockSignals(True)
            self.selector.clear()
            for profile_id in sorted(self._profiles):
                profile = self._profiles[profile_id]
                self.selector.addItem(f"{profile.data['display_name']} — {profile_id}", profile_id)
            if previous in self._profiles:
                self.selector.setCurrentIndex(self.selector.findData(previous))
            self.selector.blockSignals(False)
            self._initial = None
            self._show_selected()

        def _show_selected(self) -> None:
            profile_id = self._selected_profile_id()
            if not profile_id or profile_id not in self._profiles:
                self.details.setPlainText("No validated profile is selected.")
                return
            self.details.setPlainText(_profile_details(self._profiles[profile_id]))

        def _show_doctor(self) -> None:
            try:
                report = build_diagnostic_report(
                    repo_root=REPO_ROOT,
                    devices_root=self._root,
                    profile_id=self._selected_profile_id(),
                )
            except (OperatorDiagnosticsError, ProfileError) as exc:
                QMessageBox.critical(self, "Offline doctor failed", str(exc))
                return
            self.details.setPlainText(format_diagnostic_report(report))

        def _show_recovery(self) -> None:
            profile_id = self._selected_profile_id()
            if not profile_id or profile_id not in self._profiles:
                self.details.setPlainText("Select a validated profile before opening recovery guidance.")
                return
            self.details.setPlainText(format_recovery_guide(build_recovery_guide(self._profiles[profile_id])))

        def _open_physical_wizard(self) -> None:
            try:
                from .physical_gui_wizard import create_physical_test_dialog

                dialog = create_physical_test_dialog(
                    self,
                    self._root,
                    self._selected_profile_id(),
                )
            except Exception as exc:
                QMessageBox.critical(self, "Physical test wizard unavailable", str(exc))
                return
            dialog.exec()

        def _export_bundle(self) -> None:
            profile_id = self._selected_profile_id()
            suggested = f"kaliphonestudio-{profile_id.replace('/', '-') if profile_id else 'host'}-diagnostics.json"
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Export offline diagnostics",
                suggested,
                "JSON files (*.json)",
            )
            if not filename:
                return
            try:
                report = build_diagnostic_report(
                    repo_root=REPO_ROOT,
                    devices_root=self._root,
                    profile_id=profile_id,
                )
                guide = build_recovery_guide(self._profiles[profile_id]) if profile_id else None
                bundle = build_operator_bundle(report, guide)
                digest = write_operator_bundle(Path(filename), bundle)
            except (OperatorDiagnosticsError, ProfileError) as exc:
                QMessageBox.critical(self, "Diagnostics export failed", str(exc))
                return
            QMessageBox.information(
                self,
                "Diagnostics exported",
                f"Saved a redacted offline bundle.\nSHA-256: {digest}\n\n"
                "No device command was executed and no hardware/Beta credit was granted.",
            )

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("KaliPhoneStudio")
    window = OfflineOperatorWindow(devices_root, initial_profile_id)
    window.show()
    return int(app.exec())


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.list_profiles:
            return _print_profiles(args.devices_root, as_json=args.json)
        if args.doctor:
            return _run_doctor(args.devices_root, args.profile_id, as_json=args.json)
        if args.recovery_guide:
            return _print_recovery_guide(args.devices_root, args.profile_id, as_json=args.json)
        if args.export_diagnostics:
            return _export_diagnostics(
                args.devices_root,
                args.profile_id,
                args.export_diagnostics,
                as_json=args.json,
            )
        if args.profile_id and not args.gui:
            return _print_profile(args.devices_root, args.profile_id, as_json=args.json)
        # `python main.py` remains the normal desktop entrypoint. --gui is
        # accepted explicitly for scripts/shortcuts and future launchers.
        return _run_gui(args.devices_root, args.profile_id)
    except (ProfileError, OperatorDiagnosticsError) as exc:
        print(f"Operator/profile error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
