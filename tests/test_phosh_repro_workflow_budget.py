from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/phosh-rootfs-reproducibility.yml"
BUILD_SCRIPT = ROOT / "scripts/run_locked_phosh_rootfs_build.py"
_MIN_OVERHEAD_SECONDS = 20 * 60


def _real_build_block(text: str) -> str:
    prefix = "\n  real-build:\n"
    suffix = "\n  compare:\n"
    assert prefix in text and suffix in text
    return text.split(prefix, 1)[1].split(suffix, 1)[0]


def _compare_block(text: str) -> str:
    prefix = "\n  compare:\n"
    suffix = "\n  materialize-candidate:\n"
    assert prefix in text and suffix in text
    return text.split(prefix, 1)[1].split(suffix, 1)[0]


def test_real_build_job_budget_covers_both_bounded_build_stages() -> None:
    workflow_text = WORKFLOW.read_text(encoding="utf-8")
    real_build = _real_build_block(workflow_text)

    job_match = re.search(r"(?m)^    timeout-minutes:\s*(\d+)\s*$", real_build)
    stage_match = re.search(r"--timeout\s+(\d+)", real_build)
    assert job_match and stage_match

    job_budget_seconds = int(job_match.group(1)) * 60
    stage_timeout_seconds = int(stage_match.group(1))
    build_script = BUILD_SCRIPT.read_text(encoding="utf-8")
    bounded_stage_runs = len(
        re.findall(r"\b_run\(plan\.(?:base|stage)_argv,", build_script)
    )
    assert bounded_stage_runs == 2

    required_seconds = (
        bounded_stage_runs * stage_timeout_seconds + _MIN_OVERHEAD_SECONDS
    )
    assert job_budget_seconds >= required_seconds, (
        f"Phosh A/B real-build timeout budget is too small: {job_budget_seconds}s "
        f"< {required_seconds}s for {bounded_stage_runs} bounded build stages plus overhead"
    )


def test_member_diagnostics_do_not_block_a_successful_strict_compare() -> None:
    workflow_text = WORKFLOW.read_text(encoding="utf-8")
    real_build = _real_build_block(workflow_text)
    compare = _compare_block(workflow_text)

    assert "Create exact member-level drift evidence" not in real_build
    assert "phosh-members.json" not in real_build
    assert "evidence/phosh-members.json" not in real_build

    strict_label = "name: Create review-required A/B reproducibility candidate"
    payload_label = "name: Download exact A/B payloads for mismatch diagnostics"
    member_label = "name: Create exact member-level drift evidence after strict mismatch"
    diagnostic_label = "name: Diagnose exact A/B member drift without promoting authority"
    fail_label = "name: Fail closed after strict A/B mismatch"

    strict_index = compare.index(strict_label)
    payload_index = compare.index(payload_label)
    member_index = compare.index(member_label)
    diagnostic_index = compare.index(diagnostic_label)
    fail_index = compare.index(fail_label)
    assert strict_index < payload_index < member_index < diagnostic_index < fail_index

    strict_section = compare[strict_index:payload_index]
    assert "id: strict_compare" in strict_section
    assert "continue-on-error: true" in strict_section

    mismatch_condition = "steps.strict_compare.outcome == 'failure'"
    for label in (payload_label, member_label, diagnostic_label, fail_label):
        section = compare[compare.index(label):]
        section = section.split("\n      - name:", 1)[0]
        assert mismatch_condition in section

    success_upload = compare[
        compare.index("name: Upload reproducibility-candidate evidence"):payload_index
    ]
    assert "steps.strict_compare.outcome == 'success'" in success_upload

    final_failure = compare[fail_index:]
    assert "exit 2" in final_failure


def test_both_exact_payloads_are_preserved_for_post_compare_use() -> None:
    workflow_text = WORKFLOW.read_text(encoding="utf-8")
    real_build = _real_build_block(workflow_text)

    assert (
        "name: phosh-rootfs-real-build-${{ matrix.build-id }}-payload" in real_build
    )
    assert "path: artifacts/phosh-${{ matrix.build-id }}.tar.xz" in real_build
    assert "compression-level: 0" in real_build
