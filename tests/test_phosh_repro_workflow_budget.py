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
