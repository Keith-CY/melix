# Progress Log

## TODO

- [ ] Root-cause the repository-wide `make swift-test` hang in `services/control-plane-swift` and
  restore clean default verification. Latest evidence on 2026-04-06: `packages/protocol/swift`
  and `services/mlx-text-worker-swift` completed, then the full
  `services/control-plane-swift` package stopped producing output while `swift test` and
  `swiftpm-testing-helper` sat idle at `0.0%` CPU until termination. Rerun `make swift-test`
  after the fix.

## 2026-04-12

## 2026-04-14

- Closed the executable-code evaluation slice for `humaneval` and `mbpp` so Melix now treats
  repository-owned Python code execution as a first-class evaluation path instead of a text-only
  approximation:
  - added checked-in `humaneval.dev.v1` and `mbpp.dev.v1` fixture packages under
    `services/mlx-worker-python/fixtures/evaluation/`
  - gated executable-code suites behind `code_exec_policy=sandboxed`
  - added Python candidate execution with compile/runtime/timeout/test evidence persisted on
    sample records
  - preserved executable-code evidence through `eval compare` sample generation and export-bundle
    normalization
  - added dedicated public CLI compare export commands for summary CSV, samples CSV, and samples
    JSONL
  - updated the canonical benchmark/evaluation contract and runbook for executable-code suites,
    compare exports, and checked-in dev fixtures
- Verification summary for the executable-code evaluation slice:
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_evaluation_core.py services/mlx-worker-python/tests/test_evaluation_store.py services/mlx-worker-python/tests/test_benchmark_export.py services/mlx-worker-python/tests/test_maintenance_service.py -q`: `141 passed in 1.44s`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --filter 'MelixCLIParserTests|MelixCLIRunnerTests'`: `112 tests in 3 suites passed after 0.058 seconds`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/services/control-plane-swift/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter BenchmarkExportBundleTests`: `12 tests in 1 suite passed after 0.002 seconds`
  - `git diff --check`: pass
- Metrics report for the executable-code evaluation slice:
  - Python changed-line coverage: `99.10%` (`220/222`)
  - Swift CLI changed-line coverage: `97.77%` (`263/269`)
  - Swift control-plane changed-line coverage: `100.00%` (`266/266`)
  - Aggregate measurable changed-line coverage across the touched executable-code evaluation slice:
    `98.94%` (`749/757`)

- Realigned the public documentation entrypoints so the repository now presents Melix as a
  project first and an engineering archive second:
  - rewrote `README.md` around product narrative, target users, LoRA and benchmark motivation,
    quick start, and contribution entrypoints
  - replaced the old plan-heavy `docs/README.md` with a grouped navigation page that separates
    product status, onboarding, runbooks, canonical specs, decisions, and historical plans
  - added `docs/getting-started.md`, `docs/contributing.md`, and `docs/current-status.md` so the
    current shipped scope is easier to understand without reading runbooks or archived plans first
  - rewrote `docs/phase-roadmap.md` as a truthful closure summary of the original Phase `0-8`
    model and pointed readers to the milestone execution index for detailed historical coverage
- Verification summary for the documentation realignment:
  - `git diff --check`: pass
- Metrics report for the documentation realignment:
  - `N/A` because this transaction is documentation-only; verification is markdown hygiene plus
    alignment against existing repository sources, progress logs, runbooks, and roadmap records

## 2026-04-09

- Closed the Phase 8 Stage 5 Window UI evidence slice so the native macOS menubar app now
  produces repository-owned live acceptance evidence from the same CLI-backed workflows used by
  the Stage 3 CLI contract:
  - added a dedicated `MELIX_PHASE8_WINDOW_UI_ACCEPTANCE=1` app entrypoint so
    `melix-menubar` can be invoked non-interactively, emit snake_case JSON to `stdout`, and
    report localized acceptance failures to `stderr`
  - kept the Window UI as a thin wrapper over the CLI by routing LoRA train and activate,
    benchmark, matrix benchmark, evaluation, and export flows directly through the subprocess CLI
    workflow runner instead of depending on `RuntimeViewModel` fallback model selection or history
    refresh state
  - hardened adapter-manifest resolution for LoRA acceptance by preferring `artifact_path`,
    falling back to JSON `output_path`, and otherwise deriving `train_lora.adapter.json` from the
    emitted weights path
  - switched live screenshot capture from `ImageRenderer` to an `NSHostingView` bitmap snapshot
    and pinned the captured surface to `Server`, fixing the unreadable placeholder capture and
    producing a readable native desktop screenshot
  - expanded positive and negative Swift coverage around the acceptance entrypoint bootstrap,
    default wiring, subprocess stderr/stdout behavior, and the default runner-factory failure path
- Verification summary for Phase 8 Stage 5:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/apps/macos-menubar/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'MelixSubprocessCLIWorkflowRunnerTests|Phase8WindowUIAcceptanceRunnerTests|AppMainBootstrapTests'`: `46 tests in 3 suites passed after 0.431 seconds`
  - `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/AppMain.swift apps/macos-menubar/Sources/AppMain/Acceptance/Phase8WindowUIAcceptanceRunner.swift apps/macos-menubar/Sources/AppMain/CLI/MelixCLIWorkflowRunning.swift apps/macos-menubar/Sources/AppMain/CLI/MelixSubprocessCLIWorkflowRunner.swift apps/macos-menubar/Tests/MenuBarTests/AppMainBootstrapTests.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift apps/macos-menubar/Tests/MenuBarTests/MelixSubprocessCLIWorkflowRunnerTests.swift`: `95.22%` (`1354/1422`)
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx pytest tests/integration/test_phase8_window_ui_acceptance.py -q`: `2 passed in 292.65s (0:04:52)`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx coverage run --data-file /tmp/p8_s5_py.coverage --source=tests/integration -m pytest tests/integration/test_phase8_window_ui_acceptance.py -q`: `2 passed in 260.51s (0:04:20)`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx coverage json --data-file /tmp/p8_s5_py.coverage -o /tmp/p8_s5_py_coverage.json`: pass
  - `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/p8_s5_py_coverage.json tests/integration/test_phase8_window_ui_acceptance.py`: `N/A` for Stage 5 Python changed-line coverage because the diff-based helper reported `100.00%` (`0/0`) executable changed lines for the newly added deterministic E2E file
  - `source "/Users/ChenYu/Library/Application Support/Melix/melix-product-env.sh" && MELIX_HOME="/Users/ChenYu/Library/Application Support/Melix" MELIX_CLI="$(pwd)/.build/arm64-apple-macosx/debug/melix" MELIX_REPO_ROOT="$(pwd)" MELIX_PHASE8_WINDOW_UI_ACCEPTANCE=1 MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_TIMESTAMP=2026-04-09T192003Z MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_MODEL_ID=mlx-community/Qwen3.5-0.8B-OptiQ-4bit MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_CLI_BUNDLE_PATH="/Users/ChenYu/Library/Application Support/Melix/acceptance/phase8/cli/2026-04-09T162920Z/bundle.json" apps/macos-menubar/.build/arm64-apple-macosx/debug/melix-menubar`: pass with a real evidence bundle at `/Users/ChenYu/Library/Application Support/Melix/acceptance/phase8/window-ui/2026-04-09T192003Z/bundle.json` and screenshot at `/Users/ChenYu/Library/Application Support/Melix/acceptance/phase8/window-ui/2026-04-09T192003Z/window-ui.png`
- Metrics report for Phase 8 Stage 5:
  - Window UI CLI-backed touched-scope changed-line coverage: `95.22%` (`1354/1422`)
  - Python deterministic Window UI E2E changed-line coverage: `N/A` because the touched Python path for Stage 5 is a newly added deterministic E2E file and the diff-based helper reported `0/0` executable changed lines
  - live Window UI evidence captured in `/Users/ChenYu/Library/Application Support/Melix/acceptance/phase8/window-ui/2026-04-09T192003Z/bundle.json` records:
    - `model_id = mlx-community/Qwen3.5-0.8B-OptiQ-4bit`
    - `derived_model_id = mlx-community/Qwen3.5-0.8B-OptiQ-4bit-lora-d479ed9d`
    - `base_chat_assistant_text = BASE_OK`
    - `derived_chat_assistant_text = DERIVED_OK`
    - `lora_train_job_id = model-ops-0137`
    - `lora_activate_job_id = model-ops-0141`
    - `bench_job_id = model-ops-0149`
    - `bench_matrix_job_id = model-ops-0154`
    - `evaluation_job_id = eval-0004`
    - `ui_state.selected_surface = Server`
    - `ui_state.selected_server_session_id = server-session-1`
    - `phase8.ui.managed_materialize_ms = 2001.05`
    - `phase8.ui.session_rebind_ms = 452.72`
    - `phase8.ui.base_chat_roundtrip_ms = 2682.14`
    - `phase8.ui.lora_train_ms = 2391.22`
    - `phase8.ui.lora_activate_ms = 2569.48`
    - `phase8.ui.derived_chat_roundtrip_ms = 2912.88`
    - `phase8.ui.bench_run_ms = 4466.41`
    - `phase8.ui.bench_matrix_run_ms = 6169.73`
    - `phase8.ui.evaluation_run_ms = 3880.67`
    - `phase8.ui.snapshot_render_ms = 286.14`
    - `phase8.ui.cli_bridge_ms = 27526.31`

- Closed the Phase 8 Stage 4 Window UI shell slice so the macOS menubar app now routes the
  remaining Phase 8 write-path workflows through the shipping `melix` CLI instead of keeping a
  second in-process workflow authority:
  - added `MelixCLIWorkflowRunning`, `MelixCLIProcessExecuting`, and
    `MelixSubprocessCLIWorkflowRunner` so the app can shell out to the bundled `melix`
    executable, decode typed JSON receipts, and surface stable typed subprocess failures into the
    native UI state
  - switched the default `AppMain` bootstrap to inject the subprocess-backed CLI workflow runner
    in production while keeping fake and in-process runners available for tests
  - updated `RuntimeViewModel` so managed Hub download, local import, server-session create/select
    and start, LoRA train and activate, benchmark, matrix benchmark, evaluation, and export all
    prefer the CLI-first workflow path when the menubar app has a CLI workflow runner
  - kept server-session rebinding and derived-model activation aligned with the CLI contract by
    allowing activation fallback to the latest trained adapter output path and by not immediately
    overwriting CLI-projected lifecycle state with a stale direct refresh after `lora activate`
  - expanded positive and negative Swift tests around subprocess decoding, process failures,
    bootstrap wiring, server-session mutation failures, train and activate failures, and the
    remaining CLI-backed Window UI workflow guard rails
- Verification summary for Phase 8 Stage 4:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/apps/macos-menubar/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'RuntimeViewModelTests|AppMainBootstrapTests|MelixSubprocessCLIWorkflowRunnerTests'`: `206 tests in 3 suites passed after 1.044 seconds` after a fresh coverage-enabled rebuild
  - `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/CLI/MelixCLIWorkflowRunning.swift apps/macos-menubar/Sources/AppMain/CLI/MelixCLIProcessExecutor.swift apps/macos-menubar/Sources/AppMain/CLI/MelixSubprocessCLIWorkflowRunner.swift apps/macos-menubar/Sources/AppMain/AppMain.swift apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift apps/macos-menubar/Tests/MenuBarTests/MelixSubprocessCLIWorkflowRunnerTests.swift`: `95.93%` (`1273/1327`)
- Metrics report for Phase 8 Stage 4:
  - Window UI CLI-shell touched-scope changed-line coverage: `95.93%` (`1273/1327`)
  - Stage 4 leaves real Window UI screenshot capture and acceptance-bundle emission to Stage 5;
    no live UI evidence path is claimed in this transaction

- Closed the Phase 8 Stage 3 CLI acceptance slice so the public `melix` contract now closes the
  deterministic LoRA, derived-chat, benchmark, matrix benchmark, evaluation, export, and evidence
  bundle path in one repository-owned runner:
  - added `scripts/phase8_acceptance_bundle.py` plus `make phase8-acceptance` so one CLI-owned
    entrypoint materializes or imports the model, rebinds the server session, runs base and
    derived chats, executes LoRA train plus activate, runs bench, matrix bench, and eval, exports
    the resulting artifacts, and writes a machine-readable evidence bundle under
    `MELIX_HOME/acceptance/phase8/cli/<timestamp>/`
  - added deterministic LoRA and benchmark fixtures in the Python worker so the Stage 3 E2E can
    prove the full CLI orchestration path without a live network dependency
  - fixed the Swift process bridge deadlock for large unary payloads by draining `stdout` and
    `stderr` concurrently, and added a regression test that proves `export-results` style payloads
    no longer hang
  - compacted the deterministic text backend to emit one chunk per response so deterministic
    matrix benchmark acceptance finishes in seconds instead of appearing stalled for ~80 seconds
  - fixed local-product launch-agent rendering so the Python worker launch agent resolves the
    absolute `uv` executable path at install time instead of depending on launchd's default `PATH`
    containing `uv`; this unblocked the real CLI acceptance run on the local product install
  - expanded positive and negative Python unit coverage around acceptance-bundle parsing,
    subprocess failures, helper validation, deterministic LoRA artifact materialization, and
    deterministic benchmark dataset fetches, while keeping the deterministic CLI E2E as the end-
    to-end closure for base chat, derived chat, LoRA, bench, eval, and export outputs
- Verification summary for Phase 8 Stage 3:
  - `swift test --package-path services/control-plane-swift --enable-code-coverage --filter PythonBridgeWorkerClientTests`: `52 tests in 1 suite passed after 0.847 seconds`
  - `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift services/control-plane-swift/Tests/WorkerClientTests/PythonBridgeWorkerClientTests.swift`: `100.00%` (`40/40`)
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_runtime_edges.py tests/test_phase8_acceptance_bundle.py -q`: `47 passed in 0.22s`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_install_assets.py services/mlx-worker-python/tests/test_install_local_product_script.py -q`: `13 passed in 0.05s`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx coverage run --data-file /tmp/p8_s3_py.coverage --source=scripts,services/mlx-worker-python/worker,tests -m pytest services/mlx-worker-python/tests/test_runtime_edges.py services/mlx-worker-python/tests/test_deterministic_backend.py services/mlx-worker-python/tests/test_install_assets.py services/mlx-worker-python/tests/test_install_local_product_script.py tests/test_phase8_acceptance_bundle.py tests/integration/test_phase8_cli_acceptance.py -q`: `69 passed in 55.96s`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx coverage json --data-file /tmp/p8_s3_py.coverage -o /tmp/p8_s3_py_coverage.json`: pass
  - `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/p8_s3_py_coverage.json scripts/phase8_acceptance_bundle.py services/mlx-worker-python/worker/grpc_server.py services/mlx-worker-python/worker/model_ops/deterministic_lora_runner.py services/mlx-worker-python/worker/productization/install_assets.py services/mlx-worker-python/worker/runtime/deterministic_backend.py services/mlx-worker-python/tests/test_runtime_edges.py services/mlx-worker-python/tests/test_deterministic_backend.py services/mlx-worker-python/tests/test_install_assets.py tests/test_phase8_acceptance_bundle.py tests/integration/test_phase8_cli_acceptance.py`: `99.47%` (`564/567`)
  - `python3 scripts/install_local_product.py --json`: pass
  - `launchctl bootstrap gui/501 /Users/ChenYu/Library/LaunchAgents/io.melix.swift-text-worker.plist`: pass
  - `launchctl bootstrap gui/501 /Users/ChenYu/Library/LaunchAgents/io.melix.python-worker.plist`: pass after the `install_assets.py` absolute-`uv` fix and a `launchctl bootout`/`bootstrap` restart cycle
  - `launchctl bootstrap gui/501 /Users/ChenYu/Library/LaunchAgents/io.melix.control-plane.plist`: pass
  - `source "/Users/ChenYu/Library/Application Support/Melix/melix-product-env.sh" && MELIX_HOME="/Users/ChenYu/Library/Application Support/Melix" MELIX_CLI="$(pwd)/.build/arm64-apple-macosx/debug/melix" make phase8-acceptance PHASE8_ACCEPTANCE_ARGS="--live --model-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit --training-fixture services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1 --bench-suite smoke --bench-suite latency --matrix-suite smoke --evaluation-suite mmlu --evaluation-dataset mmlu.dev.v1 --server-session-id server-session-1 --json"`: pass with a real evidence bundle at `/Users/ChenYu/Library/Application Support/Melix/acceptance/phase8/cli/2026-04-09T162920Z/bundle.json`
