# Hub Catalog Size Hint Newline Fast Path

## Goal

Reduce Python-level scanning in the Hub catalog explicit size-hint parser for the common README/card line form where the `Model size` value ends at `\n`.

## Touched Files

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/hub_catalog_size_hint_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Registered Probe

Registered PR-scoped probe: `hub-catalog-size-hint-regex-precompile`.

The probe already watches the Hub catalog parser, its focused tests, and `scripts/hub_catalog_size_hint_probe.py`; it includes focused `test_command`, `coverage_command`, and `probe_command` entries. This slice relies on:

- `elapsed_ms_mean` — lower is better.
- `size_hint_calls_mean` — structural guard rail for regex fallback calls.
- `matched_hint_count` and `checksum` — behavior guard rails.

## Implementation Slice

Use `str.find("\n", value_start)` before the existing generic line-terminator loop in `_direct_explicit_size_hint_from_text`. This keeps the existing fallback for non-LF Unicode/legacy line separators while shifting the common README path to a C-level search.

## Verification Plan

1. Run the focused Hub catalog tests and PR-scoped performance tests from the registered probe.
2. Run changed-scope coverage for the registered files and require at least 95% measured coverage.
3. Run `scripts/hub_catalog_size_hint_probe.py` on Linux before and after the change and compare `elapsed_ms_mean` with unchanged guard rails.
4. Run `git diff --check` before commit.
