# Model Registry MLX-Only Search Pagination

## Goal

The Models Library registry search should visibly surface Hugging Face discovery
results for common model-family queries such as `Gemma` when the operator keeps
the default `MLX Only` filter enabled.

## Root Cause

Model Registry already refreshes its unified local, managed-download, and Hub
discovery list after Hub search completes. The failure mode is in the worker
Hub catalog search path: `mlx_only=true` fetched a single Hugging Face page
without asking the Hub to constrain results to MLX, then filtered that page
locally for MLX compatibility. For broad model-family queries, the first Hub
page can contain non-MLX or unsupported runtime formats while later pages
contain compatible MLX repositories. Filtering only the first page can
therefore return no Hub discovery rows, leaving the registry list visibly
unchanged.

## Implementation Slice

- Keep non-MLX-only search as a single Hub API request.
- For `mlx_only=true`, request the Hub API with `filter=mlx` and retain the
  local MLX-compatibility filter as a correctness guard.
- Continue following the Hub `rel="next"` cursor while the locally filtered
  MLX-compatible results are still under the requested page size.
- Bound the continuation to a small maximum page count so broad queries cannot
  produce unbounded network work.
- Preserve the current `next_cursor` contract so the UI can continue paginating
  from the last fetched Hub cursor.

## Verification And Metrics

- Add a regression test where the first Hub page for `Gemma` contains no
  MLX-compatible payloads, the `Link` header points to a second page, and the
  second page contains an MLX Gemma repository.
- Run focused Hub catalog tests and the maintenance service search test that
  exercises `mlx_only` propagation.
- Measure changed-line Python coverage for the touched worker catalog path.
- Metrics report: no runtime performance baseline is expected for this narrow
  correctness fix; the bounded page count is the performance guardrail. Report
  the selected test/coverage commands and mark broader product metrics as N/A.
