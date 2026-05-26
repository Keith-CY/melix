# Hub Catalog MLX Library Fast Path

## Scope

This slice keeps the existing Hub catalog PR-scoped probe and narrows one Python hot path: raw Hub payload MLX compatibility detection before catalog record construction.

## Registered Probe

Affected paths are already covered by `hub-catalog-size-hint-regex-precompile` in `infra/perf/pr_scoped_probes.json`.

- `test_command`: focused Hub catalog tests plus PR-scoped performance registry checks.
- `coverage_command`: focused coverage for `hub_catalog.py`, tests, registry checks, and the probe script.
- `probe_command`: `scripts/hub_catalog_size_hint_probe.py`, including `payload_compatibility_elapsed_ms_mean` for `_payload_is_mlx_compatible`.

## Change

Check the payload `library_name` / card `library_name` field before scanning tag lists, using an exact three-character ASCII case-insensitive comparison for the literal `mlx` value. This preserves the existing exact-match semantics for library names while avoiding tag-list scanning on library-signaled MLX payloads. Tag matching itself remains exact and case-insensitive via the existing lower-case path, so longer tag strings such as `mlx-compatible` remain non-matches in tag fields.

## Validation Plan

1. Run focused Hub catalog tests.
2. Run the registered changed-scope coverage command.
3. Run the registered probe locally on Linux and compare against the pre-change baseline.
4. Push and rely on the PR-scoped performance workflow for CI validation before merge.
