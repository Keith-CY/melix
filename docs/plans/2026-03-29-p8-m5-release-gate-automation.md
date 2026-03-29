# P8-M5 Release Gate Automation

## Goal

Make Melix release candidates fail closed when install, benchmark, recovery, or training evidence is missing or regresses beyond the current deterministic thresholds.

## Scope

- add a repository-owned release gate policy
- add deterministic install, benchmark, training, and restart-recovery gate collection
- add a release gate CLI that returns machine-readable evidence
- add CI workflow integration for the Phase 8 release gate
- document how to run and interpret the release gate locally

## Files

- create `services/mlx-worker-python/worker/productization/release_gates.py`
- create `services/mlx-worker-python/tests/test_release_gates.py`
- create `scripts/phase8_release_gate.py`
- create `infra/release/README.md`
- create `infra/release/phase8-release-gate-policy.json`
- create `.github/workflows/release-gates.yml`
- create `docs/runbooks/phase-8-release-gates.md`
- update `Makefile`
- update `README.md`
- update `docs/README.md`
- update `docs/runbooks/README.md`

## Implementation Notes

- keep the gate deterministic and self-contained by reusing repository-owned runtimes and maintenance flows
- evaluate install, benchmark, training, and recovery evidence against a checked-in JSON policy
- fail closed when evidence is missing, malformed, or outside the configured thresholds
- keep script entrypoints thin and put measurable logic in Python modules covered by tests
- treat the workflow file as release-integration scaffolding rather than the only place where gates run

## Verification

- `make py-test`
- `make integration-test`
- `make phase8-release-gate PHASE8_RELEASE_GATE_ARGS="--json"`
- `make py-coverage`
- `git diff --check`

## Acceptance

- local release-gate execution returns structured evidence and exits non-zero on missing or regressed signals
- restart recovery is part of the release gate rather than a manual follow-up check
- release thresholds are versioned in the repository rather than hidden in scripts
- a repository workflow exists for running the same release gate in CI
