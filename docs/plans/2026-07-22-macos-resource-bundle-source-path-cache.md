# macOS Resource Bundle Source Path Cache

## Scope

This Python-only performance slice is limited to
`worker.productization.macos_app_bundle._copy_swiftpm_resource_bundles`.
The behavior remains unchanged: SwiftPM `.bundle` directories are copied in
stable name order to each target root, existing targets are restored on copy
failure, and non-directory or non-`.bundle` entries are ignored.

## Registered probe

The affected path is covered by the existing PR-scoped probe
`macos-app-resource-bundle-scandir` in `infra/perf/pr_scoped_probes.json`.
The registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries and watches the bundle implementation plus focused
macOS app bundle tests.

## Optimization

During the `os.scandir()` pass, retain each accepted `DirEntry.path` alongside
its bundle name. The later copy loop passes that scanned source path directly to
`shutil.copytree()` instead of reconstructing `source_root / bundle_name` for
every bundle after sorting. This keeps ordering by bundle name while removing
one Path join/construction per copied bundle.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and the
registered probe locally on Linux before pushing. GitHub Actions PR-scoped
performance remains the final merge gate.
