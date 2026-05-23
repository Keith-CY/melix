# Code evaluation config JSON load binding

## Scope

This performance slice targets the embedded code-evaluation runner's config
loader in `services/mlx-worker-python/worker/engine/code_eval_runner.py`.

## Plan

- Keep the registered `code-eval-runner-script-cache` PR-scoped performance
  probe as the governing validation path.
- Preserve the existing bytes-based JSON config load behavior.
- Bind `json.loads` as a default argument inside the embedded `_load_config`
  helper so repeated config-load loops avoid the module attribute lookup while
  continuing to parse bytes from the config path.

## Validation

- Focused unit coverage: `test_runner_script_loads_config_from_bytes` confirms
  the embedded runner still loads JSON config bytes and exposes the bound helper
  expression.
- Registered probe: `scripts/code_eval_runner_script_probe.py` reports
  `config_load_elapsed_ms_mean` for repeated config loads under the same
  PR-scoped probe used by CI.
