from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import sys
import sysconfig
import tempfile


_CODE_BLOCK_PATTERN = re.compile(r"```(?:python)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
_MACOS_SANDBOX_EXECUTABLE = Path("/usr/bin/sandbox-exec")
_MAX_STDIO_BYTES = 64 * 1024
_OUTPUT_SUMMARY_BYTES = 2048


@dataclass(frozen=True)
class _HarnessProcessResult:
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool
    output_limit_exceeded: bool


@dataclass(frozen=True)
class CodeExecutionResult:
    passed: bool
    execution_status: str
    candidate_code: str
    metadata: dict[str, str]


def extract_candidate_code(raw_response: str) -> tuple[str, str]:
    normalized = raw_response.strip()
    if not normalized:
        return "", "empty_prediction"
    matches = _CODE_BLOCK_PATTERN.findall(normalized)
    if matches:
        return matches[-1].strip(), "parsed_code_block"
    return normalized, "parsed_code"


def execute_python_candidate(
    *,
    candidate_code: str,
    entry_point: str,
    test_code: str,
    code_exec_policy: str = "sandboxed",
    timeout_seconds: float = 5.0,
    max_stdio_bytes: int = _MAX_STDIO_BYTES,
) -> CodeExecutionResult:
    metadata = {
        "entry_point": entry_point,
        "code_exec_policy": code_exec_policy,
        "compile_status": "not_run",
        "runtime_status": "not_run",
        "timeout_status": "not_triggered",
        "test_status": "not_run",
        "sandbox_status": "not_requested",
        "output_status": "within_limit",
        "stdout_bytes": "0",
        "stderr_bytes": "0",
        "max_stdio_bytes": str(max_stdio_bytes),
        "return_code": "",
        "failure_message": "",
    }
    if not candidate_code.strip():
        return CodeExecutionResult(
            passed=False,
            execution_status="missing_candidate_code",
            candidate_code="",
            metadata=metadata,
        )

    harness = _python_harness(
        candidate_code=candidate_code,
        entry_point=entry_point,
        test_code=test_code,
        payload_filename="payload.json",
        max_stdio_bytes=max_stdio_bytes,
    )
    with tempfile.TemporaryDirectory(prefix="melix-eval-code-") as temp_dir_str:
        temp_dir = Path(temp_dir_str).resolve()
        script_path = temp_dir / "code_eval.py"
        payload_path = temp_dir / "payload.json"
        stdout_path = temp_dir / "stdout.txt"
        stderr_path = temp_dir / "stderr.txt"
        script_path.write_text(harness, encoding="utf-8")
        command, sandbox_status, sandbox_error = _build_execution_command(
            script_path=script_path,
            temp_dir=temp_dir,
            code_exec_policy=code_exec_policy,
        )
        metadata["sandbox_status"] = sandbox_status
        if sandbox_error:
            metadata["failure_message"] = sandbox_error
            return CodeExecutionResult(
                passed=False,
                execution_status="sandbox_unavailable",
                candidate_code=candidate_code,
                metadata=metadata,
            )
        try:
            process_result = _run_harness_process(
                command=command,
                cwd=temp_dir,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                timeout=timeout_seconds,
                max_stdio_bytes=max_stdio_bytes,
            )
        except subprocess.TimeoutExpired as error:
            metadata["timeout_status"] = "timed_out"
            timed_out_result = _read_process_result(
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                returncode=getattr(error, "returncode", None),
                timed_out=True,
                max_stdio_bytes=max_stdio_bytes,
            )
            metadata["stdout_bytes"] = str(len(timed_out_result.stdout.encode("utf-8")))
            metadata["stderr_bytes"] = str(len(timed_out_result.stderr.encode("utf-8")))
            if timed_out_result.returncode is not None:
                metadata["return_code"] = str(timed_out_result.returncode)
            if timed_out_result.output_limit_exceeded:
                metadata["output_status"] = "limit_exceeded"
            metadata["failure_message"] = _timeout_failure_message(
                timeout_seconds=timeout_seconds,
                stdout=timed_out_result.stdout,
                stderr=timed_out_result.stderr,
            )
            return CodeExecutionResult(
                passed=False,
                execution_status="timed_out",
                candidate_code=candidate_code,
                metadata=metadata,
            )

        metadata["stdout_bytes"] = str(len(process_result.stdout.encode("utf-8")))
        metadata["stderr_bytes"] = str(len(process_result.stderr.encode("utf-8")))
        if process_result.returncode is not None:
            metadata["return_code"] = str(process_result.returncode)
        if process_result.output_limit_exceeded:
            metadata["output_status"] = "limit_exceeded"

        payload = _load_harness_payload(
            payload_path=payload_path,
            process_result=process_result,
        )
    merged_metadata = {**metadata, **payload.get("metadata", {})}
    if process_result.output_limit_exceeded:
        merged_metadata["output_status"] = "limit_exceeded"
        merged_metadata["failure_message"] = _output_limit_failure_message(
            stdout=process_result.stdout,
            stderr=process_result.stderr,
            max_stdio_bytes=max_stdio_bytes,
        )
    return CodeExecutionResult(
        passed=bool(payload.get("passed", False)) and not process_result.output_limit_exceeded,
        execution_status=(
            "output_limit_exceeded"
            if process_result.output_limit_exceeded
            else str(payload.get("execution_status", "failed"))
        ),
        candidate_code=candidate_code,
        metadata=merged_metadata,
    )


def is_code_execution_policy_supported(code_exec_policy: str) -> bool:
    normalized = code_exec_policy.strip()
    if normalized != "sandboxed":
        return False
    return sys.platform == "darwin" and _MACOS_SANDBOX_EXECUTABLE.exists()


def _load_harness_payload(
    *,
    payload_path: Path,
    process_result: _HarnessProcessResult,
) -> dict[str, object]:
    if process_result.output_limit_exceeded:
        return {
            "passed": False,
            "execution_status": "output_limit_exceeded",
            "metadata": {
                "failure_message": _output_limit_failure_message(
                    stdout=process_result.stdout,
                    stderr=process_result.stderr,
                    max_stdio_bytes=_MAX_STDIO_BYTES,
                ),
            },
        }
    if not payload_path.exists():
        failure_message = process_result.stderr.strip() or process_result.stdout.strip()
        if not failure_message:
            if process_result.returncode is None:
                failure_message = "Code execution produced no result payload."
            else:
                failure_message = (
                    f"Code execution exited with status {process_result.returncode} "
                    "without a result payload."
                )
        return {
            "passed": False,
            "execution_status": "failed",
            "metadata": {
                "failure_message": failure_message,
            },
        }
    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "passed": False,
            "execution_status": "failed",
            "metadata": {
                "failure_message": (
                    process_result.stderr.strip()
                    or process_result.stdout.strip()
                    or "Code execution produced an invalid result payload."
                ),
            },
        }
    if isinstance(payload, dict):
        return payload
    return {
        "passed": False,
        "execution_status": "failed",
        "metadata": {
            "failure_message": "Unexpected code execution payload shape.",
        },
    }