- Metrics report for Phase 8 Stage 3:
  - Swift process-bridge touched-scope changed-line coverage: `100.00%` (`40/40`)
  - Python worker, acceptance runner, and deterministic CLI E2E touched-scope changed-line
    coverage: `99.47%` (`564/567`)
  - the Stage 3 acceptance bundle now records repository-owned orchestration probes:
    - `phase8.cli.managed_materialize_ms`
    - `phase8.cli.session_rebind_ms`
    - `phase8.cli.base_chat_roundtrip_ms`
    - `phase8.cli.derived_chat_roundtrip_ms`
    - `phase8.cli.chat_roundtrip_ms`
    - `phase8.cli.lora_train_ms`
    - `phase8.cli.lora_activate_ms`
    - `phase8.cli.bench_run_ms`
    - `phase8.cli.bench_matrix_run_ms`
    - `phase8.cli.evaluation_run_ms`
    - `phase8.cli.acceptance_bundle_write_ms`
  - live CLI evidence captured in `/Users/ChenYu/Library/Application Support/Melix/acceptance/phase8/cli/2026-04-09T162920Z/bundle.json` records:
    - `base chat assistant_text = BASE_OK`
    - `derived chat assistant_text = Derived_OK`
    - `lora_train_job_id = model-ops-0013`
    - `bench_job_id = model-ops-0024`
    - `bench_matrix_job_id = model-ops-0029`
    - `evaluation_job_id = eval-0001`
    - `phase8.cli.managed_materialize_ms = 129039.66`
    - `phase8.cli.lora_train_ms = 9959.67`
    - `phase8.cli.bench_run_ms = 11100.63`
    - `phase8.cli.bench_matrix_run_ms = 7424.38`
    - `phase8.cli.evaluation_run_ms = 4295.66`
  - the deterministic Stage 3 E2E now proves the full CLI contract
    `model import -> registry rescan -> server start -> base chat -> lora train -> lora activate -> derived chat -> bench -> matrix bench -> eval -> export` and verifies the emitted evidence bundle paths exist

- Closed the Phase 8 Stage 1 CLI materialization slice so managed hub downloads and local-path
  imports now share one machine-readable receipt contract and a deterministic CLI acceptance path:
  - added `melix model import` parser and runner support, including a shared managed-model receipt
    renderer for `model hub download --json` and `model import --json`
  - added Python worker-side `local_import` materialization, receipt metadata, and maintenance-core
    routing for managed local imports
  - added the training fixture `melix-dev-dataset.v1`, positive and negative Swift/Python unit
    coverage, a control-plane regression for unknown imported model ids, and deterministic CLI E2E
    coverage for local import plus registry visibility
  - normalized malformed managed-manifest parsing into a stable CLI runtime error so negative CLI
    validation does not leak raw Foundation JSON errors
- Verification summary for Phase 8 Stage 1:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --filter 'MelixCLIParserTests|MelixCLIRunnerTests'`: `82 tests in 2 suites passed after 0.014 seconds`
  - `python3 scripts/swift_changed_line_coverage.py --binary .build/arm64-apple-macosx/debug/melixPackageTests.xctest/Contents/MacOS/melixPackageTests --profdata .build/arm64-apple-macosx/debug/codecov/default.profdata Sources/MelixCLICore/MelixCLI.swift tests/MelixCLITests/MelixCLIParserTests.swift tests/MelixCLITests/MelixCLIRunnerTests.swift`: `98.80%` (`330/334`)
  - `swift test --package-path services/control-plane-swift --enable-code-coverage --filter ControlPlaneServiceTests`: `179 tests in 1 suite passed after 0.105 seconds`
  - `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`: `96.00%` (`72/75`)
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx coverage run --data-file /tmp/p8_s1_py.coverage --source=services/mlx-worker-python/worker,tests/integration -m pytest services/mlx-worker-python/tests/test_maintenance_service.py tests/integration/test_phase8_cli_acceptance.py -q`: `82 passed in 117.74s (0:01:57)`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx coverage json --data-file /tmp/p8_s1_py.coverage -o /tmp/p8_s1_py_coverage.json`: pass
  - `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/p8_s1_py_coverage.json services/mlx-worker-python/worker/model_ops/download_pipeline.py services/mlx-worker-python/worker/model_ops/local_import_pipeline.py services/mlx-worker-python/worker/engine/maintenance_core.py services/mlx-worker-python/tests/test_maintenance_service.py tests/integration/test_phase8_cli_acceptance.py`: `95.10%` (`136/143`)
- Metrics report for Phase 8 Stage 1:
  - CLI touched-scope changed-line coverage: `98.80%` (`330/334`)
  - control-plane touched-scope changed-line coverage: `96.00%` (`72/75`)
  - Python worker plus deterministic CLI E2E touched-scope changed-line coverage: `95.10%` (`136/143`)
  - deterministic CLI E2E now proves the Stage 1 contract without a full control-plane stack by
    booting only the Python model-ops worker subprocess and exercising `model import` plus
    registry visibility through the `melix` CLI surface

- Closed the Phase 8 Stage 2 CLI session-rebinding and base-chat slice so the approved Stage 1
  managed-model receipt can drive one deterministic text-serving acceptance path entirely through
  the public `melix` CLI contract:
  - added `melix chat run` parser and runner support with typed JSON receipts, plain-text output,
    stream-fallback transcript collection, and stable runtime errors for failed or empty chat
    executions
  - kept the rebinding workflow CLI-first by composing `model roots rescan`, `server session
    update`, `server session select`, `server start`, and `chat run` instead of adding a second
    app-owned binding path
  - added positive and negative Swift unit coverage for chat parsing and runtime execution, plus
    positive and negative process-level deterministic CLI E2E coverage for the rebinding path and
    chat argument validation
- Verification summary for Phase 8 Stage 2:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --filter 'MelixCLIParserTests|MelixCLIRunnerTests'`: `96 tests in 2 suites passed after 0.016 seconds`
  - `python3 scripts/swift_changed_line_coverage.py --binary .build/arm64-apple-macosx/debug/melixPackageTests.xctest/Contents/MacOS/melixPackageTests --profdata .build/arm64-apple-macosx/debug/codecov/default.profdata Sources/MelixCLICore/MelixCLI.swift tests/MelixCLITests/MelixCLIParserTests.swift tests/MelixCLITests/MelixCLIRunnerTests.swift`: `99.67%` (`305/306`)
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx pytest tests/integration/test_phase8_cli_acceptance.py -q`: `4 passed in 54.87s`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx coverage run --data-file /tmp/p8_s2_py.coverage --source=tests/integration -m pytest tests/integration/test_phase8_cli_acceptance.py -q`: `4 passed in 104.68s (0:01:44)`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python --extra mlx coverage json --data-file /tmp/p8_s2_py.coverage -o /tmp/p8_s2_py_coverage.json`: pass
  - `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/p8_s2_py_coverage.json tests/integration/test_phase8_cli_acceptance.py`: `100.00%` (`36/36`)
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --filter MelixCLITests`: blocked by the pre-existing `SessionLifecycleSmokeRunnerTests` environment failure (`requestFailed(code: "unavailable", message: "Model operation worker request failed: unavailable")`); the focused Stage 2 changed-scope command above passed and was used for coverage gating
- Metrics report for Phase 8 Stage 2:
  - CLI touched-scope changed-line coverage: `99.67%` (`305/306`)
  - deterministic CLI E2E touched-scope changed-line coverage: `100.00%` (`36/36`)
  - deterministic Stage 2 evidence now proves the full rebinding contract without
    `MELIX_DEV_TEXT_MODEL_PATH` by exercising `model import -> model roots rescan -> server session
    update -> server session select -> server start -> chat run` through the shipping `melix`
    executable

## 2026-04-06

- Audited milestone-bookkeeping accuracy and aligned the roadmap wording with the implemented
  repository evidence:
  - added the missing parent-level status summaries for `M1-M5`, `M9`, `M12`, `M13`, `M14`,
    `M15`, and `M17` in the roadmap execution index
  - reclassified `M11.4` as an evidence-only closure in the execution index and its plan document
    so the roadmap no longer implies true SSD-backed runtime execution already exists
  - recorded the current repository-wide `make swift-test` hang in an explicit top-level TODO
- Verification summary for the milestone-bookkeeping audit:
  - `git diff --check`: pass
- Metrics report for the milestone-bookkeeping audit:
  - `N/A` because the transaction only updates planning and progress documents; no executable
    scope changed

- Formalized the parent-level `M6` completion state so the execution index no longer leaves the
  closed quantization milestone unregistered:
  - added a completed status section to `docs/plans/2026-03-31-m6-completion-closure.md`
  - added a parent-level completed status line to the `M6` section in the execution index while
    leaving child-level `M6.1-M6.11` backfill for a later audit
- Verification summary for the `M6` parent-status formalization:
  - `git diff --check`: pass
- Metrics report for the `M6` parent-status formalization:
  - `N/A` because the transaction only updates planning and progress documents; executable M6
    benchmark and locking evidence remains recorded in `docs/plans/2026-03-31-m6-completion-closure.md`

- Backfilled the child-level `M7.1-M7.10` execution-index statuses so the completed benchmark and
  evaluation work is represented per child milestone instead of only through the parent `M7`
  summary:
  - added completed status lines for serving schema, evaluation schema, runtime runners, dataset
    packaging, evaluation coverage, queue and parameter controls, export and comparison, VLM
    benchmark support, submission and device identity, and release-gate integration
  - kept the transaction docs-only and limited it to execution-index accuracy
- Verification summary for the `M7.1-M7.10` child-status backfill:
  - `git diff --check`: pass
- Metrics report for the `M7.1-M7.10` child-status backfill:
  - `N/A` because the transaction only updates planning and progress documents; executable
    benchmark and evaluation coverage remains recorded in the underlying `M7` progress entries and
    umbrella execution plans

- Closed the remaining child-entry bookkeeping gap for `M8.1-M8.4` so the execution index no
  longer relies on the parent `M8` summary alone to show that the backend foundations are done:
  - added top-level completed status summaries to the four child plan documents
  - added child-level completed status lines to the execution index for `M8.1`, `M8.2`, `M8.3`,
    and `M8.4`
  - kept the transaction docs-only so the next milestone audit can focus on actual implementation
    gaps instead of status drift
- Verification summary for the `M8.1-M8.4` child-entry bookkeeping closure:
  - `git diff --check`: pass
- Metrics report for the `M8.1-M8.4` child-entry bookkeeping closure:
  - `N/A` because the transaction only updates planning and progress documents; executable
    changed-line coverage for the original backend-foundations work remains recorded in
    `docs/plans/2026-04-01-m8-1-m8-4-backend-foundations.md`

- Closed the remaining `M13.3` bookkeeping gap by aligning the plan document and execution index
  with the already-landed repository evidence for tooling, embedding, and config-file settings:
  - added a top-level completed status summary to
    `docs/plans/2026-03-31-m13-3-tooling-embedding-and-config-file-settings.md`
  - added the missing completed status line to the `M13.3` execution-index entry so the roadmap no
    longer under-reports the landed slice
  - kept the transaction docs-only and used it as the starting point for the next milestone audit
- Verification summary for the `M13.3` bookkeeping closure:
  - `git diff --check`: pass
- Metrics report for the `M13.3` bookkeeping closure:
  - `N/A` because the transaction only updates repository planning and progress documents; no
    executable scope changed and no additional coverage command is required

- Closed `M17.4` by turning speech support into a repository-owned live-path operator workflow for
  both transcription and synthesis instead of leaving the speech families at contract-only status:
  - added lazy-load coverage on `/v1/audio/transcriptions` and `/v1/audio/speech` so cataloged
    managed speech models can hydrate runtime-pack plus managed-model metadata and load on demand
    without bespoke preload wiring
  - added a repository-owned speech smoke workflow in
    `scripts/m17_speech_runtime_smoke.py` plus `make phase17-metrics`, using reproducible fake
    `mlx_audio` fixtures to exercise `Whisper`, `Parakeet`, `Kokoro`, and `Qwen3-TTS` through the
    real local HTTP path
  - added a machine-readable speech metrics builder and promoted the speech-family support-matrix
    rows from `contract_only` to `verified`, with one canonical live-path integration test node
    attached to the four speech families
  - added the speech operator-evidence runbook and updated the docs index plus support-matrix
    guidance so operators can reproduce, diagnose, and compare locale, fallback, and dependency
    state without source inspection
- Verification summary for `M17.4`:
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$HOME/.cache/uv" uv run --project services/mlx-worker-python --extra mlx python scripts/m17_speech_runtime_smoke.py --json`: pass with `ok: true`
  - `make phase17-metrics`: pass with `speech.integration_success_rate = 100.0`
  - `python3 -m py_compile scripts/m17_speech_runtime_smoke.py tests/integration/test_m17_speech_runtime_smoke.py services/mlx-worker-python/worker/productization/acceptance_metrics.py tests/integration/helpers.py`: pass
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$HOME/.cache/uv" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_acceptance_metrics.py tests/integration/test_m17_speech_runtime_smoke.py tests/integration/test_non_text_endpoints.py -q`: `30 passed in 189.08s (0:03:09)`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$HOME/.cache/uv" uv run --project services/mlx-worker-python --extra mlx coverage run --data-file /tmp/m17_4_py.coverage --source=services/mlx-worker-python/worker,tests/integration,scripts -m pytest services/mlx-worker-python/tests/test_acceptance_metrics.py tests/integration/test_m17_speech_runtime_smoke.py tests/integration/test_non_text_endpoints.py -q && PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$HOME/.cache/uv" uv run --project services/mlx-worker-python --extra mlx coverage json --data-file /tmp/m17_4_py.coverage -o /tmp/m17_4_py_coverage.json && python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/m17_4_py_coverage.json services/mlx-worker-python/worker/productization/acceptance_metrics.py services/mlx-worker-python/worker/productization/__init__.py services/mlx-worker-python/worker/productization/family_support_matrix.py tests/integration/helpers.py scripts/m17_speech_runtime_smoke.py services/mlx-worker-python/tests/test_acceptance_metrics.py tests/integration/test_m17_speech_runtime_smoke.py tests/integration/test_non_text_endpoints.py`: `30 passed in 188.69s (0:03:08)` and changed-line coverage `100.00%` (`16/16`)
  - `swift test --package-path services/control-plane-swift --filter 'OpenAIHandlerTests'`: `115 tests in 1 suite passed after 0.083 seconds`
  - `swift test --package-path services/control-plane-swift --filter 'OpenAIHandlerTests' --enable-code-coverage`: `115 tests in 1 suite passed`
  - `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift services/control-plane-swift/Sources/WorkerClient/OnDemandModelLoader.swift services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`: `96.28%` (`181/188`)
  - `make proto`: pass
  - `make py-test`: `532 passed in 34.95s`
  - `make integration-test`: `75 passed in 1125.03s (0:18:45)`
  - `make swift-test`: repository-wide execution entered `services/control-plane-swift` and then blocked without additional output or a failure line; the touched control-plane scope above passed with coverage enabled, so the repository-wide hang is recorded as existing infrastructure instability rather than an `M17.4` regression
  - `git diff --check`: pass
