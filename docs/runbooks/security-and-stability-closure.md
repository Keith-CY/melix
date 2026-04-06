# Security And Stability Closure

## Purpose

Run the repository-owned M9 closure audit so Melix can classify residual security and stability findings without relying on an external spreadsheet or a manual checklist.

The audit consumes repository evidence for the completed M9 ecosystem slices and emits a deterministic JSON artifact with:

- blocker findings
- accepted residual risks
- evidence gaps
- deferred follow-up work

## Scope

This runbook covers the first executable `M9.7` slice only.

It verifies repository-owned evidence for:

- shared access
- persistent sessions
- rich-output sanitization
- connection lifecycle recovery
- release-gate hand-off readiness

It does not attempt external scanning, penetration testing, or live third-party tool launch coverage.

## Preconditions

- repository checkout
- `python3`
- `uv`
- the standard Melix Python workspace under `services/mlx-worker-python`

## Evidence Inputs

The closure audit reads these repository-owned inputs:

- `docs/plans/2026-03-30-full-capability-roadmap-execution-index.md`
- `docs/plans/2026-03-30-m9-7-security-and-stability-closure-audit.md`
- `infra/release/phase8-release-gate-policy.json`
- `scripts/phase8_metrics_report.py`
- `docs/runbooks/phase-8-release-gates.md`
- `docs/runbooks/mcp-tooling.md`
- `docs/runbooks/external-agent-integrations.md`
- `docs/runbooks/shared-access.md`
- `docs/runbooks/persistent-sessions.md`
- `docs/runbooks/rich-output-sanitization.md`
- `docs/runbooks/connection-lifecycle.md`

The current probe vocabulary required by the audit is:

- `gateway.accepted_api_key_count`
- `shared_access.accepted_client_count`
- `shared_access.rejected_request_count`
- `persistent_session.restore_success_rate`
- `persistent_session.sign_out_latency_ms`
- `sanitized_output.enforcement_count`
- `sanitized_output.blocked_html_fragment_count`
- `sanitized_output.unsafe_uri_rejection_count`
- `disconnect.keepalive_gap_ms`
- `disconnect.recovery_latency_ms`
- `disconnect.resume_success_rate`
- `disconnect.terminal_failure_count`

## Run The Audit

Emit the machine-readable audit and save it under `.runtime/`:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
UV_CACHE_DIR="$(pwd)/.uv-cache" \
uv run --project services/mlx-worker-python \
python scripts/m9_closure_audit.py --repo-root "$(pwd)" --json
```

Default output path:

```bash
.runtime/m9-closure-audit/closure-audit.json
```

The command exits non-zero only when blocker findings remain.

## Interpretation

Interpret the counts this way:

- `closure_audit.blocker_count`
  - repository closure is not release-ready for the covered M9 surface
- `closure_audit.accepted_risk_count`
  - the repository intentionally keeps documented residual risk inside the accepted scope boundary
- `closure_audit.evidence_gap_count`
  - a required runbook, policy artifact, or probe vocabulary is missing
- `closure_audit.deferred_work_count`
  - follow-up work exists, but the current covered surface can still be audited deterministically

Typical outcomes:

- `0 blockers`, `0 evidence gaps`
  - the current repository evidence is internally complete for the audited M9 surface
- non-zero `accepted_risk_count`
  - the repository has documented scope limits that still need to be carried into release review
- non-zero `deferred_work_count`
  - later milestones still need to consume the audit, but the audit itself is usable

## File Follow-Up Work

When the audit reports findings:

- blockers
  - file or update the relevant milestone transaction before merge
- evidence gaps
  - restore the missing runbook, probe name, or policy artifact in the same change if possible
- accepted risks
  - update the active decision record if the accepted boundary changes
- deferred work
  - link the finding to the next milestone that consumes the evidence

The current downstream consumer is:

- `docs/plans/2026-03-30-m9-8-ecosystem-and-security-release-gates.md`

## Metrics

`M9.7` records these machine-readable metrics:

- `closure_audit.blocker_count`
- `closure_audit.accepted_risk_count`
- `closure_audit.evidence_gap_count`
- `closure_audit.deferred_work_count`

## Release-Gate Hand-Off

This audit is preparatory evidence for the later release-gate wiring work.

Use it together with:

- `docs/runbooks/phase-8-release-gates.md`
- `docs/runbooks/phase-8-product-acceptance.md`
- `docs/plans/2026-03-30-m9-8-ecosystem-and-security-release-gates.md`

`M9.7` does not by itself make closure-audit findings fail the existing Phase 8 release gate.

## Troubleshooting

- If the audit reports missing probe vocabulary, confirm the expected metric names still exist in the repository-owned smoke scripts, tests, or runbooks after any refactor.
- If the audit reports missing release-gate assets, restore `infra/release/phase8-release-gate-policy.json`, `scripts/phase8_metrics_report.py`, or the Phase 8 gate runbook before treating the closure evidence as complete.
- If the audit unexpectedly reports blockers for completed milestones, verify the wording in `docs/plans/2026-03-30-full-capability-roadmap-execution-index.md` still uses `Status: completed`.
