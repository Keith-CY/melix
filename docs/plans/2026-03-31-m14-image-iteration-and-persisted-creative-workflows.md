# M14 Image Iteration And Persisted Creative Workflows

## Goal

Turn image generation and editing into an iterative creative workflow by adding variations, iterate and redo actions, persisted image defaults, and explicit generate-versus-edit model roles on top of the existing image-job architecture.

## Scope

- add image variations and iterate flows
- persist image-generation defaults across restarts
- separate generate-model and edit-model roles in operator workflows
- extend timeout policy for long-running creative jobs
- complete image-family picker coverage for supported families

## Coverage

- source-image variations with explicit strength control
- iterate-from-previous-artifact flow
- always-visible redo and reiteration actions
- explicit generate-model and edit-model role separation in the picker
- persisted defaults for steps, size, guidance, strength, and negative prompt
- longer `30-minute` timeout policy for generation and edit workflows
- picker coverage for `Kontext`, `Fill`, `QwenImage`, `FIBO`, and `Klein`

## Execution Slices

- `M14.1` Image variation and iterate request semantics
- `M14.2` Persisted image defaults and role-aware picker
- `M14.3` Redo actions and long-running timeout policy
- `M14.4` Image iteration integration and artifact-lineage evidence

## Files

- update `services/mlx-worker-python/worker/runtime/`
- update `services/mlx-worker-python/worker/engine/`
- update `services/control-plane-swift/Sources/`
- update `apps/macos-menubar/Sources/AppMain/Image/`
- update `apps/macos-menubar/Sources/AppMain/Models/`
- update `tests/integration/`
- update `docs/runbooks/`

## Implementation Notes

- Variations and iterate flows must remain image-job operations rather than ad hoc desktop-only shortcuts.
- Persisted image defaults should merge cleanly with model-specific defaults and per-request overrides.
- Longer timeout handling should remain explicit in job state and operator surfaces, not hidden inside worker-local retries.
- Model-role separation should be driven by capability metadata rather than UI-only labeling.

## Verification

- `make swift-test`
- `make py-test`
- `make integration-test`
- image-iteration smoke command for the touched scope

## Acceptance

- Image variations, iterate actions, and redo flows are available through the supported product surface.
- Persisted image defaults survive restart and remain inspectable.
- Long-running image jobs expose coherent timeout, cancel, and retry behavior.