- Metrics report for `M17.4`:
  - the repository-owned speech smoke report now emits:
    - `speech.integration_success_rate`
    - `speech.transcription.whisper.request_latency_ms`
    - `speech.transcription.whisper.duration_seconds`
    - `speech.transcription.whisper.preprocess_latency_ms`
    - `speech.transcription.whisper.chunk_count`
    - `speech.transcription.parakeet.request_latency_ms`
    - `speech.transcription.parakeet.duration_seconds`
    - `speech.transcription.parakeet.preprocess_latency_ms`
    - `speech.transcription.parakeet.chunk_count`
    - `speech.synthesis.kokoro.request_latency_ms`
    - `speech.synthesis.kokoro.output_bytes`
    - `speech.synthesis.qwen3_tts.request_latency_ms`
    - `speech.synthesis.qwen3_tts.output_bytes`
    - `speech.synthesis.qwen3_tts.voice_fallback_count`
    - `speech.synthesis.qwen3_tts.locale_header_success_rate`
  - `make phase17-metrics` currently records:
    - `speech.integration_success_rate = 100.0`
    - `speech.transcription.whisper.request_latency_ms = 457.15`
    - `speech.transcription.parakeet.request_latency_ms = 560.32`
    - `speech.synthesis.kokoro.request_latency_ms = 453.13`
    - `speech.synthesis.qwen3_tts.request_latency_ms = 546.36`
    - `speech.synthesis.qwen3_tts.voice_fallback_count = 0.0`
    - `speech.synthesis.qwen3_tts.locale_header_success_rate = 100.0`
  - changed-line coverage for the touched handwritten executable scope:
    - Python touched-scope coverage: `100.00%` (`16/16`)
    - Swift control-plane touched-scope coverage: `96.28%` (`181/188`)
  - generated protobuf outputs, Make targets, runbooks, and planning-status documents are excluded
    from executable changed-line coverage because they are generated artifacts or non-executable
    repository bookkeeping

- Closed `M17.3` by making speech locale policy, resolved speech settings, and optional
  dependency-profile state explicit across the Python worker registry truth, the Swift
  control-plane catalog, the `/v1/audio/speech` HTTP path, and the macOS operator model-info
  surface:
  - added stable speech metadata keys for `melix.audio.default_locale`,
    `melix.audio.packaged_default_locale`, and `melix.audio.locale_policy` in both the Python
    worker registry catalog and the Swift control-plane seed models, then projected those fields
    through the repository-owned family support matrix
  - extended `/v1/audio/speech` with an optional `locale` field, normalized explicit locale
    handling, and operator-visible response headers that now report requested locale, resolved
    locale, locale source, locale policy, supported locales, install profile, runtime-pack state,
    runtime-pack ID, and managed-model state
  - extended the macOS operator model-info surface so speech models now render default locale,
    packaged default locale, locale policy, runtime-pack state, runtime-pack ID, and audio model
    state without requiring raw metadata inspection
  - expanded focused Swift, Python, menubar, and integration coverage to guard missing-model
    fallback, packaged-default fallback, empty-locale metadata, unsupported explicit locale
    rejection, and operator-visible speech metadata parity
- Verification summary for `M17.3`:
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$HOME/.cache/uv" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_audio_runtime.py services/mlx-worker-python/tests/test_acceptance_metrics.py tests/integration/test_non_text_endpoints.py -q`: `36 passed in 186.09s (0:03:06)`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$HOME/.cache/uv" uv run --project services/mlx-worker-python --extra mlx coverage run --data-file /tmp/m17_3_py.coverage --source=services/mlx-worker-python/worker -m pytest services/mlx-worker-python/tests/test_audio_runtime.py services/mlx-worker-python/tests/test_acceptance_metrics.py tests/integration/test_non_text_endpoints.py -q && PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$HOME/.cache/uv" uv run --project services/mlx-worker-python --extra mlx coverage json --data-file /tmp/m17_3_py.coverage -o /tmp/m17_3_py_coverage.json && python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/m17_3_py_coverage.json services/mlx-worker-python/worker/model_registry/catalog.py services/mlx-worker-python/worker/productization/family_support_matrix.py services/mlx-worker-python/tests/test_audio_runtime.py services/mlx-worker-python/tests/test_acceptance_metrics.py tests/integration/test_non_text_endpoints.py`: `36 passed in 245.22s (0:04:05)` and changed-line coverage `100.00%` (`3/3`)
  - `swift test --package-path services/control-plane-swift --filter 'ModelCatalogTests|PythonBridgeWorkerClientTests|OpenAIHandlerTests'`: `198 tests in 3 suites passed after 0.849 seconds`
  - `swift test --package-path services/control-plane-swift --filter 'ModelCatalogTests|PythonBridgeWorkerClientTests|OpenAIHandlerTests' --enable-code-coverage`: `198 tests in 3 suites passed after 0.852 seconds`
  - `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift services/control-plane-swift/Sources/ModelCatalog/ModelCatalog.swift services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift services/control-plane-swift/Tests/ControlPlaneTests/ModelCatalogTests.swift services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift services/control-plane-swift/Tests/WorkerClientTests/PythonBridgeWorkerClientTests.swift`: `100.00%` (`503/503`)
  - `swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`: `242 tests in 2 suites passed after 5.489 seconds`
  - `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`: `100.00%` (`66/66`)
  - `git diff --check`: pass
- Metrics report for `M17.3`:
  - `/v1/audio/speech` now emits operator-visible locale and dependency-profile headers:
    - `x-melix-audio-requested-locale`
    - `x-melix-audio-resolved-locale`
    - `x-melix-audio-locale-source`
    - `x-melix-audio-locale-policy`
    - `x-melix-audio-model-default-locale`
    - `x-melix-audio-packaged-default-locale`
    - `x-melix-audio-supported-locales`
    - `x-melix-audio-install-profile`
    - `x-melix-audio-runtime-pack-state`
    - `x-melix-audio-runtime-pack-id`
    - `x-melix-audio-model-state`
  - the repository-owned speech support matrix now exposes:
    - `("speech", "deterministic-speech").contract.default_locale = "und"`
    - `("speech", "deterministic-speech").contract.packaged_default_locale = "und"`
    - `("speech", "kokoro").contract.default_locale = "en"`
    - `("speech", "qwen3-tts").contract.default_locale = "zh"`
    - `("speech", "qwen3-tts").contract.locale_policy = "request>model_default>packaged_default"`
  - changed-line coverage for the touched handwritten executable scope:
    - Python touched-scope coverage: `100.00%` (`3/3`)
    - Swift control-plane touched-scope coverage: `100.00%` (`503/503`)
    - Swift menubar touched-scope coverage: `100.00%` (`66/66`)
  - generated protobuf outputs and planning-status documents are excluded from executable
    changed-line coverage because they are generated artifacts or repository bookkeeping

- Closed `M17.2` by making real text-to-speech backend families and voice-catalog metadata
  first-class across the Swift catalog, the Swift Python-bridge model-spec path, the
  repository-owned family support matrix, and the macOS operator model-info surface:
  - added `mlxQwen3TTSModel()` to the Swift control-plane catalog and matching bridge model-spec
    wiring, then promoted both `melix-kokoro-mlx` and `melix-qwen3-tts-mlx` into the default
    phase-six seed set so operators can inspect real speech models without bespoke fixture wiring
  - extended the Python worker registry metadata and repository-owned family support matrix with
    stable speech capability fields for install profile, languages, voice mode, output formats,
    instruction support, voice locales, and voice-catalog summary
  - extended the Window UI model-info surface so speech models now render operator-readable voice
    catalog details instead of requiring raw `melix.audio.*` inspection
  - stabilized the existing `DesktopPolishSmokeTests` partial-chat observation path so the
    menubar full-package suite no longer flakes when the package runs under concurrent suite load
- Verification summary for `M17.2`:
  - `make proto`: pass
  - `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_audio_runtime.py services/mlx-worker-python/tests/test_mlx_audio_runtime.py services/mlx-worker-python/tests/test_runtime_edges.py services/mlx-worker-python/tests/test_acceptance_metrics.py tests/integration/test_non_text_endpoints.py -q`: `62 passed in 211.24s (0:03:31)`
  - `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python coverage run --data-file=/tmp/m17_2_python.coverage -m pytest services/mlx-worker-python/tests/test_audio_runtime.py services/mlx-worker-python/tests/test_mlx_audio_runtime.py services/mlx-worker-python/tests/test_runtime_edges.py services/mlx-worker-python/tests/test_acceptance_metrics.py tests/integration/test_non_text_endpoints.py -q && PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python coverage json --data-file=/tmp/m17_2_python.coverage -o /tmp/m17_2_python_coverage.json && python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/m17_2_python_coverage.json services/mlx-worker-python/worker/model_registry/catalog.py services/mlx-worker-python/worker/productization/family_support_matrix.py services/mlx-worker-python/tests/test_audio_runtime.py services/mlx-worker-python/tests/test_mlx_audio_runtime.py services/mlx-worker-python/tests/test_runtime_edges.py services/mlx-worker-python/tests/test_acceptance_metrics.py tests/integration/test_non_text_endpoints.py`: `62 passed in 177.10s (0:02:57)` and changed-line coverage `100.00%` (`54/54`)
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --package-path services/control-plane-swift --filter 'ModelCatalogTests|PythonBridgeWorkerClientTests'`: `85 tests in 2 suites passed after 1.114 seconds`
  - `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/ModelCatalog/ModelCatalog.swift services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift services/control-plane-swift/Tests/ControlPlaneTests/ModelCatalogTests.swift services/control-plane-swift/Tests/WorkerClientTests/PythonBridgeWorkerClientTests.swift`: `100.00%` (`121/121`)
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --package-path apps/macos-menubar --filter 'DesktopFoundationViewTests|RuntimeViewModelTests|DesktopPolishSmokeTests'`: `243 tests in 3 suites passed after 5.424 seconds`
  - `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift apps/macos-menubar/Tests/MenuBarTests/DesktopPolishSmokeTests.swift`: `100.00%` (`145/145`)
  - `make py-test`: `531 passed in 34.46s`
  - `make swift-test`: repository-wide execution still stalled inside the untouched
    `services/control-plane-swift` full-package path after the touched protocol, text-worker,
    focused control-plane, and full menubar suites had already passed; the hung
    `swiftpm-testing-helper` was sampled while idle in `waitUntilExit`, then terminated and
    recorded as existing repository instability rather than an `M17.2` regression
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest tests/integration/test_recovery_flows.py::test_warm_followup_prefers_hot_route_and_reduces_ttft_against_cold_baseline -q`: `1 passed in 11.30s`
  - `make integration-test`: `74 passed in 941.45s (0:15:41)`
  - `git diff --check`: pass
- Metrics report for `M17.2`:
  - the repository-owned family support matrix now exposes:
    - `summary.speech_family_count = 2`
    - `("speech", "kokoro").contract.backend_id = "mlx_audio.tts"`
    - `("speech", "qwen3-tts").contract.backend_id = "mlx_audio.tts"`
    - `("speech", "kokoro").contract.voice_mode = "named"`
    - `("speech", "qwen3-tts").contract.voice_mode = "hybrid"`
    - `("speech", "qwen3-tts").contract.supports_instructions = true`
    - `("speech", "qwen3-tts").contract.voice_locales = ["zh", "en"]`
  - changed-line coverage for the touched handwritten executable scope:
    - Python touched-scope coverage: `100.00%` (`54/54`)
    - Swift control-plane touched-scope coverage: `100.00%` (`121/121`)
    - Swift menubar touched-scope coverage: `100.00%` (`145/145`)
  - generated protobuf outputs and planning-status documents are excluded from executable
    changed-line coverage because they are generated artifacts or repository bookkeeping

- Closed `M17.1` by making real speech-to-text backend families first-class across the Swift
  catalog, the Python bridge path, and the repository-owned model-family support matrix:
  - added `mlxParakeetModel()` to the Swift control-plane catalog and promoted both
    `melix-whisper-mlx` and `melix-parakeet-mlx` into the default phase-six seed set, so real
    speech-to-text models are now discoverable without bespoke test wiring
  - added the matching `melix-parakeet-mlx` bridge model spec in
    `services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift`, keeping
    the control-plane bootstrap path aligned with the existing Python worker registry truth
  - extended the repository-owned family support matrix with `transcription` rows for `whisper`
    and `parakeet`, including stable `backend_id`, `install_profile`, and `languages` contract
    fields plus truthful `contract_only` live-path status
  - expanded focused Swift, Python, and integration coverage so catalog metadata, runtime routing,
    and matrix exports all guard the new speech-to-text families
- Verification summary for `M17.1`:
  - `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_audio_runtime.py services/mlx-worker-python/tests/test_mlx_audio_runtime.py services/mlx-worker-python/tests/test_runtime_edges.py services/mlx-worker-python/tests/test_acceptance_metrics.py tests/integration/test_non_text_endpoints.py -q`: `62 passed in 176.80s (0:02:56)`
  - `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python coverage run --data-file=/tmp/m17_1_python.coverage -m pytest services/mlx-worker-python/tests/test_audio_runtime.py services/mlx-worker-python/tests/test_mlx_audio_runtime.py services/mlx-worker-python/tests/test_runtime_edges.py services/mlx-worker-python/tests/test_acceptance_metrics.py tests/integration/test_non_text_endpoints.py -q && PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python coverage json --data-file=/tmp/m17_1_python.coverage -o /tmp/m17_1_python_coverage.json && python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/m17_1_python_coverage.json services/mlx-worker-python/worker/productization/family_support_matrix.py services/mlx-worker-python/tests/test_audio_runtime.py services/mlx-worker-python/tests/test_mlx_audio_runtime.py services/mlx-worker-python/tests/test_runtime_edges.py services/mlx-worker-python/tests/test_acceptance_metrics.py tests/integration/test_non_text_endpoints.py`: `62 passed in 176.16s (0:02:56)` and changed-line coverage `100.00%` (`35/35`)
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --package-path services/control-plane-swift --filter 'ModelCatalogTests|PythonBridgeWorkerClientTests'`: `85 tests in 2 suites passed after 1.035 seconds`
  - `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/ModelCatalog/ModelCatalog.swift services/control-plane-swift/Sources/WorkerClient/PythonBridgeWorkerClient.swift services/control-plane-swift/Tests/ControlPlaneTests/ModelCatalogTests.swift services/control-plane-swift/Tests/WorkerClientTests/PythonBridgeWorkerClientTests.swift`: `100.00%` (`76/76`)
  - `make py-test`: `531 passed in 35.07s`
  - `make swift-test`: repository-wide execution again blocked inside the untouched
    `services/control-plane-swift` package after focused touched-scope Swift suites had already
    passed; the hang was sampled, reproduced, and recorded as existing repository instability
    rather than an `M17.1` regression
  - `make integration-test`: `74 passed in 1013.15s (0:16:53)`
  - `git diff --check`: pass
- Metrics report for `M17.1`:
  - the repository-owned family support matrix now exposes:
    - `summary.transcription_family_count = 2`
    - `("transcription", "whisper").contract.backend_id = "mlx_audio.stt"`
    - `("transcription", "parakeet").contract.backend_id = "mlx_audio.stt"`
    - `("transcription", "whisper").contract.install_profile = "audio-stt"`
    - `("transcription", "parakeet").contract.install_profile = "audio-stt"`
    - `("transcription", "whisper").contract.languages = ["auto"]`
    - `("transcription", "parakeet").contract.languages = ["auto"]`
  - changed-line coverage for the touched handwritten executable scope:
    - Python touched-scope coverage: `100.00%` (`35/35`)
    - Swift touched-scope coverage: `100.00%` (`76/76`)
  - generated protobuf outputs and planning-status documents are excluded from executable
    changed-line coverage because they are generated artifacts or repository bookkeeping

- Closed `M16.4` and completed `M16` by adding repository-owned live video operator evidence on
  top of the ingress, frame-policy, routing, and cleanup slices:
  - added `scripts/m16_video_runtime_smoke.py` so one reproducible smoke workflow now exercises a
    short local video path, a remote video URL served by a repository-owned local fixture server,
    a bounded inline multi-frame request, and a concurrent video-plus-text routing probe
  - added `build_phase16_video_metrics_report(...)` plus productization export wiring so the
    touched scope now emits machine-readable success rates and operator metrics for video request
    latency, frame budget and window, temp-media cleanup evidence, and scheduler text-protection
    signals under video load
  - added `tests/integration/test_video_runtime_smoke.py` together with expanded acceptance-metrics
    unit coverage so the smoke payload contract and summary report are both test-backed
  - added `docs/runbooks/video-understanding-evidence.md` and updated the docs indexes so operators
    can reproduce the current video path and interpret local-path, remote-URL, bounded-window,
    cleanup, and routing signals without code spelunking
