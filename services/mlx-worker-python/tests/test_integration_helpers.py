from __future__ import annotations

import json
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace

import grpc
import pytest

from tests.integration import helpers


def test_resolve_swift_product_binary_raises_when_build_output_is_missing(tmp_path: Path) -> None:
    with pytest.raises(AssertionError, match="Required Swift product binary is missing"):
        helpers.resolve_swift_product_binary(
            tmp_path,
            package_path=Path("services/control-plane-swift"),
            product_name="melix-control-plane",
        )


def test_wait_for_worker_handshake_raises_when_worker_exits_before_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeChannel:
        def close(self) -> None:
            return None

    stdout_path = tmp_path / "worker.stdout.log"
    stderr_path = tmp_path / "worker.stderr.log"
    stdout_path.write_text("stdout marker", encoding="utf-8")
    stderr_path.write_text("stderr marker", encoding="utf-8")

    worker = SimpleNamespace(poll=lambda: 1)

    monkeypatch.setattr(helpers.grpc, "insecure_channel", lambda target: FakeChannel())
    monkeypatch.setattr(helpers.runtime_pb2_grpc, "RuntimeServiceStub", lambda channel: object())

    with pytest.raises(AssertionError, match="Worker exited before handshake completed"):
        helpers.wait_for_worker_handshake(
            tmp_path / "worker.sock",
            worker=worker,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            timeout_seconds=0.01,
        )


def test_wait_for_worker_handshake_times_out_when_rpc_never_succeeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeChannel:
        def close(self) -> None:
            return None

    class FakeStub:
        def Handshake(self, request, timeout: float) -> None:
            raise grpc.RpcError("not ready")

    perf_times = iter([0.0, 0.3, 0.6])

    monkeypatch.setattr(helpers.grpc, "insecure_channel", lambda target: FakeChannel())
    monkeypatch.setattr(helpers.runtime_pb2_grpc, "RuntimeServiceStub", lambda channel: FakeStub())
    monkeypatch.setattr(helpers.time, "time", lambda: next(perf_times))
    monkeypatch.setattr(helpers.time, "sleep", lambda seconds: None)

    with pytest.raises(AssertionError, match="Worker never became ready"):
        helpers.wait_for_worker_handshake(tmp_path / "worker.sock", timeout_seconds=0.5)


