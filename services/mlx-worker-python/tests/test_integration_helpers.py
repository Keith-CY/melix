from __future__ import annotations

import json
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


@pytest.mark.parametrize(
    ("stderr", "expected"),
    [
        ("bind() failed: Address already in use", True),
        ("POSIXErrorCode(rawValue: 48)", True),
        ("freed pointer was not the last allocation", True),
        ("fatal error: unrelated control plane crash", False),
    ],
)
def test_control_plane_startup_retry_classification(
    tmp_path: Path,
    stderr: str,
    expected: bool,
) -> None:
    stack = helpers.LiveMelixStack(tmp_path)
    stack.control_plane_stderr_path.write_text(stderr, encoding="utf-8")

    assert stack._control_plane_startup_failure_is_retryable() is expected


def test_live_stack_retries_retryable_control_plane_startup_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ports = iter([12345, 12346])
    processes: list[object] = []
    wait_calls = 0

    class FakeProcess:
        pid = 42

        def poll(self) -> int:
            return 1

        def wait(self, timeout: float) -> None:
            return None

    def fake_wait_for_http_ready(*args, **kwargs) -> None:
        nonlocal wait_calls
        wait_calls += 1
        if wait_calls == 1:
            kwargs["control_plane_stderr_path"].write_text(
                "freed pointer was not the last allocation",
                encoding="utf-8",
            )
            raise AssertionError("retryable startup exit")

    monkeypatch.setattr(helpers, "reserve_port", lambda: next(ports))
    monkeypatch.setattr(
        helpers,
        "resolve_swift_product_binary",
        lambda *args, **kwargs: tmp_path / "melix-control-plane",
    )
    monkeypatch.setattr(
        helpers.subprocess,
        "Popen",
        lambda *args, **kwargs: processes.append(FakeProcess()) or processes[-1],
    )
    monkeypatch.setattr(helpers, "wait_for_http_ready", fake_wait_for_http_ready)

    stack = helpers.LiveMelixStack(
        tmp_path,
        start_swift_text_worker=False,
        start_python_worker=False,
    )
    try:
        stack.start()

        assert wait_calls == 2
        assert len(processes) == 2
        assert stack.http_port == 12346
    finally:
        stack.stop()


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


def test_wait_for_metric_value_returns_payload_once_threshold_is_reached(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text("{}", encoding="utf-8")
    payloads = iter(
        [
            {"values": {"scheduler.multimodal_active_requests": 0}},
            {"values": {"scheduler.multimodal_active_requests": 1}},
        ]
    )
    perf_times = iter([0.0, 0.01, 0.02, 0.03])

    monkeypatch.setattr(helpers, "read_metrics_export", lambda path: next(payloads))
    monkeypatch.setattr(helpers.time, "time", lambda: next(perf_times))
    monkeypatch.setattr(helpers.time, "sleep", lambda seconds: None)

    payload = helpers.wait_for_metric_value(
        metrics_path,
        "scheduler.multimodal_active_requests",
        minimum=1,
        timeout_seconds=0.05,
    )

    assert payload == {"values": {"scheduler.multimodal_active_requests": 1}}


def test_wait_for_metric_value_raises_when_threshold_is_never_reached(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text("{}", encoding="utf-8")
    perf_times = iter([0.0, 0.02, 0.04, 0.06])

    monkeypatch.setattr(
        helpers,
        "read_metrics_export",
        lambda path: {"values": {"scheduler.multimodal_active_requests": 0}},
    )
    monkeypatch.setattr(helpers.time, "time", lambda: next(perf_times))
    monkeypatch.setattr(helpers.time, "sleep", lambda seconds: None)

    with pytest.raises(AssertionError, match="scheduler.multimodal_active_requests"):
        helpers.wait_for_metric_value(
            metrics_path,
            "scheduler.multimodal_active_requests",
            minimum=1,
            timeout_seconds=0.05,
        )
