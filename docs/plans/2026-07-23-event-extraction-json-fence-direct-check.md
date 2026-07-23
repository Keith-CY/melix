# Event extraction JSON fence direct-check performance slice

## Scope

This Python-only performance slice is limited to event-extraction response JSON parsing in `services/mlx-worker-python/worker/productization/event_extraction.py`.

## Plan

- Keep parsing behavior unchanged for direct JSON objects, leading-whitespace objects, ` ```json ` fenced objects, generic fenced objects, inline closing fences, and invalid trailing text.
- Avoid `str.startswith(...)` calls in the closing-fence tail check by using direct character checks for the hot `\n```` and inline ```` suffixes.
- Extend the registered PR-scoped probe evidence so the primary metric measures fenced JSON responses while retaining leading-whitespace and direct-object companion metrics.

## Probe

Registered probe: `event-extraction-response-json-fence-trim` in `infra/perf/pr_scoped_probes.json`.

Metrics:

- `elapsed_ms_mean` / `peak_bytes_mean`: fenced JSON response parsing, lower is better.
- `leading_elapsed_ms_mean` / `leading_peak_bytes_mean`: leading-whitespace unfenced response parsing, informational companion metrics emitted by the probe script.
- `direct_elapsed_ms_mean` / `direct_peak_bytes_mean`: direct-object response parsing, lower is better.

## Verification

Run the registered focused test command, changed-scope coverage command, and `scripts/event_extraction_response_json_probe.py` locally on Linux before PR creation. The GitHub PR-scoped performance workflow remains the merge gate for registered probe validation.
