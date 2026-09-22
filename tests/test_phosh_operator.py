from __future__ import annotations

import pytest

from kaliphonestudio.phosh_operator import build_parser, main


def test_parser_exposes_exact_host_only_phosh_handoff_commands() -> None:
    parser = build_parser()
    help_text = parser.format_help()
    for command in (
        "build-first-boot-binding",
        "build-successor-candidate",
        "bind-physical-candidate",
    ):
        assert command in help_text
    assert "Host-only" in help_text
    assert "write phone storage" in help_text
    assert "grant Beta credit" in help_text


@pytest.mark.parametrize(
    "command",
    [
        "build-first-boot-binding",
        "build-successor-candidate",
        "bind-physical-candidate",
    ],
)
def test_each_phosh_handoff_subcommand_has_frozen_help(command: str) -> None:
    with pytest.raises(SystemExit) as exc:
        main([command, "--help"])
    assert exc.value.code == 0


def test_phosh_operator_fails_closed_without_required_inputs() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["bind-physical-candidate"])
    assert exc.value.code == 2
