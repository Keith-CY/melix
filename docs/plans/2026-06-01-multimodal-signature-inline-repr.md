# Multimodal fast-path signature inline top-level representation

## Scope

This Python-only performance slice is limited to `fast_path_probe_signature()` in
`services/mlx-worker-python/worker/runtime/multimodal_fast_paths.py`.

The slice keeps signature semantics unchanged while reducing per-call overhead
for the fixed four top-level loaded-model fields used by the VLM fast-path probe
signature. It does not change metadata precedence, image preprocessing, cache
admission, or runtime decode behavior.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`multimodal-fast-path-signature-top-level-key-cache` in
`infra/perf/pr_scoped_probes.json`.

That registry entry already defines focused `test_command`, `coverage_command`,
and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/multimodal_fast_paths.py`
- `services/mlx-worker-python/tests/test_multimodal_fast_paths.py`
- `scripts/multimodal_fast_path_signature_probe.py`

## Measurement plan

Run the registered focused tests, changed-scope coverage command, and probe on
Linux before PR creation. The probe metric of record is `elapsed_ms_mean` with
lower values preferred; `peak_bytes_mean` remains a guardrail metric.

## Acceptance

Accept the slice only if behavior tests pass, changed-scope coverage remains at
or above repository policy for the touched path, and the registered probe shows a
clear non-regressing direction locally and in PR-scoped CI.