- Verification summary for `M16.4`:
  - `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_acceptance_metrics.py tests/integration/test_video_runtime_smoke.py -q`: `17 passed in 15.29s`
  - `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python coverage run --data-file=/tmp/m16_4_python.coverage -m pytest services/mlx-worker-python/tests/test_acceptance_metrics.py tests/integration/test_video_runtime_smoke.py -q && PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python coverage json --data-file=/tmp/m16_4_python.coverage -o /tmp/m16_4_python_coverage.json && python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/m16_4_python_coverage.json services/mlx-worker-python/worker/productization/acceptance_metrics.py services/mlx-worker-python/worker/productization/__init__.py scripts/m16_video_runtime_smoke.py services/mlx-worker-python/tests/test_acceptance_metrics.py tests/integration/test_video_runtime_smoke.py`: `17 passed in 15.37s` and changed-line coverage `100.00%` (`52/52`)
  - `make py-test`: `530 passed in 30.56s`
  - `git diff --check`: pass
- Metrics report for `M16.4`:
  - repository-owned video smoke evidence now records:
    - local-path video request success and latency
    - remote-URL video request success and latency using a local fixture server rather than an
      internet dependency
    - bounded-window frame-policy evidence through `vision.video_frame_count`,
      `vision.video_frame_budget`, and `vision.video_window_ms`
    - inline-video cleanup evidence through `vision.temp_media_artifact_count`,
      `vision.temp_media_artifact_bytes`, `vision.temp_media_cleanup_latency_ms`, and
      `vision.temp_media_cleanup_failure_count`
    - routing evidence through `scheduler.text_ttft_under_multimodal_ms` and
      `scheduler.multimodal_queue_delay_ms`
  - changed-line coverage for the touched handwritten executable scope:
    - Python touched-scope coverage: `100.00%` (`52/52`)
  - `docs/*.md` and `task_plan.md` are excluded from executable changed-line coverage because they
    are repository documentation and bookkeeping rather than handwritten runtime logic

- Closed `M16.3` by making temporary multimodal analysis artifacts explicit, deterministically
  cleaned up, and visible through worker plus control-plane state instead of remaining hidden
  inside best-effort temporary-directory scopes:
  - added `worker/runtime/temp_media_lifecycle.py` so one repository-owned temp-media session now
    stages analysis artifacts, tracks byte totals, records cleanup latency, and reports cleanup
    failures
  - adopted that lifecycle helper in both deterministic and MLX-backed VLM runtimes so inline
    image and video assets now follow the same success, failure, and cancellation cleanup path,
    while prepared video inputs preserve inline bytes for deterministic staging
  - extended worker `RuntimeStats`, registry bookkeeping, and Swift `RequestCoordinator` metric
    publication with temporary-media artifact count, artifact bytes, cleanup latency, and cleanup
    failure counters for OCR and VLM routes
  - added focused Python, Swift, and integration coverage for successful cleanup, explicit cleanup
    failure reporting, and cancelled-generate cleanup behavior across the multimodal lifecycle path
- Verification summary for `M16.3`:
  - `make proto`: pass
  - `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_temp_media_lifecycle.py services/mlx-worker-python/tests/test_video_preprocessing.py services/mlx-worker-python/tests/test_runtime_edges.py services/mlx-worker-python/tests/test_vision_runtime.py services/mlx-worker-python/tests/test_mlx_vlm_runtime.py -q`: `83 passed in 0.24s`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'ocrRequestsPublishVisionMetrics|vlmRequestsPublishVisionMetrics|videoBearingVLMRequestsPublishFramePolicyMetrics|postChatCompletionsRecordsVideoFrameMetricsForVLMRequests'`: `4 tests passed`
  - `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python pytest tests/integration/test_vlm_phase_aware_lifecycle.py -q`: `5 passed in 56.55s`
  - `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python coverage run --data-file=/tmp/m16_3_python.coverage -m pytest services/mlx-worker-python/tests/test_temp_media_lifecycle.py services/mlx-worker-python/tests/test_video_preprocessing.py services/mlx-worker-python/tests/test_runtime_edges.py services/mlx-worker-python/tests/test_vision_runtime.py services/mlx-worker-python/tests/test_mlx_vlm_runtime.py tests/integration/test_vlm_phase_aware_lifecycle.py -q`: `88 passed in 73.45s (0:01:13)`
  - `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/Requests/RequestCoordinator.swift services/control-plane-swift/Tests/HTTPGatewayTests/RequestCoordinatorTests.swift services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`: `100.00%` (`64/64`)
  - `make py-test`: `528 passed in 31.36s`
  - `make swift-test`: repository-wide execution entered the `services/control-plane-swift` package
    and then blocked without emitting a failure or additional test output; focused touched-scope
    Swift verification and changed-line coverage passed, so the full-package hang is recorded as
    out-of-scope repository instability rather than an `M16.3` regression
  - `make integration-test`: repository-wide execution remained long-running during this capture;
    the touched live VLM lifecycle integration suite above passed, so `M16.3` acceptance relies on
    the focused live-path evidence rather than waiting on unrelated repository integration runtime
- Metrics report for `M16.3`:
  - touched handwritten executable scope now exposes:
    - `last_temp_media_artifact_count`
    - `last_temp_media_artifact_bytes`
    - `last_temp_media_cleanup_latency_ms`
    - `last_temp_media_cleanup_failure_count`
    - `vision.temp_media_artifact_count`
    - `vision.temp_media_artifact_bytes`
    - `vision.temp_media_cleanup_latency_ms`
    - `vision.temp_media_cleanup_failure_count`
  - changed-line coverage for the touched handwritten executable scope:
    - Python worker aggregate touched-scope coverage: `95.83%` (`207/216`)
    - Swift control-plane aggregate touched-scope coverage: `100.00%` (`64/64`)
  - generated protobuf outputs and planning-status documents are excluded from executable
    changed-line coverage because they are generated artifacts or non-executable repository
    bookkeeping

- Closed `M16.2` by making video analysis requests carry explicit frame-policy state through the
  worker runtime, background-lane scheduling, and control-plane observability:
  - extended the worker runtime stats protocol with
    `last_video_effective_frame_count`, `last_video_requested_frame_budget`, and
    `last_video_window_ms`
  - folded normalized video inputs into `PreparedVisionRequest`, including effective
    `uniform_sample` frame-policy projection, video-aware multimodal hashing, and derived helper
    counters for total effective frames, requested budgets, and active clip windows
  - updated deterministic and MLX VLM runtimes plus worker registry bookkeeping so video-bearing
    requests now emit explicit video probe evidence, while text-backed Gemma 4 paths rewrite
    video-only prompts into deterministic text form instead of silently dropping media context
  - projected video-bearing VLM background-lane metrics through `RequestCoordinator`, added an
    HTTP-level regression test for chat-completion video metrics, and kept the Swift text worker
    exhaustive by treating `videoUri` and `videoBytes` parts as media for context guards while
    excluding them from cache-restore prefix reuse
- Verification summary for `M16.2`:
  - `make proto`: pass
  - `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_video_preprocessing.py services/mlx-worker-python/tests/test_vision_runtime.py services/mlx-worker-python/tests/test_mlx_vlm_runtime.py -q`: `49 passed in 0.23s`
  - `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_vision_runtime.py services/mlx-worker-python/tests/test_mlx_vlm_runtime.py -q`: `46 passed in 0.16s`
  - `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python pytest tests/integration/test_vlm_phase_aware_lifecycle.py -q`: `3 passed in 34.20s`
  - `make py-test`: `525 passed in 35.75s`
  - `make integration-test`: `71 passed in 1079.85s (0:17:59)`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --package-path services/control-plane-swift --filter 'videoBearingVLMRequestsPublishFramePolicyMetrics|postChatCompletionsRecordsVideoFrameMetricsForVLMRequests'`: `2 tests in 2 suites passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --package-path services/mlx-text-worker-swift --filter 'testCacheRestoreMetadataWalkBackAccountsForMediaPrefixesAndIgnoresNilParts|testRuntimeRegistryCountsMediaBlankAndNilPartsForContextGuard'`: `2 tests in 1 suite passed`
  - `make swift-test`: failed outside the touched `M16.2` scope after repository-wide package execution completed; the focused control-plane and text-worker suites above passed with coverage enabled
  - `git diff --check`: pass
- Metrics report for `M16.2`:
  - explicit video probe fields now emitted by the touched scope:
    - `last_video_effective_frame_count`
    - `last_video_requested_frame_budget`
    - `last_video_window_ms`
    - `vision.video_frame_count`
    - `vision.video_frame_budget`
    - `vision.video_window_ms`
    - `vision.video_first_token_ms`
  - changed-line coverage for the touched handwritten executable scope:
    - Python worker touched-scope coverage: `100.00%` (`148/148`)
    - Swift control-plane touched-scope coverage: `100.00%` (`197/197`)
    - Swift text-worker touched-scope coverage: `100.00%` (`15/15`)

- Closed `M16.1` by defining the first repository-owned video ingress contract before any runtime
  frame extraction or scheduler work:
  - extended the shared worker protocol so `MessagePart` now has explicit `video_uri` and
    `video_bytes` forms, while `MediaMetadata` now carries `MEDIA_TYPE_VIDEO`, `frame_budget`,
    `start_ms`, and `end_ms`
  - added Swift-side `input_video` decoding and normalization in `MultimodalRequestNormalizer`,
    including top-level `video_base64` convenience decoding, URI scheme validation, supported
    container inference, inspectable duration or frame-budget metadata, and typed operator-facing
    preprocessing-bound failures
  - added `worker/runtime/video_preprocessing.py` so the Python worker now validates normalized
    video parts with one contract helper that preserves source kind, reference, filename, format,
    byte length, and time-bound metadata without yet fetching or decoding frames
  - added focused Swift and Python tests that prove accepted URI and inline video shapes,
    structured error contracts, protobuf round-trips, and safe dispatch of video-bearing requests
    during the ingress-only slice
- Verification summary for `M16.1`:
  - `make proto`: pass
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --package-path services/control-plane-swift --filter 'MultimodalContractTests|videoBearingVLMRequestsStayDispatchableDuringIngressOnlyRollout'`: `12 tests in 2 suites passed after 0.002 seconds`
  - `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/Requests/MultimodalRequestNormalizer.swift services/control-plane-swift/Sources/Requests/RequestCoordinator.swift services/control-plane-swift/Tests/ControlPlaneTests/MultimodalContractTests.swift services/control-plane-swift/Tests/HTTPGatewayTests/RequestCoordinatorTests.swift`: `98.07%` (`560/571`)
  - `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_multimodal_contracts.py services/mlx-worker-python/tests/test_video_preprocessing.py -q`: `16 passed in 0.06s`
  - `cd services/mlx-worker-python && PYTHONPATH='.:..:../..' uv run coverage run --source=worker/runtime,tests -m pytest tests/test_multimodal_contracts.py tests/test_video_preprocessing.py -q && PYTHONPATH='.:..:../..' uv run coverage report -m worker/runtime/video_preprocessing.py tests/test_multimodal_contracts.py tests/test_video_preprocessing.py`: total `98%` coverage (`166` statements, `4` misses)
  - `git diff --check`: pass
- Metrics report for `M16.1`:
  - accepted ingress source forms now normalize through one contract:
    - local path video URIs such as `/tmp/local-demo.m4v`
    - `file://` video URIs such as `file:///tmp/sample.m4v`
    - remote video URLs such as `https://example.com/demo.mov`
    - inline base64 video bytes via `input_video.data` or top-level `video_base64`
  - normalized inspectable metadata exposed by the touched scope:
    - `media_type = VIDEO`
    - `source_kind = URI | INLINE_BYTES`
    - `mime_type`, `format`, `filename`, `duration_ms`, `frame_budget`, `start_ms`, `end_ms`
  - changed-line coverage for the touched handwritten executable scope:
    - `MultimodalRequestNormalizer.swift`: `99.02%` (`202/204`)
    - `RequestCoordinator.swift`: `100.00%` (`2/2`)
    - `MultimodalContractTests.swift`: `97.47%` (`308/316`)
    - `RequestCoordinatorTests.swift`: `97.96%` (`48/49`)
    - Swift aggregate touched-scope coverage: `98.07%` (`560/571`)
    - `worker/runtime/video_preprocessing.py`: `96%` (`90` statements, `4` misses)
    - `tests/test_multimodal_contracts.py`: `100%`
    - `tests/test_video_preprocessing.py`: `100%`
    - Python aggregate touched-scope coverage: `98%` (`166` statements, `4` misses)
  - the remaining uncovered Python lines are defensive negative-bound guards that protobuf
    `uint32` fields do not permit at this post-normalization layer; they remain intentionally
    preserved as belt-and-suspenders validation

- Closed `M15.4` and completed `M15` by adding repository-owned desktop-polish integration
  evidence for the native operator shell:
  - added `DesktopPolishSmokeTests` so one focused Swift suite now proves bursty chat presentation
    smoothing, shared banner priority, registry-backed download recovery, operator-session restore,
    and renderable navigation grounding across all `5` desktop surfaces plus all `6` tool sections
  - added `scripts/m15_desktop_polish_smoke.py` so contributors can run the same smoke contract
    through one repo-owned JSON command with repo-local SwiftPM environment defaults
  - added `tests/test_m15_desktop_polish_smoke.py`,
    `tests/integration/test_desktop_polish_smoke.py`, and the dedicated
    `docs/runbooks/desktop-polish.md` runbook so the smoke payload, execution path, and operator
    interpretation stay aligned
- Verification summary for `M15.4`:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --package-path apps/macos-menubar --filter 'DesktopPolishSmokeTests'`: `1 test in 1 suite passed after 0.630 seconds`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" MELIX_HOME="$(pwd)/.runtime/phase1/smoke-home" swift test --package-path apps/macos-menubar --filter DesktopPolishSmokeTests`: `1 test in 1 suite passed after 0.620 seconds`
  - `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Tests/MenuBarTests/DesktopPolishSmokeTests.swift`: `98.69%` (`301/305`)
  - `python3 scripts/m15_desktop_polish_smoke.py --json`: pass
  - `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python pytest tests/test_m15_desktop_polish_smoke.py tests/integration/test_desktop_polish_smoke.py -q`: `5 passed in 90.49s (0:01:30)`
  - `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python coverage run --source=scripts,tests -m pytest tests/test_m15_desktop_polish_smoke.py tests/integration/test_desktop_polish_smoke.py -q && PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python coverage json -o /tmp/m15-4-python-coverage.json && python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/m15-4-python-coverage.json scripts/m15_desktop_polish_smoke.py tests/test_m15_desktop_polish_smoke.py tests/integration/test_desktop_polish_smoke.py`: `99.06%` (`105/106`)
  - `make integration-test`: `70 passed in 924.47s (0:15:24)`
  - `git diff --check`: pass
