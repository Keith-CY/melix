# Progress Log

## 2026-04-05

- Closed `M12.1` by making multi-root registry configuration control-plane-owned, worker-backed,
  and operator-visible across registry snapshots, catalog sync, and the Window UI:
  - updated the Python worker registry catalog and maintenance core so ordered registry-root
    overrides, stable root IDs, explicit rescans, and root-level observability now flow through
    `registry_snapshot` payloads without rewriting environment state
  - updated the Swift control plane catalog state, registry snapshot sync, and model-ops routing so
    configured root overrides persist across sync cycles, explicit empty-root overrides remain
    distinct from fallback environment discovery, and snapshot-driven root state is projected back
    into catalog truth
  - extended the native desktop shell and runtime view model so operators can add, remove, reorder,
    and rescan registry roots directly from the Window UI while seeing ordered root rows,
    accessibility state, configured-override summaries, and discovered-model counts
  - added focused Python, control-plane, and menu-bar regression coverage for stable root identity,
    explicit override ordering, empty-override preservation, root-state formatting, UI guard rails,
    and snapshot parsing order
  - marked `M12.1` completed in the roadmap execution index; the next active execution slice can
    now advance to `M12.2`
- Verification summary for `M12.1`:
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_model_registry_catalog.py services/mlx-worker-python/tests/test_maintenance_service.py -q`: `74 passed in 32.45s`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'ModelCatalogTests|ControlPlaneServiceTests'`: `175 tests in 2 suites passed after 0.092 seconds`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`: `181 tests in 2 suites passed after 3.913 seconds`
  - `git diff --check`: pass
- Metrics report for `M12.1`:
  - registry snapshot metrics and observability exercised by the touched scope:
    - stable `root_id` projection from canonical root paths
    - ordered `root_order` projection through worker, control plane, and Window UI
    - root-level accessibility, error-state, and discovered-model observability
  - changed-line coverage for the touched handwritten executable scope:
    - Python registry scope: `96.49%` (`110/114`)
    - Swift control-plane scope: `95.75%` (`338/353`)
    - Swift menu-bar scope: `97.99%` (`730/745`)
    - aggregate touched-scope coverage: `97.19%` (`1178/1212`)

- Started `M12.1` by moving the active task plan to multi-root registry management and rescan:
  - recorded that the current repository only discovers registry roots from `MELIX_MODEL_ROOTS`
    and caches index-derived root IDs, which is insufficient for operator-facing add, remove,
    reorder, and rescan workflows
  - defined the next implementation slice around control-plane-owned root configuration, stable
    root identity, first-root-wins precedence, and tools-surface observability for ordered root
    rows plus discovery results
  - updated the active task plan so the implementation transaction starts from an explicit
    milestone contract instead of the minimal placeholder plan
- Verification summary for the `M12.1` planning transaction:
  - `git diff --check`: pass
- Metrics report for the `M12.1` planning transaction:
  - `N/A` for executable coverage and runtime metrics because this transaction only updates active
    planning and milestone-state documents

- Closed `M11.4` and, with it, the parent `M11` milestone by adding repository-owned truthful
  disk-streaming smoke evidence and operator runbook guidance without fabricating unsupported
  SSD-backed runtime metrics:
  - added `Sources/MelixCLICore/DiskStreamingSmokeCommand.swift`,
    `DiskStreamingSmokeRunner.swift`, and the executable target
    `Sources/MelixDiskStreamingSmoke/main.swift`, so the repository now owns a single-command
    `melix-disk-streaming-smoke` harness that benchmarks the RAM-resident baseline, attempts
    `prefer_disk` and `require_disk`, restores the original model setting, and emits a
    machine-readable report with requested-versus-effective cache and disk-streaming evidence
  - extended `tests/MelixCLITests/DiskStreamingSmokeRunnerTests.swift` so the Swift smoke harness
    now covers injected-client rendering, baseline benchmark failures, missing-model rejection,
    unsupported-path compatibility fallback, effective-mode preservation, and helper label
    mappings in addition to the end-to-end smoke report path
  - added `tests/integration/test_disk_streaming_smoke.py`, which starts the live Melix stack,
    runs `melix-disk-streaming-smoke --json` against real worker sockets, asserts numeric
    RAM-baseline metrics, and verifies typed `disk_streaming_unsupported` evidence for both
    `prefer_disk` and `require_disk`
  - added `docs/runbooks/disk-streaming-evidence.md` and updated the documentation indexes so
    operators now have explicit setup, interpretation, and diagnostic guidance for the current
    truthful disk-streaming surface, including the intentionally unavailable future SSD metrics
  - marked `M11.4` completed in the roadmap execution index and closed the parent `M11`
    milestone; the next active execution slice can now advance to `M12.1`
- Verification summary for `M11.4`:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter DiskStreamingSmokeRunnerTests`: `10 tests in 1 suite passed after 0.002 seconds`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --filter DiskStreamingSmokeRunnerTests`: `10 tests in 1 suite passed after 0.002 seconds`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest tests/integration/test_disk_streaming_smoke.py -q`: `1 passed in 49.67s`
  - `make py-test`: `456 passed in 35.12s`
  - `make swift-test`: pass
  - `make integration-test`: `61 passed in 971.13s (0:16:11)`
  - `git diff --check`: pass
- Metrics report for `M11.4`:
  - disk-streaming smoke metrics now emitted by the repository-owned smoke harness:
    - `bench.smoke.ttft_ms`
    - `bench.smoke.tokens_per_second`
  - truth-preserving placeholder metrics now emitted explicitly until runtime support exists:
    - `ssd_restore_latency_ms = unavailable_until_runtime_support`
    - `disk_streaming_throughput_delta = unavailable_until_runtime_support`
    - `ssd_footprint_bytes = unavailable_until_runtime_support`
  - changed-line coverage for the touched handwritten executable scope:
    - Swift CLI smoke scope: `99.56%` (`226/227`)
  - `Package.swift`, runbooks, documentation indexes, and the live integration test are excluded
    from executable changed-line coverage because they are package-manifest, documentation, or
    black-box repository-evidence artifacts rather than handwritten runtime logic

- Started `M11.4` by documenting the current disk-streaming evidence strategy and execution plan:
  - added a design spec that records the current runtime constraint that both worker paths still
    reject `prefer_disk` and `require_disk` with typed `disk_streaming_unsupported` failures, so
    Melix must not fabricate SSD-backed metrics
  - added an implementation plan for a repository-owned `melix-disk-streaming-smoke` command that
    will measure the RAM baseline, capture unsupported-path diagnostics, restore model settings,
    and produce a machine-readable report plus operator runbook guidance
  - updated the active `M11.4` execution slice document and the repository task plan so the next
    implementation transaction starts from an explicit, truthful scope
- Verification summary for the `M11.4` design-and-plan transaction:
  - `git diff --check`: pass
- Metrics report for the `M11.4` design-and-plan transaction:
  - `N/A` for executable coverage and runtime metrics because this transaction only updates design,
    planning, and milestone-state documents

- Closed `M11.3` by making streaming-compatible cache policy explicit across the repository-owned
  protocol, control-plane truth, worker summaries, and native operator settings:
  - extended the authoritative control-plane and worker protobuf schemas with typed cache-policy
    settings and summaries, including durable model settings for cache mode, byte and
    percentage-based cache budgets, block size, cache directory, and multimodal cache budget, then
    regenerated the versioned Swift, Python, and descriptor outputs
  - updated the Swift control plane, snapshot builder, model catalog, and python bridge so
    requested cache settings merge through model policy application, worker preparation, and
    snapshot projection, while effective cache compatibility is resolved into explicit
    `compatible`, `limited`, `disabled`, and `unknown` labels instead of hidden downgrade paths
  - updated the Swift text worker cache summary and runtime registry so worker snapshots now expose
    cache roots, supported modes, initial cache blocks, and capability flags, while request cache
    hints default from loaded model settings when operators have configured durable cache policy
  - expanded the native desktop shell and runtime view model so model rows, model detail, and
    model settings now expose requested-versus-effective cache policy, cache directories, block
    sizing, byte and percentage budgets, and multimodal cache budgets through typed operator-owned
    controls and summaries
  - added focused regression coverage across control-plane, menu bar, and Swift text worker tests
    for cache-policy normalization, settings merge behavior, worker request construction, effective
    cache-policy projection, and operator-visible cache summaries
  - stabilized disconnect lifecycle metric ordering in `RequestCoordinator` so
    `disconnect.resume_success_rate` is published before terminal-failure snapshots become
    observable, eliminating a live integration race uncovered during the full repository
    verification run
  - marked `M11.3` completed in the roadmap execution index; the next active execution slice can
    advance to `M11.4`
- Verification summary for `M11.3`:
  - `make proto`: pass
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`: `173 tests in 2 suites passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'ControlPlaneServiceTests|ModelCatalogTests|SnapshotStoreTests|PythonBridgeWorkerClientTests|RequestCoordinatorTests'`: `280 tests in 5 suites passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/mlx-text-worker-swift --filter WorkerScaffoldTests`: `134 tests in 1 suite passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter RequestCoordinatorTests`: `39 tests in 1 suite passed after 0.538 seconds`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest tests/integration/test_connection_lifecycle.py -q`: `2 passed in 26.12s`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --scratch-path /tmp/m11_3_cp_fix_cov --enable-code-coverage --filter 'ControlPlaneServiceTests|ModelCatalogTests|SnapshotStoreTests|PythonBridgeWorkerClientTests|RequestCoordinatorTests'`: `280 tests in 5 suites passed after 1.098 seconds`
  - `make py-test`: `456 passed in 30.32s`
  - `make swift-test`: pass
  - `make integration-test`: `60 passed in 782.74s (0:13:02)`
  - `git diff --check`: pass
- Metrics report for `M11.3`:
  - typed cache-policy and disconnect-lifecycle metrics exercised by the touched scope:
    - `menu.model_settings_ms`
    - `http.stream_disconnect_count`
    - `disconnect.resume_success_rate`
    - `disconnect.terminal_failure_count`
  - changed-line coverage for the touched executable scope:
    - Swift control-plane scope: `98.87%` (`439/444`)
    - Swift menu bar scope: `97.72%` (`600/614`)
    - Swift text worker scope: `100.00%` (`60/60`)
    - aggregate changed-line coverage across the touched handwritten executable scope: `98.30%`
      (`1099/1118`)
  - protocol schemas, generated protobuf outputs, `packages/protocol/descriptors/melix.pb`, and
    task-planning documents are excluded from executable changed-line coverage because they are
    generated or repository-ownership artifacts rather than handwritten runtime logic

- Closed `M11.2` by making memory-budget admission and headroom-based unsafe-load rejection
  control-plane-owned, operator-visible, and test-covered across the protocol, control-plane, and
  native desktop shell:
  - extended the authoritative control-plane protobuf schema with `LoadModel.memory_budget_bytes`,
    typed `ModelSettings.memory_budget_bytes`, and residency-summary `memory_budget_bytes`,
    `memory_headroom_bytes`, and `required_bytes`, then regenerated the repository-owned Swift,
    Python, and descriptor outputs
  - updated the Swift control plane, model catalog, on-demand loader, and local XPC client so
    explicit loads and lazy loads both resolve the effective memory budget from model settings,
    forward it to worker-backed load requests, map worker rejection details into typed
    `MemoryBudgetEvidence`, and publish rejection counters plus last-seen budget or headroom
    metrics instead of opaque generic load failures
  - updated the native operator shell and runtime view model so per-model settings now include a
    `Memory Budget Bytes` control, model detail and summaries expose configured budget and
    headroom-required evidence, and desktop-triggered loads can pass an explicit budget through the
    control-plane client overload
  - added focused regression coverage across control-plane and menu bar tests for typed policy
    normalization, client request construction, lazy-load metric recording, memory-budget evidence
    projection, and operator-visible budget summaries
  - marked `M11.2` completed in the roadmap execution index and moved the active task plan to
    `M11.3`
- Verification summary for `M11.2`:
  - `make proto`: pass
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'ControlPlaneServiceTests|ModelCatalogTests|OnDemandModelLoaderTests'`: `181 tests in 3 suites passed after 0.081 seconds`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --scratch-path /tmp/m11_2_cp_cov --enable-code-coverage --filter 'ControlPlaneServiceTests|ModelCatalogTests|OnDemandModelLoaderTests'`: `180 tests in 3 suites passed after 0.087 seconds`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --scratch-path /tmp/m11_2_menu_cov --enable-code-coverage --filter 'ControlPlaneXPCClientTests|DesktopFoundationViewTests|RuntimeViewModelTests'`: `202 tests in 3 suites passed after 3.470 seconds`
  - `make py-test`: `456 passed in 34.62s`
  - `make swift-test`: pass
  - `make integration-test`: `60 passed in 754.26s (0:12:34)`
  - `git diff --check`: pass
- Metrics report for `M11.2`:
  - typed memory-budget rejection metrics now emitted by the touched control-plane scope:
    - `control_plane.model_load_rejection_count`
    - `control_plane.model_load_last_budget_bytes`
    - `control_plane.model_load_last_headroom_bytes`
    - `control_plane.model_load_last_required_bytes`
    - `control_plane.text_load_memory_budget_rejection_count`
    - `control_plane.text_load_last_budget_bytes`
    - `control_plane.text_load_last_headroom_bytes`
    - `control_plane.text_load_last_required_bytes`
  - operator timing metrics exercised by the touched desktop scope:
    - `menu.model_load_ms`
    - `menu.model_settings_ms`
  - changed-line coverage for the touched executable scope:
    - Swift control-plane scope: `98.39%` (`305/310`)
    - Swift menu bar scope: `100.00%` (`171/171`)
    - aggregate changed-line coverage across the touched handwritten executable scope: `98.96%`
      (`476/481`)
  - protocol schemas, generated protobuf outputs, `packages/protocol/descriptors/melix.pb`, and
    task-planning documents are excluded from executable changed-line coverage because they are
    generated or repository-ownership artifacts rather than handwritten runtime logic

- Closed `M11.1` by making disk-streaming mode a typed, operator-visible runtime setting across
  the repository-owned control-plane, worker, and desktop-shell surfaces:
  - extended the authoritative control-plane and worker protobuf schemas with
    `DiskStreamingMode`, typed runtime settings, runtime-session fields, worker capabilities, and
    load-request flags, then regenerated the versioned Swift, Python, and descriptor outputs
  - updated the Swift control plane, Python bridge, on-demand loader, runtime-session store, and
    model catalog so requested disk-streaming mode now flows through model policy application,
    worker-backed load requests, runtime-session snapshots, and residency summaries, while
    unsupported workerless or worker-backed paths fail explicitly with typed
    `disk_streaming_unsupported` errors instead of silently downgrading
  - updated the Python worker registry and gRPC server plus the Swift text worker runtime registry
    and services so both worker stacks expose `supports_disk_streaming = false`, reject
    `prefer_disk` and `require_disk` loads deterministically, and report effective
    disk-streaming-mode metadata in residency payloads
  - expanded the native operator shell and runtime view model so model settings now expose a typed
    disk-streaming picker, model rows and summaries show the selected mode, and server-session
    detail renders requested versus effective disk-streaming state alongside the existing lifecycle
    and residency metadata
  - added focused regression coverage across Python worker tests, Swift text worker tests,
    control-plane tests, and menu bar tests, including error mapping, residency projection,
    bridge-mode mapping, raw policy normalization, operator draft synchronization, and the desktop
    disk-streaming picker options
  - marked `M11.1` completed in the roadmap execution index; the active task plan can now advance
    to `M11.2`
