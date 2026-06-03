# Daily Main App Packaging CI Plan

## Goal

Run the existing self-contained Melix app packaging workflow every day at 00:00 UTC on `main`, and package the app only when `main` has changed since the last successful scheduled app artifact.

## Architecture

Extend `.github/workflows/package-self-contained-app.yml` rather than creating a second packaging workflow. A scheduled-only preflight job queries previous successful scheduled runs of the same workflow, verifies that a matching Melix app artifact exists, and compares that run's `head_sha` with the current scheduled `main` SHA. The existing packaging job runs unchanged for manual, push, tag, and labeled PR events, while scheduled runs enter the packaging path only when the preflight reports a new `main` commit.

Scheduled runs use an event-scoped concurrency key so a daily archive cannot cancel an in-progress `main` push package for the same ref.

## Scope

- Add a daily `schedule` trigger with `cron: "0 0 * * *"`.
- Add scheduled preflight summary output for both package and no-package decisions.
- Keep current manual, push, tag, and PR label behavior intact.
- Isolate scheduled concurrency from push and manual package runs on the same ref.
- Upload nightly-style app artifacts with `retention-days: 14`.
- Add focused workflow regression tests.

## Files

- Modify `.github/workflows/package-self-contained-app.yml`.
- Modify `services/mlx-worker-python/tests/test_package_macos_menubar_app_script.py`.

## Verification

- Focused pytest:
  `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_package_macos_menubar_app_script.py -q`
- Workflow lint when available:
  `actionlint .github/workflows/package-self-contained-app.yml`
- Whitespace check:
  `git diff --check`

## Coverage and Metrics

Changed scope is GitHub Actions YAML plus Python workflow text tests. Runtime performance probes are `N/A` because the change does not alter Melix runtime, worker, Swift app, or packaging implementation code paths; it only changes when an existing CI packaging path runs and how long artifacts are retained.

- Coverage: `N/A` for production code because no production Python, Swift, or generated protocol code changes.
- Metrics: `N/A` because there is no runtime execution path or performance-sensitive code path change.
- Observability mode: minimal CI summary output for scheduled package or skip decisions.
- Probe overhead: `N/A`; no runtime probes are added.

## Implementation Steps

1. Add failing workflow tests for the daily trigger, scheduled preflight, scheduled skip summary, package job gate, and artifact retention.
2. Run the focused pytest and confirm those tests fail against the current workflow.
3. Update the workflow with the schedule trigger, preflight job, package job condition, needs wiring, summary text, and retention.
4. Run the focused pytest until it passes.
5. Run `actionlint` if installed and `git diff --check`.
6. Review the final diff against the user-approved design.
