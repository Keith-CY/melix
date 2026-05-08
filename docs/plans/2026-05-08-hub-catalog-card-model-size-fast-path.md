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

## Success Metrics

- Preserve all existing size-hint parsing behavior by falling back to `_size_hint_from_text(...)` when the direct parser cannot handle the value.
- Reduce `_size_hint_from_text(...)` calls for direct `cardData.model_size` values in the registered probe.
- Improve or hold steady `elapsed_ms_mean` in the local registered probe.
