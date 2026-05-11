# Swift Binary Resolution Streaming Probe Slice

## Scope

This performance slice keeps the existing Swift integration binary lookup behavior but removes candidate-list materialization from the resolver used by `tests/integration/helpers.py`.

Affected path:

- `tests/integration/helpers.py`
- `tests/integration/test_helper_binary_resolution.py`
- `scripts/integration_swift_binary_resolution_probe.py`
- `infra/perf/pr_scoped_probes.json` entry `integration-swift-binary-resolution-scandir`

## Registered Probe

The affected path is covered by the registered PR-scoped probe `integration-swift-binary-resolution-scandir`.

Required focused commands:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q tests/integration/test_helper_binary_resolution.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_integration_swift_binary_resolution_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_integration_swift_binary_resolution_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q tests/integration/test_helper_binary_resolution.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_integration_swift_binary_resolution_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_integration_swift_binary_resolution_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json tests/integration/helpers.py tests/integration/test_helper_binary_resolution.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/integration_swift_binary_resolution_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_SWIFT_BINARY_RESOLUTION_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python bash -c 'SCRIPT="scripts/integration_swift_binary_resolution_probe.py"; if [ -f "$SCRIPT" ]; then python3 "$SCRIPT"; else for PREFIX in "${MELIX_SWIFT_BINARY_RESOLUTION_HEAD_REPO:-}" "${GITHUB_WORKSPACE:-}/head" "../head"; do CANDIDATE="$PREFIX/$SCRIPT"; if [ -f "$CANDIDATE" ]; then python3 "$CANDIDATE"; exit $?; fi; done; echo "missing probe script fallback for $SCRIPT" >&2; exit 2; fi'
```

## Implementation Plan

1. Preserve `_swift_product_binary_candidates()` for existing direct callers and regression coverage.
2. Keep the streaming resolver path that considers the flat debug binary and each architecture-specific debug binary without building an executable candidate list.
3. Preserve the existing newest-mtime tie-breaker while replacing per-candidate `Path.parts` allocation with a constant flat/scoped depth rank.
4. Extend focused integration-helper coverage to prove equal-mtime scoped candidates remain preferred without reading `Path.parts` during resolution.
5. Measure the registered probe against the legacy glob/list baseline and accept only if elapsed and/or peak memory remain improved.

## Success Metrics

- Focused tests pass.
- Changed-scope coverage for touched Python lines is at least 95%.
- The registered probe reports lower `elapsed_ms_mean` and/or `peak_bytes_mean` versus its legacy glob/list baseline.

## Verification Boundary

This is a Python integration-helper slice and is locally verifiable on Linux. It does not validate Swift runtime performance locally; the resolver path itself is Python and the registered PR-scoped probe remains the merge gate.
