# Stream Assembler Long Literal Suffix Bound

This Python performance slice is limited to `RequestStreamAssembler._partial_structural_tag_suffix()` in `services/mlx-worker-python/worker/runtime/stream_assembler.py`.

## Optimization

The partial structural tag suffix helper now records the maximum viable suffix length for the active parser mode during assembler initialization. When the final `<` marker starts a long literal tail that is longer than any known partial structural tag, the helper returns early before slicing the whole tail and hashing it for membership.

This preserves existing parser behavior because no valid held structural suffix can be longer than the cached parser-mode maximum. It only reduces work for literal content such as `"<" + long_non_tag_payload`.

## PR-Scoped Probe

Affected path coverage is already registered under `stream-assembler-structural-prefix-cache` in `infra/perf/pr_scoped_probes.json`. The registration includes focused `test_command`, `coverage_command`, and `probe_command` entries and reports `long_literal_suffix_elapsed_ms_mean` for this exact long-literal suffix path.

## Verification Plan

Run the registered focused tests, changed-scope coverage command, and registered PR-scoped probe locally on Linux. Accept the slice only if behavior tests pass, changed-scope coverage remains at or above 95%, and the registered probe shows lower `long_literal_suffix_elapsed_ms_mean` without regressing the primary suffix metric.
