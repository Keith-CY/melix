# Dev-up MLX Metal dist-info entry-path slice

## Scope

This performance slice keeps `scripts/dev_up.py` behavior unchanged while reducing
path-construction overhead in `read_mlx_metal_dist_info_version`. The scan still
walks ancestors of `mlx.metallib`, accepts `mlx_metal-*.dist-info` directories,
reads `METADATA` when present, falls back to the dist-info directory version, and
continues past unreadable directories or metadata files.

## Registered PR-scoped probe

The affected path is covered by the registered PR-scoped performance probe
`dev-up-mlx-metal-dist-info-scandir` in `infra/perf/pr_scoped_probes.json`. The
entry includes focused `test_command`, `coverage_command`, and `probe_command`
fields for `scripts/dev_up.py` and the associated regression tests.

## Implementation plan

- Preserve the existing `os.scandir` directory iteration and fallback semantics.
- Build the `METADATA` path from `DirEntry.path` so matching entries avoid an
  extra `ancestor / entry_name` path join before appending `METADATA`.
- Do not change candidate ordering, version parsing, or error handling.

## Verification plan

Run locally on Linux before PR:

1. Focused dist-info regression tests from the registered probe.
2. Changed-scope coverage using the registered `coverage_command`.
3. Registered probe locally against `origin/main` and this branch with
   `scripts/pr_scoped_performance_run.py`.
4. `git diff --check`.

GitHub Actions PR-scoped performance remains the merge gate for base-vs-head
validation before merge.
