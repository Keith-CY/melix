# Local job follow-up payload copy bindings

## Scope

This Python-only performance slice keeps local job follow-up semantics unchanged and narrows only the projection payload-copy helpers in `services/mlx-worker-python/worker/runtime/local_job_continuation.py`.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `local-job-followup-scan-scandir` in `infra/perf/pr_scoped_probes.json`. The probe already includes focused `test_command`, `coverage_command`, and `probe_command` entries covering the local job continuation module, tests, probe registry selection, and `scripts/local_job_followup_scan_probe.py`.

## Optimization

`_copy_prompt_user_payload()` and `_copy_untrusted_context_receipts()` now bind `_copy_json_like_value()` once per helper invocation and use explicit loops for payload/receipt projection. This avoids repeated global lookup from nested comprehensions while preserving the existing shallow container allocation and recursive JSON-like copy behavior.

## Verification plan

1. Run the focused local job continuation tests from the registered probe.
2. Run changed-scope coverage from the registered probe and remove generated `coverage.json` afterwards.
3. Run `scripts/local_job_followup_scan_probe.py` locally on Linux and compare projection metrics with the pre-change baseline. `projection_elapsed_ms_mean` remains the primary projection gate. `projection_elapsed_ms_min` is retained as an informational stability signal because per-sample temporary-directory setup makes the minimum sensitive to runner jitter even when the mean and helper-specific metrics improve.
4. Use the PR-scoped performance workflow as the merge gate before squash merging.