def _build_execution_command(
    *,
    script_path: Path,
    temp_dir: Path,
    code_exec_policy: str,
) -> tuple[list[str], str, str]:
    python_executable = Path(sys.executable)
    base_command = [str(python_executable), "-I", str(script_path)]
    if code_exec_policy == "sandboxed":
        if not is_code_execution_policy_supported(code_exec_policy):
            return (
                base_command,
                "unavailable",
                "code_exec_policy 'sandboxed' requires macOS sandbox-exec on this worker",
            )
        profile_path = temp_dir / "sandbox.sb"
        profile_path.write_text(
            _macos_sandbox_profile(
                temp_dir=temp_dir,
                python_executable=python_executable,
            ),
            encoding="utf-8",
        )
        return (
            [
                str(_MACOS_SANDBOX_EXECUTABLE),
                "-f",
                str(profile_path),
                *base_command,
            ],
            "active",
            "",
        )
    return base_command, "not_requested", ""


def _macos_sandbox_profile(*, temp_dir: Path, python_executable: Path) -> str:
    allowed_subpaths = sorted(
        {
            str(temp_dir),
            str(Path(sys.base_prefix).resolve()),
            str(Path(sys.prefix).resolve()),
            str(Path(sysconfig.get_path("stdlib")).resolve()),
            str(Path(sysconfig.get_path("platstdlib")).resolve()),
            "/System",
            "/usr/lib",
            "/private/usr/lib",
            "/dev",
        }
    )
    profile_lines = [
        "(version 1)",
        "(deny default)",
        '(import "bsd.sb")',
        "(allow file-read* process-exec",
        f'    (literal "{python_executable}")',
    ]
    profile_lines.extend(f'    (subpath "{path}")' for path in allowed_subpaths)
    profile_lines.append(")")
    profile_lines.extend(
        [
            "(allow file-write*",
            f'    (subpath "{temp_dir}")',
            ")",
            "(deny network*)",
        ]
    )
    return "\n".join(profile_lines) + "\n"


