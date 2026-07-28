# Text Family Config Copy Elision

## Goal

Reduce redundant work in text-family config resolution by avoiding repeated full `dict(...)` copies of large Hugging Face-style config payload mappings and by short-circuiting empty CSV metadata parsing.

## Linux-only constraint

This slice is Python-only under `services/mlx-worker-python` and can be verified locally on Linux with focused pytest, changed-scope coverage, and a command-json performance probe.

## Touched files

- `services/mlx-worker-python/worker/runtime/text_family_adapters.py`
- `services/mlx-worker-python/tests/test_text_family_adapters.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/text_family_config_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Probe definition

Register `text-family-config-copy-elision` in the PR-scoped performance registry.

The probe repeatedly resolves a Qwen3-MoE text family config using a large read-only mapping that records `keys()` calls. The old implementation calls `dict(config_payload)` repeatedly, forcing whole-mapping copies; the optimized implementation reads from the mapping directly.

The 2026-05-09 follow-up slice keeps the same registered probe and narrows the new behavior change to `_split_csv()`: empty metadata strings return immediately without allocating split parts, and non-empty values strip each CSV item once.

The 2026-07-23 follow-up keeps the same registered probe and narrows the new behavior change to `_bool_from_any()`: exact normalized string literals (`"true"`, `"false"`, `"on"`, etc.) return before the fallback `strip().lower()` normalization. Whitespace-padded and mixed-case strings still use the fallback path, preserving the existing bool parsing behavior while avoiding per-resolution string normalization for already-normalized metadata values.

The 2026-07-28 follow-up keeps the same registered probe and narrows the behavior-preserving change to `_bool_value()`: missing and empty metadata still return the caller default, exact normalized bool literals now return before `strip()`, and whitespace-only metadata still falls back to the default after the strip. This avoids one string strip on common already-normalized metadata flags while preserving padded and mixed-case bool parsing through `_bool_from_any()`.

A second 2026-07-28 follow-up keeps the same registered probe and narrows to `_resolved_expert_count()`: missing or empty `melix.text.moe.expert_count` metadata now returns to config/default inference before calling `strip()`, and an empty `melix.text.moe.expert_count_source` similarly avoids a source normalization call. Invalid non-empty expert-count metadata still falls through to the existing family-default path after the guarded `ValueError` handling.

Local Linux registered probe samples for the 2026-07-28 expert-metadata follow-up on this host:

- baseline `origin/main`: `151.5909326262772`, `158.11064094305038`, `149.95074956677854` ms; mean `153.217441045368` ms.
- expert-metadata empty fast path: `148.41943220235407`, `148.65166936069727`, `151.46144940517843` ms; mean `149.510850322743` ms.
- delta: `-3.706590722625` ms, `2.419170231100%` faster (`1.024791449681x`).
- `config_copy_calls_mean`: unchanged at `0.0`; `config_key_accesses_mean`: unchanged at `20000.0`; `peak_bytes_mean`: unchanged at `1008.0`.

Local Linux registered probe samples for the 2026-07-23 follow-up on this host:

- baseline `origin/main`: `156.5028017386794`, `164.59141615778208`, `158.0336649902165` ms; mean `159.709294295559` ms.
- exact bool literal fast path: `152.33040382154286`, `152.0294691901654`, `150.74609643779695` ms; mean `151.701989816501` ms.
- delta: `-8.007304479058` ms, `5.013674698300%` faster (`1.052783120964x`).
- `config_copy_calls_mean`: unchanged at `0.0`; `config_key_accesses_mean`: unchanged at `20000.0`.

Metrics:

- `elapsed_ms_mean`
- `peak_bytes_mean`
- `config_copy_calls_mean`
- `iterations`

## Success metrics

- Preserve existing text-family resolution behavior.
- Drive `config_copy_calls_mean` to `0.0` on the optimized branch.
- Improve local base-vs-head probe latency and/or peak traced memory on the registered synthetic workload.
- Maintain at least 95% changed-scope coverage for touched executable Python files.

## Verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_text_family_adapters.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_text_family_config_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_text_family_config_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_text_family_adapters.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_text_family_config_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_text_family_config_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/runtime/text_family_adapters.py services/mlx-worker-python/tests/test_text_family_adapters.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/text_family_config_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/text_family_config_probe.py
python3 scripts/pr_scoped_performance_run.py --probe-id text-family-config-copy-elision --output /tmp/text-family-config-probe.json
```
