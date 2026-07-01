# Model Registry Metadata Payload Direct Fast Path

## Slice

Optimize one Python model-registry metadata helper path: `_metadata_payload_has_mlx_signal` should reuse the direct `library_name`/`tags` MLX signal check before serializing the whole metadata payload to JSON.

## Registered Probe Coverage

The affected path remains covered by the existing PR-scoped probes in `infra/perf/pr_scoped_probes.json`:

- `model-registry-readme-source-fastpath`
- `model-registry-plain-local-manifest-stat-elision`

Both probes provide focused `test_command`, `coverage_command`, and `probe_command` entries for the model registry catalog path.

## Expected Behavior

- Exact and normalized direct MLX metadata values still return `True`.
- Non-direct metadata continues through the JSON text fallback.
- Unserializable non-direct metadata still returns `False`.

## Measurement Plan

Run the focused model-registry tests, the changed-scope coverage command for the registered probe, and the registered local Python probe on Linux. Compare baseline-vs-head probe metrics before pushing.
