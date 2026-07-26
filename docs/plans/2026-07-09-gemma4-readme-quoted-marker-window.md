# Gemma4 README quoted-marker search window performance slice

## Scope

This Python-only performance slice is limited to the Gemma4 QAT README `base_model:` extraction helper in `services/mlx-worker-python/worker/model_registry/catalog.py`.

The behavior remains unchanged: an earlier valid unquoted `base_model:` line still takes precedence over a later quoted YAML list-style marker, invalid marker prefixes are ignored, and the existing model-size fallback remains intact.

## Registered probe

The affected path is covered by the registered PR-scoped probe `model-registry-readme-source-fastpath` in `infra/perf/pr_scoped_probes.json`. The registry entry provides focused `test_command`, `coverage_command`, and `probe_command` entries for the model registry README source path.

## Slice plan

1. Keep the existing quoted-marker fast path, but bound the preliminary earlier-marker validation search to the text before the quoted marker.
2. Preserve fallback scanning for READMEs with an earlier valid marker or invalid marker prefixes.
3. Run the registered focused tests, changed-scope coverage command, and registered probe locally on Linux before opening the PR.
4. Use GitHub Actions PR-scoped performance as the merge gate for the registered probe report.

## Metrics

Primary metric: `new_elapsed_ms_mean` from `scripts/model_registry_readme_source_probe.py`; lower is better. The probe also reports `speedup`, `delta_ms`, and peak bytes against the legacy line-splitting source extraction baseline.

## 2026-07-26 follow-up: quoted marker prefix length constant

This follow-up stays inside `_gemma4_qat_source_model(...)` and keeps the same
registered `model-registry-readme-source-fastpath` probe. The quoted marker path
now reuses a module-level prefix length constant instead of recomputing
`len("\n  '")` during every README source scan. Quoted-marker precedence,
invalid-prefix rejection, fallback scanning, and model-size fallback behavior stay
unchanged.

Expected effect: lower `new_elapsed_ms_mean` in the registered README source
probe with unchanged extracted source model and non-regressive peak bytes.