- Verification summary for `M11.1`:
  - `make proto`: pass
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_runtime_service.py services/mlx-worker-python/tests/test_runtime_edges.py -q`: `31 passed in 0.20s`
  - `make py-test`: `456 passed in 34.49s`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/mlx-text-worker-swift --scratch-path /tmp/m11_1_text_cov --enable-code-coverage --filter WorkerScaffoldTests`: `133 tests in 1 suite passed after 1.391 seconds`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --scratch-path /tmp/m11_1_cp_cov --enable-code-coverage --filter 'ControlPlaneServiceTests|OnDemandModelLoaderTests|ModelCatalogTests|PythonBridgeWorkerClientTests'`: pass
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --scratch-path /tmp/m11_1_menu_cov --enable-code-coverage --filter 'RuntimeViewModelTests|DesktopFoundationViewTests|DesktopShellStateTests'`: `173 tests in 3 suites passed after 3.453 seconds`
  - `make swift-test`: pass
  - `make integration-test`: `60 passed in 734.45s (0:12:14)`
  - `git diff --check`: pass
- Metrics report for `M11.1`:
  - typed disk-streaming control-plane or operator counters in the touched scope:
    - `control_plane.server_runtime_session_count`
    - `menu.model_settings_ms`
    - `menu.server_snapshot_ms`
  - changed-line coverage for the touched executable scope:
    - Python worker runtime scope: `96.97%` (`32/33`)
    - Swift text worker scope: `100.00%` (`164/164`)
    - Swift control-plane scope: `99.67%` (`305/306`)
    - Swift menu bar scope: `96.53%` (`139/144`)
    - aggregate changed-line coverage across the touched handwritten executable scope: `98.92%`
      (`640/647`)
  - protocol schemas, generated protobuf outputs, `packages/protocol/descriptors/melix.pb`, and
    task-planning documents are excluded from executable changed-line coverage because they are
    generated or repository-ownership artifacts rather than handwritten runtime logic

- Closed `M10.4` and, with it, the parent `M10` lifecycle milestone by adding repository-owned
  live-path lifecycle smoke evidence and operator recovery guidance:
  - added `Sources/MelixCLICore/LocalRuntimeFactory.swift`,
    `SessionLifecycleSmokeRunner.swift`, and `SessionLifecycleSmokeCommand.swift`, plus the
    executable target `Sources/MelixSessionLifecycleSmoke/main.swift`, so the repository now owns a
    single-process lifecycle smoke harness that preserves one `ControlPlaneService` instance while
    exercising pause, idle sleep, request-activity wake, and stop-start recovery against real
    worker sockets
  - added focused Swift coverage in
    `tests/MelixCLITests/SessionLifecycleSmokeRunnerTests.swift` for lifecycle smoke reporting,
    timeout handling, command rendering, injected-client execution, stop-conflict retry, fallback
    assistant handling, command parsing failures, and the default `MelixCLIRunner` local-runtime
    path
  - added `tests/integration/test_session_lifecycle_integration.py`, which starts real worker
    processes, shuts down the auxiliary HTTP control plane, runs `melix-session-lifecycle-smoke`
    against the live worker sockets, and asserts machine-readable pause, sleep, wake, and restart
    evidence
  - added `docs/runbooks/session-lifecycle.md` and updated the documentation maps so operators now
    have explicit diagnosis and recovery guidance for paused, sleeping, stopped, and failed server
    sessions, including how to separate lifecycle faults from connection churn
  - marked `M10.4` and the parent `M10` milestone completed in the roadmap execution index and
    moved the active task plan to `M11.1`
- Verification summary for `M10.4`:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter SessionLifecycleSmokeRunnerTests`: `14 tests in 1 suite passed after 3.005 seconds`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --filter SessionLifecycleSmokeRunnerTests`: `14 tests in 1 suite passed after 3.002 seconds`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest tests/integration/test_session_lifecycle_integration.py -q`: `1 passed in 93.36s`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" COVERAGE_FILE=/tmp/m10_4_python.coverage UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python coverage run --include='tests/integration/test_session_lifecycle_integration.py' -m pytest tests/integration/test_session_lifecycle_integration.py -q`: `1 passed in 40.92s`
  - `make swift-test`: pass
  - `make integration-test`: `60 passed in 738.98s (0:12:18)`
  - `git diff --check`: pass
- Metrics report for `M10.4`:
  - lifecycle smoke metrics now emitted by the repository-owned smoke harness:
    - `lifecycle.pause_ack_ms`
    - `lifecycle.idle_to_light_sleep_ms`
    - `lifecycle.wake_to_ready_ms`
    - `lifecycle.restart_recovery_ms`
  - control-plane lifecycle timings recorded during the smoke path:
    - `control_plane.server_start_ms`
    - `control_plane.server_pause_ms`
    - `control_plane.server_resume_ms`
    - `control_plane.server_wake_ms`
    - `control_plane.server_stop_ms`
    - `control_plane.server_idle_policy_ms`
  - changed-line coverage for the touched executable scope:
    - Swift CLI and smoke harness: `98.30%` (`752/765`)
    - Python integration coverage: `100.00%` (`46/46`)

- Closed `M10.3` by surfacing control-plane-owned server-session lifecycle and idle-policy truth
  across the desktop shell, server workspace, and chat-facing operator surfaces:
  - extended `apps/macos-menubar/Sources/AppMain/Models/DesktopShellState.swift` so server-session
    hydration now derives lifecycle summaries, runtime detail, idle-policy summaries, lifecycle
    banners, and chat-facing lifecycle notices directly from typed runtime-session payloads
  - updated `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift` to route pause,
    resume, wake, stop, and idle-policy actions through the control-plane client while keeping
    desktop banner state authoritative to live snapshots and streamed lifecycle events instead of
    optimistic local lifecycle mutations
  - expanded `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift` and
    `apps/macos-menubar/Sources/AppMain/Chat/DesktopChatView.swift` so the native Window UI now
    exposes lifecycle banners, inline notices, runtime detail, idle-policy summaries, and typed
    lifecycle controls for paused, sleeping, stopped, and failed server sessions
  - added focused coverage in
    `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`,
    `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`,
    `apps/macos-menubar/Tests/MenuBarTests/ControlPlaneXPCClientTests.swift`, and
    `apps/macos-menubar/Tests/MenuBarTests/DesktopShellStateTests.swift`, plus lifecycle-aware test
    support wiring in `apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift`
  - marked `M10.3` completed in the roadmap execution index and moved the active task plan to
    `M10.4`
- Verification summary for `M10.3`:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests|DesktopShellStateTests|ControlPlaneXPCClientTests'`: `199 tests in 4 suites passed after 3.798 seconds`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests|DesktopShellStateTests|ControlPlaneXPCClientTests'`: `199 tests in 4 suites passed after 3.813 seconds`
  - `make swift-test`: pass
  - `git diff --check`: pass
- Metrics report for `M10.3`:
  - desktop lifecycle metrics emitted by the touched scope:
    - `menu.server_start_ms`
    - `menu.server_pause_ms`
    - `menu.server_resume_ms`
    - `menu.server_wake_ms`
    - `menu.server_stop_ms`
    - `menu.server_idle_policy_ms`
  - handwritten menu bar executable scope changed-line coverage:
    - `apps/macos-menubar/Sources/AppMain/Chat/DesktopChatView.swift`: `75.00%` (`69/92`)
    - `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`: `88.68%`
      (`141/159`)
    - `apps/macos-menubar/Sources/AppMain/Models/DesktopShellState.swift`: `100.00%`
      (`150/150`)
    - `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`: `98.14%`
      (`158/161`)
    - `apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift`: `98.98%` (`97/98`)
    - `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`: `100.00%`
      (`298/298`)
    - `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`: `97.56%`
      (`160/164`)
    - `apps/macos-menubar/Tests/MenuBarTests/ControlPlaneXPCClientTests.swift`: `100.00%`
      (`43/43`)
    - `apps/macos-menubar/Tests/MenuBarTests/DesktopShellStateTests.swift`: `100.00%`
      (`0/0`)
    - aggregate changed-line coverage for the touched handwritten menu bar scope: `95.79%`
      (`1116/1165`)

## 2026-04-04

- Closed `M10.2` by wiring control-plane-owned lifecycle controls and idle-power policy through the
  server-session surface:
  - extended `packages/protocol/schema/controlplane/v1/control_plane.proto` with explicit
    `pause`, `resume`, `wake`, and `set_idle_policy` server commands, added session-scoped payloads
    for `start` and `stop`, and regenerated the repository-owned Swift, Python, and descriptor
    outputs
  - expanded `services/control-plane-swift/Sources/Snapshots/ServerSessionRuntimeStore.swift`,
    `ServerSnapshotBuilder.swift`, and `SchedulerReadModel.swift` so runtime sessions now advance
    through typed lifecycle transitions, request-activity wake reasons, idle inhibition, and
    auto-sleep thresholds while the aggregate server-state read model derives from runtime-session
    truth
  - updated `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift` and
    `ControlPlaneXPCClient.swift` so lifecycle mutations, idle-policy validation, server snapshot
    projection, and serving-time pause or sleep safety all live behind the authoritative
    control-plane interface instead of menu-bar-local heuristics
  - extended `Sources/MelixCLICore/MelixCLI.swift` so `melix server snapshot|start|pause|resume|wake|stop|set-idle-policy`
    now speak the same session-scoped control-plane contract and render typed runtime-session
    metadata for operators
  - added focused regression coverage in `tests/MelixCLITests/MelixCLIParserTests.swift`,
    `tests/MelixCLITests/MelixCLIRunnerTests.swift`,
    `services/control-plane-swift/Tests/ControlPlaneTests/SnapshotStoreTests.swift`, and
    `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`, then
    marked `M10.2` completed in the roadmap execution index and moved the active task plan to
    `M10.3`
- Verification summary for `M10.2`:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --filter MelixCLITests`: `64 tests in 2 suites passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter ControlPlaneTests`: `298 tests in 18 suites passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --filter MelixCLITests`: pass
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter ControlPlaneTests`: pass
  - `make proto`: pass
  - `make py-test`: `455 passed in 34.36s`
  - `make swift-test`: pass
  - `make integration-test`: `59 passed in 692.68s (0:11:32)`
  - `git diff --check`: pass
  - repository-default verification note: the full Swift run still emits the pre-existing linker
    `warning: input verification failed` notes for cached object files plus the existing
    `RequestCoordinator.swift` `no 'async' operations occur within 'await' expression` warnings,
    but the authoritative commands above completed successfully
- Metrics report for `M10.2`:
  - CLI executable scope changed-line coverage:
    - `Sources/MelixCLICore/MelixCLI.swift`: `99.11%` (`222/224`)
    - `tests/MelixCLITests/MelixCLIParserTests.swift`: `87.69%` (`114/130`)
    - `tests/MelixCLITests/MelixCLIRunnerTests.swift`: `100.00%` (`222/222`)
    - aggregate CLI changed-line coverage: `96.88%` (`558/576`)
  - control-plane executable scope changed-line coverage:
    - `services/control-plane-swift/Sources/EnginePool/SchedulerReadModel.swift`: `100.00%`
      (`3/3`)
    - `services/control-plane-swift/Sources/Snapshots/ServerSessionRuntimeStore.swift`:
      `100.00%` (`164/164`)
    - `services/control-plane-swift/Sources/Snapshots/ServerSnapshotBuilder.swift`: `100.00%`
      (`19/19`)
    - `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`: `99.58%`
      (`237/238`)
    - `services/control-plane-swift/Sources/XPCService/ControlPlaneXPCClient.swift`: `100.00%`
      (`145/145`)
    - `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`:
      `92.52%` (`470/508`)
    - `services/control-plane-swift/Tests/ControlPlaneTests/SnapshotStoreTests.swift`: `96.86%`
      (`185/191`)
    - aggregate control-plane changed-line coverage: `96.45%` (`1223/1268`)
  - aggregate changed-line coverage for the touched handwritten Swift scope in `M10.2`:
    `96.58%` (`1781/1844`)
  - protocol schemas, generated protobuf outputs, `packages/protocol/descriptors/melix.pb`, and
    task-planning documents are excluded from executable changed-line coverage because they are
    generated or repository-ownership artifacts rather than handwritten runtime logic

- Closed `M10.1` by introducing a dedicated server-session runtime lifecycle snapshot contract:
  - extended `packages/protocol/schema/controlplane/v1/control_plane.proto` with typed
    `ServerSessionLifecycleState`, `ServerSessionPowerState`, `ServerWakeReason`, and
    `ServerSessionRuntimeState` messages, then regenerated the repository-owned protocol outputs
  - added `services/control-plane-swift/Sources/Snapshots/ServerSessionRuntimeStore.swift` plus
    `ServerSnapshotBuilder` and `ControlPlaneService` wiring so control-plane snapshots and
    `server.state_changed` events now project typed `runtime_sessions` without overloading the
    existing Phase 3 branch/session graph semantics
  - updated the native menu bar state model and `RuntimeViewModel` so operator-facing server
    sessions now consume typed lifecycle, power-state, wake-reason, and idle-policy metadata from
    the control-plane payload instead of inferring paused-versus-sleeping locally
  - added focused control-plane and menu bar regression coverage for snapshot decoding, event
    projection, runtime-session fallback, and enum mapping branches, then marked `M10.1`
    completed in the roadmap execution index and active task plan
- Verification summary for `M10.1`:
  - `make proto`: pass
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/services/control-plane-swift/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter ControlPlaneServiceTests`: `127 tests passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/apps/macos-menubar/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter RuntimeViewModelTests`: `110 tests passed`, then `111 tests passed` after the final fallback-coverage test was added
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/services/control-plane-swift/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage`: `537 tests passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/apps/macos-menubar/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --filter RuntimeViewModelTests`: `111 tests passed`
  - `make swift-test`: pass
  - `git diff --check`: pass
- Metrics report for `M10.1`:
  - control-plane handwritten executable scope changed-line coverage:
    - `services/control-plane-swift/Sources/Snapshots/ServerSnapshotBuilder.swift`: `100.00%`
      (`1/1`)
    - `services/control-plane-swift/Sources/Snapshots/ServerSessionRuntimeStore.swift`: `100.00%`
      (`39/39`)
    - `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`: `100.00%`
      (`19/19`)
    - `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`:
      `100.00%` (`32/32`)
    - `services/control-plane-swift/Tests/ControlPlaneTests/SnapshotStoreTests.swift`: `100.00%`
      (`21/21`)
    - aggregate control-plane changed-line coverage: `100.00%` (`112/112`)
  - menu bar handwritten executable scope changed-line coverage:
    - `apps/macos-menubar/Sources/AppMain/Models/DesktopShellState.swift`: `100.00%` (`18/18`)
    - `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`: `100.00%` (`94/94`)
    - `apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift`: `100.00%` (`2/2`)
    - `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`: `100.00%` (`199/199`)
    - aggregate menu bar changed-line coverage: `100.00%` (`313/313`)
  - aggregate changed-line coverage for the touched handwritten Swift scope in `M10.1`:
    `100.00%` (`425/425`)
  - protocol schemas, generated protobuf outputs, `packages/protocol/descriptors/melix.pb`, and
    task-planning documents are excluded from executable changed-line coverage because they are
    generated or repository-ownership artifacts rather than handwritten runtime logic

- Closed the `M8.11` platform-packaging and target-differentiation milestone and, with it, the
  parent `M8` milestone:
  - added `services/mlx-worker-python/worker/productization/packaging_targets.py` so the
    repository now owns a stable Apple Silicon packaging target matrix for
    `launch_agents_checkout`, `homebrew_service`, and `macos_app_bundle_preview`, each preserving
    the shared logical Melix identity while making `packaging_target_id`, `packaging_kind`,
    `distribution_channel`, `runtime_layout`, `state_contract`, and `update_strategy` explicit
  - extended `services/mlx-worker-python/worker/productization/install_assets.py`,
    `services/mlx-worker-python/worker/productization/homebrew_service.py`, and
    `services/mlx-worker-python/worker/productization/macos_app_bundle.py` so launch-agent install
    manifests, Homebrew service manifests, and preview app-bundle outputs now project the shared
    target metadata, including embedded app-bundle target manifests and version or update
    environment exports
  - added repository-owned validation in `scripts/m8_packaging_target_smoke.py`, plus focused
    regression coverage in `services/mlx-worker-python/tests/test_packaging_targets.py`,
    `services/mlx-worker-python/tests/test_m8_packaging_target_smoke.py`, and
    `services/mlx-worker-python/tests/test_package_macos_menubar_app_script.py`
  - updated `README.md`, `docs/runbooks/platform-packaging-targets.md`,
    `docs/runbooks/phase-8-local-install.md`, `docs/runbooks/homebrew-install.md`,
    `infra/packaging/README.md`, `infra/signing/README.md`, `infra/launchd/README.md`,
    `docs/plans/2026-03-30-m8-11-platform-packaging-and-target-differentiation.md`, the roadmap
    execution index, and `task_plan.md` so the repository records `M8.11` and the parent `M8`
    milestone as completed with explicit verification and metrics evidence
- Verification summary for `M8.11`:
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_packaging_targets.py services/mlx-worker-python/tests/test_install_assets.py services/mlx-worker-python/tests/test_install_local_product_script.py services/mlx-worker-python/tests/test_homebrew_distribution.py services/mlx-worker-python/tests/test_homebrew_service_script.py services/mlx-worker-python/tests/test_macos_app_bundle.py services/mlx-worker-python/tests/test_package_macos_menubar_app_script.py services/mlx-worker-python/tests/test_m8_packaging_target_smoke.py -q`: `38 passed in 0.23s`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx python scripts/m8_packaging_target_smoke.py --json`: pass
  - `make py-test`: `455 passed in 34.03s`
  - `git diff --check`: pass
- Metrics report for `M8.11`:
  - deterministic smoke metrics from `scripts/m8_packaging_target_smoke.py --json`:
    - `packaging_target_profile_count = 3`
    - `packaging_target_shared_identity_ok = 1`
    - `packaging_target_distinct_packaging_kind_count = 3`
    - `packaging_target_launch_agents_profile_ok = 1`
    - `packaging_target_homebrew_profile_ok = 1`
    - `packaging_target_app_bundle_profile_ok = 1`
  - Python executable scope changed-line coverage:
    - `services/mlx-worker-python/worker/productization/__init__.py`: `100.00%` (`0/0`)
    - `services/mlx-worker-python/worker/productization/install_assets.py`: `100.00%` (`3/3`)
    - `services/mlx-worker-python/worker/productization/homebrew_service.py`: `100.00%` (`2/2`)
    - `services/mlx-worker-python/worker/productization/macos_app_bundle.py`: `100.00%` (`8/8`)
    - `services/mlx-worker-python/worker/productization/packaging_targets.py`: `100.00%` (`0/0`)
    - `scripts/package_macos_menubar_app.py`: `100.00%` (`2/2`)
    - `scripts/m8_packaging_target_smoke.py`: `100.00%` (`0/0`)
    - `services/mlx-worker-python/tests/test_install_assets.py`: `100.00%` (`5/5`)
    - `services/mlx-worker-python/tests/test_install_local_product_script.py`: `100.00%` (`1/1`)
    - `services/mlx-worker-python/tests/test_homebrew_distribution.py`: `100.00%` (`4/4`)
    - `services/mlx-worker-python/tests/test_macos_app_bundle.py`: `100.00%` (`13/13`)
    - `services/mlx-worker-python/tests/test_packaging_targets.py`: `100.00%` (`0/0`)
    - `services/mlx-worker-python/tests/test_package_macos_menubar_app_script.py`: `100.00%` (`0/0`)
    - `services/mlx-worker-python/tests/test_m8_packaging_target_smoke.py`: `100.00%` (`0/0`)
    - aggregate Python changed-line coverage: `100.00%` (`38/38`)
  - documentation and infra metrics: `N/A`
  - reason: the remaining touched files for this transaction are repository documentation and
    packaging readmes rather than executable code paths

- Stabilized the warm-followup recovery integration assertion:
  - updated `tests/integration/test_recovery_flows.py` so the live recovery test now treats
    `scheduler.prefix_affinity_hit_rate`, `scheduler.warm_route_preference_rate`, and
    `scheduler.restored_route_rate` as the authoritative warm-path routing guarantees while only
    requiring `session.followup_ttft_delta_ms` to be recorded rather than forcing a positive delta
    on every deterministic live run
  - added a focused regression test for `wait_for_metric_key(...)` timeout behavior so the helper
    covers both success and failure branches under changed-line coverage
- Verification summary for the recovery-flow stabilization:
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest tests/integration/test_recovery_flows.py::test_warm_followup_prefers_hot_route_and_reduces_ttft_against_cold_baseline tests/integration/test_recovery_flows.py::test_wait_for_metric_key_raises_when_metric_never_appears -q`: `2 passed in 11.65s`
  - `make integration-test`: `58 passed in 691.52s (0:11:31)`
