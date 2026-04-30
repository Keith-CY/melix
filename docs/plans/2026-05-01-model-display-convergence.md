# Model Display Convergence Plan

## Goal

Make Melix model listings less confusing for normal users while preserving stable model IDs and internal routing behavior.

## Architecture

The Swift control plane remains the source of truth for the public model listing. `/v1/models` keeps its OpenAI-compatible response shape, filters internal model-operation entries, and projects user-facing display and capability metadata. The desktop shell consumes the same catalog summaries but filters internal models from user-facing lists and prefers aliases for visible labels.

## Implementation Notes

- Keep `melix-dev-*` IDs stable.
- Do not remove `melix-dev-model-ops` from `ModelCatalog`; only hide it from public `/v1/models` and ordinary desktop model lists.
- Continue exposing registry metadata for imported or registry-discovered models.
- Do not expose built-in seed default paths such as `models/melix-dev-text` through `/v1/models` metadata.

## Verification

- Add Swift gateway tests for public filtering and metadata projection.
- Add menu bar view-model tests for hidden internal entries and friendly aliases.
- Update the live `/v1/models` integration test for the same public contract.

## Success Metrics

- Public `/v1/models` rows do not include `melix-dev-model-ops` or models marked with `melix.visibility=internal`.
- Public model metadata includes display, kind, and capability fields without leaking built-in `models/melix-dev-*` default paths.
- Registry-discovered models retain their existing registry identity metadata and `melix.model_path` fields.
- Desktop model lists and pickers show alias/display name first and keep model IDs as secondary detail.

## Measurement Points

- HTTP projection is measured by gateway tests around `/v1/models` response content.
- Desktop projection is measured by `RuntimeViewModel` tests around visible model rows and picker source collections.
- Live behavior is measured by the integration test that boots a local stack and queries `/v1/models`.
