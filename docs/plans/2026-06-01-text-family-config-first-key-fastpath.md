# Text family config first-key fast path

## Scope

Optimize the registered `text-family-config-copy-elision` Python path in
`services/mlx-worker-python/worker/runtime/text_family_adapters.py` by checking
the most common config keys directly before falling back to the remaining
synonym loops:

- `model_type` in `_detected_architecture`
- `num_local_experts` in `_expert_count_from_config`
- `moe_gate_dequant` in `_inferred_moe_gate_dequant`

This keeps behavior identical while avoiding extra helper dispatch or one tuple
iteration step on the Qwen3-MoE config resolution hot path measured by the
existing probe.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`text-family-config-copy-elision` in `infra/perf/pr_scoped_probes.json`. The
registry entry already provides focused `test_command`, `coverage_command`, and
`probe_command` entries for the runtime adapter, text-family tests,
PR-scoped-performance tests, and `scripts/text_family_config_probe.py`.

## Linux verification boundary

This slice is Python-only under `services/mlx-worker-python`, so focused tests,
changed-scope coverage, and the registered probe are locally verifiable on
Linux. GitHub Actions remains the merge gate for the PR-scoped probe report.

## Acceptance criteria

- Preserve existing fallback semantics for alternate expert-count and MoE
  gate-dequant config keys.
- Keep `config_copy_calls_mean` at `0.0`.
- Local baseline-vs-head probe shows lower `elapsed_ms_mean` without increasing
  `peak_bytes_mean`.
- Changed-scope coverage for touched executable Python remains at least 95%.
