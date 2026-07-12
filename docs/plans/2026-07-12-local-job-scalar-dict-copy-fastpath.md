# Local Job Scalar Dict Copy Fast Path

## Scope

This Python performance slice is limited to the local-job follow-up projection
copy helper in `worker.runtime.local_job_continuation._copy_json_like_value(...)`.
The helper copies prompt-context payloads and receipts before projecting local job
follow-up messages.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`local-job-followup-scan-scandir` in `infra/perf/pr_scoped_probes.json`. The
probe includes focused `test_command`, `coverage_command`, and `probe_command`
entries and reports `scalar_copy_*` metrics for the JSON-like copy helper.

## Change

Exact built-in dict payloads now copy scalar JSON values directly while still
recursing for nested dicts, lists, and tuples. Container subclasses continue to
use the existing generic fallback path so subclass behavior remains unchanged.

## Verification

Run the registered local-job follow-up test command, changed-scope coverage, and
registered probe locally on Linux. The expected signal is lower
`scalar_copy_optimized_elapsed_ms_mean` and a higher `scalar_copy_speedup` while
scan/projection counts remain unchanged.

CI remains the merge gate for the PR-scoped performance workflow report.
