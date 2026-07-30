# Dataset Source Read Decode Method Slice

## Scope

This Python-only performance slice is limited to the unbounded dataset ingest
source reader in `services/mlx-worker-python/worker/productization/dataset_preparation.py`.
The behavioral contract remains unchanged: `_read_source_text(path)` performs one
binary read for uncapped sources and decodes UTF-8 text.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`dataset-source-records-scandir` in `infra/perf/pr_scoped_probes.json`. The
registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries covering source-file iteration, source-kind
classification, source reads, and record construction.

## Optimization

Use the bytes object's direct `.decode("utf-8")` method for the uncapped fast path
instead of first binding `bytes.decode` and passing the bytes object explicitly.
The capped read path keeps the bound decoder because it decodes the joined chunk
buffer after cap enforcement.

## 2026-07-30 follow-up slice: direct binary open

The next source-read slice keeps the same one-read UTF-8 behavior while replacing
`Path.read_bytes()` on the uncapped path with a direct `open(os.fspath(path),
"rb").read()` call. The capped path already uses the direct binary-open helper;
sharing that setup avoids the extra `Path.read_bytes()` method dispatch and keeps
both reader modes on the same low-level file access path.

## Validation plan

1. Run the registered focused test command locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux.
3. Run the registered probe locally before and after the change and compare
   `read_elapsed_ms_mean` plus the overall `elapsed_ms_mean`.
4. Use GitHub Actions PR-scoped performance as the merge gate after push.

## Success criteria

- Focused tests and changed-scope coverage pass.
- The registered probe shows a directionally lower `read_elapsed_ms_mean` without
  regressing the file scan, source-kind, or record-construction timings beyond
  normal noise.
- The PR-scoped performance CI report completes successfully before merge.
