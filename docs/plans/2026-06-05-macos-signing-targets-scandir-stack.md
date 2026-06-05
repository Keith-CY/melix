# macOS signing target scandir stack slice

## Scope

This Python-only performance slice is limited to `worker.productization.macos_app_bundle._iter_nested_macho_signing_targets`.
The signing target walk already avoids `Path.rglob`; this slice removes the remaining `os.walk` tuple assembly and `root_path / filename` joins from the Mach-O signing discovery path by using a direct `os.scandir` stack.

## Registered probe

The affected path is covered by the registered PR-scoped probe `macos-app-signing-targets-scandir` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries and runs `scripts/macos_app_signing_targets_probe.py`.

## Plan

1. Preserve signing target semantics: return nested Mach-O files sorted by POSIX path, skip symlinked directories, and tolerate metadata/read errors.
2. Add a regression guard proving the helper does not call `os.walk` or `Path.rglob` for this scan.
3. Replace the helper implementation with an explicit `os.scandir` directory stack that keeps directory stack entries as `Path` values.
4. Verify with the registered focused tests, changed-scope coverage, and the registered local Linux probe; use PR-scoped performance CI as the merge gate.

## Metrics

Success is measured by `elapsed_ms_mean`, `elapsed_ms_min`, and `discovered_count` from `scripts/macos_app_signing_targets_probe.py`; behavior parity is measured by focused macOS app bundle tests and changed-scope coverage for the touched module, tests, registry, and probe script.
