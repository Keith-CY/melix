# Video URI identity hash cache

## Scope

This Python-only performance slice is limited to repeated URI video preprocessing in
`services/mlx-worker-python/worker/runtime/video_preprocessing.py`.

The hot path prepares many remote video references with the same URI metadata frame.
The behavior remains unchanged: URI validation, inferred filename/format metadata,
byte-length accounting, and the SHA-256 identity string are preserved.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`video-preprocessing-uri-byte-length-reuse` in `infra/perf/pr_scoped_probes.json`.
The registry entry already includes focused `test_command`, `coverage_command`, and
`probe_command` entries. The probe measures:

- `elapsed_ms_mean` for repeated `prepare_video_input(...)` calls.
- `byte_length_getattrs_per_call`, which must remain at one metadata read per call.
- `parse_calls_per_call`, which must remain at the cached parse behavior.

## Implementation plan

1. Add an LRU cache to `_uri_identity_hash(...)`, keyed by its immutable metadata
   frame inputs, reusing the same bounded cache size as URI parse metadata.
2. Add regression coverage proving repeated identical metadata frames hit the cache
   and return the same digest.
3. Run the registered focused test command, changed-scope coverage command, and
   registered probe locally on Linux before opening the PR.
4. Use the GitHub Actions PR-scoped performance report as the merge gate.

## Expected outcome

Repeated URI video preprocessing avoids recomputing the same identity SHA-256
digest while preserving the existing public `PreparedVideoInput` output shape and
validation semantics.
