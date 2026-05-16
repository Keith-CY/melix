# Evaluation Normalized Option Fast Path

## Goal

Reduce avoidable numeric-shape regex checks in evaluation answer normalization for
single-letter multiple-choice answers while preserving the existing normalized
answer contract.

## Scope

This slice is limited to `EvaluationCore._normalized_answer()` and the existing
registered PR-scoped probe `evaluation-answer-normalization-fast-path`.

## Change

`_normalized_answer()` now handles already-stripped single-character option
answers before numeric detection. Single-letter answers still return the
canonical uppercase option, numeric strings still use numeric normalization, and
free-text answers keep the existing whitespace/case-fold behavior.

## Metrics

Primary registered probe: `evaluation-answer-normalization-fast-path`.

- `elapsed_ms_mean`: lower is better.
- `numeric_extract_calls_mean`: lower is better; should remain unchanged because
  the slice avoids the numeric shape check, not the numeric extractor itself.
- `option_extract_calls_mean`: lower is better; should remain unchanged for the
  registered workload because option answers are still normalized as options.

## Verification

Run the registered focused test command, changed-scope coverage command, and
registered probe locally on Linux. The PR-scoped performance workflow remains the
merge gate for the scheduled slice.
