# Real model HF cache fallback cache

## Scope

This Python-only performance slice is limited to the Hugging Face cache fallback
path in `scripts/real_model_support.py`, specifically repeated resolution of the
same model snapshot when `refs/main` is unavailable and the resolver must inspect
`$HOME/.cache/huggingface/hub/.../snapshots`.

## Registered performance probe

The affected path is already covered by the registered PR-scoped probe
`real-model-support-hf-cache-latest-snapshot` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries and watches:

- `scripts/real_model_support.py`
- `tests/test_real_model_support.py`
- `scripts/real_model_support_hf_cache_probe.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

Primary metrics: `hf_cache_elapsed_ms_mean` and `hf_cache_peak_bytes_mean` should
move lower for repeated fallback resolution. The weight preflight metric is a
same-probe guard and is not expected to change.

## Implementation plan

1. Preserve explicit env path, managed-root, and `refs/main` behavior unchanged.
2. Cache only the fallback snapshot-directory scan result after `refs/main` is
   unavailable.
3. Key the cache by model id, resolved cache root, and the snapshots directory
   stat fingerprint so directory changes invalidate the cached fallback.
4. Add focused regression coverage proving repeated fallback resolution reuses the
   cached snapshot result without another `os.scandir()` call.
5. Run the registered focused tests, changed-scope coverage command, and
   registered probe locally on Linux; use PR-scoped performance CI as the merge
   gate.

## Boundaries

No Swift runtime behavior changes are included. Local validation is Linux-only
for this Python helper path; CI remains the registered probe source of truth
before merge.
