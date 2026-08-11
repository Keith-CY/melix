from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
TOOLCHAIN_ACTION_PATH = ".github/actions/setup-melix-swift-toolchain/action.yml"
TOOLCHAIN_ACTION_USE_SUFFIX = "/.github/actions/setup-melix-swift-toolchain"
SWIFT_WORKFLOW_JOBS = {
    ".github/workflows/bench-eval-report.yml": ("report",),
    ".github/workflows/ci-full-scheduled.yml": ("full-regression",),
    ".github/workflows/ci-pr.yml": ("proto-drift", "swift-tests", "integration-tests"),
    ".github/workflows/package-self-contained-app.yml": (
        "package-app",
        "publish-signed-release",
    ),
    ".github/workflows/release-gates.yml": ("release-gates",),
}


def _load_yaml(relative_path: str) -> dict[str, object]:
    payload = yaml.safe_load((REPO_ROOT / relative_path).read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


@pytest.mark.parametrize(
    ("workflow_path", "job_name"),
    [
        (workflow_path, job_name)
        for workflow_path, job_names in SWIFT_WORKFLOW_JOBS.items()
        for job_name in job_names
    ],
)
def test_swift_build_jobs_use_macos_26_and_the_shared_toolchain_action(
    workflow_path: str,
    job_name: str,
) -> None:
    workflow = _load_yaml(workflow_path)
    job = workflow["jobs"][job_name]

    assert job["runs-on"] == "macos-26"
    assert any(
        step.get("uses", "").endswith(TOOLCHAIN_ACTION_USE_SUFFIX)
        for step in job["steps"]
        if isinstance(step, dict)
    )


def test_macos_performance_probes_use_the_swift_6_3_runner() -> None:
    registry = json.loads(
        (REPO_ROOT / "infra/perf/pr_scoped_probes.json").read_text(encoding="utf-8")
    )
    macos_probes = [probe for probe in registry if probe["runner"].startswith("macos-")]

    assert macos_probes
    assert {probe["runner"] for probe in macos_probes} == {"macos-26"}

    workflow = _load_yaml(".github/workflows/pr-scoped-performance.yml")
    probes_job = workflow["jobs"]["probes"]
    assert probes_job["runs-on"] == "${{ matrix.runner }}"
    assert any(
        step.get("uses") == "./head/.github/actions/setup-melix-swift-toolchain"
        for step in probes_job["steps"]
        if isinstance(step, dict)
    )


def test_shared_toolchain_action_pins_xcode_swift_and_cache_namespace() -> None:
    action = _load_yaml(TOOLCHAIN_ACTION_PATH)
    select_step = action["runs"]["steps"][0]
    script = select_step["run"]

    assert select_step["name"] == "Select Xcode 26.5 and verify Swift 6.3"
    assert 'xcode_version="26.5"' in script
    assert 'swift_version_prefix="6.3"' in script
    assert 'developer_dir="/Applications/Xcode_${xcode_version}.app/Contents/Developer"' in script
    assert "xcode-26-5-swift-6-3" in script
    assert 'exit 1' in script
