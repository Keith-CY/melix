# Closure Audit Dataclass Slots Performance Slice

## Context

The registered PR-scoped probe `closure-audit-probe-source-short-circuit` covers `services/mlx-worker-python/worker/productization/closure_audit.py`. The audit builds multiple immutable finding/report objects while scanning repository-owned M9 evidence.

## Slice

Add `slots=True` to `ClosureAuditFinding` and `ClosureAuditReport`, and reuse a zeroed severity-metric template when aggregating finding metrics. These dataclasses are immutable value records and do not require dynamic instance dictionaries. Slotting them lowers per-instance allocation overhead, while copying the template avoids rebuilding the same metric-key dictionary for every audit. Both changes preserve the public `to_dict()` output and report rendering behavior.

## Validation

Use the existing registered probe and focused coverage commands from `infra/perf/pr_scoped_probes.json`:

- `closure-audit-probe-source-short-circuit` focused test command
- `closure-audit-probe-source-short-circuit` changed-scope coverage command
- `closure-audit-probe-source-short-circuit` registered probe command

Success requires focused tests and changed-scope coverage to pass. The registered probe should show lower or neutral elapsed/peak memory metrics and unchanged probe file read counts.
