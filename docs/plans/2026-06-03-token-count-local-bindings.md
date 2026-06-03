# Token Count Local Binding Fast Path

## Goal

Reduce overhead in `whitespace_token_count(...)` by binding the ASCII whitespace
set and Unicode whitespace predicate once in the helper signature. The token
counting loop and semantics remain unchanged; this only removes repeated local
setup on the OCR/VLM deterministic runtime token-count hot path.

## Scope

- `services/mlx-worker-python/worker/runtime/token_counting.py`
- `docs/plans/2026-06-03-token-count-local-bindings.md`

## Registered Probe

The affected path is covered by the registered PR-scoped
`deterministic-ocr-token-count-scan` probe in `infra/perf/pr_scoped_probes.json`.
The entry includes focused `test_command`, `coverage_command`, and
`probe_command` values for `worker/runtime/token_counting.py`, the OCR runtime,
focused vision runtime tests, and `scripts/deterministic_ocr_token_count_probe.py`.
No registry changes are required for this local-binding-only slice.

## Verification Plan

- Run the registered focused `test_command` locally on Linux.
- Run the registered changed-scope `coverage_command` locally on Linux and keep
  touched scope at or above 95% coverage.
- Run the registered `probe_command` before and after the implementation on
  Linux and compare `elapsed_ms_mean` and `peak_bytes_mean`.

## Success Metrics

- Preserve existing token-count behavior for ASCII and Unicode whitespace cases.
- Improve `elapsed_ms_mean` in the local registered OCR token-count probe.
- Keep `peak_bytes_mean` stable within the registered probe tolerance.
