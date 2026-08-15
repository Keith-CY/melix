# Code eval payload known-value ordinal fast path

## Scope

This Python-only performance slice is limited to `worker.engine.code_eval_runner._known_code_eval_payload_string_value(...)`, the helper used by the registered `code-eval-payload-json-bytes` PR-scoped probe while decoding known status strings from compact code-evaluation payload JSON.

The affected path is already covered by the registered PR-scoped performance probe `code-eval-payload-json-bytes` in `infra/perf/pr_scoped_probes.json`. That registry entry has focused `test_command`, `coverage_command`, and `probe_command` entries for the code-evaluation payload loader and probe script.

## Change

The known-value decoder now compares byte ordinals directly for the small fixed vocabulary emitted by the code-evaluation runner (`ok`, `passed`, `failed`, `compiled`, and related status strings) instead of repeatedly dispatching through `bytes.startswith(...)` after every value length check.

This preserves fallback behavior: unknown values with the same lengths still return `None` so callers decode arbitrary failure details with UTF-8, and malformed payloads still fall back to full JSON parsing or rejection through the existing loader path.

## Validation Plan

- Run the focused code-evaluation payload fast-path tests.
- Run changed-scope coverage through the registered probe coverage command.
- Run `scripts/code_eval_payload_json_probe.py` locally on Linux and compare against the pre-change baseline.
- Rely on the registered PR-scoped performance workflow in CI for repository gating after PR creation.

## Local Baseline

Before this change on `origin/main` (`299f5b16`), the registered probe reported:

```json
{"elapsed_ms_mean": 57.443895722307, "iteration_count": 1200.0, "payload_bytes": 51874.0, "peak_bytes_mean": 52795.0, "sample_count": 7.0}
```
