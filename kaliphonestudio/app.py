"""KaliPhoneStudio application entrypoint and offline device-profile browser.

The GUI intentionally performs no ADB/Fastboot calls and exposes no destructive
operation.  It is a safe offline surface for selecting and inspecting profiles
before build/evidence workflows are invoked by dedicated tooling.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sys
from typing import Sequence

from . import __version__
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
    parser.add_argument("--list-profiles", action="store_true", help="List validated profiles and exit.")
    parser.add_argument("--profile-id", help="Inspect one validated profile and exit.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON for list/profile output.")
    parser.add_argument("--gui", action="store_true", help="Launch the offline PySide6 profile selector.")
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


def _run_gui(devices_root: Path) -> int:
    # Lazy import keeps the core/CLI testable on minimal CI hosts where PySide6
    # is intentionally not installed by tests.yml.
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QApplication,
            QComboBox,
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

    class OfflineProfileWindow(QMainWindow):
        def __init__(self, root: Path) -> None:
            super().__init__()
            self._root = Path(root)
            self._profiles: dict[str, DeviceProfile] = {}
            self.setWindowTitle(f"KaliPhoneStudio {__version__} — Offline Profile Studio")
            self.resize(1080, 720)

            central = QWidget(self)
            layout = QVBoxLayout(central)

            title = QLabel("KaliPhoneStudio — Offline Device Profile Studio")
            title.setStyleSheet("font-size: 20px; font-weight: 700;")
            layout.addWidget(title)

            safety = QLabel(
                "SAFE OFFLINE MODE — this screen does not call adb/fastboot and cannot flash a phone. "
                "A listed profile is not proof of hardware support."
            )
            safety.setWordWrap(True)
            safety.setStyleSheet(
                "padding: 10px; border: 1px solid #3a6ea5; border-radius: 6px; font-weight: 600;"
            )
            layout.addWidget(safety)

            controls = QHBoxLayout()
            controls.addWidget(QLabel("Device profile:"))
            self.selector = QComboBox()
            self.selector.setMinimumWidth(380)
            controls.addWidget(self.selector, 1)
            refresh = QPushButton("Refresh profiles")
            refresh.clicked.connect(self.reload_profiles)
            controls.addWidget(refresh)
            layout.addLayout(controls)

            divider = QFrame()
            divider.setFrameShape(QFrame.Shape.HLine)
            layout.addWidget(divider)

            self.details = QPlainTextEdit()
            self.details.setReadOnly(True)
            self.details.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
            layout.addWidget(self.details, 1)

            footer = QLabel("by Swir — https://github.com/Swir/KaliPhoneStudio")
            footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
            footer.setStyleSheet("padding: 6px; opacity: 0.8;")
            layout.addWidget(footer)

            self.setCentralWidget(central)
            self.selector.currentIndexChanged.connect(self._show_selected)
            self.reload_profiles()

        def reload_profiles(self) -> None:
            try:
                profiles = discover_profiles(self._root)
            except ProfileError as exc:
                QMessageBox.critical(self, "Profile validation failed", str(exc))
                return
            previous = self.selector.currentData()
            self._profiles = {item.profile_id: item for item in profiles}
            self.selector.blockSignals(True)
            self.selector.clear()
            for profile_id in sorted(self._profiles):
                profile = self._profiles[profile_id]
                self.selector.addItem(f"{profile.data['display_name']} — {profile_id}", profile_id)
            if previous in self._profiles:
                self.selector.setCurrentIndex(self.selector.findData(previous))
            self.selector.blockSignals(False)
            self._show_selected()

        def _show_selected(self) -> None:
            profile_id = self.selector.currentData()
            if not profile_id or profile_id not in self._profiles:
                self.details.setPlainText("No validated profile is selected.")
                return
            self.details.setPlainText(_profile_details(self._profiles[profile_id]))

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("KaliPhoneStudio")
    window = OfflineProfileWindow(devices_root)
    window.show()
    return int(app.exec())


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.list_profiles:
            return _print_profiles(args.devices_root, as_json=args.json)
        if args.profile_id:
            return _print_profile(args.devices_root, args.profile_id, as_json=args.json)
        # `python main.py` remains the normal desktop entrypoint. --gui is
        # accepted explicitly for scripts/shortcuts and future launchers.
        return _run_gui(args.devices_root)
    except ProfileError as exc:
        print(f"Profile error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
