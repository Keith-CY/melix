# M17.2 Text-To-Speech Backend Adapters And Multilingual Voice Catalog

## Goal

Add real text-to-speech backend families and a multilingual voice catalog so Melix can expose voice-aware synthesis behavior rather than a generic speech placeholder.

## Scope

- add `Kokoro`-class backend adapters and multilingual native-voice support
- expose voice, language, and output-format metadata
- validate per-voice synthesis routing and fallback behavior

## Files

- update `services/mlx-worker-python/worker/runtime/`
- update `services/mlx-worker-python/worker/model_registry/`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `apps/macos-menubar/Sources/AppMain/`
- update `tests/integration/`

## Implementation Notes

- Voice identity should be first-class metadata, not an unstructured string buried inside request arguments.
- Fallback behavior must be deterministic when a requested language or voice is unavailable.

## Verification

- `make py-test`
- `make swift-test`
- `make integration-test`

## Acceptance

- Text-to-speech backends and voices are operator-visible, routable, and test-covered.
- Voice and language fallback behavior remains explicit and reproducible.

## Status

- Completed on 2026-04-06.
- Verification:
  - `make proto`
  - `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_audio_runtime.py services/mlx-worker-python/tests/test_mlx_audio_runtime.py services/mlx-worker-python/tests/test_runtime_edges.py services/mlx-worker-python/tests/test_acceptance_metrics.py tests/integration/test_non_text_endpoints.py -q`
  - `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python coverage run --data-file=/tmp/m17_2_python.coverage -m pytest services/mlx-worker-python/tests/test_audio_runtime.py services/mlx-worker-python/tests/test_mlx_audio_runtime.py services/mlx-worker-python/tests/test_runtime_edges.py services/mlx-worker-python/tests/test_acceptance_metrics.py tests/integration/test_non_text_endpoints.py -q`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --package-path services/control-plane-swift --filter 'ModelCatalogTests|PythonBridgeWorkerClientTests'`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --package-path apps/macos-menubar --filter 'DesktopFoundationViewTests|RuntimeViewModelTests|DesktopPolishSmokeTests'`
  - `make py-test`
  - `make integration-test`
  - `git diff --check`
- Notes:
  - repository-wide `make swift-test` still stalls in the untouched `services/control-plane-swift`
    full-package path after the touched focused suites pass; the hung `swiftpm-testing-helper`
    was sampled and terminated, and the issue remains recorded as existing repository instability
    outside the `M17.2` touched scope.
