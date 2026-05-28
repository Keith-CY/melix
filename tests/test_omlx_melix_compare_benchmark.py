from __future__ import annotations

import importlib.util
import hashlib
import io
import json
from pathlib import Path
import sys
import urllib.error

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
    with pytest.raises(ValueError, match="Header name is empty"):
        bench.parse_header_values([": value"])


def test_prompt_text_and_sse_edge_cases() -> None:
    assert bench.estimate_tokens_from_text("") == 0.0
    assert bench.estimate_tokens_from_text("abcd") == 1.0
    concise = bench.build_prompt(
        32,
        cache_profile="repeated",
        request_key="request-1",
        prompt_style="concise",
    )
    assert "MELIX-OMLX-BENCH-REPEATED" in concise
    assert "Keep the answer concise" in concise

    with pytest.raises(ValueError, match="prompt_token_target"):
        bench.build_prompt(0, cache_profile="repeated", request_key="r")
    with pytest.raises(ValueError, match="Unsupported cache profile"):
        bench.build_prompt(32, cache_profile="unknown", request_key="r")
    with pytest.raises(ValueError, match="Unsupported prompt style"):
        bench.build_prompt(32, cache_profile="repeated", request_key="r", prompt_style="unknown")

    assert bench.extract_openai_delta_text({"choices": "not-a-list"}) == ""
    assert bench.extract_openai_delta_text({"choices": [None]}) == ""
    assert bench.extract_openai_delta_text({
        "choices": [{"delta": {"content": [{"text": "hel"}, {"text": "lo"}]}}],
    }) == "hello"
    assert bench.extract_openai_delta_text({
        "choices": [{"message": {"reasoning_content": "think"}}],
    }) == "think"
    assert bench.extract_openai_delta_text({"choices": [{"text": "flat"}]}) == "flat"

    content, chunk_count, usage, saw_done = bench.parse_sse_data_lines([
        b": comment\n",
        b"\n",
        b"data: not-json\n",
        b"data: {\"choices\":[{\"message\":{\"content\":[{\"text\":\"hi\"}]}}]}\n",
        b"data: [DONE]\n",
    ])
    assert content == "hi"
    assert chunk_count == 1
    assert usage is None
    assert saw_done is True


def test_decode_json_body_handles_empty_invalid_and_array_payloads() -> None:
    assert bench._decode_json_body(b"") == {}
    assert bench._decode_json_body(b"not-json") == {"raw_body": "not-json"}
    assert bench._decode_json_body(b"[1, 2]") == {"payload": [1, 2]}


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