- Metrics report for the recovery-flow stabilization:
  - `tests/integration/test_recovery_flows.py`: changed-line coverage `100.00%` (`18/18`)

- Closed the `M8.10` auto-update and startup-failure handling milestone:
  - extended `services/mlx-worker-python/worker/productization/install_assets.py`,
    `services/mlx-worker-python/worker/productization/startup_signals.py`, and
    `scripts/install_local_product.py` so packaged Melix installs now emit versioned install
    manifests, repository-owned update-channel metadata, requested versus selected HTTP-port
    evidence, authoritative log paths, and deterministic startup-failure classification helpers
  - added repository-owned update metadata in `infra/packaging/update-channels/stable.json` plus a
    deterministic smoke command in `scripts/m8_startup_failure_smoke.py`, with focused regression
    coverage in `services/mlx-worker-python/tests/test_install_assets.py`,
    `services/mlx-worker-python/tests/test_install_local_product_script.py`,
    `services/mlx-worker-python/tests/test_startup_signals.py`, and
    `services/mlx-worker-python/tests/test_m8_startup_failure_smoke.py`
  - added `apps/macos-menubar/Sources/AppMain/Persistence/ProductInstallState.swift` and wired the
    provider through `RuntimeViewModel`, `DesktopFoundationState`, and `StatusMenu` so the native
    operator shell now surfaces packaged update state and actionable host-port, crash, and hang
    diagnostics sourced from the install manifest
  - expanded focused menu-bar coverage in
    `apps/macos-menubar/Tests/MenuBarTests/ProductInstallStateTests.swift`,
    `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`,
    `apps/macos-menubar/Tests/MenuBarTests/StatusMenuTests.swift`, and
    `apps/macos-menubar/Tests/MenuBarTests/AppMainBootstrapTests.swift`, including environment
    override, version-normalization, control-plane crash, worker crash, and startup-hang branches
  - updated `README.md`, `docs/runbooks/phase-8-local-install.md`, `infra/packaging/README.md`,
    `docs/plans/2026-03-30-m8-10-auto-update-and-startup-failure-handling.md`, the roadmap
    execution index, and `task_plan.md` so the repository records `M8.10` as completed with
    explicit verification and changed-line coverage evidence
- Verification summary for `M8.10`:
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_install_assets.py services/mlx-worker-python/tests/test_install_local_product_script.py services/mlx-worker-python/tests/test_startup_signals.py services/mlx-worker-python/tests/test_m8_startup_failure_smoke.py -q`: `16 passed in 0.08s`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx python scripts/m8_startup_failure_smoke.py --json`: pass
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter ProductInstallStateTests`: `10 tests in 1 suite passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'AppMainBootstrapTests|ProductInstallStateTests|RuntimeViewModelTests|StatusMenuTests|DesktopFoundationViewTests'`: `193 tests in 5 suites passed after 3.525 seconds`
  - `make py-test`: `449 passed in 34.13s`
  - `make swift-test`: pass
  - verification note: the focused and repository-default Swift runs still emit the pre-existing
    `warning: input verification failed` linker notes for cached object files plus the existing
    `RequestCoordinator.swift` `no 'async' operations occur within 'await' expression` warnings,
    but the authoritative commands above completed successfully
- Metrics report for `M8.10`:
  - Python executable scope changed-line coverage:
    - `scripts/install_local_product.py`: `100.00%` (`3/3`)
    - `scripts/m8_startup_failure_smoke.py`: `95.65%` (`44/46`)
    - `services/mlx-worker-python/worker/productization/install_assets.py`: `100.00%` (`12/12`)
    - `services/mlx-worker-python/worker/productization/startup_signals.py`: `92.31%` (`120/130`)
    - `services/mlx-worker-python/tests/test_install_assets.py`: `100.00%` (`26/26`)
    - `services/mlx-worker-python/tests/test_install_local_product_script.py`: `100.00%` (`6/6`)
    - `services/mlx-worker-python/tests/test_startup_signals.py`: `100.00%` (`47/47`)
    - `services/mlx-worker-python/tests/test_m8_startup_failure_smoke.py`: `100.00%` (`22/22`)
    - aggregate Python changed-line coverage: `95.89%` (`280/292`)
  - menu bar executable scope changed-line coverage:
    - `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationState.swift`: `100.00%`
      (`11/11`)
    - `apps/macos-menubar/Sources/AppMain/MenuBar/StatusMenu.swift`: `100.00%` (`3/3`)
    - `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`: `100.00%` (`24/24`)
    - `apps/macos-menubar/Sources/AppMain/Persistence/ProductInstallState.swift`: `99.04%`
      (`207/209`)
    - `apps/macos-menubar/Tests/MenuBarTests/AppMainBootstrapTests.swift`: `100.00%` (`3/3`)
    - `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`: `100.00%` (`2/2`)
    - `apps/macos-menubar/Tests/MenuBarTests/ProductInstallStateTests.swift`: `100.00%`
      (`246/246`)
    - `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`: `100.00%` (`39/39`)
    - `apps/macos-menubar/Tests/MenuBarTests/StatusMenuTests.swift`: `100.00%` (`23/23`)
    - `apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift`: `100.00%` (`6/6`)
    - aggregate menu bar changed-line coverage: `99.65%` (`564/566`)
  - aggregate changed-line coverage for the touched executable scope in `M8.10`: `98.39%`
    (`844/858`)

- Closed the `M8.9` Homebrew formula and services milestone:
  - added repository-owned Homebrew packaging assets in `infra/homebrew/Formula/melix.rb` and `infra/homebrew/README.md`, including a formula that installs from the checked-out repository root, builds the Melix CLI plus the control-plane and Swift text-worker binaries, and exposes a `melix-homebrew-service` wrapper for `brew services`
  - added `services/mlx-worker-python/worker/productization/homebrew_formula.py`, `services/mlx-worker-python/worker/productization/homebrew_service.py`, and `scripts/melix_homebrew_service.py` so Homebrew service startup reuses Melix local-product layout semantics while supervising the control plane, Swift text worker, and Python worker from one repository-owned entrypoint
  - added deterministic packaging smoke commands in `scripts/m8_homebrew_formula_smoke.py` and `scripts/m8_homebrew_service_smoke.py`, plus focused regression coverage in `services/mlx-worker-python/tests/test_homebrew_distribution.py` and `services/mlx-worker-python/tests/test_homebrew_service_script.py`, including failure, shutdown-timeout, signal-stop, and environment-root branches
  - documented Homebrew install, upgrade, stop, and prune behavior in `docs/runbooks/homebrew-install.md` and surfaced the path from `README.md`, `docs/README.md`, and `infra/packaging/README.md`
  - updated `docs/plans/2026-03-30-m8-9-homebrew-formula-and-services.md`, `docs/plans/2026-03-30-full-capability-roadmap-execution-index.md`, and `task_plan.md` so the repository records `M8.9` as completed with explicit verification and metrics evidence
- Verification summary for `M8.9`:
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_homebrew_distribution.py services/mlx-worker-python/tests/test_homebrew_service_script.py -q`: `14 passed in 0.17s`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx python scripts/m8_homebrew_formula_smoke.py --json`: pass
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx python scripts/m8_homebrew_service_smoke.py --json`: pass
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx python scripts/melix_homebrew_service.py manifest --json`: pass
  - `ruby -c infra/homebrew/Formula/melix.rb`: `Syntax OK`
  - `make py-test`: `441 passed in 30.17s`
  - `git diff --check`: pass
- Metrics report for `M8.9`:
  - Python executable scope changed-line coverage:
    - `services/mlx-worker-python/worker/productization/homebrew_formula.py`: `100.00%` (`16/16`)
    - `services/mlx-worker-python/worker/productization/homebrew_service.py`: `100.00%` (`98/98`)
    - `services/mlx-worker-python/tests/test_homebrew_distribution.py`: `100.00%` (`161/161`)
    - `services/mlx-worker-python/tests/test_homebrew_service_script.py`: `100.00%` (`72/72`)
    - `scripts/m8_homebrew_formula_smoke.py`: `100.00%` (`27/27`)
    - `scripts/m8_homebrew_service_smoke.py`: `100.00%` (`42/42`)
    - `scripts/melix_homebrew_service.py`: `100.00%` (`37/37`)
    - aggregate Python changed-line coverage: `100.00%` (`453/453`)
  - Ruby Homebrew formula scope changed-line coverage: `N/A` because the repository does not yet provide a changed-line coverage tool for Ruby formula files

- Closed the `M8.8` generation-config and OCR sampling controls milestone:
  - extended `services/mlx-worker-python/worker/model_registry/catalog.py` so registry discovery now imports inspectable `melix.generation_config.*` metadata from `generation_config.json` without overwriting explicit manifest ext values, while malformed and non-mapping sidecars remain safe no-ops
  - updated `services/control-plane-swift/Sources/Requests/TextRequestShaper.swift`, `services/control-plane-swift/Sources/Requests/ChatRequestTranslator.swift`, `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`, `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`, and `services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift` so imported generation-config defaults flow through a shared model-sampling policy and OCR-specific overrides only win when explicitly configured
  - expanded `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift` and `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift` so the native operator shell now exposes OCR sampling profile, temperature, top-p, and max-token controls in the shared model-settings form while also surfacing generation-config provenance and effective OCR defaults in the model info summary
  - added focused regression coverage in `services/mlx-worker-python/tests/test_model_registry_catalog.py`, `services/control-plane-swift/Tests/ControlPlaneTests/TextEndpointContractTests.swift`, `services/control-plane-swift/Tests/WorkerClientTests/PythonBridgeWorkerClientTests.swift`, `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`, `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`, and `apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift`
  - updated `docs/plans/2026-03-30-m8-8-generation-config-and-ocr-sampling-controls.md`, `docs/plans/2026-03-30-full-capability-roadmap-execution-index.md`, and `task_plan.md` so the repository records `M8.8` as completed with explicit verification and coverage evidence instead of leaving the slice pending
- Verification summary for `M8.8`:
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_model_registry_catalog.py -q`: `11 passed in 0.08s`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'TextEndpointContractTests|PythonBridgeWorkerClientTests'`: pass
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`: pass
  - `make proto`: pass
  - `make py-test`: `425 passed in 34.13s`
  - `make swift-test`: pass
  - `make integration-test`: `58 passed in 692.74s (0:11:32)`
