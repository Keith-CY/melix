from __future__ import annotations

import io
import importlib.util
import json
from pathlib import Path
import sys
import urllib.error

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "three_way_serving_compare.py"
MODULE_SPEC = importlib.util.spec_from_file_location("three_way_serving_compare", MODULE_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
three_way = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = three_way
MODULE_SPEC.loader.exec_module(three_way)


def test_parse_endpoint_spec_supports_three_named_runtimes() -> None:
    endpoint = three_way.parse_endpoint_spec(
        "swiftlm=http://127.0.0.1:18062/v1::mlx-community/gemma-4-31b-it-8bit",
        headers={"X-Test": "1"},
    )

    assert endpoint.name == "swiftlm"
    assert endpoint.base_url == "http://127.0.0.1:18062/v1"
    assert endpoint.model == "mlx-community/gemma-4-31b-it-8bit"
    assert endpoint.headers == {"X-Test": "1"}


def test_parse_endpoint_spec_rejects_invalid_names() -> None:
    with pytest.raises(ValueError, match="endpoint name"):
        three_way.parse_endpoint_spec(
            "swift lm=http://127.0.0.1:18062/v1::model",
            headers={},
        )


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        ("swiftlm-http://127.0.0.1:18062/v1::model", "format"),
        ("swiftlm=::model", "base URL"),
        ("swiftlm=http://127.0.0.1:18062/v1::", "model is empty"),
    ],
)
def test_parse_endpoint_spec_rejects_malformed_specs(spec: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        three_way.parse_endpoint_spec(spec, headers={})


def test_parse_endpoint_headers_are_grouped_by_endpoint() -> None:
    grouped = three_way.parse_endpoint_headers([
        "melix=Authorization: Bearer local",
        "swiftlm=X-Test: 1",
    ])

    assert grouped == {
        "melix": {"Authorization": "Bearer local"},
        "swiftlm": {"X-Test": "1"},
    }


def test_parse_endpoint_headers_rejects_missing_endpoint_name() -> None:
    with pytest.raises(ValueError, match="format"):
        three_way.parse_endpoint_headers(["Authorization: Bearer local"])


def test_runtime_base_url_strips_openai_v1_prefix() -> None:
    assert three_way.runtime_base_url("http://127.0.0.1:12441/v1") == "http://127.0.0.1:12441"
    assert three_way.runtime_base_url("http://127.0.0.1:12441/custom/v1/") == "http://127.0.0.1:12441/custom"
    assert three_way.runtime_base_url("http://127.0.0.1:12441") == "http://127.0.0.1:12441"


def test_request_optional_json_captures_success_http_error_and_url_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        status = 200

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"status":"ok"}'

    monkeypatch.setattr(three_way.urllib.request, "urlopen", lambda *_args, **_kwargs: FakeResponse())
    assert three_way.request_optional_json(
        "http://127.0.0.1:12441",
        "/health",
        headers={},
        timeout_seconds=1,
    ) == {
        "ok": True,
        "payload": {"status": "ok"},
        "status_code": 200,
        "url": "http://127.0.0.1:12441/health",
    }

    def raise_http_error(*_args: object, **_kwargs: object) -> None:
        raise urllib.error.HTTPError(
            "http://127.0.0.1:12441/metrics",
            404,
            "not found",
            hdrs=None,
            fp=io.BytesIO(b'{"error":"missing"}'),
        )

    monkeypatch.setattr(three_way.urllib.request, "urlopen", raise_http_error)
    http_error = three_way.request_optional_json(
        "http://127.0.0.1:12441",
        "/metrics",
        headers={},
        timeout_seconds=1,
    )
    assert http_error["ok"] is False
    assert http_error["status_code"] == 404
    assert http_error["payload"] == {"error": "missing"}

    monkeypatch.setattr(
        three_way.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(urllib.error.URLError("offline")),
    )
    url_error = three_way.request_optional_json(
        "http://127.0.0.1:12441",
        "/health",
        headers={},
        timeout_seconds=1,
    )
    assert url_error["ok"] is False
    assert url_error["status_code"] == 0
    assert "URLError" in url_error["error"]