def test_wait_for_http_wrapper_functions_forward_expected_required_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[dict[str, str]] = []

    def fake_wait_for_http_model_states(port: int, **kwargs) -> None:
        observed.append(dict(kwargs["required_states"]))

    monkeypatch.setattr(helpers, "wait_for_http_model_states", fake_wait_for_http_model_states)

    helpers.wait_for_http_models(11434)
    helpers.wait_for_http_ready(11434)

    assert observed == [{"melix-dev-text": "warm"}, {}]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {
                "swift_text_worker": SimpleNamespace(poll=lambda: 1),
                "swift_text_worker_stdout_path": None,
                "swift_text_worker_stderr_path": None,
            },
            "Swift text worker exited before warm model was visible",
        ),
        (
            {
                "python_worker": SimpleNamespace(poll=lambda: 1),
                "python_worker_stdout_path": None,
                "python_worker_stderr_path": None,
            },
            "Python worker exited before warm model was visible",
        ),
        (
            {
                "control_plane": SimpleNamespace(poll=lambda: 1),
                "control_plane_stdout_path": None,
                "control_plane_stderr_path": None,
            },
            "Control plane exited before warm model was visible",
        ),
    ],
)
def test_wait_for_http_model_states_raises_when_process_exits(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(AssertionError, match=message):
        helpers.wait_for_http_model_states(
            11434,
            required_states={"melix-dev-text": "warm"},
            timeout_seconds=0.01,
            **kwargs,
        )


def test_wait_for_http_model_states_times_out_with_last_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    perf_times = iter([0.0, 0.3, 0.6])

    monkeypatch.setattr(helpers.time, "time", lambda: next(perf_times))
    monkeypatch.setattr(helpers.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        helpers.urllib.request,
        "urlopen",
        lambda url, timeout: (_ for _ in ()).throw(helpers.urllib.error.URLError("down")),
    )

    with pytest.raises(AssertionError, match="Control plane never exposed the required model states"):
        helpers.wait_for_http_model_states(
            11434,
            required_states={"melix-dev-text": "warm"},
            timeout_seconds=0.5,
        )


def test_wait_for_http_model_states_accepts_pinned_when_warm_is_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    perf_times = iter([0.0, 0.1, 0.2, 0.3, 0.4, 0.6])

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def read(self) -> bytes:
            return json.dumps(
                {
                    "data": [
                        {"id": "melix-dev-image", "melix_state": "pinned"},
                    ]
                }
            ).encode("utf-8")

    monkeypatch.setattr(helpers.time, "time", lambda: next(perf_times))
    monkeypatch.setattr(helpers.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(helpers.urllib.request, "urlopen", lambda url, timeout: FakeResponse())

    helpers.wait_for_http_model_states(
        11434,
        required_states={"melix-dev-image": "warm"},
        timeout_seconds=0.5,
    )


def test_stop_process_escalates_to_sigkill_after_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProcess:
        pid = 42

        def __init__(self) -> None:
            self.wait_calls = 0

        def poll(self) -> None:
            return None

        def wait(self, timeout: float) -> None:
            self.wait_calls += 1
            if self.wait_calls == 1:
                raise subprocess.TimeoutExpired(cmd="worker", timeout=timeout)

    sent_signals: list[tuple[int, int]] = []
    process = FakeProcess()
    stack = helpers.LiveMelixStack(tmp_path)

    monkeypatch.setattr(helpers.os, "getpgid", lambda pid: pid + 100)
    monkeypatch.setattr(
        helpers.os,
        "killpg",
        lambda pgid, signal_value: sent_signals.append((pgid, signal_value)),
    )

    stack._stop_process("worker", process)

    assert sent_signals == [
        (142, helpers.signal.SIGTERM),
        (142, helpers.signal.SIGKILL),
    ]
    assert process.wait_calls == 2


def test_stop_process_waits_for_already_exited_process(tmp_path: Path) -> None:
    class FakeProcess:
        def __init__(self) -> None:
            self.wait_calls = 0

        def poll(self) -> int:
            return 0

        def wait(self, timeout: float) -> None:
            self.wait_calls += 1

    process = FakeProcess()
    stack = helpers.LiveMelixStack(tmp_path)

    stack._stop_process("worker", process)

    assert process.wait_calls == 1


def test_format_process_failure_reads_existing_logs(tmp_path: Path) -> None:
    stdout_path = tmp_path / "stdout.log"
    stderr_path = tmp_path / "stderr.log"
    stdout_path.write_text("hello", encoding="utf-8")
    stderr_path.write_text("world", encoding="utf-8")

    message = helpers._format_process_failure("boom", stdout_path, stderr_path)

    assert "stdout='hello'" in message
    assert "stderr='world'" in message


def test_read_metrics_export_parses_json_payload(tmp_path: Path) -> None:
    payload = {"values": {"control_plane.http_ready_ms": 3.1}}
    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text(json.dumps(payload), encoding="utf-8")

    assert helpers.read_metrics_export(metrics_path) == payload


def test_live_melix_stack_cli_environment_includes_runtime_socket_and_store_paths(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    stack = helpers.LiveMelixStack(
        repo_root,
        environment_overrides={
            "MELIX_HOME": "/custom/home",
            "MELIX_GATEWAY_CONFIG_STORE_PATH": "/custom/config.json",
            "MELIX_GATEWAY_SERVING_DEFAULTS_STORE_PATH": "/custom/defaults.json",
        },
    )

    environment = stack.cli_environment(repo_root)

    assert environment["MELIX_HOME"] == "/custom/home"
    assert environment["MELIX_GATEWAY_CONFIG_STORE_PATH"] == "/custom/config.json"
    assert environment["MELIX_GATEWAY_SERVING_DEFAULTS_STORE_PATH"] == "/custom/defaults.json"
    assert environment["MELIX_REPO_ROOT"] == str(repo_root)
    assert environment["MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH"] == str(stack.swift_socket_path)
    assert environment["MELIX_WORKER_SOCKET_PATH"] == str(stack.python_socket_path)
    assert environment["MELIX_CONTROL_PLANE_METRICS_PATH"] == str(stack.control_plane_metrics_path)
    assert environment["MELIX_MODEL_OPS_JOBS_ROOT"] == str(stack.model_ops_jobs_root)
    assert environment["MELIX_EVALUATION_JOBS_ROOT"] == str(stack.evaluation_jobs_root)


def test_live_melix_stack_start_uses_ensured_swift_binaries_and_runtime_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    stack = helpers.LiveMelixStack(repo_root, start_python_worker=False)
    recorded_binary_requests: list[tuple[Path, str]] = []
    recorded_processes: list[tuple[list[str], dict[str, str]]] = []

    class FakeProcess:
        def __init__(self, pid: int) -> None:
            self.pid = pid

        def poll(self) -> None:
            return None

    def fake_ensure_swift_product_binary(repo_root_arg: Path, *, package_path: Path, product_name: str, timeout_seconds: float = 600.0) -> Path:
        recorded_binary_requests.append((package_path, product_name))
        return repo_root_arg / package_path / ".build" / "arm64-apple-macosx" / "debug" / product_name

    def fake_popen(command, **kwargs):
        recorded_processes.append((command, kwargs["env"]))
        return FakeProcess(pid=100 + len(recorded_processes))

    monkeypatch.setattr(helpers, "ensure_swift_product_binary", fake_ensure_swift_product_binary)
    monkeypatch.setattr(helpers.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(helpers, "wait_for_worker_handshake", lambda *args, **kwargs: None)
    monkeypatch.setattr(helpers, "wait_for_http_ready", lambda *args, **kwargs: None)
    monkeypatch.setattr(stack, "_stop_process", lambda name, process: None)

    try:
        stack.start()
    finally:
        stack.stop()

    assert recorded_binary_requests == [
        (Path("services/mlx-text-worker-swift"), "melix-text-worker-swift"),
        (Path("services/control-plane-swift"), "melix-control-plane"),
    ]
    assert recorded_processes[0][0] == [
        str(repo_root / "services/mlx-text-worker-swift/.build/arm64-apple-macosx/debug/melix-text-worker-swift")
    ]
    assert recorded_processes[1][0] == [
        str(repo_root / "services/control-plane-swift/.build/arm64-apple-macosx/debug/melix-control-plane")
    ]
    assert recorded_processes[0][1]["MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH"] == str(stack.swift_socket_path)
    assert recorded_processes[1][1]["MELIX_HOME"] == str(stack.runtime_state_root)


def test_phase1_canonical_cli_cases_parses_positive_and_negative_commands(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    runbook_path = repo_root / "docs" / "runbooks" / "m7-benchmark-and-evaluation-foundation.md"
    runbook_path.parent.mkdir(parents=True, exist_ok=True)
    runbook_path.write_text(
        """
## Phase 1 Canonical CLI Acceptance Suite

Prerequisite: ensure the release CLI binary exists before running this suite.

```bash
swift build -c release --product melix
```

Use the release build to run the positive acceptance suite against
`mlx-community/Qwen3.5-0.8B-OptiQ-4bit`.

```bash
# comment line
./.build/release/melix bench run --repo-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit --suite smoke --context-length 1024 --generation-length 128 --batch-size 1 --sample-size 2 --batch-factor 1 --json
echo helper note
./.build/release/melix bench matrix run --repo-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit --suite smoke --requests 4 --json
./.build/release/melix eval run --repo-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit --suite mmlu --json
```

Use these negative acceptance commands for two CLI failure-path categories.

```bash
# comment line
./.build/release/melix bench matrix run --repo-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit --suite smoke --requests 4 --duration-seconds 30
echo helper note
./.build/release/melix eval run --repo-id mlx-community/Qwen-Image-2512-4bit --suite mmlu --json
```

## Next Section
""".strip(),
        encoding="utf-8",
    )

    commands = helpers._phase1_canonical_cli_cases(repo_root)

    assert commands["bench_run_positive"] == [
        "bench",
        "run",
        "--repo-id",
        "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
        "--suite",
        "smoke",
        "--context-length",
        "1024",
        "--generation-length",
        "128",
        "--batch-size",
        "1",
        "--sample-size",
        "2",
        "--batch-factor",
        "1",
        "--json",
    ]
    assert commands["bench_matrix_conflicting_load_budget_negative"][-2:] == [
        "--duration-seconds",
        "30",
    ]
    assert commands["eval_run_unsupported_repo_negative"][3] == "mlx-community/Qwen-Image-2512-4bit"


def test_phase1_canonical_cli_cases_rejects_missing_required_commands(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    runbook_path = repo_root / "docs" / "runbooks" / "m7-benchmark-and-evaluation-foundation.md"
    runbook_path.parent.mkdir(parents=True, exist_ok=True)
    runbook_path.write_text(
        """
## Phase 1 Canonical CLI Acceptance Suite

Prerequisite: ensure the release CLI binary exists before running this suite.

```bash
swift build -c release --product melix
```

Use the release build to run the positive acceptance suite against
`mlx-community/Qwen3.5-0.8B-OptiQ-4bit`.

```bash
./.build/release/melix bench run --repo-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit --suite smoke --context-length 1024 --generation-length 128 --batch-size 1 --sample-size 2 --batch-factor 1 --json
```

Use these negative acceptance commands for two CLI failure-path categories.

```bash
./.build/release/melix eval run --repo-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit --suite mmlu --json
```
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(AssertionError, match="Phase 1 canonical CLI cases are missing"):
        helpers._phase1_canonical_cli_cases(repo_root)


def test_phase1_canonical_cli_cases_rejects_missing_section_marker(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    runbook_path = repo_root / "docs" / "runbooks" / "m7-benchmark-and-evaluation-foundation.md"
    runbook_path.parent.mkdir(parents=True, exist_ok=True)
    runbook_path.write_text("# Different Section\n", encoding="utf-8")

    with pytest.raises(AssertionError, match="Unable to locate '## Phase 1 Canonical CLI Acceptance Suite'"):
        helpers._phase1_canonical_cli_cases(repo_root)


def test_phase1_canonical_cli_cases_ignores_noncanonical_bash_blocks(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    runbook_path = repo_root / "docs" / "runbooks" / "m7-benchmark-and-evaluation-foundation.md"
    runbook_path.parent.mkdir(parents=True, exist_ok=True)
    runbook_path.write_text(
        """
## Phase 1 Canonical CLI Acceptance Suite

Prerequisite: ensure the release CLI binary exists before running this suite.

```bash
swift build -c release --product melix
```

This auxiliary snippet should not be treated as part of the canonical suite.

```bash
echo helper note
```

Use the release build to run the positive acceptance suite against
`mlx-community/Qwen3.5-0.8B-OptiQ-4bit`.

```bash
./.build/release/melix bench run --repo-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit --suite smoke --context-length 1024 --generation-length 128 --batch-size 1 --sample-size 2 --batch-factor 1 --json
./.build/release/melix bench matrix run --repo-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit --suite smoke --requests 4 --json
./.build/release/melix eval run --repo-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit --suite mmlu --json
```

Use these negative acceptance commands for two CLI failure-path categories.

```bash
./.build/release/melix bench matrix run --repo-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit --suite smoke --requests 4 --duration-seconds 30
./.build/release/melix eval run --repo-id mlx-community/Qwen-Image-2512-4bit --suite mmlu --json
```
""".strip(),
        encoding="utf-8",
    )

    commands = helpers._phase1_canonical_cli_cases(repo_root)

    assert commands["bench_run_positive"][0:2] == ["bench", "run"]
    assert commands["eval_run_unsupported_repo_negative"][3] == "mlx-community/Qwen-Image-2512-4bit"


def test_resolve_cli_binary_uses_root_package_build_output(tmp_path: Path) -> None:
    binary_path = tmp_path / ".build/arm64-apple-macosx/debug/melix"
    binary_path.parent.mkdir(parents=True, exist_ok=True)
    binary_path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    binary_path.chmod(binary_path.stat().st_mode | stat.S_IXUSR)

    assert helpers.resolve_cli_binary(tmp_path) == binary_path


def test_ensure_cli_binary_delegates_to_swift_product_binary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    recorded: dict[str, object] = {}

    def fake_ensure_swift_product_binary(
        repo_root: Path,
        *,
        package_path: Path,
        product_name: str,
        timeout_seconds: float = 600.0,
        configuration: str = "debug",
    ) -> Path:
        recorded["repo_root"] = repo_root
        recorded["package_path"] = package_path
        recorded["product_name"] = product_name
        recorded["timeout_seconds"] = timeout_seconds
        recorded["configuration"] = configuration
        return repo_root / ".build/arm64-apple-macosx/debug/melix"

    monkeypatch.setattr(helpers, "ensure_swift_product_binary", fake_ensure_swift_product_binary)

    resolved = helpers.ensure_cli_binary(tmp_path, timeout_seconds=11.0, configuration="release")

    assert resolved == tmp_path / ".build/arm64-apple-macosx/debug/melix"
    assert recorded == {
        "repo_root": tmp_path,
        "package_path": Path("."),
        "product_name": "melix",
        "timeout_seconds": 11.0,
        "configuration": "release",
    }


def test_run_melix_cli_executes_binary_with_merged_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    recorded: dict[str, object] = {}

    def fake_run(command, **kwargs):
        recorded["command"] = command
        recorded["cwd"] = kwargs["cwd"]
        recorded["env"] = kwargs["env"]
        recorded["timeout"] = kwargs["timeout"]
        return subprocess.CompletedProcess(command, 0, stdout='{"ok":true}', stderr="")

    monkeypatch.setattr(
        helpers,
        "ensure_cli_binary",
        lambda repo_root, timeout_seconds=600.0, configuration="debug": recorded.update({"configuration": configuration})
        or repo_root / ".build/debug/melix",
    )
    monkeypatch.setattr(helpers.subprocess, "run", fake_run)
    monkeypatch.setenv("PATH", "/usr/bin")

    result = helpers.run_melix_cli(
        tmp_path,
        ["bench", "list", "--json"],
        {"MELIX_HOME": "/tmp/melix-home"},
        configuration="release",
        timeout_seconds=12.5,
    )

    assert result.returncode == 0
    assert recorded["command"] == [str(tmp_path / ".build/debug/melix"), "bench", "list", "--json"]
    assert recorded["cwd"] == tmp_path
    assert recorded["env"]["PATH"] == "/usr/bin"
    assert recorded["env"]["MELIX_HOME"] == "/tmp/melix-home"
    assert recorded["configuration"] == "release"
    assert recorded["timeout"] == 12.5


def test_run_phase1_canonical_cli_uses_resolved_command_arguments(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    recorded: dict[str, object] = {}
    completed = subprocess.CompletedProcess(["melix", "bench", "run"], 0, stdout="{}", stderr="")

    monkeypatch.setattr(helpers, "_phase1_canonical_cli_cases", lambda repo_root: {"bench_run_positive": ["bench", "run", "--json"]})
    monkeypatch.setattr(
        helpers,
        "run_melix_cli",
        lambda repo_root, args, environment, timeout_seconds=600.0, configuration="debug": recorded.update(
            {
                "repo_root": repo_root,
                "args": args,
                "environment": environment,
                "timeout_seconds": timeout_seconds,
                "configuration": configuration,
            }
        )
        or completed,
    )

    result = helpers.run_phase1_canonical_cli(
        tmp_path,
        {"MELIX_HOME": "/tmp/melix-home"},
        case_id="bench_run_positive",
        timeout_seconds=33.0,
    )

    assert result == completed
    assert recorded == {
        "repo_root": tmp_path,
        "args": ["bench", "run", "--json"],
        "environment": {"MELIX_HOME": "/tmp/melix-home"},
        "timeout_seconds": 33.0,
        "configuration": "release",
    }


def test_ensure_swift_product_binary_builds_missing_product(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    binary_path = repo_root / "services/control-plane-swift/.build/arm64-apple-macosx/debug/melix-control-plane"
    recorded: dict[str, object] = {}

    def fake_run(command, **kwargs):
        recorded["command"] = command
        recorded["cwd"] = kwargs["cwd"]
        recorded["env"] = kwargs["env"]
        binary_path.parent.mkdir(parents=True, exist_ok=True)
        binary_path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        binary_path.chmod(binary_path.stat().st_mode | stat.S_IXUSR)
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(helpers.subprocess, "run", fake_run)

    resolved = helpers.ensure_swift_product_binary(
        repo_root,
        package_path=Path("services/control-plane-swift"),
        product_name="melix-control-plane",
        timeout_seconds=42.0,
    )

    assert resolved == binary_path
    assert recorded["command"] == [
        "swift",
        "build",
        "--package-path",
        str(repo_root / "services/control-plane-swift"),
        "--product",
        "melix-control-plane",
    ]
    assert recorded["cwd"] == repo_root
    assert recorded["env"]["HOME"] == str(repo_root / ".swift-home")
    assert recorded["env"]["CLANG_MODULE_CACHE_PATH"] == str(repo_root / ".build" / "ModuleCache.noindex")


def test_ensure_swift_product_binary_raises_when_build_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"

    monkeypatch.setattr(
        helpers.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command,
            1,
            stdout="swift build stdout",
            stderr="swift build stderr",
        ),
    )

    with pytest.raises(AssertionError, match="Unable to build required Swift product"):
        helpers.ensure_swift_product_binary(
            repo_root,
            package_path=Path("services/mlx-text-worker-swift"),
            product_name="melix-text-worker-swift",
        )


def test_run_phase1_canonical_cli_rejects_unknown_case(tmp_path: Path) -> None:
    runbook_path = tmp_path / "docs" / "runbooks" / "m7-benchmark-and-evaluation-foundation.md"
    runbook_path.parent.mkdir(parents=True, exist_ok=True)
    runbook_path.write_text(
        """
## Phase 1 Canonical CLI Acceptance Suite

Prerequisite: ensure the release CLI binary exists before running this suite.

```bash
swift build -c release --product melix
```

Use the release build to run the positive acceptance suite against
`mlx-community/Qwen3.5-0.8B-OptiQ-4bit`.

```bash
./.build/release/melix bench run --repo-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit --suite smoke --context-length 1024 --generation-length 128 --batch-size 1 --sample-size 2 --batch-factor 1 --json
./.build/release/melix bench matrix run --repo-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit --suite smoke --requests 4 --json
./.build/release/melix eval run --repo-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit --suite mmlu --json
```

Use these negative acceptance commands for two CLI failure-path categories.

```bash
./.build/release/melix bench matrix run --repo-id mlx-community/Qwen3.5-0.8B-OptiQ-4bit --suite smoke --requests 4 --duration-seconds 30
./.build/release/melix eval run --repo-id mlx-community/Qwen-Image-2512-4bit --suite mmlu --json
```
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(AssertionError, match="Unknown Phase 1 canonical CLI case"):
        helpers.run_phase1_canonical_cli(tmp_path, {}, case_id="not-a-real-case")