def test_stream_chat_completion_reports_http_and_transport_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    class FakeHttpError(urllib.error.HTTPError):
        def read(self):
            return b'{"error":{"message":"bad"}}'

    def fake_http_error(_request, timeout):
        raise FakeHttpError(
            url="http://example.test/v1/chat/completions",
            code=500,
            msg="bad",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(bench.urllib.request, "urlopen", fake_http_error)
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

    assert observation.status == "error"
    assert observation.http_status == 500
    assert "bad" in observation.error

    monkeypatch.setattr(bench.urllib.request, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
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
    assert observation.status == "error"
    assert observation.error == "RuntimeError: boom"


def test_stream_chat_completion_marks_empty_stream_as_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def readline(self):
            return b""

    monkeypatch.setattr(bench.urllib.request, "urlopen", lambda *_args, **_kwargs: FakeResponse())
    endpoint = bench.EndpointConfig("melix", "http://127.0.0.1:12434/v1", "target-model", {})
    scenario = bench.BenchmarkScenario("pt128-out16-c1-r0", 128, 16, 1, "repeated", 0)

    observation = bench.stream_chat_completion(
        endpoint,
        scenario,
        request_index=0,
        request_key="same",
        include_usage=False,
        temperature=0.0,
        top_p=1.0,
        top_k=0,
        timeout_seconds=5.0,
        group_id="group",
        group_elapsed_ms=0.0,
    )

    assert observation.status == "error"
    assert observation.error == "stream completed without text deltas"


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


def test_request_json_handles_http_error_and_extract_model_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeHttpError(urllib.error.HTTPError):
        def read(self):
            return b'{"error":{"message":"missing"}}'

    def fake_urlopen(_request, timeout):
        raise FakeHttpError(
            url="http://example.test/v1/models",
            code=503,
            msg="unavailable",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(bench.urllib.request, "urlopen", fake_urlopen)

    status, payload = bench.request_json(
        "http://example.test/v1/models",
        headers={},
        timeout_seconds=1.0,
    )

    assert status == 503
    assert payload == {"error": {"message": "missing"}}
    assert bench.extract_model_ids({"data": "not-a-list"}) == []
    assert bench.extract_model_ids({"data": [{"id": "a"}, {"id": 1}, "x"]}) == ["a"]


def test_preflight_wait_returns_when_timeout_expires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint = bench.EndpointConfig(
        name="melix",
        base_url="http://127.0.0.1:12434/v1",
        model="target-model",
        headers={},
    )
    times = iter([0.0, 0.2, 0.4])
    monkeypatch.setattr(bench.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(bench.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        bench,
        "preflight_endpoint",
        lambda *args, **kwargs: {
            "endpoint": "melix",
            "ok": False,
        },
    )

    preflight = bench.preflight_endpoints(
        [endpoint],
        timeout_seconds=1.0,
        wait_seconds=0.1,
        retry_interval_seconds=0.25,
    )

    assert preflight == [{"endpoint": "melix", "ok": False, "attempt_count": 1, "elapsed_seconds": 0.2}]


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


def test_statistics_helpers_cover_empty_and_percentile_edges() -> None:
    assert bench.median([None]) is None
    assert bench.percentile([None], 95) is None
    assert bench.percentile([5.0], 95) == 5.0
    assert bench.percentile([1.0, 2.0, 3.0], 50) == 2.0
    assert bench._is_regressed_latency(None, 100.0) is False
    assert bench._is_regressed_throughput(None, 100.0) is False
    assert bench._is_regressed_throughput(10.0, 0.0) is False


def test_comparison_hints_skip_missing_peer_and_flag_reliability() -> None:
    melix = bench.ScenarioSummary(
        endpoint="melix",
        model="model",
        prompt_token_target=128,
        max_tokens=64,
        concurrency=1,
        cache_profile="cold_unique",
        request_count=2,
        success_count=1,
        error_count=1,
        error_rate=0.5,
        median_ttft_ms=100.0,
        p95_ttft_ms=100.0,
        median_total_ms=200.0,
        p95_total_ms=200.0,
        median_decode_tokens_per_second=60.0,
        median_aggregate_output_tokens_per_second=60.0,
        median_completion_tokens=64.0,
    )
    omlx = bench.ScenarioSummary(
        endpoint="omlx",
        model="model",
        prompt_token_target=128,
        max_tokens=64,
        concurrency=1,
        cache_profile="cold_unique",
        request_count=2,
        success_count=2,
        error_count=0,
        error_rate=0.0,
        median_ttft_ms=100.0,
        p95_ttft_ms=100.0,
        median_total_ms=200.0,
        p95_total_ms=200.0,
        median_decode_tokens_per_second=60.0,
        median_aggregate_output_tokens_per_second=60.0,
        median_completion_tokens=64.0,
    )

    assert bench.comparison_hints([melix])[0:0] == []
    hints = bench.comparison_hints([melix, omlx])

    assert [hint["area"] for hint in hints] == ["reliability"]


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


def test_binary_metadata_detects_release_debug_and_sha256(tmp_path: Path) -> None:
    release_binary = tmp_path / "services/mlx-text-worker-swift/.build/release/melix-text-worker-swift"
    release_binary.parent.mkdir(parents=True)
    release_binary.write_bytes(b"release-binary")
    debug_binary = tmp_path / "services/control-plane-swift/.build/arm64-apple-macosx/debug/melix-control-plane"
    debug_binary.parent.mkdir(parents=True)
    debug_binary.write_bytes(b"debug-binary")

    release = bench.binary_metadata(release_binary)
    debug = bench.binary_metadata(debug_binary)

    assert release["build_mode"] == "release"
    assert release["sha256"] == hashlib.sha256(b"release-binary").hexdigest()
    assert debug["build_mode"] == "debug"
    assert debug["sha256"] == hashlib.sha256(b"debug-binary").hexdigest()


def test_detect_swift_build_mode_prefers_innermost_build_directory() -> None:
    path = Path("/outer/.build/debug/package/services/worker/.build/release/melix-text-worker-swift")

    assert bench.detect_swift_build_mode(path) == "release"


def test_binary_metadata_marks_unreadable_binary_without_raising(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_binary = tmp_path / ".build/release/melix-text-worker-swift"
    release_binary.parent.mkdir(parents=True)
    release_binary.write_bytes(b"release")
    monkeypatch.setattr(
        bench,
        "file_sha256",
        lambda _path: (_ for _ in ()).throw(PermissionError("denied")),
    )

    metadata = bench.binary_metadata(release_binary)

    assert metadata["provided"] is True
    assert metadata["exists"] is False
    assert metadata["build_mode"] == "release"
    assert metadata["sha256"] is None
    assert "not readable" in metadata["error"]


def test_comparison_validity_uses_binary_error_reason(tmp_path: Path) -> None:
    missing_binary = tmp_path / ".build/release/missing-text-worker"
    release_control = tmp_path / "control/.build/release/melix-control-plane"
    release_control.parent.mkdir(parents=True)
    release_control.write_bytes(b"release")
    metadata = {
        "melix": {
            "binaries": {
                "text_worker": bench.binary_metadata(missing_binary),
                "control_plane": bench.binary_metadata(release_control),
            },
        },
    }

    validity = bench.comparison_validity_metadata(metadata, comparison_scope="peer")

    assert validity["status"] == "invalid"
    assert "binary error: binary path does not exist or is not a file" in validity["reasons"][0]
    assert str(missing_binary) in validity["reasons"][0]


def test_comparison_validity_rejects_debug_melix_binary(tmp_path: Path) -> None:
    debug_binary = tmp_path / ".build/debug/melix-text-worker-swift"
    debug_binary.parent.mkdir(parents=True)
    debug_binary.write_bytes(b"debug")
    release_control = tmp_path / "control/.build/release/melix-control-plane"
    release_control.parent.mkdir(parents=True)
    release_control.write_bytes(b"release")
    metadata = {
        "melix": {
            "binaries": {
                "text_worker": bench.binary_metadata(debug_binary),
                "control_plane": bench.binary_metadata(release_control),
            },
        },
    }

    validity = bench.comparison_validity_metadata(metadata, comparison_scope="peer")

    assert validity["status"] == "invalid"
    assert validity["peer_comparison_valid"] is False
    assert "debug build path" in validity["reasons"][0]


def test_comparison_validity_rejects_missing_melix_binary_metadata() -> None:
    metadata = {
        "melix": {
            "binaries": {
                "text_worker": bench.binary_metadata(None),
                "control_plane": bench.binary_metadata(None),
            },
        },
    }

    validity = bench.comparison_validity_metadata(metadata, comparison_scope="peer")

    assert validity["status"] == "invalid"
    assert validity["peer_comparison_valid"] is False
    assert "binary metadata was not provided" in validity["reasons"][0]


def test_comparison_validity_rejects_unknown_melix_build_mode(tmp_path: Path) -> None:
    binary = tmp_path / "melix-text-worker-swift"
    binary.write_bytes(b"binary")
    release_control = tmp_path / "control/.build/release/melix-control-plane"
    release_control.parent.mkdir(parents=True)
    release_control.write_bytes(b"release")
    metadata = {
        "melix": {
            "binaries": {
                "text_worker": bench.binary_metadata(binary),
                "control_plane": bench.binary_metadata(release_control),
            },
        },
    }

    validity = bench.comparison_validity_metadata(metadata, comparison_scope="peer")

    assert validity["status"] == "invalid"
    assert "not a release build" in validity["reasons"][0]


def test_split_source_summary_skips_non_strings() -> None:
    assert bench._split_source_summary(["usage,estimate", None, 123, "unknown", "usage"]) == [
        "estimate",
        "usage",
    ]


def test_comparison_validity_rejects_mixed_token_accounting_by_default(
    tmp_path: Path,
) -> None:
    release_binary = tmp_path / ".build/release/melix-text-worker-swift"
    release_binary.parent.mkdir(parents=True)
    release_binary.write_bytes(b"release")
    release_control = tmp_path / "control/.build/release/melix-control-plane"
    release_control.parent.mkdir(parents=True)
    release_control.write_bytes(b"release")
    metadata = {
        "melix": {
            "binaries": {
                "text_worker": bench.binary_metadata(release_binary),
                "control_plane": bench.binary_metadata(release_control),
            },
        },
    }
    token_accounting = {
        "mixed_prompt_token_sources": True,
        "mixed_completion_token_sources": False,
        "allow_mixed_token_accounting": False,
    }

    validity = bench.comparison_validity_metadata(
        metadata,
        comparison_scope="peer",
        token_accounting=token_accounting,
    )

    assert validity["status"] == "invalid"
    assert "Prompt token accounting used mixed sources" in validity["reasons"][0]


def test_comparison_validity_allows_explicit_mixed_token_accounting(
    tmp_path: Path,
) -> None:
    release_binary = tmp_path / ".build/release/melix-text-worker-swift"
    release_binary.parent.mkdir(parents=True)
    release_binary.write_bytes(b"release")
    release_control = tmp_path / "control/.build/release/melix-control-plane"
    release_control.parent.mkdir(parents=True)
    release_control.write_bytes(b"release")
    metadata = {
        "melix": {
            "binaries": {
                "text_worker": bench.binary_metadata(release_binary),
                "control_plane": bench.binary_metadata(release_control),
            },
        },
    }
    token_accounting = {
        "mixed_prompt_token_sources": True,
        "mixed_completion_token_sources": True,
        "allow_mixed_token_accounting": True,
    }

    validity = bench.comparison_validity_metadata(
        metadata,
        comparison_scope="peer",
        token_accounting=token_accounting,
    )

    assert validity["status"] == "valid"
    assert validity["warnings"] == ["Mixed token accounting was explicitly allowed for this run."]


def test_comparison_validity_marks_debug_only_scope(tmp_path: Path) -> None:
    release_binary = tmp_path / ".build/release/melix-text-worker-swift"
    release_binary.parent.mkdir(parents=True)
    release_binary.write_bytes(b"release")
    release_control = tmp_path / "control/.build/release/melix-control-plane"
    release_control.parent.mkdir(parents=True)
    release_control.write_bytes(b"release")
    metadata = {
        "melix": {
            "binaries": {
                "text_worker": bench.binary_metadata(release_binary),
                "control_plane": bench.binary_metadata(release_control),
            },
        },
    }

    validity = bench.comparison_validity_metadata(metadata, comparison_scope="debug-only")

    assert validity["status"] == "debug_only"
    assert validity["peer_comparison_valid"] is False
    assert "debug-only" in validity["reasons"][0]


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


def test_metrics_snapshot_handles_missing_invalid_and_bad_sources(tmp_path: Path) -> None:
    assert bench.load_metrics_snapshot(None) is None
    missing_path = tmp_path / "missing.json"
    missing = bench.load_metrics_snapshot(missing_path)
    assert missing["ok"] is False
    assert "FileNotFoundError" in missing["error"]
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not-json", encoding="utf-8")
    assert bench.load_metrics_snapshot(invalid)["ok"] is False
    non_object = tmp_path / "array.json"
    non_object.write_text("[]", encoding="utf-8")
    assert bench.load_metrics_snapshot(non_object)["error"] == "metrics snapshot must be a JSON object"
    missing_values = tmp_path / "missing-values.json"
    missing_values.write_text("{}", encoding="utf-8")
    assert bench.load_metrics_snapshot(missing_values)["error"] == "metrics snapshot is missing a values object"

    snapshot = bench.load_melix_metrics_snapshot(
        control_plane_path=missing_path,
        swift_text_worker_path=None,
    )
    assert snapshot["ok"] is False
    assert "control_plane" in snapshot["error"]
    assert bench.load_melix_metrics_snapshot(control_plane_path=None, swift_text_worker_path=None) is None

    assert bench.enrich_hints_with_metrics([{"area": "existing"}], None) == [{"area": "existing"}]
    assert bench.enrich_hints_with_metrics([], {"ok": True, "values": []}) == []
    assert bench.metrics_manifest_entries(None, artifact_name="metrics.json") == {}


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
        measurement_profile={
            "profile": "cold",
            "warmup_requests_per_endpoint": 0,
            "operator_note": "",
        },
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
        top_p: float,
        top_k: int,
        timeout_seconds: float,
        run_key: str = "",
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
    assert manifest["scenario_settings"] == {
        "cache_profiles": ["cold_unique"],
        "concurrency": [1],
        "max_tokens": [128],
        "prompt_style": "concise",
        "prompt_styles": ["concise"],
        "prompt_token_targets": [1024],
        "repeat_count": 1,
    }
    assert manifest["token_accounting"] == {
        "allow_mixed_token_accounting": False,
        "include_usage_requested": False,
        "mixed_completion_token_sources": False,
        "mixed_prompt_token_sources": False,
        "observed_completion_token_sources": ["usage"],
        "observed_prompt_token_sources": ["usage"],
    }
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


def test_runtime_metadata_markdown_rows_include_non_binary_runtime_and_snapshot() -> None:
    rows = bench.runtime_metadata_markdown_rows({
        "melix": {
            "model": "melix-model",
            "revision": "sha",
            "version": "dev",
            "binaries": {
                "weird": "not-a-dict",
            },
        },
        "omlx": {
            "model": "omlx-model",
            "revision": "omlx-sha",
            "version": "0.3.12",
        },
        "swiftlm": {
            "model": "",
            "revision": "swift-sha",
            "version": "",
            "binaries": {
                "server": {
                    "build_mode": "release",
                    "sha256": "abc",
                },
            },
        },
        "model_snapshot": {
            "path": "/tmp/snapshot",
        },
    })

    assert "| omlx | `omlx-model` | `omlx-sha` | `0.3.12` | n/a | n/a |" in rows
    assert "| swiftlm:server | `` | `swift-sha` | `` | `release` | `abc` |" in rows
    assert "| model_snapshot | `/tmp/snapshot` |  |  | n/a | n/a |" in rows


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


def test_dry_run_manifest_records_runtime_metadata_and_invalid_debug_binary(
    tmp_path: Path,
) -> None:
    debug_text_worker = tmp_path / "services/mlx-text-worker-swift/.build/debug/melix-text-worker-swift"
    debug_text_worker.parent.mkdir(parents=True)
    debug_text_worker.write_bytes(b"debug-text-worker")
    release_control_plane = tmp_path / "services/control-plane-swift/.build/release/melix-control-plane"
    release_control_plane.parent.mkdir(parents=True)
    release_control_plane.write_bytes(b"release-control-plane")
    args = bench.build_arg_parser().parse_args(
        [
            "--model",
            "shared-model",
            "--melix-model",
            "melix-dev-text",
            "--omlx-model",
            "gemma-4-E4B-it-MLX-8bit",
            "--run-id",
            "metadata-run",
            "--staging-root",
            str(tmp_path),
            "--no-export",
            "--dry-run",
            "--melix-revision",
            "melix-sha",
            "--omlx-revision",
            "omlx-sha",
            "--omlx-version",
            "0.3.12",
            "--melix-text-worker-binary",
            str(debug_text_worker),
            "--melix-control-plane-binary",
            str(release_control_plane),
            "--model-snapshot-path",
            "/tmp/models--unsloth--gemma-4-E4B-it-MLX-8bit/snapshots/abc",
        ]
    )
    bench.validate_args(args)

    result = bench.run_benchmark(args)

    staging_dir = tmp_path / "metadata-run"
    manifest = json.loads((staging_dir / "manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((staging_dir / "summary.json").read_text(encoding="utf-8"))
    markdown = (staging_dir / "summary.md").read_text(encoding="utf-8")

    assert result["comparison_validity"]["status"] == "invalid"
    assert manifest["comparison_validity"]["peer_comparison_valid"] is False
    assert manifest["runtime_metadata"]["melix"]["revision"] == "melix-sha"
    assert manifest["runtime_metadata"]["omlx"]["revision"] == "omlx-sha"
    assert manifest["runtime_metadata"]["omlx"]["version"] == "0.3.12"
    assert manifest["runtime_metadata"]["melix"]["binaries"]["text_worker"]["build_mode"] == "debug"
    assert manifest["runtime_metadata"]["melix"]["binaries"]["text_worker"]["sha256"] == hashlib.sha256(
        b"debug-text-worker"
    ).hexdigest()
    assert manifest["runtime_metadata"]["melix"]["binaries"]["control_plane"]["build_mode"] == "release"
    assert summary["comparison_validity"]["status"] == "invalid"
    assert "- Peer comparison status: `invalid`" in markdown
    assert "Melix text_worker binary uses a debug build path" in markdown


def test_dry_run_manifest_records_release_binary_as_peer_valid(tmp_path: Path) -> None:
    release_text_worker = tmp_path / "services/mlx-text-worker-swift/.build/release/melix-text-worker-swift"
    release_text_worker.parent.mkdir(parents=True)
    release_text_worker.write_bytes(b"release-text-worker")
    release_control_plane = tmp_path / "services/control-plane-swift/.build/release/melix-control-plane"
    release_control_plane.parent.mkdir(parents=True)
    release_control_plane.write_bytes(b"release-control-plane")
    args = bench.build_arg_parser().parse_args(
        [
            "--model",
            "shared-model",
            "--run-id",
            "release-metadata-run",
            "--staging-root",
            str(tmp_path),
            "--no-export",
            "--dry-run",
            "--melix-text-worker-binary",
            str(release_text_worker),
            "--melix-control-plane-binary",
            str(release_control_plane),
        ]
    )
    bench.validate_args(args)

    bench.run_benchmark(args)

    manifest = json.loads((tmp_path / "release-metadata-run" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["comparison_validity"]["status"] == "valid"
    assert manifest["comparison_validity"]["peer_comparison_valid"] is True
    assert manifest["runtime_metadata"]["melix"]["binaries"]["text_worker"]["build_mode"] == "release"
    assert manifest["runtime_metadata"]["melix"]["binaries"]["control_plane"]["build_mode"] == "release"


def test_export_bundle_uses_suffix_when_destination_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "manifest.json").write_text("{}", encoding="utf-8")
    export_dir = tmp_path / "exports"
    existing = export_dir / "staging"
    existing.mkdir(parents=True)

    class FakeDateTime:
        @staticmethod
        def now(_timezone):
            class FakeNow:
                def strftime(self, _fmt):
                    return "123456"

            return FakeNow()

    monkeypatch.setattr(bench, "datetime", FakeDateTime)

    destination = bench.export_bundle(staging, export_dir)

    assert destination == export_dir / "staging-123456"
    assert (destination / "manifest.json").read_text(encoding="utf-8") == "{}"
    assert bench.export_bundle(staging, None) is None


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
    assert manifest["scenario_settings"] == {
        "cache_profiles": ["cold_unique"],
        "concurrency": [1],
        "max_tokens": [128],
        "prompt_style": "concise",
        "prompt_styles": ["concise"],
        "prompt_token_targets": [1024],
        "repeat_count": 1,
    }
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


def test_preflight_only_skips_warmup_and_measurement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint_results = {
        "melix": {
            "endpoint": "melix",
            "base_url": "http://127.0.0.1:12434/v1",
            "status_code": 200,
            "ok": True,
            "model": "local-model",
            "model_listed": True,
            "model_count": 1,
            "models": ["local-model"],
            "error": None,
        },
        "omlx": {
            "endpoint": "omlx",
            "base_url": "http://127.0.0.1:8000/v1",
            "status_code": 200,
            "ok": True,
            "model": "local-model",
            "model_listed": True,
            "model_count": 1,
            "models": ["local-model"],
            "error": None,
        },
    }
    monkeypatch.setattr(
        bench,
        "preflight_endpoint",
        lambda endpoint, *, timeout_seconds: endpoint_results[endpoint.name],
    )
    monkeypatch.setattr(
        bench,
        "run_group",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("run_group should not run")),
    )
    args = bench.build_arg_parser().parse_args([
        "--model",
        "local-model",
        "--preflight-only",
        "--run-id",
        "preflight-only",
        "--staging-root",
        str(tmp_path),
        "--no-export",
    ])
    bench.validate_args(args)

    result = bench.run_benchmark(args)

    assert result["observation_count"] == 0
    assert result["warmup_count"] == 0
    assert result["preflight"][0]["ok"] is True


def test_run_benchmark_blocks_failed_preflight_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        bench,
        "preflight_endpoint",
        lambda endpoint, *, timeout_seconds: {
            "endpoint": endpoint.name,
            "ok": endpoint.name != "melix",
            "model": endpoint.model,
        },
    )
    args = bench.build_arg_parser().parse_args([
        "--model",
        "local-model",
        "--run-id",
        "failed-preflight",
        "--staging-root",
        str(tmp_path),
        "--no-export",
    ])
    bench.validate_args(args)

    with pytest.raises(RuntimeError, match="Endpoint preflight failed"):
        bench.run_benchmark(args)


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


def test_validate_args_rejects_core_invalid_values() -> None:
    cases = [
        (["--model", "m", "--repeats", "0"], "--repeats"),
        (["--model", "m", "--max-tokens", "0"], "--max-tokens"),
        (["--model", "m", "--prompt-token-targets", "0"], "--prompt-token-targets"),
        (["--model", "m", "--concurrency", "0"], "--concurrency"),
        (["--model", "m", "--timeout-seconds", "0"], "Timeout values"),
        (["--model", "m", "--preflight-timeout-seconds", "0"], "Timeout values"),
    ]
    for argv, expected in cases:
        args = bench.build_arg_parser().parse_args(argv)
        with pytest.raises(ValueError, match=expected):
            bench.validate_args(args)


def test_main_prints_json_text_and_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        bench,
        "run_benchmark",
        lambda args: {
            "run_id": "run",
            "staging_dir": str(tmp_path / "run"),
            "exported_to": str(tmp_path / "exported"),
            "scenario_count": 1,
            "observation_count": 2,
            "optimization_hint_count": 3,
        },
    )

    assert bench.main(["--model", "m", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["run_id"] == "run"

    assert bench.main(["--model", "m"]) == 0
    text = capsys.readouterr().out
    assert "Run id: run" in text
    assert "Exported to:" in text

    monkeypatch.setattr(bench, "run_benchmark", lambda args: (_ for _ in ()).throw(RuntimeError("bad")))
    assert bench.main(["--model", "m"]) == 2
    assert "error: bad" in capsys.readouterr().err