def test_capture_runtime_snapshots_uses_runtime_root(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_request_optional_json(
        base_url: str,
        path: str,
        *,
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> dict[str, object]:
        calls.append((base_url, path))
        return {"ok": True, "status_code": 200, "payload": {"path": path}}

    monkeypatch.setattr(three_way, "request_optional_json", fake_request_optional_json)

    snapshots = three_way.capture_runtime_snapshots(
        [
            three_way.base.EndpointConfig(
                name="melix",
                base_url="http://127.0.0.1:12441/custom/v1",
                model="model",
                headers={"X-Test": "1"},
            )
        ],
        timeout_seconds=3,
    )

    assert calls == [
        ("http://127.0.0.1:12441/custom", "/health"),
        ("http://127.0.0.1:12441/custom", "/metrics"),
    ]
    assert snapshots["melix"]["service_root_url"] == "http://127.0.0.1:12441/custom"


def test_prompt_token_evidence_records_actual_token_range() -> None:
    observations = [
        three_way.base.RequestObservation(
            endpoint="melix",
            model="model",
            scenario_id="scenario",
            group_id="group",
            prompt_token_target=225000,
            prompt_token_source="usage",
            max_tokens=128,
            concurrency=2,
            cache_profile="cold_unique",
            repeat_index=0,
            request_index=0,
            status="ok",
            http_status=200,
            error="",
            ttft_ms=100.0,
            total_ms=200.0,
            decode_ms=100.0,
            completion_tokens=128,
            completion_token_source="usage",
            prompt_tokens=131010,
            streamed_chunks=128,
            completion_chars=512,
            decode_tokens_per_second=1280.0,
            group_elapsed_ms=250.0,
            prompt_style="concise",
        ),
        three_way.base.RequestObservation(
            endpoint="melix",
            model="model",
            scenario_id="scenario",
            group_id="group",
            prompt_token_target=225000,
            prompt_token_source="estimated_chars",
            max_tokens=128,
            concurrency=2,
            cache_profile="cold_unique",
            repeat_index=0,
            request_index=1,
            status="ok",
            http_status=200,
            error="",
            ttft_ms=110.0,
            total_ms=220.0,
            decode_ms=110.0,
            completion_tokens=128,
            completion_token_source="usage",
            prompt_tokens=131020,
            streamed_chunks=128,
            completion_chars=512,
            decode_tokens_per_second=1163.6,
            group_elapsed_ms=250.0,
            prompt_style="concise",
        ),
    ]

    evidence = three_way.prompt_token_evidence(observations)

    assert evidence == [
        {
            "endpoint": "melix",
            "prompt_token_target": 225000,
            "max_tokens": 128,
            "concurrency": 2,
            "cache_profile": "cold_unique",
            "prompt_style": "concise",
            "request_count": 2,
            "success_count": 2,
            "prompt_token_sources": ["estimated_chars", "usage"],
            "min_prompt_tokens": 131010,
            "median_prompt_tokens": 131015.0,
            "max_prompt_tokens": 131020,
        }
    ]


def test_peer_comparisons_identify_best_peer_and_melix_gaps() -> None:
    summaries = [
        three_way.base.ScenarioSummary(
            endpoint="melix",
            model="model",
            prompt_token_target=131072,
            max_tokens=128,
            concurrency=2,
            cache_profile="cold_unique",
            request_count=4,
            success_count=4,
            error_count=0,
            error_rate=0.0,
            median_ttft_ms=1200.0,
            p95_ttft_ms=1300.0,
            median_total_ms=3200.0,
            p95_total_ms=3400.0,
            median_decode_tokens_per_second=38.0,
            median_aggregate_output_tokens_per_second=70.0,
            median_completion_tokens=128.0,
        ),
        three_way.base.ScenarioSummary(
            endpoint="omlx",
            model="model",
            prompt_token_target=131072,
            max_tokens=128,
            concurrency=2,
            cache_profile="cold_unique",
            request_count=4,
            success_count=4,
            error_count=0,
            error_rate=0.0,
            median_ttft_ms=1000.0,
            p95_ttft_ms=1100.0,
            median_total_ms=3000.0,
            p95_total_ms=3200.0,
            median_decode_tokens_per_second=42.0,
            median_aggregate_output_tokens_per_second=80.0,
            median_completion_tokens=128.0,
        ),
        three_way.base.ScenarioSummary(
            endpoint="swiftlm",
            model="model",
            prompt_token_target=131072,
            max_tokens=128,
            concurrency=2,
            cache_profile="cold_unique",
            request_count=4,
            success_count=4,
            error_count=0,
            error_rate=0.0,
            median_ttft_ms=900.0,
            p95_ttft_ms=1000.0,
            median_total_ms=2800.0,
            p95_total_ms=3000.0,
            median_decode_tokens_per_second=45.0,
            median_aggregate_output_tokens_per_second=90.0,
            median_completion_tokens=128.0,
        ),
    ]

    comparisons, hints = three_way.peer_comparisons(summaries, target_endpoint="melix")

    assert len(comparisons) == 1
    comparison = comparisons[0]
    assert comparison["winners"]["median_ttft_ms"] == "swiftlm"
    assert comparison["winners"]["median_total_ms"] == "swiftlm"
    assert comparison["winners"]["median_decode_tokens_per_second"] == "swiftlm"
    assert comparison["winners"]["median_aggregate_output_tokens_per_second"] == "swiftlm"
    assert {hint["area"] for hint in hints} == {
        "ttft",
        "end_to_end_latency",
        "decode_throughput",
        "concurrency_aggregate_throughput",
    }
    assert all(hint["best_peer"] == "swiftlm" for hint in hints)


def test_peer_comparisons_records_target_errors_and_missing_target() -> None:
    summaries = [
        three_way.base.ScenarioSummary(
            endpoint="melix",
            model="model",
            prompt_token_target=512,
            max_tokens=16,
            concurrency=1,
            cache_profile="cold_unique",
            request_count=1,
            success_count=0,
            error_count=1,
            error_rate=1.0,
            median_ttft_ms=None,
            p95_ttft_ms=None,
            median_total_ms=None,
            p95_total_ms=None,
            median_decode_tokens_per_second=None,
            median_aggregate_output_tokens_per_second=None,
            median_completion_tokens=None,
        ),
        three_way.base.ScenarioSummary(
            endpoint="omlx",
            model="model",
            prompt_token_target=512,
            max_tokens=16,
            concurrency=1,
            cache_profile="cold_unique",
            request_count=1,
            success_count=1,
            error_count=0,
            error_rate=0.0,
            median_ttft_ms=10.0,
            p95_ttft_ms=10.0,
            median_total_ms=20.0,
            p95_total_ms=20.0,
            median_decode_tokens_per_second=30.0,
            median_aggregate_output_tokens_per_second=20.0,
            median_completion_tokens=16.0,
        ),
    ]

    comparisons, hints = three_way.peer_comparisons(summaries, target_endpoint="melix")
    missing_target_comparisons, missing_target_hints = three_way.peer_comparisons(
        summaries,
        target_endpoint="swiftlm",
    )

    assert comparisons[0]["winners"]["median_ttft_ms"] == "omlx"
    assert hints == [
        {
            "scenario": {
                "prompt_token_target": 512,
                "max_tokens": 16,
                "concurrency": 1,
                "cache_profile": "cold_unique",
                "prompt_style": "concise",
            },
            "area": "reliability",
            "severity": "high",
            "message": "melix returned errors in this scenario.",
            "target_error_count": 1,
        }
    ]
    assert missing_target_comparisons == []
    assert missing_target_hints == []


def test_gap_helpers_ignore_missing_and_zero_values() -> None:
    assert three_way._latency_gap(None, 10.0) is False
    assert three_way._latency_gap(20.0, None) is False
    assert three_way._throughput_gap(None, 10.0) is False
    assert three_way._throughput_gap(5.0, None) is False
    assert three_way._throughput_gap(5.0, 0.0) is False


def test_dry_run_writes_three_way_artifacts(tmp_path: Path) -> None:
    args = three_way.build_arg_parser().parse_args(
        [
            "--endpoint",
            "melix=http://127.0.0.1:12441/v1::model",
            "--endpoint",
            "omlx=http://127.0.0.1:18061/v1::model",
            "--endpoint",
            "swiftlm=http://127.0.0.1:18062/v1::model",
            "--dry-run",
            "--run-id",
            "three-way-dry",
            "--staging-root",
            str(tmp_path),
            "--no-export",
        ]
    )
    three_way.validate_args(args)

    result = three_way.run_comparison(args)

    staging_dir = tmp_path / "three-way-dry"
    assert result["endpoint_count"] == 3
    assert result["observation_count"] == 0
    assert (staging_dir / "manifest.json").exists()
    assert (staging_dir / "summary.md").exists()
    manifest = json.loads((staging_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["dry_run"] is True
    assert [endpoint["name"] for endpoint in manifest["endpoints"]] == [
        "melix",
        "omlx",
        "swiftlm",
    ]
    assert manifest["scenario_count"] == 3


def test_dry_run_copies_run_evidence_into_artifacts(tmp_path: Path) -> None:
    evidence_path = tmp_path / "input-run-evidence.json"
    evidence = {
        "build_mode": "release",
        "melix_git_head": "abc123",
        "melix_worker_binary": "/tmp/melix-text-worker-swift",
        "melix_worker_sha256": "worker-sha",
        "melix_control_binary": "/tmp/melix-control-plane",
        "melix_control_sha256": "control-sha",
        "model_id": "unsloth/gemma-4-E4B-it-MLX-8bit",
        "measurement_profile": {
            "profile": "warm",
            "prompt_token_targets": [128, 1024],
        },
    }
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    args = three_way.build_arg_parser().parse_args(
        [
            "--endpoint",
            "melix=http://127.0.0.1:12441/v1::model",
            "--endpoint",
            "omlx=http://127.0.0.1:18061/v1::model",
            "--dry-run",
            "--run-id",
            "three-way-run-evidence",
            "--staging-root",
            str(tmp_path),
            "--run-evidence",
            str(evidence_path),
            "--no-export",
        ]
    )
    three_way.validate_args(args)

    result = three_way.run_comparison(args)

    staging_dir = tmp_path / "three-way-run-evidence"
    manifest = json.loads((staging_dir / "manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((staging_dir / "summary.json").read_text(encoding="utf-8"))
    markdown = (staging_dir / "summary.md").read_text(encoding="utf-8")
    copied_evidence = json.loads((staging_dir / "run-evidence.json").read_text(encoding="utf-8"))

    assert result["artifacts"]["run_evidence"].endswith("run-evidence.json")
    assert manifest["artifacts"]["run_evidence"] == "run-evidence.json"
    assert manifest["run_evidence"] == evidence
    assert summary["run_evidence"] == evidence
    assert copied_evidence == evidence
    assert "- Run evidence artifact: `run-evidence.json`" in markdown
    assert "## Run Evidence" in markdown
    assert "`melix_worker_sha256` | `worker-sha`" in markdown


def test_load_run_evidence_rejects_missing_invalid_and_non_object(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        three_way.load_run_evidence(tmp_path / "missing.json")

    invalid_json = tmp_path / "invalid.json"
    invalid_json.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        three_way.load_run_evidence(invalid_json)

    list_json = tmp_path / "list.json"
    list_json.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        three_way.load_run_evidence(list_json)


def test_preflight_only_captures_runtime_snapshots_without_requests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_preflight(
        endpoints: list[three_way.base.EndpointConfig],
        *,
        timeout_seconds: float,
        wait_seconds: float,
        retry_interval_seconds: float,
    ) -> list[dict[str, object]]:
        return [
            {
                "endpoint": endpoint.name,
                "base_url": endpoint.base_url,
                "status_code": 200,
                "ok": True,
                "model": endpoint.model,
                "model_listed": True,
                "model_count": 1,
                "models": [endpoint.model],
                "error": None,
            }
            for endpoint in endpoints
        ]

    monkeypatch.setattr(three_way.base, "preflight_endpoints", fake_preflight)
    monkeypatch.setattr(
        three_way,
        "capture_runtime_snapshots",
        lambda endpoints, *, timeout_seconds: {
            endpoint.name: {"health": {"status_code": 200}, "metrics": {"status_code": 404}}
            for endpoint in endpoints
        },
    )
    args = three_way.build_arg_parser().parse_args(
        [
            "--endpoint",
            "melix=http://127.0.0.1:12441/v1::model",
            "--endpoint",
            "swiftlm=http://127.0.0.1:18062/v1::model",
            "--preflight-only",
            "--run-id",
            "three-way-preflight",
            "--staging-root",
            str(tmp_path),
            "--no-export",
        ]
    )

    result = three_way.run_comparison(args)

    runtime_snapshots = json.loads(
        (tmp_path / "three-way-preflight" / "runtime-snapshots.json").read_text(encoding="utf-8")
    )
    assert result["observation_count"] == 0
    assert runtime_snapshots["melix"]["health"]["status_code"] == 200


def test_preflight_failure_requires_explicit_allowance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        three_way.base,
        "preflight_endpoints",
        lambda *_args, **_kwargs: [
            {
                "endpoint": "melix",
                "status_code": 200,
                "ok": False,
                "model": "model",
                "model_listed": False,
                "model_count": 0,
                "models": [],
                "error": None,
            }
        ],
    )
    monkeypatch.setattr(three_way, "capture_runtime_snapshots", lambda *_args, **_kwargs: {})
    args = three_way.build_arg_parser().parse_args(
        [
            "--endpoint",
            "melix=http://127.0.0.1:12441/v1::model",
            "--endpoint",
            "omlx=http://127.0.0.1:18061/v1::model",
            "--run-id",
            "three-way-failed-preflight",
            "--staging-root",
            str(tmp_path),
            "--no-export",
        ]
    )

    with pytest.raises(RuntimeError, match="Endpoint preflight failed"):
        three_way.run_comparison(args)


def test_warmup_requests_mark_three_way_measurements_as_warm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_preflight(endpoint: three_way.base.EndpointConfig, *, timeout_seconds: float) -> dict[str, object]:
        return {
            "endpoint": endpoint.name,
            "base_url": endpoint.base_url,
            "status_code": 200,
            "ok": True,
            "model": endpoint.model,
            "model_listed": True,
            "model_count": 1,
            "models": [endpoint.model],
            "error": None,
        }

    def fake_run_group(
        endpoint: three_way.base.EndpointConfig,
        scenario: three_way.base.BenchmarkScenario,
        *,
        include_usage: bool,
        temperature: float,
        top_p: float,
        top_k: int,
        timeout_seconds: float,
        run_key: str = "",
    ) -> list[three_way.base.RequestObservation]:
        assert top_p == 1.0
        assert top_k == 0
        return [
            three_way.base.RequestObservation(
                endpoint=endpoint.name,
                model=endpoint.model,
                scenario_id=scenario.scenario_id,
                group_id=f"{endpoint.name}-{scenario.scenario_id}",
                prompt_token_target=scenario.prompt_token_target,
                prompt_token_source="usage",
                max_tokens=scenario.max_tokens,
                concurrency=scenario.concurrency,
                cache_profile=scenario.cache_profile,
                repeat_index=scenario.repeat_index,
                request_index=0,
                status="ok",
                http_status=200,
                error="",
                ttft_ms=10.0 if scenario.scenario_id.startswith("warmup") else 100.0,
                total_ms=20.0 if scenario.scenario_id.startswith("warmup") else 200.0,
                decode_ms=10.0,
                completion_tokens=5.0,
                completion_token_source="usage",
                prompt_tokens=20.0,
                streamed_chunks=1,
                completion_chars=20,
                decode_tokens_per_second=500.0,
                group_elapsed_ms=20.0,
                prompt_style=scenario.prompt_style,
            )
        ]

    monkeypatch.setattr(three_way.base, "preflight_endpoint", fake_preflight)
    monkeypatch.setattr(three_way.base, "run_group", fake_run_group)
    args = three_way.build_arg_parser().parse_args(
        [
            "--endpoint",
            "melix=http://127.0.0.1:12441/v1::model",
            "--endpoint",
            "omlx=http://127.0.0.1:18061/v1::model",
            "--endpoint",
            "swiftlm=http://127.0.0.1:18062/v1::model",
            "--warmup-requests",
            "1",
            "--prompt-token-targets",
            "1024",
            "--max-tokens",
            "16",
            "--run-id",
            "three-way-warm",
            "--staging-root",
            str(tmp_path),
            "--no-export",
        ]
    )
    three_way.validate_args(args)

    result = three_way.run_comparison(args)

    staging_dir = tmp_path / "three-way-warm"
    manifest = json.loads((staging_dir / "manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((staging_dir / "summary.json").read_text(encoding="utf-8"))
    markdown = (staging_dir / "summary.md").read_text(encoding="utf-8")

    assert result["measurement_profile"] == "warm"
    assert manifest["measurement_profile"] == {
        "profile": "warm",
        "warmup_requests_per_endpoint": 1,
        "operator_note": "",
    }
    assert summary["measurement_profile"]["profile"] == "warm"
    assert "- Measurement profile: `warm`" in markdown


def test_three_way_run_writes_merged_melix_metrics_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_preflight(endpoint: three_way.base.EndpointConfig, *, timeout_seconds: float) -> dict[str, object]:
        return {
            "endpoint": endpoint.name,
            "base_url": endpoint.base_url,
            "status_code": 200,
            "ok": True,
            "model": endpoint.model,
            "model_listed": True,
            "model_count": 1,
            "models": [endpoint.model],
            "error": None,
        }

    def fake_run_group(
        endpoint: three_way.base.EndpointConfig,
        scenario: three_way.base.BenchmarkScenario,
        *,
        include_usage: bool,
        temperature: float,
        top_p: float,
        top_k: int,
        timeout_seconds: float,
        run_key: str = "",
    ) -> list[three_way.base.RequestObservation]:
        assert top_p == 1.0
        assert top_k == 0
        return [
            three_way.base.RequestObservation(
                endpoint=endpoint.name,
                model=endpoint.model,
                scenario_id=scenario.scenario_id,
                group_id=f"{endpoint.name}-{scenario.scenario_id}",
                prompt_token_target=scenario.prompt_token_target,
                prompt_token_source="usage",
                max_tokens=scenario.max_tokens,
                concurrency=scenario.concurrency,
                cache_profile=scenario.cache_profile,
                repeat_index=scenario.repeat_index,
                request_index=0,
                status="ok",
                http_status=200,
                error="",
                ttft_ms=100.0,
                total_ms=200.0,
                decode_ms=100.0,
                completion_tokens=5.0,
                completion_token_source="usage",
                prompt_tokens=20.0,
                streamed_chunks=1,
                completion_chars=20,
                decode_tokens_per_second=50.0,
                group_elapsed_ms=200.0,
                prompt_style=scenario.prompt_style,
            )
        ]

    control_plane_path = tmp_path / "control-plane-metrics.json"
    swift_worker_path = tmp_path / "swift-text-worker-metrics.json"
    control_plane_path.write_text(
        json.dumps({
            "updated_at_unix_ms": 100,
            "values": {"control_plane.text_first_load_ms": 8547.46},
        }),
        encoding="utf-8",
    )
    swift_worker_path.write_text(
        json.dumps({
            "updated_at_unix_ms": 200,
            "values": {"swift_text.prefill_ms": 3706},
        }),
        encoding="utf-8",
    )

    monkeypatch.setattr(three_way.base, "preflight_endpoint", fake_preflight)
    monkeypatch.setattr(three_way.base, "run_group", fake_run_group)
    args = three_way.build_arg_parser().parse_args(
        [
            "--endpoint",
            "melix=http://127.0.0.1:12441/v1::model",
            "--endpoint",
            "omlx=http://127.0.0.1:18061/v1::model",
            "--endpoint",
            "swiftlm=http://127.0.0.1:18062/v1::model",
            "--prompt-token-targets",
            "1024",
            "--max-tokens",
            "16",
            "--run-id",
            "three-way-metrics",
            "--staging-root",
            str(tmp_path),
            "--melix-control-plane-metrics",
            str(control_plane_path),
            "--melix-swift-text-worker-metrics",
            str(swift_worker_path),
            "--no-export",
        ]
    )
    three_way.validate_args(args)

    result = three_way.run_comparison(args)

    staging_dir = tmp_path / "three-way-metrics"
    manifest = json.loads((staging_dir / "manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((staging_dir / "summary.json").read_text(encoding="utf-8"))
    metrics_snapshot = json.loads((staging_dir / "melix-metrics.json").read_text(encoding="utf-8"))
    request_phase_rows = json.loads((staging_dir / "request-phase-rows.json").read_text(encoding="utf-8"))
    peer_delta_rows = json.loads((staging_dir / "peer-delta-rows.json").read_text(encoding="utf-8"))
    threshold_status = json.loads((staging_dir / "threshold-status.json").read_text(encoding="utf-8"))
    markdown = (staging_dir / "summary.md").read_text(encoding="utf-8")

    assert result["request_phase_row_count"] == 3
    assert result["peer_delta_row_count"] == 1
    assert result["threshold_status"]["status"] == "ok"
    assert manifest["request_phase_row_count"] == 3
    assert manifest["peer_delta_row_count"] == 1
    assert manifest["threshold_status"]["status"] == "ok"
    assert manifest["artifacts"]["request_phase_rows"] == "request-phase-rows.json"
    assert manifest["artifacts"]["peer_delta_rows"] == "peer-delta-rows.json"
    assert manifest["artifacts"]["threshold_status"] == "threshold-status.json"
    assert len(request_phase_rows) == 3
    assert len(peer_delta_rows) == 1
    assert request_phase_rows[0]["first_http_sse_event_ms"] == 100.0
    assert request_phase_rows[0]["output_tokens"] == 5.0
    assert peer_delta_rows[0]["target_endpoint"] == "melix"
    assert peer_delta_rows[0]["status"] == "ok"
    assert threshold_status["row_count"] == 1
    assert summary["request_phase_rows"] == request_phase_rows
    assert summary["peer_delta_rows"] == peer_delta_rows
    assert summary["threshold_status"] == threshold_status
    assert metrics_snapshot["values"]["control_plane.text_first_load_ms"] == 8547.46
    assert metrics_snapshot["values"]["swift_text.prefill_ms"] == 3706
    assert metrics_snapshot["sources"]["control_plane"]["source_kind"] == "control_plane"
    assert metrics_snapshot["sources"]["swift_text_worker"]["source_kind"] == "worker"
    assert "- Threshold status: `ok`" in markdown
    assert "## Peer Delta Rows" in markdown
    assert "## Request Phase Rows" in markdown
    assert "First HTTP/SSE Event ms" in markdown
    assert "`swift_text.prefill_ms` | 3706.00" in markdown


def test_three_way_markdown_surfaces_melix_first_load_metrics() -> None:
    markdown = three_way.render_markdown_summary(
        [],
        [],
        [],
        preflight=[],
        runtime_snapshots={},
        prompt_evidence=[],
        warmups=[],
        metrics_snapshot={
            "ok": True,
            "values": {
                "scheduler.admission_cohort_size": 2,
                "scheduler.admission_active_cohorts": 1,
                "control_plane.text_first_load_ms": 8547.46,
                "control_plane.text_first_load_resident_bytes": 32942997504,
                "swift_text.decode_batch_size": 1,
                "swift_text.model_eval_batch_size": 1,
                "swift_text.per_batch_output_token_count": 16,
                "swift_text.per_batch_output_tokens_per_second": 8,
                "swift_text.decode_batch_observation_count": 1,
                "swift_text.decode_batch_token_eval_total_us": 64000,
                "swift_text.decode_batch_token_eval_call_count": 4,
                "swift_text.decode_batch_token_eval_avg_us": 16000,
                "swift_text.decode_harmony_filter_total_us": 2000,
                "swift_text.decode_harmony_filter_call_count": 6,
                "swift_text.decode_harmony_filter_avg_us": 333,
                "swift_text.decode_grpc_write_total_us": 3000,
                "swift_text.decode_grpc_write_call_count": 10,
                "swift_text.decode_grpc_write_avg_us": 300,
                "swift_text.prefill_ms": 3447.17,
                "swift_text.decode_ttft_ms": 8554.38,
                "http.worker_event_handle_total_us": 5000,
                "http.worker_event_handle_call_count": 4,
                "http.worker_event_handle_avg_us": 1250,
                "http.sse_write_total_us": 7000,
                "http.sse_write_call_count": 3,
                "http.sse_write_avg_us": 2333,
            },
        },
        dry_run=False,
        target_endpoint="melix",
        measurement_profile={
            "profile": "cold",
            "warmup_requests_per_endpoint": 0,
            "operator_note": "first measured request includes model load",
        },
    )

    assert "- Measurement profile: `cold`" in markdown
    assert "`scheduler.admission_cohort_size` | 2.00" in markdown
    assert "`swift_text.decode_batch_size` | 1.00" in markdown
    assert "`swift_text.model_eval_batch_size` | 1.00" in markdown
    assert "`swift_text.per_batch_output_token_count` | 16.00" in markdown
    assert "`swift_text.per_batch_output_tokens_per_second` | 8.00" in markdown
    assert "`swift_text.decode_batch_observation_count` | 1.00" in markdown
    assert "`swift_text.decode_batch_token_eval_total_us` | 64000.00" in markdown
    assert "`swift_text.decode_batch_token_eval_call_count` | 4.00" in markdown
    assert "`swift_text.decode_batch_token_eval_avg_us` | 16000.00" in markdown
    assert "`swift_text.decode_harmony_filter_total_us` | 2000.00" in markdown
    assert "`swift_text.decode_harmony_filter_call_count` | 6.00" in markdown
    assert "`swift_text.decode_harmony_filter_avg_us` | 333.00" in markdown
    assert "`swift_text.decode_grpc_write_total_us` | 3000.00" in markdown
    assert "`swift_text.decode_grpc_write_call_count` | 10.00" in markdown
    assert "`swift_text.decode_grpc_write_avg_us` | 300.00" in markdown
    assert "`control_plane.text_first_load_ms` | 8547.46" in markdown
    assert "`swift_text.prefill_ms` | 3447.17" in markdown
    assert "`swift_text.decode_ttft_ms` | 8554.38" in markdown
    assert "`http.worker_event_handle_total_us` | 5000.00" in markdown
    assert "`http.worker_event_handle_call_count` | 4.00" in markdown
    assert "`http.worker_event_handle_avg_us` | 1250.00" in markdown
    assert "`http.sse_write_total_us` | 7000.00" in markdown
    assert "`http.sse_write_call_count` | 3.00" in markdown
    assert "`http.sse_write_avg_us` | 2333.00" in markdown


def test_three_way_markdown_lists_token_count_sources() -> None:
    markdown = three_way.render_markdown_summary(
        [
            three_way.base.ScenarioSummary(
                endpoint="swiftlm",
                model="model",
                prompt_token_target=1024,
                max_tokens=16,
                concurrency=1,
                cache_profile="cold_unique",
                request_count=1,
                success_count=1,
                error_count=0,
                error_rate=0.0,
                median_ttft_ms=100.0,
                p95_ttft_ms=100.0,
                median_total_ms=200.0,
                p95_total_ms=200.0,
                median_decode_tokens_per_second=16.0,
                median_aggregate_output_tokens_per_second=8.0,
                median_completion_tokens=16.0,
                prompt_token_sources="usage",
                completion_token_sources="estimated_chars",
            )
        ],
        [],
        [],
        preflight=[],
        runtime_snapshots={},
        prompt_evidence=[],
        warmups=[],
        metrics_snapshot=None,
        dry_run=False,
        target_endpoint="melix",
        measurement_profile={
            "profile": "warm",
            "warmup_requests_per_endpoint": 1,
            "operator_note": "",
        },
    )

    assert "Prompt Source" in markdown
    assert "Completion Source" in markdown
    assert "| swiftlm | 1024 | concise | usage | estimated_chars | 16 | 1 | 0 |" in markdown


def test_markdown_empty_sections_and_missing_metrics_are_explicit() -> None:
    markdown = three_way.render_markdown_summary(
        [],
        [],
        [],
        preflight=[],
        runtime_snapshots={},
        prompt_evidence=[],
        warmups=[],
        metrics_snapshot={"ok": False, "error": "missing metrics"},
        dry_run=True,
        target_endpoint="melix",
        measurement_profile={
            "profile": "mixed",
            "warmup_requests_per_endpoint": 0,
            "operator_note": "",
        },
    )

    assert "No prompt token evidence was collected." in markdown
    assert "No peer comparison rows were generated." in markdown
    assert "No runtime snapshots were captured." in markdown
    assert "Metrics snapshot unavailable: `missing metrics`" in markdown
    assert "No target endpoint bottleneck hints were generated." in markdown


def test_export_bundle_uses_timestamp_suffix_when_destination_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staging_dir = tmp_path / "run"
    staging_dir.mkdir()
    (staging_dir / "summary.md").write_text("# Summary\n", encoding="utf-8")
    export_dir = tmp_path / "exports"
    (export_dir / "run").mkdir(parents=True)

    class FakeDateTime:
        @staticmethod
        def now(_timezone: object) -> object:
            class FakeNow:
                def strftime(self, _format: str) -> str:
                    return "123456"

            return FakeNow()

    monkeypatch.setattr(three_way, "datetime", FakeDateTime)

    destination = three_way.export_bundle(staging_dir, export_dir)

    assert destination == export_dir / "run-123456"
    assert (destination / "summary.md").read_text(encoding="utf-8") == "# Summary\n"


def test_export_bundle_returns_none_when_disabled(tmp_path: Path) -> None:
    assert three_way.export_bundle(tmp_path, None) is None


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        ([], "Pass at least two"),
        (
            [
                "--endpoint",
                "melix=http://127.0.0.1:12441/v1::model",
                "--endpoint",
                "melix=http://127.0.0.1:12442/v1::model",
            ],
            "unique",
        ),
        (
            [
                "--endpoint",
                "melix=http://127.0.0.1:12441/v1::model",
                "--endpoint",
                "omlx=http://127.0.0.1:18061/v1::model",
                "--target-endpoint",
                "swiftlm",
            ],
            "target-endpoint",
        ),
        (
            [
                "--endpoint",
                "melix=http://127.0.0.1:12441/v1::model",
                "--endpoint",
                "omlx=http://127.0.0.1:18061/v1::model",
                "--repeats",
                "0",
            ],
            "repeats",
        ),
        (
            [
                "--endpoint",
                "melix=http://127.0.0.1:12441/v1::model",
                "--endpoint",
                "omlx=http://127.0.0.1:18061/v1::model",
                "--max-tokens",
                "0",
            ],
            "max-tokens",
        ),
        (
            [
                "--endpoint",
                "melix=http://127.0.0.1:12441/v1::model",
                "--endpoint",
                "omlx=http://127.0.0.1:18061/v1::model",
                "--warmup-requests",
                "-1",
            ],
            "warmup-requests",
        ),
        (
            [
                "--endpoint",
                "melix=http://127.0.0.1:12441/v1::model",
                "--endpoint",
                "omlx=http://127.0.0.1:18061/v1::model",
                "--warmup-prompt-token-target",
                "0",
            ],
            "warmup-prompt-token-target",
        ),
        (
            [
                "--endpoint",
                "melix=http://127.0.0.1:12441/v1::model",
                "--endpoint",
                "omlx=http://127.0.0.1:18061/v1::model",
                "--warmup-max-tokens",
                "0",
            ],
            "warmup-max-tokens",
        ),
        (
            [
                "--endpoint",
                "melix=http://127.0.0.1:12441/v1::model",
                "--endpoint",
                "omlx=http://127.0.0.1:18061/v1::model",
                "--prompt-token-targets",
                "0",
            ],
            "prompt-token-targets",
        ),
        (
            [
                "--endpoint",
                "melix=http://127.0.0.1:12441/v1::model",
                "--endpoint",
                "omlx=http://127.0.0.1:18061/v1::model",
                "--concurrency",
                "0",
            ],
            "concurrency",
        ),
        (
            [
                "--endpoint",
                "melix=http://127.0.0.1:12441/v1::model",
                "--endpoint",
                "omlx=http://127.0.0.1:18061/v1::model",
                "--timeout-seconds",
                "0",
            ],
            "Timeout",
        ),
        (
            [
                "--endpoint",
                "melix=http://127.0.0.1:12441/v1::model",
                "--endpoint",
                "omlx=http://127.0.0.1:18061/v1::model",
                "--total-latency-threshold-ratio",
                "-0.1",
            ],
            "total-latency",
        ),
        (
            [
                "--endpoint",
                "melix=http://127.0.0.1:12441/v1::model",
                "--endpoint",
                "omlx=http://127.0.0.1:18061/v1::model",
                "--decode-throughput-threshold-ratio",
                "-0.1",
            ],
            "decode-throughput",
        ),
        (
            [
                "--endpoint",
                "melix=http://127.0.0.1:12441/v1::model",
                "--endpoint",
                "omlx=http://127.0.0.1:18061/v1::model",
                "--decode-throughput-threshold-ratio",
                "1.1",
            ],
            "decode-throughput",
        ),
        (
            [
                "--endpoint",
                "melix=http://127.0.0.1:12441/v1::model",
                "--endpoint",
                "omlx=http://127.0.0.1:18061/v1::model",
                "--preflight-wait-seconds",
                "-1",
            ],
            "preflight-wait",
        ),
        (
            [
                "--endpoint",
                "melix=http://127.0.0.1:12441/v1::model",
                "--endpoint",
                "omlx=http://127.0.0.1:18061/v1::model",
                "--preflight-retry-interval-seconds",
                "0",
            ],
            "preflight-retry",
        ),
    ],
)
def test_validate_args_rejects_invalid_inputs(argv: list[str], message: str) -> None:
    args = three_way.build_arg_parser().parse_args(argv)
    with pytest.raises(ValueError, match=message):
        three_way.validate_args(args)


def test_main_prints_text_summary_and_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = {
        "run_id": "run-1",
        "staging_dir": str(tmp_path / "run-1"),
        "exported_to": str(tmp_path / "exports" / "run-1"),
        "endpoint_count": 3,
        "scenario_count": 2,
        "observation_count": 6,
        "optimization_hint_count": 1,
    }
    monkeypatch.setattr(three_way, "run_comparison", lambda _args: dict(result))
    assert three_way.main([
        "--endpoint",
        "melix=http://127.0.0.1:12441/v1::model",
        "--endpoint",
        "omlx=http://127.0.0.1:18061/v1::model",
    ]) == 0
    text_output = capsys.readouterr().out
    assert "Run id: run-1" in text_output
    assert "Exported to:" in text_output

    assert three_way.main([
        "--endpoint",
        "melix=http://127.0.0.1:12441/v1::model",
        "--endpoint",
        "omlx=http://127.0.0.1:18061/v1::model",
        "--json",
    ]) == 0
    json_output = json.loads(capsys.readouterr().out)
    assert json_output["run_id"] == "run-1"
    assert "elapsed_seconds" in json_output


def test_main_returns_error_on_validation_failure(capsys: pytest.CaptureFixture[str]) -> None:
    assert three_way.main([]) == 2
    assert "Pass at least two" in capsys.readouterr().err
