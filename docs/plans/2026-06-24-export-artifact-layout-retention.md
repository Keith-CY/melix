# Export Artifact Layout And Retention Policy

## Goal

Implement the #1507 runtime export layout slice so each export target has a
predictable workspace path, a machine-readable retention report, cleanup
dry-run and apply behavior, and byte-accounting metrics for retained and
cleanable artifacts.

## Scope

This slice consumes the `melix.export_target_manifest.v1` contract from #1506.
It does not add target types, perform real model conversion, run post-export
smoke checks, or parse runtime diagnostics. Those remain in #1509 and #1510.

## Layout Contract

Runtime export targets are materialized under the owning workspace:

```text
exports/
  adapters/
    <adapter-id-segment>/
      <adapter-snapshot-segment>/
        <export-id-segment>/
          targets/
            <target-type>/
              <target-id-segment>/
                export-target-manifest.json
                export-report.json
                artifacts/
                intermediates/
                logs/
                smoke/
                diagnostics/
                retention/
                  retention-report.json
```

The adapter id, adapter snapshot, export id, and target id segments are stable
path-safe encodings of the manifest values. Target type is one of
`melix_managed`, `ollama`, `gguf`, or `mlx_runtime`.

Manifest file rows remain relative to the target directory. The layout module
never treats absolute host paths as export authority.

## Retention Policy

The retention report classifies every manifest file row:

- `required` and `evidence` files are retained.
- `intermediate`, `cache`, and `temporary` files become cleanable only after
  target verification has passed or been explicitly waived.
- `runtime_log` files are retained until the manifest retention TTL expires,
  then become cleanable by TTL.

Cleanup dry-run reports the same decisions without deleting files. Cleanup
apply deletes only cleanable existing files and never deletes manifests,
verification evidence, or required runtime artifacts.

## Reports And Metrics

The export report and retention report include:

- `retained_byte_size`
- `cleanable_byte_size`
- `deleted_byte_size`
- `retention_decision_count`
- `retained_file_count`
- `cleanable_file_count`
- `deleted_file_count`
- `missing_file_count`

The PR-scoped probe records layout materialization latency, target count,
retained byte size, cleanable byte size, deleted file count, and retention
decision count. Runtime-log TTL decisions reuse the file metadata collected
while checking manifest-row existence, avoiding an extra stat call on the
retention hot path while preserving the missing-file race fallback. A follow-up
2026-06-26 metrics slice reuses the retention report already written during
materialization for `cleanup="dry-run"` metrics reports, avoiding a second
manifest validation and retention-decision pass when no cleanup side effects are
requested.

A follow-up 2026-06-29 placeholder materialization slice keeps the symlink-escape
guard unchanged while resolving each target root once per placeholder pass and
reusing that resolved root for manifest rows and evidence files. This avoids
repeated target-root resolution during layout materialization without relaxing
per-file path normalization or target-root containment checks.

A follow-up 2026-07-17 report bootstrap slice discovers the fixed fixture
manifest set with one `os.scandir()` pass instead of `Path.glob()` expansion in
the layout retention report and registered probe. The runtime export layout and
retention decisions are unchanged; only the report/probe fixture bootstrap path
avoids glob object allocation before calling `build_layout_metrics_report`.

## Verification

Focused verification:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" \
  UV_PYTHON=3.12 \
  uv run --project services/mlx-worker-python --extra mlx pytest -q \
  services/mlx-worker-python/tests/test_export_target_layout_retention.py \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_runtime_export_layout_retention_probe \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_runtime_export_layout_retention_probe_script_emits_metrics \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
```

Changed-scope coverage must stay at or above 95 percent for the new module,
tests, scripts, and PR-scoped registry coverage.
