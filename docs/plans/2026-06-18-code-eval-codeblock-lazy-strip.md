# Code eval code-block lazy strip performance slice

## Scope

This Python-only performance slice is limited to `extract_candidate_code(...)` in
`services/mlx-worker-python/worker/engine/code_eval_runner.py`. The code-block
path should avoid allocating a fully stripped copy of large model responses before
the last fenced block is located. Plain text responses keep the existing stripped
return value, and whitespace-only responses still report `empty_prediction`.

## Registered PR-scoped probe

The affected path is covered by the registered PR-scoped performance probe
`code-eval-code-block-last-match-streaming` in `infra/perf/pr_scoped_probes.json`.
The probe includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `services/mlx-worker-python/tests/test_code_eval_runner.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/code_eval_code_block_extract_probe.py`

## Implementation plan

1. Preserve the empty/whitespace-only behavior without allocating a stripped copy
   on normal code-block responses.
2. Use the original response string for fenced-block `rfind`, count, slicing, and
   content-start detection.
3. Strip only the extracted candidate or plain-text fallback.
4. Add regression coverage for leading/trailing whitespace around a fenced Python
   block.

## Verification plan

- Run the registered focused tests.
- Run the registered changed-scope coverage command.
- Run the registered code-block extraction probe locally on Linux and compare the
  before/after `elapsed_ms_mean` and `peak_bytes_mean` values.
- Use GitHub Actions and the PR-scoped performance workflow as the final merge
  gate.

## Expected outcome

The code-block hot path should reduce or hold peak allocation by avoiding a
full-response `strip()` copy when model output includes outer whitespace, and it
should show lower or neutral `elapsed_ms_mean` on the synthetic multi-block
extraction probe.