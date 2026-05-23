# Text family metadata mapping no-copy slice

## Scope

Optimize the registered `text-family-config-copy-elision` Python path by avoiding an eager `dict()` copy of the `metadata` mapping in `resolve_text_family_config`.

## Constraints

- Preserve read-only mapping semantics; `resolve_text_family_config` must not mutate caller-provided metadata.
- Keep the existing config mapping no-copy behavior intact.
- Validate through the registered PR-scoped probe entry in `infra/perf/pr_scoped_probes.json`.

## Evidence target

Run focused text-family tests, changed-scope coverage, and `scripts/text_family_config_probe.py` locally on Linux. Accept only if the probe shows lower `elapsed_ms_mean` and lower or unchanged peak bytes versus `origin/main`, then rely on CI's registered PR-scoped performance report for final gate evidence.
