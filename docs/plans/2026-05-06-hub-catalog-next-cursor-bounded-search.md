# Hub Catalog Next-Cursor Bounded Relation Search

## Scope

This performance slice is Python-only and targets the Hugging Face Hub catalog
pagination helper in `services/mlx-worker-python/worker/model_ops/hub_catalog.py`.
The affected helper scans RFC-style `Link` header segments and extracts the
encoded `cursor` value from the `rel="next"` segment.

## Registered probe

Use the existing `hub-catalog-next-cursor-fast-parse` PR-scoped performance
probe in `infra/perf/pr_scoped_probes.json`. It includes focused test,
coverage, and probe commands for:

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/hub_catalog_next_cursor_probe.py`

## Optimization hypothesis

The current segment scanner already avoids full `urllib.parse.urlparse` and
`parse_qs`, but relation detection still materializes the relation slice before
checking for `rel="next"`. Replace that substring allocation with a bounded
`str.find(...)` over the same segment range.

Expected effect: preserve cursor behavior while reducing per-segment allocation
and improving `elapsed_ms_mean` / `peak_bytes_mean` in the registered probe.

## Verification

Run the focused cursor tests, changed-scope coverage for the touched Python
scope, and the registered local probe before opening the PR. The CI PR-scoped
performance workflow must also complete the registered probe successfully before
merge.
