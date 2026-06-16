# Hub catalog next-cursor link boundary fast path

## Scope

This performance slice keeps the registered Hub catalog next-cursor parser behavior unchanged while shaving one reverse search from the RFC 5988 Link header fast path.

Affected path:

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`

Registered PR-scoped probe:

- `hub-catalog-next-cursor-fast-parse`

## Rationale

`_next_cursor_from_link()` already locates the `rel="next"` marker before extracting the associated URL. The previous implementation searched backward for the URL closing `>` first, then searched backward again for `<` before that close marker. For the valid next-link shape used by Hub responses, the opening `<` before the relation marker is enough to bound a forward search for the closing `>` between the URL start and relation marker.

The slice therefore changes only the link-boundary lookup order:

1. Find `rel="next"`.
2. Find the nearest preceding `<`.
3. Find the matching `>` between that `<` and `rel="next"`.

Malformed headers still skip to the next relation marker or return an empty cursor, matching the existing parser contract.

## Verification Plan

Run the registered probe commands for `hub-catalog-next-cursor-fast-parse` on Linux:

- focused tests from `test_command`
- changed-scope coverage from `coverage_command`
- registered probe from `probe_command`

The PR-scoped performance workflow is the authoritative CI evidence for the registered probe report.