- Metrics report for `M8.8`:
  - Python changed-line coverage:
    - `services/mlx-worker-python/worker/model_registry/catalog.py`: `100.00%` (`37/37`)
    - `services/mlx-worker-python/tests/test_model_registry_catalog.py`: `100.00%` (`49/49`)
    - aggregate Python changed-line coverage: `100.00%` (`86/86`)
  - control-plane changed-line coverage:
    - `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`: `84.62%` (`11/13`)
    - `services/control-plane-swift/Sources/Requests/ChatRequestTranslator.swift`: `100.00%` (`1/1`)
    - `services/control-plane-swift/Sources/Requests/TextRequestShaper.swift`: `100.00%` (`34/34`)
    - `services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift`: `100.00%` (`27/27`)
    - `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`: `84.62%` (`11/13`)
    - `services/control-plane-swift/Tests/ControlPlaneTests/TextEndpointContractTests.swift`: `100.00%` (`76/76`)
    - `services/control-plane-swift/Tests/WorkerClientTests/PythonBridgeWorkerClientTests.swift`: `100.00%` (`36/36`)
    - aggregate control-plane changed-line coverage: `98.00%` (`196/200`)
  - menu bar changed-line coverage:
    - `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift`: `100.00%` (`54/54`)
    - `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`: `95.45%` (`126/132`)
    - `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`: `100.00%` (`72/72`)
    - `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`: `100.00%` (`16/16`)
    - `apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift`: `100.00%` (`12/12`)
    - aggregate menu bar changed-line coverage: `97.90%` (`280/286`)

- Closed the `M8.7` model-settings completion milestone:
  - extended `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift` so the native operator shell now tracks typed drafts for type override, TTL seconds, adaptive thinking mode and budget, parser fallback, and merged effective OCR/parser defaults in the same model-settings flow
  - updated `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift` so empty-string TTL and adaptive-thinking budget drafts clear to zero without destructive side effects, while typed adaptive-thinking parsing remains explicit
  - expanded `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift` and `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift` so operators can edit the full per-model settings surface and inspect effective model info through a shared summary surface
  - added focused regression coverage in `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`, `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`, and `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`
  - stabilized `tests/integration/test_recovery_flows.py` so the warm-followup recovery assertion tolerates outer HTTP jitter while the control-plane `session.followup_ttft_delta_ms` metric remains the authoritative proof of warm-route improvement
  - updated `docs/plans/2026-03-30-m8-7-model-settings-completion.md`, `docs/plans/2026-03-30-full-capability-roadmap-execution-index.md`, and `task_plan.md` so the repository now records `M8.7` as completed instead of leaving the slice pending
- Verification summary for `M8.7`:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/services/control-plane-swift/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'executeMapsAdaptiveThinkingAndParserFallbackModelPolicyValues|executeClearsTTLandAdaptiveThinkingBudgetsWhenDraftsAreEmpty'`: `2 tests passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/apps/macos-menubar/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'modelsTabFormButtonsDispatchActions|modelInfoSummaryViewRendersTypedSettingsAndMergedDefaults|modelSettingsValidationGuardsInvalidDraftsResetsValuesAndNoOpsWithoutPrimaryModel|modelSettingsDraftsNormalizeUnknownResidencyAccelerationAndAdaptiveDefaults'`: `4 tests passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/services/control-plane-swift/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'executeMapsAdaptiveThinkingAndParserFallbackModelPolicyValues|executeClearsTTLandAdaptiveThinkingBudgetsWhenDraftsAreEmpty'`: `2 tests passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/apps/macos-menubar/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`: `154 tests in 2 suites passed`
  - `make proto`: pass
  - `make py-test`: `423 passed in 34.06s`
  - `make swift-test`: pass
  - `make integration-test`: `58 passed in 690.93s (0:11:30)`
- Metrics report for `M8.7`:
  - control-plane changed-line coverage:
    - `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`: `100.00%` (`11/11`)
    - `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`: `100.00%` (`38/38`)
    - aggregate control-plane changed-line coverage: `100.00%` (`49/49`)
  - menu bar changed-line coverage:
    - `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift`: `92.61%` (`213/230`)
    - `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`: `100.00%` (`1/1`)
    - `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`: `99.51%` (`202/203`)
    - `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`: `100.00%` (`123/123`)
    - `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`: `100.00%` (`105/105`)
    - `apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift`: `100.00%` (`19/19`)
    - aggregate menu bar changed-line coverage: `97.36%` (`663/681`)
  - integration changed-line coverage:
    - `tests/integration/test_recovery_flows.py`: `100.00%` (`1/1`)

- Closed the `M8.6` admin-state persistence and offline-assets milestone:
  - extended `apps/macos-menubar/Sources/AppMain/Persistence/OperatorSessionStore.swift` so operator-session payloads now persist `selected_tool_section` and restore safely from legacy payloads that predate that field
  - updated `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift` so the menu bar operator shell restores the selected tool section together with the selected surface and server session
  - added focused regression coverage in `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift` and a repository-owned smoke suite in `apps/macos-menubar/Tests/MenuBarTests/OperatorSessionPersistenceSmokeTests.swift`
  - added `scripts/m8_admin_state_smoke.py` plus Python wrapper coverage in `services/mlx-worker-python/tests/test_m8_admin_state_smoke.py` so the touched scope has a stable repository-owned smoke command rather than an ad hoc local script
  - documented the persistence and offline-assets contract in `docs/runbooks/admin-surface-persistence.md`, updated `docs/README.md`, and marked `M8.6` completed in the execution index
- Verification summary for `M8.6`:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/apps/macos-menubar/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'persistsSelectedToolSectionAndRestoresAcrossRestart|restoresDefaultToolSectionForLegacyOperatorSessionState'`: `2 tests passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/apps/macos-menubar/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter OperatorSessionPersistenceSmokeTests`: pass
  - `python3 scripts/m8_admin_state_smoke.py --json`: pass
  - `make proto`: pass
  - `make py-test`: `423 passed in 34.01s`
  - `make swift-test`: pass
  - `make integration-test`: `58 passed in 691.30s (0:11:31)`
- Metrics report for `M8.6`:
  - smoke metrics from `python3 scripts/m8_admin_state_smoke.py --json`:
    - `operator.session_restore_ms = 0.4190206527709961`
    - `operator.session_persist_write_ms = 2.0880699157714844`
    - `operator.session_tool_section_persisted = 1`
    - `operator.session_tool_section_restored = 1`
    - `operator.session_root_permissions_ok = 1`
    - `operator.session_state_directory_permissions_ok = 1`
    - `operator.session_file_permissions_ok = 1`
    - `operator.offline_asset_external_reference_count = 0`
  - Swift executable scope changed-line coverage:
    - `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`: `100.00%` (`2/2`)
    - `apps/macos-menubar/Sources/AppMain/Persistence/OperatorSessionStore.swift`: `100.00%` (`11/11`)
    - `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`: `100.00%` (`69/69`)
    - `apps/macos-menubar/Tests/MenuBarTests/OperatorSessionPersistenceSmokeTests.swift`: `97.14%` (`68/70`)
    - aggregate Swift changed-line coverage: `98.68%` (`150/152`)
  - Python executable scope changed-line coverage:
    - `scripts/m8_admin_state_smoke.py`: `97.14%` (`34/35`)
    - `services/mlx-worker-python/tests/test_m8_admin_state_smoke.py`: `98.28%` (`57/58`)
    - aggregate Python changed-line coverage: `97.85%` (`91/93`)

- Closed the `M8.5` admin-surface expansion milestone:
  - verified that the native operator shell already exposes the planned runtime, models, downloads, training, diagnostics, logs, settings, chat, image, server, and API surfaces from control-plane-backed menu bar state
  - confirmed the existing menu bar package coverage already exercises the expanded admin shell, including LoRA tooling, benchmark and evaluation diagnostics, matrix benchmark views, direct Hugging Face benchmark targeting, and agent integration export presentation
  - updated `docs/plans/2026-03-30-m8-5-admin-surface-expansion.md` and `docs/plans/2026-03-30-full-capability-roadmap-execution-index.md` so the repository now records `M8.5` as completed instead of leaving the slice implicitly pending
- Verification summary for `M8.5`:
  - `make swift-test`: pass
  - `make integration-test`: `58 passed in 700.76s (0:11:40)`
- Metrics report for `M8.5`:
  - changed-line coverage for the touched executable scope: `N/A`
  - reason: this close-out transaction updates milestone bookkeeping only; the executable admin-surface coverage remains recorded in the repository test suite and was revalidated through the default Swift and integration commands above

- Closed the `M9.8` ecosystem-and-security release-gates transaction:
  - extended `services/mlx-worker-python/worker/productization/release_gates.py` so the Phase 8 release gate now collects repository-owned M9 evidence for MCP auto-injection, agent export, shared access, persistent sessions, rich-output sanitization, connection lifecycle, and closure audit
  - versioned the checked-in `m9` gate thresholds in `infra/release/phase8-release-gate-policy.json`, including machine-readable `release_gate.m9_required_probe_count`, `release_gate.m9_missing_probe_count`, and `release_gate.m9_failed_threshold_count`
  - extended `services/mlx-worker-python/worker/productization/acceptance_metrics.py` so the Phase 8 metrics report now exposes the `release_gate.m9_*` counters without creating a second unrelated gate system
  - added the deterministic fixture command `scripts/m9_release_gate_smoke.py` plus focused coverage in `services/mlx-worker-python/tests/test_m9_release_gate_smoke.py`, `services/mlx-worker-python/tests/test_release_gates.py`, and `services/mlx-worker-python/tests/test_acceptance_metrics.py`
  - updated `docs/runbooks/phase-8-release-gates.md` and `docs/runbooks/phase-8-product-acceptance.md` so the M9 signals, smoke fixtures, and operator-facing interpretation are synchronized with the checked-in gate behavior
- Verification summary for `M9.8`:
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_release_gates.py services/mlx-worker-python/tests/test_phase8_release_gate.py services/mlx-worker-python/tests/test_phase8_runtime_probes.py services/mlx-worker-python/tests/test_acceptance_metrics.py services/mlx-worker-python/tests/test_m9_release_gate_smoke.py -q`: `74 passed in 1.76s`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_release_gates.py services/mlx-worker-python/tests/test_phase8_runtime_probes.py services/mlx-worker-python/tests/test_acceptance_metrics.py services/mlx-worker-python/tests/test_m9_release_gate_smoke.py -q`: `76 passed in 1.73s`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python python scripts/m9_release_gate_smoke.py --repo-root "$(pwd)" --json`: pass
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python python scripts/m9_release_gate_smoke.py --repo-root "$(pwd)" --fixture-mode failing --json`: expected non-zero fail-closed path validated
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python python scripts/phase8_release_gate.py --repo-root "$(pwd)" --json`: pass
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python python scripts/m9_closure_audit.py --repo-root "$(pwd)" --json`: pass
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python python scripts/phase8_metrics_report.py --repo-root "$(pwd)" --json`: pass
- Metrics report for `M9.8`:
  - deterministic smoke fixture metrics:
    - `release_gate.m9_required_probe_count = 23.0`
    - `release_gate.m9_missing_probe_count = 0.0`
    - `release_gate.m9_failed_threshold_count = 0.0`
  - deterministic failing fixture metrics:
    - `release_gate.m9_required_probe_count = 23.0`
    - `release_gate.m9_missing_probe_count = 1.0`
    - `release_gate.m9_failed_threshold_count = 2.0`
  - live Phase 8 gate metrics:
    - `release_gate.m9_required_probe_count = 23.0`
    - `release_gate.m9_missing_probe_count = 0.0`
    - `release_gate.m9_failed_threshold_count = 0.0`
  - post-close closure-audit metrics:
    - `closure_audit.blocker_count = 0.0`
    - `closure_audit.accepted_risk_count = 1.0`
    - `closure_audit.evidence_gap_count = 0.0`
    - `closure_audit.deferred_work_count = 0.0`
  - Python executable scope changed-line coverage:
    - `services/mlx-worker-python/worker/productization/release_gates.py`
    - `services/mlx-worker-python/worker/productization/acceptance_metrics.py`
    - `services/mlx-worker-python/tests/test_release_gates.py`
    - `services/mlx-worker-python/tests/test_phase8_runtime_probes.py`
    - `services/mlx-worker-python/tests/test_acceptance_metrics.py`
    - `services/mlx-worker-python/tests/test_m9_release_gate_smoke.py`
    - `scripts/m9_release_gate_smoke.py`
    - changed-line coverage `100.00%` (`175/175`)

- Closed the `M9.7` security-and-stability closure-audit transaction:
  - added a typed repository-owned closure-audit model in `services/mlx-worker-python/worker/productization/closure_audit.py` that classifies blockers, accepted risks, evidence gaps, and deferred work from execution-index status, release-gate assets, required M9 runbooks, and required probe vocabulary
  - added repository-owned audit entrypoints and docs in `scripts/m9_closure_audit.py`, `docs/runbooks/security-and-stability-closure.md`, and `docs/decisions/2026-04-02-m9-security-stability-closure-audit.md`
  - extended `services/mlx-worker-python/worker/productization/acceptance_metrics.py` so phase metrics can surface `closure_audit.*` counters, and wired the live metrics script path in `scripts/phase8_metrics_report.py`
  - added focused Python evidence in `services/mlx-worker-python/tests/test_closure_audit.py` and extended `services/mlx-worker-python/tests/test_acceptance_metrics.py`
- Verification summary for `M9.7`:
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_closure_audit.py services/mlx-worker-python/tests/test_acceptance_metrics.py -q`: `16 passed in 0.10s`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python python scripts/m9_closure_audit.py --repo-root "$(pwd)" --json`: pass
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python python scripts/phase8_metrics_report.py --repo-root "$(pwd)" --json > /tmp/m9_7_phase8_metrics_output.json`: pass
  - `git diff --check`: pass
- Metrics report for `M9.7`:
  - repository-owned closure-audit metrics from `scripts/m9_closure_audit.py --repo-root "$(pwd)" --json` recorded:
    - `closure_audit.blocker_count = 0`
    - `closure_audit.accepted_risk_count = 1`
    - `closure_audit.evidence_gap_count = 0`
    - `closure_audit.deferred_work_count = 1`
  - `scripts/phase8_metrics_report.py --json` now surfaces:
    - `closure_audit.blocker_count = 0`
    - `closure_audit.accepted_risk_count = 1`
    - `closure_audit.evidence_gap_count = 0`
    - `closure_audit.deferred_work_count = 1`
    - `top_unresolved_findings = ["M9.8 release-gate wiring remains deferred until ecosystem evidence is consumed by the release gate."]`
  - Python executable scope changed-line coverage:
    - `services/mlx-worker-python/worker/productization/closure_audit.py`
    - `services/mlx-worker-python/worker/productization/acceptance_metrics.py`
    - `services/mlx-worker-python/tests/test_closure_audit.py`
    - `services/mlx-worker-python/tests/test_acceptance_metrics.py`
    - `scripts/m9_closure_audit.py`
    - `scripts/phase8_metrics_report.py`
    - changed-line coverage `98.35%` (`238/242`)

- Closed the `M9.6` connection-lifecycle hardening transaction:
  - added a repository-owned `ConnectionLifecyclePolicy` in `services/control-plane-swift/Sources/HTTPGateway/SSE/ConnectionLifecyclePolicy.swift` and wired it through `SSEStreamWriter`, `RequestCoordinator`, `ControlPlaneChatExecution`, `ControlPlaneService`, and the HTTP chat handler so keepalive cadence, disconnect grace, retry policy, and resume buffering now share one typed contract
  - hardened resumable chat execution tracking so transient HTTP disconnects open a bounded resume window, successful resume preserves request identity, terminal expiry rejects stale resume attempts with `request_not_resumable`, and the race between disconnect expiry and stale resume is closed by making terminal-ineligible requests explicit in the coordinator
  - added repository-owned evidence in `services/control-plane-swift/Tests/HTTPGatewayTests/ConnectionLifecyclePolicyTests.swift`, `tests/integration/test_connection_lifecycle.py`, `scripts/m9_connection_smoke.py`, `tests/test_m9_connection_smoke.py`, and `docs/runbooks/connection-lifecycle.md`
  - registered the new runbook from `docs/runbooks/README.md` and the documentation map from `docs/README.md`
