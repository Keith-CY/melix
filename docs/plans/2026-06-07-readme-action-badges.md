# README Action Badge Repair Plan

## Goal

Restore the root README action badges so they report meaningful release and app packaging status for `main`.

## Diagnosis

- The `release-gates` workflow was manually disabled in GitHub Actions, leaving the README badge stuck on the latest historical failed or cancelled main run.
- Main push-triggered `release-gates` runs also cancelled earlier main runs, so a fast merge sequence could leave the branch badge red even when no release gate failed.
- The `package-self-contained-app` workflow is healthy, but the README badge queries all `main` workflow runs. Frequent push-triggered packaging runs can be cancelled by concurrency when newer main commits land, so the badge can briefly report failure even when the scheduled app artifact path is healthy.

## Scope

- Re-enable the `release-gates` workflow in GitHub Actions and trigger a fresh `main` run.
- Keep the release-gates README badge on `main` so real gate failures remain visible.
- Keep main push-triggered `release-gates` runs from cancelling each other, while preserving cancellation for repeated non-main/manual/scheduled runs.
- Scope the app packaging README badge to the scheduled packaging event, which is the durable public app artifact signal.
- Add a focused README regression test for the badge URLs.

## Verification

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_readme_action_badges.py -q`
- `actionlint .github/workflows/release-gates.yml .github/workflows/package-self-contained-app.yml` when available
- `git diff --check`
- GitHub Actions status for `release-gates.yml` and `package-self-contained-app.yml`

## Coverage and Metrics

- Coverage: focused README badge URL regression coverage.
- Metrics: `N/A`; the change is documentation and CI-status presentation only. It does not alter runtime, worker, Swift app, or packaging implementation performance paths.
