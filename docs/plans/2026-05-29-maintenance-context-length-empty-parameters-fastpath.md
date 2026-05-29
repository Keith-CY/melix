# Maintenance Context-Length Empty-Parameters Fast Path

## Scope

Optimize one Python hot path in `MaintenanceCore._benchmark_context_lengths`: resolving the default benchmark context length when callers pass an empty parameter mapping.

## Probe

The affected path is covered by the registered PR-scoped probe `maintenance-prompt-shape-vector-repeat` in `infra/perf/pr_scoped_probes.json`.

The registered probe includes:

- focused behavior tests through `test_command`
- changed-scope coverage through `coverage_command`
- repeated local/CI metrics through `scripts/maintenance_prompt_shape_probe.py`

Primary metric for this slice: `elapsed_ms_mean` from the prompt-shaping/default-context loop. Guard metrics remain `token_count_mean` and `plain_token_count_mean`.

## Plan

1. Preserve default context-length behavior for empty parameter mappings and explicit parameter values.
2. Avoid the redundant `parameters.get("context_lengths", "").strip()` lookup when the parameters mapping is empty.
3. Add a regression test proving empty parameter mappings use the default prompt path without reading parameter keys.
4. Run focused tests, changed-scope coverage, and the registered probe locally on Linux before PR creation.
5. Use GitHub Actions PR-scoped performance output as the merge gate.

## Verification Notes

Local Linux verification is sufficient for this Python slice. No Swift runtime effect is claimed.
