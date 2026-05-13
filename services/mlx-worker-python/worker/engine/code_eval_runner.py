from __future__ import annotations

import ast
from dataclasses import dataclass
from functools import lru_cache
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import textwrap

_DEFAULT_STDIO_LIMIT_BYTES = 32_768
_JSON_LOADS = json.loads
_JSON_DECODE_ERROR = json.JSONDecodeError


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

    closing = normalized.rfind("```")
    if closing >= 0:
        opening = normalized.rfind("```", 0, closing)
        if opening >= 0:
            if opening >= 0:
                content_start = _code_block_content_start(normalized, opening + 3)
                candidate = normalized[content_start:closing].strip()
                if candidate:
                    return candidate, "parsed_code_block"
                if normalized.count("```") % 2 == 0:
                    return candidate, "parsed_code_block"
                closing = opening
                opening = normalized.rfind("```", 0, closing)
                if opening >= 0:
                    content_start = _code_block_content_start(normalized, opening + 3)
                    return normalized[content_start:closing].strip(), "parsed_code_block"

    return normalized, "parsed_code"


def _code_block_content_start(text: str, start: int) -> int:
    if text[start : start + 6].lower() == "python":
        start += 6
    while start < len(text) and text[start].isspace():
        start += 1
    return start


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
    tests_total: int | None = None

    def _resolved_tests_total() -> int:
        nonlocal tests_total
        if tests_total is None:
            tests_total = _count_tests(test_code)
        return tests_total

    try:
        compile(candidate_code, "<candidate>", "exec")
    except SyntaxError as exc:
        return CodeEvaluationResult(
            compile_status="syntax_error",
            runtime_status="not_run",
            timeout_status="ok",
            test_status="not_run",
            tests_passed=0,
            tests_total=_resolved_tests_total(),
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
            tests_total=_resolved_tests_total(),
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
                    tests_total=_resolved_tests_total(),
                    failure_detail=detail,
                )

        stdout_tail, stdout_size = _read_limited_stdio(stdout_path, stdout_limit_bytes)
        stderr_tail, stderr_size = _read_limited_stdio(stderr_path, stdout_limit_bytes)
        output_limit_exceeded = stdout_size >= stdout_limit_bytes or stderr_size >= stdout_limit_bytes
        if output_limit_exceeded:
            return CodeEvaluationResult(
                compile_status="compiled",
                runtime_status="error",
                timeout_status="ok",
                test_status="failed",
                tests_passed=0,
                tests_total=_resolved_tests_total(),
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
                tests_total=_resolved_tests_total(),
                failure_detail=detail,
            )

        payload_tests_total = payload.get("tests_total")
        resolved_payload_tests_total = (
            int(payload_tests_total) if payload_tests_total else _resolved_tests_total()
        )
        return CodeEvaluationResult(
            compile_status=str(payload.get("compile_status", "compiled")),
            runtime_status=str(payload.get("runtime_status", "error")),
            timeout_status=str(payload.get("timeout_status", "ok")),
            test_status=str(payload.get("test_status", "failed")),
            tests_passed=int(payload.get("tests_passed", 0) or 0),
            tests_total=resolved_payload_tests_total,
            failure_detail=str(payload.get("failure_detail", "")),
        )


@lru_cache(maxsize=128)
def _count_tests(test_code: str) -> int:
    if "assert" not in test_code:
        return _count_nonblank_test_lines(test_code)
    try:
        module = ast.parse(test_code, filename="<tests>", mode="exec")
    except SyntaxError:
        return _count_nonblank_test_lines(test_code)
    assert_count = sum(1 for node in ast.walk(module) if isinstance(node, ast.Assert))
    return assert_count or _count_nonblank_test_lines(test_code)


def _count_nonblank_test_lines(test_code: str) -> int:
    count = 0
    in_line = False
    for char in test_code:
        if char in "\r\n":
            in_line = False
        elif not in_line and not char.isspace():
            count += 1
            in_line = True
    return count


