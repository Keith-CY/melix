# Dataset Preview Supported-File Stat Order Performance Slice

## Scope

Optimize the dataset registry preview scanner used by
`read_hf_dataset_snapshot_rows(..., limit=N)` when it gathers the first few
supported dataset files from a snapshot directory.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`dataset-registry-preview-limit-short-circuit` in
`infra/perf/pr_scoped_probes.json`.

The probe includes:

- focused tests for dataset preview limiting and scan edge cases,
- changed-scope coverage for `worker/dataset_registry/catalog.py`, and
- `scripts/dataset_registry_preview_limit_probe.py` for local and CI metrics.

## Slice

For supported dataset filenames discovered during limited preview scans, check
`DirEntry.is_file(follow_symlinks=False)` before falling back to the directory
check. This avoids the prior directory-type check on the common path where the
entry is already a supported regular dataset file, while still preserving the
existing directory recursion behavior and OSError handling for unsupported names
and nested directories.

## Success Metrics

Use the registered probe metrics:

- `elapsed_ms_mean` lower is better,
- `multi_limit_elapsed_ms_mean` lower is better,
- `peak_bytes_mean` informational for this slice.

The change is accepted only if focused tests pass and the registered probe shows
an improved or neutral elapsed-time direction in the local Linux run and in the
PR-scoped CI report.
