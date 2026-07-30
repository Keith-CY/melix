# Hub catalog library MLX exact fast path

This Python-only performance slice is limited to `worker.model_ops.hub_catalog` MLX compatibility checks.

## Scope

The common Hugging Face metadata cases already report `library_name` as exactly `"mlx"` or `"MLX"`. This slice adds an exact-value guard before falling back to the mixed-case three-character `_is_mlx_atom(...)` helper in `_payload_is_mlx_compatible(...)` and `_is_mlx_compatible(...)`.

Behavior is unchanged for:

- exact `"mlx"` and `"MLX"` library names,
- mixed-case three-character variants such as `"MlX"`,
- card-level `library_name` fallback,
- tag and repository-id compatibility checks.

## Registered performance probe

The affected path is covered by the existing registered PR-scoped probe `hub-catalog-size-hint-regex-precompile` in `infra/perf/pr_scoped_probes.json`. That registry entry includes focused `test_command`, `coverage_command`, and `probe_command` fields and reports `payload_compatibility_elapsed_ms_mean` for `_payload_is_mlx_compatible(...)`.

## Validation plan

Run the registered focused test command, changed-scope coverage command, and local registered probe on Linux before opening the PR. Use the GitHub PR-scoped performance workflow as the merge gate after the PR is opened.