def _load_payload_file(
    payload_path: Path,
    *,
    _loads=_JSON_LOADS,
    _decode_error=_JSON_DECODE_ERROR,
) -> dict[str, object] | None:
    try:
        payload_bytes = payload_path.read_bytes()
    except OSError:
        return None

    fast_payload = _extract_code_eval_payload_fields(payload_bytes)
    if fast_payload is not None:
        return fast_payload

    try:
        payload = _loads(payload_bytes)
    except _decode_error:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


_CODE_EVAL_PAYLOAD_STRING_KEYS = (
    "compile_status",
    "runtime_status",
    "timeout_status",
    "test_status",
    "failure_detail",
)
_CODE_EVAL_PAYLOAD_INT_KEYS = ("tests_passed", "tests_total")
_REQUIRED_CODE_EVAL_PAYLOAD_STRING_KEYS = (
    "runtime_status",
    "timeout_status",
    "test_status",
    "failure_detail",
)
_CODE_EVAL_PAYLOAD_KEY_TOKENS = {
    key: json.dumps(key, separators=(",", ":")).encode("utf-8")
    for key in (*_CODE_EVAL_PAYLOAD_STRING_KEYS, *_CODE_EVAL_PAYLOAD_INT_KEYS)
}


def _extract_code_eval_payload_fields(payload_bytes: bytes) -> dict[str, object] | None:
    stripped = payload_bytes.strip()
    if not stripped.startswith(b"{") or not stripped.endswith(b"}"):
        return None

    payload: dict[str, object] = {}
    for key in _CODE_EVAL_PAYLOAD_STRING_KEYS:
        value = _extract_json_string_field(payload_bytes, key)
        if value is not None:
            payload[key] = value

    for key in _CODE_EVAL_PAYLOAD_INT_KEYS:
        value = _extract_json_int_field(payload_bytes, key)
        if value is None:
            return None
        payload[key] = value

    if all(key in payload for key in _REQUIRED_CODE_EVAL_PAYLOAD_STRING_KEYS):
        return payload
    return None


def _json_field_value_start(payload_bytes: bytes, key: str) -> int | None:
    key_token = _CODE_EVAL_PAYLOAD_KEY_TOKENS.get(key)
    if key_token is None:
        key_token = json.dumps(key, separators=(",", ":")).encode("utf-8")
    key_index = payload_bytes.find(key_token)
    if key_index < 0:
        return None
    cursor = key_index + len(key_token)
    payload_length = len(payload_bytes)
    while cursor < payload_length and payload_bytes[cursor] in b" \t\r\n":
        cursor += 1
    if cursor >= payload_length or payload_bytes[cursor] != ord(":"):
        return None
    cursor += 1
    while cursor < payload_length and payload_bytes[cursor] in b" \t\r\n":
        cursor += 1
    if cursor >= payload_length:
        return None
    return cursor


def _extract_json_string_field(payload_bytes: bytes, key: str) -> str | None:
    start = _json_field_value_start(payload_bytes, key)
    if start is None or payload_bytes[start] != ord('"'):
        return None
    cursor = start + 1
    value_start = cursor
    payload_length = len(payload_bytes)
    while cursor < payload_length:
        char = payload_bytes[cursor]
        if char == ord('"'):
            return payload_bytes[value_start:cursor].decode("utf-8")
        if char == ord("\\"):
            return None
        cursor += 1
    return None


def _extract_json_int_field(payload_bytes: bytes, key: str) -> int | None:
    start = _json_field_value_start(payload_bytes, key)
    if start is None:
        return None
    cursor = start
    payload_length = len(payload_bytes)
    sign = 1
    if cursor < payload_length and payload_bytes[cursor] == ord("-"):
        sign = -1
        cursor += 1
    if cursor >= payload_length:
        return None
    value = 0
    digit_count = 0
    while cursor < payload_length:
        digit = payload_bytes[cursor] - ord("0")
        if digit < 0 or digit > 9:
            break
        value = (value * 10) + digit
        digit_count += 1
        cursor += 1
    if digit_count == 0:
        return None
    return sign * value


