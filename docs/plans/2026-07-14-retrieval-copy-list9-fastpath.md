# Retrieval copy list9 fast path

## Scope

This Python-only performance slice targets the lookup payload copy helper in
`services/mlx-worker-python/worker/runtime/retrieval_context.py`. The change is
limited to explicit copy fast paths for exactly nine-item JSON-like list and
tuple payloads used by retrieval lookup metadata.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`retrieval-context-projection-fastpath` in `infra/perf/pr_scoped_probes.json`.
That probe already defines focused `test_command`, `coverage_command`, and
`probe_command` entries. This slice extends the existing probe workload with
nine-item list and tuple windows so CI compares `origin/main` against the head
implementation using the same registered probe script.

## Plan

1. Add regression coverage proving nine-item lookup payload lists and tuples are
   copied with the same deep-copy semantics as existing short payload windows.
2. Add explicit nine-item list and tuple branches in `_copy_payload_value()`.
3. Extend `scripts/retrieval_context_projection_probe.py` with representative
   nine-item metadata windows.
4. Run the registered focused tests, changed-scope coverage command, and probe
   locally on Linux before opening the PR.

## Metrics

Primary metric: `lookup_copy_optimized_elapsed_ms_mean` and
`lookup_copy_delta_ms` from `scripts/retrieval_context_projection_probe.py`.
The PR-scoped performance workflow remains the merge gate for the registered
probe report.
