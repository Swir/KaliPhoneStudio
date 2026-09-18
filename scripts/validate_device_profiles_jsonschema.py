from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from jsonschema import Draft202012Validator

from kaliphonestudio.profiles import ProfileError, load_profile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT / "devices" / "profile.schema.json"
DEFAULT_DEVICES = ROOT / "devices"


def validate_repository_profiles(schema_path: Path, devices_root: Path) -> tuple[int, tuple[str, ...]]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)

    profile_paths = tuple(sorted(devices_root.glob("*/*/profile.json")))
    if not profile_paths:
        raise ValueError("device profile registry is empty")

    validated: list[str] = []
    for path in profile_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.absolute_path))
        if errors:
            rendered = "; ".join(
                f"{path}:{'/'.join(str(p) for p in error.absolute_path) or '<root>'}: {error.message}"
                for error in errors
            )
            raise ValueError(rendered)
        profile = load_profile(path)
        validated.append(profile.profile_id)

    return len(validated), tuple(validated)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate all KaliPhoneStudio device profiles against JSON Schema and runtime semantics."
    )
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--devices-root", type=Path, default=DEFAULT_DEVICES)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        count, profile_ids = validate_repository_profiles(args.schema, args.devices_root)
    except (OSError, json.JSONDecodeError, ValueError, ProfileError) as exc:
        print(f"device profile schema validation: FAIL: {exc}")
        return 2
    print("device profile schema validation: PASS")
    print(f"profiles: {count}")
    for profile_id in profile_ids:
        print(f"- {profile_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