def _read_limited_stdio(path: Path, byte_limit: int) -> tuple[str, int]:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return "", 0

    try:
        size = os.fstat(fd).st_size
        read_limit = max(int(byte_limit), 0)
        if size > read_limit:
            os.lseek(fd, -read_limit, os.SEEK_END)
            read_size = read_limit
        else:
            read_size = size
        return os.read(fd, read_size).decode("utf-8", errors="replace").strip(), size
    except OSError:
        return "", 0
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def _read_limited_text(path: Path, byte_limit: int) -> str:
    text, _size = _read_limited_stdio(path, byte_limit)
    return text


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
    static_profile = _sandbox_static_profile_fragments(_sandbox_static_profile_key())
    temp_read_filters = " ".join(
        f"(subpath {json.dumps(str(path))})"
        for path in _sandbox_allow_path_variants((temp_root,))
    )
    return " ".join(
        (
            static_profile.prefix,
            f"(allow file-read* {static_profile.runtime_read_filters} {temp_read_filters})",
            f"(allow file-write* (subpath {json.dumps(str(temp_root))}))",
        )
    )


@dataclass(frozen=True)
class _SandboxStaticProfileFragments:
    prefix: str
    runtime_read_filters: str


_SANDBOX_STATIC_PROFILE_KEY_CACHE: tuple[tuple[object, ...], tuple[object, ...]] | None = None


def _sandbox_static_profile_environment_fingerprint() -> tuple[object, ...]:
    return (
        sys.executable,
        sys.prefix,
        sys.exec_prefix,
        sys.base_prefix,
        sys.base_exec_prefix,
        id(sysconfig.get_paths),
    )


def _sandbox_static_profile_key() -> tuple[object, ...]:
    global _SANDBOX_STATIC_PROFILE_KEY_CACHE
    fingerprint = _sandbox_static_profile_environment_fingerprint()
    if _SANDBOX_STATIC_PROFILE_KEY_CACHE is not None:
        cached_fingerprint, cached_key = _SANDBOX_STATIC_PROFILE_KEY_CACHE
        if cached_fingerprint == fingerprint:
            return cached_key
    key = (
        *fingerprint[:-1],
        tuple(sorted((key, value or "") for key, value in sysconfig.get_paths().items())),
    )
    _SANDBOX_STATIC_PROFILE_KEY_CACHE = (fingerprint, key)
    return key


def _sandbox_static_profile_key_cache_clear() -> None:
    global _SANDBOX_STATIC_PROFILE_KEY_CACHE
    _SANDBOX_STATIC_PROFILE_KEY_CACHE = None


@lru_cache(maxsize=8)
def _sandbox_static_profile_fragments(
    _cache_key: tuple[object, ...],
) -> _SandboxStaticProfileFragments:
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
    runtime_read_filters = " ".join(
        f"(subpath {json.dumps(str(path))})"
        for path in _sandbox_allow_path_variants(runtime_paths)
    )
    return _SandboxStaticProfileFragments(
        prefix=" ".join(clauses),
        runtime_read_filters=runtime_read_filters,
    )


def _sandbox_executable_paths() -> tuple[Path, ...]:
    resolved = _resolved_python_executable()
    preferred = _sandbox_python_executable()
    paths = [preferred, resolved]
    launcher_path = _python_framework_launcher_path(resolved)
    if launcher_path is not None:
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
    resolved = _resolved_python_executable()
    launcher_path = _python_framework_launcher_path(resolved)
    return launcher_path or resolved


def _resolved_python_executable() -> Path:
    return Path(sys.executable).resolve()


def _python_framework_launcher_path(resolved_executable: Path) -> Path | None:
    launcher_path = (
        resolved_executable.parent.parent / "Resources" / "Python.app" / "Contents" / "MacOS" / "Python"
    )
    if launcher_path.exists():
        return launcher_path.resolve()
    return None


def _sandbox_runtime_read_paths() -> tuple[Path, ...]:
    roots: list[Path] = [
        _resolved_python_executable().parent.parent,
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


@lru_cache(maxsize=1)
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


        def _load_config(config_path: Path) -> dict[str, object]:
            payload = json.loads(config_path.read_bytes())
            if not isinstance(payload, dict):
                raise TypeError("runner config must be a JSON object")
            return payload


        def main() -> int:
            config = _load_config(Path(sys.argv[1]))
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
