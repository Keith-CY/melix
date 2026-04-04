# M9.8 Ecosystem And Security Release Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend Melix release-gate automation so ecosystem-integration readiness, closure-audit evidence, sanitization enforcement, and connection-lifecycle recovery become formal machine-readable release requirements.

**Architecture:** Reuse the existing phase-8 gate and metrics pipeline, add deterministic evidence collectors for the new M9 surfaces, and fail closed when required M9 evidence or thresholds are missing. Keep the policy in versioned JSON and preserve a clear split between hard blockers and informational metrics.

**Tech Stack:** Python 3.12, pytest, repository-owned release-gate policy JSON, smoke scripts, metrics-report helpers.

---

## Scope Notes

- Gate inputs must come from repository-owned evidence collectors, not manual assertions in CI configuration.
- The policy must remain machine-readable and diffable.
- M9 gate additions should layer on top of the existing phase-8 release gate rather than creating a second unrelated gate system.

## Performance Probes And Success Metrics

- `release_gate.m9_required_probe_count`
- `release_gate.m9_missing_probe_count`
- `release_gate.m9_failed_threshold_count`

## Task 1: Add M9 Evidence Collectors To Release-Gate Logic

**Files:**
- Modify: `services/mlx-worker-python/worker/productization/release_gates.py`
- Modify: `services/mlx-worker-python/worker/productization/acceptance_metrics.py`
- Modify: `scripts/phase8_release_gate.py`
- Modify: `scripts/phase8_metrics_report.py`
- Modify: `services/mlx-worker-python/tests/test_release_gates.py`
- Modify: `services/mlx-worker-python/tests/test_phase8_release_gate.py`
- Modify: `services/mlx-worker-python/tests/test_phase8_runtime_probes.py`
- Modify: `services/mlx-worker-python/tests/test_acceptance_metrics.py`

- [x] Add typed evidence collectors for MCP auto-injection, agent export smoke, shared-access smoke, persistent-session smoke, sanitization smoke, connection-lifecycle smoke, and closure-audit output.
- [x] Feed those collectors into the release gate and metrics report with stable field names and deterministic local-fixture data.
- [x] Add failing and then passing tests for missing-evidence failure, threshold failure, and success with complete M9 evidence.

## Task 2: Version M9 Release Policy And Runbook Expectations

**Files:**
- Modify: `infra/release/phase8-release-gate-policy.json`
- Modify: `docs/runbooks/phase-8-release-gates.md`
- Modify: `docs/runbooks/phase-8-product-acceptance.md`

- [x] Extend the release-gate policy JSON with thresholds for M9 probes and counts, including missing-probe and failed-threshold behavior.
- [x] Document how M9 ecosystem and security signals influence the release decision and how to interpret failures.
- [x] Keep the runbook examples synchronized with the actual gate and metrics commands.

## Task 3: Add End-To-End Gate Smoke Coverage

**Files:**
- Add: `scripts/m9_release_gate_smoke.py`
- Add: `services/mlx-worker-python/tests/test_m9_release_gate_smoke.py`

- [x] Add a deterministic smoke command that assembles fixture M9 evidence, runs the updated release gate, and emits machine-readable pass or fail output.
- [x] Add tests that verify the smoke command covers both passing and failing gate states.
- [x] Record `release_gate.m9_required_probe_count`, `release_gate.m9_missing_probe_count`, and `release_gate.m9_failed_threshold_count`.

## Verification And Commit Gate

- [x] Run targeted verification:
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_release_gates.py services/mlx-worker-python/tests/test_phase8_release_gate.py services/mlx-worker-python/tests/test_phase8_runtime_probes.py services/mlx-worker-python/tests/test_acceptance_metrics.py services/mlx-worker-python/tests/test_m9_release_gate_smoke.py -q`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python python scripts/m9_release_gate_smoke.py --json`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python python scripts/phase8_release_gate.py --repo-root "$(pwd)" --json`
- [x] Measure changed-line coverage for the touched Python scope and confirm coverage is at least `95%`.
- [x] Record the changed-scope metrics report for `release_gate.m9_required_probe_count`, `release_gate.m9_missing_probe_count`, and `release_gate.m9_failed_threshold_count`.
- [x] Commit Task 8:
  - `git add services/mlx-worker-python/worker/productization/release_gates.py services/mlx-worker-python/worker/productization/acceptance_metrics.py services/mlx-worker-python/tests/test_release_gates.py services/mlx-worker-python/tests/test_phase8_release_gate.py services/mlx-worker-python/tests/test_phase8_runtime_probes.py services/mlx-worker-python/tests/test_acceptance_metrics.py services/mlx-worker-python/tests/test_m9_release_gate_smoke.py scripts/phase8_release_gate.py scripts/phase8_metrics_report.py scripts/m9_release_gate_smoke.py infra/release/phase8-release-gate-policy.json docs/runbooks/phase-8-release-gates.md docs/runbooks/phase-8-product-acceptance.md docs/plans/2026-03-30-m9-8-ecosystem-and-security-release-gates.md`
  - `git commit -m "feat: add M9 ecosystem and security release gates"`