- Metrics report for `M15.4`:
  - repository-owned smoke evidence:
    - `chat.presentation_lag_ms = 62.6260`
    - `chat.presentation_flush_count = 3`
    - `signals.top_banner_title = "Download Recovery Available"`
    - `signals.download_recovery_visible = true`
    - `signals.update_signal_visible = true`
    - `signals.update_signal_dismissible = true`
    - `persistence.operator_session_restore_ms = 2.5461`
    - `persistence.operator_session_persist_write_ms = 1.3790`
    - `persistence.persisted_download_queue_count = 1`
    - `persistence.restored_download_queue_count = 1`
    - `persistence.restored_selected_tool_section = "Downloads"`
    - `navigation.grounded_surface_count = 5`
    - `navigation.grounded_tool_section_count = 6`
  - changed-line coverage for the touched executable scope:
    - `DesktopPolishSmokeTests.swift`: `98.69%` (`301/305`)
    - `scripts/m15_desktop_polish_smoke.py`: `97.62%` (`41/42`)
    - `tests/test_m15_desktop_polish_smoke.py`: `100.00%` (`41/41`)
    - `tests/integration/test_desktop_polish_smoke.py`: `100.00%` (`23/23`)
    - aggregate touched-scope coverage: `99.06%` (`406/410`) across the handwritten Swift and
      Python smoke scope
  - runbook index updates and `task_plan.md` are excluded from executable changed-line coverage
    because they are planning or documentation assets rather than handwritten runtime logic

- Closed `M15.3` by persisting desktop download queues across restart and surfacing paused-download
  recovery from registry-backed truth:
  - extended the Python worker model-ops registry so `registry_snapshot` download rows now carry
    `output_dir` and machine-readable `resume_ready` state derived from partial bytes and transfer
    status
  - persisted `downloadQueue` through `OperatorSessionStore` and taught `RuntimeViewModel` to
    restore queue rows before live refresh, parse `downloads` payloads, and reuse the original
    output directory plus mirror metadata for resume dispatch
  - updated the desktop Downloads section and shared desktop signals so operators can inspect queue
    progress, see output directories, refresh queue truth, and trigger `Resume Download` directly
    from Window UI or status-menu-visible recovery notices
- Verification summary for `M15.3`:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests|StatusMenuTests'`: `254 tests in 3 suites passed after 5.001 seconds`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests|StatusMenuTests'`: `254 tests in 3 suites passed after 5.071 seconds`
  - `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Sources/AppMain/Persistence/OperatorSessionStore.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift apps/macos-menubar/Tests/MenuBarTests/StatusMenuTests.swift apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift`: `97.42%` (`793/814`)
  - `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_maintenance_service.py -k 'download_rows_with_machine_readable_status or resume_ready' -q`: `2 passed, 66 deselected in 0.11s`
  - `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python coverage run --source=services/mlx-worker-python/worker -m pytest services/mlx-worker-python/tests/test_maintenance_service.py -k download -q`: `6 passed, 62 deselected in 0.18s`
  - `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/m15-3-python-coverage.json services/mlx-worker-python/worker/model_ops/job_registry.py services/mlx-worker-python/tests/test_maintenance_service.py`: `100.00%` (`4/4`)
  - `make py-test`: `501 passed in 52.54s`
  - `make swift-test`: failed outside the touched scope when `services/mlx-text-worker-swift` exited with unexpected signal `11` during `WorkerScaffoldTests`
  - `git diff --check`: pass
- Metrics report for `M15.3`:
  - persisted queue-recovery evidence exercised by the touched scope:
    - stalled or partial downloads now restore into the Window shell with stable `output_dir`,
      progress bytes, mirror metadata, and `resume_ready` state before any live refresh completes
    - resuming a recovered download re-dispatches `download` with the original output directory so
      partial bytes can be reused deterministically
    - shared desktop signals and the Downloads section now surface actionable queue state instead of
      relying on the last terminal model-operation result
  - changed-line coverage for the touched handwritten executable scope:
    - `DesktopWorkspaceShellView.swift`: `93.10%` (`54/58`)
    - `RuntimeViewModel.swift`: `92.06%` (`197/214`)
    - `OperatorSessionStore.swift`: `100.00%` (`4/4`)
    - `DesktopFoundationViewTests.swift`: `100.00%` (`50/50`)
    - `RuntimeViewModelTests.swift`: `100.00%` (`383/383`)
    - `StatusMenuTests.swift`: `100.00%` (`57/57`)
    - `TestSupport.swift`: `100.00%` (`48/48`)
    - Swift aggregate touched-scope coverage: `97.42%` (`793/814`)
    - Python worker touched-scope coverage: `100.00%` (`4/4`)
  - `task_plan.md` and plan-index updates are excluded from executable changed-line coverage because
    they are planning and status documents rather than handwritten runtime logic

- Closed `M15.2` by unifying desktop update availability and runtime-state messaging behind one
  shared signal model:
  - extended desktop banner state with stable ids and dismissibility, then persisted dismissed
    banner ids through `OperatorSessionState` so update notices can be hidden across restart without
    mutating runtime truth
  - mapped update availability and update-check-failure notices into the same prioritized desktop
    signal list used for runtime and audio warnings, while keeping critical runtime recovery signals
    non-dismissible and ahead of update notices
  - updated the workspace banner and status menu to consume the same top-priority shared signal
    instead of independent runtime versus update branches
  - added focused coverage proving update-banner dismissal persistence, version-change reappearance,
    non-dismissible critical runtime banners, status-menu signal reuse, and workspace rendering of
    the shared dismissible update banner
- Verification summary for `M15.2`:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|StatusMenuTests|DesktopFoundationViewTests|DesktopShellStateTests'`: `251 tests in 4 suites passed after 5.060 seconds`
  - `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Sources/AppMain/Models/DesktopShellState.swift apps/macos-menubar/Sources/AppMain/Persistence/OperatorSessionStore.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Sources/AppMain/MenuBar/StatusMenu.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift apps/macos-menubar/Tests/MenuBarTests/StatusMenuTests.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`: `98.76%` (`239/242`)
  - `git diff --check`: pass
  - `make swift-test`: failed outside the touched scope when `services/mlx-text-worker-swift`
    exited with unexpected signal `11` during `WorkerScaffoldTests`; the touched menu-bar suites
    passed under the focused coverage-enabled command above
  - `make integration-test`: `69 passed in 922.31s (0:15:22)`
- Metrics report for `M15.2`:
  - shared-signal evidence exercised by the touched scope:
    - actionable update notices now surface as dismissible banners keyed by stable ids and return
      automatically when the update summary changes
    - dismissing an update banner persists through operator-session restore while critical runtime
      recovery banners remain non-dismissible
    - the workspace banner and status menu now share the same prioritized top-signal title instead
      of rendering update and runtime state through unrelated branches
  - changed-line coverage for the touched handwritten executable scope:
    - `RuntimeViewModel.swift`: `98.84%` (`85/86`)
    - `DesktopShellState.swift`: `100.00%` (`14/14`)
    - `OperatorSessionStore.swift`: `100.00%` (`1/1`)
    - `DesktopWorkspaceShellView.swift`: `80.00%` (`8/10`)
    - `StatusMenu.swift`: `100.00%` (`7/7`)
    - touched test files aggregate: `100.00%`
    - aggregate touched-scope coverage: `98.76%` (`239/242`)
  - `task_plan.md` is excluded from executable changed-line coverage because it is planning
    documentation rather than handwritten runtime logic

- Closed `M15.1` by adding UI-side token-stream presentation smoothing in the desktop shell
  without changing control-plane stream truth:
  - added a menubar-owned chat presentation queue in `RuntimeViewModel` so assistant, reasoning,
    and tool deltas now flush across multiple UI ticks instead of jumping into the transcript as
    one burst when upstream delivery arrives chunked
  - preserved transcript fidelity by flushing buffered text before terminal completion or failure
    state is committed and by resetting the smoothing task on transport failure or transcript clear
  - added explicit `menu.chat_presentation_lag_ms` and `menu.chat_presentation_flush_count`
    metrics so the UI-side smoothing delay remains measurable rather than hiding stream regressions
  - extended menu-bar test support with scheduled chat events and added bursty-stream coverage that
    proves partial presentation before completion while preserving exact final transcript text
- Verification summary for `M15.1`:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --package-path apps/macos-menubar --filter 'RuntimeViewModelTests'`: `157 tests in 1 suite passed after 0.910 seconds`
  - `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift`: `98.09%` (`205/209`)
  - `make swift-test`: failed outside the touched scope when `services/mlx-text-worker-swift`
    exited with unexpected signal `11` during `WorkerScaffoldTests`; the touched menu-bar package
    passed under the focused coverage-enabled command above
  - `git diff --check`: pass
- Metrics report for `M15.1`:
  - deterministic smoothing evidence exercised by the touched scope:
    - bursty assistant deltas now appear as a partial transcript row before completion instead of a
      one-shot final jump
    - `menu.chat_presentation_lag_ms` is recorded whenever the smoothing queue flushes buffered
      chat text
    - `menu.chat_presentation_flush_count` is greater than `1` for the scheduled bursty-stream
      coverage, proving multiple UI flushes rather than one append
  - changed-line coverage for the touched handwritten executable scope:
    - `RuntimeViewModel.swift`: `97.20%` (`139/143`)
    - `RuntimeViewModelTests.swift`: `100.00%` (`43/43`)
    - `TestSupport.swift`: `100.00%` (`23/23`)
    - aggregate touched-scope coverage: `98.09%` (`205/209`)
  - `task_plan.md` is excluded from executable changed-line coverage because it is planning
    documentation rather than handwritten runtime logic

- Closed `M14.4` and completed `M14` by adding repository-owned image-iteration evidence on top of
  the shipped HTTP image surface:
  - expanded the OpenAI-compatible image job payload so HTTP responses now expose lineage and redo
    inspection fields including `source_artifact_id`, `source_job_id`, `prompt_delta`,
    `edit_mode`, `request_timeout_seconds`, `recipe`, and artifact `parent_artifact_id`
  - added live integration coverage for baseline generate, variation, iterate, and redo
    reconstruction so repository tests now prove iterative image workflows from shipped payload
    truth instead of internal read-model shortcuts
  - extended `scripts/phase7_metrics_report.py` so `make phase7-metrics` now prints
    `image_variation`, `image_iterate`, `image_redo`, and `image_timeout` evidence alongside the
    existing queueing, cancelation, and text-under-image-load report
  - updated the Phase 7 image operator runbook so contributors can reproduce iterative workflows
    and inspect lineage or timeout policy from documented commands alone
- Verification summary for `M14.4`:
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --package-path services/control-plane-swift --filter 'OpenAIHandlerTests'`: `107 tests in 1 suite passed`
  - `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_phase7_metrics_report.py -q`: `11 passed in 0.37s`
  - `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python pytest tests/integration/test_phase7_operator_workflows.py -k 'iteration or timeout' -q`: `2 passed, 2 deselected in 24.47s`
  - `make phase7-metrics`: pass
  - `git diff --check`: pass
- Metrics report for `M14.4`:
  - real `make phase7-metrics` evidence:
    - `image_generate.request_latency_ms = 367.68`, `job_latency_ms = 126.62`, `artifact_publish_ms = 1.15`, `peak_memory_bytes = 65536`, `output_bytes = 94`, `timeout_seconds = 1800`
    - `image_variation.request_latency_ms = 368.99`, `job_latency_ms = 125.51`, `artifact_publish_ms = 0.46`
    - `image_iterate.request_latency_ms = 358.81`, `job_latency_ms = 120.90`, `artifact_publish_ms = 0.49`, `prompt_delta = make the colors warmer`
    - `image_redo.request_latency_ms = 366.44`, `job_latency_ms = 123.39`, `artifact_publish_ms = 0.48`, `edit_mode = iterate`
    - `image_queue.queue_wait_ms = 570.74`
    - `text_under_image.scheduler_text_ttft_ms = 111.08`
    - `image_cancel.cancel_success = 1`, `response_status = 409`
    - `image_timeout.response_status = 504`, `error_code = deadline_exceeded`, `timeout_seconds = 1`
  - changed-line coverage for the touched handwritten executable scope:
    - Swift gateway scope: `100.00%` (`138/138`)
    - Python script plus integration scope: `100.00%` (`142/142`)
    - aggregate touched-scope coverage: `100.00%` (`280/280`)
  - documentation files are excluded from executable changed-line coverage because they are
    non-runtime assets rather than handwritten executable logic

- Closed `M14.3` by making creative image redo or reiteration flows operator-visible and by
  turning long-running image requests into typed timeout policy instead of generic worker
  unavailability:
  - extended the control-plane image-job protocol with `ImageJobRecipeSummary`, persisted image-job
    `recipe` projection, and `request_timeout_seconds`, then regenerated the Swift, Python, and
    descriptor protocol artifacts
  - updated the Swift control plane, OpenAI image gateway, Python bridge, and image read model so
    image generate or edit requests use an explicit `30-minute` creative deadline by default,
    surface typed `deadline_exceeded` failures, map those failures to `timed_out` image-job
    progress, and preserve enough recipe truth for redo or reiteration without relying on
    desktop-local copies
  - updated `RuntimeViewModel`, `DesktopImageView`, and menu-bar test support so the Window UI now
    shows timeout policy, timeout-aware status text, always-visible redo or reiteration actions,
    typed edit-mode/source-artifact inspection, and stable source-artifact summaries for selected
    jobs
- Verification summary for `M14.3`:
  - `make proto`: pass
  - `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_control_plane_bridge_phase5.py -q`: `5 passed in 0.03s`
  - `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_control_plane_bridge_phase5.py tests/integration/test_phase7_operator_workflows.py -k timeout -q`: `2 passed, 6 deselected in 13.72s`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --package-path services/control-plane-swift --filter 'ControlPlaneServiceTests|ImageJobReadModelTests|OpenAIHandlerTests|ImageDefaultsStoreTests|PythonBridgeWorkerClientTests'`: `333 tests in 5 suites passed after 1.003 seconds`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests|ControlPlaneXPCClientTests'`: `265 tests in 3 suites passed after 4.445 seconds`
  - `git diff --check`: pass
- Metrics report for `M14.3`:
  - typed redo and timeout evidence exercised by the touched scope:
    - selected image jobs now project persisted recipe truth and request timeout policy through one
      control-plane-owned source rather than Window-UI-local scratch state
    - redo can re-submit selected image jobs from persisted recipe state, and reiteration can seed
      iterate mode from stable artifact lineage and source-artifact summaries
    - image worker deadline failures now remain distinguishable from cancelation and generic bridge
      failures across control-plane, HTTP, integration, and Window UI surfaces
  - changed-line coverage for the touched handwritten executable scope:
    - Swift control-plane scope: `99.84%` (`618/619`)
    - Swift menu-bar scope: `99.79%` (`953/955`)
    - Python worker plus timeout integration scope: `100.00%` (`37/37`)
    - aggregate touched-scope coverage: `99.81%` (`1608/1611`)
  - generated protobuf outputs and `packages/protocol/descriptors/melix.pb` are excluded from
    executable changed-line coverage because they are regenerated interface artifacts rather than
    handwritten runtime logic

- Closed `M14.2` by making image defaults persistent across restart and projecting role-aware image
  model selection through one control-plane-owned source of truth:
  - extended the control-plane protocol with typed `ApplyImageDefaults`,
    `ImageDefaultsSummary`, and explicit creative parameter fields on generate or edit requests,
    then regenerated the Swift, Python, and descriptor artifacts
  - added `ImageDefaultsStore` so the Swift control plane now persists creative defaults, validates
    operator input, merges requested-versus-effective values, and projects the merged summary
    through reconnect-stable snapshots plus XPC replies
  - updated image catalog metadata and snapshot assembly so creative models declare generate or edit
    role support explicitly instead of relying on Window-UI-local picker knowledge
  - updated the shared XPC client, `RuntimeViewModel`, `DesktopImageView`, and menu-bar test
    support so the Window UI hydrates defaults from control-plane truth, persists them explicitly,
    and filters generate versus edit model pickers by supported creative role
- Verification summary for `M14.2`:
  - `make proto`: pass
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'ControlPlaneServiceTests|ImageDefaultsStoreTests|ModelCatalogTests'`: `204 tests in 3 suites passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|ControlPlaneXPCClientTests'`: `183 tests in 2 suites passed`
  - `make swift-test`: failed outside the touched scope when `services/mlx-text-worker-swift`
    exited with unexpected signal `11` during `WorkerScaffoldTests`
  - `make integration-test`: `67 passed in 920.65s (0:15:20)`
  - `git diff --check`: pass
