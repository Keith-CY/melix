# CI Fast PR Gates Plan

## Goal

Reduce pull request feedback latency and macOS runner contention so multiple Melix
PRs can iterate concurrently without weakening the full pre-merge safety net.

## Current Bottleneck

The pull request gate runs broad macOS jobs on every push. The Swift test job is
the heaviest default gate because it runs all Swift packages and many
`RequestCoordinatorTests` cases serially inside one long macOS job. The packaged
app workflow also starts a full macOS packaging build for broad runtime path
changes, even when the PR only needs fast validation.

## Touched Files

- `.github/workflows/ci-pr.yml`
- `.github/workflows/package-self-contained-app.yml`
- `Makefile`

## Optimization Slice

- Split `make swift-test` into stable shard targets while preserving the
  existing aggregate `make swift-test` command for local and release workflows.
- Run PR Swift shards as a macOS matrix with a stable `swift-tests-report`
  aggregation job for branch protection.
- Remove Python environment bootstrap from the Swift-only PR job path.
- Restore dependency caches for Python, SwiftPM, package build directories, and
  the repository-local module cache in CI jobs that reuse those artifacts.
- Keep full integration tests on PRs when affected and always on merge queue
  events.
- Make the self-contained app package job opt-in on pull requests through a
  `package-app` label, while preserving manual, main, develop, and tag builds.

## Success Metrics

- PR Swift feedback can fan out across shards instead of waiting on one
  long-running serial job.
- Default PR pushes no longer start a full packaged app build unless the operator
  labels the PR with `package-app`.
- The required branch-protection surface can depend on stable aggregate checks:
  `swift-tests-report`, `python-tests`, `proto-drift`, `integration-tests` when
  selected, `pr-evidence`, and fast lint/scope checks.
- Full safety remains available through merge queue and release gates.

## Verification Commands

- `make swift-test-protocol`
- `make swift-test-control-request-coordinator-a`
- `actionlint .github/workflows/ci-pr.yml .github/workflows/package-self-contained-app.yml`
- `git diff --check`

## Metrics Report

The changed scope is CI configuration and command orchestration. Runtime coverage
is not applicable because no executable product code changes. Metrics are the
CI measurement points introduced by the workflow split: per-shard Swift job
duration, `swift-tests-report` completion time, and package workflow skipped vs.
executed counts on pull requests.
