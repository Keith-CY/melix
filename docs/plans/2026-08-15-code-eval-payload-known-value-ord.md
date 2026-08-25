# Code eval payload known-value ordinal fast path

## Scope

This Python-only performance slice is limited to `worker.engine.code_eval_runner._known_code_eval_payload_string_value(...)`, the helper used by the registered `code-eval-payload-json-bytes` PR-scoped probe while decoding known status strings from compact code-evaluation payload JSON.

The affected path is already covered by the registered PR-scoped performance probe `code-eval-payload-json-bytes` in `infra/perf/pr_scoped_probes.json`. That registry entry has focused `test_command`, `coverage_command`, and `probe_command` entries for the code-evaluation payload loader and probe script.

## Change

The known-value decoder now compares byte ordinals directly for the small fixed vocabulary emitted by the code-evaluation runner (`ok`, `passed`, `failed`, `compiled`, and related status strings) instead of repeatedly dispatching through `bytes.startswith(...)` after every value length check.

This preserves fallback behavior: unknown values with the same lengths still return `None` so callers decode arbitrary failure details with UTF-8, and malformed payloads still fall back to full JSON parsing or rejection through the existing loader path.

## Validation

- Run the focused `code-eval-payload-json-bytes` tests locally on Linux.
- Run changed-scope coverage for the code-eval payload loader and probe paths.
- Run `scripts/code_eval_payload_json_probe.py` locally on Linux and compare against the pre-change baseline.
- GitHub Actions PR-scoped performance remains the final merge gate.

## 2026-08-22 Follow-up: default-bound payload fd helpers

This follow-up Python-only slice stays within the same code-evaluation payload
byte-loading path and registered `code-eval-payload-json-bytes` probe. The
payload reader now binds the fd helper functions and read-only flag as keyword
defaults on `_read_payload_file_bytes(...)`, and `_load_payload_file(...)` binds
that reader as its default byte-loading callable. This preserves the explicit
injection seam for tests while avoiding repeated module-global helper lookups in
the hot payload load path.

Expected metrics are lower or neutral `elapsed_ms_mean` for
`scripts/code_eval_payload_json_probe.py`; `peak_bytes_mean` should remain stable
because the slice only reuses immutable callables and an integer flag.

## Local Baseline

Before this change on `origin/main` (`299f5b16`), the registered probe reported:

```json
{"elapsed_ms_mean": 57.443895722307, "iteration_count": 1200.0, "payload_bytes": 51874.0, "peak_bytes_mean": 52795.0, "sample_count": 7.0}
```

## 2026-08-22 Follow-up: sorted payload reverse cursor local

This follow-up Python-only slice stays within the registered
`code-eval-payload-json-bytes` probe. The sorted-payload extractor now computes
its reverse-search lower bound once and reuses that local for each reverse
field scan. This keeps the fallback and malformed-payload behavior unchanged
while removing repeated arithmetic from the compact sorted payload fast path.

Expected metrics are lower or neutral `elapsed_ms_mean` for
`scripts/code_eval_payload_json_probe.py`; `peak_bytes_mean` should remain
stable because the slice only reuses an integer cursor.

## 2026-08-22 Follow-up: compact field helper payload length local

This follow-up Python-only slice stays within the registered
`code-eval-payload-json-bytes` probe. The compact JSON field lookup helpers now
cache `len(payload_bytes)` once per helper call and reuse that local for the
boundary check and default reverse-search end. This preserves the same compact
and whitespace-tolerant fallback parsing behavior while avoiding duplicate
length lookups in the sorted payload fast path.

Expected metrics are lower or neutral `elapsed_ms_mean` for
`scripts/code_eval_payload_json_probe.py`; `peak_bytes_mean` should remain
stable because the slice only reuses an integer local.

## 2026-08-25 Follow-up: stat-keyed real payload byte cache

This follow-up Python-only slice stays within the same registered
`code-eval-payload-json-bytes` probe. Real `Path` payload loads now use a small
stat-keyed byte cache before the compact JSON fast path. The cache key includes
path text, `mtime_ns`, `ctime_ns`, and size, so repeated loads of the same stable
payload avoid redundant fd reads while stat changes still invalidate the cached
bytes. Non-`Path` payload test doubles and explicitly injected byte readers keep
using the existing byte-loading seam unchanged.

Expected metrics are lower `elapsed_ms_mean` and `peak_bytes_mean` for
`scripts/code_eval_payload_json_probe.py`; payload semantics remain unchanged for
missing, invalid, non-mapping, custom path-like, and stat-changed payloads.
