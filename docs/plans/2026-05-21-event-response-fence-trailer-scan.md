# Event extraction fenced JSON trailer scan slice

## Scope

This Python performance slice keeps event-extraction response parsing semantics unchanged while reducing allocation in the fenced JSON closing-trailer check.

Affected path: `services/mlx-worker-python/worker/productization/event_extraction.py`.

## Registered probe

Existing registered probe: `event-extraction-response-json-fence-trim` in `infra/perf/pr_scoped_probes.json`.

The probe already defines focused `test_command`, `coverage_command`, and `probe_command` entries for:

- fenced JSON response parsing unit tests
- PR-scoped probe registry tests
- `scripts/event_extraction_response_json_probe.py`

No registry change is required for this slice.

## Optimization

`_has_only_optional_closing_fence()` previously used `response_text[trailer_start:response_length].isspace()` for the common decoded-object trailer shape `\n```   \n`. That materialized a short substring on every parse. The slice replaces that substring allocation with an index scan over the existing response string.

This preserves accepted trailers:

- exact `\n```` after a decoded object
- `\n```   \n` with trailing whitespace
- whitespace-only trailers without a fence

It still rejects non-whitespace text after a fenced JSON object.

## Verification plan

Run the registered focused test command, coverage command, and probe command locally on Linux. Compare the local probe against the pre-change `origin/main` baseline before pushing. The PR-scoped performance workflow remains the final registered probe gate in CI.

## Local metrics

Pre-change Linux probe on `origin/main` worktree:

```json
{"checksum": 640000.0, "elapsed_ms_mean": 1357.4019073974341, "event_count": 1600.0, "iterations_per_sample": 80.0, "peak_bytes_mean": 2999220.0, "sample_count": 5.0}
```

Post-change Linux probe on this branch:

```json
{"checksum": 640000.0, "elapsed_ms_mean": 1254.386511957273, "event_count": 1600.0, "iterations_per_sample": 80.0, "peak_bytes_mean": 2999220.0, "sample_count": 5.0}
```

Delta: `elapsed_ms_mean` improved by 103.015 ms, or 7.589%; `peak_bytes_mean` was unchanged.
