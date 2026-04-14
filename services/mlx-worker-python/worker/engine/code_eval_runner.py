from __future__ import annotations

import ast
from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import textwrap

_CODE_BLOCK_PATTERN = re.compile(r"```(?:python)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
_DEFAULT_STDIO_LIMIT_BYTES = 32_768


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


def extract_candidate_code(raw_response: str) -> tuple[str, str]:
    normalized = raw_response.strip()
    if not normalized:
        return "", "empty_prediction"
    matches = _CODE_BLOCK_PATTERN.findall(normalized)
    if matches:
        return matches[-1].strip(), "parsed_code_block"
    return normalized, "parsed_code"


def is_code_execution_policy_supported(code_exec_policy: str) -> bool:
    return code_exec_policy.strip() == "sandboxed" and bool(shutil.which("sandbox-exec"))


def run_python_code_evaluation(
    *,
    candidate_code: str,
    entry_point: str,
    test_code: str,
    timeout_seconds: int = 3,
    memory_limit_mb: int = 256,
    stdout_limit_bytes: int = _DEFAULT_STDIO_LIMIT_BYTES,
) -> CodeEvaluationResult:
    tests_total = _count_tests(test_code)
    try:
        compile(candidate_code, "<candidate>", "exec")
    except SyntaxError as exc:
        return CodeEvaluationResult(
            compile_status="syntax_error",
            runtime_status="not_run",
            timeout_status="ok",
            test_status="not_run",
            tests_passed=0,
            tests_total=tests_total,
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
            tests_total=tests_total,
            failure_detail="sandbox-exec is unavailable on this host.",
        )

    with tempfile.TemporaryDirectory(prefix="melix-code-eval-") as temp_dir:
        temp_root = Path(temp_dir).resolve()
        candidate_path = temp_root / "candidate.py"
        config_path = temp_root / "config.json"
        runner_path = temp_root / "runner.py"
        payload_path = temp_root / "payload.json"
        stdout_path = temp_root / "stdout.txt"
        stderr_path = temp_root / "stderr.txt"
        candidate_path.write_text(candidate_code, encoding="utf-8")
        config_path.write_text(
            json.dumps(
                {
                    "candidate_path": str(candidate_path),
                    "entry_point": entry_point,
                    "test_code": test_code,
                    "memory_limit_mb": memory_limit_mb,
                    "payload_path": str(payload_path),
                    "stdio_limit_bytes": int(max(stdout_limit_bytes, 1024)),
                }
            ),
            encoding="utf-8",
        )
        runner_path.write_text(_runner_script(), encoding="utf-8")

        with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
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
                    stdout=stdout_handle,
                    stderr=stderr_handle,
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
                stdout_tail = _read_limited_text(stdout_path, stdout_limit_bytes)
                stderr_tail = _read_limited_text(stderr_path, stdout_limit_bytes)
                detail = _timeout_failure_detail(
                    timeout_seconds=timeout_seconds,
                    stdout_tail=stdout_tail,
                    stderr_tail=stderr_tail,
                )
                return CodeEvaluationResult(
                    compile_status="compiled",
                    runtime_status="timeout",
                    timeout_status="timed_out",
                    test_status="not_run",
                    tests_passed=0,
                    tests_total=tests_total,
                    failure_detail=detail,
                )

        stdout_tail = _read_limited_text(stdout_path, stdout_limit_bytes)
        stderr_tail = _read_limited_text(stderr_path, stdout_limit_bytes)
        output_limit_exceeded = any(
            path.exists() and path.stat().st_size >= stdout_limit_bytes
            for path in (stdout_path, stderr_path)
        )
        if output_limit_exceeded:
            return CodeEvaluationResult(
                compile_status="compiled",
                runtime_status="error",
                timeout_status="ok",
                test_status="failed",
                tests_passed=0,
                tests_total=tests_total,
                failure_detail=_output_limit_failure_detail(
                    stdio_limit_bytes=stdout_limit_bytes,
                    stdout_tail=stdout_tail,
                    stderr_tail=stderr_tail,
                ),
            )

        payload = _load_payload_file(payload_path)
        if payload is None:
            detail = (
                stderr_tail
                or stdout_tail
                or f"Subprocess exited with status {completed.returncode} without a result payload."
            )
            return CodeEvaluationResult(
                compile_status="compiled",
                runtime_status="error",
                timeout_status="ok",
                test_status="failed",
                tests_passed=0,
                tests_total=tests_total,
                failure_detail=detail,
            )

        return CodeEvaluationResult(
            compile_status=str(payload.get("compile_status", "compiled")),
            runtime_status=str(payload.get("runtime_status", "error")),
            timeout_status=str(payload.get("timeout_status", "ok")),
            test_status=str(payload.get("test_status", "failed")),
            tests_passed=int(payload.get("tests_passed", 0) or 0),
            tests_total=int(payload.get("tests_total", tests_total) or tests_total),
            failure_detail=str(payload.get("failure_detail", "")),
        )


def _count_tests(test_code: str) -> int:
    try:
        module = ast.parse(test_code, filename="<tests>", mode="exec")
    except SyntaxError:
        return len([line for line in test_code.splitlines() if line.strip()])
    assert_count = sum(1 for node in ast.walk(module) if isinstance(node, ast.Assert))
    return assert_count or len([line for line in test_code.splitlines() if line.strip()])


def _load_payload_file(payload_path: Path) -> dict[str, object] | None:
    if not payload_path.exists():
        return None
    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _read_limited_text(path: Path, byte_limit: int) -> str:
    if not path.exists():
        return ""
    with path.open("rb") as file:
        if path.stat().st_size > byte_limit:
            file.seek(-byte_limit, 2)
        return file.read().decode("utf-8", errors="replace").strip()


def _timeout_failure_detail(*, timeout_seconds: int, stdout_tail: str, stderr_tail: str) -> str:
    summary = _summarize_stdio(stdout_tail=stdout_tail, stderr_tail=stderr_tail)
    if summary:
        return f"Timed out after {timeout_seconds}s. {summary}"
    return f"Timed out after {timeout_seconds}s"


def _output_limit_failure_detail(
    *,
    stdio_limit_bytes: int,
    stdout_tail: str,
    stderr_tail: str,
) -> str:
    summary = _summarize_stdio(stdout_tail=stdout_tail, stderr_tail=stderr_tail)
    if summary:
        return f"Code execution exceeded the {stdio_limit_bytes}-byte stdio limit. {summary}"
    return f"Code execution exceeded the {stdio_limit_bytes}-byte stdio limit."


def _summarize_stdio(*, stdout_tail: str, stderr_tail: str) -> str:
    parts: list[str] = []
    if stdout_tail:
        parts.append(f"stdout tail: {stdout_tail}")
    if stderr_tail:
        parts.append(f"stderr tail: {stderr_tail}")
    return " | ".join(parts)


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
    denied_read_roots = (
        Path("/Applications"),
        Path("/Library"),
        Path("/System"),
        Path("/Users"),
        Path("/Volumes"),
        Path("/etc"),
        Path("/opt"),
        Path("/private"),
        Path("/tmp"),
        Path("/usr"),
    )
    clauses.extend(
        f"(deny file-read* (subpath {json.dumps(str(path))}))"
        for path in denied_read_roots
    )
    if executable_paths:
        executable_filters = " ".join(
            f"(literal {json.dumps(str(path))})"
            for path in executable_paths
        )
        clauses.append(f"(allow process-exec {executable_filters})")
    read_filters = " ".join(
        f"(subpath {json.dumps(str(path))})"
        for path in _sandbox_allow_path_variants((*runtime_paths, temp_root))
    )
    clauses.append(f"(allow file-read* {read_filters})")
    clauses.append(f"(allow file-write* (subpath {json.dumps(str(temp_root))}))")
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
    roots: list[Path] = [
        _sandbox_python_executable().parent.parent,
        Path(sys.prefix).resolve(),
        Path(sys.exec_prefix).resolve(),
        Path(sys.base_prefix).resolve(),
        Path(sys.base_exec_prefix).resolve(),
        Path("/System/Library"),
        Path("/usr/lib"),
    ]
    for raw_path in sysconfig.get_paths().values():
        if raw_path:
            roots.append(Path(raw_path).resolve())
    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in roots:
        if path in seen:
            continue
        seen.add(path)
        deduped.append(path)
    return tuple(deduped)


def _sandbox_allow_path_variants(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        variants = [path]
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        variants.append(resolved)
        for variant in variants:
            if variant in seen:
                continue
            seen.add(variant)
            deduped.append(variant)
    return tuple(deduped)


def _runner_script() -> str:
    script = """
        from __future__ import annotations

        import ast
        import importlib.util
        import json
        from pathlib import Path
        import resource
        import sys
        import traceback


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


        def _set_limits(memory_limit_bytes: int, stdio_limit_bytes: int) -> None:
            rlimit_as = getattr(resource, "RLIMIT_AS", None)
            if rlimit_as is not None:
                current_soft, current_hard = resource.getrlimit(rlimit_as)
                if current_hard == resource.RLIM_INFINITY:
                    address_space_limit = memory_limit_bytes
                else:
                    address_space_limit = min(memory_limit_bytes, current_hard)
                try:
                    resource.setrlimit(rlimit_as, (address_space_limit, current_hard))
                except (OSError, ValueError):
                    pass
            cpu_soft, cpu_hard = resource.getrlimit(resource.RLIMIT_CPU)
            cpu_limit = min(2, cpu_hard) if cpu_hard != resource.RLIM_INFINITY else 2
            try:
                resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_hard))
            except (OSError, ValueError):
                pass
            try:
                resource.setrlimit(resource.RLIMIT_FSIZE, (stdio_limit_bytes, stdio_limit_bytes))
            except (OSError, ValueError):
                pass
            try:
                resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            except (OSError, ValueError):
                pass


        def main() -> int:
            with open(sys.argv[1], "r", encoding="utf-8") as file:
                config = json.load(file)
            memory_limit_mb = int(config.get("memory_limit_mb", 256) or 256)
            stdio_limit_bytes = int(config.get("stdio_limit_bytes", 32768) or 32768)
            payload_path = Path(config["payload_path"])
            _set_limits(memory_limit_mb * 1024 * 1024, stdio_limit_bytes)

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

            payload_path.write_text(json.dumps(payload), encoding="utf-8")
            return 0


        if __name__ == "__main__":
            raise SystemExit(main())
        """
    return textwrap.dedent(script).strip() + "\n"
