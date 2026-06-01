# Evaluation answer ASCII lower fast path

## Scope

This performance slice narrows the registered evaluation answer-normalization
hot path to a single local optimization in
`worker.engine.evaluation_core.EvaluationCore._normalized_answer`.

## Registered probe

The affected path is covered by `evaluation-answer-normalization-fast-path` in
`infra/perf/pr_scoped_probes.json`.

- `test_command`: focused evaluation normalization tests plus PR-scoped probe
  registry tests.
- `coverage_command`: changed-scope coverage for the same focused test set.
- `probe_command`: command-json probe that repeatedly normalizes free-text,
  numeric, and option answers and reports elapsed time plus extractor-call
  counts.

## Implementation plan

1. Preserve the existing wrapping, numeric, option, and whitespace-normalization
   behavior.
2. Use `str.lower()` for normalized answers that are already ASCII, where it is
   semantically equivalent to `str.casefold()` and avoids the broader Unicode
   folding path.
3. Keep `str.casefold()` for non-ASCII answers so Unicode equivalence behavior is
   unchanged.
4. Validate locally on Linux with the registered focused tests, coverage command,
   and probe command before opening the PR.

## Validation boundary

This slice only touches Python worker code and is locally verifiable on Linux.
Swift runtime validation is not involved.