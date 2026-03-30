# Phase 8 Cache Recovery Benchmarks

## Purpose

Inspect the machine-readable cache recovery benchmark evidence emitted as part of the Phase 8 release-gate benchmark bundle.

## Prerequisites

- Apple Silicon macOS host
- `swift`
- `python3`
- `uv`
- repository checkout with the local stack dependencies installed

## Generate The Evidence

Run the standard release gate:

```bash
make phase8-release-gate PHASE8_RELEASE_GATE_ARGS="--json"
```

The benchmark evidence now contains two artifacts:

- the existing bench markdown report
- a machine-readable cache recovery report named `cache-recovery-report.json`

## What The Cache Recovery Report Covers

The cache recovery report is split into four sections:

- `restart`
- `hot_tier`
- `cold_tier`
- `partial_restore`

The flattened benchmark metrics are also exposed under `benchmarks.recovery_metrics` in the release-gate JSON payload.

## Key Metric Names

Use these metric names when reviewing regressions or extending later release gates:

- `bench.recovery.restart_to_ready_ms`
- `bench.recovery.snapshot_restore_ms`
- `bench.recovery.restart_recovery_ms`
- `bench.recovery.restart_recovery_success_rate`
- `bench.recovery.hot_followup_ttft_delta_ms`
- `bench.recovery.hot_prefix_affinity_hit_rate`
- `bench.recovery.hot_warm_route_preference_rate`
- `bench.recovery.hot_restored_route_rate`
- `bench.recovery.cold_l2_hit_rate`
- `bench.recovery.partial_restore_ratio_pct`
- `bench.recovery.partial_restore_walk_back_count`
- `bench.recovery.partial_restore_restored_tokens`
- `bench.recovery.partial_restore_total_tokens`

## Interpretation

- `restart_*` measures persisted snapshot reuse across a worker restart.
- `hot_*` measures follow-up routing and TTFT improvement on a warm path.
- `cold_*` measures reuse promoted from the SSD-backed cold tier.
- `partial_restore_*` measures safe walk-back reuse when only a prompt prefix matches.

Higher hit rates and restore ratios are better. Lower restart, restore, and TTFT delta timings are better.

## Notes

- The release gate currently records this benchmark evidence for operator review and for later gate expansion.
- The primary release thresholds still live in `infra/release/phase8-release-gate-policy.json`.
