# Hub Catalog Card Model Size Fast Path

## Goal

Avoid running the generic size-hint regex for the common Hugging Face `cardData.model_size` shape where the value is already a bare numeric size such as `128 MB`. The generic parser remains the fallback for labeled or unusual text.

## Scope

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- `scripts/hub_catalog_size_hint_probe.py`

## Registered Probe

The affected path is already covered by the PR-scoped `hub-catalog-size-hint-regex-precompile` command-json probe in `infra/perf/pr_scoped_probes.json`. It provides focused `test_command`, `coverage_command`, and `probe_command` entries for this file and probe script.

## Verification Plan

- Run the registered focused pytest command for the hub catalog probe.
- Run the registered changed-scope coverage command and require at least 95% coverage for touched executable scope.
- Run `scripts/hub_catalog_size_hint_probe.py` before and after the change on Linux and compare `elapsed_ms_mean` plus `size_hint_calls_mean`.

## Follow-up Slice: Direct Parser Bounded Split

This follow-up keeps the same registered probe and narrows `_direct_size_hint_from_text(...)`
to a bounded two-token split. Direct `cardData.model_size` values are expected to be shaped
like `128 MB`; values with additional words still return `0` from the direct parser so the
existing generic `_size_hint_from_text(...)` fallback can handle labeled text such as
`Model size: 7 MB`.

## 2026-05-16 Slice: Direct Parser Unpack Split

Keep the same two-token direct-parser semantics, but unpack `text.split()` directly and handle
`ValueError` for non-two-token values. This removes the temporary `parts` list length branch and
keeps invalid/labeled values on the existing generic parser fallback path.

## Success Metrics

- Preserve all existing size-hint parsing behavior by falling back to `_size_hint_from_text(...)` when the direct parser cannot handle the value.
- Keep `_size_hint_from_text(...)` call counts unchanged for this bounded-split follow-up.
- Improve or hold steady `elapsed_ms_mean` in the local registered probe.

## 2026-05-29 Follow-up: Direct Parser Bounded Split Implementation

This slice implements the bounded split in `_direct_size_hint_from_text(...)` by
using `text.split(maxsplit=2)` and rejecting any shape that does not produce
exactly two tokens. Two-token values keep the existing integer/float multiplier
semantics, while values with extra words still return `0` so callers can fall
back to the regex parser when appropriate. The registered
`hub-catalog-size-hint-regex-precompile` probe remains the validation gate.

## 2026-06-08 Follow-up: Uppercase Model Marker Fast Path

This slice keeps the same registered `hub-catalog-size-hint-regex-precompile`
probe and reorders `_may_contain_model_marker(...)` so uppercase `MODEL SIZE`
text exits on the first substring scan. Hugging Face card/readme metadata often
uses uppercase headings, while the helper still checks all four case combinations
and preserves the downstream regex fallback behavior.
