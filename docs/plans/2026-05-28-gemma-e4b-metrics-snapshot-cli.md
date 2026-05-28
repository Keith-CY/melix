# Gemma E4B Metrics Snapshot CLI

## Goal

Expose Melix serving metrics through a stable local command that benchmark
harnesses can consume without scraping sidecar state ad hoc or depending on a
public `/metrics` HTTP endpoint.

This is the implementation slice for issue #1648 under the Gemma E4B serving
performance investigation. It supports the phase-attribution work in #1647 and
the root comparison gate in #1642.

## Scope

- Add a JSON-emitting CLI under `scripts/` that reads the current Melix
  control-plane, Swift text-worker, and optional Python-worker metrics exports.
- Support explicit metrics paths and worktree-local `MELIX_RUNTIME_DIR`
  discovery, so benchmark runners can call the command from a separate shell.
- Preserve the existing flattened `values` object consumed by comparison
  reports while also distinguishing per-source values and source metadata.
- Record source freshness for each configured source from the runtime
  `updated_at_unix_ms` payload when available, falling back to file mtime.
- Keep missing-source output machine-readable. The default command emits
  `ok: false` and exits successfully so reports can preserve evidence; `--strict`
  exits non-zero for shell gates.

## Non-Goals

- Do not add a public HTTP `/metrics` endpoint in this slice.
- Do not change the runtime metrics exporters or metric names.
- Do not add the phase-delta report rows from #1649; this slice only exposes the
  stable snapshot interface that #1649 will consume.

## CLI Contract

Benchmark harnesses should call:

```bash
python3 scripts/melix_metrics_snapshot.py \
  --runtime-dir .runtime/sidecars/<instance-name>
```

or pass explicit paths:

```bash
python3 scripts/melix_metrics_snapshot.py \
  --control-plane-metrics "$MELIX_CONTROL_PLANE_METRICS_PATH" \
  --swift-text-worker-metrics "$MELIX_SWIFT_TEXT_WORKER_METRICS_PATH"
```

The JSON payload includes:

- `schema_version`, `generated_at`, and `generated_at_unix_ms`.
- top-level `ok`, `missing_required_sources`, `updated_at_unix_ms`, and
  flattened `values` for existing report consumers.
- `sources.<source_name>` metadata, including `component`, `source_kind`,
  `required`, `path`, `ok`, and `freshness`.
- `source_values.<source_name>` metric maps to keep control-plane metrics
  separate from worker metrics.

## Verification

- Unit tests cover successful multi-source export, runtime-dir discovery, missing
  required sources, and strict-mode exit behavior.
- Runtime-dir discovery is covered by the registered PR-scoped performance probe
  `melix-metrics-snapshot-runtime-scandir`, which measures latest metrics file
  lookup across a synthetic runtime directory with thousands of matching
  snapshots and worker-metrics noise files.
- Existing OMLX/Melix and three-way comparison tests continue to cover report
  artifact integration.

## Performance Slice: Runtime Discovery Scandir

The metrics snapshot CLI may be called during benchmark harness setup where the
runtime directory contains many historical metrics snapshots. Runtime-dir source
resolution should therefore avoid materializing a `Path.glob()` candidate list and
avoid a second `Path.stat()` pass. The lookup now scans the runtime directory
once with `os.scandir()`, filters names with the source runtime glob pattern, and
tracks the highest file mtime while preserving the existing missing-directory and
OSError fallback to `None`.
