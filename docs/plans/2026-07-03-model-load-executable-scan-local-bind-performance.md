# Model Load Executable Scan Local Binding Performance Slice

## Scope

This Python-only performance slice is limited to
`worker.model_load_trust._detect_executable_model_files()`, the fallback scan
that detects executable Python model files when `config.json` does not already
prove a custom loader via `auto_map`.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`model-load-config-json-bytes` in `infra/perf/pr_scoped_probes.json`. The entry
watches `services/mlx-worker-python/worker/model_load_trust.py`, the focused
model-load trust tests, `scripts/model_load_config_json_bytes_probe.py`, and the
probe registry itself. It includes focused `test_command`, `coverage_command`,
and `probe_command` entries for local Linux and PR-scoped CI validation.

## Slice

Bind `_is_executable_model_file_entry` to a local variable before the
`os.scandir()` generator filters directory entries. This preserves the same
filename, prefix, and non-symlink regular-file checks while avoiding a global
lookup per scanned entry in the executable-file fallback path.

## Success Metrics

Use the registered probe metrics:

- `elapsed_ms_mean` lower is better,
- `elapsed_ms_min` informational,
- `peak_bytes_mean` lower is better,
- `rejections_mean` informational for parity.

The change is accepted only if focused tests pass, changed-scope coverage passes,
and the registered probe shows an improved or neutral elapsed-time direction
locally on Linux and in PR-scoped CI.