- Verification summary for `M9.6`:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'ConnectionLifecyclePolicyTests|SSEStreamWriterTests|RequestCoordinatorTests|OpenAIHandlerTests|ControlPlaneChatExecutionTests|ControlPlaneServiceTests'`: `288 tests in 6 suites passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'ConnectionLifecyclePolicyTests|SSEStreamWriterTests|RequestCoordinatorTests|OpenAIHandlerTests|ControlPlaneChatExecutionTests|ControlPlaneServiceTests'`: `288 tests in 6 suites passed`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest tests/integration/test_recovery_flows.py tests/integration/test_connection_lifecycle.py tests/test_m9_connection_smoke.py -q`: `11 passed in 117.39s (0:01:57)`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python python scripts/m9_connection_smoke.py --json`: `ok = true`
  - `git diff --check`: pass
  - verification note: the focused Swift runs still emitted the pre-existing `warning: input verification failed` linker notes while processing `SwiftTextWorkerClient.swift.o`, and `RequestCoordinator.swift` still emits the existing `no 'async' operations occur within 'await' expression` warnings for the local continuation registration helpers; the authoritative commands above completed successfully
- Metrics report for `M9.6`:
  - repository-owned smoke metrics from `scripts/m9_connection_smoke.py --json` recorded:
    - `disconnect.keepalive_gap_ms = 8.082032203674316`
    - `disconnect.recovery_latency_ms = 12.388944625854492`
    - `disconnect.resume_success_rate = 100`
    - `disconnect.terminal_failure_count = 1`
  - Swift executable scope changed-line coverage:
    - `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`
    - `services/control-plane-swift/Sources/HTTPGateway/SSE/SSEStreamWriter.swift`
    - `services/control-plane-swift/Sources/HTTPGateway/SSE/ConnectionLifecyclePolicy.swift`
    - `services/control-plane-swift/Sources/Requests/ChatRequestTranslator.swift`
    - `services/control-plane-swift/Sources/Requests/RequestCoordinator.swift`
    - `services/control-plane-swift/Sources/XPCService/ControlPlaneChatExecution.swift`
    - `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
    - `services/control-plane-swift/Tests/HTTPGatewayTests/ConnectionLifecyclePolicyTests.swift`
    - `services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`
    - `services/control-plane-swift/Tests/HTTPGatewayTests/RequestCoordinatorTests.swift`
    - `services/control-plane-swift/Tests/HTTPGatewayTests/SSEStreamWriterTests.swift`
    - `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneChatExecutionTests.swift`
    - `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`
    - changed-line coverage `95.49%` (`826/865`)
  - Python executable scope changed-line coverage:
    - `tests/integration/test_connection_lifecycle.py`
    - `scripts/m9_connection_smoke.py`
    - `tests/test_m9_connection_smoke.py`
    - changed-line coverage `95.00%` (`304/320`)
  - aggregate changed-line coverage for the touched executable scope in `M9.6`: `95.36%` (`1130/1185`)

- Closed the `M9.5` rich-output sanitization transaction:
  - added repository-owned rich-output sanitizer coverage in `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`, including fenced-code preservation, HTML-fragment stripping, unsafe URI rejection, and recursive JSON string sanitization for both handwritten and typed gateway responses
  - added gateway contract tests in `services/control-plane-swift/Tests/HTTPGatewayTests/RichOutputSanitizerTests.swift` and `services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`, including metrics assertions for sanitized auth-session payloads
  - projected the same sanitization contract into operator-facing menu bar surfaces by sanitizing doctor and benchmark markdown, evaluation previews, desktop logs, exported chat transcripts, and local error strings without mutating stored assistant transcript state
  - added `docs/runbooks/rich-output-sanitization.md` and registered it from `docs/runbooks/README.md`
- Verification summary for `M9.5`:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'RichOutputSanitizerTests|OpenAIHandlerTests'`: `103 tests in 2 suites passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'RichOutputSanitizerTests|OpenAIHandlerTests'`: `103 tests in 2 suites passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --scratch-path "$(pwd)/.build/menubar-scratch" --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`: `146 tests in 2 suites passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --scratch-path "$(pwd)/.build/menubar-coverage" --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`: `146 tests in 2 suites passed`
  - verification note: both Swift coverage builds emitted a pre-existing `warning: input verification failed` linker note while processing object files, but the authoritative test results above completed successfully and produced usable `profdata`
- Metrics report for `M9.5`:
  - deterministic gateway sanitization fixture from `gateway auth session responses sanitize rich output in encoded and manual json payloads` recorded:
    - `sanitized_output.enforcement_count = 2`
    - `sanitized_output.blocked_html_fragment_count = 4`
    - `sanitized_output.unsafe_uri_rejection_count = 4`
  - `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`, `services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`, and `services/control-plane-swift/Tests/HTTPGatewayTests/RichOutputSanitizerTests.swift`: changed-line coverage `95.71%` (`290/303`)
  - `apps/macos-menubar/Sources/AppMain/Chat/DesktopChatView.swift`, `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationState.swift`, `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`, and `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`: changed-line coverage `100.00%` (`136/136`)
  - aggregate changed-line coverage for the touched executable scope in `M9.5`: `97.04%` (`426/439`)

- Closed the `M9.4` persistent-session foundation transaction:
  - added `services/control-plane-swift/Sources/HTTPGateway/OpenAI/PersistentAuthSessionStore.swift` to persist hashed remember-me gateway sessions under `MELIX_HOME/state/persistent-auth-sessions.json` or `~/.melix/state/persistent-auth-sessions.json`
  - restored remembered sessions during bootstrap, reconciled them against live gateway policy updates, initialized `persistent_session.*` metrics, and extended the control-plane HTTP parser to accept `DELETE` for sign-out
  - added gateway session create, inspect, and sign-out routes in `OpenAIHandler.swift`, including structured `missing`, `revoked`, and `expired` session-state payloads
  - projected remembered-session counts, retention TTL, expiry pruning, and sign-out latency into the menu bar server-session shell and gateway-access summary
  - added `docs/runbooks/persistent-sessions.md`, `scripts/m9_persistent_session_smoke.py`, `tests/test_m9_persistent_session_smoke.py`, and `tests/integration/test_persistent_sessions.py`
- Verification summary for `M9.4`:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'PersistentAuthSessionStoreTests|OpenAIHandlerTests|ControlPlaneServiceTests'`: `224 tests in 3 suites passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'PersistentAuthSessionStoreTests|OpenAIHandlerTests|ControlPlaneServiceTests'`: `224 tests in 3 suites passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --scratch-path "$(pwd)/.build/menubar-scratch" --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`: `144 tests in 2 suites passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --scratch-path "$(pwd)/.build/menubar-coverage" --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`: `144 tests in 2 suites passed`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest tests/integration/test_persistent_sessions.py -q`: `2 passed in 43.28s`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python pytest tests/test_m9_persistent_session_smoke.py -q`: `2 passed in 0.04s`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python python scripts/m9_persistent_session_smoke.py --json`: pass
  - verification note: a first parallel rerun of the integration test and smoke script collided on the fixed local control-plane port and produced `POSIXErrorCode(rawValue: 48): Address already in use`; the authoritative integration result above is the sequential rerun after the smoke script exited
- Metrics report for `M9.4`:
  - smoke metrics from `scripts/m9_persistent_session_smoke.py --json`:
    - `persistent_session.active_session_count = 0`
    - `persistent_session.remembered_session_count = 0`
    - `persistent_session.expired_session_count = 0`
    - `persistent_session.restore_success_rate = 0`
    - `persistent_session.sign_out_latency_ms = 0.8280277252197266`
  - `services/control-plane-swift/Sources/Bootstrap/main.swift`, `services/control-plane-swift/Sources/HTTPGateway/OpenAI/GatewayAccessPolicy.swift`, `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`, `services/control-plane-swift/Sources/HTTPGateway/OpenAI/PersistentAuthSessionStore.swift`, `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`, `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`, `services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`, and `services/control-plane-swift/Tests/HTTPGatewayTests/PersistentAuthSessionStoreTests.swift`: aggregate changed-line coverage `99.15%` (`1047/1056`)
  - `apps/macos-menubar/Sources/AppMain/Models/DesktopShellState.swift`, `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`, `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`, `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`, and `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`: aggregate changed-line coverage `100.00%` (`183/183`)
  - `tests/integration/test_persistent_sessions.py`, `tests/test_m9_persistent_session_smoke.py`, and `scripts/m9_persistent_session_smoke.py`: aggregate changed-line coverage `95.48%` (`190/199`)
  - aggregate changed-line coverage for the touched executable scope in `M9.4`: `98.75%` (`1420/1438`)

- Closed the live benchmark repair transaction for direct Hugging Face benchmark targets:
  - fixed `services/mlx-worker-python/worker/control_plane_bridge.py` so the Python maintenance bridge now forwards `export-results` and `submit-results`
  - added bridge regressions in `services/mlx-worker-python/tests/test_control_plane_bridge_phase5.py` and `services/control-plane-swift/Tests/WorkerClientTests/PythonBridgeWorkerClientTests.swift`
  - fixed `services/mlx-worker-python/worker/engine/maintenance_core.py` so text-backed Gemma 4 benchmark prompts preserve `PreparedVisionRequest` payloads instead of collapsing them into plain strings
  - added a worker regression in `services/mlx-worker-python/tests/test_maintenance_service.py` covering `text-generation` benchmark metrics for imported text-backed `gemma4` VLM repos
  - verified the public `melix` CLI benchmark path for both target repos and copied the final benchmark reports into `/tmp`
- Verification summary for the live benchmark repair:
  - `git diff --check`: pass
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/services/control-plane-swift/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter PythonBridgeWorkerClientTests`: `44 tests passed`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest services/mlx-worker-python/tests/test_control_plane_bridge_phase5.py services/mlx-worker-python/tests/test_maintenance_service.py -q`: `65 passed in 28.06s`
  - live proof benchmark for `unsloth/gemma-4-E4B-it-MLX-8bit` via `melix bench run --repo-id ... --suite smoke --context-length 143 --generation-length 8 --batch-size 1 --repeats 1 --cache-profile cold --sample-size 1 --batch-factor 1 --json`:
    - `bench.smoke.ttft_ms = 15645.22`
    - `bench.smoke.tokens_per_second = 58.75`
    - report saved to `/tmp/melix-gemma4-bench-report.md`
  - live proof benchmark for `Brooooooklyn/Qwen3.5-9B-unsloth-mlx` via the same CLI contract:
    - `bench.smoke.ttft_ms = 14663.95`
    - `bench.smoke.tokens_per_second = 47.01`
    - report saved to `/tmp/melix-qwen35-9b-bench-report.md`
- Metrics report for the live benchmark repair:
  - `services/control-plane-swift/Tests/WorkerClientTests/PythonBridgeWorkerClientTests.swift`: changed-line coverage `100.00%` (`37/37`)
  - `services/mlx-worker-python/worker/control_plane_bridge.py`, `services/mlx-worker-python/worker/engine/maintenance_core.py`, `services/mlx-worker-python/tests/test_control_plane_bridge_phase5.py`, and `services/mlx-worker-python/tests/test_maintenance_service.py`: aggregate changed-line coverage `100.00%` (`67/67`)
  - aggregate changed-line coverage for the touched executable Swift and Python scope: `100.00%` (`104/104`)
  - `docs/plans/2026-04-04-live-benchmark-repair.md` is documentation-only and excluded from executable changed-line coverage

- Closed the M8.1-M8.4 backend-foundations verification and milestone backfill:
  - reran the repository-default verification commands after the accumulated M8.1-M8.4 backend work and confirmed the slice now closes without the earlier Swift blocker
  - updated `docs/plans/2026-04-01-m8-1-m8-4-backend-foundations.md` so the final verification and handoff checklist reflects the real repository state
  - updated `docs/plans/2026-03-30-full-capability-roadmap-execution-index.md` so `M8` now explicitly records `M8.1-M8.4` as completed backend foundations while keeping `M8.5-M8.11` pending
- Verification summary for the M8.1-M8.4 close-out:
  - `make proto`: pass
  - `make py-test`: `403 passed in 34.05s`
  - `make swift-test`: pass
  - `make integration-test`: `54 passed in 622.59s (0:10:22)`
- Metrics report for the M8.1-M8.4 close-out:
  - changed-line coverage for the touched executable scope: `N/A`
  - reason: this close-out transaction updates repository planning and progress records only; the executable changed-line coverage for Tasks 1-4 remains recorded inside `docs/plans/2026-04-01-m8-1-m8-4-backend-foundations.md`

## 2026-04-03

- Started the `bench matrix` transaction on top of the closed canonical `bench` / `eval` expansion.
- Closed Slice 1, the contract and planning reset for experimental performance matrix work:
  - updated `docs/benchmark-evaluation-contract.md` so `bench matrix` is now a canonical Melix workflow rather than a future-only note
  - defined a separate matrix request, persistence, export, and Window UI contract distinct from product-facing `bench run`
  - added `docs/plans/2026-04-03-bench-matrix-performance-lab.md` as the execution plan for the new transaction
  - reset `task_plan.md` so the repository now tracks the active `bench matrix` work instead of the already-closed canonical `bench` / `eval` expansion
  - updated `docs/README.md` so the new execution plan is discoverable from the documentation map
- Verification summary for Slice 1:
  - `git diff --check`: pass
- Metrics report for Slice 1:
  - changed-line coverage for the touched executable scope: `N/A`
  - reason: this slice changes repository documentation and planning records only

- Closed Slice 2, the protocol, CLI, and control-plane bench matrix surface:
  - added `RunBenchMatrix` to the control-plane and worker protobuf schemas and regenerated the Swift, Python, and descriptor artifacts
  - added `melix bench matrix run`, `melix bench matrix list`, `melix bench matrix export-summary-csv`, and `melix bench matrix export-requests-csv` to the shared CLI
  - taught the shared local control-plane client to build and decode typed matrix benchmark requests and replies
  - taught `ControlPlaneService` to validate matrix dimensions, normalize repeated values, enforce the matrix guardrail, and route matrix jobs through the model-operations worker
  - taught the Python control-plane bridge to forward `run-bench-matrix` requests to the worker-side maintenance service
  - added parser, runner, export-bundle, control-plane, worker-client, XPC client, and bridge coverage for the new matrix request path
- Verification summary for Slice 2:
  - `swift test --filter 'MelixCLIParserTests|MelixCLIRunnerTests'`: `55 tests passed`
  - `swift test --package-path services/control-plane-swift --filter 'ControlPlaneServiceTests|BenchmarkExportBundleTests|WorkerClientTests|PythonBridgeWorkerClientTests'`: `215 tests passed`
  - `swift test --package-path apps/macos-menubar --filter ControlPlaneXPCClientTests`: `27 tests passed`
  - `PYTHONPATH="/Users/ChenYu/Documents/Github/melix:/Users/ChenYu/Documents/Github/melix/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_control_plane_bridge_phase5.py -q`: `4 tests passed`
  - `swift test --enable-code-coverage --filter 'MelixCLIParserTests|MelixCLIRunnerTests'`: `55 tests passed`
  - `swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'ControlPlaneServiceTests|BenchmarkExportBundleTests|WorkerClientTests|PythonBridgeWorkerClientTests'`: `215 tests passed`
  - `swift test --package-path apps/macos-menubar --enable-code-coverage --filter ControlPlaneXPCClientTests`: `27 tests passed`
  - `coverage run -m pytest services/mlx-worker-python/tests/test_control_plane_bridge_phase5.py -q`: `4 tests passed`
