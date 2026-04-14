from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap


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
                [sys.executable, "-I", "-S", str(runner_path), str(config_path)],
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env={
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONNOUSERSITE": "1",
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

        stdout = completed.stdout[:stdout_limit_bytes].strip()
        stderr = completed.stderr[:stdout_limit_bytes].strip()
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
    return len([line for line in test_code.splitlines() if line.strip()])


def _load_payload(stdout: str) -> dict[str, object] | None:
    if not stdout:
        return None
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _runner_script() -> str:
    return textwrap.dedent(
        """
        from __future__ import annotations

        import importlib.util
        import json
        import resource
        import sys
        import traceback


        def main() -> int:
            config = json.loads(open(sys.argv[1], "r", encoding="utf-8").read())
            memory_limit_mb = int(config.get("memory_limit_mb", 256) or 256)
            memory_limit_bytes = memory_limit_mb * 1024 * 1024
            current_soft, current_hard = resource.getrlimit(resource.RLIMIT_AS)
            if current_hard == resource.RLIM_INFINITY:
                address_space_limit = memory_limit_bytes
            else:
                address_space_limit = min(memory_limit_bytes, current_hard)
            try:
                resource.setrlimit(resource.RLIMIT_AS, (address_space_limit, current_hard))
            except (OSError, ValueError):
                pass
            cpu_soft, cpu_hard = resource.getrlimit(resource.RLIMIT_CPU)
            cpu_limit = min(2, cpu_hard) if cpu_hard != resource.RLIM_INFINITY else 2
            try:
                resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, cpu_hard))
            except (OSError, ValueError):
                pass

            candidate_path = config["candidate_path"]
            entry_point = str(config.get("entry_point", ""))
            test_code = str(config.get("test_code", ""))
            tests = [line for line in test_code.splitlines() if line.strip()]

            try:
                spec = importlib.util.spec_from_file_location("candidate", candidate_path)
                if spec is None or spec.loader is None:
                    raise RuntimeError("Unable to load candidate module")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if entry_point and hasattr(module, entry_point) is False:
                    raise AttributeError(f"Missing entry point: {entry_point}")

                namespace = dict(module.__dict__)
                tests_passed = 0
                for test in tests:
                    exec(test, namespace, namespace)
                    tests_passed += 1

                payload = {
                    "compile_status": "compiled",
                    "runtime_status": "ok",
                    "timeout_status": "ok",
                    "test_status": "passed",
                    "tests_passed": tests_passed,
                    "tests_total": len(tests),
                    "failure_detail": "",
                }
            except AssertionError as exc:
                payload = {
                    "compile_status": "compiled",
                    "runtime_status": "ok",
                    "timeout_status": "ok",
                    "test_status": "failed",
                    "tests_passed": locals().get("tests_passed", 0),
                    "tests_total": len(tests),
                    "failure_detail": str(exc) or "AssertionError",
                }
            except BaseException as exc:
                payload = {
                    "compile_status": "compiled",
                    "runtime_status": "error",
                    "timeout_status": "ok",
                    "test_status": "failed",
                    "tests_passed": locals().get("tests_passed", 0),
                    "tests_total": len(tests),
                    "failure_detail": "".join(traceback.format_exception_only(type(exc), exc)).strip(),
                }

            print(json.dumps(payload))
            return 0


        if __name__ == "__main__":
            raise SystemExit(main())
        """
    ).strip() + "\n"