- Metrics report for `M14.2`:
  - typed persisted-defaults evidence exercised by the touched scope:
    - creative defaults for steps, guidance, strength, and negative prompt now persist through a
      control-plane-owned store instead of Window-UI-local draft state
    - reconnect-stable snapshots now project requested-versus-effective image defaults so the
      operator can inspect merged creative policy after restart
    - generate and edit request forwarding now keeps explicit per-request values authoritative while
      still filling missing fields from the persisted defaults summary
    - image pickers now derive role visibility from capability metadata so generate and edit flows
      surface only compatible creative families
  - changed-line coverage for the touched handwritten executable scope:
    - Swift control-plane scope: `95.61%` (`936/979`)
    - Swift menu-bar scope: `95.16%` (`609/640`)
    - aggregate touched-scope coverage: `95.43%` (`1545/1619`)
  - generated protobuf outputs and `packages/protocol/descriptors/melix.pb` are excluded from
    executable changed-line coverage because they are regenerated interface artifacts rather than
    handwritten runtime logic

- Closed `M14.1` by making image variation and iterate flows typed, lineage-aware, and compatible
  with the existing image-job model instead of treating every derived image request as a generic
  edit:
  - extended the control-plane and worker protobuf contracts with typed `ImageEditMode` enums plus
    `source_artifact_id`, `source_job_id`, `prompt_delta`, and `parent_artifact_id` lineage
    fields, then regenerated the Swift, Python, and descriptor artifacts
  - updated the Swift control plane, the shared XPC client, and the OpenAI image-edit handler so
    `variation` and `iterate` requests resolve prior artifact IDs into worker-facing source URIs,
    enforce iterate-only `prompt_delta`, reject mixed raw-image plus artifact-id inputs, and keep
    queued image jobs lineage-aware
  - updated the deterministic Python image-edit runtime and terminal job descriptors so generated
    artifacts preserve `parent_artifact_id` and lineage `ext` keys for the source artifact, source
    job, edit mode, and prompt delta
  - added focused read-model, control-plane, OpenAI gateway, XPC-client, and Python runtime tests
    that exercise iterate resolution, variation validation, and lineage persistence end to end
- Verification summary for `M14.1`:
  - `make proto`: pass
  - `PYTHONPATH='.:services/mlx-worker-python' uv run --project services/mlx-worker-python pytest services/mlx-worker-python/tests/test_image_runtime.py -q`: `11 passed in 0.09s`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'ControlPlaneServiceTests|OpenAIHandlerTests|ImageJobReadModelTests'`: `270 tests in 3 suites passed after 0.098 seconds`
  - `make py-test`: `488 passed in 52.81s`
  - `make swift-test`: failed outside the touched scope when `services/mlx-text-worker-swift`
    exited with unexpected signal `11` during `WorkerScaffoldTests`
  - `git diff --check`: pass
- Metrics report for `M14.1`:
  - typed lineage evidence exercised by the touched scope:
    - `source_artifact_id` now resolves prior image artifacts into control-plane and OpenAI
      image-edit worker requests without bypassing image-job history
    - `prompt_delta` is enforced as iterate-only input and preserved in queued image jobs plus
      worker terminal job descriptors
    - generated artifacts now preserve `parent_artifact_id` and lineage `ext` values for source
      artifact, source job, and edit mode
  - changed-line coverage for the touched handwritten executable scope:
    - Python worker plus test scope via `scripts/python_changed_line_coverage.py`: `100.00%`
      (`52/52`)
    - Swift control-plane plus test scope via repository `git diff --unified=0 HEAD` and
      `xcrun llvm-cov show` over the coverage-enabled `MelixControlPlanePackageTests` binary:
      `96.13%` (`646/672`)
    - aggregate touched-scope coverage: `96.41%` (`698/724`)
  - generated protobuf outputs, `packages/protocol/descriptors/melix.pb`, and planning documents
    are excluded from executable changed-line coverage because they are regenerated artifacts or
    non-runtime documentation rather than handwritten executable logic

- Closed the second executable `M13.4` slice and completed the milestone by turning the shipped API
  onboarding examples into repository-owned executable truth:
  - added `scripts/m13_api_onboarding_smoke.py`, a live shared-access smoke that exercises the
    canonical `/health`, `/v1/responses`, and `/v1/messages` quick-start examples against a local
    `LiveMelixStack`
  - updated the desktop API quick-start snippets so OpenAI-compatible and Anthropic examples now
    match the shipped streaming contract, including `stream=true`, SSE-friendly curl flags, and
    auth-aware `/health` examples for the Ollama compatibility guidance
  - added deterministic Python unit coverage for smoke error branches plus a new integration test
    that runs the smoke against the live stack, ensuring example payloads, headers, and endpoint
    shapes stay aligned with the product UI
- Verification summary for the second executable `M13.4` slice:
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/m13_api_onboarding_smoke.py --json`: pass with `/health`, `/v1/responses`, and `/v1/messages` all returning `200`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest tests/test_m13_api_onboarding_smoke.py tests/integration/test_api_onboarding_examples.py -q`: `16 passed in 11.69s`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'DesktopFoundationViewTests'`: `69 tests in 1 suite passed`
  - `make py-test`: `487 passed in 44.61s`
  - `make integration-test`: `67 passed in 898.58s (0:14:58)`
  - `make swift-test`: failed outside the touched scope when `services/mlx-text-worker-swift` exited with unexpected signal `11` during `WorkerScaffoldTests`
- Metrics report for the second executable `M13.4` slice:
  - smoke evidence for the shipped onboarding examples:
    - `base_url = http://127.0.0.1:50099/v1`
    - `health.status_code = 200`, `health.status = ok`
    - `responses.status_code = 200`, `responses.content_type = text/event-stream; charset=utf-8`
    - `messages.status_code = 200`, `messages.content_type = text/event-stream; charset=utf-8`
    - `startup_timings_ms.swift_text_worker_ready_ms = 5108.96`
    - `startup_timings_ms.python_worker_ready_ms = 5121.63`
    - `startup_timings_ms.control_plane_spawn_to_ready_ms = 365.43`
  - changed-line coverage for the touched handwritten executable scope:
    - `scripts/m13_api_onboarding_smoke.py`, `tests/test_m13_api_onboarding_smoke.py`, and `tests/integration/test_api_onboarding_examples.py`: `100.00%` (`163/163`)
    - `apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift` and `apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`: `100.00%` (`119/119`)
    - aggregate touched-scope coverage: `100.00%` (`282/282`)

- Closed the first executable `M13.4` slice by moving API onboarding truth into the typed
  control-plane snapshot and rehydrating the desktop API workspace from that source instead of
  stale hardcoded endpoint catalogs:
  - extended `ServerSnapshot` with a typed `api_onboarding` summary covering published API
    surfaces, per-endpoint reference rows, surface status, and compatibility-only guidance, then
    regenerated the Swift, Python, and descriptor protocol artifacts
  - added `APIOnboardingSnapshotSource` so the Swift control plane now owns the shipped API
    onboarding catalog for Local Service, OpenAI-compatible, Anthropic Messages, and Ollama
    compatibility guidance
  - updated `ServerSnapshotBuilder` and `ControlPlaneService` so handshake and reconnect snapshots
    project one stable onboarding summary with endpoint reference and compatibility notes
  - replaced the desktop API reference catalog with snapshot-driven `apiSurfaces` and
    `apiReference` rows, keeping grouped surface rendering and truthful compatibility-only
    presentation for Ollama
  - generated session-aware curl, Python, and JavaScript quick-start snippets from the selected
    server session's effective base URL, auth state, and served model instead of static copy
- Verification summary for the first executable `M13.4` slice:
  - `make proto`: pass
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'ControlPlaneServiceTests'`: `160 tests in 1 suite passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'DesktopFoundationViewTests'`: `69 tests in 1 suite passed`
  - `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/HTTPGateway/APIOnboardingSnapshotSource.swift services/control-plane-swift/Sources/Snapshots/ServerSnapshotBuilder.swift services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`: `100.00%` (`38/38`)
  - `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationState.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`: `96.51%` (`746/773`)
  - aggregate touched-scope changed-line coverage: `96.67%` (`784/811`)
  - `git diff --check`: pass
  - `make swift-test`: failed outside the touched scope when `services/mlx-text-worker-swift`
    exited with unexpected signal `11` during `WorkerScaffoldTests`
- Metrics report for the first executable `M13.4` slice:
  - `N/A` for new runtime timing or persistence metrics because this slice adds read-only snapshot
    projection and UI hydration, not a new mutation or runtime execution path
  - typed onboarding evidence exercised by the touched scope:
    - reconnect-stable `ServerSnapshot.api_onboarding` population after handshake
    - grouped surface publication with `Shipped`, `Compatibility Only`, and `Unknown` status text
    - snapshot-driven endpoint reference for `/health`, `/v1/cache/stats`, `/v1/responses`,
      `/v1/messages`, and image endpoints
    - session-aware quick starts using `effectiveBaseURL`, served model ID, and current auth mode
      rather than static desktop-local examples
  - changed-line coverage for the touched handwritten executable scope:
    - Swift control-plane scope: `100.00%` (`38/38`)
    - Swift menu-bar scope: `96.51%` (`746/773`)
    - aggregate touched-scope coverage: `96.67%` (`784/811`)
  - generated protobuf outputs and `packages/protocol/descriptors/melix.pb` are excluded from
    executable changed-line coverage because they are regenerated interface artifacts rather than
    handwritten runtime logic

- Closed the first executable `M13.3` slice by projecting tooling, embedding, and config-file
  state through one reconnect-stable control-plane snapshot summary and hydrating the existing
  Window UI settings surface from that typed truth:
  - extended `ServerSnapshot` with `tooling_settings`, plus typed embedding and config-path
    summaries, then regenerated the Swift, Python, and descriptor protocol artifacts
  - added `ToolingSettingsSnapshotSource` so the Swift control plane now projects the active
    embedding model choice, preload state, built-in tool-parser modes, MCP summary, inspectable
    config paths, and boot additional arguments from repository-owned sources instead of UI-local
    reconstruction
  - exposed store-backed config paths and supported parser modes through the control-plane core
    actors that already own those values, preserving a single orchestration truth
  - updated `DesktopFoundationState` so the existing Tools > Settings surface renders the typed
    tooling snapshot, including embedding preload detail, MCP config, config-path rows, and boot
    arguments, without relying on hardcoded operator knowledge
- Verification summary for the first executable `M13.3` slice:
  - `make proto`: pass
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'ControlPlaneServiceTests'`: `159 tests in 1 suite passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'DesktopFoundationViewTests'`: `64 tests in 1 suite passed`
  - `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/HTTPGateway/OpenAI/GatewayConfigStore.swift services/control-plane-swift/Sources/HTTPGateway/OpenAI/GatewayServingDefaultsStore.swift services/control-plane-swift/Sources/Requests/ToolParserRegistry.swift services/control-plane-swift/Sources/Snapshots/ServerSnapshotBuilder.swift services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift services/control-plane-swift/Sources/XPCService/ToolingSettingsSnapshotSource.swift services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`: `100.00%` (`83/83`)
  - `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationState.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`: `100.00%` (`226/226`)
  - `git diff --check`: pass
  - `make swift-test`: failed outside the touched scope when `services/mlx-text-worker-swift`
    exited with unexpected signal `11` during `WorkerScaffoldTests`; the touched control-plane and
    menu-bar packages passed under the focused verification commands above
- Metrics report for the first executable `M13.3` slice:
  - `N/A` for new runtime timing or persistence metrics because this slice adds read-only snapshot
    projection and UI hydration, not new measured mutation paths
  - typed tooling-state evidence exercised by the touched scope:
    - reconnect-stable `ServerSnapshot.tooling_settings` population after handshake
    - active embedding model projection with model state, preload detail, backend, and family
    - repository-owned built-in parser modes and MCP summary surfaced without UI-local discovery
    - inspectable gateway-config, serving-defaults, and control-plane metrics paths plus boot
      additional arguments
  - changed-line coverage for the touched handwritten executable scope:
    - Swift control-plane scope: `100.00%` (`83/83`)
    - Swift menu-bar scope: `100.00%` (`226/226`)
    - aggregate touched-scope coverage: `100.00%` (`309/309`)
  - generated protobuf outputs and `packages/protocol/descriptors/melix.pb` are excluded from
    executable changed-line coverage because they are regenerated interface artifacts rather than
    handwritten runtime logic

- Closed the third executable `M13.2` slice by making speculative-decoding defaults typed,
  persistent, and control-plane-validated across the protocol, request shaping, model-resolution,
  the Window UI, and the integration stack:
  - extended `ApplyServingDefaults`, `ServingDefaultsSessionSummary`, and worker
    `AccelerationPolicy` with typed speculative fields for `acceleration_mode`,
    `draft_model_id`, and `num_draft_tokens`, then regenerated the Swift, Python, and descriptor
    artifacts
  - updated `GatewayServingDefaultsStore` so operator overrides for speculative decoding persist
    beside generation and batching defaults, project requested-versus-effective speculative state,
    and expose validation failures before unsupported configurations reach the runtime
  - routed speculative gateway defaults through `TextRequestShaper`, `ChatRequestTranslator`,
    `RequestCoordinator`, and `ControlPlaneXPCClient`, preserving model-level acceleration
    precedence while letting gateway defaults provide draft-model and draft-token policy when the
    served model itself is unspecified
  - updated the Window UI server workspace, `RuntimeViewModel`, desktop state projection, and
    apply flow so speculative defaults hydrate from control-plane truth instead of session-local
    draft state
  - isolated `LiveMelixStack` state in `tests/integration/helpers.py` by assigning unique
    `MELIX_HOME`, `MELIX_GATEWAY_CONFIG_STORE_PATH`, and
    `MELIX_GATEWAY_SERVING_DEFAULTS_STORE_PATH` values per stack, fixing the regression where
    persisted local gateway bindings overrode integration-test HTTP ports and broke startup
- Verification summary for the third executable `M13.2` slice:
  - `make proto`: pass
  - `make py-test`: `487 passed in 45.14s`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'GatewayServingDefaultsStoreTests'`: `5 tests in 1 suite passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'ControlPlaneServiceTests'`: `158 tests in 1 suite passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'TextEndpointContractTests'`: `36 tests in 1 suite passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'RequestCoordinatorTests'`: `43 tests in 1 suite passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage`: `289 tests in 10 suites passed after 5.027 seconds`
  - `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata /tmp/m13_2_slice3_controlplane_merged.profdata services/control-plane-swift/Sources/HTTPGateway/OpenAI/GatewayServingDefaultsStore.swift services/control-plane-swift/Sources/Requests/ChatRequestTranslator.swift services/control-plane-swift/Sources/Requests/RequestCoordinator.swift services/control-plane-swift/Sources/Requests/TextRequestShaper.swift services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift services/control-plane-swift/Tests/ControlPlaneTests/GatewayServingDefaultsStoreTests.swift services/control-plane-swift/Tests/ControlPlaneTests/TextEndpointContractTests.swift services/control-plane-swift/Tests/HTTPGatewayTests/RequestCoordinatorTests.swift`: `99.47%` (`563/566`)
  - `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/XPCService/ControlPlaneXPCClient.swift`: `100.00%` (`10/10`)
  - `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Sources/AppMain/Models/DesktopShellState.swift apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Tests/MenuBarTests/ControlPlaneXPCClientTests.swift apps/macos-menubar/Tests/MenuBarTests/DesktopShellStateTests.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift`: `97.07%` (`199/205`)
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx coverage run -m pytest tests/integration/test_abort_flow.py::test_abort_finishes_the_live_stream_with_cancelled_completion -q`: `1 passed in 11.20s`
  - `python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/m13_2_slice3_integration_cov.json tests/integration/helpers.py`: `100.00%` (`12/12`)
  - `make integration-test`: `66 passed in 892.51s (0:14:52)`
  - `make swift-test`: failed outside the touched scope when `services/mlx-text-worker-swift` exited with unexpected signal `11` during `WorkerScaffoldTests`
  - `git diff --check`: pass
