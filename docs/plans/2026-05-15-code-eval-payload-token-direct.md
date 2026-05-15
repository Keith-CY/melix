# Code Evaluation Payload Direct Token Extraction

## Goal

Remove the per-field dictionary lookup from the code-evaluation payload JSON fast path. The fast path already precomputes JSON key tokens for stable runner result fields; this slice groups those key tokens into ordered `(key, token)` pairs so extraction can pass bytes tokens directly to the field scanners.

## Scope

- `services/mlx-worker-python/worker/engine/code_eval_runner.py`
- `docs/plans/2026-05-15-code-eval-payload-token-direct.md`

## Registered Probe

The affected path is covered by the existing PR-scoped `code-eval-payload-json-bytes` probe in `infra/perf/pr_scoped_probes.json`. That registry entry watches `code_eval_runner.py` and includes focused `test_command`, `coverage_command`, and `probe_command` entries for the code-evaluation payload fast path.

## Verification Plan

- Run the registered focused pytest command for `code-eval-payload-json-bytes`.
- Run the registered changed-scope coverage command and require at least 95% changed-scope coverage for the touched executable file.
- Run `scripts/code_eval_payload_json_probe.py` on `origin/main` and on this branch with the same Linux environment, using at least three samples per side.

## Success Metrics

- Preserve payload fast-path behavior, including public string-key helper wrappers used by tests.
- Keep fallback behavior for unknown keys and malformed JSON payloads.
- Improve or hold steady the registered probe's elapsed time and allocation metrics on Linux.
