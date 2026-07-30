# Text family string value boundary fast path

## Scope

This Python-only performance slice is limited to `worker/runtime/text_family_adapters.py`, specifically `_string_value()` calls used by repeated text family config resolution.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `text-family-config-copy-elision` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/text_family_adapters.py`
- `services/mlx-worker-python/tests/test_text_family_adapters.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/text_family_config_probe.py`

This slice adds this plan file to the probe watch list so future text-family resolver follow-ups keep the governing performance plan visible in PR-scoped runs.

## Optimization slice

Exact metadata string values that already have no leading or trailing whitespace now return directly from `_string_value()` instead of allocating a `strip()` result. Values with leading or trailing whitespace still use the existing `strip()` fallback, and empty values still fall back to the supplied default.

The registered probe uses exact text-family metadata values for the hot resolver loop, so elapsed time and peak allocations measure the avoided string normalization work directly.

## Verification plan

Run the focused registered test command, changed-scope coverage command, and registered probe locally on Linux before opening the PR. GitHub Actions PR-scoped performance remains the merge gate for the registered probe report.

## Linux verification boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime effect is claimed.