def _run_harness_process(
    *,
    command: list[str],
    cwd: Path,
    stdout_path: Path,
    stderr_path: Path,
    timeout: float,
    max_stdio_bytes: int,
) -> _HarnessProcessResult:
    with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
        try:
            completed = subprocess.run(
                command,
                cwd=str(cwd),
                stdout=stdout_handle,
                stderr=stderr_handle,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise
    return _read_process_result(
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        returncode=completed.returncode,
        timed_out=False,
        max_stdio_bytes=max_stdio_bytes,
    )


def _read_process_result(
    *,
    stdout_path: Path,
    stderr_path: Path,
    returncode: int | None,
    timed_out: bool,
    max_stdio_bytes: int,
) -> _HarnessProcessResult:
    stdout = stdout_path.read_text(encoding="utf-8", errors="replace") if stdout_path.exists() else ""
    stderr = stderr_path.read_text(encoding="utf-8", errors="replace") if stderr_path.exists() else ""
    output_limit_exceeded = any(
        path.exists() and path.stat().st_size >= max_stdio_bytes
        for path in (stdout_path, stderr_path)
    )
    return _HarnessProcessResult(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        output_limit_exceeded=output_limit_exceeded,
    )
def _timeout_failure_message(*, timeout_seconds: float, stdout: str, stderr: str) -> str:
    summary = _summarize_process_output(stdout=stdout, stderr=stderr)
    if summary:
        return f"Timed out after {timeout_seconds:.1f}s. {summary}"
    return f"Timed out after {timeout_seconds:.1f}s"


def _output_limit_failure_message(*, stdout: str, stderr: str, max_stdio_bytes: int) -> str:
    summary = _summarize_process_output(stdout=stdout, stderr=stderr)
    if summary:
        return f"Code execution exceeded the {max_stdio_bytes}-byte stdio limit. {summary}"
    return f"Code execution exceeded the {max_stdio_bytes}-byte stdio limit."


def _summarize_process_output(*, stdout: str, stderr: str) -> str:
    parts: list[str] = []
    stdout_tail = stdout.strip()[-_OUTPUT_SUMMARY_BYTES:]
    stderr_tail = stderr.strip()[-_OUTPUT_SUMMARY_BYTES:]
    if stdout_tail:
        parts.append(f"stdout tail: {stdout_tail}")
    if stderr_tail:
        parts.append(f"stderr tail: {stderr_tail}")
    return " | ".join(parts)


def _python_harness(
    *,
    candidate_code: str,
    entry_point: str,
    test_code: str,
    payload_filename: str,
    max_stdio_bytes: int,
) -> str:
    return f"""import json
from pathlib import Path
import resource
import traceback

candidate_code = {candidate_code!r}
entry_point = {entry_point!r}
test_code = {test_code!r}
payload_path = Path({payload_filename!r})
max_stdio_bytes = {max_stdio_bytes!r}
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
resource.setrlimit(resource.RLIMIT_FSIZE, (max_stdio_bytes, max_stdio_bytes))
namespace = {{}}
payload = {{
    "passed": False,
    "execution_status": "failed",
    "metadata": {{
        "entry_point": entry_point,
        "compile_status": "not_run",
        "runtime_status": "not_run",
        "timeout_status": "not_triggered",
        "test_status": "not_run",
        "sandbox_status": "active",
        "output_status": "within_limit",
        "failure_message": "",
    }},
}}

try:
    compiled = compile(candidate_code, "<candidate>", "exec")
    payload["metadata"]["compile_status"] = "passed"
except Exception:
    payload["metadata"]["compile_status"] = "failed"
    payload["metadata"]["failure_message"] = traceback.format_exc().strip()
else:
    try:
        exec(compiled, namespace)
        payload["metadata"]["runtime_status"] = "passed"
    except Exception:
        payload["metadata"]["runtime_status"] = "failed"
        payload["metadata"]["failure_message"] = traceback.format_exc().strip()
    else:
        if entry_point and entry_point not in namespace:
            payload["metadata"]["runtime_status"] = "missing_entry_point"
            payload["metadata"]["failure_message"] = f"Missing entry point: {{entry_point}}"
        else:
            try:
                exec(test_code, namespace)
                payload["metadata"]["test_status"] = "passed"
                payload["execution_status"] = "passed"
                payload["passed"] = True
            except AssertionError:
                payload["metadata"]["test_status"] = "failed"
                payload["metadata"]["failure_message"] = traceback.format_exc().strip()
            except Exception:
                payload["metadata"]["test_status"] = "error"
                payload["metadata"]["failure_message"] = traceback.format_exc().strip()

payload_path.write_text(json.dumps(payload), encoding="utf-8")
"""
