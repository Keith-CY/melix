# Response-Only LoRA UI Receipts Plan

## Goal

Surface the response-only LoRA truncated-label guard added in #1231 as
structured Window UI evidence instead of leaving operators to inspect raw JSON
or terminal output.

## Scope

- Decode `response_only_labels_truncated` and the related response-only token
  metrics from saved LoRA training job output.
- Render a dedicated saved-job detail section for response-only safety,
  including the recovery hint, `max_seq_length`, boundary statistics, trainable
  response token count, and fully truncated sample count.
- Keep the raw output disclosure for auditability, but make the actionable
  failure reason visible before it.

## Out Of Scope

- Changing the backend guard or training semantics.
- Adding a new training execution path.
- Launching the app or running manual UI E2E for this focused follow-up.

## Verification

- Add focused `RuntimeViewModelTests` coverage for receipt decoding.
- Add focused `DesktopFoundationViewTests` coverage for saved-job detail
  rendering.
- Keep the macOS menubar Makefile verification path on `-Xswiftc -gnone`
  while the Swift 6.2/macOS 26 linker emits DWARF input-verification noise for
  full debug symbols in this SwiftUI-heavy test bundle.
- Run the touched Swift test filters after implementation.
