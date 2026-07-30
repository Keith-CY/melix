# Dev-up MLX Metal dist-info name-prefix performance slice

## Context

`scripts/dev_up.py` resolves the local `mlx.metallib` package version by scanning ancestor directories for `mlx_metal-*.dist-info` siblings. The registered PR-scoped probe `dev-up-mlx-metal-dist-info-scandir` covers this path with focused tests, changed-scope coverage, and a synthetic `site-packages` directory containing many unrelated `.dist-info` directories.

## Slice

Add a single cheap name-prefix guard before the full `startswith("mlx_metal-")` / `endswith(".dist-info")` checks in `read_mlx_metal_dist_info_version()`. The common probe case has many unrelated package metadata directories that do not start with `m`; skipping those before the longer prefix/suffix checks preserves behavior while reducing per-entry string work.

## Verification

- Focused tests: registered `dev-up-mlx-metal-dist-info-scandir` `test_command`.
- Coverage: registered `coverage_command` with `scripts/dev_up.py`, `test_dev_up_script.py`, and `test_pr_scoped_performance.py` in changed scope.
- Probe: registered `probe_command`, comparing the base commit and this branch locally on Linux.

## Boundaries

This is a Python/Linux-verifiable slice. It does not change Swift runtime behavior or generated protobuf artifacts.
