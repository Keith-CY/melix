# Local job follow-up scan loop bindings

This Python performance slice is limited to `LocalJobContinuationStore.scan_followup_candidates(...)` in `services/mlx-worker-python/worker/runtime/local_job_continuation.py`.

## Goal

Keep local job follow-up scan behavior unchanged while reducing per-record Python overhead in large continuation stores. The scan already uses one `os.scandir(...)` pass; this follow-up slice builds the sortable record-id list directly during the scandir pass, removes the per-entry helper call for `.json` stem extraction, and keeps the record-file filter on regular top-level JSON files without following symlinks.

## Probe coverage

The affected path is covered by the registered PR-scoped performance probe `local-job-followup-scan-scandir` in `infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`, `coverage_command`, and `probe_command` entries and measures scan elapsed time, scan syscall shape, receipt/candidate counts, and follow-up projection metrics.

## Verification plan

1. Run focused local job continuation tests plus registry/probe tests.
2. Run changed-scope coverage for the touched Python paths and probe script.
3. Run the registered `local-job-followup-scan-scandir` probe locally on Linux against `origin/main` and this branch.
4. Use the PR-scoped performance workflow as the merge gate.

## 2026-06-30 follow-up: suffix check before file stat

This Python-only follow-up keeps the same registered `local-job-followup-scan-scandir` probe and narrows the top-level scandir filter. `scan_followup_candidates(...)` now rejects non-`.json` directory entries before calling `DirEntry.is_file(follow_symlinks=False)`, and uses direct suffix slicing rather than `str.endswith(...)` on the hot path. JSON-named directories still receive the no-follow file check and are skipped; non-record files such as `*.json.tmp` and `*.txt` avoid an unnecessary metadata query.

## 2026-07-01 follow-up: projection receipt shallow copy

This Python-only follow-up keeps the same registered `local-job-followup-scan-scandir` probe and narrows the batch projection copy path. `project_local_job_session_followups(...)` now copies the claim-batch receipt envelope with a receipt-aware shallow copier instead of calling generic `deepcopy(...)` over the full receipt tuple. The helper still isolates top-level receipt mutations and the nested `prompt_context_receipts` list used by claimed follow-ups, while avoiding recursive traversal of immutable scalar fields for every projected local-job receipt.

The focused regression guard mutates both a copied top-level receipt field and a nested prompt-context receipt field to prove downstream projection mutations do not leak back into the claim batch. No record schema, reconciliation, claim, prompt-context admission, scan ordering, or receipt payload semantics change.

## 2026-07-03 follow-up: projection claim narrow copies

This Python-only follow-up keeps the same registered `local-job-followup-scan-scandir` probe and narrows `_project_local_job_session_followup_claim(...)`. The projection path now uses JSON-shape copy helpers for the prompt user payload, untrusted-context receipts, and claim receipt instead of invoking generic `deepcopy(...)` for every projected claim. The copy helpers preserve downstream mutation isolation for the local-job completion summary and receipt dictionaries while avoiding generic memo/type-dispatch overhead on the registered projection workload.

The focused regression guard monkeypatches the module-level `deepcopy` symbol to reject generic deep copies, then mutates copied completion-summary and receipt data to prove projection changes do not leak back into the claim/prompt-context state. No record schema, reconciliation, claim, prompt-context admission, scan ordering, or receipt payload fields change.

## 2026-07-05 follow-up: projection JSON scalar fast path

This Python-only follow-up keeps the same registered `local-job-followup-scan-scandir` probe and narrows `_copy_json_like_value(...)`, the helper used by local-job follow-up projection copies. The helper now returns exact JSON scalar values (`str`, `int`, `float`, `bool`, and `None`) before checking container types, avoiding repeated `dict`/`list`/`tuple` guards for immutable scalar leaves in completion summaries and untrusted-context receipts.

The registered probe entry now includes the focused scalar-copy regression test in both `test_command` and `coverage_command`, and `scripts/local_job_followup_scan_probe.py` now reports scalar-copy baseline/optimized/delta metrics alongside the existing scan and projection metrics. Changed-scope coverage covers the new fast path before local and CI probe comparisons, while the scalar-copy probe isolates the JSON-scalar leaf-copy hot path from scan I/O noise. No record schema, reconciliation, claim, prompt-context admission, scan ordering, or receipt payload fields change.

## Linux validation boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime behavior changes are included.
