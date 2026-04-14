from __future__ import annotations

import ast
from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap

_PAYLOAD_SENTINEL = "__MELIX_CODE_EVAL_PAYLOAD__:"


@dataclass(frozen=True)
class CodeEvaluationResult:
    compile_status: str
    runtime_status: str
    timeout_status: str
    test_status: str
    tests_passed: int
    tests_total: int
    failure_detail: str

    @property
    def passed(self) -> bool:
        return (
            self.compile_status == "compiled"
            and self.runtime_status == "ok"
            and self.timeout_status == "ok"
            and self.test_status == "passed"
        )


def run_python_code_evaluation(
    *,
    candidate_code: str,
    entry_point: str,
    test_code: str,
    timeout_seconds: int = 3,
    memory_limit_mb: int = 256,
    stdout_limit_bytes: int = 32_768,
    ) -> CodeEvaluationResult:
    try:
        compile(candidate_code, "<candidate>", "exec")
    except SyntaxError as exc:
        return CodeEvaluationResult(
            compile_status="syntax_error",
            runtime_status="not_run",
            timeout_status="ok",
            test_status="not_run",
            tests_passed=0,
            tests_total=_count_tests(test_code),
            failure_detail=str(exc),
        )

    sandbox_exec = shutil.which("sandbox-exec")
    if not sandbox_exec:
        return CodeEvaluationResult(
            compile_status="compiled",
            runtime_status="error",
            timeout_status="ok",
            test_status="failed",
            tests_passed=0,
            tests_total=_count_tests(test_code),
            failure_detail="sandbox-exec is unavailable on this host.",
        )

    with tempfile.TemporaryDirectory(prefix="melix-code-eval-") as temp_dir:
        temp_root = Path(temp_dir)
        candidate_path = temp_root / "candidate.py"
        config_path = temp_root / "config.json"
        runner_path = temp_root / "runner.py"
        candidate_path.write_text(candidate_code, encoding="utf-8")
        config_path.write_text(
            json.dumps(
                {
                    "candidate_path": str(candidate_path),
                    "entry_point": entry_point,
                    "test_code": test_code,
                    "memory_limit_mb": memory_limit_mb,
                }
            ),
            encoding="utf-8",
        )
        runner_path.write_text(_runner_script(), encoding="utf-8")

        try:
            completed = subprocess.run(
                [
                    sandbox_exec,
                    "-p",
                    _sandbox_profile(temp_root=temp_root),
                    str(_sandbox_python_executable()),
                    "-I",
                    "-S",
                    str(runner_path),
                    str(config_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=str(temp_root),
                env={
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONNOUSERSITE": "1",
                    "HOME": str(temp_root),
                    "TMPDIR": str(temp_root),
                },
            )
        except subprocess.TimeoutExpired:
            return CodeEvaluationResult(
                compile_status="compiled",
                runtime_status="timeout",
                timeout_status="timed_out",
                test_status="not_run",
                tests_passed=0,
                tests_total=_count_tests(test_code),
                failure_detail=f"Timed out after {timeout_seconds}s",
            )

        stdout = completed.stdout[-stdout_limit_bytes:].strip()
        stderr = completed.stderr[-stdout_limit_bytes:].strip()
        payload = _load_payload(stdout)
        if payload is None:
            detail = stderr or stdout or f"Subprocess exited with status {completed.returncode}"
            return CodeEvaluationResult(
                compile_status="compiled",
                runtime_status="error",
                timeout_status="ok",
                test_status="failed",
                tests_passed=0,
                tests_total=_count_tests(test_code),
                failure_detail=detail,
            )

        return CodeEvaluationResult(
            compile_status=str(payload.get("compile_status", "compiled")),
            runtime_status=str(payload.get("runtime_status", "error")),
            timeout_status=str(payload.get("timeout_status", "ok")),
            test_status=str(payload.get("test_status", "failed")),
            tests_passed=int(payload.get("tests_passed", 0) or 0),
            tests_total=int(payload.get("tests_total", 0) or 0),
            failure_detail=str(payload.get("failure_detail", "")),
        )


def _count_tests(test_code: str) -> int:
    try:
        module = ast.parse(test_code, filename="<tests>", mode="exec")
    except SyntaxError:
        return len([line for line in test_code.splitlines() if line.strip()])
    assert_count = sum(1 for node in ast.walk(module) if isinstance(node, ast.Assert))
    return assert_count or len([line for line in test_code.splitlines() if line.strip()])


def _load_payload(stdout: str) -> dict[str, object] | None:
    if not stdout:
        return None
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith(_PAYLOAD_SENTINEL):
            return _decode_payload(line.removeprefix(_PAYLOAD_SENTINEL))
    if lines:
        return _decode_payload(lines[-1])
    return _decode_payload(stdout)


def _decode_payload(raw_payload: str) -> dict[str, object] | None:
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _sandbox_profile(*, temp_root: Path) -> str:
    executable_paths = _sandbox_executable_paths()
    runtime_paths = _sandbox_runtime_read_paths()
    clauses = [
        "(version 1)",
        "(allow default)",
        "(deny network*)",
        "(deny file-write*)",
        "(deny process-fork)",
        "(deny process-exec)",
    ]
    if executable_paths:
        executable_filters = " ".join(
            f"(literal {json.dumps(str(path))})"
            for path in executable_paths
        )
        clauses.append(f"(allow process-exec {executable_filters})")
    home_path = Path.home()
    clauses.append(f"(deny file-read* (subpath {json.dumps(str(home_path))}))")
    read_filters = " ".join(
        f"(subpath {json.dumps(str(path))})"
        for path in (*runtime_paths, temp_root)
    )
    clauses.append(f"(allow file-read* {read_filters})")
    return " ".join(clauses)


def _sandbox_executable_paths() -> tuple[Path, ...]:
    resolved = _sandbox_python_executable()
    paths = [resolved]
    launcher_path = resolved.parent.parent / "Resources" / "Python.app" / "Contents" / "MacOS" / "Python"
    if launcher_path.exists():
        paths.append(launcher_path)
    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        deduped.append(path)
    return tuple(deduped)


def _sandbox_python_executable() -> Path:
    return Path(sys.executable).resolve()


def _sandbox_runtime_read_paths() -> tuple[Path, ...]:
    roots = [_sandbox_python_executable().parent.parent]
    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in roots:
        if path in seen:
            continue
        seen.add(path)
        deduped.append(path)
    return tuple(deduped)


def _runner_script() -> str:
    script = """
        from __future__ import annotations

        import ast
        import importlib.util
        import json
        import resource
        import sys
        import traceback

        PAYLOAD_SENTINEL = __PAYLOAD_SENTINEL__


        class _AssertInstrumentor(ast.NodeTransformer):
            def __init__(self) -> None:
                self.tests_total = 0

            def visit_Assert(self, node: ast.Assert):
                self.tests_total += 1
                self.generic_visit(node)
                instrumented = ast.Expr(
                    value=ast.Call(
                        func=ast.Name(id="__melix_assert", ctx=ast.Load()),
                        args=[
                            node.test,
                            node.msg if node.msg is not None else ast.Constant(value=None),
                        ],
                        keywords=[],
                    )
                )
                return ast.copy_location(instrumented, node)


        def _compile_tests(test_code: str):
            module = ast.parse(test_code, filename="<tests>", mode="exec")
            instrumentor = _AssertInstrumentor()
            instrumented = instrumentor.visit(module)
            ast.fix_missing_locations(instrumented)
            return compile(instrumented, "<tests>", "exec"), instrumentor.tests_total


        def _set_address_space_limit(memory_limit_bytes: int) -> None:
            rlimit_as = getattr(resource, "RLIMIT_AS", None)
            if rlimit_as is None:
                return
            current_soft, current_hard = resource.getrlimit(rlimit_as)
            if current_hard == resource.RLIM_INFINITY:
                address_space_limit = memory_limit_bytes
            else:
                address_space_limit = min(memory_limit_bytes, current_hard)
            try:
                resource.setrlimit(rlimit_as, (address_space_limit, current_hard))
            except (OSError, ValueError):
                pass


        def main() -> int:
            with open(sys.argv[1], "r", encoding="utf-8") as file:
                config = json.load(file)
            memory_limit_mb = int(config.get("memory_limit_mb", 256) or 256)
            memory_limit_bytes = memory_limit_mb * 1024 * 1024
            _set_address_space_limit(memory_limit_bytes)
            cpu_soft, cpu_hard = resource.getrlimit(resource.RLIMIT_CPU)
            cpu_limit = min(2, cpu_hard) if cpu_hard != resource.RLIM_INFINITY else 2
            try:
                resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_hard))
            except (OSError, ValueError):
                pass

            candidate_path = config["candidate_path"]
            entry_point = str(config.get("entry_point", ""))
            test_code = str(config.get("test_code", ""))
            tests_total = 0
            tests_passed = 0

            try:
                spec = importlib.util.spec_from_file_location("candidate", candidate_path)
                if spec is None or spec.loader is None:
                    raise RuntimeError("Unable to load candidate module")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if entry_point and hasattr(module, entry_point) is False:
                    raise AttributeError(f"Missing entry point: {entry_point}")

                namespace = dict(module.__dict__)
                test_state = {"passed": 0}

                def __melix_assert(condition, message=None):
                    if not condition:
                        if message is None:
                            raise AssertionError()
                        raise AssertionError(message)
                    test_state["passed"] += 1

                namespace["__melix_assert"] = __melix_assert
                compiled_tests, tests_total = _compile_tests(test_code)
                exec(compiled_tests, namespace, namespace)
                tests_passed = int(test_state["passed"])

                payload = {
                    "compile_status": "compiled",
                    "runtime_status": "ok",
                    "timeout_status": "ok",
                    "test_status": "passed",
                    "tests_passed": tests_passed,
                    "tests_total": tests_total,
                    "failure_detail": "",
                }
            except AssertionError as exc:
                payload = {
                    "compile_status": "compiled",
                    "runtime_status": "ok",
                    "timeout_status": "ok",
                    "test_status": "failed",
                    "tests_passed": locals().get("tests_passed", 0),
                    "tests_total": locals().get("tests_total", 0),
                    "failure_detail": str(exc) or "AssertionError",
                }
            except BaseException as exc:
                payload = {
                    "compile_status": "compiled",
                    "runtime_status": "error",
                    "timeout_status": "ok",
                    "test_status": "failed",
                    "tests_passed": locals().get("tests_passed", 0),
                    "tests_total": locals().get("tests_total", 0),
                    "failure_detail": "".join(traceback.format_exception_only(type(exc), exc)).strip(),
                }

            print(PAYLOAD_SENTINEL + json.dumps(payload))
            return 0


        if __name__ == "__main__":
            raise SystemExit(main())
        """
    return textwrap.dedent(script).replace("__PAYLOAD_SENTINEL__", repr(_PAYLOAD_SENTINEL)).strip() + "\n"
