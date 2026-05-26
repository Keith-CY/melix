# Real Model Weight Suffix Lowercase Fast Path

## Slice

Optimize `scripts/real_model_support.py::_has_recognized_model_weight_files()` for the common lowercase model-weight filename path.

The current implementation lowercases every scanned filename before checking model-weight suffixes. Real model directories commonly contain many lowercase sidecar/config files and lowercase `.safetensors` shards, so lowercasing every non-matching entry adds avoidable allocation and CPU work during preflight scans.

## Registered Probe

The affected path is covered by the existing `real-model-support-hf-cache-latest-snapshot` PR-scoped probe. This slice extends that probe to also measure a synthetic flat model directory with many lowercase non-weight files followed by a lowercase weight file:

- `weight_scan_elapsed_ms_mean`
- `weight_scan_peak_bytes_mean`
- `weight_file_count`

The existing HF-cache latest-snapshot metrics remain in the same probe so prior coverage is preserved.

## Implementation Plan

1. Preserve exact behavior for explicitly recognized index filenames and uppercase model-weight suffixes.
2. Fast-path lowercase suffix checks with `name.endswith(_REAL_MODEL_WEIGHT_SUFFIXES)` before falling back to `name.lower()` only when the filename is not already lowercase.
3. Add a regression test proving uppercase suffix fallback remains accepted.
4. Extend probe/test coverage for the weight-directory scan metrics.

## Verification

Run the focused tests, changed-scope coverage, and the registered probe locally on Linux. Use the PR-scoped performance workflow as the merge gate for the registered probe report.
