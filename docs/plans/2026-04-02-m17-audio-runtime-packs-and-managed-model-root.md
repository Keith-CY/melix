# M17 Audio Runtime Packs, Managed Model Root, And First-Use Download Flows

## Goal

Turn the existing `mlx-audio` library integration into a product-shaped Melix audio experience by separating downloadable runtime assets from downloadable model assets, routing models through one managed model root, and making first-use download requirements explicit in the control plane and desktop shell.

## Scope

- stabilize and commit the current `mlx-audio` library-integration baseline
- add a product-managed default model root for Melix-owned downloaded assets
- add an audio runtime-pack asset layer separate from model storage
- add control-plane readiness checks before real audio requests are dispatched
- add operator-visible first-use download flows for audio support and audio models
- extend release gates and recovery checks for runtime-pack install and model download behavior

## Non-Goals

- no new public audio HTTP routes
- no speech-to-speech support
- no separate audio-only model path that bypasses the registry
- no reliance on `pip`, `uv sync`, or direct upstream lazy downloads on end-user machines

## Dependencies

- existing library integration plan: `docs/plans/2026-04-02-m17-mlx-audio-library-integration.md`
- existing multi-root registry direction: `docs/plans/2026-03-30-m8-1-multi-root-model-registry.md`
- existing registry-management slice: `docs/plans/2026-03-31-m12-1-multi-root-registry-management-and-rescan.md`
- existing download resilience direction: `docs/plans/2026-03-30-m8-4-resumable-downloads-retries-and-mirrors.md`
- existing desktop download recovery direction: `docs/plans/2026-03-31-m15-3-download-queue-persistence-and-paused-recovery.md`

## Execution Slices

- `M17.5` Verify and commit the current `mlx-audio` adapter baseline as the prerequisite integration layer.
- `M17.6` Add a default managed model root under `MELIX_HOME` and define product-owned audio runtime-pack metadata and state.
- `M17.7` Add control-plane audio readiness checks plus desktop download prompts so first-use audio requests surface clear runtime-pack and model requirements.
- `M17.8` Add recovery, release-gate, and metrics coverage for slim and full product builds.

## Files

- update `docs/README.md`
- update `services/mlx-worker-python/worker/productization/install_assets.py`
- update `services/mlx-worker-python/worker/productization/macos_app_bundle.py`
- update `services/mlx-worker-python/worker/productization/release_gates.py`
- update `services/mlx-worker-python/worker/productization/acceptance_metrics.py`
- update `services/control-plane-swift/Sources/ModelCatalog/`
- update `services/control-plane-swift/Sources/WorkerClient/`
- update `services/control-plane-swift/Sources/XPCService/`
- update `services/control-plane-swift/Sources/HTTPGateway/OpenAI/`
- update `services/control-plane-swift/Sources/Snapshots/`
- update `apps/macos-menubar/Sources/AppMain/`
- update `services/mlx-worker-python/worker/model_ops/`
- update `tests/integration/`

## Design Rules

- The Melix app bundle may ship with Python runtime support, but audio runtime-pack installation remains a Melix-managed asset action rather than a user-managed Python dependency action.
- Downloaded audio models must live under the default managed model root and be registered through the same root-based registry semantics used for other Melix-managed models.
- Runtime-pack state and model-download state must be operator-visible and machine-readable.
- The control plane should block first-use real audio requests before worker dispatch when required assets are missing, so the desktop shell can offer targeted remediation instead of surfacing raw backend errors.
- The worker remains the fallback truth for missing dependency failures, but the primary user-facing path should be a control-plane readiness check.
- The first product slice may map `audio-stt` and `audio-tts` to one runtime-pack artifact if that keeps packaging and recovery simpler.

## Managed Paths

- default managed model root: `$MELIX_HOME/models/default-managed`, with `$HOME/.melix/models/default-managed` as the default
- audio runtime-pack root: `$MELIX_HOME/runtime-packs/audio`, with `$HOME/.melix/runtime-packs/audio` as the default

Both paths are product defaults, not hardcoded audio-only discovery exceptions. The managed model root must remain compatible with future ordered multi-root scanning.

## Metrics

- existing audio runtime probes remain stable
- add product metrics for:
  - `audio_runtime_pack_install_ms`
  - `audio_model_download_ms`
  - `audio_first_use_blocked_runtime_pack_count`
  - `audio_first_use_blocked_model_count`
  - `audio_runtime_pack_recovery_success_rate`

## Verification

- `make proto`
- `make py-test`
- `make swift-test`
- `tests/integration/test_non_text_endpoints.py -q`
- targeted touched-scope coverage for the Python worker and new audio asset paths
- targeted Swift test selections covering model catalog, control-plane gating, and desktop download state

## Acceptance

- The current `mlx-audio` adapter baseline is committed and remains verified.
- Melix-managed downloaded audio models resolve through the managed model root rather than an audio-specific side path.
- First-use audio requests clearly distinguish missing runtime-pack state from missing model state.
- The desktop shell can guide an operator through installing audio support and then downloading the requested model.
- Release evidence distinguishes slim builds that require download actions from full builds that ship with audio support preinstalled.
