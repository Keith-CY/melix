# Runtime Export Diagnostic Parser

## Scope

This plan implements the #1510 worker-owned slice of runtime export failure
diagnostics. The parser reads target-local runtime logs and smoke failure
messages, writes `diagnostics/diagnostics-receipt.json`, and exposes typed
operator remedies through `export-report.json`.

The slice does not change protobuf schemas. The existing
`ExportDiagnosticPolicy` and `ExportEvidencePolicy.diagnostics_receipt_path`
fields are sufficient for the first parser policy.

## Receipt Contract

The diagnostics receipt uses schema `melix.export_diagnostics_receipt.v1` and
records:

- target identity and `parser_policy_id`
- parser status: `matched`, `unknown`, or `not_applicable`
- typed diagnosis rows with code, severity, matched pattern id, operator
  message, remediation, and redacted evidence pointer
- bounded redacted log excerpt metadata
- operator remedies for CLI, Desktop, and reports
- parser metrics: coverage, parsed failure count, unknown failure count,
  redaction count, and latency

Supported diagnosis codes for this slice are:

- `runtime_load_failed`
- `unsupported_architecture`
- `duplicate_tensor_name`
- `missing_blob`
- `missing_binary`
- `invalid_runtime_path`
- `runtime_timeout`
- `permission_denied`
- `insufficient_memory`
- `unknown_failure`

## Redaction Policy

The parser writes `diagnostics/redacted-log-excerpt.txt` instead of copying raw
logs into operator-facing receipts. It redacts:

- absolute host paths, using target-relative labels when a path is under the
  export target root
- bearer tokens, API keys, proxy credentials, passwords, and certificate-like
  secrets
- full prompt, response, completion, dataset row, private prompt template, and
  operator-input lines
- user or operator identity values that are not needed for diagnosis

Unknown failures still receive a bounded redacted excerpt so parser coverage can
be expanded without leaking credentials or private text.

## Export Integration

Failed or blocked smoke receipts must finish diagnostics before updating the
target export report. The export report exposes `diagnostic_status`,
`diagnostic_codes`, and `operator_remedies` from the shared receipt; UI surfaces
render those fields instead of parsing raw logs independently.

Waived runtime-unavailable checks keep the existing waiver path. Missing binary
diagnosis is covered by parser fixtures and by non-waivable runtime binary
failures.

## Metrics And Verification

The PR-scoped performance probe id is `runtime-export-diagnostic-parser`.
It measures:

- `elapsed_ms_mean`
- `peak_bytes_mean`
- `diagnostic_parser_coverage`
- `parsed_failure_count`
- `unknown_failure_count`
- `redaction_count`
- `diagnostic_latency_ms`

The 2026-06-25 optimization slice keeps the parser contract unchanged and caches
`layout.target_root.resolve(strict=False)` once per redacted excerpt build. It
also labels absolute paths that are already lexically under the resolved target
root without per-path filesystem resolution, falling back to the previous
`Path.resolve(strict=False)` path when `..` segments require normalization. This
avoids repeated resolution work in multi-path runtime logs while preserving
safe target-relative redaction labels.

A follow-up 2026-06-25 slice keeps the same redaction contract but gates the
secret/identity regex substitutions behind cheap marker checks. Plain runtime
log lines that only contain an absolute target path still run the absolute-path
redactor, but skip the bearer-token, named-secret, URL credential, OpenAI key,
certificate, and identity regex passes. Lines with `:`, `=`, `@`, `sk-`, or a
certificate preamble continue through the relevant guarded regexes before path
redaction.

A 2026-06-25 metric aggregation slice keeps the receipt schema and parser
semantics unchanged while deriving parsed-failure count, unknown-failure count,
and matched diagnosis codes in a single pass. The aggregate report also folds
receipt metrics and diagnosis code discovery into one receipt pass, avoiding the
previous extra comprehensions and metric summations on every diagnostic report.

Focused verification:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" \
  uv run --project services/mlx-worker-python pytest -q \
  services/mlx-worker-python/tests/test_export_target_diagnostics.py \
  services/mlx-worker-python/tests/test_export_target_smoke_policy.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_runtime_export_diagnostic_parser_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_runtime_export_diagnostic_parser_probe_script_emits_metrics \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
```
