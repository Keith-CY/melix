# Code Eval Payload String Field Find

## Scope

This Python-only performance slice is limited to the code-evaluation payload fast
path in `services/mlx-worker-python/worker/engine/code_eval_runner.py`. It does
not change sandbox execution, code-block extraction, stdio tail handling,
protobuf artifacts, Swift, or macOS runtime behavior.

## Registered probe

The affected path is already covered by the registered PR-scoped probe
`code-eval-payload-json-bytes` in `infra/perf/pr_scoped_probes.json`. The probe
entry includes focused `test_command`, `coverage_command`, and `probe_command`
values and reports `elapsed_ms_mean`, `peak_bytes_mean`, `payload_bytes`,
`sample_count`, and `iteration_count`.

## Optimization

`_extract_json_string_field_at()` now uses `bytes.find()` to locate the closing
quote and any escape byte in C-backed scans instead of stepping through each
byte in Python. Escaped strings still fall back to the full JSON loader so the
fast path only accepts the same unescaped status/detail fields as before.

## Verification plan

- Run the registered focused pytest command locally on Linux.
- Run the registered changed-scope coverage command locally on Linux and require
  at least 95% for the changed executable scope.
- Run the registered `code-eval-payload-json-bytes` probe locally before and
  after the change and compare `elapsed_ms_mean` and `peak_bytes_mean`.
- Use the PR-scoped performance workflow as the merge gate after push.

## Success criteria

- Focused tests pass.
- Changed-scope coverage remains at or above 95%.
- The local registered probe preserves payload semantics and shows a clear or
  noise-bounded improvement in `elapsed_ms_mean` without increasing peak memory.
