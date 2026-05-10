# LoRA Run Directory Scan Path Allocation Slice

## Goal

Reduce peak allocation in the LoRA experiment run-directory scan while keeping the
existing sorted `Path` return contract and no-entry-path-read invariant.

## Scope

This slice is limited to `worker.productization.lora_experiment_store._iter_lora_run_dirs`
and its registered PR-scoped performance probe. It does not change LoRA run
persistence, index payload semantics, run filtering, or experiment grouping.

## Registered Probe

The affected path is covered by the `lora-experiment-run-dir-name-scan` entry in
`infra/perf/pr_scoped_probes.json`, with focused test, changed-scope coverage, and
`command_json` probe commands. This slice also keeps the registered commands on
`python3` for scheduled Linux verification.

## Implementation Plan

1. Preserve the scandir/name-first filtering behavior so fake and real directory
   entries do not need `entry.path` reads.
2. Sort the accumulated run directory names in place before materializing `Path`
   objects, avoiding the extra list produced by `sorted(...)`.
3. Reuse a local `Path.__truediv__` binding while creating the output tuple to
   keep the hot loop allocation-focused and scoped.

## Verification

- Run the registered focused tests.
- Run the registered changed-scope coverage command.
- Run the registered `lora-experiment-run-dir-name-scan` probe locally on Linux
  and compare against the pre-change baseline.
- CI PR-scoped performance remains the merge gate for the registered probe.
