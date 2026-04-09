ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
UV_CACHE_DIR := $(ROOT)/.uv-cache
SWIFT_HOME := $(ROOT)/.swift-home
CLANG_MODULE_CACHE_PATH := $(ROOT)/.build/ModuleCache.noindex

.PHONY: bootstrap proto swift-test py-test integration-test swift-coverage py-coverage coverage phase1-metrics phase2-metrics phase5-metrics phase6-metrics phase7-metrics phase8-acceptance phase8-install-smoke phase8-release-gate phase8-metrics phase17-metrics

PHASE1_METRICS_ARGS ?=
PHASE2_METRICS_ARGS ?=
PHASE17_METRICS_ARGS ?=
PHASE8_ACCEPTANCE_ARGS ?=
PHASE8_INSTALL_SMOKE_ARGS ?=
PHASE8_RELEASE_GATE_ARGS ?=
PHASE8_METRICS_ARGS ?=

bootstrap:
	mkdir -p "$(UV_CACHE_DIR)" "$(SWIFT_HOME)" "$(CLANG_MODULE_CACHE_PATH)"
	UV_CACHE_DIR="$(UV_CACHE_DIR)" uv sync --project services/mlx-worker-python --extra mlx

proto:
	./scripts/proto_gen.sh

swift-test:
	mkdir -p "$(SWIFT_HOME)" "$(CLANG_MODULE_CACHE_PATH)"
	HOME="$(SWIFT_HOME)" CLANG_MODULE_CACHE_PATH="$(CLANG_MODULE_CACHE_PATH)" swift test --package-path packages/protocol/swift
	HOME="$(SWIFT_HOME)" CLANG_MODULE_CACHE_PATH="$(CLANG_MODULE_CACHE_PATH)" swift test --package-path services/mlx-text-worker-swift
	HOME="$(SWIFT_HOME)" CLANG_MODULE_CACHE_PATH="$(CLANG_MODULE_CACHE_PATH)" swift test --package-path services/control-plane-swift
	HOME="$(SWIFT_HOME)" CLANG_MODULE_CACHE_PATH="$(CLANG_MODULE_CACHE_PATH)" swift test --package-path apps/macos-menubar

py-test:
	mkdir -p "$(UV_CACHE_DIR)"
	PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests -q

integration-test:
	mkdir -p "$(UV_CACHE_DIR)"
	PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx pytest tests/integration -q

swift-coverage:
	mkdir -p "$(SWIFT_HOME)" "$(CLANG_MODULE_CACHE_PATH)"
	HOME="$(SWIFT_HOME)" CLANG_MODULE_CACHE_PATH="$(CLANG_MODULE_CACHE_PATH)" swift test --package-path services/mlx-text-worker-swift --enable-code-coverage
	HOME="$(SWIFT_HOME)" CLANG_MODULE_CACHE_PATH="$(CLANG_MODULE_CACHE_PATH)" swift test --package-path services/control-plane-swift --enable-code-coverage
	HOME="$(SWIFT_HOME)" CLANG_MODULE_CACHE_PATH="$(CLANG_MODULE_CACHE_PATH)" swift test --package-path apps/macos-menubar --enable-code-coverage
	python3 scripts/swift_coverage_summary.py services/mlx-text-worker-swift/.build/arm64-apple-macosx/debug/codecov/MelixTextWorkerSwift.json /services/mlx-text-worker-swift/Sources/
	python3 scripts/swift_coverage_summary.py services/control-plane-swift/.build/arm64-apple-macosx/debug/codecov/MelixControlPlane.json /services/control-plane-swift/Sources/
	python3 scripts/swift_coverage_summary.py apps/macos-menubar/.build/arm64-apple-macosx/debug/codecov/MelixMacOSMenubar.json /apps/macos-menubar/Sources/

py-coverage:
	mkdir -p "$(UV_CACHE_DIR)"
	PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx coverage run --source=services/mlx-worker-python/worker,phase8_runtime_probes,phase8_metrics_report -m pytest services/mlx-worker-python/tests -q
	PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx coverage report --include='services/mlx-worker-python/worker/*,scripts/phase8_runtime_probes.py,scripts/phase8_metrics_report.py'

coverage: swift-coverage py-coverage

phase1-metrics:
	mkdir -p "$(UV_CACHE_DIR)"
	PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx python scripts/phase1_metrics_report.py $(PHASE1_METRICS_ARGS)

phase2-metrics:
	mkdir -p "$(UV_CACHE_DIR)"
	PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx python scripts/phase2_metrics_report.py $(PHASE2_METRICS_ARGS)

phase5-metrics:
	mkdir -p "$(UV_CACHE_DIR)"
	PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx python scripts/phase5_control_plane_metrics.py

phase6-metrics:
	mkdir -p "$(UV_CACHE_DIR)"
	PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx python scripts/phase6_metrics_report.py

phase7-metrics:
	mkdir -p "$(UV_CACHE_DIR)"
	PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx python scripts/phase7_metrics_report.py

phase8-acceptance:
	mkdir -p "$(UV_CACHE_DIR)"
	PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx python scripts/phase8_acceptance_bundle.py $(PHASE8_ACCEPTANCE_ARGS)

phase8-install-smoke:
	mkdir -p "$(UV_CACHE_DIR)"
	PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx python scripts/phase8_install_smoke.py $(PHASE8_INSTALL_SMOKE_ARGS)

phase8-release-gate:
	mkdir -p "$(UV_CACHE_DIR)"
	PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx python scripts/phase8_release_gate.py $(PHASE8_RELEASE_GATE_ARGS)

phase8-metrics:
	mkdir -p "$(UV_CACHE_DIR)"
	PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx python scripts/phase8_metrics_report.py $(PHASE8_METRICS_ARGS)

phase17-metrics:
	mkdir -p "$(UV_CACHE_DIR)"
	PYTHONPATH="$(ROOT):$(ROOT)/services/mlx-worker-python" UV_CACHE_DIR="$(UV_CACHE_DIR)" uv run --project services/mlx-worker-python --extra mlx python scripts/m17_speech_runtime_smoke.py $(PHASE17_METRICS_ARGS)
