# Phase 8 Release Gates

## Purpose

Run the deterministic Phase 8 release gate and inspect the release evidence before merge or tagging.

## Prerequisites

- Apple Silicon macOS host
- `swift`
- `python3`
- `uv`
- repository checkout with built Swift products from the standard local workflow

## Run The Gate

Execute the release gate and emit JSON evidence:

```bash
make phase8-release-gate PHASE8_RELEASE_GATE_ARGS="--json"
```

The release gate checks:

- install asset generation
- benchmark thresholds
- evaluation thresholds
- evaluation comparison verdicts and paired confidence intervals
- cache recovery benchmark evidence
- restart recovery
- training sanity
- M9 ecosystem and security evidence

The command exits non-zero when:

- required evidence is missing
- a numeric threshold regresses past the checked-in policy
- restart recovery cannot restore a persisted snapshot

## Cache Recovery Benchmark Bundle

The benchmark section also emits a machine-readable cache recovery report alongside the bench markdown report.

See:

```bash
docs/runbooks/phase-8-cache-recovery-benchmarks.md
```

Use that report when you need to inspect:

- hot-tier follow-up TTFT improvement
- cold-tier L2 reuse
- partial-prefix walk-back reuse
- restart plus restore timing splits

## Policy

The gate thresholds are versioned in:

```bash
infra/release/phase8-release-gate-policy.json
```

Update the policy in the same change as any intentional benchmark or release-threshold adjustment.

The checked-in policy now includes an `evaluation` section for deterministic suite metrics such as
`eval.mmlu.accuracy`. Treat benchmark and evaluation regressions as first-class release inputs.

The checked-in policy also includes an `evaluation_compare` section for paired compare suites such
as `mmlu`. Each suite policy owns:

- `confidence_level`
- `bootstrap_iterations`
- `bootstrap_seed`
- `effect_threshold`
- `required_verdict`

The compare release verdict is policy-backed and uses the same `CI + threshold` rule as runtime
reporting:

- `improvement` only when delta clears the positive effect threshold and both interval families stay
  above zero
- `regression` only when delta clears the negative effect threshold and both interval families stay
  below zero
- `inconclusive` otherwise

The checked-in policy also includes an `m9` section for repository-owned ecosystem and security
signals. The current required M9 probes include:

- MCP auto-injection metrics
- agent export smoke metrics
- shared-access gateway metrics
- persistent-session recovery metrics
- sanitization enforcement metrics
- connection-lifecycle recovery metrics
- closure-audit blocker and evidence-gap metrics

The Phase 8 gate fails closed when:

- any required `m9` probe is missing
- any checked-in `m9` threshold regresses
- the closure audit reports blockers or evidence gaps

Interpret the top-level M9 counters as:

- `release_gate.m9_required_probe_count`: number of policy-backed M9 probes that must be present
- `release_gate.m9_missing_probe_count`: required M9 probes that were not emitted by the evidence collectors
- `release_gate.m9_failed_threshold_count`: required M9 probes that emitted data but violated the checked-in policy

To exercise the deterministic M9-only release-gate fixtures without running the full Phase 8 gate:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" \
uv run --project services/mlx-worker-python python scripts/m9_release_gate_smoke.py --repo-root "$(pwd)" --json
```

Use `--fixture-mode failing` to prove the gate fails closed on missing or regressed M9 evidence.

When you inspect the emitted release-gate JSON, the top-level `evaluation_compare` section is the
operator-facing summary for compare evidence. Verify:

- `verdict` matches the policy-required verdict
- `effect_threshold` is at least the checked-in policy value
- both `bootstrap` and `analytical` intervals are present under `statistical_evidence`
- `release_gate_summary` explains whether a compare was accepted or rejected

## CI Workflow

The repository workflow entrypoint for the same gate is:

```bash
.github/workflows/release-gates.yml
```

Use the local gate first when adjusting thresholds or release evidence collection.
