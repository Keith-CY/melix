from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import textwrap

from worker.engine import code_eval_runner
from worker.engine.code_eval_runner import run_python_code_evaluation


def test_extract_candidate_code_handles_empty_plaintext_and_code_blocks() -> None:
    assert code_eval_runner.extract_candidate_code("   ") == ("", "empty_prediction")
    assert code_eval_runner.extract_candidate_code("print('hi')") == ("print('hi')", "parsed_code")
    assert code_eval_runner.extract_candidate_code("```python\nprint('hi')\n```") == (
        "print('hi')",
        "parsed_code_block",
    )


def test_is_code_execution_policy_supported_requires_sandboxed_policy_and_binary(monkeypatch) -> None:
    monkeypatch.setattr(code_eval_runner.shutil, "which", lambda _: "/usr/bin/sandbox-exec")
    assert code_eval_runner.is_code_execution_policy_supported(" sandboxed ") is True
    assert code_eval_runner.is_code_execution_policy_supported("host") is False

    monkeypatch.setattr(code_eval_runner.shutil, "which", lambda _: None)
    assert code_eval_runner.is_code_execution_policy_supported("sandboxed") is False


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


def test_run_python_code_evaluation_handles_candidate_stdout_without_trailing_newline() -> None:
    result = run_python_code_evaluation(
        candidate_code=textwrap.dedent(
            """
            def identity(value):
                print("candidate-noise", end="")
                return value
            """
        ).strip(),
        entry_point="identity",
        test_code="assert identity(4) == 4",
    )

    assert result.passed is True
    assert result.tests_passed == 1
    assert result.tests_total == 1


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


def test_run_python_code_evaluation_sandbox_blocks_host_file_writes(tmp_path: Path) -> None:
    outside_path = tmp_path / "escape.txt"
    result = run_python_code_evaluation(
        candidate_code=textwrap.dedent(
            f"""
            from pathlib import Path

            def write_probe():
                Path({str(outside_path)!r}).write_text("escape", encoding="utf-8")
                return "ok"
            """
        ).strip(),
        entry_point="write_probe",
        test_code="assert write_probe() == 'ok'",
    )

    assert result.passed is False
    assert result.runtime_status == "error"
    assert result.test_status == "failed"
    assert "PermissionError" in result.failure_detail
    assert outside_path.exists() is False


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


def test_run_python_code_evaluation_fails_when_output_exceeds_limit() -> None:
    result = run_python_code_evaluation(
        candidate_code=textwrap.dedent(
            """
            def identity(value):
                print("x" * 70000)
                return value
            """
        ).strip(),
        entry_point="identity",
        test_code="assert identity(1) == 1",
        stdout_limit_bytes=4096,
    )

    assert result.passed is False
    assert result.runtime_status == "error"
    assert result.test_status == "failed"
    assert "stdio limit" in result.failure_detail


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

    def fake_run(*args, **kwargs):
        stderr_handle = kwargs["stderr"]
        stderr_handle.write(b"runtime exploded")
        stderr_handle.flush()
        return subprocess.CompletedProcess(args=args[0], returncode=7)

    monkeypatch.setattr(code_eval_runner.subprocess, "run", fake_run)

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


def test_read_limited_text_handles_missing_and_oversized_files(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.txt"
    assert code_eval_runner._read_limited_text(missing_path, 8) == ""

    output_path = tmp_path / "output.txt"
    output_path.write_text("0123456789abcdef", encoding="utf-8")

    assert code_eval_runner._read_limited_text(output_path, 4) == "cdef"


def test_timeout_and_output_limit_failure_details_include_stdio_when_present() -> None:
    assert code_eval_runner._timeout_failure_detail(
        timeout_seconds=2,
        stdout_tail="out",
        stderr_tail="err",
    ) == "Timed out after 2s. stdout tail: out | stderr tail: err"
    assert code_eval_runner._output_limit_failure_detail(
        stdio_limit_bytes=128,
        stdout_tail="",
        stderr_tail="",
    ) == "Code execution exceeded the 128-byte stdio limit."


def test_sandbox_python_executable_prefers_python_app_launcher_when_present(
    tmp_path: Path,
    monkeypatch,
) -> None:
    resolved = tmp_path / "Frameworks" / "Python.framework" / "Versions" / "3.12" / "bin" / "python3.12"
    resolved.parent.mkdir(parents=True)
    resolved.write_text("", encoding="utf-8")
    launcher = (
        resolved.parent.parent
        / "Resources"
        / "Python.app"
        / "Contents"
        / "MacOS"
        / "Python"
    )
    launcher.parent.mkdir(parents=True)
    launcher.write_text("", encoding="utf-8")

    monkeypatch.setattr(code_eval_runner.sys, "executable", str(resolved))

    assert code_eval_runner._sandbox_python_executable() == launcher.resolve()


def test_sandbox_executable_paths_keep_wrapper_allowed_when_launcher_is_preferred(
    tmp_path: Path,
    monkeypatch,
) -> None:
    resolved = tmp_path / "Frameworks" / "Python.framework" / "Versions" / "3.12" / "bin" / "python3.12"
    resolved.parent.mkdir(parents=True)
    resolved.write_text("", encoding="utf-8")
    launcher = (
        resolved.parent.parent
        / "Resources"
        / "Python.app"
        / "Contents"
        / "MacOS"
        / "Python"
    )
    launcher.parent.mkdir(parents=True)
    launcher.write_text("", encoding="utf-8")

    monkeypatch.setattr(code_eval_runner.sys, "executable", str(resolved))

    paths = code_eval_runner._sandbox_executable_paths()

    assert paths[0] == launcher.resolve()
    assert resolved.resolve() in paths


def test_sandbox_allow_path_variants_falls_back_when_resolve_raises() -> None:
    class BrokenPath:
        def __init__(self, label: str) -> None:
            self.label = label

        def resolve(self):
            raise OSError("broken resolve")

        def __hash__(self) -> int:
            return hash(self.label)

        def __eq__(self, other: object) -> bool:
            return isinstance(other, BrokenPath) and self.label == other.label

    broken = BrokenPath("broken")

    assert code_eval_runner._sandbox_allow_path_variants((broken,)) == (broken,)


def test_count_tests_falls_back_when_no_asserts_are_present() -> None:
    test_code = textwrap.dedent(
        """
        def check(candidate):
            return candidate(1)

        check(identity)
        """
    ).strip()

    assert code_eval_runner._count_tests(test_code) == 3


def test_load_payload_file_rejects_invalid_and_non_mapping_json(tmp_path: Path) -> None:
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("{", encoding="utf-8")
    assert code_eval_runner._load_payload_file(invalid_path) is None

    list_path = tmp_path / "list.json"
    list_path.write_text("[1, 2, 3]", encoding="utf-8")
    assert code_eval_runner._load_payload_file(list_path) is None

    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps({"runtime_status": "ok"}), encoding="utf-8")
    assert code_eval_runner._load_payload_file(payload_path) == {"runtime_status": "ok"}


def test_code_exec_policy_support_and_output_summary_helpers() -> None:
    assert code_eval_runner.is_code_execution_policy_supported("disabled") is False
    assert "stdout tail: hello" in code_eval_runner._summarize_stdio(
        stdout_tail="hello",
        stderr_tail="",
    )
    assert "stderr tail: boom" in code_eval_runner._summarize_stdio(
        stdout_tail="",
        stderr_tail="boom",
    )
