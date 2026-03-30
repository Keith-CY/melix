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
- cache recovery benchmark evidence
- restart recovery
- training sanity

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

## CI Workflow

The repository workflow entrypoint for the same gate is:

```bash
.github/workflows/release-gates.yml
```

Use the local gate first when adjusting thresholds or release evidence collection.
