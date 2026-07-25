# Multimodal fast-path signature processor-key probe

## Scope

This Python-only performance slice is limited to the processor-metadata presence
check used by `fast_path_probe_signature(...)` in
`services/mlx-worker-python/worker/runtime/multimodal_fast_paths.py`.

The behavior contract stays unchanged: image/video requests still include
processor metadata in the signature only when one of the fixed processor metadata
keys is present and non-empty on the loaded model or its nested `metadata`
dictionary. Text/no-media signatures continue to use only core metadata keys.

## Registered probe

The affected path is already covered by the registered PR-scoped probe
`multimodal-fast-path-signature-top-level-key-cache` in
`infra/perf/pr_scoped_probes.json`.

The probe entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/multimodal_fast_paths.py`
- `services/mlx-worker-python/tests/test_multimodal_fast_paths.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/multimodal_fast_path_signature_probe.py`

This slice uses the registered probe's `elapsed_ms_mean` as the primary metric
because the workload repeatedly calls `fast_path_probe_signature(...)` against a
representative VLM loaded-model dictionary with no processor metadata present.

## Implementation plan

1. Keep the existing signature behavior tests as guards, including nested
   metadata precedence and processor-key expansion behavior.
2. Reuse a pre-sorted tuple of fixed processor metadata keys for the hot presence
   probe.
3. Avoid the generic `frozenset.isdisjoint(...)` source scan for the registered
   processor-key path while preserving the generic helper behavior for other key
   sets.
4. Run the registered focused tests, changed-scope coverage command, and
   registered probe locally on Linux.
5. Use GitHub Actions PR-scoped performance as the merge gate after push.

## Success criteria

- Focused multimodal fast-path tests pass.
- Changed-scope coverage remains at or above the repository threshold for touched files.
- The registered probe reports directionally lower `elapsed_ms_mean` locally and
  in CI without introducing gated regressions.
- Hosted `multimodal-fast-path-signature-top-level-key-cache` PR-scoped CI
  completes successfully before merge.
