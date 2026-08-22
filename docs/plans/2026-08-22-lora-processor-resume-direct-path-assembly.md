# LoRA processor resume direct path assembly

## Scope

This Python-only performance slice stays inside
`services/mlx-worker-python/worker/model_ops/lora_runtime_metadata.py` and narrows
`_processor_resume_mode()` after the prior `os.path.isfile` fast path.

The helper still preserves resume precedence:

1. `processor_config.json`
2. `preprocessor_config.json`
3. `tokenizer_config.json`
4. `missing`

The new slice avoids calling `os.path.join()` for each candidate file. It builds
one base path prefix from `os.fspath(base_model_dir) + os.sep`, keeps the local
`os.path.isfile` binding, and concatenates each constant filename directly.

## Registered Probe

Registered PR-scoped probe: `lora-aux-modules-scandir` in
`infra/perf/pr_scoped_probes.json`.

The registry entry covers the affected LoRA runtime metadata module and includes
focused `test_command`, `coverage_command`, and `probe_command` entries. It also
watches this plan. The probe reports the processor resume path via:

- `processor_resume_baseline_elapsed_ms_mean`
- `processor_resume_optimized_elapsed_ms_mean`
- `processor_resume_delta_ms`
- `processor_resume_isfile_calls_mean`

## Verification Plan

- Run the focused processor resume tests to preserve precedence and missing-file
  behavior.
- Run the registered `lora-aux-modules-scandir` focused test command locally on
  Linux.
- Run the registered changed-scope coverage command locally on Linux.
- Run the registered probe locally on Linux before opening the PR and compare
  `processor_resume_optimized_elapsed_ms_mean` against the baseline commit.
- Use the PR-scoped performance workflow as the CI merge gate.

## Expected Metrics

This slice should reduce processor resume mode overhead without changing the
bounded three-file existence checks or the observed `os.path.isfile` call count.
