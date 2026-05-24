from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "omlx_melix_compare_benchmark.py"
MODULE_SPEC = importlib.util.spec_from_file_location("omlx_melix_compare_benchmark", MODULE_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
bench = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = bench
MODULE_SPEC.loader.exec_module(bench)


def test_parse_header_values_rejects_malformed_header() -> None:
    assert bench.parse_header_values(["Authorization: Bearer local"]) == {
        "Authorization": "Bearer local"
    }
    with pytest.raises(ValueError, match="Header must use"):
        bench.parse_header_values(["Authorization"])


def test_parse_sse_data_lines_extracts_content_usage_and_done() -> None:
    lines = [
        b"data: {\"choices\":[{\"delta\":{\"content\":\"hel\"}}]}\n",
        b"data: {\"choices\":[{\"delta\":{\"content\":\"lo\"}}]}\n",
        b"data: {\"choices\":[],\"usage\":{\"prompt_tokens\":10,\"completion_tokens\":2}}\n",
        b"data: [DONE]\n",
    ]

    content, chunk_count, usage, saw_done = bench.parse_sse_data_lines(lines)

    assert content == "hello"
    assert chunk_count == 2
    assert usage == {"prompt_tokens": 10, "completion_tokens": 2}
    assert saw_done is True


def test_build_prompt_supports_saturating_decode_style() -> None:
    prompt = bench.build_prompt(
        128,
        cache_profile="cold_unique",
        request_key="request-1",
        prompt_style="saturating",
    )

    assert "Do not conclude, summarize, or stop early" in prompt
    assert "MELIX-OMLX-BENCH-request-1" in prompt


def test_request_key_is_endpoint_independent_for_fair_comparison() -> None:
    scenario = bench.BenchmarkScenario(
        scenario_id="pt128-out64-c1-r0",
        prompt_token_target=128,
        max_tokens=64,
        concurrency=1,
        cache_profile="cold_unique",
        repeat_index=0,
        prompt_style="saturating",
    )

    assert bench.request_key_for_scenario(scenario, request_index=0) == (
        "pt128-out64-c1-r0-req0"
    )


def test_cold_unique_request_key_includes_run_key_without_endpoint() -> None:
    scenario = bench.BenchmarkScenario(
        scenario_id="pt512-out64-c1-r0",
        prompt_token_target=512,
        max_tokens=64,
        concurrency=1,
        cache_profile="cold_unique",
        repeat_index=0,
        prompt_style="saturating",
    )

    assert bench.request_key_for_scenario(
        scenario,
        request_index=0,
        run_key="run-20260524",
    ) == "run-20260524-pt512-out64-c1-r0-req0"


def test_repeated_request_key_omits_run_key_for_warm_cache() -> None:
    scenario = bench.BenchmarkScenario(
        scenario_id="pt512-out64-c1-r0",
        prompt_token_target=512,
        max_tokens=64,
        concurrency=1,
        cache_profile="repeated",
        repeat_index=0,
        prompt_style="saturating",
    )

    assert bench.request_key_for_scenario(
        scenario,
        request_index=0,
        run_key="run-20260524",
    ) == "pt512-out64-c1-r0-req0"


def test_stream_chat_completion_sends_explicit_sampling_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def readline(self):
            lines = captured.setdefault(
                "lines",
                iter(
                    [
                        b'data: {"choices":[{"delta":{"content":"ok"}}],"usage":{"prompt_tokens":3,"completion_tokens":1}}\n',
                        b"data: [DONE]\n",
                    ]
                ),
            )
            return next(lines, b"")

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(bench.urllib.request, "urlopen", fake_urlopen)

    endpoint = bench.EndpointConfig(
        name="melix",
        base_url="http://127.0.0.1:12434/v1",
        model="target-model",
        headers={},
    )
    scenario = bench.BenchmarkScenario(
        scenario_id="pt128-out16-c1-r0",
        prompt_token_target=128,
        max_tokens=16,
        concurrency=1,
        cache_profile="repeated",
        repeat_index=0,
    )

    observation = bench.stream_chat_completion(
        endpoint,
        scenario,
        request_index=0,
        request_key="same",
        include_usage=True,
        temperature=0.0,
        top_p=1.0,
        top_k=0,
        timeout_seconds=5.0,
        group_id="group",
        group_elapsed_ms=0.0,
    )

    assert observation.status == "ok"
    assert captured["payload"]["temperature"] == 0.0
    assert captured["payload"]["top_p"] == 1.0
    assert captured["payload"]["top_k"] == 0


def test_preflight_requires_target_model_to_be_listed(monkeypatch: pytest.MonkeyPatch) -> None:
    endpoint = bench.EndpointConfig(
        name="melix",
        base_url="http://127.0.0.1:12434/v1",
        model="target-model",
        headers={},
    )

    monkeypatch.setattr(
        bench,
        "request_json",
        lambda *args, **kwargs: (
            200,
            {"data": [{"id": "other-model", "object": "model"}]},
        ),
    )

    result = bench.preflight_endpoint(endpoint, timeout_seconds=1.0)

    assert result["status_code"] == 200
    assert result["model_listed"] is False
    assert result["ok"] is False


def test_preflight_wait_retries_until_target_model_is_listed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint = bench.EndpointConfig(
        name="melix",
        base_url="http://127.0.0.1:12434/v1",
        model="target-model",
        headers={},
    )
    responses = iter([
        (200, {"data": [{"id": "other-model", "object": "model"}]}),
        (200, {"data": [{"id": "target-model", "object": "model"}]}),
    ])
    sleeps: list[float] = []

    monkeypatch.setattr(bench, "request_json", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr(bench.time, "sleep", lambda seconds: sleeps.append(seconds))

    preflight = bench.preflight_endpoints(
        [endpoint],
        timeout_seconds=1.0,
        wait_seconds=5.0,
        retry_interval_seconds=0.25,
    )

    assert len(preflight) == 1
    assert preflight[0]["ok"] is True
    assert preflight[0]["model_listed"] is True
    assert preflight[0]["attempt_count"] == 2
    assert sleeps == [0.25]


def test_summarize_observations_computes_latency_and_group_throughput() -> None:
    rows = [
        bench.RequestObservation(
            endpoint="melix",
            model="model",
            scenario_id="s1",
            group_id="g1",
            prompt_token_target=1024,
            prompt_token_source="usage",
            max_tokens=32,
            concurrency=2,
            cache_profile="cold_unique",
            repeat_index=0,
            request_index=0,
            status="ok",
            http_status=200,
            error="",
            ttft_ms=100.0,
            total_ms=300.0,
            decode_ms=200.0,
            completion_tokens=20.0,
            completion_token_source="usage",
            prompt_tokens=100.0,
            streamed_chunks=5,
            completion_chars=80,
            decode_tokens_per_second=100.0,
            group_elapsed_ms=400.0,
        ),
        bench.RequestObservation(
            endpoint="melix",
            model="model",
            scenario_id="s1",
            group_id="g1",
            prompt_token_target=1024,
            prompt_token_source="usage",
            max_tokens=32,
            concurrency=2,
            cache_profile="cold_unique",
            repeat_index=0,
            request_index=1,
            status="ok",
            http_status=200,
            error="",
            ttft_ms=120.0,
            total_ms=340.0,
            decode_ms=220.0,
            completion_tokens=20.0,
            completion_token_source="usage",
            prompt_tokens=100.0,
            streamed_chunks=5,
            completion_chars=80,
            decode_tokens_per_second=90.0,
            group_elapsed_ms=400.0,
        ),
    ]

    summaries = bench.summarize_observations(rows)

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.request_count == 2
    assert summary.success_count == 2
    assert summary.error_count == 0
    assert summary.median_ttft_ms == 110.0
    assert summary.median_decode_tokens_per_second == 95.0
    assert summary.median_aggregate_output_tokens_per_second == 100.0
    assert summary.prompt_style == "concise"


def test_comparison_hints_flags_melix_regressions() -> None:
    summaries = [
        bench.ScenarioSummary(
            endpoint="melix",
            model="model",
            prompt_token_target=1024,
            max_tokens=64,
            concurrency=4,
            cache_profile="cold_unique",
            request_count=4,
            success_count=4,
            error_count=0,
            error_rate=0.0,
            median_ttft_ms=200.0,
            p95_ttft_ms=240.0,
            median_total_ms=600.0,
            p95_total_ms=650.0,
            median_decode_tokens_per_second=30.0,
            median_aggregate_output_tokens_per_second=80.0,
            median_completion_tokens=64.0,
        ),
        bench.ScenarioSummary(
            endpoint="omlx",
            model="model",
            prompt_token_target=1024,
            max_tokens=64,
            concurrency=4,
            cache_profile="cold_unique",
            request_count=4,
            success_count=4,
            error_count=0,
            error_rate=0.0,
            median_ttft_ms=120.0,
            p95_ttft_ms=140.0,
            median_total_ms=350.0,
            p95_total_ms=390.0,
            median_decode_tokens_per_second=60.0,
            median_aggregate_output_tokens_per_second=160.0,
            median_completion_tokens=64.0,
        ),
    ]

    hints = bench.comparison_hints(summaries)

    assert {hint["area"] for hint in hints} == {
        "ttft",
        "end_to_end_latency",
        "decode_throughput",
        "continuous_batching",
    }


def test_metrics_snapshot_adds_multimodal_batching_hint(tmp_path: Path) -> None:
    metrics_path = tmp_path / "control-plane-metrics.json"
    metrics_path.write_text(
        json.dumps({
            "updated_at_unix_ms": 123,
            "values": {
                "scheduler.multimodal_continuous_batch_enabled": 0,
                "scheduler.multimodal_continuous_batch_requested_capacity": 2,
                "scheduler.multimodal_continuous_batch_effective_capacity": 1,
                "scheduler.multimodal_continuous_batch_blocked_count": 4,
                "scheduler.multimodal_continuous_batch_blocked_reason_code": 2,
            },
        }),
        encoding="utf-8",
    )

    snapshot = bench.load_metrics_snapshot(metrics_path)
    hints = bench.enrich_hints_with_metrics([], snapshot)

    assert snapshot["ok"] is True
    assert len(hints) == 1
    assert hints[0]["severity"] == "high"
    assert hints[0]["melix_requested_batch_capacity"] == 2
    assert hints[0]["melix_effective_batch_capacity"] == 1
    assert hints[0]["melix_blocked_reason_code"] == 2
    assert "cooperative text-only token-step batching" in hints[0]["melix_blocked_reason"]


def test_melix_metrics_snapshot_merges_control_plane_and_swift_worker(tmp_path: Path) -> None:
    control_plane_path = tmp_path / "control-plane-metrics.json"
    swift_worker_path = tmp_path / "swift-text-worker-metrics.json"
    control_plane_path.write_text(
        json.dumps({
            "updated_at_unix_ms": 100,
            "values": {
                "control_plane.text_first_load_ms": 8547.46,
                "http.ttfd_ms": 3447.17,
            },
        }),
        encoding="utf-8",
    )
    swift_worker_path.write_text(
        json.dumps({
            "updated_at_unix_ms": 200,
            "values": {
                "swift_text.prefill_ms": 3706,
                "swift_text.decode_ttft_ms": 1910,
                "swift_text.decode_tokens_per_second": 2,
            },
        }),
        encoding="utf-8",
    )

    snapshot = bench.load_melix_metrics_snapshot(
        control_plane_path=control_plane_path,
        swift_text_worker_path=swift_worker_path,
    )

    assert snapshot["ok"] is True
    assert snapshot["updated_at_unix_ms"] == 200
    assert snapshot["sources"] == {
        "control_plane": {
            "ok": True,
            "path": str(control_plane_path),
            "updated_at_unix_ms": 100,
        },
        "swift_text_worker": {
            "ok": True,
            "path": str(swift_worker_path),
            "updated_at_unix_ms": 200,
        },
    }
    assert snapshot["values"]["control_plane.text_first_load_ms"] == 8547.46
    assert snapshot["values"]["swift_text.prefill_ms"] == 3706
    assert snapshot["values"]["swift_text.decode_tokens_per_second"] == 2


def test_markdown_summary_lists_text_batch_generator_metrics() -> None:
    markdown = bench.render_markdown_summary(
        [],
        [],
        preflight=[],
        warmups=[],
        metrics_snapshot={
            "ok": True,
            "values": {
                "vision.text_batch_generator.step_count": 16,
                "vision.text_batch_generator.first_visible_token_index_total": 2,
                "vision.text_batch_generator.first_empty_segment_count": 0,
                "vision.text_batch_generator.next_ms_total": 120.5,
                "vision.text_batch_generator.emit_ms_total": 4.25,
                "vision.text_batch_generator.speculative_cycle_count_total": 4,
                "vision.text_batch_generator.speculative_backbone_ms_total": 210.5,
                "http.parser.text_batch_generator_speculative_cycle_count_total": 39,
                "http.parser.text_batch_generator_speculative_accepted_count_total": 24,
                "http.parser.text_batch_generator_speculative_backbone_ms_total": 3197.16,
                "http.parser.text_batch_generator_prepare_ms": 2.5,
                "http.parser.text_batch_generator_prompt_encode_ms": 0.75,
                "http.parser.text_batch_generator_prefill_ms": 8.25,
                "http.parser.text_batch_generator_batch_insert_ms": 0.5,
            },
        },
        dry_run=False,
        measurement_profile={
            "profile": "cold",
            "warmup_requests_per_endpoint": 0,
            "operator_note": "",
        },
    )

    assert "`vision.text_batch_generator.step_count` | 16.00" in markdown
    assert "`vision.text_batch_generator.first_visible_token_index_total` | 2.00" in markdown
    assert "`vision.text_batch_generator.first_empty_segment_count` | 0.00" in markdown
    assert "`vision.text_batch_generator.next_ms_total` | 120.50" in markdown
    assert "`vision.text_batch_generator.emit_ms_total` | 4.25" in markdown
    assert "`vision.text_batch_generator.speculative_cycle_count_total` | 4.00" in markdown
    assert "`vision.text_batch_generator.speculative_backbone_ms_total` | 210.50" in markdown
    assert "`http.parser.text_batch_generator_speculative_cycle_count_total` | 39.00" in markdown
    assert "`http.parser.text_batch_generator_speculative_accepted_count_total` | 24.00" in markdown
    assert "`http.parser.text_batch_generator_speculative_backbone_ms_total` | 3197.16" in markdown
    assert "`http.parser.text_batch_generator_prepare_ms` | 2.50" in markdown
    assert "`http.parser.text_batch_generator_prompt_encode_ms` | 0.75" in markdown
    assert "`http.parser.text_batch_generator_prefill_ms` | 8.25" in markdown
    assert "`http.parser.text_batch_generator_batch_insert_ms` | 0.50" in markdown


def test_metrics_snapshot_reports_text_batch_generator_http_gap() -> None:
    markdown = bench.render_markdown_summary(
        [],
        [],
        preflight=[],
        warmups=[],
        metrics_snapshot={
            "ok": True,
            "values": {
                "http.stream_first_event_ms": 1552.02,
                "http.parser.text_batch_generator_first_visible_ms": 1435.31,
            },
        },
        dry_run=False,
    )

    assert "`http.stream_first_event_ms` | 1552.02" in markdown
    assert "`http.parser.text_batch_generator_first_visible_ms` | 1435.31" in markdown
    assert "`http.text_batch_generator_first_visible_to_stream_first_event_ms` | 116.71" in markdown


def test_warmup_requests_mark_measurements_as_warm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_preflight(endpoint: bench.EndpointConfig, *, timeout_seconds: float) -> dict[str, object]:
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
        endpoint: bench.EndpointConfig,
        scenario: bench.BenchmarkScenario,
        *,
        include_usage: bool,
        temperature: float,
        timeout_seconds: float,
    ) -> list[bench.RequestObservation]:
        return [
            bench.RequestObservation(
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
            )
        ]

    monkeypatch.setattr(bench, "preflight_endpoint", fake_preflight)
    monkeypatch.setattr(bench, "run_group", fake_run_group)
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
    args = bench.build_arg_parser().parse_args(
        [
            "--model",
            "local-model",
            "--run-id",
            "warm-run",
            "--staging-root",
            str(tmp_path),
            "--no-export",
            "--warmup-requests",
            "1",
            "--repeats",
            "1",
            "--melix-control-plane-metrics",
            str(control_plane_path),
            "--melix-swift-text-worker-metrics",
            str(swift_worker_path),
        ]
    )
    bench.validate_args(args)

    result = bench.run_benchmark(args)

    staging_dir = tmp_path / "warm-run"
    manifest = json.loads((staging_dir / "manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((staging_dir / "summary.json").read_text(encoding="utf-8"))
    markdown = (staging_dir / "summary.md").read_text(encoding="utf-8")

    assert result["measurement_profile"] == "warm"
    assert manifest["measurement_profile"]["profile"] == "warm"
    assert summary["measurement_profile"]["warmup_requests_per_endpoint"] == 1
    assert manifest["metrics"]["melix"]["artifact"] == "melix-metrics.json"
    assert manifest["metrics"]["melix_control_plane"]["path"] == str(control_plane_path)
    assert manifest["metrics"]["melix_control_plane"]["artifact"] == "melix-metrics.json"
    assert summary["melix_metrics_snapshot"]["values"]["swift_text.prefill_ms"] == 3706
    assert "- Measurement profile: `warm`" in markdown
    assert "`swift_text.prefill_ms` | 3706.00" in markdown


def test_markdown_summary_lists_text_first_load_metrics() -> None:
    markdown = bench.render_markdown_summary(
        [],
        [],
        preflight=[],
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


def test_markdown_summary_lists_token_count_sources() -> None:
    markdown = bench.render_markdown_summary(
        [
            bench.ScenarioSummary(
                endpoint="omlx",
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
                prompt_token_sources="estimated_chars",
                completion_token_sources="usage",
            )
        ],
        [],
        preflight=[],
        warmups=[],
        metrics_snapshot=None,
        dry_run=False,
        measurement_profile={
            "profile": "warm",
            "warmup_requests_per_endpoint": 1,
            "operator_note": "",
        },
    )

    assert "Prompt Token Source" in markdown
    assert "Completion Token Source" in markdown
    assert "| omlx | 1024 | concise | estimated_chars | usage | 16 | 1 | 0 |" in markdown


def test_dry_run_writes_artifacts_without_export(tmp_path: Path) -> None:
    args = bench.build_arg_parser().parse_args(
        [
            "--model",
            "local-model",
            "--dry-run",
            "--run-id",
            "test-run",
            "--staging-root",
            str(tmp_path),
            "--no-export",
            "--json",
        ]
    )
    bench.validate_args(args)

    result = bench.run_benchmark(args)

    staging_dir = tmp_path / "test-run"
    assert result["observation_count"] == 0
    assert (staging_dir / "manifest.json").exists()
    assert (staging_dir / "summary.md").exists()
    manifest = json.loads((staging_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["dry_run"] is True
    assert manifest["scenario_count"] == 3
    assert manifest["warmup_count"] == 0
    assert "warmups" not in manifest["artifacts"]


def test_warmups_are_written_separately_from_summaries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_preflight(endpoint: bench.EndpointConfig, *, timeout_seconds: float) -> dict[str, object]:
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

    run_keys: list[str] = []

    def fake_run_group(
        endpoint: bench.EndpointConfig,
        scenario: bench.BenchmarkScenario,
        *,
        include_usage: bool,
        temperature: float,
        top_p: float,
        top_k: int,
        timeout_seconds: float,
        run_key: str = "",
    ) -> list[bench.RequestObservation]:
        run_keys.append(run_key)
        return [
            bench.RequestObservation(
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
            )
        ]

    monkeypatch.setattr(bench, "preflight_endpoint", fake_preflight)
    monkeypatch.setattr(bench, "run_group", fake_run_group)
    args = bench.build_arg_parser().parse_args(
        [
            "--model",
            "local-model",
            "--run-id",
            "warm-run",
            "--staging-root",
            str(tmp_path),
            "--no-export",
            "--warmup-requests",
            "1",
            "--repeats",
            "1",
        ]
    )
    bench.validate_args(args)

    result = bench.run_benchmark(args)

    staging_dir = tmp_path / "warm-run"
    manifest = json.loads((staging_dir / "manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((staging_dir / "summary.json").read_text(encoding="utf-8"))
    warmups = (staging_dir / "warmups.jsonl").read_text(encoding="utf-8").strip().splitlines()
    observations = (staging_dir / "observations.jsonl").read_text(encoding="utf-8").strip().splitlines()

    assert result["warmup_count"] == 2
    assert result["observation_count"] == 2
    assert manifest["warmup_count"] == 2
    assert manifest["warmup_settings"] == {
        "max_tokens": 8,
        "prompt_style": "concise",
        "prompt_token_target": 128,
        "request_count_per_endpoint": 1,
    }
    assert manifest["scenario_settings"] == {"prompt_style": "concise"}
    assert manifest["artifacts"]["warmups"] == "warmups.jsonl"
    assert len(warmups) == 2
    assert len(observations) == 2
    assert len(summary["warmups"]) == 2
    assert all(json.loads(line)["scenario_id"].startswith("warmup") for line in warmups)
    assert {
        (item["cache_profile"], item["prompt_token_target"], item["max_tokens"], item["prompt_style"])
        for item in summary["summaries"]
    } == {("cold_unique", 1024, 128, "concise")}
    assert run_keys == ["warmup", "warmup", "warm-run", "warm-run"]


def test_alternate_endpoint_order_reverses_odd_repeats(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_preflight(endpoint: bench.EndpointConfig, *, timeout_seconds: float) -> dict[str, object]:
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

    calls: list[tuple[str, int]] = []

    def fake_run_group(
        endpoint: bench.EndpointConfig,
        scenario: bench.BenchmarkScenario,
        *,
        include_usage: bool,
        temperature: float,
        top_p: float,
        top_k: int,
        timeout_seconds: float,
        run_key: str = "",
    ) -> list[bench.RequestObservation]:
        calls.append((endpoint.name, scenario.repeat_index))
        return [
            bench.RequestObservation(
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
            )
        ]

    monkeypatch.setattr(bench, "preflight_endpoint", fake_preflight)
    monkeypatch.setattr(bench, "run_group", fake_run_group)
    args = bench.build_arg_parser().parse_args(
        [
            "--model",
            "local-model",
            "--run-id",
            "alternate-run",
            "--staging-root",
            str(tmp_path),
            "--no-export",
            "--warmup-requests",
            "0",
            "--repeats",
            "2",
            "--endpoint-order",
            "alternate",
        ]
    )
    bench.validate_args(args)

    bench.run_benchmark(args)

    assert calls == [
        ("melix", 0),
        ("omlx", 0),
        ("omlx", 1),
        ("melix", 1),
    ]


def test_validate_args_rejects_invalid_warmup_values() -> None:
    args = bench.build_arg_parser().parse_args(["--model", "m", "--warmup-requests", "-1"])
    with pytest.raises(ValueError, match="--warmup-requests"):
        bench.validate_args(args)

    args = bench.build_arg_parser().parse_args(["--model", "m", "--warmup-prompt-token-target", "0"])
    with pytest.raises(ValueError, match="--warmup-prompt-token-target"):
        bench.validate_args(args)

    args = bench.build_arg_parser().parse_args(["--model", "m", "--warmup-max-tokens", "0"])
    with pytest.raises(ValueError, match="--warmup-max-tokens"):
        bench.validate_args(args)


def test_validate_args_rejects_invalid_preflight_wait_values() -> None:
    args = bench.build_arg_parser().parse_args(["--model", "m", "--preflight-wait-seconds", "-1"])
    with pytest.raises(ValueError, match="--preflight-wait-seconds"):
        bench.validate_args(args)

    args = bench.build_arg_parser().parse_args([
        "--model",
        "m",
        "--preflight-retry-interval-seconds",
        "0",
    ])
    with pytest.raises(ValueError, match="--preflight-retry-interval-seconds"):
        bench.validate_args(args)
