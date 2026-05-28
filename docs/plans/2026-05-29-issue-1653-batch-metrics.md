# Issue 1653 Admission And Worker Batch Metrics

Date: 2026-05-29

## Context

Issue #1642 tracks the remaining Gemma E4B release serving gap against OMLX
and SwiftLM. Issue #1652 added a deterministic same-cohort probe and proved
that current scheduler admission batching can be observed without proving
worker/model-step fused decode batching.

Issue #1653 finishes that attribution slice by making the metric names and
reporting surface distinguish the control-plane admission cohort from worker
decode execution and model-eval batch size. The goal is observability, not yet
the homogeneous batch decode implementation tracked by #1655 and #1656.

## Plan

1. Add explicit scheduler admission-cohort metric names alongside the existing
   compatibility metrics.
   - Keep `scheduler.continuous_batch_size` for existing dashboards.
   - Add `scheduler.admission_cohort_size` and
     `scheduler.admission_active_cohorts` so benchmark evidence cannot treat
     admission as model execution.
2. Extend the same-cohort probe contract.
   - Report admission cohort size separately from worker decode batch size,
     model eval batch size, decode batch observations, and per-batch token
     cadence.
   - Keep a warning when admission cohort size is greater than one while worker
     and model eval batch sizes remain singleton.
3. Extend Gemma E4B comparison reporting.
   - Include admission, worker decode, and model eval batch metrics in the
     Melix metrics snapshot section.
   - Add a report hint when metrics show an admission cohort larger than the
     worker/model execution batch.
4. Verify the metric contract with focused Python and Swift tests that cover
   single-request, same-cohort two-request, and non-cohort fallback evidence.

## Success Metrics

- The deterministic same-cohort probe emits separate numeric fields for
  `scheduler_admission_cohort_size`, `worker_decode_batch_size`, and
  `worker_model_eval_batch_size`.
- The Gemma E4B report lists those fields in the Melix metrics snapshot when
  present.
- Tests cover singleton, same-cohort two-request, and non-cohort fallback
  behavior without requiring a real model or peer runtime.