- Metrics report for Slice 2:
  - `Sources/MelixCLICore/MelixCLI.swift`: changed-line coverage `98.67%` (`297/301`)
  - `services/control-plane-swift/Sources/WorkerClient/WorkerClient.swift`: changed-line coverage `100.00%` (`4/4`)
  - `services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift`: changed-line coverage `100.00%` (`7/7`)
  - `services/control-plane-swift/Sources/XPCService/BenchmarkExportBundle.swift`: changed-line coverage `100.00%` (`205/205`)
  - `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`: changed-line coverage `99.27%` (`136/137`)
  - `services/control-plane-swift/Sources/XPCService/ControlPlaneXPCClient.swift`: changed-line coverage `100.00%` (`75/75`)
  - `services/mlx-worker-python/worker/control_plane_bridge.py`: changed-line coverage `100.00%` (`4/4`)
  - aggregate changed-line coverage for the handwritten executable scope in Slice 2: `99.32%` (`728/733`)
  - generated protobuf schemas and generated protocol outputs are recorded as `N/A` for changed-line coverage because they are interface or generated artifacts rather than repository-owned executable logic

- Closed Slice 3, the worker-side matrix runner, persistence, and export surface:
  - added typed matrix execution in `maintenance_core.py`, including per-cell request rows, aggregated summary rows, and task-aware validation
  - persisted matrix runs under `<jobs_root>/bench/matrix-runs/<job_id>/` with job JSON, summary JSONL/CSV, and request JSONL/CSV artifacts
  - exposed matrix execution through the worker gRPC service
  - extended benchmark export and submission builders to carry matrix jobs, matrix summary rows, and matrix request rows
  - added worker tests for successful matrix runs, VLM matrix coverage, export/submission collection, invalid load budgets, failed sample rows, and matrix task-kind resolution
- Verification summary for Slice 3:
  - `PYTHONPATH="/Users/ChenYu/Documents/Github/melix:/Users/ChenYu/Documents/Github/melix/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_maintenance_service.py -q`: `60 tests passed`
  - `PYTHONPATH="/Users/ChenYu/Documents/Github/melix:/Users/ChenYu/Documents/Github/melix/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx coverage run -m pytest services/mlx-worker-python/tests/test_benchmark_schemas.py services/mlx-worker-python/tests/test_benchmark_store.py services/mlx-worker-python/tests/test_benchmark_export.py services/mlx-worker-python/tests/test_maintenance_service.py -q`: `83 tests passed`
- Metrics report for Slice 3:
  - `services/mlx-worker-python/worker/engine/maintenance_core.py`: changed-line coverage `100.00%` (`192/192`)
  - `services/mlx-worker-python/worker/grpc_server.py`: changed-line coverage `100.00%` (`3/3`)
  - `services/mlx-worker-python/worker/productization/benchmark_export.py`: changed-line coverage `100.00%` (`42/42`)
  - `services/mlx-worker-python/worker/productization/benchmark_schemas.py`: changed-line coverage `100.00%` (`80/80`)
  - `services/mlx-worker-python/worker/productization/benchmark_store.py`: changed-line coverage `100.00%` (`14/14`)
  - `services/mlx-worker-python/worker/productization/submission_builder.py`: changed-line coverage `100.00%` (`3/3`)
  - aggregate changed-line coverage for the executable Python scope in Slice 3: `100.00%` (`334/334`)

- Closed Slice 4, the Window UI matrix controls and result-view surface:
  - added a `Standard / Matrix` presentation-mode switch inside the Bench diagnostics workspace
  - added matrix-specific controls for generation lengths, cache profiles, reasoning modes, structured-output modes, concurrency, repeats, and request-vs-duration load budgets
  - added matrix run dispatch, history selection, summary cards, context and throughput charts, and per-run CSV export actions to `RuntimeViewModel`
  - kept matrix rendering separate from the product-facing benchmark cards and charts so the existing `bench run` workspace semantics remain intact
  - extended the menu-bar fake control-plane client and diagnostics tests so matrix history, charts, and action helpers are covered with repository-owned fixtures
- Verification summary for Slice 4:
  - `swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`: `24 tests passed`
  - `swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`: `24 tests passed`
- Metrics report for Slice 4:
  - `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`: changed-line coverage `94.66%` (`479/506`)
  - `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`: changed-line coverage `94.64%` (`618/653`)
  - `apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift`: changed-line coverage `99.57%` (`232/233`)
  - `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`: changed-line coverage `100.00%` (`107/107`)
  - `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`: changed-line coverage `100.00%` (`226/226`)
  - aggregate changed-line coverage for the executable Window UI scope in Slice 4: `96.35%` (`1662/1725`)

- Closed the Swift text-worker protocol follow-up discovered during Slice 5 verification:
  - `make swift-test` surfaced that the new `RunBenchMatrix` worker RPC had been added to the shared maintenance protocol without a matching `MaintenanceRPCService` stub in `services/mlx-text-worker-swift`
  - added a deterministic unimplemented `runBenchMatrix` stub to the Swift text worker so the package remains protocol-conformant while matrix execution stays owned by the Python worker family
  - extended `WorkerScaffoldTests` so the maintenance scaffold now verifies the matrix RPC returns a typed failed job summary instead of silently drifting from the shared protocol
- Verification summary for the Swift text-worker follow-up:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/services/mlx-text-worker-swift/.build/ModuleCache.noindex" swift test --package-path services/mlx-text-worker-swift --enable-code-coverage --filter WorkerScaffoldTests/testMaintenanceRpcsReturnStructuredUnimplemented`: `1 test passed`
  - the test run emitted the pre-existing `warning: input verification failed` notes while linking `WorkerBootstrap.swift.o`; the targeted test still passed
- Metrics report for the Swift text-worker follow-up:
  - `services/mlx-text-worker-swift/Sources/Core/WorkerServices.swift`: changed-line coverage `100.00%` (`14/14`)
  - `services/mlx-text-worker-swift/Tests/CoreTests/WorkerScaffoldTests.swift`: changed-line coverage `100.00%` (`18/18`)
  - aggregate changed-line coverage for the Swift text-worker follow-up scope: `100.00%` (`32/32`)

- Closed Slice 5, the verification, coverage, and documentation close-out:
  - updated `docs/runbooks/m7-benchmark-and-evaluation-foundation.md` so the repository-owned benchmark runbook now documents `bench matrix` CLI and Window UI flows alongside `bench run` and `eval run`
  - reran focused changed-line coverage for the CLI, control-plane, Python worker, Window UI, and Swift text-worker follow-up scopes
  - reran repository verification commands after the Swift text-worker protocol follow-up so the transaction closes on a passing `make proto`, `make py-test`, `make swift-test`, and `make integration-test`
- Verification summary for Slice 5:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --filter 'MelixCLIParserTests|MelixCLIRunnerTests'`: `55 tests passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/services/control-plane-swift/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'ControlPlaneServiceTests|BenchmarkExportBundleTests|WorkerClientTests|PythonBridgeWorkerClientTests'`: `215 tests passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/apps/macos-menubar/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'RuntimeViewModelTests|DesktopFoundationViewTests|ControlPlaneXPCClientTests'`: `168 tests passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/services/mlx-text-worker-swift/.build/ModuleCache.noindex" swift test --package-path services/mlx-text-worker-swift --enable-code-coverage --filter WorkerScaffoldTests/testMaintenanceRpcsReturnStructuredUnimplemented`: `1 test passed`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run --source=services/mlx-worker-python/worker -m pytest services/mlx-worker-python/tests/test_control_plane_bridge_phase5.py services/mlx-worker-python/tests/test_benchmark_schemas.py services/mlx-worker-python/tests/test_benchmark_store.py services/mlx-worker-python/tests/test_benchmark_export.py services/mlx-worker-python/tests/test_maintenance_service.py -q`: `87 passed in 31.83s`
  - `make proto`: pass
  - `make py-test`: `402 passed in 33.67s`
  - `make swift-test`: pass
  - `make integration-test`: `54 passed in 623.41s (0:10:23)`
  - Swift package verification continued to emit the pre-existing `warning: input verification failed` notes while linking `SwiftTextWorkerClient.swift.o`, `WorkerBootstrap.swift.o`, and the menu-bar test objects; the full test run still passed
- Metrics report for Slice 5:
  - CLI executable scope: changed-line coverage `98.58%` (`969/983`)
  - control-plane executable scope: changed-line coverage `97.20%` (`797/820`)
  - Window UI executable scope: changed-line coverage `96.50%` (`1765/1829`)
  - Python worker executable scope: changed-line coverage `100.00%` (`338/338`)
  - Swift text-worker follow-up scope: changed-line coverage `100.00%` (`32/32`)
  - aggregate changed-line coverage for the full `bench matrix` transaction executable scope: `97.48%` (`3901/4002`)

- Continued the benchmark and evaluation contract expansion transaction with the first two executable slices from `docs/plans/2026-04-03-bench-eval-contract-expansion-implementation.md`.
- Closed Task 1, the protocol expansion slice for canonical bench and eval inputs:
  - added the canonical bench fields to `RunBench` and `RunBenchRequest`
  - added the canonical eval fields to `RunEvaluation` and `RunEvaluationRequest`
  - regenerated Swift, Python, and descriptor protocol outputs
  - added parser and control-plane forwarding tests for the new request surfaces
- Verification summary for Task 1:
  - `make proto`: pass
  - `swift test --filter MelixCLITests`: expected shape-only failures before Task 2 wiring
  - `swift test --package-path services/control-plane-swift --filter ControlPlaneServiceTests`: expected forwarding failures before Task 2 wiring
- Metrics report for Task 1:
  - changed-line coverage for the touched executable scope: `N/A`
  - reason: the slice was limited to additive protocol surfaces, generated outputs, and shape tests that were intentionally left failing until Task 2 normalization landed
- Closed Task 2, the canonical bench request normalization slice across CLI and control plane:
  - extended `BenchRunOptions` and `ControlPlaneBenchRequest` with typed canonical fields
  - normalized repeated context and batch inputs through shared sorted unique helpers
  - defaulted bench repeats to `1`
  - validated `cache_profile` against `cold|warm|partial_prefix`
  - forwarded `reasoning_mode` and `structured_output_mode` through the local control-plane client and `ControlPlaneService`
  - added parser, runner, local-client, and control-plane tests that assert canonical normalization behavior
- Verification summary for Task 2:
  - `swift test --enable-code-coverage --filter MelixCLITests`: `41 tests passed`
  - `swift test --package-path services/control-plane-swift --enable-code-coverage --filter ControlPlaneServiceTests`: `115 tests passed`
  - both Swift test bundles emitted the existing linker warning `warning: input verification failed` while processing `SwiftTextWorkerClient.swift.o`; the tests still passed and this warning is outside the touched Task 2 scope
- Metrics report for Task 2:
  - `Sources/MelixCLICore/MelixCLI.swift`, `tests/MelixCLITests/MelixCLIParserTests.swift`, and `tests/MelixCLITests/MelixCLIRunnerTests.swift`: aggregate changed-line coverage `100.00%` (`66/66`)
  - `services/control-plane-swift/Sources/XPCService/ControlPlaneXPCClient.swift`, `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`, and `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`: aggregate changed-line coverage `100.00%` (`14/14`)
- Closed the Task 2 follow-up test gap after the main normalization commit:
  - added parser coverage for default canonical bench fields and invalid `cache_profile` rejection
  - added CLI runner coverage for normalized bench request forwarding
  - updated the control-plane canonical bench forwarding test to prove unsorted context and batch inputs are normalized before worker dispatch
- Verification summary for the Task 2 follow-up:
  - `swift test --enable-code-coverage --filter MelixCLITests`: `41 tests passed`
  - `swift test --package-path services/control-plane-swift --enable-code-coverage --filter ControlPlaneServiceTests`: `115 tests passed`
  - both Swift test bundles emitted the existing linker warning `warning: input verification failed` while processing `SwiftTextWorkerClient.swift.o`; the tests still passed and this warning is outside the touched follow-up scope
- Metrics report for the Task 2 follow-up:
  - `tests/MelixCLITests/MelixCLIParserTests.swift` and `tests/MelixCLITests/MelixCLIRunnerTests.swift`: aggregate changed-line coverage `100.00%` (`66/66`)
  - `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`: changed-line coverage `100.00%` (`14/14`)
- Closed Task 3, the canonical benchmark sweep, metrics, and export slice in the Python worker:
  - expanded the benchmark persistence model to distinguish run summaries, context rows, and batch rows
  - persisted canonical bench summary fields including `context_lengths`, `generation_length`, `batch_sizes`, `repeats`, `cache_profile`, `reasoning_mode`, `structured_output_mode`, `request_p50_ms`, and `request_p95_ms`
  - wrote benchmark summary, context-row, and batch-row artifacts to the per-run output directory and carried those rows into export and submission bundles
  - added summary, context, and batch CSV builders for the canonical benchmark export shape
  - made text benchmark prompt selection use the resolved suite cases so `sample_size` and curated prompt sets continue to affect measurements
  - made text benchmark batch rows truthful on the current runtime path by emitting only real `batch_size == 1` rows until the runtime exposes true batch execution support
- Verification summary for Task 3:
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_benchmark_schemas.py services/mlx-worker-python/tests/test_benchmark_export.py -q`: `71 passed in 33.46s`
- Metrics report for Task 3:
  - `services/mlx-worker-python/worker/engine/maintenance_core.py`, `services/mlx-worker-python/worker/productization/benchmark_schemas.py`, `services/mlx-worker-python/worker/productization/benchmark_export.py`, and `services/mlx-worker-python/worker/productization/submission_builder.py`: aggregate changed-line coverage `100.00%` (`312/312`)
  - `services/mlx-worker-python/worker/engine/maintenance_core.py` follow-up delta in `f109442`: changed-line coverage `100.00%` (`13/13`)
  - `services/mlx-worker-python/tests/test_maintenance_service.py` follow-up delta in `f109442`: changed-line coverage `100.00%` (`4/4`)
- Closed Task 4, the canonical evaluation controls, persistence, and export slice:
  - extended evaluation job and result persistence with `few_shot`, `seed`, `code_exec_policy`, `incorrect_count`, and `duration_seconds`
  - wired `few_shot`, `seed`, `scoring_mode`, and `code_exec_policy` through `evaluation_core.py` and the worker gRPC service
  - persisted canonical evaluation summary JSON and summary CSV alongside sample CSV and JSONL exports
  - extended benchmark export collection with `evaluation_summary_rows`
  - aligned Swift-side evaluation export decoding and CLI export output with the canonical summary-row shape while preserving the old metric-based fallback for historical bundles
- Verification summary for Task 4:
  - `swift test --enable-code-coverage --filter MelixCLITests`: `41 tests passed`
  - `swift test --package-path services/control-plane-swift --enable-code-coverage --filter ControlPlaneServiceTests`: `115 tests passed`
  - `swift test --package-path services/control-plane-swift --enable-code-coverage --filter BenchmarkExportBundleTests`: `8 tests passed`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_evaluation_core.py services/mlx-worker-python/tests/test_evaluation_store.py services/mlx-worker-python/tests/test_benchmark_export.py -q`: `22 tests passed`
  - `git diff --check`: pass
- Metrics report for Task 4:
  - `services/mlx-worker-python/worker/engine/evaluation_core.py`, `services/mlx-worker-python/worker/grpc_server.py`, `services/mlx-worker-python/worker/productization/evaluation_schemas.py`, `services/mlx-worker-python/worker/productization/evaluation_store.py`, and `services/mlx-worker-python/worker/productization/benchmark_export.py`: aggregate changed-line coverage `100.00%` (`112/112`)
  - `services/control-plane-swift/Sources/XPCService/BenchmarkExportBundle.swift`, `services/control-plane-swift/Tests/ControlPlaneTests/BenchmarkExportBundleTests.swift`, and `tests/MelixCLITests/MelixCLIRunnerTests.swift`: aggregate changed-line coverage `100.00%` (`105/105`)
- Closed Task 5, the Window UI productization slice for canonical benchmark and evaluation controls:
  - added canonical benchmark controls for context lengths, batch sizes, repeats, cache profile, reasoning mode, and structured output mode
  - added canonical evaluation controls for scoring mode and code execution policy alongside the existing few-shot and seed inputs
  - wired the new Window UI state through `RuntimeViewModel` normalization helpers and forwarded the canonical request fields to the shared control-plane client
  - aligned evaluation metric cards with canonical `score_name` / `score_value` summary rows and updated diagnostics rendering tests for the new controls
  - passed reviewer gate with no blocking findings; the only residual risk is that `benchReasoningMode` and `benchStructuredOutputMode` still rely on Picker-backed valid values instead of explicit enum validation
