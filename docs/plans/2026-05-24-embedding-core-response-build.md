# Embedding Core Response Build Performance Slice

## Scope

Optimize the Python embedding response build path in `services/mlx-worker-python/worker/engine/embedding_core.py`.

This slice is intentionally limited to replacing the intermediate Python list of `Embedding` messages with direct protobuf repeated-field appends. The runtime input forwarding behavior stays unchanged: `request.inputs` is still passed through to the embedding runtime without list materialization.

## Registered Probe

The affected path is covered by the existing PR-scoped performance probe `embedding-core-inputs-view` in `infra/perf/pr_scoped_probes.json`.

The probe already includes:

- `test_command` for focused embedding core behavior and probe registry selection tests.
- `coverage_command` for the same changed scope.
- `probe_command` via `scripts/embedding_core_inputs_probe.py` reporting `elapsed_ms_mean` and `peak_bytes_mean`.

## Local Verification Plan

Run on Linux before PR creation:

1. Focused test command from the registered probe.
2. Focused coverage command from the registered probe.
3. Registered probe command locally.
4. Head-vs-`origin/main` comparison using the same probe workload.

## Expected Effect

Directly appending protobuf repeated messages should reduce temporary Python allocation and elapsed time for large embedding responses while preserving response contents and error behavior.
