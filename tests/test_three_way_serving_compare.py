from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

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


def test_parse_endpoint_headers_are_grouped_by_endpoint() -> None:
    grouped = three_way.parse_endpoint_headers([
        "melix=Authorization: Bearer local",
        "swiftlm=X-Test: 1",
    ])

    assert grouped == {
        "melix": {"Authorization": "Bearer local"},
        "swiftlm": {"X-Test": "1"},
    }


def test_runtime_base_url_strips_openai_v1_prefix() -> None:
    assert three_way.runtime_base_url("http://127.0.0.1:12441/v1") == "http://127.0.0.1:12441"
    assert three_way.runtime_base_url("http://127.0.0.1:12441/custom/v1/") == "http://127.0.0.1:12441/custom"
    assert three_way.runtime_base_url("http://127.0.0.1:12441") == "http://127.0.0.1:12441"


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
        timeout_seconds: float,
    ) -> list[three_way.base.RequestObservation]:
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
        timeout_seconds: float,
    ) -> list[three_way.base.RequestObservation]:
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

    three_way.run_comparison(args)

    staging_dir = tmp_path / "three-way-metrics"
    metrics_snapshot = json.loads((staging_dir / "melix-metrics.json").read_text(encoding="utf-8"))
    markdown = (staging_dir / "summary.md").read_text(encoding="utf-8")

    assert metrics_snapshot["values"]["control_plane.text_first_load_ms"] == 8547.46
    assert metrics_snapshot["values"]["swift_text.prefill_ms"] == 3706
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
                "control_plane.text_first_load_ms": 8547.46,
                "control_plane.text_first_load_resident_bytes": 32942997504,
                "swift_text.prefill_ms": 3447.17,
                "swift_text.decode_ttft_ms": 8554.38,
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
    assert "`control_plane.text_first_load_ms` | 8547.46" in markdown
    assert "`swift_text.prefill_ms` | 3447.17" in markdown
    assert "`swift_text.decode_ttft_ms` | 8554.38" in markdown


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
