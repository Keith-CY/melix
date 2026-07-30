# Evaluation normalized-answer plain ASCII fast path

## Scope

This Python-only performance slice is limited to `EvaluationCore._normalized_answer()` in `services/mlx-worker-python/worker/engine/evaluation_core.py`.

The hot path normalizes many already-trimmed ASCII free-text answers during local evaluation scoring. Those answers do not need wrapping removal, numeric normalization, Unicode whitespace folding, or casefolding.

## Registered probe

The affected path is covered by the registered PR-scoped probe `evaluation-answer-normalization-fast-path` in `infra/perf/pr_scoped_probes.json`.

The probe defines focused `test_command`, `coverage_command`, and `probe_command` entries and reports:

- `elapsed_ms_mean` for answer normalization
- `answer_match_elapsed_ms_mean` for answer matching
- extractor call counts and checksums to guard behavior

## Change

Add an early branch for plain ASCII answers that are already trimmed, not wrapped, not numeric literals, not single-option answers, and do not require whitespace collapsing. The branch returns `value.lower()` directly.

This follow-up slice keeps that branch behavior-equivalent while binding the first and last characters once inside the ASCII branch, avoiding repeated boundary indexing/attribute lookups before the plain-text fast-path return.

## Validation plan

1. Run focused evaluation helper tests and PR-scoped registry tests.
2. Run changed-scope coverage for the changed evaluation source, tests, registry tests, and probe script.
3. Run the registered probe locally on Linux before pushing.
4. Use GitHub Actions PR-scoped performance as the final registered probe merge gate.

## Local result

Local Linux probe (`scripts/evaluation_answer_normalization_probe.py`, default 5 samples):

- base (`origin/main`): `elapsed_ms_mean=123.083289`, `answer_match_elapsed_ms_mean=44.636862`
- head: `elapsed_ms_mean=108.239728`, `answer_match_elapsed_ms_mean=43.770581`
- normalization delta: `-14.843561 ms` (`-12.06%`)
- answer-match delta: `-0.866281 ms` (`-1.94%`)
- checksum unchanged: `normalization_checksum=7724000`, `answer_match_checksum=324000`

Follow-up boundary-binding slice (`scripts/pr_scoped_performance_run.py`, base/head worktrees, 2026-07-28):

- base (`origin/main`): `elapsed_ms_mean=107.328982`, `answer_match_elapsed_ms_mean=46.076059`
- head: `elapsed_ms_mean=99.065209`, `answer_match_elapsed_ms_mean=43.856885`
- normalization delta: `-8.263773 ms` (`-7.70%`)
- answer-match delta: `-2.219174 ms` (`-4.82%`)
- checksum unchanged: `normalization_checksum=7724000`, `answer_match_checksum=324000`
