# M9.7 Security And Stability Closure Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a repository-owned closure audit for the completed Melix roadmap surface so residual security and stability gaps are explicit, reproducible, and ready for release-gate consumption.

**Architecture:** Collect deterministic evidence from repository-owned probes, runbooks, and newly landed M9 metrics, score the resulting findings into blockers versus accepted residual risk, and emit both human-readable and machine-readable audit artifacts. Keep the audit lightweight enough to run in CI and explicit enough for future milestone closure work.

**Tech Stack:** Python 3.12, pytest, repository-owned audit schema, Markdown runbooks and decision records.

---

## Scope Notes

- The audit must consume repository-owned evidence only; no hidden external spreadsheet or manual checklist is allowed.
- Findings must distinguish actionable blockers, follow-up work, and accepted residual risk.
- The audit is not a generic scanner; it is a Melix-specific closure summary grounded in the roadmap probes that now exist.

## Performance Probes And Success Metrics

- `closure_audit.blocker_count`
- `closure_audit.accepted_risk_count`
- `closure_audit.evidence_gap_count`

## Task 1: Add A Typed Closure-Audit Evidence Model

**Files:**
- Add: `services/mlx-worker-python/worker/productization/closure_audit.py`
- Add: `services/mlx-worker-python/tests/test_closure_audit.py`

- [ ] Define a typed audit schema for finding severity, finding category, probe coverage, evidence source, and required follow-up.
- [ ] Implement deterministic audit assembly that ingests release-gate evidence, metrics-report probe presence, and required M9 runbook artifacts.
- [ ] Add failing and then passing tests for blocker classification, accepted-risk classification, evidence-gap detection, and stable JSON emission.

## Task 2: Add Repository-Owned Audit Outputs And Decision Logging

**Files:**
- Add: `scripts/m9_closure_audit.py`
- Add: `docs/runbooks/security-and-stability-closure.md`
- Add: `docs/decisions/2026-04-02-m9-security-stability-closure-audit.md`

- [ ] Add a CLI wrapper that emits JSON audit evidence and returns non-zero only when blocking findings remain.
- [ ] Write a repository-owned runbook describing how to run the closure audit, interpret results, and file follow-up work.
- [ ] Record the first audit decision document with blocker, accepted-risk, and deferred-work sections populated from real evidence.

## Task 3: Feed Audit State Into Acceptance Metrics

**Files:**
- Modify: `services/mlx-worker-python/worker/productization/acceptance_metrics.py`
- Modify: `services/mlx-worker-python/tests/test_acceptance_metrics.py`

- [ ] Extend acceptance metrics so the phase metrics report can surface closure-audit counts and top unresolved findings.
- [ ] Add failing and then passing tests that assert the new closure-audit metrics appear in machine-readable output with stable names.
- [ ] Record `closure_audit.blocker_count`, `closure_audit.accepted_risk_count`, and `closure_audit.evidence_gap_count`.

## Verification And Commit Gate

- [ ] Run targeted verification:
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_closure_audit.py services/mlx-worker-python/tests/test_acceptance_metrics.py -q`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python python scripts/m9_closure_audit.py --repo-root "$(pwd)" --json`
- [ ] Measure changed-line coverage for the touched Python scope and confirm coverage is at least `95%`.
- [ ] Record the changed-scope metrics report for `closure_audit.blocker_count`, `closure_audit.accepted_risk_count`, and `closure_audit.evidence_gap_count`.
- [ ] Commit Task 7:
  - `git add services/mlx-worker-python/worker/productization/closure_audit.py services/mlx-worker-python/worker/productization/acceptance_metrics.py services/mlx-worker-python/tests/test_closure_audit.py services/mlx-worker-python/tests/test_acceptance_metrics.py scripts/m9_closure_audit.py docs/runbooks/security-and-stability-closure.md docs/decisions/2026-04-02-m9-security-stability-closure-audit.md docs/plans/2026-03-30-m9-7-security-and-stability-closure-audit.md`
  - `git commit -m "feat: add security and stability closure audit"`