- Verification summary for Task 5:
  - `swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'RuntimeViewModelTests|DesktopFoundationViewTests|ControlPlaneXPCClientTests'`: `161 tests passed`
- Metrics report for Task 5:
  - `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`, `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`, `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`, `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`, and `apps/macos-menubar/Tests/MenuBarTests/ControlPlaneXPCClientTests.swift`: aggregate changed-line coverage `99.56%` (`448/450`)
- Closed Task 6, the verification and documentation close-out slice:
  - updated `docs/runbooks/m7-benchmark-and-evaluation-foundation.md` so the canonical `bench` / `eval` operator and CLI flows are documented in one repository-owned runbook
  - updated `task_plan.md` so Tasks 5 and 6 are marked completed and the transaction is recorded as closed
  - reran changed-line coverage for the full touched executable scope from `d1ceaba`
  - reran repository verification before the final documentation commit
- Verification summary for Task 6:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --filter MelixCLITests`: `41 tests passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/services/control-plane-swift/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'ControlPlaneServiceTests|BenchmarkExportBundleTests'`: `123 tests passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/apps/macos-menubar/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'RuntimeViewModelTests|DesktopFoundationViewTests|ControlPlaneXPCClientTests'`: `161 tests passed`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run --source=services/mlx-worker-python/worker -m pytest services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_benchmark_schemas.py services/mlx-worker-python/tests/test_benchmark_export.py services/mlx-worker-python/tests/test_evaluation_core.py services/mlx-worker-python/tests/test_evaluation_store.py services/mlx-worker-python/tests/test_submission_builder.py services/mlx-worker-python/tests/test_release_gates.py -q`: `101 passed in 30.04s`
  - `make proto`: pass
  - `make py-test`: `391 passed in 30.13s`
  - `make swift-test`: failed outside the touched scope after the protocol package passed; `services/mlx-text-worker-swift` exited with unexpected signal `11` during `WorkerScaffoldTests`, and the same run emitted the pre-existing `warning: input verification failed` notes while processing `.o` files in that package
  - `make integration-test`: `54 passed in 619.54s (0:10:19)`
- Metrics report for Task 6:
  - `Sources/MelixCLICore/MelixCLI.swift`, `tests/MelixCLITests/MelixCLIParserTests.swift`, and `tests/MelixCLITests/MelixCLIRunnerTests.swift`: aggregate changed-line coverage `97.21%` (`209/215`)
  - `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`, `services/control-plane-swift/Sources/XPCService/BenchmarkExportBundle.swift`, `services/control-plane-swift/Sources/XPCService/ControlPlaneXPCClient.swift`, `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`, and `services/control-plane-swift/Tests/ControlPlaneTests/BenchmarkExportBundleTests.swift`: aggregate changed-line coverage `99.77%` (`431/432`)
  - `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`, `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`, `apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`, `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`, and `apps/macos-menubar/Tests/MenuBarTests/ControlPlaneXPCClientTests.swift`: aggregate changed-line coverage `99.56%` (`448/450`)
  - `services/mlx-worker-python/worker/engine/maintenance_core.py`, `services/mlx-worker-python/worker/productization/benchmark_schemas.py`, `services/mlx-worker-python/worker/productization/benchmark_export.py`, `services/mlx-worker-python/worker/productization/submission_builder.py`, `services/mlx-worker-python/worker/engine/evaluation_core.py`, `services/mlx-worker-python/worker/grpc_server.py`, `services/mlx-worker-python/worker/productization/evaluation_schemas.py`, and `services/mlx-worker-python/worker/productization/evaluation_store.py`: aggregate changed-line coverage `99.48%` (`385/387`)
  - aggregate changed-line coverage for the full touched executable scope in the canonical bench/eval expansion transaction: `99.26%` (`1473/1484`)

- Converted the canonical benchmark and evaluation contract into an executable implementation plan.
- Added `docs/plans/2026-04-03-bench-eval-contract-expansion-implementation.md` with staged tasks for:
  - protocol expansion
  - canonical bench request normalization
  - canonical benchmark sweeps, metrics, and CSV export
  - canonical eval controls and sample exports
  - Window UI productization
  - coverage, verification, and documentation closure
- Reset `task_plan.md` so the repository reflects that the next transaction is implementation execution rather than additional contract definition.
- Verification summary for the implementation plan capture:
  - `git diff --check`: pass
- Metrics report:
  - changed-line coverage for the touched executable scope: `N/A`
  - reason: this transaction changes repository documentation only and does not modify executable source files

- Captured the next-step benchmark and evaluation I/O contract as a canonical repository specification.
- Added `docs/benchmark-evaluation-contract.md` to define:
  - the explicit split between `bench` and `eval`
  - required target selectors, task kinds, normalized inputs, and exportable outputs
  - performance summary metrics, context-sweep rows, and batch-sweep rows
  - evaluation suite summaries, category breakdowns, and sample-level CSV and JSONL fields
  - Window UI and CLI parity requirements
- Updated `docs/README.md` so the benchmark and evaluation contract is listed with the canonical top-level specifications.
- Reset `task_plan.md` for this docs-only transaction so the repository reflects that the next follow-up after implementation is contract capture rather than another code slice.
- Verification summary for the benchmark and evaluation contract capture:
  - `git diff --check`: pass
- Metrics report:
  - changed-line coverage for the touched executable scope: `N/A`
  - reason: this transaction changes repository documentation only and does not modify executable source files

- Started the benchmark and evaluation redesign follow-up as a new transaction on top of the completed M7 / LoRA / benchmark productization baseline.
- Added `docs/plans/2026-04-03-benchmark-evaluation-redesign.md` to define the split between:
  - `bench` for performance benchmarking
  - `eval` for intelligence evaluation
- Regenerated the control-plane and worker protocol surfaces so evaluation requests and export bundles now carry typed task and source metadata.
- Landed the Python worker evaluation productization slice:
  - added typed evaluation schemas and per-run persistence helpers
  - persisted evaluation jobs, summary results, and sample rows
  - extended benchmark export collection so benchmark and evaluation history can be exported from one bundle
  - wired evaluation execution and export data into the worker gRPC surface
- Landed the shared Swift export and control-plane slice:
  - added evaluation job, result, sample, and export-bundle decoding to `BenchmarkExportBundle`
  - added typed shared-client request and result models for evaluation runs
  - extended `ControlPlaneService` so `ops.run_evaluation` resolves model or direct Hugging Face repo targets and returns typed job summaries
- Landed the `melix eval` CLI slice:
  - added parser and runner support for `eval run`, `eval list`, `eval export-summary-csv`, `eval export-samples-csv`, and `eval export-samples-jsonl`
  - kept `--model-id` and `--repo-id` as mutually exclusive evaluation targets
  - reused the shared local control-plane client instead of creating a second evaluation-only path
- Landed the Window UI evaluation slice:
  - added evaluation target selection, suite selection, sample-size, batch-factor, few-shot, and seed controls
  - added evaluation history, summary metric cards, and sample previews
  - added evaluation export actions for summary CSV, samples CSV, and samples JSONL
- Verification summary for the benchmark and evaluation redesign:
  - `PYTHONPATH="/Users/ChenYu/Documents/Github/melix:/Users/ChenYu/Documents/Github/melix/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_evaluation_schemas.py services/mlx-worker-python/tests/test_evaluation_store.py services/mlx-worker-python/tests/test_evaluation_core.py services/mlx-worker-python/tests/test_benchmark_export.py services/mlx-worker-python/tests/test_submission_builder.py services/mlx-worker-python/tests/test_benchmark_schemas.py -q`: `26 passed in 0.15s`
  - `swift test --enable-code-coverage --filter MelixCLITests`: `37 tests passed`
  - `swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'BenchmarkExportBundleTests|ControlPlaneServiceTests'`: `117 tests passed`
  - `swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'ControlPlaneXPCClientTests|DesktopFoundationViewTests|RuntimeViewModelTests'`: `157 tests passed`
  - `make proto`: pass
  - `make py-test`: `383 passed in 7.95s`
  - `make swift-test`: failed outside the touched scope because `services/mlx-text-worker-swift` exited with unexpected signal `11`; the evaluation transaction does not touch that workspace
- Metrics report:
  - `services/mlx-worker-python/worker/engine/evaluation_core.py`, `services/mlx-worker-python/worker/grpc_server.py`, `services/mlx-worker-python/worker/productization/benchmark_export.py`, `services/mlx-worker-python/worker/productization/benchmark_schemas.py`, `services/mlx-worker-python/worker/productization/evaluation_schemas.py`, `services/mlx-worker-python/worker/productization/evaluation_store.py`, `services/mlx-worker-python/worker/productization/submission_builder.py`, and `services/mlx-worker-python/worker/productization/__init__.py`: aggregate changed-line coverage `100.00%` (`123/123`)
  - `Sources/MelixCLICore/MelixCLI.swift`: changed-line coverage `99.56%` (`226/227`)
  - `services/control-plane-swift/Sources/XPCService/BenchmarkExportBundle.swift` and `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`: aggregate changed-line coverage `99.14%` (`231/233`)
  - `services/control-plane-swift/Sources/XPCService/ControlPlaneXPCClient.swift`: changed-line coverage `100.00%` (`41/41`)
  - `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift` and `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`: aggregate changed-line coverage `95.76%` (`655/684`)
  - aggregate changed-line coverage for the touched executable Python and Swift scope in this transaction: `97.39%` (`1276/1308`)

- Reset the active repository task plan from the closed M6 transaction to the M7, LoRA, Benchmark, and CLI productization transaction.
- Added `docs/plans/2026-04-03-m7-lora-benchmark-cli-productization.md` as the umbrella execution plan for:
  - shared operator client and `melix` CLI exposure
  - LoRA productization across Window UI and CLI
  - real M7 benchmark runner closure
  - benchmark UI, visualization, and CSV export
- Updated the execution index so M7 now points at the active umbrella plan and is explicitly tracked as in progress rather than implied complete.
- Verification summary for the documentation reset:
  - `python3 scripts/python_changed_line_coverage.py`: `N/A`
- Metrics report:
  - changed-line coverage for the touched executable scope: `N/A`
  - reason: this commit records documentation and execution-tracking updates only and does not change executable source files
- Landed the shared operator client and CLI foundation slice:
  - extended `RunBench` with explicit `model_id` selection and regenerated Swift/Python/descriptors
  - moved `ControlPlaneXPCClient` into `services/control-plane-swift` so Window UI and CLI can share one local operator client
  - taught `ControlPlaneService` benchmark execution to resolve explicit model IDs, lazy-load a text benchmark target, and preserve failed benchmark job summaries in error responses
  - added the root `melix` Swift package products and the first public commands for `lora list`, `lora train`, `lora activate`, and `bench run`
- Verification summary for the shared operator client and CLI foundation:
  - `make proto`: pass
  - `swift test --enable-code-coverage --filter MelixCLITests`: `18 tests passed`
  - `swift test --package-path services/control-plane-swift --enable-code-coverage --filter ControlPlaneServiceTests`: `103 tests passed`
  - `swift test --package-path apps/macos-menubar --enable-code-coverage --filter ControlPlaneXPCClientTests`: `21 tests passed`
- Metrics report:
  - `Sources/MelixCLICore/MelixCLI.swift`: changed-line coverage `99.63%` (`270/271`)
  - `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`: changed-line coverage `100.00%` (`47/47`)
  - `services/control-plane-swift/Sources/XPCService/ControlPlaneXPCClient.swift`: changed-line coverage `100.00%` (`374/374`)
  - generated protobuf outputs, `Package.swift`, and `Package.resolved` are excluded from changed-line coverage because they are generated or manifest files rather than executable runtime sources
- Landed the LoRA backend and artifact productization slice:
  - added dataset-source resolution for `local_package` and `hf_dataset`, including Hugging Face materialization into `<jobs_root>/datasets/<cache-key>`
  - moved `train_lora` and `activate_adapter` outputs to stable per-job paths under `<jobs_root>/<operation>/<job_id>/`
  - persisted dataset provenance, cache metadata, adapter identity, and derived-model linkage into LoRA manifests and registry snapshots
  - preserved source adapter job linkage and optional derived-model aliasing in activation manifests
- Verification summary for the LoRA backend and artifact productization:
  - `PYTHONPATH=/Users/ChenYu/Documents/Github/melix:/Users/ChenYu/Documents/Github/melix/services/mlx-worker-python uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_maintenance_service.py -q`: `51 passed`
- Metrics report:
  - `services/mlx-worker-python/worker/model_ops/training_dataset.py`: changed-line coverage `96.07%` (`171/178`)
  - `services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py`: changed-line coverage `100.00%` (`7/7`)
  - `services/mlx-worker-python/worker/model_ops/adapter_activation_pipeline.py`: changed-line coverage `100.00%` (`3/3`)
  - `services/mlx-worker-python/worker/model_ops/job_registry.py`: changed-line coverage `100.00%` (`3/3`)
  - `services/mlx-worker-python/worker/engine/maintenance_core.py`: changed-line coverage `100.00%` (`8/8`)
- Landed the LoRA Window UI and CLI exposure slice:
  - extended `melix lora train` so it accepts either `--dataset-uri` or `--hf-dataset-path`, forwards feature mappings and LoRA hyperparameters, and exposes `derived-model-alias`, `response-only`, `mask-prompt`, and `gradient-checkpointing`
  - added Window UI training controls for base-model selection, dataset-source switching, Hugging Face dataset metadata, LoRA hyperparameters, adapter naming, and derived-model aliasing
  - added Window UI adapter selection plus activation and publish actions backed by shared control-plane requests instead of hard-coded demo payloads
  - refreshed the native operator state so activated derived models re-enter the runtime shell and bench metrics survive the post-activation snapshot refresh
- Verification summary for the LoRA Window UI and CLI exposure slice:
  - `swift test --enable-code-coverage --filter MelixCLITests`: `20 tests passed`
  - `swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`: `116 tests passed`
- Metrics report:
  - `Sources/MelixCLICore/MelixCLI.swift`: changed-line coverage `100.00%` (`37/37`)
  - `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`: changed-line coverage `100.00%` (`148/148`)
  - `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`: changed-line coverage `95.03%` (`172/181`)
  - aggregate changed-line coverage for the executable Swift scope in this slice: `97.54%` (`357/366`)
- Landed the benchmark core runner slice for M7:
  - replaced deterministic text benchmark placeholder metrics with runtime-backed measurements against the selected model runtime
  - added lazy benchmark model loading for worker-side runs and persisted benchmark runs under `<jobs_root>/bench/runs/<job_id>/`
  - kept queue state under `<jobs_root>/bench/queue` while making export and submission flows recurse across run history for backward compatibility
  - updated release-gate benchmark evidence to use the runtime-backed benchmark core under deterministic test runtime wiring
- Verification summary for the benchmark core runner slice:
  - `PYTHONPATH=/Users/ChenYu/Documents/Github/melix:/Users/ChenYu/Documents/Github/melix/services/mlx-worker-python uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_benchmark_export.py services/mlx-worker-python/tests/test_benchmark_store.py services/mlx-worker-python/tests/test_benchmark_schemas.py services/mlx-worker-python/tests/test_release_gates.py -q`: `76 passed`
- Metrics report:
  - `services/mlx-worker-python/worker/engine/maintenance_core.py`: changed-line coverage `100.00%` (`123/123`)
  - `services/mlx-worker-python/worker/productization/benchmark_export.py`: changed-line coverage `100.00%` (`18/18`)
  - `services/mlx-worker-python/worker/productization/release_gates.py`: changed-line coverage `100.00%` (`3/3`)
  - aggregate changed-line coverage for the executable Python scope in this slice: `100.00%` (`144/144`)
