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
- `path_redaction_elapsed_ms_mean`
- `diagnosis_matching_elapsed_ms_mean`
- `diagnosis_matching_line_count`

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

A follow-up 2026-06-25 path-redaction slice keeps the same redaction contract
but checks whether a matched absolute path is lexically under the resolved target
root before constructing a fallback `Path`. Clean target-local paths now produce
the same `<target>/...` labels through string slicing, while paths with `..`
segments or paths outside the target root continue through the existing
normalization fallback.

A follow-up 2026-06-25 diagnosis matching slice keeps the diagnosis semantics
unchanged while adding cheap lowercase marker gates to each diagnosis pattern.
Runtime lines whose text cannot contain a given failure class now skip that
class's regex expressions, while lines that contain a marker continue through the
same compiled regexes and matched-pattern ids as before. This reduces repeated
regex scans across bounded excerpts with many non-matching lines.

A follow-up 2026-06-26 diagnosis matching slice keeps the same parser semantics
but computes each source line's lowercase form once per diagnosis scan and shares
it across all marker-gated diagnosis patterns. This preserves the per-pattern
marker checks and regex match ids while avoiding repeated `str.lower()` calls on
large bounded excerpts with many non-matching progress lines.

A follow-up 2026-06-26 source-row iteration slice keeps source collection
semantics unchanged while iterating generated, required, and intermediate file
repeated fields separately instead of expanding them into one temporary tuple.
This avoids an intermediate container allocation when each diagnostic receipt
scans manifest rows for runtime logs.

A follow-up 2026-06-27 diagnosis prefilter slice keeps the existing per-pattern
marker gates and regex expressions, but first checks each lowercased source line
against the union of known diagnosis markers. Lines with no diagnostic marker
skip the pattern loop entirely, while matching lines still use the same compiled
regexes and matched-pattern ids as before. This reduces bounded-excerpt scans
with many progress lines that contain no supported failure terms.

A follow-up 2026-06-28 all-known-code short-circuit slice keeps the parser
semantics unchanged while stopping diagnosis matching once every known diagnosis
code has already been emitted for the bounded excerpt. Later lines cannot add a
new known-code diagnosis at that point because duplicate codes are already
suppressed, so the parser avoids lowercasing and marker scans across trailing
runtime-log noise.

A follow-up 2026-06-29 private-line redaction marker slice keeps the redaction
contract unchanged while gating the private prompt/response regex behind a cheap
leading-character marker. Runtime log lines that cannot begin one of the
registered private-text labels (`prompt`, `private prompt template`, `response`,
`completion`, `generated text`, `dataset row`, or `operator input`, after leading
whitespace) skip the anchored regex; lines with a compatible leading label still
use the same regex and redaction counters as before.

A follow-up 2026-06-29 diagnosis pattern loop slice keeps the diagnosis
semantics and pattern priority unchanged while shrinking per-pattern matching.
Each pattern now uses explicit marker and expression loops instead of
generator-backed `any(...)` calls. Duplicate diagnosis codes are still suppressed
for a bounded excerpt; overlapping later lines still fall through to the
remaining lower-priority patterns, and the scan still stops once every known code
has matched.

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
