# Runtime Settings and Discovery Surfaces

## Issue

Implements GitHub issue #641: Melix needs a stable machine-readable contract for
runtime settings, local discovery, instructions, capabilities, schema locations,
and config metadata. CLI, macOS UI, scripts, and the local daemon should consume
the same shape instead of parsing help text.

## Scope

- Add a persisted user settings file at `~/.melix/runtime_settings.json`, with
  `MELIX_HOME` resolving the user root in tests and local worktrees.
- Add a project override file at `.melix/runtime_settings.json`.
- Define settings precedence as CLI flag, environment variable, project settings,
  user settings, then default.
- Add CLI surfaces:
  - `melix settings show --json`
  - `melix settings set <key> <value>`
  - `melix settings validate`
  - `melix settings reset <key>`
  - `melix info --json`
  - `melix capabilities --json`
  - `melix instructions --json`
  - `melix schema --json`
  - `melix config metadata --json`
- Add daemon discovery surfaces when the local HTTP gateway is running:
  - `/.well-known/melix.json`
  - `/api/instructions`
  - `/api/capabilities`
  - `/api/config-metadata`
- Add model alias discovery and suggestion metadata so UI and scripts can offer
  family-safe hints without rewriting valid local paths or full model IDs.
- Add a best-effort version/update receipt to `melix info --json`. It must not
  perform network access, must not block startup, and must be safe for CI or
  non-TTY contexts.

## Settings Contract

Settings are constrained to a curated registry:

- `model_cache_path`
- `dataset_cache_path`
- `artifact_path`
- `max_concurrent_jobs`
- `memory_pressure_threshold`
- `default_dtype`
- `default_quantization`
- `benchmark_warmup`
- `benchmark_repeats`
- `eval_sample_size`
- `log_retention_days`
- `auto_cleanup_policy`

Each setting has a type, default value, environment override name, and metadata.
The effective settings payload includes both the value and source:

```json
{
  "settings": {
    "max_concurrent_jobs": {
      "value": 6,
      "source": "environment",
      "source_detail": "MELIX_MAX_CONCURRENT_JOBS"
    }
  }
}
```

## Discovery Contract

All discovery payloads use explicit schema versions and stable top-level keys.

- `melix.discovery.info.v1`
- `melix.discovery.capabilities.v1`
- `melix.discovery.instructions.v1`
- `melix.discovery.schema.v1`
- `melix.discovery.config_metadata.v1`
- `melix.runtime_settings.effective.v1`

The CLI discovery payloads include:

- Melix version and update receipt.
- Enabled features and supported task families.
- API endpoint metadata.
- Schema paths.
- Local Melix paths.
- Settings and config metadata.
- Model alias families and same-family suggestions.

## Version and Update Receipt

The update receipt is best effort and local-only:

- `installed_version`
- `latest_known_version`
- `update_available`
- `update_channel`
- `install_method`
- `suggested_update_command`
- `checked`
- `status`

The default source is local repository/package metadata plus an optional local
channel file. Missing files produce an `unavailable` receipt rather than an
error. Suggested commands are returned as argv arrays only.

## Probes and Metrics

Changed paths must report timings in JSON payloads where useful:

- `settings_resolve_ms`
- `settings_write_ms`
- `settings_validate_ms`
- `discovery_build_ms`
- HTTP discovery latency metrics:
  - `operator.discovery_well_known_latency_ms`
  - `operator.discovery_capabilities_latency_ms`
  - `operator.discovery_instructions_latency_ms`
  - `operator.discovery_config_metadata_latency_ms`

Success metrics:

- Settings resolution is deterministic and covered by precedence tests.
- CLI and HTTP discovery payloads are valid JSON and do not require help-text
  parsing.
- Alias suggestions preserve valid local paths and full Hugging Face IDs.
- Update checks are silent and non-fatal when no local channel metadata exists.

## Verification Plan

- Swift CLI parser tests for all new commands and codec IDs.
- Swift CLI runner tests for settings precedence, mutation, reset, discovery
  payloads, alias suggestions, and update receipt degradation.
- Swift HTTP gateway tests for the daemon discovery endpoints.
- Changed-line coverage for touched Swift files must stay at or above 95%.
