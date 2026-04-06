# M15.4 Desktop Polish Integration Evidence

## Goal

Close the desktop-polish milestone with integration evidence, navigation grounding, and product-shell validation.

## Scope

- add integration coverage for polished desktop signals
- verify placeholders remain grounded in real navigation and control-plane state
- record desktop-polish metrics and operator runbook notes

## Files

- update `apps/macos-menubar/Tests/MenuBarTests/`
- update `scripts/`
- update `tests/`
- update `tests/integration/`
- update `docs/runbooks/`
- update `docs/README.md`

## Implementation Notes

- Evidence should cover token smoothing, banners, and queue recovery together.
- Placeholder validation should confirm that future-facing tabs remain attached to real product-shell state.
- Metrics should remain lightweight but reproducible.

## Verification

- `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --package-path apps/macos-menubar --filter DesktopPolishSmokeTests`
- `python3 scripts/m15_desktop_polish_smoke.py --json`
- `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest tests/test_m15_desktop_polish_smoke.py tests/integration/test_desktop_polish_smoke.py -q`
- `make integration-test`

## Acceptance

- Desktop polish has live integration evidence and documented operator workflows.
- Navigation grounding and runtime-signal behavior remain explicit and test-covered.
