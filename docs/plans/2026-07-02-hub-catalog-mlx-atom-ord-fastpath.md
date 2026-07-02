# Hub Catalog MLX Atom Ord Fast Path

## Goal

Keep Hub catalog MLX compatibility detection behavior unchanged while reducing the
small hot-path cost of exact `MLX` atom checks. The slice replaces repeated
single-character membership checks with direct ASCII code comparisons in
`_is_mlx_atom(...)`, which is used by library-name, tag, and card metadata
compatibility paths.

## Scope

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`

No protocol, dependency, or generated artifact changes are part of this slice.

## Registered Performance Probe

The affected path is already covered by the registered PR-scoped probe
`hub-catalog-size-hint-regex-precompile` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` values and watches:

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/hub_catalog_size_hint_probe.py`

Although the probe name originated with size-hint parsing, its script also
measures `_payload_is_mlx_compatible(...)` across repo-id, library-name, tag,
and card-tag compatibility branches. This slice uses that existing registered
coverage rather than introducing a second probe for the same Hub catalog file.

## Linux Verification Plan

Run the registered focused test command, changed-scope coverage command, and the
registered local probe on Linux before opening the PR. GitHub Actions
PR-scoped performance remains the final merge gate.

## Success Metrics

- Focused Hub catalog and PR-scoped performance tests pass.
- Changed-scope coverage for touched Python scope is at least 95%.
- Local base-vs-head registered probe shows behavior parity and a non-regressed
  Hub catalog probe result; the compatibility sub-metric is expected to improve
  modestly because `_is_mlx_atom(...)` is intentionally tiny.
