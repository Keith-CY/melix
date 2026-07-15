# Stream Assembler Token Count Sum Cache

## Goal

Reduce repeated list summation in the Python request stream assembler token-count annotation hot path while preserving the existing token distribution semantics for content, reasoning, and tool-call deltas.

## Scope

- `services/mlx-worker-python/worker/runtime/stream_assembler.py`
- `services/mlx-worker-python/tests/test_stream_assembler.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/stream_assembler_token_bytes_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Registered Probe

The affected runtime path is covered by the registered PR-scoped probe `stream-assembler-token-byte-fast-decode` in `infra/perf/pr_scoped_probes.json`. This slice extends that probe script with a focused `token_count_annotation_ms_mean` local metric so the same PR-scoped probe workload exercises the `_annotate_token_counts(...)` multi-delta path directly, in addition to the existing token-byte and large ASCII token-count helper metrics.

The probe entry already keeps focused `test_command`, `coverage_command`, and `probe_command` fields and runs on `ubuntu-latest`, so Linux local verification and CI can both validate this Python-only slice without broadening registry scope.

## Implementation Plan

1. Preserve behavior with the existing focused stream assembler token annotation tests.
2. Extend `scripts/stream_assembler_token_bytes_probe.py` to time repeated multi-delta token-count annotation and emit a local `token_count_annotation_ms_mean` evidence metric.
3. Cache `sum(weights)` once inside `_annotate_token_counts(...)` and reuse it for branch selection and extra-token calculation.
4. Run focused tests, changed-scope coverage, and the registered probe locally on Linux.
5. Use the PR-scoped performance workflow report as the merge gate.

## Metrics

Primary registered metrics for this slice:

- `stream-assembler-token-byte-fast-decode.token_count_annotation_ms_mean` (lower is better)
- Existing context metrics: `elapsed_ms_mean`, `delta_token_count_new_ms_mean`, and `peak_bytes_mean`

Success requires behavior tests passing, changed-scope coverage at or above 95%, and no PR-scoped performance regression.