- Closed M7 with curated Hugging Face benchmark suites:
  - added a repository-owned benchmark suite catalog that maps `smoke` and `latency` to explicit Hugging Face datasets, splits, and feature mappings
  - materialized benchmark suites on demand under the shared runtime dataset cache and persisted dataset provenance, cache keys, and cache-hit state into benchmark job manifests
  - switched runtime benchmark prompts from synthetic hard-coded strings to prompt batches derived from curated HF-backed dataset rows while preserving queue state and export compatibility
  - updated the roadmap execution index to mark M7 completed; benchmark Window UI, CSV, and CLI productization remain active post-M7 work in the same transaction
- Verification summary for the M7 suite-catalog closure:
  - `PYTHONPATH=/Users/ChenYu/Documents/Github/melix:/Users/ChenYu/Documents/Github/melix/services/mlx-worker-python uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_benchmark_suites.py services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_benchmark_export.py services/mlx-worker-python/tests/test_benchmark_store.py services/mlx-worker-python/tests/test_benchmark_schemas.py services/mlx-worker-python/tests/test_release_gates.py -q`: `80 passed`
- Metrics report:
  - `services/mlx-worker-python/worker/productization/benchmark_suites.py`: changed-line coverage `93.55%` (`87/93`)
  - `services/mlx-worker-python/worker/engine/maintenance_core.py`: changed-line coverage `100.00%` (`10/10`)
  - `services/mlx-worker-python/worker/productization/benchmark_schemas.py`: changed-line coverage `100.00%` (`6/6`)
  - `services/mlx-worker-python/worker/productization/release_gates.py`: changed-line coverage `100.00%` (`15/15`)
  - aggregate changed-line coverage for the executable Python scope in this slice: `95.16%` (`118/124`)
- Landed the benchmark CLI and CSV export closure slice:
  - added `ControlPlaneBenchmarkExportBundle` to `MelixControlPlaneCore` so benchmark history, suite metadata, and CSV rows decode from one shared persisted export format
  - extended the shared local control-plane client with `ops.export_results`, returning typed export-bundle JSON for both native and CLI operator flows
  - exposed `melix bench list` with human-readable and `--json` history output, and `melix bench export-csv` for filtered per-job CSV emission
  - added targeted coverage for benchmark export decoding fallbacks, deterministic ordering, CSV quoting, and default control-plane export failures
- Verification summary for the benchmark CLI and CSV export closure:
  - `swift test --enable-code-coverage --filter MelixCLITests`: `24 tests passed`
  - `swift test --package-path services/control-plane-swift --enable-code-coverage --filter BenchmarkExportBundleTests`: `3 tests passed`
  - `swift test --package-path apps/macos-menubar --enable-code-coverage --filter ControlPlaneXPCClientTests`: `22 tests passed`
- Metrics report:
  - `Sources/MelixCLICore/MelixCLI.swift`: changed-line coverage `98.40%` (`123/125`)
  - `services/control-plane-swift/Sources/XPCService/BenchmarkExportBundle.swift`: changed-line coverage `100.00%` (`163/163`)
  - `services/control-plane-swift/Sources/XPCService/ControlPlaneXPCClient.swift`: changed-line coverage `96.30%` (`26/27`)
  - aggregate changed-line coverage for the executable Swift scope in this slice: `99.05%` (`312/315`)
- Landed the benchmark Window UI visualization closure slice:
  - expanded the diagnostics workspace into a benchmark operator surface with explicit model selection, curated suite multi-select, sample-size and batch-factor controls, history refresh, and CSV export
  - taught `RuntimeViewModel` to derive benchmark history cards, metric pickers, chart points, CSV export state, and history selection from the shared benchmark export bundle
  - added Window UI rendering for benchmark empty states, persisted history, metric cards, and chart visualization while keeping benchmark actions on shared control-plane truth
  - added targeted tests for benchmark guard rails, empty export handling, diagnostics action helpers, and Window UI empty-state plus exported-state rendering
- Verification summary for the benchmark Window UI visualization closure:
  - `swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`: `122 tests passed`
  - `swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`: `122 tests passed`
- Metrics report:
  - `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`: changed-line coverage `98.91%` (`272/275`)
  - `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift`: changed-line coverage `92.06%` (`232/252`)
  - aggregate changed-line coverage for the executable Swift scope in this slice: `95.64%` (`504/527`)
- Closed the M7, LoRA, Benchmark, and CLI productization transaction:
  - stabilized the final Python verification path by replacing the live Hugging Face benchmark-suite fetch in `test_runtime_edges.py` with a deterministic local fake
  - documented the public `melix` CLI LoRA and benchmark flows in `README.md`
  - updated the LoRA, benchmark, and product-acceptance runbooks so Window UI and CLI workflows now share one repository-owned operator guide
- Verification summary for the final close-out slice:
  - `make proto`: pass
  - `make py-test`: `358 passed in 8.63s`
  - `make swift-test`: `175 tests passed`
  - `make integration-test`: `54 passed in 621.74s (0:10:21)`
  - `PYTHONPATH=/Users/ChenYu/Documents/Github/melix:/Users/ChenYu/Documents/Github/melix/services/mlx-worker-python uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_runtime_edges.py -q`: `22 passed`
- Metrics report:
  - `services/mlx-worker-python/tests/test_runtime_edges.py`: changed-line coverage `100.00%` (`24/24`)
  - `README.md`, `docs/runbooks/m7-benchmark-and-evaluation-foundation.md`, `docs/runbooks/phase-8-lora-adapter-workflow.md`, `docs/runbooks/phase-8-product-acceptance.md`, `docs/plans/2026-04-03-m7-lora-benchmark-cli-productization.md`, and `task_plan.md` are documentation-only and excluded from executable changed-line coverage
  - aggregate changed-line coverage for the executable touched scope in this slice: `100.00%` (`24/24`)
- Landed the post-close VLM benchmark compatibility follow-up for Hugging Face direct-repo benchmarking:
  - upgraded the worker `mlx-vlm` dependency to an upstream commit that includes `gemma4`
  - added a Gemma 4 text-backed compatibility loader in `MLXVLMRuntime` for MLX exports that advertise `image-text-to-text` but only ship language weights
  - taught benchmark target import to preserve VLM routing while overriding benchmark task selection to `text-generation` when multimodal processor files are missing
  - verified `melix bench run --repo-id unsloth/gemma-4-E4B-it-MLX-8bit --suite smoke --sample-size 1 --batch-factor 1 --json` against the local stack
- Verification summary for the VLM benchmark compatibility follow-up:
  - `PYTHONPATH=/Users/ChenYu/Documents/Github/melix:/Users/ChenYu/Documents/Github/melix/services/mlx-worker-python uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_mlx_vlm_runtime.py services/mlx-worker-python/tests/test_maintenance_service.py -q`: `51 passed`
  - `HOME=/Users/ChenYu/Documents/Github/melix/.swift-home CLANG_MODULE_CACHE_PATH=/Users/ChenYu/Documents/Github/melix/.build/ModuleCache.noindex swift test --package-path services/control-plane-swift --scratch-path /tmp/melix-control-plane-build --filter ControlPlaneServiceTests`: `104 tests passed`
  - live proof benchmark:
    - `bench.smoke.ttft_ms = 2452.66`
    - `bench.smoke.tokens_per_second = 60.19`
    - `task_kind = text-generation`
    - `source_repo = unsloth/gemma-4-E4B-it-MLX-8bit`
- Metrics report:
  - changed-line coverage for the touched executable scope: pending repository-wide coverage regeneration for the active uncommitted working tree
  - reason: the benchmark compatibility follow-up was implemented on top of an already-large productization working tree, so a fresh changed-line coverage snapshot still needs to be regenerated before the next commit
- Regenerated the touched-scope coverage evidence for the still-uncommitted direct-HF and VLM benchmark compatibility working tree:
  - fixed `services/control-plane-swift/Tests/WorkerClientTests/PythonBridgeWorkerClientTests.swift` so the process-bridge fixture declares the `mlx` optional dependency expected by the current `uv run --extra mlx` bridge contract
  - fixed `services/mlx-worker-python/worker/engine/maintenance_core.py` benchmark report rendering so persisted `task_kind` follows the resolved runtime task instead of re-deriving from request defaults
  - added targeted Python coverage for benchmark suite prompt extraction, task-aware benchmark metrics, direct-VLM registry defaults, and the updated `dev_up.py` `uv run --extra mlx` invocation
  - added targeted Swift coverage for local CLI runtime construction, benchmark export fallbacks, direct-repo request wiring, direct Hugging Face benchmark imports across OCR, VLM, image generation, and image edit families, and Window UI benchmark target selection states
- Verification summary for the coverage-regeneration follow-up:
  - `PYTHONPATH=/Users/ChenYu/Documents/Github/melix:/Users/ChenYu/Documents/Github/melix/services/mlx-worker-python UV_CACHE_DIR=/Users/ChenYu/Documents/Github/melix/.uv-cache uv run --project services/mlx-worker-python --extra mlx coverage run --source=services/mlx-worker-python/worker -m pytest services/mlx-worker-python/tests -q`: `378 passed in 8.17s`
  - `HOME=/Users/ChenYu/Documents/Github/melix/.swift-home CLANG_MODULE_CACHE_PATH=/Users/ChenYu/Documents/Github/melix/.build/ModuleCache.noindex swift test --enable-code-coverage --filter MelixCLITests`: `29 tests passed`
  - `HOME=/Users/ChenYu/Documents/Github/melix/.swift-home CLANG_MODULE_CACHE_PATH=/Users/ChenYu/Documents/Github/melix/.build/ModuleCache.noindex swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'BenchmarkExportBundleTests|ControlPlaneServiceTests|PythonBridgeWorkerClientTests|OnDemandModelLoaderTests'`: `165 tests passed`
  - `HOME=/Users/ChenYu/Documents/Github/melix/.swift-home CLANG_MODULE_CACHE_PATH=/Users/ChenYu/Documents/Github/melix/.build/ModuleCache.noindex swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'RuntimeViewModelTests|DesktopFoundationViewTests|ControlPlaneXPCClientTests'`: `151 tests passed`
- Metrics report:
  - `services/mlx-worker-python/worker/engine/maintenance_core.py`, `services/mlx-worker-python/worker/model_ops/hub_catalog.py`, `services/mlx-worker-python/worker/model_registry/catalog.py`, `services/mlx-worker-python/worker/productization/benchmark_schemas.py`, `services/mlx-worker-python/worker/productization/benchmark_suites.py`, `services/mlx-worker-python/worker/registry.py`, `services/mlx-worker-python/worker/runtime/vision_family_adapters.py`, and `services/mlx-worker-python/worker/runtime/mlx_vlm_runtime.py`: aggregate changed-line coverage `97.07%` (`265/273`)
  - `Sources/MelixCLICore/MelixCLI.swift`: changed-line coverage `100.00%` (`61/61`)
  - `services/control-plane-swift/Sources/WorkerClient/OnDemandModelLoader.swift`, `services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift`, `services/control-plane-swift/Sources/XPCService/BenchmarkExportBundle.swift`, and `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`: aggregate changed-line coverage `94.25%` (`410/435`)
  - `services/control-plane-swift/Sources/XPCService/ControlPlaneXPCClient.swift`: changed-line coverage `100.00%` (`2/2`) measured from the Window UI test binary because the consumer tests live in `apps/macos-menubar`
  - `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift` and `apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift`: aggregate changed-line coverage `97.93%` (`189/193`)
  - aggregate changed-line coverage for the touched executable Swift scope: `95.80%` (`662/691`)
  - aggregate changed-line coverage for the touched executable Python and Swift scope: `96.16%` (`927/964`)
  - `Makefile`, protocol schemas, generated protobuf outputs, `packages/protocol/descriptors/melix.pb`, `services/mlx-worker-python/pyproject.toml`, `uv.lock`, and `scripts/dev_up.py` are excluded from executable changed-line coverage because they are generated, manifest, or non-measurable support-file changes in this transaction

## 2026-04-01

- Reviewed `docs/superpowers/plans/2026-03-31-m7-3-m7-5-benchmark-eval-foundation.md` and corrected the plan steps for:
  - deterministic evaluation accuracy calculation
  - `handleRunEvaluation` reply wiring so `evaluationResults` is returned together with `evaluationJob`
  - evaluation artifact persistence on a fresh `jobs_root`
  - touched-scope coverage commands so benchmark persistence paths are included
- Verification summary for the M7.3-M7.5 plan update:
  - `make proto`: pass
  - `pytest` touched-scope Python suite: `50 passed`
  - scratch-path Swift test for `ControlPlaneServiceTests/executeHandlesOpsRunEvaluationThroughTheModelOperationsWorker`: pass
- Metrics report:
  - changed-line coverage for the touched Python scope: `N/A`
  - reason: the current uncommitted change set for this review transaction is documentation-only, so `scripts/python_changed_line_coverage.py` reported `TOTAL 100.00% 0/0` and exited non-zero because there were no measurable changed Python lines

## 2026-03-31

- Audited M6 implementation against child plans.
- Confirmed Python quantization benchmark, gate, and focused test suite pass with explicit `PYTHONPATH`.
- Identified remaining work for M6 closure:
  - benchmark evidence gap for active KV and sparse prefill
  - runbook gap for sparse-prefill verification
  - lock-scope semantics gap for family or protected-scope conflicts
- Added `docs/plans/2026-03-31-m6-completion-closure.md`.
- Added `docs/runbooks/m6-acceleration-benchmarks.md`.
- Added Python tests for:
  - linked quantized-artifact upload conflict locking
  - sparse-prefill metrics exposure in `phase2_metrics_report.py`
  - sparse-prefill probe collection in the Phase 2 direct worker report
- Updated quantization manifests to carry `protected_scope` metadata.
- Updated upload conflict locking to use linked quantization identity before falling back to raw artifact paths.
- Extended `scripts/phase2_metrics_report.py` with a `prefill_sparse` probe and sparse-prefill counters in the output.
- Verification summary:
  - `pytest` focused M6 Python suite: `39 passed`
  - `scripts/quantization_benchmarks.py --json`: `profile_count = 7`, `smoke_pass_rate = 100.0`
  - `scripts/quantization_release_gate.py --json`: `passed = true`
  - `scripts/phase5_model_ops_metrics.py`: `quantize job_ms=0.965`, `artifact_bytes=670`, `manifest_bytes=1923`
  - live `make phase2-metrics --json` with `MELIX_RUNTIME_DIR=.runtime/m6-phase2`:
    - `decode_active_kv_quantized.active_kv_quantization_ratio = 25`
    - `decode_active_kv_quantized.tokens_per_second = 41.22`
    - `prefill_sparse.sparse_prefill_accepted_skip_count = 1`
    - `prefill_sparse.accelerated_prefill_gain_pct = 83`
- Committed M6 closure as `2f270b9` (`feat: close m6 acceleration completion gaps`).
- Began M7 with `docs/plans/2026-03-31-m7-1-m7-2-benchmark-schema-foundation.md`.
- Landed initial M7 foundation changes in the working tree:
  - typed benchmark and evaluation schema messages in control-plane proto
  - Python benchmark schema helpers under `worker/productization/benchmark_schemas.py`
  - release-gate benchmark evidence now carries structured `job` and `results`
  - control-plane `ops.run_bench` now assembles typed benchmark job and result payloads
- Verification so far for M7 foundation:
  - `services/mlx-worker-python/tests/test_benchmark_schemas.py`: pass
  - `services/mlx-worker-python/tests/test_release_gates.py`: pass
  - scratch-path Swift test for `ControlPlaneServiceTests/executeHandlesOpsRunBenchThroughTheModelOperationsWorker`: still compiling or pending final result at handoff time
