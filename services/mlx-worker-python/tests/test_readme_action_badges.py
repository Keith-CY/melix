from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
README = REPO_ROOT / "README.md"
RELEASE_GATES_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release-gates.yml"


def test_release_gates_badge_reports_main_branch_status() -> None:
    readme = README.read_text(encoding="utf-8")

    assert (
        "img.shields.io/github/actions/workflow/status/"
        "Keith-CY/melix/release-gates.yml?branch=main&label=release%20gates"
    ) in readme


def test_app_packaging_badge_reports_scheduled_main_artifact_status() -> None:
    readme = README.read_text(encoding="utf-8")

    assert (
        "img.shields.io/github/actions/workflow/status/"
        "Keith-CY/melix/package-self-contained-app.yml?"
        "branch=main&event=schedule&label=app%20packaging"
    ) in readme
    assert "actions/workflows/package-self-contained-app.yml?query=event%3Aschedule+branch%3Amain" in readme


def test_release_gates_main_push_runs_are_not_cancelled_by_later_main_pushes() -> None:
    workflow = RELEASE_GATES_WORKFLOW.read_text(encoding="utf-8")

    assert "release-gates-${{ github.event_name }}-${{ github.ref }}" in workflow
    assert "github.event_name != 'push' || github.ref != 'refs/heads/main'" in workflow
