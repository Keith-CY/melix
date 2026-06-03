# Hub Catalog Uppercase Model-Size Label Fast Path

## Goal

Reduce hot-path string scanning in `worker.model_ops.hub_catalog._strip_model_size_label(...)` for the common uppercase `cardData.model_size` label shapes emitted by the registered size-hint probe, such as `MODEL SIZE:128 MB`.

## Scope

- `services/mlx-worker-python/worker/model_ops/hub_catalog.py`
- `services/mlx-worker-python/tests/test_hub_catalog.py`
- Existing registered probe: `hub-catalog-size-hint-regex-precompile`

## Registered Probe

The affected path is covered by `hub-catalog-size-hint-regex-precompile` in `infra/perf/pr_scoped_probes.json`. The registry entry already includes focused `test_command`, `coverage_command`, and `probe_command` entries for Hub catalog size-hint parsing and the synthetic probe script.

## Slice

Add a narrow exact-prefix branch for uppercase `MODEL SIZE:` and `MODEL SIZE|` direct card-size labels before falling back to the generic case-insensitive character-by-character label scanner. This keeps existing accepted label formats intact while avoiding the generic scanner for the synthetic and common uppercase direct-label form.

Follow-up within the same registered probe path: add exact lowercase unit suffix
branches in `_direct_size_hint_from_text(...)` for integer `kb`/`mb`/`gb` direct
card-size values. This preserves the decimal/fallback parser for fractional and
unusual values while avoiding `split(...)`, `lower()`, and `float(...)` on common
lowercase integer unit labels such as `MODEL SIZE:7 kb`.

## Verification Plan

- Run the registered focused test command for the Hub catalog probe.
- Run the registered changed-scope coverage command and require at least 95% coverage for touched executable scope.
- Run the registered `scripts/hub_catalog_size_hint_probe.py` locally on Linux before and after the change and compare `elapsed_ms_mean`, `size_hint_calls_mean`, and peak memory.

## Success Metrics

- Preserve direct card model-size behavior for mixed-case labels, uppercase labels, colon/pipe separators, and invalid `model-size` text.
- Keep `_size_hint_from_text(...)` fallback call counts unchanged.
- Improve or hold steady `elapsed_ms_mean` in the local registered probe and rely on PR-scoped CI as the merge gate.
