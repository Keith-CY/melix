# Storage Inventory And Cleanup Receipts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver #1517 by adding shared storage inventory, cleanup dry-run, and cleanup apply receipts for Melix workspace and runtime artifacts.

**Architecture:** The Swift CLI owns one shared storage maintenance builder that scans workspace manifests and Melix-owned runtime roots, emits canonical JSON receipts, and performs guarded deletion only during apply. Desktop consumes the same receipt fields from diagnostic bundle JSON and renders summaries without re-running inventory or cleanup logic.

**Tech Stack:** Swift CLI core, Swift Testing, macOS menubar SwiftUI state tests, JSON receipt contracts from `docs/plans/2026-06-25-desktop-environment-doctor-storage-cleanup.md`.

---

## Governing Context

- Issue: [#1517](https://github.com/Keith-CY/melix/issues/1517)
- Parent: [#1515](https://github.com/Keith-CY/melix/issues/1515)
- Roadmap: `docs/plans/2026-05-24-m-courtyard-improvement-roadmap.md`
- Contract: `docs/plans/2026-06-25-desktop-environment-doctor-storage-cleanup.md`
- Workspace manifest contract: `docs/workspace-manifest-contract.md`

This slice does not change protobuf schemas. It introduces local CLI and
Desktop receipt handling for the already documented P4.2 storage contract.

## Command Surface

Add these CLI commands:

```bash
melix storage inventory [--workspace-manifest PATH] [--json]
melix storage cleanup plan [--workspace-manifest PATH] [--json]
melix storage cleanup apply [--workspace-manifest PATH] [--json]
```

`--json` returns the canonical receipt. Text output is a short operator summary
derived from the same receipt fields.

## Receipt Behavior

Inventory writes schema `melix.storage_inventory_receipt.v1` and includes every
artifact kind required by #1517:

- `raw_file`
- `cleaned_segment`
- `dataset_version`
- `checkpoint`
- `adapter_output`
- `export_intermediate`
- `runtime_log`
- `stale_temp_file`
- `evidence_bundle`

Cleanup dry-run writes schema `melix.storage_cleanup_plan.v1` with mode
`dry_run`. It reports retained, cleanable, protected, and blocked byte counts
and never deletes files.

Cleanup apply writes schema `melix.storage_cleanup_receipt.v1`. It creates a
same-run inventory and plan, rechecks mtime, byte size, path digest, ownership,
and active-job protection immediately before deletion, then deletes only
unchanged cleanable Melix-owned artifacts. Each apply writes the receipt under
`$MELIX_HOME/storage-cleanup/cleanup-receipts/` and returns only a redacted
receipt path plus a path digest in JSON output.

Debug bundle generation writes `storage-inventory.json` and
`storage-cleanup-plan.json` from the same storage maintenance builder. When an
apply receipt already exists under the Melix-owned receipt directory, the debug
bundle also copies the latest receipt to `storage-cleanup-receipt.json`. The
manifest embeds the same redacted payloads so Desktop can render inventory,
plan, and apply-result summaries without re-running storage probes or inferring
cleanup state from UI.

## Retention Rules

Retained by default:

- raw files
- dataset versions
- adapter outputs
- evidence bundles

Cleanable when Melix-owned or workspace-owned and inactive:

- cleaned segments
- checkpoints
- export intermediates
- runtime logs
- stale temp files

Blocked:

- missing manifest entries
- external read-only roots
- unknown artifact kinds or unsafe paths

Unsafe manifest paths include empty paths, absolute paths, Windows-style drive
or backslash paths, and relative paths that escape their declared artifact root
after normalization. Storage maintenance records those entries as blocked
without stat'ing or deleting the escaped target.

Protected:

- any artifact path equal to or contained under an active run artifact root
- any artifact path equal to or contained under an active local training queue
  run directory
- any artifact that changes between same-run plan generation and apply deletion

## Metrics

Receipts include these metrics where applicable:

- `storage_inventory_latency_ms`
- `inventory_artifact_count`
- `inventory_byte_size`
- `retained_byte_size`
- `cleanable_byte_size`
- `protected_active_artifact_count`
- `cleanup_dry_run_latency_ms`
- `cleanup_apply_latency_ms`
- `safe_delete_count`
- `deleted_byte_size`
- `cleanup_failure_count`

## Files

- Create `Sources/MelixCLICore/MelixStorageMaintenance.swift`
- Modify `Sources/MelixCLICore/MelixCLI.swift`
- Modify `Sources/MelixCLICore/MelixCLICommandCodec.swift`
- Modify `Sources/MelixCLICore/MelixDiagnostics.swift`
- Modify `tests/MelixCLITests/MelixCLIParserTests.swift`
- Modify `tests/MelixCLITests/MelixCLIRunnerTests.swift`
- Modify `apps/macos-menubar/Sources/AppMain/Models/RuntimeDiagnosticsDebugBundleState.swift`
- Modify `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`
- Modify `apps/macos-menubar/Tests/MenuBarTests/RuntimeEvidenceReportStateTests.swift`

## Verification

Use TDD for each behavior. Focused checks:

```bash
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --filter 'MelixCLIParserTests/parsesRuntimeSettingsAndDiscoveryCommands'
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --filter 'MelixCLIRunnerTests/storageInventoryCleanupPlanAndApplyShareSafeReceipts'
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --filter 'MelixCLIRunnerTests/debugBundleEmbedsLatestStorageCleanupReceiptForDesktopResultParity'
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" swift test --filter 'MelixCLIRunnerTests/offlineRunRecordCommandsListShowExportAndReportLocalArtifacts'
HOME="$PWD/.swift-home-menubar" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.menubar.noindex" swift test --package-path apps/macos-menubar --filter 'RuntimeEvidenceReportStateTests/diagnosticsRendersStorageCleanupReceiptsFromDebugBundleState'
HOME="$PWD/.swift-home" CLANG_MODULE_CACHE_PATH="$PWD/.build/ModuleCache.noindex" make swift-test
```

Full pre-PR gate:

```bash
git diff --check
make swift-test
make py-test
make integration-test
```
