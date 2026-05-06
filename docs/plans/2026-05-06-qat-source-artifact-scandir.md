# QAT source artifact scandir performance slice

## Scope

This Linux-verifiable Python performance slice is limited to QAT source artifact
file discovery in `services/mlx-worker-python/worker/model_ops/quantization_pipeline.py`.
The existing fake-quant QAT flow hashes every source artifact file before writing
training evidence. Large adapter artifacts should avoid allocating a full
`Path.rglob("*")` iterator tree during that discovery step.

## Plan

- Keep QAT behavior unchanged for file sources, nested directory sources, and
  empty directory validation.
- Replace `Path.rglob("*")` discovery with an explicit `os.scandir()` stack that
  collects files, skips recursion into directory symlinks, and sorts the final
  `Path` list to preserve deterministic digest order.
- Add a focused regression test that fails if QAT source discovery regresses to
  `Path.rglob()` allocation.
- Extend the registered model-ops bundle artifact PR-scoped probe commands so the
  focused QAT scandir regression runs with the existing changed-scope tests and
  coverage gate for `quantization_pipeline.py`.

## Verification

Run the registered probe's focused test command, changed-scope coverage command,
and probe command locally on Linux. Compare the registered probe metric before
and after the slice. The probe remains registered as
`model-ops-bundle-artifact-byte-accounting` and covers the changed quantization
pipeline path.