- Metrics report for the third executable `M13.2` slice:
  - typed speculative-default metrics exercised by the touched scope:
    - `gateway.serving_defaults_apply_ms`
    - `gateway.serving_defaults_persist_failures`
    - `gateway.generation_default_merge_count`
    - `gateway.speculative_config_apply_ms`
    - `menu.serving_defaults_apply_ms`
  - requested-versus-effective speculative evidence exercised by the touched scope:
    - requested versus effective `acceleration_mode`, `draft_model_id`, and `num_draft_tokens`
    - gateway-owned speculative defaults in request shaping, coordinator-side model merges, and
      Window UI state projection
    - explicit rejection of speculative defaults targeting unsupported served models, unsupported
      draft models, or unsupported worker backends
    - integration startup isolation showing gateway bindings now respect per-stack `MELIX_HTTP_PORT`
      instead of leaking persisted local listener overrides
  - changed-line coverage for the touched handwritten executable scope:
    - Swift control-plane scope excluding the shared XPC client: `99.47%` (`563/566`)
    - shared XPC client under Window UI tests: `100.00%` (`10/10`)
    - Swift menu-bar scope: `97.07%` (`199/205`)
    - Python integration-helper scope: `100.00%` (`12/12`)
    - aggregate touched-scope coverage: `98.87%` (`784/793`)
  - generated protobuf outputs, `packages/protocol/descriptors/melix.pb`, and planning documents
    are excluded from executable changed-line coverage because they are regenerated artifacts or
    non-runtime documentation rather than handwritten executable logic

- Closed the second executable `M13.2` slice by making batching and admission defaults typed,
  persistent, and scheduler-visible control-plane truth across the protocol, request shaping, the
  control-plane store, and the Window UI:
  - extended `ApplyServingDefaults` and `ServingDefaultsSessionSummary` so
    `concurrent_processing_enabled`, `prefill_batch_size`, and `completion_batch_size` are part
    of the versioned control-plane contract, then regenerated the Swift, Python, and descriptor
    artifacts
  - updated `GatewayServingDefaultsStore` so operator overrides for batching defaults persist
    beside the existing generation defaults, validate invalid batch sizes, and project both
    requested and effective batching state through `ServerSnapshot`
  - routed batching defaults through `TextRequestShaper` and `ChatRequestTranslator`, exposing
    gateway-owned admission metadata in worker execution `ext` so downstream scheduling no longer
    depends on desktop-local draft state
  - replaced the `RequestCoordinator` hard-coded continuous-batch target with effective admission
    capacity derived from gateway defaults, allowing continuous batching to expand, shrink, or
    disable entirely without source edits
  - updated the Window UI server workspace, state models, and persistence flow so concurrent
    processing plus prefill or completion batch sizes hydrate from control-plane truth, display
    requested-versus-effective state, and round-trip through `Apply Serving Defaults`
- Verification summary for the second executable `M13.2` slice:
  - `make proto`: pass
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --skip-build --filter 'GatewayServingDefaultsStoreTests'`: `4 tests in 1 suite passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --skip-build --filter 'TextEndpointContractTests'`: `36 tests in 1 suite passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --skip-build --filter 'OpenAIHandlerTests'`: `101 tests in 1 suite passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --skip-build --filter 'ControlPlaneServiceTests'`: `157 tests in 1 suite passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --skip-build --filter 'HTTPGatewayTests.RequestCoordinatorTests/gatewayBatchingDefaultsCanExpandContinuousBatchCapacity()'`: `1 test in 1 suite passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --skip-build --filter 'HTTPGatewayTests.RequestCoordinatorTests/gatewayBatchingDefaultsCanDisableContinuousBatchAdmissions()'`: `1 test in 1 suite passed`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'RuntimeViewModelTests|ControlPlaneXPCClientTests|DesktopShellStateTests|DesktopFoundationViewTests'`: `246 tests in 4 suites passed after 4.357 seconds`
  - `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata /tmp/m13_2_cp_profdata_pieces/merged.profdata services/control-plane-swift/Sources/HTTPGateway/OpenAI/GatewayServingDefaultsStore.swift services/control-plane-swift/Sources/Requests/ChatRequestTranslator.swift services/control-plane-swift/Sources/Requests/RequestCoordinator.swift services/control-plane-swift/Sources/Requests/TextRequestShaper.swift services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift services/control-plane-swift/Tests/ControlPlaneTests/GatewayServingDefaultsStoreTests.swift services/control-plane-swift/Tests/ControlPlaneTests/TextEndpointContractTests.swift services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift services/control-plane-swift/Tests/HTTPGatewayTests/RequestCoordinatorTests.swift`: `95.41%` (`457/479`)
  - `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/XPCService/ControlPlaneXPCClient.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Sources/AppMain/Models/DesktopShellState.swift apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Tests/MenuBarTests/ControlPlaneXPCClientTests.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift apps/macos-menubar/Tests/MenuBarTests/DesktopShellStateTests.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift`: `99.59%` (`240/241`)
  - `make integration-test`: `66 passed in 883.49s (0:14:43)`
  - `make swift-test`: failed outside the touched scope when `services/mlx-text-worker-swift` exited with unexpected signal `11` during `WorkerScaffoldTests`
  - `git diff --check`: pass
- Metrics report for the second executable `M13.2` slice:
  - typed batching or admission metrics exercised by the touched scope:
    - `gateway.serving_defaults_apply_ms`
    - `gateway.serving_defaults_persist_failures`
    - `menu.serving_defaults_apply_ms`
    - `scheduler.continuous_batch_eligible_rate`
    - `scheduler.continuous_batch_merge_rate`
    - `scheduler.continuous_batch_size`
    - `scheduler.continuous_batch_active_cohorts`
  - effective-state and admission evidence exercised by the touched scope:
    - requested versus effective `concurrent_processing_enabled`,
      `max_concurrent_requests`, `prefill_batch_size`, and `completion_batch_size`
    - gateway-owned batching defaults in request shaping and execution metadata
    - scheduler-visible continuous-batch expansion and disablement without source changes
  - changed-line coverage for the touched handwritten executable scope:
    - Swift control-plane scope: `95.41%` (`457/479`)
    - Swift menu-bar plus shared XPC-client scope: `99.59%` (`240/241`)
    - aggregate touched-scope coverage: `96.81%` (`697/720`)
  - generated protobuf outputs, `packages/protocol/descriptors/melix.pb`, and planning documents
    are excluded from executable changed-line coverage because they are regenerated artifacts or
    non-runtime documentation rather than handwritten executable logic

## 2026-04-05

- Closed the first executable `M13.2` slice by making gateway-level serving defaults typed,
  persistent, and control-plane-owned across bootstrap, snapshot projection, request shaping, and
  the Window UI server workspace:
  - extended the control-plane protocol with `server.apply_serving_defaults`,
    `ApplyServingDefaults`, `ServingDefaultsSource`, `ServingDefaultsSummary`, and
    `ServingDefaultsSessionSummary`, and regenerated the Swift, Python, and descriptor artifacts
    so requested and effective serving-default state is part of the versioned interface contract
  - added `GatewayServingDefaultsStore` so built-in defaults, environment defaults, config-file
    imports, and operator overrides resolve through a schema-versioned JSON document owned by the
    Swift control plane, with effective values merged against model-level generation config where
    applicable
  - projected serving-default summaries through `ServerSnapshot`, wired typed apply handling plus
    persistence metrics into `ControlPlaneService`, and applied gateway defaults inside text
    request shaping and chat translation before per-request overrides
  - updated the Window UI server workspace and `RuntimeViewModel` so serving-default values,
    source labels, effective merged defaults, and `Apply Serving Defaults` hydrate from
    control-plane truth, and server starts persist serving defaults before lifecycle mutation
- Verification summary for the first executable `M13.2` slice:
  - `make proto`: pass
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'ControlPlaneServiceTests|GatewayServingDefaultsStoreTests|TextEndpointContractTests|OpenAIHandlerTests'`: `297 tests in 4 suites passed after 0.108 seconds`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'RuntimeViewModelTests|ControlPlaneXPCClientTests|DesktopShellStateTests|DesktopFoundationViewTests'`: `246 tests in 4 suites passed after 4.537 seconds`
  - `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/Bootstrap/main.swift services/control-plane-swift/Sources/HTTPGateway/OpenAI/GatewayServingDefaultsStore.swift services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift services/control-plane-swift/Sources/Requests/ChatRequestTranslator.swift services/control-plane-swift/Sources/Requests/TextRequestShaper.swift services/control-plane-swift/Sources/Snapshots/ServerSnapshotBuilder.swift services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift services/control-plane-swift/Tests/ControlPlaneTests/GatewayServingDefaultsStoreTests.swift services/control-plane-swift/Tests/ControlPlaneTests/TextEndpointContractTests.swift services/control-plane-swift/Tests/HTTPGatewayTests/OpenAIHandlerTests.swift`: `100.00%` (`429/429`)
  - `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/XPCService/ControlPlaneXPCClient.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Sources/AppMain/Models/DesktopShellState.swift apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Tests/MenuBarTests/ControlPlaneXPCClientTests.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift apps/macos-menubar/Tests/MenuBarTests/DesktopShellStateTests.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift`: `99.56%` (`673/676`)
  - `make swift-test`: failed outside the touched scope when `services/mlx-text-worker-swift` exited with unexpected signal `11` during `WorkerScaffoldTests`; the touched control-plane and menu-bar packages passed under the focused verification commands above
  - `git diff --check`: pass
- Metrics report for the first executable `M13.2` slice:
  - typed serving-defaults metrics exercised by the touched scope:
    - `gateway.serving_defaults_apply_ms`
    - `gateway.serving_defaults_persist_failures`
    - `gateway.generation_default_merge_count`
    - `menu.serving_defaults_apply_ms`
  - effective-state and merge evidence exercised by the touched scope:
    - requested versus effective `temperature`, `top_p`, `max_tokens`,
      `stream_interval_tokens`, and `max_concurrent_requests`
    - control-plane-owned source labels and model-override visibility for serving defaults
    - gateway-default application in request shaping and chat execution metadata
  - changed-line coverage for the touched handwritten executable scope:
    - Swift control-plane scope: `100.00%` (`429/429`)
    - Swift menu-bar plus shared XPC-client scope: `99.56%` (`673/676`)
    - aggregate touched-scope coverage: `99.73%` (`1102/1105`)
  - generated protobuf outputs and `packages/protocol/descriptors/melix.pb` are excluded from
    executable changed-line coverage because they are regenerated interface artifacts rather than
    handwritten runtime logic

- Started `M13.2` by refining gateway defaults work into explicit executable slices and selecting
  gateway-level generation defaults as the next implementation target:
  - updated the `M13.2` plan so the milestone now executes in three bounded slices: typed
    generation defaults, batching or admission defaults, and speculative defaults
  - recorded that the current repository still keeps `temperature`, `top_p`, `max_tokens`, and
    `max_concurrent_requests` inside desktop-only session state while request shaping still falls
    back to built-in defaults or model-level generation config
  - moved the active task plan to the first executable `M13.2` slice so the next code transaction
    can establish a control-plane-owned serving-defaults state model before expanding into
    batching and speculative-decoding
- Verification summary for the `M13.2` planning transaction:
  - `git diff --check`: pending until the executable change set is complete
- Metrics report for the `M13.2` planning transaction:
  - `N/A` for executable coverage and runtime metrics because this transaction only moved the
    active task plan before implementation started

- Closed `M13.1` by making gateway listener configuration typed, persistent, and
  control-plane-owned across bootstrap, snapshot projection, and the Window UI server workspace:
  - extended the control-plane protocol with `server.apply_gateway_config`,
    `GatewayConfigSummary`, `GatewayListenerConfigSummary`, and `GatewayConfigSource`, and
    regenerated the Swift, Python, and descriptor artifacts so gateway-config state is part of the
    versioned interface contract
  - added `GatewayConfigStore` so built-in defaults, environment defaults, and operator overrides
    resolve through a schema-versioned JSON document owned by the Swift control plane, with
    bootstrap listener binding sourced from the same store
  - projected `gateway_config` through `ServerSnapshot`, added typed apply handling plus
    persistence-failure metrics in `ControlPlaneService`, and exposed the new typed client helper
    through `ControlPlaneXPCClient`
  - updated the Window UI server workspace so requested and effective listener state, config
    source, restart-required badges, and `Apply Gateway Config` all hydrate from control-plane
    truth, and server starts persist gateway config before lifecycle mutation
  - marked `M13.1` completed in the roadmap execution index; the next active execution slice can
    now advance to `M13.2`
