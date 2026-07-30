# Hub Catalog Next Cursor Direct Rel Suffix Performance Slice

## Status

Accepted for the 2026-07-29 performance slice after local Linux tests,
changed-scope coverage, and the registered hub catalog next-cursor probe.

## Scope

Optimize the Python hub catalog `Link` header next-cursor parser in
`services/mlx-worker-python/worker/model_ops/hub_catalog.py` by adding a direct
common-case `>; rel="next"` suffix lookup before falling back to the existing
spacing-tolerant parser.

## Registered Probe

This slice is covered by the existing PR-scoped performance probe:

- `hub-catalog-next-cursor-fast-parse`
- watched path: `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- focused tests: `services/mlx-worker-python/tests/test_hub_catalog.py`
- coverage command: registered `coverage_command` in
  `infra/perf/pr_scoped_probes.json`
- probe command: registered `probe_command` in
  `infra/perf/pr_scoped_probes.json`

## Behavior

The direct suffix path handles the canonical Hugging Face Link header segment
shape used by Melix search pagination, for example:

```text
<https://huggingface.co/api/models?limit=50&cursor=page%2F1>; rel="next"
```

Headers that omit the optional space after the semicolon still use the existing
fallback parser, preserving compact forms such as `>;rel="next"`.

## Verification Plan

1. Run the focused hub catalog next-cursor tests and the PR-scoped probe script
   test.
2. Run changed-scope coverage using the registered coverage command.
3. Run `scripts/hub_catalog_next_cursor_probe.py` locally on Linux and compare
   the metrics against the pre-change baseline.
4. Let GitHub Actions run the registered PR-scoped performance workflow before
   merge.
