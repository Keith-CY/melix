# Dataset Version Listing Open-Time Manifest Validation

This Python-only performance slice is limited to `list_dataset_versions(...)` in `services/mlx-worker-python/worker/productization/dataset_preparation.py`.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `dataset-version-listing-scandir` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for the dataset version listing hot path.

## Slice

The version listing iterator currently emits only child directories with a filesystem `os.path.isfile(...)` probe for `dataset-version.json` before the caller opens the same manifest. On the common path where every version directory contains a manifest, that adds one pre-open stat per version that duplicates open-time validation.

This slice moves missing/non-file manifest handling to the direct `open(..., "rb")` step and lets `_iter_dataset_version_manifest_paths(...)` yield the deterministic candidate path for each child version directory. The caller preserves existing behavior by skipping missing, directory, or not-a-directory manifest candidates while continuing to surface malformed JSON errors.

## Verification Plan

1. Add regression coverage that `list_dataset_versions(...)` does not use `Path.glob`, `Path.read_bytes`, `_read_json_file`, or pre-open `os.path.isfile(...)` probes.
2. Add behavior coverage for version directories with missing or directory-valued `dataset-version.json` candidates.
3. Run the registered focused test command for `dataset-version-listing-scandir`.
4. Run changed-scope coverage for the registered probe and require at least 95% on the touched scope.
5. Run the registered probe locally on Linux against `origin/main` versus the slice branch before creating the PR.

## Boundary

This is a Linux-verified Python slice. No Swift runtime effect is claimed.
