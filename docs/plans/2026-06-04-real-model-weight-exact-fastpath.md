# Real Model Weight Exact Filename Fast Path

## Context

The registered `real-model-support-hf-cache-latest-snapshot` PR-scoped probe covers
`scripts/real_model_support.py`, including Hugging Face cache snapshot selection and
real-local weight file detection. The synthetic probe creates a model directory with
many non-weight JSON files and a common `model.safetensors` artifact.

## Slice

This slice keeps the existing HF cache snapshot fallback unchanged and only adds a
small exact-filename fast path for common top-level real-model weight artifacts before
falling back to the existing `os.scandir()` suffix scan.

## Probe

Registered probe: `real-model-support-hf-cache-latest-snapshot` in
`infra/perf/pr_scoped_probes.json`.

This slice gates only `weight_scan_elapsed_ms_mean`, because the HF cache latest
snapshot timing is a separate path in the same support script and is not affected
by the exact filename fast path. The probe still validates latest-snapshot
selection with invariant counters, but the performance decision for this slice is
scoped to the synthetic common-weight-file scan.

Required local commands:

- focused tests from the registry, extended with the exact filename regression test
- changed-scope coverage from the registry
- registered probe command on Linux

## Success Criteria

- Behavior remains equivalent for recognized exact filenames, suffix-based weight
  files, missing directories, and scanner fallback cases.
- The probe reports lower `weight_scan_elapsed_ms_mean` for common exact weight files.
- Changed-scope coverage for the touched files stays at or above 95%.
