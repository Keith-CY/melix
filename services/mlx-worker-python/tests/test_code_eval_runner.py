from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
from typing import Callable, SupportsIndex, cast
from types import ModuleType

import pytest

from worker.engine import code_eval_runner
from worker.engine.code_eval_runner import run_python_code_evaluation


def test_code_evaluation_result_uses_slots_without_instance_dict() -> None:
    result = code_eval_runner.CodeEvaluationResult(
        compile_status="compiled",
        runtime_status="ok",
        timeout_status="ok",
        test_status="passed",
        tests_passed=1,
        tests_total=1,
        failure_detail="",
    )

    assert result.passed is True
    assert not hasattr(result, "__dict__")


def test_extract_candidate_code_handles_empty_plaintext_and_code_blocks() -> None:
    assert code_eval_runner.extract_candidate_code("   ") == ("", "empty_prediction")
    assert code_eval_runner.extract_candidate_code("print('hi')") == ("print('hi')", "parsed_code")
    assert code_eval_runner.extract_candidate_code("```python\nprint('hi')\n```") == (
        "print('hi')",
        "parsed_code_block",
    )
    assert code_eval_runner.extract_candidate_code("```PyThOn\nprint('case')\n```") == (
        "print('case')",
        "parsed_code_block",
    )
    assert code_eval_runner.extract_candidate_code("```PYTHON\nprint('upper')\n```") == (
        "print('upper')",
        "parsed_code_block",
    )
    assert code_eval_runner.extract_candidate_code("```pYtHoN\nprint('case2')\n```") == (
        "print('case2')",
        "parsed_code_block",
    )
    assert code_eval_runner.extract_candidate_code("```python\nprint('hi')\n```   \n\t") == (
        "print('hi')",
        "parsed_code_block",
    )
    assert code_eval_runner.extract_candidate_code("```python\nprint('unicode-space')\u2003\n```") == (
        "print('unicode-space')",
        "parsed_code_block",
    )
    assert code_eval_runner.extract_candidate_code("```python\nprint('unicode-char')é\n```") == (
        "print('unicode-char')é",
        "parsed_code_block",
    )
    assert code_eval_runner.extract_candidate_code("\n  ```python\nprint('wrapped')\n```   \n\t") == (
        "print('wrapped')",
        "parsed_code_block",
    )
    assert code_eval_runner.extract_candidate_code("```python\n\n```") == (
        "",
        "parsed_code_block",
    )
    assert code_eval_runner.extract_candidate_code("```python\r\t  print('ascii-leading')\n```") == (
        "print('ascii-leading')",
        "parsed_code_block",
    )
    assert code_eval_runner.extract_candidate_code("```python\u2003print('unicode-leading')\n```") == (
        "print('unicode-leading')",
        "parsed_code_block",
    )
    assert code_eval_runner.extract_candidate_code("```pythonéprint('unicode-non-space')\n```") == (
        "éprint('unicode-non-space')",
        "parsed_code_block",
    )
    assert code_eval_runner.extract_candidate_code("```\n   print('trimmed')\n```") == (
        "print('trimmed')",
        "parsed_code_block",
    )
    assert code_eval_runner.extract_candidate_code("```   print('inline-trimmed')\n```") == (
        "print('inline-trimmed')",
        "parsed_code_block",
    )
    assert code_eval_runner.extract_candidate_code(
        "first attempt:\n```python\nprint('old')\n```\nfinal answer:\n```python\nprint('new')\n```"
    ) == ("print('new')", "parsed_code_block")
    assert code_eval_runner.extract_candidate_code("```javascript\nprint('tag stays')\n```") == (
        "javascript\nprint('tag stays')",
        "parsed_code_block",
    )
    assert code_eval_runner.extract_candidate_code(
        "```python\nprint('complete')\n```\n```python\nprint('unterminated')"
    ) == ("print('complete')", "parsed_code_block")
    assert code_eval_runner.extract_candidate_code(
        "```python\nprint('complete')\n```\n```"
    ) == ("print('complete')", "parsed_code_block")
    count_calls: list[tuple[str, tuple[SupportsIndex, ...]]] = []

    class CountingResponse(str):
        def count(self, sub: str, *args: SupportsIndex) -> int:  # type: ignore[override]
            count_calls.append((sub, args))
            return super().count(sub, *args)

    trailing_text = "\n" + ("post-answer whitespace scan guard " * 64)
    empty_trailing_block = CountingResponse(
        "```python\nprint('complete')\n```\n```python\n```" + trailing_text
    )
    assert code_eval_runner.extract_candidate_code(empty_trailing_block) == (
        "",
        "parsed_code_block",
    )
    assert count_calls == []
    assert code_eval_runner.extract_candidate_code(
        "```python\nprint('complete')\n```\nfinal commentary after the answer"
    ) == ("print('complete')", "parsed_code_block")
    blocks = [
        f"draft {index}\n```python\ndef candidate():\n    return {index}\n```"
        for index in range(32)
    ]
    assert code_eval_runner.extract_candidate_code("\n".join(blocks)) == (
        "def candidate():\n    return 31",
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


def test_run_python_code_evaluation_skips_parent_test_counting_after_successful_payload(monkeypatch) -> None:
    monkeypatch.setattr(code_eval_runner.shutil, "which", lambda _: "/usr/bin/sandbox-exec")

    def fail_if_counted(test_code: str) -> int:
        raise AssertionError("_count_tests should not run on the successful payload path")

    try:
        fail_if_counted("assert identity(0) == 0")
    except AssertionError:
        pass
    else:
        raise AssertionError("fail_if_counted should raise when invoked")

    def fake_run(*args, **kwargs):
        config_path = Path(args[0][-1])
        config = json.loads(config_path.read_text(encoding="utf-8"))
        payload_path = Path(config["payload_path"])
        payload_path.write_text(
            json.dumps(
                {
                    "compile_status": "compiled",
                    "runtime_status": "ok",
                    "timeout_status": "ok",
                    "test_status": "passed",
                    "tests_passed": 1,
                    "tests_total": 1,
                    "failure_detail": "",
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(args=args[0], returncode=0)

    monkeypatch.setattr(code_eval_runner, "_count_tests", fail_if_counted)
    monkeypatch.setattr(code_eval_runner.subprocess, "run", fake_run)

    result = run_python_code_evaluation(
        candidate_code="def identity(value):\n    return value",
        entry_point="identity",
        test_code="assert identity(1) == 1",
    )

    assert result.passed is True
    assert result.tests_passed == 1
    assert result.tests_total == 1


def test_count_tests_falls_back_for_syntax_error_input() -> None:
    assert code_eval_runner._count_tests("assert True\n  assert False") == 2


def test_count_tests_reuses_cached_counts_for_repeated_payloads() -> None:
    test_code = "assert identity(1) == 1\nassert identity(2) == 2"
    code_eval_runner._count_tests.cache_clear()

    assert code_eval_runner._count_tests(test_code) == 2
    assert code_eval_runner._count_tests(test_code) == 2

    cache_info = code_eval_runner._count_tests.cache_info()
    assert cache_info.hits == 1
    assert cache_info.misses == 1


def test_count_assert_nodes_counts_nested_asserts() -> None:
    module = code_eval_runner.ast.parse(
        textwrap.dedent(
            """
            assert identity(1) == 1
            if enabled:
                assert identity(2) == 2
            else:
                with context:
                    assert identity(3) == 3
            try:
                assert identity(4) == 4
            except Exception:
                assert identity(5) == 5
            finally:
                assert identity(6) == 6
            def check():
                assert identity(7) == 7
            class Nested:
                assert identity(8) == 8
            match status:
                case "ok":
                    assert identity(9) == 9
            """
        ),
        filename="<tests>",
        mode="exec",
    )

    assert code_eval_runner._count_assert_nodes(module) == 9


def test_count_assert_nodes_uses_exact_type_for_direct_asserts() -> None:
    module = code_eval_runner.ast.parse(
        "value = identity(0)\nassert identity(1) == 1\nassert identity(2) == 2",
        filename="<tests>",
        mode="exec",
    )

    def fail_assert_isinstance(node: object, class_or_tuple: object) -> bool:
        if class_or_tuple is code_eval_runner.ast.Assert:  # pragma: no cover
            raise AssertionError(
                "direct assert counting should use exact type checks"
            )
        return isinstance(node, class_or_tuple)

    assert code_eval_runner._count_assert_nodes(module, _isinstance=fail_assert_isinstance) == 2


def test_count_assert_nodes_fast_paths_all_top_level_asserts() -> None:
    module = code_eval_runner.ast.parse(
        "\n".join(f"assert identity({index}) == {index}" for index in range(16)),
        filename="<tests>",
        mode="exec",
    )

    def fail_isinstance(*args, **kwargs):
        raise AssertionError(  # pragma: no cover - regression-only failure path
            "all-assert modules should return without stack traversal"
        )

    assert code_eval_runner._count_assert_nodes(module, _isinstance=fail_isinstance) == 16


def test_count_assert_nodes_caches_repeated_module_counts() -> None:
    module = code_eval_runner.ast.parse(
        "value = identity(0)\nif enabled:\n    assert identity(1) == 1",
        filename="<tests>",
        mode="exec",
    )

    assert code_eval_runner._count_assert_nodes(module) == 1

    def fail_isinstance(*args, **kwargs):
        raise AssertionError(  # pragma: no cover - regression-only failure path
            "repeated assert-node counting should reuse the module-local count"
        )

    assert code_eval_runner._count_assert_nodes(module, _isinstance=fail_isinstance) == 1


def test_count_assert_nodes_returns_zero_without_asserts() -> None:
    module = code_eval_runner.ast.parse(
        "value = identity(1)\nif enabled:\n    value += identity(2)",
        filename="<tests>",
        mode="exec",
    )

    assert code_eval_runner._count_assert_nodes(module) == 0


def test_count_nonblank_test_lines_matches_splitlines_semantics() -> None:
    samples = [
        "\n assert one\r\n\t\rassert two\n   \nassert three",
        "\r\n\t\r\nassert one\rassert two\n\u2003assert three\n",
        "case one\x1fcontinued\n\t\x1fcase two\x1ccase three",
        "case one\vcase two\fcase three\x1ccase four\x1dcase five\x1ecase six\x85case seven\u2028case eight\u2029case nine",
        "   \n\t\r\n\r",
    ]

    for test_code in samples:
        assert code_eval_runner._count_nonblank_test_lines(test_code) == len(
            [line for line in test_code.splitlines() if line.strip()]
        )


def test_count_tests_fallback_counts_nonblank_lines() -> None:
    assert code_eval_runner._count_tests("def broken(:\nassert one\nassert two") == 3


def test_count_tests_no_assert_fallback_counts_nonblank_lines() -> None:
    test_code = textwrap.dedent(
        """
        def check(candidate):
            return candidate(1)

        check(identity)
        """
    ).strip()

    assert code_eval_runner._count_tests(test_code) == 3


class _SplitlinesGuard(str):
    def splitlines(self, *args, **kwargs):
        raise AssertionError(  # pragma: no cover - regression-only failure path
            "large fallback test counting should stream without splitlines"
        )


def test_count_tests_no_assert_fast_path_skips_ast_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    code_eval_runner._count_tests.cache_clear()

    def fail_parse(*args, **kwargs):
        raise AssertionError(  # pragma: no cover - regression-only failure path
            "no-assert fallback should not parse the test AST"
        )

    monkeypatch.setattr(code_eval_runner.ast, "parse", fail_parse)

    assert code_eval_runner._count_tests("setup()\nrun_case(identity)\n") == 2


def test_count_tests_ignores_assert_tokens_in_comments_and_strings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    code_eval_runner._count_tests.cache_clear()
    test_code = textwrap.dedent(
        '''
        # assert appears in prose, not as a statement
        message = "assert should stay inside the string"
        details = """multi-line assert mention"""
        value = candidate(1)
        '''
    ).strip()

    def fail_parse(*args, **kwargs):
        raise AssertionError(  # pragma: no cover - regression-only failure path
            "comment/string assert mentions should use the non-AST fallback"
        )

    monkeypatch.setattr(code_eval_runner.ast, "parse", fail_parse)

    assert code_eval_runner._count_tests(test_code) == 4


def test_count_tests_preserves_inline_assert_statement_detection() -> None:
    code_eval_runner._count_tests.cache_clear()

    assert code_eval_runner._count_tests("setup(); assert identity(1) == 1") == 1


def test_count_tests_plain_assert_lines_skip_ast_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    code_eval_runner._count_tests.cache_clear()

    def fail_parse(*args, **kwargs):
        raise AssertionError(  # pragma: no cover - regression-only failure path
            "plain assert-only payloads should count assertion lines without AST parsing"
        )

    monkeypatch.setattr(code_eval_runner.ast, "parse", fail_parse)

    assert code_eval_runner._count_tests("assert one\n\tassert two\n\nassert three") == 3


def test_count_tests_plain_assert_fast_path_defers_mixed_statements() -> None:
    code_eval_runner._count_tests.cache_clear()

    assert code_eval_runner._count_tests("assert one\nvalue = candidate(1)") == 1


def test_plain_assert_line_counter_rejects_identifier_prefix() -> None:
    assert code_eval_runner._count_plain_assert_statement_lines("asser") == 0
    assert code_eval_runner._count_plain_assert_statement_lines("assert_valid_name") == 0


def test_plain_assert_line_counter_accepts_common_space_and_tab_boundaries() -> None:
    assert code_eval_runner._count_plain_assert_statement_lines("assert one\nassert\ttwo") == 2


def test_plain_assert_line_counter_accepts_unindented_space_fast_path() -> None:
    assert code_eval_runner._count_plain_assert_statement_lines("assert one\nassert two\n") == 2


def test_plain_assert_line_counter_counts_uniform_unindented_payload_without_line_walk() -> None:
    def fail_find(*args, **kwargs):  # pragma: no cover - regression-only failure path
        raise AssertionError("uniform unindented assert payloads should not line-walk")

    assert code_eval_runner._count_plain_assert_statement_lines("assert one\nassert two\nassert three", _find=fail_find) == 3


def test_assert_prescan_handles_boundary_and_literal_edges() -> None:
    assert code_eval_runner._may_contain_assert_statement("# assert only in trailing comment") is False
    assert code_eval_runner._may_contain_assert_statement("reassert = 'value'") is False
    assert code_eval_runner._may_contain_assert_statement("text = 'escaped \\\' assert'") is False
    assert code_eval_runner._may_contain_assert_statement('text = "unterminated assert') is False
    assert code_eval_runner._may_contain_assert_statement("if ready: assert value") is True


def test_assert_prescan_common_followers_skip_isalnum() -> None:
    def fail_isalnum(_value: str) -> bool:
        raise AssertionError(  # pragma: no cover - regression-only failure path
            "common assert followers should use direct membership"
        )

    assert (
        code_eval_runner._may_contain_assert_statement(
            "setup(); assert value\nassert\tother",
            _isalnum=fail_isalnum,
        )
        is True
    )


def test_assert_prescan_absent_token_uses_single_find_pass() -> None:
    class NoContainsString(str):
        def __contains__(self, value: object) -> bool:  # pragma: no cover - sentinel
            raise AssertionError("assert prescan should avoid a separate containment scan")

    test_code = NoContainsString("setup()\nrun_case(identity)\n")

    assert code_eval_runner._may_contain_assert_statement(test_code) is False


def test_count_tests_syntax_error_fallback_uses_nonblank_line_counter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def tracked_count(test_code: str) -> int:
        calls.append(test_code)
        return 5

    monkeypatch.setattr(code_eval_runner, "_count_nonblank_test_lines", tracked_count)
    code_eval_runner._count_tests.cache_clear()

    assert code_eval_runner._count_tests("def check(candidate):\n    return candidate(1)") == 5
    assert calls == ["def check(candidate):\n    return candidate(1)"]


def test_count_nonblank_lines_streams_without_filtered_list() -> None:
    test_code = _SplitlinesGuard(
        "\n".join("assert value" if index % 3 else "   " for index in range(100_000))
    )

    assert code_eval_runner._count_nonblank_test_lines(test_code) == 66_666


def test_count_nonblank_lines_streams_short_inputs_without_splitlines() -> None:
    test_code = _SplitlinesGuard("assert value\n   \nassert other")

    assert code_eval_runner._count_nonblank_test_lines(test_code) == 2


def test_read_limited_text_handles_missing_and_oversized_files(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.txt"
    assert code_eval_runner._read_limited_text(missing_path, 8) == ""
    assert code_eval_runner._read_limited_stdio(missing_path, 8) == ("", 0)

    empty_path = tmp_path / "empty.txt"
    empty_path.write_text("", encoding="utf-8")
    assert code_eval_runner._read_limited_stdio(empty_path, 4) == ("", 0)

    output_path = tmp_path / "output.txt"
    output_path.write_text("0123456789abcdef", encoding="utf-8")

    assert code_eval_runner._read_limited_text(output_path, 4) == "cdef"
    assert code_eval_runner._read_limited_stdio(output_path, 4) == ("cdef", 16)
    assert code_eval_runner._read_limited_stdio(output_path, 0) == ("", 16)

    directory_path = tmp_path / "directory"
    directory_path.mkdir()
    assert code_eval_runner._read_limited_stdio(directory_path, 4) == ("", 0)


def test_read_limited_stdio_handles_open_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_path = tmp_path / "output.txt"
    output_path.write_text("secret output", encoding="utf-8")

    def fake_open(path, flags, *args, **kwargs):
        raise FileNotFoundError(str(path))

    assert code_eval_runner._read_limited_stdio(
        output_path,
        4,
        _os_open=fake_open,
    ) == ("", 0)


def test_read_limited_stdio_ignores_close_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_path = tmp_path / "output.txt"
    output_path.write_text("0123456789abcdef", encoding="utf-8")

    def fake_close(fd: int) -> None:
        raise OSError("close failed")

    assert code_eval_runner._read_limited_stdio(
        output_path,
        4,
        _os_close=fake_close,
    ) == ("cdef", 16)


def test_read_limited_stdio_reads_oversized_tail_without_lseek(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_path = tmp_path / "output.txt"
    output_path.write_text("0123456789abcdef", encoding="utf-8")

    def fail_lseek(*args: object, **kwargs: object) -> int:  # pragma: no cover - sentinel
        raise AssertionError("oversized stdio tail reads should use positional pread")

    monkeypatch.setattr(code_eval_runner.os, "lseek", fail_lseek)

    assert code_eval_runner._read_limited_stdio(output_path, 4) == ("cdef", 16)


def test_read_limited_stdio_reuses_cached_os_bindings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_path = tmp_path / "output.txt"
    output_path.write_text("0123456789abcdef", encoding="utf-8")

    def fail_open(*args: object, **kwargs: object) -> int:  # pragma: no cover - sentinel
        raise AssertionError("stdio reads should use cached os.open binding")

    def fail_fstat(*args: object, **kwargs: object) -> object:  # pragma: no cover - sentinel
        raise AssertionError("stdio reads should use cached os.fstat binding")

    def fail_pread(*args: object, **kwargs: object) -> bytes:  # pragma: no cover - sentinel
        raise AssertionError("stdio reads should use cached os.pread binding")

    def fail_read(*args: object, **kwargs: object) -> bytes:  # pragma: no cover - sentinel
        raise AssertionError("stdio reads should use cached os.read binding")

    def fail_close(*args: object, **kwargs: object) -> None:  # pragma: no cover - sentinel
        raise AssertionError("stdio reads should use cached os.close binding")

    monkeypatch.setattr(code_eval_runner.os, "open", fail_open)
    monkeypatch.setattr(code_eval_runner.os, "fstat", fail_fstat)
    monkeypatch.setattr(code_eval_runner.os, "pread", fail_pread)
    monkeypatch.setattr(code_eval_runner.os, "read", fail_read)
    monkeypatch.setattr(code_eval_runner.os, "close", fail_close)

    assert code_eval_runner._read_limited_stdio(output_path, 4) == ("cdef", 16)


def test_read_limited_stdio_reuses_cached_rdonly_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_path = tmp_path / "output.txt"
    output_path.write_text("0123456789abcdef", encoding="utf-8")

    monkeypatch.setattr(code_eval_runner, "_OS_RDONLY", -1)

    assert code_eval_runner._read_limited_stdio(output_path, 4) == ("cdef", 16)


def test_output_limit_reuses_limited_stdio_sizes(monkeypatch) -> None:
    monkeypatch.setattr(code_eval_runner.shutil, "which", lambda _: "/usr/bin/sandbox-exec")
    read_paths: list[str] = []

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=0)

    def fake_read_limited_stdio(path: Path, byte_limit: int) -> tuple[str, int]:
        read_paths.append(path.name)
        if path.name == "stdout.txt":
            return "stdout-tail", byte_limit
        return "", 0

    monkeypatch.setattr(code_eval_runner.subprocess, "run", fake_run)
    monkeypatch.setattr(code_eval_runner, "_read_limited_stdio", fake_read_limited_stdio)

    result = run_python_code_evaluation(
        candidate_code="def identity(value):\n    return value",
        entry_point="identity",
        test_code="assert identity(1) == 1",
        stdout_limit_bytes=4096,
    )

    assert result.runtime_status == "error"
    assert result.test_status == "failed"
    assert "stdio limit" in result.failure_detail
    assert read_paths == ["stdout.txt", "stderr.txt"]


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


def test_sandbox_profile_reuses_static_runtime_fragments(
    tmp_path: Path,
    monkeypatch,
) -> None:
    code_eval_runner._sandbox_static_profile_fragments.cache_clear()
    code_eval_runner._sandbox_static_profile_key_cache_clear()
    runtime_calls = 0
    executable_calls = 0
    get_paths_calls = 0

    def fake_runtime_paths() -> tuple[Path, ...]:
        nonlocal runtime_calls
        runtime_calls += 1
        return (tmp_path / "python-runtime",)

    def fake_executable_paths() -> tuple[Path, ...]:
        nonlocal executable_calls
        executable_calls += 1
        return (tmp_path / "python",)

    def fake_get_paths() -> dict[str, str]:
        nonlocal get_paths_calls
        get_paths_calls += 1
        return {"stdlib": str(tmp_path / "stdlib")}

    monkeypatch.setattr(code_eval_runner, "_sandbox_runtime_read_paths", fake_runtime_paths)
    monkeypatch.setattr(code_eval_runner, "_sandbox_executable_paths", fake_executable_paths)
    monkeypatch.setattr(code_eval_runner.sysconfig, "get_paths", fake_get_paths)

    first_root = tmp_path / "eval-a"
    second_root = tmp_path / "eval-b"
    first_profile = code_eval_runner._sandbox_profile(temp_root=first_root)
    second_profile = code_eval_runner._sandbox_profile(temp_root=second_root)

    assert runtime_calls == 1
    assert executable_calls == 1
    assert get_paths_calls == 1
    assert str(first_root) in first_profile
    assert str(second_root) not in first_profile
    assert str(second_root) in second_profile
    assert str(tmp_path / "python-runtime") in second_profile

    code_eval_runner._sandbox_static_profile_fragments.cache_clear()
    code_eval_runner._sandbox_static_profile_key_cache_clear()


def test_sandbox_static_profile_key_reuses_cached_fingerprint_without_tuple_rebuild(
    monkeypatch,
) -> None:
    code_eval_runner._sandbox_static_profile_key_cache_clear()
    fingerprint_calls = 0
    original_fingerprint = code_eval_runner._sandbox_static_profile_environment_fingerprint

    def tracked_fingerprint() -> tuple[object, ...]:
        nonlocal fingerprint_calls
        fingerprint_calls += 1
        return original_fingerprint()

    monkeypatch.setattr(
        code_eval_runner,
        "_sandbox_static_profile_environment_fingerprint",
        tracked_fingerprint,
    )

    first_key = code_eval_runner._sandbox_static_profile_key()
    second_key = code_eval_runner._sandbox_static_profile_key()

    assert first_key is second_key
    assert fingerprint_calls == 1

    code_eval_runner._sandbox_static_profile_key_cache_clear()


def test_sandbox_temp_root_read_filters_elides_duplicate_resolved_path(
    tmp_path: Path,
) -> None:
    filters = code_eval_runner._sandbox_temp_root_read_filters(tmp_path)

    assert filters == f"(subpath {json.dumps(str(tmp_path))})"


def test_sandbox_temp_root_read_filters_preserves_relative_and_resolved_paths() -> None:
    temp_root = Path("relative-eval-root")
    filters = code_eval_runner._sandbox_temp_root_read_filters(temp_root)

    assert filters == (
        f"(subpath {json.dumps(str(temp_root))}) "
        f"(subpath {json.dumps(str(temp_root.resolve()))})"
    )


def test_sandbox_temp_root_read_filters_falls_back_when_resolve_raises() -> None:
    class BrokenTempRoot:
        def __str__(self) -> str:
            return "broken-temp-root"

        def resolve(self):
            raise OSError("broken resolve")

    filters = code_eval_runner._sandbox_temp_root_read_filters(cast(Path, BrokenTempRoot()))

    assert filters == f"(subpath {json.dumps('broken-temp-root')})"


def test_runner_script_reuses_precomputed_static_payload(monkeypatch) -> None:
    code_eval_runner._runner_script.cache_clear()
    calls = 0
    original_dedent = code_eval_runner.textwrap.dedent

    def tracked_dedent(text: str) -> str:
        nonlocal calls
        calls += 1
        return original_dedent(text)

    monkeypatch.setattr(code_eval_runner.textwrap, "dedent", tracked_dedent)

    first_script = code_eval_runner._runner_script()
    second_script = code_eval_runner._runner_script()

    assert calls == 0
    assert first_script is second_script
    assert first_script is code_eval_runner._RUNNER_SCRIPT
    assert "def main() -> int:" in first_script
    assert first_script.endswith("\n")

    code_eval_runner._runner_script.cache_clear()


def test_runner_script_loads_config_with_single_fd_read(tmp_path: Path) -> None:
    code_eval_runner._runner_script.cache_clear()
    script = code_eval_runner._runner_script()
    namespace: dict[str, object] = {"__name__": "melix_runner_probe"}
    exec(compile(script, "<melix-runner>", "exec"), namespace)
    load_config = namespace["_load_config"]

    config_path = tmp_path / "config.json"
    config_path.write_bytes(b'{"payload_path": "/tmp/payload.json", "memory_limit_mb": 64}')

    close_calls = 0
    os_module = cast(ModuleType, namespace["os"])
    original_close = os_module.close

    def tracked_close(fd: int) -> None:
        nonlocal close_calls
        close_calls += 1
        original_close(fd)

    typed_load_config = cast(Callable[..., dict[str, object]], load_config)
    assert typed_load_config(config_path, _os_close=tracked_close) == {
        "payload_path": "/tmp/payload.json",
        "memory_limit_mb": 64,
    }
    assert close_calls == 1
    assert "_os_read(fd, _os_fstat(fd).st_size)" in script
    assert "_read_bytes=Path.read_bytes" not in script
    assert "payload = _json_loads(_read_bytes(config_path))" not in script
    assert 'json.dumps(payload, separators=(",", ":"))' in script
    assert "json.load(file)" not in script

    code_eval_runner._runner_script.cache_clear()


def test_runner_script_loads_config_from_bytes(tmp_path: Path) -> None:
    test_runner_script_loads_config_with_single_fd_read(tmp_path)


def test_sandbox_profile_cache_key_tracks_python_environment(
    tmp_path: Path,
    monkeypatch,
) -> None:
    code_eval_runner._sandbox_static_profile_fragments.cache_clear()
    code_eval_runner._sandbox_static_profile_key_cache_clear()
    runtime_calls = 0

    def fake_runtime_paths() -> tuple[Path, ...]:
        nonlocal runtime_calls
        runtime_calls += 1
        return (tmp_path / f"runtime-{runtime_calls}",)

    monkeypatch.setattr(code_eval_runner, "_sandbox_runtime_read_paths", fake_runtime_paths)
    monkeypatch.setattr(code_eval_runner, "_sandbox_executable_paths", lambda: (tmp_path / "python",))

    monkeypatch.setattr(code_eval_runner.sys, "executable", str(tmp_path / "python-a"))
    first_profile = code_eval_runner._sandbox_profile(temp_root=tmp_path / "eval-a")
    second_profile = code_eval_runner._sandbox_profile(temp_root=tmp_path / "eval-b")
    monkeypatch.setattr(code_eval_runner.sys, "executable", str(tmp_path / "python-b"))
    third_profile = code_eval_runner._sandbox_profile(temp_root=tmp_path / "eval-c")

    assert runtime_calls == 2
    assert "runtime-1" in first_profile
    assert "runtime-1" in second_profile
    assert "runtime-2" in third_profile

    code_eval_runner._sandbox_static_profile_fragments.cache_clear()
    code_eval_runner._sandbox_static_profile_key_cache_clear()


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


def test_count_tests_no_assert_fallback_uses_nonblank_line_counter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def tracked_count(test_code: str) -> int:
        calls.append(test_code)
        return 5

    monkeypatch.setattr(code_eval_runner, "_count_nonblank_test_lines", tracked_count)
    code_eval_runner._count_tests.cache_clear()

    assert code_eval_runner._count_tests("def check(candidate):\n    return candidate(1)") == 5
    assert calls == ["def check(candidate):\n    return candidate(1)"]


def test_load_payload_file_rejects_invalid_and_non_mapping_json(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.json"
    assert code_eval_runner._load_payload_file(missing_path) is None

    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("{", encoding="utf-8")
    assert code_eval_runner._load_payload_file(invalid_path) is None

    list_path = tmp_path / "list.json"
    list_path.write_text("[1, 2, 3]", encoding="utf-8")
    assert code_eval_runner._load_payload_file(list_path) is None

    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps({"runtime_status": "ok"}), encoding="utf-8")
    assert code_eval_runner._load_payload_file(payload_path) == {"runtime_status": "ok"}


class _BytesOnlyPayloadPath:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.read_bytes_calls = 0

    def read_bytes(self) -> bytes:
        self.read_bytes_calls += 1
        return self.payload

    def read_text(self, *args: object, **kwargs: object) -> str:
        raise AssertionError("payload loading should not decode through read_text")


def test_load_payload_file_reads_payload_bytes_without_text_decode() -> None:
    payload_path = _BytesOnlyPayloadPath(
        json.dumps({"runtime_status": "ok", "tests_total": 3}).encode("utf-8")
    )

    assert code_eval_runner._load_payload_file(payload_path) == {
        "runtime_status": "ok",
        "tests_total": 3,
    }
    assert payload_path.read_bytes_calls == 1
    with pytest.raises(AssertionError):
        payload_path.read_text()


def test_load_payload_file_uses_os_read_for_real_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_bytes(json.dumps({"runtime_status": "ok", "tests_total": 3}).encode("utf-8"))

    def fail_read_bytes(self: Path) -> bytes:  # pragma: no cover
        raise AssertionError("real payload path should use fd-based byte loading")

    monkeypatch.setattr(Path, "read_bytes", fail_read_bytes)

    assert code_eval_runner._load_payload_file(payload_path) == {
        "runtime_status": "ok",
        "tests_total": 3,
    }


def test_read_payload_file_bytes_handles_fallback_and_fd_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingFallbackPath:
        def read_bytes(self) -> bytes:
            raise OSError("fallback read failed")

    assert (
        code_eval_runner._read_payload_file_bytes(cast(Path, FailingFallbackPath()))
        is None
    )

    assert (
        code_eval_runner._read_payload_file_bytes(
            Path("payload.json"),
            _os_open=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                OSError("open failed")
            ),
        )
        is None
    )

    def fail_fstat(_fd: int) -> object:
        raise OSError("fstat failed")

    assert (
        code_eval_runner._read_payload_file_bytes(
            Path("payload.json"),
            _os_open=lambda *_args, **_kwargs: 123,
            _os_fstat=fail_fstat,
        )
        is None
    )

    def fail_close(_fd: int) -> None:
        raise OSError("close failed")

    assert (
        code_eval_runner._read_payload_file_bytes(
            Path("payload.json"),
            _os_open=lambda *_args, **_kwargs: 123,
            _os_fstat=fail_fstat,
            _os_close=fail_close,
        )
        is None
    )


def test_read_payload_file_bytes_uses_bound_fd_helpers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_bytes(b'{"runtime_status":"ok"}')
    original_open = code_eval_runner._OS_OPEN
    original_fstat = code_eval_runner._OS_FSTAT
    original_read = code_eval_runner._OS_READ
    original_close = code_eval_runner._OS_CLOSE
    calls: list[str] = []

    def counted_open(path: os.PathLike[str], flags: int) -> int:
        calls.append("open")
        return original_open(path, flags)

    def counted_fstat(fd: int) -> object:
        calls.append("fstat")
        return original_fstat(fd)

    def counted_read(fd: int, size: int) -> bytes:
        calls.append("read")
        return original_read(fd, size)

    def counted_close(fd: int) -> None:
        calls.append("close")
        original_close(fd)

    def fail_os_open(*_args: object) -> int:  # pragma: no cover - regression guard
        raise AssertionError("payload byte loading should use bound os.open")

    monkeypatch.setattr(code_eval_runner.os, "open", fail_os_open)

    assert (
        code_eval_runner._read_payload_file_bytes(
            payload_path,
            _os_open=counted_open,
            _os_fstat=counted_fstat,
            _os_read=counted_read,
            _os_close=counted_close,
        )
        == b'{"runtime_status":"ok"}'
    )
    assert calls == ["open", "fstat", "read", "close"]


def test_read_payload_file_bytes_reuses_default_fd_helpers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_bytes(b'{"runtime_status":"ok"}')

    def fail_cached_open(*_args: object) -> int:  # pragma: no cover - regression guard
        raise AssertionError("payload byte loading should use default-bound os.open")

    monkeypatch.setattr(code_eval_runner, "_OS_OPEN", fail_cached_open)

    assert code_eval_runner._read_payload_file_bytes(payload_path) == b'{"runtime_status":"ok"}'


def test_load_payload_file_fast_path_extracts_runner_fields_without_metadata_parse() -> None:
    payload_path = _BytesOnlyPayloadPath(
        json.dumps(
            {
                "compile_status": "compiled",
                "failure_detail": "",
                "metadata": {f"case_{index}": "ignored" for index in range(128)},
                "runtime_status": "ok",
                "test_status": "passed",
                "tests_passed": 7,
                "tests_total": 7,
                "timeout_status": "ok",
            },
            sort_keys=True,
        ).encode("utf-8")
    )

    assert code_eval_runner._load_payload_file(payload_path) == {
        "compile_status": "compiled",
        "failure_detail": "",
        "runtime_status": "ok",
        "test_status": "passed",
        "tests_passed": 7,
        "tests_total": 7,
        "timeout_status": "ok",
    }
    assert payload_path.read_bytes_calls == 1


def test_load_payload_file_fast_path_extracts_sorted_payload_without_json_parse() -> None:
    payload_path = _BytesOnlyPayloadPath(
        json.dumps(
            {
                "failure_detail": "",
                "metadata": {f"case_{index}": "ignored" for index in range(128)},
                "runtime_status": "ok",
                "test_status": "passed",
                "tests_passed": 7,
                "tests_total": 7,
                "timeout_status": "ok",
            },
            sort_keys=True,
        ).encode("utf-8")
    )

    def fail_json_loads(*_args: object, **_kwargs: object) -> dict[str, object]:  # pragma: no cover
        raise AssertionError("sorted code-eval payload should stay on the fast path")

    assert (
        code_eval_runner._load_payload_file(cast(Path, payload_path), _loads=fail_json_loads)
        == {
            "failure_detail": "",
            "runtime_status": "ok",
            "test_status": "passed",
            "tests_passed": 7,
            "tests_total": 7,
            "timeout_status": "ok",
        }
    )
    assert payload_path.read_bytes_calls == 1


def test_sorted_payload_fast_path_uses_compact_field_offsets(monkeypatch) -> None:
    payload = json.dumps(
        {
            "failure_detail": "",
            "metadata": {f"case_{index}": "ignored" for index in range(128)},
            "runtime_status": "ok",
            "test_status": "passed",
            "tests_passed": 7,
            "tests_total": 7,
            "timeout_status": "ok",
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    def fail_generic_scanner(*_args: object, **_kwargs: object) -> int | None:  # pragma: no cover
        raise AssertionError("compact sorted payload should not use the whitespace scanner")

    monkeypatch.setattr(
        code_eval_runner,
        "_json_field_value_start_for_token",
        fail_generic_scanner,
    )

    assert code_eval_runner._extract_sorted_code_eval_payload_fields(payload) == {
        "failure_detail": "",
        "runtime_status": "ok",
        "test_status": "passed",
        "tests_passed": 7,
        "tests_total": 7,
        "timeout_status": "ok",
    }


def test_sorted_payload_fast_path_reuses_empty_failure_prefix(monkeypatch) -> None:
    payload = json.dumps(
        {
            "failure_detail": "",
            "metadata": {f"case_{index}": "ignored" for index in range(16)},
            "runtime_status": "ok",
            "test_status": "passed",
            "tests_passed": 7,
            "tests_total": 7,
            "timeout_status": "ok",
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert code_eval_runner._CODE_EVAL_SORTED_EMPTY_FAILURE_VALUE_START == payload.find(b'""')

    def fail_forward_compact_scanner(
        *_args: object, **_kwargs: object
    ) -> int | None:  # pragma: no cover
        raise AssertionError("leading empty failure_detail prefix should avoid scanning")

    monkeypatch.setattr(
        code_eval_runner,
        "_compact_json_field_value_start_for_token",
        fail_forward_compact_scanner,
    )

    assert code_eval_runner._extract_sorted_code_eval_payload_fields(payload) == {
        "failure_detail": "",
        "runtime_status": "ok",
        "test_status": "passed",
        "tests_passed": 7,
        "tests_total": 7,
        "timeout_status": "ok",
    }


def test_sorted_payload_fast_path_uses_bound_key_tokens(monkeypatch) -> None:
    payload = json.dumps(
        {
            "failure_detail": "",
            "metadata": {f"case_{index}": "ignored" for index in range(16)},
            "runtime_status": "ok",
            "test_status": "passed",
            "tests_passed": 7,
            "tests_total": 7,
            "timeout_status": "ok",
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    class FailingTokenDict(dict):
        def __getitem__(self, key: str) -> bytes:  # pragma: no cover
            raise AssertionError(f"sorted fast path should use bound key token for {key}")

    monkeypatch.setattr(code_eval_runner, "_CODE_EVAL_PAYLOAD_KEY_TOKENS", FailingTokenDict())

    assert code_eval_runner._extract_sorted_code_eval_payload_fields(payload) == {
        "failure_detail": "",
        "runtime_status": "ok",
        "test_status": "passed",
        "tests_passed": 7,
        "tests_total": 7,
        "timeout_status": "ok",
    }


def test_sorted_payload_fast_path_reuses_reverse_search_start(monkeypatch) -> None:
    payload = json.dumps(
        {
            "failure_detail": "",
            "metadata": {f"case_{index}": "ignored" for index in range(16)},
            "runtime_status": "ok",
            "test_status": "passed",
            "tests_passed": 7,
            "tests_total": 7,
            "timeout_status": "ok",
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    expected_start = code_eval_runner._CODE_EVAL_SORTED_EMPTY_FAILURE_VALUE_START + len(b'""')
    observed_starts: list[int] = []
    original_reverse = code_eval_runner._compact_json_field_value_start_for_token_reverse

    def tracking_reverse(
        payload_bytes: bytes,
        key_token: bytes,
        *,
        start: int = 0,
        end: int | None = None,
    ) -> int | None:
        observed_starts.append(start)
        return original_reverse(payload_bytes, key_token, start=start, end=end)

    monkeypatch.setattr(
        code_eval_runner,
        "_compact_json_field_value_start_for_token_reverse",
        tracking_reverse,
    )

    assert code_eval_runner._extract_sorted_code_eval_payload_fields(payload) == {
        "failure_detail": "",
        "runtime_status": "ok",
        "test_status": "passed",
        "tests_passed": 7,
        "tests_total": 7,
        "timeout_status": "ok",
    }
    assert observed_starts == [expected_start] * 5

    class BrokenTempRoot:
        def __str__(self) -> str:
            return "broken-temp-root"

        def resolve(self) -> object:
            raise OSError("broken resolve")

    assert code_eval_runner._sandbox_temp_root_read_filters(Path("relative-eval-root")) == (
        f"(subpath {json.dumps('relative-eval-root')}) "
        f"(subpath {json.dumps(os.path.realpath('relative-eval-root'))})"
    )
    assert code_eval_runner._sandbox_temp_root_read_filters(cast(Path, BrokenTempRoot())) == (
        f"(subpath {json.dumps('broken-temp-root')})"
    )


def test_sorted_payload_fast_path_skips_reserved_metadata_keys() -> None:
    payload_path = _BytesOnlyPayloadPath(
        json.dumps(
            {
                "failure_detail": "",
                "metadata": {
                    "runtime_status": "metadata should not be parsed",
                    "test_status": "metadata should not be parsed",
                    "tests_passed": "metadata should not be parsed",
                    "tests_total": "metadata should not be parsed",
                    "timeout_status": "metadata should not be parsed",
                },
                "runtime_status": "ok",
                "test_status": "passed",
                "tests_passed": 7,
                "tests_total": 7,
                "timeout_status": "ok",
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )

    def fail_json_loads(*_args: object, **_kwargs: object) -> dict[str, object]:  # pragma: no cover
        raise AssertionError("reserved metadata keys should not force full JSON parsing")

    assert code_eval_runner._load_payload_file(cast(Path, payload_path), _loads=fail_json_loads) == {
        "failure_detail": "",
        "runtime_status": "ok",
        "test_status": "passed",
        "tests_passed": 7,
        "tests_total": 7,
        "timeout_status": "ok",
    }


def test_compact_field_offset_fallback_reuses_known_key_index(monkeypatch) -> None:
    payload = b'{"metadata":{},"runtime_status" : "ok"}'
    key_token = b'"runtime_status"'
    original_start = payload.find(b'{}')

    def fail_generic_scanner(*_args: object, **_kwargs: object) -> int | None:  # pragma: no cover
        raise AssertionError("known compact key index should skip a second find")

    monkeypatch.setattr(code_eval_runner, "_json_field_value_start_for_token", fail_generic_scanner)

    assert (
        code_eval_runner._compact_json_field_value_start_for_token(
            payload,
            key_token,
            start=original_start,
        )
        == payload.find(b'"ok"')
    )
    assert (
        code_eval_runner._compact_json_field_value_start_for_token_reverse(
            payload,
            key_token,
            start=original_start,
        )
        == payload.find(b'"ok"')
    )


def test_json_field_value_start_after_key_index_handles_whitespace_edges() -> None:
    payload = b'{"runtime_status" : "ok", "tests_total": 2}'
    cursor = payload.find(b'"runtime_status"') + len(b'"runtime_status"')

    assert code_eval_runner._json_field_value_start_after_key_index(payload, cursor) == payload.find(b'"ok"')
    assert code_eval_runner._json_field_value_start_after_key_index(b'{"runtime_status" "ok"}', cursor) is None
    assert code_eval_runner._json_field_value_start_after_key_index(b'{"runtime_status": ', cursor) is None


def test_sorted_payload_fast_path_returns_none_for_missing_or_malformed_fields() -> None:
    assert (
        code_eval_runner._extract_sorted_code_eval_payload_fields(
            b'{"failure_detail":"","test_status":"passed","tests_passed":1,'
            b'"tests_total":1,"timeout_status":"ok"}'
        )
        is None
    )
    assert (
        code_eval_runner._extract_sorted_code_eval_payload_fields(
            b'{"failure_detail":"","runtime_status":"ok","test_status":"passed",'
            b'"tests_passed":x,"tests_total":1,"timeout_status":"ok"}'
        )
        is None
    )
    assert (
        code_eval_runner._extract_sorted_code_eval_payload_fields(
            b'{"failure_detail":"","runtime_status":"ok","test_status":"passed",'
            b'"tests_passed":1,"tests_total":x,"timeout_status":"ok"}'
        )
        is None
    )
    assert (
        code_eval_runner._extract_sorted_code_eval_payload_fields(
            b'{"failure_detail":"","runtime_status":"ok","test_status":"passed",'
            b'"tests_passed":1,"tests_total":1,"timeout_status":ok}'
        )
        is None
    )


def test_code_eval_payload_fast_path_decodes_known_status_values() -> None:
    payload = json.dumps(
        {
            "compile_status": "compiled",
            "runtime_status": "timeout",
            "timeout_status": "timed_out",
            "test_status": "failed",
            "tests_passed": 0,
            "tests_total": 3,
            "failure_detail": "",
        },
        separators=(",", ":"),
    ).encode("utf-8")

    assert code_eval_runner._extract_code_eval_payload_fields(payload) == {
        "compile_status": "compiled",
        "runtime_status": "timeout",
        "timeout_status": "timed_out",
        "test_status": "failed",
        "tests_passed": 0,
        "tests_total": 3,
        "failure_detail": "",
    }
    for known_value in (
        "",
        "compiled",
        "syntax_error",
        "not_run",
        "ok",
        "error",
        "timeout",
        "timed_out",
        "failed",
        "passed",
    ):
        token = known_value.encode("utf-8")
        assert (
            code_eval_runner._known_code_eval_payload_string_value(
                b'"' + token + b'"',
                1,
                len(token) + 1,
            )
            == known_value
        )
    assert (
        code_eval_runner._known_code_eval_payload_string_value(
            b'"custom_failure"',
            1,
            len(b'"custom_failure"') - 1,
        )
        is None
    )


@pytest.mark.parametrize(
    "unknown_value",
    [
        "no",
        "other",
        "fallow",
        "parsed",
        "notrun_",
        "timedup",
        "compilex",
        "timedout_",
        "syntaxerror_",
    ],
)
def test_code_eval_payload_known_value_ord_fast_path_rejects_same_length_unknowns(
    unknown_value: str,
) -> None:
    for known_value in (
        "ok",
        "error",
        "failed",
        "passed",
        "not_run",
        "timeout",
        "compiled",
        "timed_out",
        "syntax_error",
    ):
        known_token = known_value.encode("utf-8")
        assert (
            code_eval_runner._known_code_eval_payload_string_value(
                b'"' + known_token + b'"',
                1,
                len(known_token) + 1,
            )
            == known_value
        )

    token = unknown_value.encode("utf-8")

    assert (
        code_eval_runner._known_code_eval_payload_string_value(
            b'"' + token + b'"',
            1,
            len(token) + 1,
        )
        is None
    )


def test_code_eval_payload_missing_required_field_falls_back_to_json_parse(
    tmp_path: Path,
) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(
        json.dumps(
            {
                "metadata": {"preserved_by_fallback": True},
                "runtime_status": "ok",
                "test_status": "passed",
                "tests_passed": 2,
                "tests_total": 2,
                "timeout_status": "ok",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    assert code_eval_runner._load_payload_file(payload_path) == {
        "metadata": {"preserved_by_fallback": True},
        "runtime_status": "ok",
        "test_status": "passed",
        "tests_passed": 2,
        "tests_total": 2,
        "timeout_status": "ok",
    }


def test_load_payload_file_fast_path_reuses_precomputed_key_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    payload_path = _BytesOnlyPayloadPath(
        json.dumps(
            {
                "compile_status": "compiled",
                "failure_detail": "",
                "runtime_status": "ok",
                "test_status": "passed",
                "tests_passed": 2,
                "tests_total": 2,
                "timeout_status": "ok",
            },
            sort_keys=True,
        ).encode("utf-8")
    )

    def fail_json_dumps(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("known code-eval payload keys should use cached tokens")

    monkeypatch.setattr(code_eval_runner.json, "dumps", fail_json_dumps)

    assert code_eval_runner._load_payload_file(payload_path) == {
        "compile_status": "compiled",
        "failure_detail": "",
        "runtime_status": "ok",
        "test_status": "passed",
        "tests_passed": 2,
        "tests_total": 2,
        "timeout_status": "ok",
    }

    whitespace_payload_path = _BytesOnlyPayloadPath(
        b'  {"compile_status":"compiled","runtime_status":"ok",'
        b'"timeout_status":"ok","test_status":"passed",'
        b'"tests_passed":1,"tests_total":1,"failure_detail":""}\n'
    )
    assert code_eval_runner._load_payload_file(whitespace_payload_path) == {
        "compile_status": "compiled",
        "runtime_status": "ok",
        "timeout_status": "ok",
        "test_status": "passed",
        "tests_passed": 1,
        "tests_total": 1,
        "failure_detail": "",
    }

    with pytest.raises(AssertionError, match="known code-eval payload keys"):
        code_eval_runner._json_field_value_start(b'{"other":1}', "other")


def test_load_payload_file_fast_path_falls_back_for_unexpected_key_order() -> None:
    payload_path = _BytesOnlyPayloadPath(
        json.dumps(
            {
                "tests_total": 3,
                "failure_detail": "",
                "timeout_status": "ok",
                "tests_passed": 3,
                "compile_status": "compiled",
                "test_status": "passed",
                "runtime_status": "ok",
            },
            sort_keys=False,
        ).encode("utf-8")
    )

    assert code_eval_runner._load_payload_file(payload_path) == {
        "compile_status": "compiled",
        "failure_detail": "",
        "runtime_status": "ok",
        "test_status": "passed",
        "tests_passed": 3,
        "tests_total": 3,
        "timeout_status": "ok",
    }


def test_load_payload_file_fast_path_falls_back_for_escaped_fields(tmp_path: Path) -> None:
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(
        json.dumps(
            {
                "failure_detail": "line one\\nline two",
                "runtime_status": "error",
                "test_status": "failed",
                "tests_passed": 0,
                "tests_total": 1,
                "timeout_status": "ok",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    assert code_eval_runner._load_payload_file(payload_path) == {
        "failure_detail": "line one\\nline two",
        "runtime_status": "error",
        "test_status": "failed",
        "tests_passed": 0,
        "tests_total": 1,
        "timeout_status": "ok",
    }


def test_payload_fast_path_field_extractors_cover_malformed_edges() -> None:
    assert code_eval_runner._json_object_payload_bounds(b'{"runtime_status":"ok"}') == (0, 22)
    assert code_eval_runner._json_object_payload_bounds(b' \n {"runtime_status":"ok"}\t ') == (3, 25)
    assert code_eval_runner._json_object_payload_bounds(b"   ") is None
    assert code_eval_runner._json_object_payload_bounds(b' {"runtime_status":"ok"] ') is None
    assert code_eval_runner._json_field_value_start(b'{"runtime_status":"ok"}', "runtime_status") == 18
    assert code_eval_runner._json_field_value_start(b'{"runtime_status" : "ok"}', "runtime_status") == 20
    assert code_eval_runner._json_field_value_start(b'{"runtime_status" "ok"}', "runtime_status") is None
    assert code_eval_runner._json_field_value_start(b'{"runtime_status": ', "runtime_status") is None
    assert code_eval_runner._extract_json_string_field(b'{"failure_detail":"ok"}', "failure_detail") == "ok"
    assert code_eval_runner._extract_json_string_field(b'{"failure_detail":"oops}', "failure_detail") is None
    assert code_eval_runner._extract_json_string_field(b'{"failure_detail":"line\\nbreak"}', "failure_detail") is None
    assert code_eval_runner._extract_json_int_field(b'{"tests_passed":-7}', "tests_passed") == -7
    assert code_eval_runner._extract_json_int_field(b'{"tests_total":12345}', "tests_total") == 12345
    assert code_eval_runner._extract_json_int_field_value_and_end(b'-42, "next": 1', 0) == (-42, 3)
    assert code_eval_runner._extract_json_int_field(b'{"tests_total":-}', "tests_total") is None
    assert code_eval_runner._extract_json_int_field(b'{"tests_total": }', "tests_total") is None


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
