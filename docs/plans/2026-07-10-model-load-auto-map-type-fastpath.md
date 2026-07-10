# Model load auto_map exact string fast path

This Python-only performance slice is limited to
`worker.model_load_trust._auto_map_has_custom_loader()`.

## Slice

Most `config.json` `auto_map` values decoded by `json.loads()` are exact
`str` instances. The current scan routes those values through `isinstance`,
which also preserves `str` subclass behavior but pays the generic type check on
the common JSON path. This slice adds an exact-`str` branch before the existing
subclass-compatible fallback.

Behavior remains unchanged:

- empty and whitespace-only strings are still ignored
- non-blank strings still require explicit `trust_remote_code`
- `str` subclasses still avoid coercion and keep their existing semantics
- non-string values still use the existing fallback

## Registered performance probe

The affected path is covered by the registered PR-scoped performance probe
`model-load-config-json-bytes` in `infra/perf/pr_scoped_probes.json`. The probe
watches `services/mlx-worker-python/worker/model_load_trust.py`, focused trust
policy tests, `scripts/model_load_config_json_bytes_probe.py`, and this plan. It
has focused `test_command`, `coverage_command`, and `probe_command` entries.

## Verification plan

Run the registered focused tests, changed-scope coverage command, and the
registered probe locally on Linux. GitHub Actions PR-scoped performance remains
the merge gate after PR creation.
