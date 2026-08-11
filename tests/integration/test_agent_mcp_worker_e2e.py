from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

import grpc

from packages.protocol.python.worker.v1 import (
    common_pb2,
    tool_runtime_pb2,
    tool_runtime_pb2_grpc,
)
from tests.integration.helpers import (
    swift_package_command,
    swift_package_environment,
    wait_for_worker_handshake,
)


def test_real_stdio_mcp_crosses_worker_rpc_and_swift_agent_loop(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    fixture_path = (
        repo_root
        / "tests"
        / "integration"
        / "fixtures"
        / "agent_mcp_stdio_server.py"
    )
    socket_path = Path("/tmp") / f"melix-agent-mcp-{uuid.uuid4().hex[:10]}.sock"
    stdout_path = tmp_path / "python-worker.stdout.log"
    stderr_path = tmp_path / "python-worker.stderr.log"
    melix_home = tmp_path / "melix-home"
    secret = "Bearer agent-mcp-e2e-secret-must-not-reenter"
    worker_environment = os.environ.copy()
    worker_environment.update(
        {
            "PYTHONPATH": os.pathsep.join(
                [
                    str(repo_root),
                    str(repo_root / "services" / "mlx-worker-python"),
                ]
            ),
            "UV_CACHE_DIR": str(repo_root / ".uv-cache"),
            "MELIX_HOME": str(melix_home),
            "MELIX_AGENT_MCP_E2E_SECRET": secret,
            "MELIX_MCP_CREDENTIAL_ENV_KEYS": "MELIX_AGENT_MCP_E2E_SECRET",
        }
    )

    worker_started_at = time.perf_counter()
    with stdout_path.open("w", encoding="utf-8") as worker_stdout, stderr_path.open(
        "w", encoding="utf-8"
    ) as worker_stderr:
        worker = subprocess.Popen(
            [
                "uv",
                "run",
                "--project",
                str(repo_root / "services" / "mlx-worker-python"),
                "python",
                "-m",
                "worker.bootstrap",
                "--socket-path",
                str(socket_path),
                "--backend-mode",
                "deterministic",
            ],
            cwd=repo_root,
            env=worker_environment,
            stdout=worker_stdout,
            stderr=worker_stderr,
            text=True,
            start_new_session=True,
        )
        try:
            wait_for_worker_handshake(
                socket_path,
                worker=worker,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                timeout_seconds=60,
            )
            worker_ready_ms = (time.perf_counter() - worker_started_at) * 1_000

            python_mcp_preflight_started_at = time.perf_counter()
            _preflight_real_mcp(
                socket_path=socket_path,
                fixture_path=fixture_path,
                repo_root=repo_root,
            )
            python_mcp_preflight_ms = (
                time.perf_counter() - python_mcp_preflight_started_at
            ) * 1_000

            swift_environment = swift_package_environment(
                repo_root,
                "agent-mcp-e2e",
                base_env=os.environ.copy(),
            )
            swift_environment.update(
                {
                    "MELIX_RUN_AGENT_MCP_E2E": "1",
                    "MELIX_AGENT_MCP_E2E_WORKER_SOCKET": str(socket_path),
                    "MELIX_AGENT_MCP_E2E_FIXTURE": str(fixture_path),
                    "MELIX_AGENT_MCP_E2E_PYTHON": sys.executable,
                    "MELIX_AGENT_MCP_E2E_REPO_ROOT": str(repo_root),
                    "MELIX_AGENT_MCP_E2E_SECRET": secret,
                }
            )
            swift_test_arguments = ["--no-parallel"]
            if (
                os.environ.get("MELIX_AGENT_MCP_E2E_ENABLE_SWIFT_COVERAGE")
                == "1"
            ):
                swift_test_arguments.append("--enable-code-coverage")
            swift_test_arguments.extend(
                ["--filter", "AgentMCPWorkerIntegrationTests"]
            )
            swift_started_at = time.perf_counter()
            completed = subprocess.run(
                swift_package_command(
                    repo_root / "services" / "control-plane-swift",
                    repo_root,
                    "agent-mcp-e2e",
                    "test",
                    swift_test_arguments,
                ),
                cwd=repo_root,
                env=swift_environment,
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
            swift_e2e_ms = (time.perf_counter() - swift_started_at) * 1_000
            worker_stdout.flush()
            worker_stderr.flush()
            assert completed.returncode == 0, (
                "Swift Agent MCP E2E failed\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}\n"
                f"worker stdout:\n{stdout_path.read_text(encoding='utf-8')}\n"
                f"worker stderr:\n{stderr_path.read_text(encoding='utf-8')}"
            )

            evidence_files = sorted(
                (melix_home / "state" / "agent-tool-evidence").rglob("*.json")
            )
            assert evidence_files
            evidence_bytes = 0
            for evidence_path in evidence_files:
                evidence = evidence_path.read_text(encoding="utf-8")
                evidence_bytes += len(evidence.encode("utf-8"))
                assert secret not in evidence
                assert "agent-mcp-e2e-secret-must-not-reenter" not in evidence

            worker_log_texts = (
                stdout_path.read_text(encoding="utf-8"),
                stderr_path.read_text(encoding="utf-8"),
            )
            credential_variants = (
                secret,
                "agent-mcp-e2e-secret-must-not-reenter",
            )
            credential_leak_count = sum(
                log_text.count(credential)
                for log_text in worker_log_texts
                for credential in credential_variants
            )
            assert credential_leak_count == 0

            print(
                json.dumps(
                    {
                        "worker_ready_ms": worker_ready_ms,
                        "python_mcp_preflight_ms": python_mcp_preflight_ms,
                        "swift_agent_mcp_e2e_ms": swift_e2e_ms,
                        "evidence_file_count": len(evidence_files),
                        "evidence_bytes": evidence_bytes,
                        "credential_leak_count": credential_leak_count,
                    },
                    sort_keys=True,
                )
            )
        finally:
            if worker.poll() is None:
                os.killpg(os.getpgid(worker.pid), signal.SIGTERM)
                try:
                    worker.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(os.getpgid(worker.pid), signal.SIGKILL)
                    worker.wait(timeout=10)
            socket_path.unlink(missing_ok=True)


def _preflight_real_mcp(
    *,
    socket_path: Path,
    fixture_path: Path,
    repo_root: Path,
) -> None:
    owner_session = "agent-mcp-preflight-session"
    owner_branch = "agent-mcp-preflight-branch"
    owner_actor = "agent-mcp-preflight-operator"
    source = tool_runtime_pb2.AgentToolSourceConfig(
        source_id="agent-e2e-preflight",
        enabled=True,
        stdio=tool_runtime_pb2.MCPStdioTransport(
            command=sys.executable,
            arguments=[str(fixture_path)],
            working_directory=str(repo_root),
            environment_references={
                "MCP_E2E_SECRET": "MELIX_AGENT_MCP_E2E_SECRET",
            },
        ),
        request_timeout_ms=15_000,
        connect_timeout_ms=30_000,
        max_result_bytes=4_096,
        configuration_revision="agent-mcp-preflight-v1",
    )
    channel = grpc.insecure_channel(f"unix://{socket_path}")
    stub = tool_runtime_pb2_grpc.ToolRuntimeServiceStub(channel)
    try:
        catalog = stub.ListAgentTools(
            tool_runtime_pb2.ListAgentToolsRequest(
                id=common_pb2.RequestIdentity(
                    request_id="agent-mcp-preflight-list",
                    session_id=owner_session,
                    branch_id=owner_branch,
                ),
                sources=[source],
                refresh_sources=True,
                deadline_unix_ms=int(time.time() * 1_000) + 45_000,
                owner_actor_id=owner_actor,
                lease_ttl_ms=30_000,
            ),
            timeout=45,
        )
        assert any(
            tool.source_tool_name == "bounded_secret_echo"
            for tool in catalog.tools
        )
        release = stub.ListAgentTools(
            tool_runtime_pb2.ListAgentToolsRequest(
                id=common_pb2.RequestIdentity(
                    request_id="agent-mcp-preflight-release",
                    session_id=owner_session,
                    branch_id=owner_branch,
                ),
                deadline_unix_ms=int(time.time() * 1_000) + 5_000,
                owner_actor_id=owner_actor,
                lease_ttl_ms=1,
                release_sources=True,
            ),
            timeout=5,
        )
        assert not release.sources
        assert all(
            tool.source_id != "agent-e2e-preflight"
            for tool in release.tools
        )
    finally:
        channel.close()
