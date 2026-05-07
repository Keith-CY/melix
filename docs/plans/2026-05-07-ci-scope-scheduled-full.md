# CI Scope Gates And Scheduled Full Regression

## Goal

Reduce pull-request CI queue pressure by running heavyweight macOS jobs only
when the changed paths require them, while preserving a complete repository
regression signal on a four-hour scheduled workflow.

## Scope

- Add a repository-owned path classifier for `ci-pr`.
- Gate `proto-drift`, Swift shards, Python tests, and integration tests from
  the classifier output.
- Keep `swift-tests-report` as the stable Swift aggregate check and let it pass
  explicitly when Swift tests are skipped by scope.
- Add a scheduled full regression workflow that runs every four hours and can
  also be triggered manually.

Out of scope:

- Changing the existing local `make swift-test` aggregate.
- Changing branch protection rules.
- Fixing unrelated Swift test failures such as missing runner metallib state.

## Metrics And Success Targets

- Docs-only pull requests do not enqueue macOS Swift, protocol, Python, or
  integration jobs.
- Python-only pull requests do not enqueue Swift shards.
- Swift or protocol pull requests still enqueue the relevant macOS checks.
- Full regression still runs `make proto-check`, `make swift-test`,
  `make py-test`, and `make integration-test` every four hours.
- Workflow-only, Makefile, dependency, or toolchain changes conservatively run
  every `ci-pr` test family.

## Verification

- `uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_ci_scope.py -q`
- `python3 -m py_compile scripts/ci_scope.py`
- `ruby -e 'require "yaml"; YAML.load_file(".github/workflows/ci-pr.yml"); YAML.load_file(".github/workflows/ci-full-scheduled.yml")'`
- `git diff --check`
