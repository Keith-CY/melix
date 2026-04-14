from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile


_CODE_BLOCK_PATTERN = re.compile(r"```(?:python)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


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
    timeout_seconds: float = 5.0,
) -> CodeExecutionResult:
    metadata = {
        "entry_point": entry_point,
        "compile_status": "not_run",
        "runtime_status": "not_run",
        "timeout_status": "not_triggered",
        "test_status": "not_run",
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
    )
    with tempfile.TemporaryDirectory(prefix="melix-eval-code-") as temp_dir:
        script_path = Path(temp_dir) / "code_eval.py"
        script_path.write_text(harness, encoding="utf-8")
        try:
            completed = subprocess.run(
                [sys.executable, "-I", str(script_path)],
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            metadata["timeout_status"] = "timed_out"
            metadata["failure_message"] = f"Timed out after {timeout_seconds:.1f}s"
            return CodeExecutionResult(
                passed=False,
                execution_status="timed_out",
                candidate_code=candidate_code,
                metadata=metadata,
            )

    payload = _load_harness_payload(completed.stdout, completed.stderr)
    merged_metadata = {**metadata, **payload.get("metadata", {})}
    return CodeExecutionResult(
        passed=bool(payload.get("passed", False)),
        execution_status=str(payload.get("execution_status", "failed")),
        candidate_code=candidate_code,
        metadata=merged_metadata,
    )


def _load_harness_payload(stdout: str, stderr: str) -> dict[str, object]:
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        return {
            "passed": False,
            "execution_status": "failed",
            "metadata": {
                "failure_message": stderr.strip() or "Code execution produced no result payload.",
            },
        }
    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError:
        return {
            "passed": False,
            "execution_status": "failed",
            "metadata": {
                "failure_message": stderr.strip() or lines[-1].strip(),
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


def _python_harness(*, candidate_code: str, entry_point: str, test_code: str) -> str:
    return f"""import json
import traceback

candidate_code = {candidate_code!r}
entry_point = {entry_point!r}
test_code = {test_code!r}
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

print(json.dumps(payload))
"""
