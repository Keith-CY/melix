# Model Load Config Stat Cache Performance Slice

## Scope

This slice optimizes repeated model-load trust policy resolution for the same
local model directory. `resolve_model_load_trust_policy()` checks `config.json`
for `auto_map` metadata on every applicable load request; repeated checks for an
unchanged config file can reuse the parsed JSON payload keyed by the config path,
mtime nanoseconds, and byte size.

Behavior remains unchanged for missing, non-file, unreadable, invalid, or
non-object `config.json` payloads. When the file stat changes, the cache key
changes and the next policy resolution rereads and reparses the config.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`model-load-config-json-bytes` in `infra/perf/pr_scoped_probes.json`. That entry
includes focused model-load trust tests, changed-scope coverage, and a probe
command that repeatedly resolves a custom-loader model's trust policy.

## Verification plan

- Run the focused model-load trust tests from the registered probe, including a
  regression guard that repeated policy resolution reads `config.json` once for
  an unchanged stat tuple.
- Run changed-scope coverage for the touched model-load trust scope.
- Run `scripts/model_load_config_json_bytes_probe.py` locally on Linux against
  base and head to compare `elapsed_ms_mean` and `peak_bytes_mean`.
- Use the PR-scoped performance GitHub Actions workflow as the final registered
  probe validation before merge.

## Expected outcome

The repeated-resolution probe should spend less time in file reads and JSON
parsing while keeping rejection semantics and detection-source receipts stable.
