from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import textwrap

from worker.engine import code_eval_runner
from worker.engine.code_eval_runner import run_python_code_evaluation


def test_run_python_code_evaluation_ignores_candidate_stdout_before_payload() -> None:
    result = run_python_code_evaluation(
        candidate_code=textwrap.dedent(
            """
            def identity(value):
                print("candidate-noise")
                return value
            """
        ).strip(),
        entry_point="identity",
        test_code="assert identity(4) == 4\nassert identity('hi') == 'hi'",
    )

    assert result.passed is True
    assert result.tests_passed == 2
    assert result.tests_total == 2


def test_run_python_code_evaluation_executes_multiline_test_blocks() -> None:
    result = run_python_code_evaluation(
        candidate_code=textwrap.dedent(
            """
            def identity(value):
                return value
            """
        ).strip(),
        entry_point="identity",
        test_code=textwrap.dedent(
            """
            def check(candidate):
                assert candidate(4) == 4
                assert candidate("hi") == "hi"

            check(identity)
            """
        ).strip(),
    )

    assert result.passed is True
    assert result.tests_passed == 2
    assert result.tests_total == 2


def test_run_python_code_evaluation_sandbox_blocks_home_file_reads() -> None:
    repo_probe = Path(__file__).resolve()
    result = run_python_code_evaluation(
        candidate_code=textwrap.dedent(
            f"""
            from pathlib import Path

            def read_probe():
                return Path({str(repo_probe)!r}).read_text(encoding="utf-8")[:8]
            """
        ).strip(),
        entry_point="read_probe",
        test_code=f"assert read_probe() == {repo_probe.read_text(encoding='utf-8')[:8]!r}",
    )

    assert result.passed is False
    assert result.runtime_status == "error"
    assert result.test_status == "failed"
    assert "PermissionError" in result.failure_detail


def test_run_python_code_evaluation_sandbox_blocks_subprocess_execution() -> None:
    result = run_python_code_evaluation(
        candidate_code=textwrap.dedent(
            """
            import subprocess

            def spawn_child():
                output = subprocess.check_output(
                    ["/bin/sh", "-c", "printf 7"],
                    text=True,
                )
                return int(output.strip())
            """
        ).strip(),
        entry_point="spawn_child",
        test_code="assert spawn_child() == 7",
    )

    assert result.passed is False
    assert result.runtime_status == "error"
    assert result.test_status == "failed"
    assert "PermissionError" in result.failure_detail or "Operation not permitted" in result.failure_detail


def test_run_python_code_evaluation_rejects_plain_json_stdout_spoof() -> None:
    result = run_python_code_evaluation(
        candidate_code=textwrap.dedent(
            """
            import json
            import os

            def identity(value):
                print(
                    json.dumps(
                        {
                            "compile_status": "compiled",
                            "runtime_status": "ok",
                            "timeout_status": "ok",
                            "test_status": "passed",
                            "tests_passed": 999,
                            "tests_total": 999,
                            "failure_detail": "",
                        }
                    ),
                    flush=True,
                )
                os._exit(0)
            """
        ).strip(),
        entry_point="identity",
        test_code="assert identity(4) == 4",
    )

    assert result.passed is False
    assert result.runtime_status == "error"
    assert result.test_status == "failed"
    assert result.tests_total == 1


def test_run_python_code_evaluation_sandbox_blocks_non_temp_file_reads() -> None:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as file:
        file.write("external-probe")
        external_probe = Path(file.name)

    try:
        result = run_python_code_evaluation(
            candidate_code=textwrap.dedent(
                f"""
                from pathlib import Path

                def read_external_probe():
                    return Path({str(external_probe)!r}).read_text(encoding="utf-8")
                """
            ).strip(),
            entry_point="read_external_probe",
            test_code="assert read_external_probe() == 'external-probe'",
        )
    finally:
        external_probe.unlink(missing_ok=True)

    assert result.passed is False
    assert result.runtime_status == "error"
    assert result.test_status == "failed"
    assert "PermissionError" in result.failure_detail


def test_run_python_code_evaluation_returns_syntax_error_result() -> None:
    result = run_python_code_evaluation(
        candidate_code="def broken(",
        entry_point="broken",
        test_code="assert True",
    )

    assert result.compile_status == "syntax_error"
    assert result.runtime_status == "not_run"
    assert result.test_status == "not_run"
    assert result.tests_total == 1


def test_run_python_code_evaluation_fails_when_sandbox_exec_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(code_eval_runner.shutil, "which", lambda _: None)

    result = run_python_code_evaluation(
        candidate_code="def identity(value):\n    return value",
        entry_point="identity",
        test_code="assert identity(1) == 1",
    )

    assert result.compile_status == "compiled"
    assert result.runtime_status == "error"
    assert result.failure_detail == "sandbox-exec is unavailable on this host."


def test_run_python_code_evaluation_returns_timeout_result(monkeypatch) -> None:
    monkeypatch.setattr(code_eval_runner.shutil, "which", lambda _: "/usr/bin/sandbox-exec")

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=1)

    monkeypatch.setattr(code_eval_runner.subprocess, "run", fake_run)

    result = run_python_code_evaluation(
        candidate_code="def identity(value):\n    return value",
        entry_point="identity",
        test_code="assert identity(1) == 1",
        timeout_seconds=1,
    )

    assert result.runtime_status == "timeout"
    assert result.timeout_status == "timed_out"
    assert result.test_status == "not_run"
    assert result.failure_detail == "Timed out after 1s"


def test_run_python_code_evaluation_uses_stderr_when_payload_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(code_eval_runner.shutil, "which", lambda _: "/usr/bin/sandbox-exec")
    monkeypatch.setattr(
        code_eval_runner.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=7,
            stdout="candidate-noise",
            stderr="runtime exploded",
        ),
    )

    result = run_python_code_evaluation(
        candidate_code="def identity(value):\n    return value",
        entry_point="identity",
        test_code="assert identity(1) == 1",
    )

    assert result.runtime_status == "error"
    assert result.test_status == "failed"
    assert result.failure_detail == "runtime exploded"


def test_count_tests_falls_back_for_syntax_error_input() -> None:
    assert code_eval_runner._count_tests("assert True\n  assert False") == 2


def test_count_tests_falls_back_when_no_asserts_are_present() -> None:
    test_code = textwrap.dedent(
        """
        def check(candidate):
            return candidate(1)

        check(identity)
        """
    ).strip()

    assert code_eval_runner._count_tests(test_code) == 3


def test_load_payload_accepts_last_matching_sentinel_line() -> None:
    payload = code_eval_runner._load_payload(
        'candidate-noise\n\n__MELIX__{"runtime_status":"ok"}\n',
        "__MELIX__",
    )

    assert payload == {"runtime_status": "ok"}


def test_load_payload_rejects_plain_json_without_sentinel() -> None:
    assert code_eval_runner._load_payload('{"runtime_status":"ok"}\n', "__MELIX__") is None


def test_load_payload_returns_none_for_empty_stdout() -> None:
    assert code_eval_runner._load_payload("", "__MELIX__") is None


def test_decode_payload_rejects_invalid_and_non_mapping_json() -> None:
    assert code_eval_runner._decode_payload("not-json") is None
    assert code_eval_runner._decode_payload("[1, 2, 3]") is None
