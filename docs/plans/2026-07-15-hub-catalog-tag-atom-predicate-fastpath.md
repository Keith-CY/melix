# Hub catalog MLX compatibility predicate fast path

## Scope

This Python-only performance slice is limited to the Hub catalog MLX compatibility
predicates in `services/mlx-worker-python/worker/model_ops/hub_catalog.py`.

The slice preserves MLX tag and repo-id matching behavior while simplifying two
hot predicates used during Hub summary construction:

- `_tag_payload_contains_mlx()` removes redundant exact `"MLX"` / `"mlx"`
  comparisons from each list item because `_is_mlx_atom()` already accepts those
  exact forms and mixed-case three-character variants.
- `_repo_id_contains_mlx()` uses one lowercase containment check instead of
  multiple case-probe scans plus a conditional lowercase fallback.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`hub-catalog-tag-normalization-single-pass` in `infra/perf/pr_scoped_probes.json`.
The probe watches the Hub catalog module, focused Hub catalog tests, PR-scoped
performance tests, and `scripts/hub_catalog_tag_normalization_probe.py`; it has
focused `test_command`, `coverage_command`, and `probe_command` entries.

## Verification plan

Run on Linux before opening the PR:

1. Focused Hub catalog regression tests and PR-scoped probe smoke tests.
2. Changed-scope coverage through the registered probe coverage command.
3. Local registered probe comparison for `hub-catalog-tag-normalization-single-pass`.

GitHub Actions PR-scoped performance remains the final merge gate for the
registered probe report.
