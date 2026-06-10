# Admin Surface Persistence

## Purpose

Validate the `M8.6` operator-session persistence contract for the native desktop admin surface:

- operator navigation restores deterministically across restart
- persisted admin state is stored under product-owned local paths
- the operator shell does not rely on CDN-hosted admin assets when offline packaging matters

## Persisted Navigation State

Melix persists operator-session state under `MELIX_HOME/state/operator-session.json`.

The current payload includes:

- `selected_surface`
- `selected_tool_section`
- `selected_provider_id`
- `providers`

`selected_tool_section` is persisted even when the operator is not currently focused on the Tools
surface. This keeps the last-selected tools workspace deterministic the next time the operator
returns to `Tools`.

The decoder remains backward compatible with older payloads that do not yet carry
`selected_tool_section`; those payloads restore with `Models Library` as the default tool section.

## Offline-Owned Assets

The native desktop admin shell uses repository-owned SwiftUI views, bundled app resources, and
platform-native SF Symbols. There are currently no CDN-hosted admin assets required for the
operator shell, so offline packaging does not depend on remote web assets.

If future admin surfaces introduce remote assets, update this runbook and the M8.6 smoke evidence
in the same change.

## Smoke Command

Run the repository-owned smoke command:

```bash
python3 scripts/m8_admin_state_smoke.py --json
```

The smoke wraps a focused Swift test suite and proves:

- `selected_tool_section` is written to the operator-session file
- the persisted tool section restores across restart
- `MELIX_HOME`, `state/`, and `operator-session.json` keep secure permissions
- the admin shell reports zero external asset references

Expected machine-readable metrics include:

- `operator.session_restore_ms`
- `operator.session_persist_write_ms`
- `operator.session_tool_section_persisted`
- `operator.session_tool_section_restored`
- `operator.session_root_permissions_ok`
- `operator.session_state_directory_permissions_ok`
- `operator.session_file_permissions_ok`
- `operator.offline_asset_external_reference_count`

## Focused Swift Verification

When debugging the smoke directly, run the underlying focused suite:

```bash
HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/apps/macos-menubar/.build/ModuleCache.noindex" \
swift test --package-path apps/macos-menubar --filter OperatorSessionPersistenceSmokeTests
```