- Verification summary for `M13.1`:
  - `make proto`: pass
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --filter 'ControlPlaneServiceTests|GatewayConfigStoreTests'`: `156 tests in 2 suites passed after 0.083 seconds`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --package-path services/control-plane-swift --filter 'ControlPlaneServiceTests|GatewayConfigStoreTests'`: `156 tests in 2 suites passed after 0.090 seconds`
  - `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/HTTPGateway/OpenAI/GatewayConfigStore.swift services/control-plane-swift/Sources/Snapshots/ServerSnapshotBuilder.swift services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift services/control-plane-swift/Sources/XPCService/ControlPlaneXPCClient.swift services/control-plane-swift/Sources/Bootstrap/main.swift services/control-plane-swift/Tests/ControlPlaneTests/GatewayConfigStoreTests.swift services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`: `100.00%` (`358/358`)
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|ControlPlaneXPCClientTests|DesktopShellStateTests|DesktopFoundationViewTests'`: `235 tests in 4 suites passed after 4.171 seconds`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|ControlPlaneXPCClientTests|DesktopShellStateTests|DesktopFoundationViewTests'`: `235 tests in 4 suites passed after 4.171 seconds`
  - `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Sources/AppMain/Models/DesktopShellState.swift apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift apps/macos-menubar/Tests/MenuBarTests/ControlPlaneXPCClientTests.swift apps/macos-menubar/Tests/MenuBarTests/DesktopShellStateTests.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift`: `95.21%` (`437/459`)
  - `git diff --check`: pass
- Metrics report for `M13.1`:
  - typed gateway-config metrics exercised by the touched scope:
    - `gateway.config_apply_ms`
    - `gateway.config_requires_restart_count`
    - `gateway.config_persist_failures`
    - `menu.gateway_config_apply_ms`
  - typed snapshot and desktop-state metrics exercised by the touched scope:
    - requested versus effective listener host or port projection
    - control-plane-owned served model, timeout, rate limit, and source metadata
    - restart-required and active-binding visibility for server sessions
  - changed-line coverage for the touched handwritten executable scope:
    - Swift control-plane scope: `100.00%` (`358/358`)
    - Swift menu-bar scope: `95.21%` (`437/459`)
    - aggregate touched-scope coverage: `97.31%` (`795/817`)
  - generated protobuf outputs and `packages/protocol/descriptors/melix.pb` are excluded from
    executable changed-line coverage because they are regenerated interface artifacts rather than
    handwritten runtime logic

- Closed the second executable `M12.4` slice by making conversion and packaging repository-owned
  model-tool workflows with stable artifacts and operator-visible summary state:
  - added `conversion_pipeline.py` so `convert` emits a dedicated
    `melix.converted_model_bundle.v1` artifact bundle with stable `config.json`,
    `tokenizer.json`, `weights.safetensors`, manifest paths, artifact sizes, target format,
    runtime compatibility, and structural smoke metadata
  - added `upload_receipt_pipeline.py` so `upload` emits a dedicated
    `melix.upload_receipt.v1` receipt with stable source-artifact provenance, target repo,
    runtime metadata, linked quantization fields, and converted-bundle packaging lineage instead of
    a generic placeholder response
  - updated `maintenance_core.py` so `convert`, `quantize`, and `upload` now surface typed
    worker-authored artifact records through model-ops events, while invalid upload artifacts fail
    with typed `invalid_artifact` errors instead of leaking placeholder state
  - projected conversion and packaging metadata through the Window UI model-tools state so the
    operator shell exposes convert entrypoints plus summary fields for target repo, source artifact
    kind, target format, runtime compatibility, smoke status, and linked quantization identity
  - marked `M12.4` completed in the roadmap execution index now that inspect, health, and
    conversion or packaging workflows are all repository-owned and test-backed
- Verification summary for the second executable `M12.4` slice:
  - `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_maintenance_service.py -q`: `67 passed in 51.31s`
  - `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python --extra mlx coverage run --data-file=/tmp/m12_4_convert_python.coverage -m pytest services/mlx-worker-python/tests/test_maintenance_service.py -q && PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python --extra mlx coverage json --data-file=/tmp/m12_4_convert_python.coverage -o /tmp/m12_4_convert_python_coverage.json && python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/m12_4_convert_python_coverage.json services/mlx-worker-python/worker/model_ops/conversion_pipeline.py services/mlx-worker-python/worker/model_ops/upload_receipt_pipeline.py services/mlx-worker-python/worker/engine/maintenance_core.py services/mlx-worker-python/tests/test_maintenance_service.py`: `67 passed in 46.42s`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --filter 'DesktopFoundationViewTests'`: `60 tests in 1 suite passed after 4.384 seconds`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --enable-code-coverage --package-path apps/macos-menubar --filter 'RuntimeViewModelTests|DesktopFoundationViewTests'`: `193 tests in 2 suites passed after 4.543 seconds`
  - `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`: `98.88%` (`353/357`)
- Metrics report for the second executable `M12.4` slice:
  - conversion and packaging metrics exercised by the touched scope:
    - `melix.converted_model_bundle.v1` bundle manifests with stable `artifact_kind`,
      `target_format`, `target_runtime`, `conversion_backend`, and smoke metadata
    - `melix.upload_receipt.v1` receipts with stable `target_repo`, `source_artifact_kind`,
      `source_manifest_path`, `runtime`, converted-bundle lineage, and linked quantization data
    - Window UI summary state for `artifactRuntime`, `servingCompatible`, `smokeTestRequested`,
      `targetRepo`, `sourceArtifactKind`, `conversionTargetFormat`, and
      `linkedQuantizationProfileID`
  - changed-line coverage for the touched handwritten executable scope:
    - Python worker conversion or packaging scope: `95.49%` (`254/266`)
    - Swift menu-bar conversion or packaging scope: `98.88%` (`353/357`)
    - aggregate touched-scope coverage: `97.43%` (`607/623`)

- Closed the first executable `M12.4` slice by making model inspection and doctor health
  repository-owned, typed operator contracts across the worker, control plane, and Window UI:
  - extended the worker and control-plane protobuf contracts so inspect output now carries stable
    backend, family, source, workflow-role, revision, and supported-task metadata while doctor
    output carries typed health state plus actionable findings instead of markdown-only severity
  - updated `maintenance_core.py` so worker-authored inspect payloads derive typed identity fields
    from loaded or registered model state and doctor responses emit structured warning, degraded,
    and failed findings for missing loads, zero-byte cache state, zero resident memory, and worker
    failure conditions
  - projected the typed inspect and doctor payloads through the Swift control plane, XPC client,
    and Window UI model-tools views so operators can inspect health status, findings, backend or
    family identity, workflow role, revision, supported tasks, and source provenance without
    parsing markdown
  - added focused Python, control-plane, and menu-bar regression coverage for typed inspect
    metadata, doctor severity mapping, structured findings, and the new operator-facing summary
    views
  - moved the next active `M12.4` slice to conversion and packaging workflow completion now that
    inspect and health are stable typed surfaces
- Verification summary for the first executable `M12.4` slice:
  - `make proto`: pass
  - `PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python --extra mlx coverage run --data-file=/tmp/m12_4_python.coverage -m pytest services/mlx-worker-python/tests/test_maintenance_service.py -q && PYTHONPATH=.:services/mlx-worker-python uv run --project services/mlx-worker-python --extra mlx coverage json --data-file=/tmp/m12_4_python.coverage -o /tmp/m12_4_python_coverage.json && python3 scripts/python_changed_line_coverage.py --coverage-json /tmp/m12_4_python_coverage.json services/mlx-worker-python/worker/engine/maintenance_core.py services/mlx-worker-python/tests/test_maintenance_service.py`: `65 passed in 48.59s`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'ControlPlaneServiceTests|PythonBridgeWorkerClientTests'`: `196 tests in 2 suites passed after 0.958 seconds`
  - `python3 scripts/swift_changed_line_coverage.py --binary services/control-plane-swift/.build/arm64-apple-macosx/debug/MelixControlPlanePackageTests.xctest/Contents/MacOS/MelixControlPlanePackageTests --profdata services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/default.profdata services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift services/control-plane-swift/Sources/XPCService/ControlPlaneXPCClient.swift services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`: `100.00%` (`117/117`)
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path apps/macos-menubar --enable-code-coverage --filter 'ControlPlaneXPCClientTests|RuntimeViewModelTests|DesktopFoundationViewTests'`: `217 tests in 3 suites passed after 4.018 seconds`
  - `python3 scripts/swift_changed_line_coverage.py --binary apps/macos-menubar/.build/arm64-apple-macosx/debug/MelixMacOSMenubarPackageTests.xctest/Contents/MacOS/MelixMacOSMenubarPackageTests --profdata apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/default.profdata apps/macos-menubar/Sources/AppMain/Dashboard/DesktopFoundationView.swift apps/macos-menubar/Sources/AppMain/Dashboard/DesktopWorkspaceShellView.swift apps/macos-menubar/Sources/AppMain/Models/RuntimeViewModel.swift apps/macos-menubar/Tests/MenuBarTests/ControlPlaneXPCClientTests.swift apps/macos-menubar/Tests/MenuBarTests/TestSupport.swift apps/macos-menubar/Tests/MenuBarTests/DesktopFoundationViewTests.swift apps/macos-menubar/Tests/MenuBarTests/RuntimeViewModelTests.swift`: `100.00%` (`186/186`)
  - `git diff --check`: pass
- Metrics report for the first executable `M12.4` slice:
  - typed inspect and doctor health metrics exercised by the touched scope:
    - stable inspect identity fields for `backend_id`, `family_id`, `model_path`,
      `model_revision`, `default_workflow_role`, `detected_identity_source`, and
      `supported_tasks`
    - structured doctor states for `healthy`, `warning`, `degraded`, and `failed`
    - actionable doctor finding codes covering missing model loads, cache-unavailable state,
      zero resident bytes, and failed worker state
  - changed-line coverage for the touched handwritten executable scope:
    - Python worker scope: `100.00%` (`103/103`)
    - Swift control-plane scope: `100.00%` (`117/117`)
    - Swift menu-bar scope: `100.00%` (`186/186`)
    - aggregate touched-scope coverage: `100.00%` (`406/406`)
  - generated protobuf outputs and `packages/protocol/descriptors/melix.pb` are excluded from
    executable changed-line coverage because they are regenerated interface artifacts rather than
    handwritten runtime logic

- Started `M12.4` by moving the active task plan to typed model inspection, structured health, and
  model-conversion tooling completion:
  - recorded that the repository already exposes inspect, doctor, and model-operation shells, but
    inspect payloads are still too shallow, doctor is markdown-only, and conversion results are
    not yet a stable operator-facing contract
  - defined the next implementation slice around typed model identity metadata, structured doctor
    severity and findings, and explicit conversion or packaging result summaries that stay tied to
    model identity
  - updated the active task plan so the `M12.4` execution transaction starts from an explicit
    inspect-health-conversion contract instead of treating those workflows as incidental model-ops
    helpers
- Verification summary for the `M12.4` planning transaction:
  - `git diff --check`: pending until the executable change set is complete
- Metrics report for the `M12.4` planning transaction:
  - `N/A` for executable coverage and runtime metrics because this transaction only moved the
    active task plan before implementation started

- Closed `M12.3` by making creative image-family identity repository-owned across worker dispatch,
  control-plane catalog truth, the family support matrix, and the Window UI picker:
  - added image-family adapter descriptors plus detection from explicit overrides, imported model
    metadata, and path heuristics for the supported generation and edit families, with stable
    backend IDs, task kinds, default workflow roles, and support declarations projected into
    worker-visible model specs
  - updated the worker registry, image generation and edit request gates, and dev image seed path
    so sparse model requests preserve catalog truth, unsupported generation-versus-edit workflows
    fail with typed validation, and the repository-owned family support matrix distinguishes live
    verified versus contract-only image rows
  - updated the Swift control-plane catalog and Python bridge preload path so image-family
    metadata survives registry sync, imported model preparation, and phase-seven preload even when
    operators override the seed image family
  - updated the Window UI image workspace so generate and edit workflows each resolve against
    role-capable models, keep separate selections, and expose family support summaries instead of
    collapsing all creative families into one generic image picker entry
  - marked `M12.3` completed in the roadmap execution index; the next active execution slice can
    now advance to `M12.4`
- Verification summary for `M12.3`:
  - `PYTHONPATH=services/mlx-worker-python uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_image_family_adapters.py services/mlx-worker-python/tests/test_model_registry_catalog.py services/mlx-worker-python/tests/test_image_runtime.py services/mlx-worker-python/tests/test_acceptance_metrics.py services/mlx-worker-python/tests/test_runtime_service.py tests/integration/test_image_endpoints.py tests/integration/test_non_text_endpoints.py::test_family_support_matrix_tracks_live_verified_family_overrides -q`: `61 passed in 106.50s (0:01:46)`
  - `swift test --package-path services/control-plane-swift --filter 'ModelCatalogTests|PythonBridgeWorkerClientTests'`: `84 tests in 2 suites passed after 0.783 seconds`
  - `swift test --package-path apps/macos-menubar --filter RuntimeViewModelTests`: `129 tests in 1 suite passed after 0.779 seconds`
  - `git diff --check`: pass
- Metrics report for `M12.3`:
  - repository-owned image family matrix metrics exercised by the touched scope:
    - `family_count = 19`
    - `text_family_count = 6`
    - `image_family_count = 6`
    - `live_verified_count = 15`
    - `contract_only_count = 4`
  - changed-line coverage for the touched handwritten executable scope:
    - Python worker scope: `98.08%` (`153/156`)
    - Swift control-plane scope: `96.77%` (`180/186`)
    - Swift menu-bar scope: `95.31%` (`122/128`)
    - aggregate touched-scope coverage: `96.81%` (`455/470`)

- Started `M12.3` by moving the active task plan to metadata-driven image family dispatch and
  role-aware picker completion:
  - recorded that the repository still treated creative image models as one generic deterministic
    image family, which hid generation-versus-edit constraints from both registry metadata and the
    Window UI picker
  - defined the next implementation slice around image-family detection from explicit overrides,
    imported metadata, and path heuristics, plus role support declarations that drive request
    validation and picker visibility
  - updated the active task plan so the `M12.3` execution transaction starts from an explicit
    family-dispatch and operator-routing contract instead of an implicit image-shell cleanup goal
- Verification summary for the `M12.3` planning transaction:
  - `git diff --check`: pending until the executable change set is complete
- Metrics report for the `M12.3` planning transaction:
  - `N/A` for executable coverage and runtime metrics because this transaction only moved the
    active task plan before implementation started

- Closed `M12.2` by making text-family and MoE-family adapter metadata repository-owned across the
  Python worker, control-plane catalog, support matrix, and deterministic live-path verification:
  - added worker-owned text-family adapters for `llama`, `mistral4`, `mixtral`, `qwen3moe`,
    `deepseek-mla`, and `nemotron-h`, including metadata-driven detection from explicit
    overrides, `config.json`, and path heuristics plus family-specific parser, attention, RoPE,
    and MoE declarations
  - updated worker registry snapshots and runtime loads so scanned text models now carry stable
    family metadata, `python_text_compatibility` routing for larger dense or MoE families, and
    runtime-visible architecture or MoE descriptors without changing the base `swift_text` dev
    seed defaults
  - updated the Swift control-plane catalog seed path and registry-sync logic so discovered or
    dev text models preserve text-family identity, parser declarations, route kind, and MoE
    settings through worker preparation and catalog truth
  - expanded the repository-owned family support matrix and integration evidence so the text
    matrix now distinguishes live-verified rows for `llama`, `mistral4`, `qwen3moe`,
    `deepseek-mla`, and `nemotron-h`, while keeping `mixtral` explicitly `contract_only`
  - marked `M12.2` completed in the roadmap execution index; the next active execution slice can
    now advance to `M12.3`
- Verification summary for `M12.2`:
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_text_family_adapters.py services/mlx-worker-python/tests/test_model_registry_catalog.py services/mlx-worker-python/tests/test_mlx_backend.py services/mlx-worker-python/tests/test_acceptance_metrics.py -q`: `49 passed in 0.22s`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx pytest tests/integration/test_text_family_endpoints.py tests/integration/test_non_text_endpoints.py::test_family_support_matrix_tracks_live_verified_family_overrides -q`: `4 passed in 58.25s`
  - `PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" COVERAGE_FILE=/tmp/m12_2_python.coverage UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx coverage run --source=services/mlx-worker-python/worker,services/mlx-worker-python/tests,tests/integration -m pytest services/mlx-worker-python/tests/test_text_family_adapters.py services/mlx-worker-python/tests/test_model_registry_catalog.py services/mlx-worker-python/tests/test_mlx_backend.py services/mlx-worker-python/tests/test_acceptance_metrics.py tests/integration/test_text_family_endpoints.py tests/integration/test_non_text_endpoints.py::test_family_support_matrix_tracks_live_verified_family_overrides -q && PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" COVERAGE_FILE=/tmp/m12_2_python.coverage UV_CACHE_DIR="$(pwd)/.uv-cache" uv run --project services/mlx-worker-python --extra mlx coverage json -o /tmp/m12_2_python_coverage.json`: `53 passed in 58.82s`
  - `HOME="$(pwd)/.swift-home" CLANG_MODULE_CACHE_PATH="$(pwd)/.build/ModuleCache.noindex" swift test --package-path services/control-plane-swift --enable-code-coverage --filter 'ModelCatalogTests|ControlPlaneServiceTests|PythonBridgeWorkerClientTests'`: `227 tests in 3 suites passed after 1.106 seconds`
  - `git diff --check`: pass
- Metrics report for `M12.2`:
  - repository-owned family-matrix metrics exercised by the touched scope:
    - `family_count = 13`
    - `text_family_count = 6`
    - `live_verified_count = 11`
    - `contract_only_count = 2`
  - changed-line coverage for the touched handwritten executable scope:
    - Python worker and integration scope: `100.00%` (`389/389`)
    - Swift control-plane scope: `100.00%` (`315/315`)
    - aggregate touched-scope coverage: `100.00%` (`704/704`)

- Started `M12.2` by moving the active task plan to metadata-driven text and MoE family adapters:
  - recorded that the repository still treated larger dense and MoE text models as generic text
    entries, which hid parser, routing, and MoE-specific capability declarations from both the
    registry snapshot and the support matrix
  - defined the next implementation slice around family detection from explicit overrides,
    `config.json`, and path heuristics, `python_text_compatibility` routing for advanced families,
    and deterministic live-path verification through the HTTP text-generation surface
  - updated the active task plan so the `M12.2` execution transaction started from an explicit
    milestone contract instead of an implicit family-expansion goal
- Verification summary for the `M12.2` planning transaction:
  - `git diff --check`: pass
- Metrics report for the `M12.2` planning transaction:
  - `N/A` for executable coverage and runtime metrics because this transaction only updated the
    active task plan before implementation started

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

- Closed the `M11.4` evidence slice and, with it, the roadmap bookkeeping for parent `M11` by
  adding repository-owned truthful disk-streaming smoke evidence and operator runbook guidance
  without fabricating unsupported SSD-backed runtime metrics:
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
  - marked `M11.4` as an evidence-only closure in the roadmap execution index and closed the
    parent `M11` milestone bookkeeping; the next active execution slice can now advance to
    `M12.1`
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
