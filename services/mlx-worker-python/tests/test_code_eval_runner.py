from __future__ import annotations

from pathlib import Path
import sys
import tempfile

import pytest

import worker.engine.code_eval_runner as code_eval_runner
from worker.engine.code_eval_runner import (
    _HarnessProcessResult,
    _build_execution_command,
    _load_harness_payload,
    _output_limit_failure_message,
    _summarize_process_output,
    _timeout_failure_message,
    execute_python_candidate,
    is_code_execution_policy_supported,
)


pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="sandboxed policy uses macOS sandbox-exec")


def test_execute_python_candidate_sandboxed_blocks_host_file_writes(tmp_path: Path) -> None:
    outside_path = tmp_path / "outside.txt"

    result = execute_python_candidate(
        candidate_code=(
            f"from pathlib import Path\n"
            f"Path({str(outside_path)!r}).write_text('escape')\n"
            f"def add(a, b):\n"
            f"    return a + b\n"
        ),
        entry_point="add",
        test_code="assert add(2, 2) == 4",
    )

    assert result.passed is False
    assert result.execution_status == "failed"
    assert result.metadata["runtime_status"] == "failed"
    assert "PermissionError" in result.metadata["failure_message"]
    assert outside_path.exists() is False


def test_execute_python_candidate_sandboxed_blocks_subprocess_execution() -> None:
    result = execute_python_candidate(
        candidate_code=(
            "import subprocess\n"
            "def add(a, b):\n"
            "    return a + b\n"
            "subprocess.run(['/bin/echo', 'escape'], check=True)\n"
        ),
        entry_point="add",
        test_code="assert add(2, 2) == 4",
    )

    assert result.passed is False
    assert result.execution_status == "failed"
    assert result.metadata["runtime_status"] == "failed"
    assert "Operation not permitted" in result.metadata["failure_message"]


def test_execute_python_candidate_reads_payload_from_file_when_candidate_stdout_has_no_newline() -> None:
    result = execute_python_candidate(
        candidate_code=(
            "print('noise', end='')\n"
            "def add(a, b):\n"
            "    return a + b\n"
        ),
        entry_point="add",
        test_code="assert add(2, 2) == 4",
    )

    assert result.passed is True
    assert result.execution_status == "passed"
    assert result.metadata["test_status"] == "passed"


def test_execute_python_candidate_fails_when_stdout_exceeds_limit() -> None:
    result = execute_python_candidate(
        candidate_code=(
            "def add(a, b):\n"
            "    return a + b\n"
            "print('x' * 70000)\n"
        ),
        entry_point="add",
        test_code="assert add(2, 2) == 4",
        max_stdio_bytes=4096,
    )

    assert result.passed is False
    assert result.execution_status == "output_limit_exceeded"
    assert result.metadata["output_status"] == "limit_exceeded"
    assert "stdio limit" in result.metadata["failure_message"]


def test_execute_python_candidate_returns_sandbox_unavailable_when_policy_cannot_be_enforced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(code_eval_runner, "is_code_execution_policy_supported", lambda policy: False)

    result = execute_python_candidate(
        candidate_code="def add(a, b):\n    return a + b\n",
        entry_point="add",
        test_code="assert add(2, 2) == 4",
    )

    assert result.passed is False
    assert result.execution_status == "sandbox_unavailable"
    assert result.metadata["sandbox_status"] == "unavailable"
    assert "requires macOS sandbox-exec" in result.metadata["failure_message"]


def test_execute_python_candidate_times_out_and_reports_timeout_output() -> None:
    result = execute_python_candidate(
        candidate_code=(
            "import time\n"
            "print('starting', end='')\n"
            "time.sleep(0.2)\n"
            "def add(a, b):\n"
            "    return a + b\n"
        ),
        entry_point="add",
        test_code="assert add(2, 2) == 4",
        timeout_seconds=0.01,
    )

    assert result.passed is False
    assert result.execution_status == "timed_out"
    assert result.metadata["timeout_status"] == "timed_out"
    assert "Timed out after" in result.metadata["failure_message"]


def test_load_harness_payload_reports_missing_payload_when_process_exits_early(tmp_path: Path) -> None:
    payload = _load_harness_payload(
        payload_path=tmp_path / "missing.json",
        process_result=_HarnessProcessResult(
            returncode=7,
            stdout="",
            stderr="",
            timed_out=False,
            output_limit_exceeded=False,
        ),
    )

    assert payload["execution_status"] == "failed"
    assert payload["metadata"]["failure_message"] == (
        "Code execution exited with status 7 without a result payload."
    )


def test_load_harness_payload_reports_invalid_json_payload(tmp_path: Path) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text("{", encoding="utf-8")

    payload = _load_harness_payload(
        payload_path=payload_path,
        process_result=_HarnessProcessResult(
            returncode=0,
            stdout="stdout fallback",
            stderr="",
            timed_out=False,
            output_limit_exceeded=False,
        ),
    )

    assert payload["execution_status"] == "failed"
    assert payload["metadata"]["failure_message"] == "stdout fallback"


def test_load_harness_payload_rejects_non_mapping_payload(tmp_path: Path) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text("[]", encoding="utf-8")

    payload = _load_harness_payload(
        payload_path=payload_path,
        process_result=_HarnessProcessResult(
            returncode=0,
            stdout="",
            stderr="",
            timed_out=False,
            output_limit_exceeded=False,
        ),
    )

    assert payload["execution_status"] == "failed"
    assert payload["metadata"]["failure_message"] == "Unexpected code execution payload shape."


def test_build_execution_command_handles_disabled_and_unavailable_policies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory(prefix="melix-eval-command-") as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        script_path = temp_dir / "code_eval.py"
        script_path.write_text("print('ok')", encoding="utf-8")

        disabled_command, disabled_status, disabled_error = _build_execution_command(
            script_path=script_path,
            temp_dir=temp_dir,
            code_exec_policy="disabled",
        )
        assert disabled_status == "not_requested"
        assert disabled_error == ""
        assert "python" in Path(disabled_command[0]).name

        monkeypatch.setattr(code_eval_runner, "is_code_execution_policy_supported", lambda policy: False)
        unavailable_command, unavailable_status, unavailable_error = _build_execution_command(
            script_path=script_path,
            temp_dir=temp_dir,
            code_exec_policy="sandboxed",
        )
        assert unavailable_status == "unavailable"
        assert "python" in Path(unavailable_command[0]).name
        assert "requires macOS sandbox-exec" in unavailable_error


def test_code_exec_policy_support_and_failure_message_helpers() -> None:
    assert is_code_execution_policy_supported("disabled") is False
    assert "stdout tail: hello" in _summarize_process_output(stdout="hello", stderr="")
    assert "stderr tail: boom" in _summarize_process_output(stdout="", stderr="boom")
    assert _timeout_failure_message(timeout_seconds=1.0, stdout="", stderr="") == "Timed out after 1.0s"
    assert "stdout tail: hello" in _timeout_failure_message(
        timeout_seconds=1.0,
        stdout="hello",
        stderr="",
    )
    assert _output_limit_failure_message(stdout="", stderr="", max_stdio_bytes=128) == (
        "Code execution exceeded the 128-byte stdio limit."
    )
