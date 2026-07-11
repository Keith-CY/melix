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

A follow-up 2026-06-29 diagnosis marker prefilter loop slice keeps the same
prefilter semantics while replacing the excerpt-wide marker `any(...)` generator
with an explicit loop helper. Lines still enter the per-pattern matcher only when
one registered diagnosis marker appears in the lowercased source text, but the
hot scan path avoids creating a generator for every bounded excerpt line.

A follow-up 2026-07-01 redacted excerpt byte accounting slice keeps the same
bounded excerpt text, line map, and byte-limit semantics while using an ASCII
fast path for rendered excerpt lines. ASCII runtime log lines now account for
`len(rendered) + 1` directly and only encode the uncommon non-ASCII path, while
clipped ASCII lines preserve the existing newline-inclusive byte boundary.

A follow-up 2026-07-01 private-line marker scan slice keeps the redaction
contract unchanged while short-circuiting prompt/response label checks before
building lowercased prefix substrings. The marker helper now checks the second
character for the `p*` and `r*` branches first, so common runtime lines such as
`runtime load failed ...` and ordinary `plain ...` status lines can skip the
anchored private-text regex without transient lowercased prefix strings.

A follow-up 2026-07-01 excerpt line-number accounting slice keeps the redacted
excerpt text, truncation behavior, and source-line map unchanged while carrying
the emitted output-line count, bound output append method, and last source-path
prefix in the loop. This avoids repeated `len()` calls on the growing output
list, repeated append attribute lookups, and repeated prefix formatting for
adjacent bounded log lines from the same source path.

A follow-up 2026-07-03 diagnosis loop binding slice keeps matched codes,
pattern priority, and evidence pointers unchanged while binding hot loop helpers
and pattern/source containers once per excerpt scan. The matcher still lowers
each considered line once, applies the same union-marker prefilter, suppresses
duplicate codes, and stops after every known diagnosis code has matched. It also
inlines the per-pattern marker/expression loops inside the excerpt scan so the
hot path avoids repeated global, method, and helper lookups in the registered
diagnostic parser probe.

A follow-up 2026-07-04 external-path redaction slice keeps target-relative
labels unchanged while short-circuiting clean external absolute paths after the
lexical target-root check. Paths that do not contain parent-directory segments
cannot become target-relative through the slower fallback, so the redactor emits
the existing `<absolute-path>` label without constructing fallback `Path` objects
or calling `relative_to()`. Paths with `..` segments continue through the
normalization fallback to preserve safe target-root labeling.

A follow-up 2026-07-04 failure-status membership slice keeps failure-check
semantics unchanged while reusing a module-level `frozenset` for statuses that
should feed diagnostic source lines. Runtime export diagnostics still admit only
failed and blocked smoke checks, but avoid constructing the two-item set inside
each checked failure row while aggregating registered diagnostic parser probe
fixtures.

A follow-up 2026-07-04 target-path relative-text slice keeps target-relative
and external path redaction labels unchanged while making the lexical
`_target_relative_text()` fast path return immediately for clean target-local
relative paths that contain no parent-directory marker. The slice also defers the
`<absolute-path>` fallback string setup until after the target-local lexical match
fails. Paths with empty relative text or `..` segments continue through the same
safe fallback behavior, but ordinary bounded runtime excerpts skip the unused
fallback assignment and the extra parent-segment boundary checks.

A follow-up 2026-07-07 failure-check source collection slice keeps mapping and
attribute-style smoke check semantics unchanged while extracting failure check
fields inline in `_collect_source_lines()`. The hot diagnostic parser probe uses
small mapping rows for synthetic smoke failures, so this avoids repeated helper
calls and repeated `Mapping` dispatch for every check row while preserving the
same source-path fallback and failed/blocked status filter.

A follow-up 2026-07-07 exact diagnosis text slice keeps diagnosis semantics and
matched pattern ids unchanged while checking the exact lowercased diagnosis-text
table before the broader marker prefilter. Fixture-like common lines already
covered by the exact table now skip the union marker scan and phrase loop,
whereas non-exact lines continue through the same marker, phrase, and regex
fallbacks.

A follow-up 2026-07-08 diagnosis evidence-path prefix slice keeps diagnosis
semantics, matched pattern ids, and emitted evidence anchors unchanged while
binding the repeated `diagnostics/redacted-log-excerpt.txt#line-` prefix once per
excerpt scan. Exact-text, fast-phrase, and regex fallback matches now append the
line number to that bound prefix instead of formatting the full evidence path in
each matched branch.

A follow-up 2026-07-11 source collection row-path reuse slice keeps runtime-log
row collection and failure-check source semantics unchanged while reading
`row.path` once per manifest row inside `_collect_source_lines()`. The manifest
row loop still uses the same runtime-log predicate, duplicate suppression,
target-relative resolution, file read, and source-line extension behavior, but
avoids repeated protobuf attribute lookups for rows that enter the diagnostic
source collection path.

A follow-up 2026-07-11 runtime-log predicate slice keeps the same runtime-log
row eligibility contract while passing the caller's already-read row path into
`_is_runtime_log_row()`. This avoids a second protobuf `path` attribute lookup
when the generated, required, and intermediate file rows are scanned for log
sources, while role and retention-class checks remain unchanged.

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
