from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from worker.productization import serving_diagnostics as serving_diagnostics_module
from worker.productization.serving_diagnostics import (
    BoundedServingDiagnosticsEventQueue,
    ServingDiagnosticsComparisonError,
    ServingDiagnosticsEvent,
    ServingDiagnosticsRequestSummary,
    ServingEvidenceRun,
    validate_prefill_chunk_size,
    write_baseline_accelerated_evidence,
    write_serving_diagnostics_bundle,
)


def test_serving_diagnostics_bundle_writes_stable_layout_and_prefill_fields(
    tmp_path: Path,
) -> None:
    summary = ServingDiagnosticsRequestSummary(
        request_id="req-1",
        task_kind="text-generation",
        model_id="mlx-community/Qwen3.5-9B-MLX-4bit",
        runtime_kind="mlx-text",
        acceleration_mode="baseline",
        prompt_protocol_id="chat.completions.v1",
        prompt_digest="sha256:prompt",
        prompt_template_digest="sha256:template",
        generation_config={"temperature": 0.0, "top_p": 1.0, "top_k": 1},
        status="completed",
        finish_reason="stop",
        prompt_tokens=128,
        completion_tokens=32,
        prefill_chunk_size=64,
        prefill_ms=12.5,
        decode_ms=22.0,
        prompt_tps=256.0,
        generation_tps=42.0,
        prefill_tokens_per_second=256.0,
        cache_hit_tokens=96,
        cache_miss_tokens=32,
        cache_restored_tokens=64,
        cache_computed_tokens=64,
        memory_used_bytes=1024,
        memory_total_bytes=4096,
        peak_memory_bytes=2048,
    )
    event = ServingDiagnosticsEvent(
        request_id="req-1",
        phase="prefill",
        event_index=0,
        status="completed",
        duration_ms=12.5,
        attributes={"prefill_chunk_size": 64, "cache_hit_tokens": 96},
    )

    paths = write_serving_diagnostics_bundle(
        output_root=tmp_path,
        bundle_id="diag-1",
        invocation={"command": "melix serve --diagnostics diag-1"},
        effective_config={"runtime": {"mode": "baseline"}},
        model_refs={"model_id": summary.model_id, "snapshot": "snap-1"},
        request_summary=summary,
        events=(event,),
        diagnostics_mode="debug",
    )

    bundle_root = tmp_path / "serving-diagnostics" / "diag-1"
    assert paths["bundle_root"] == bundle_root
    assert set(paths) == {
        "bundle_root",
        "manifest",
        "effective_config",
        "request_summary",
        "events",
    }

    manifest = json.loads((bundle_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "melix.serving_diagnostics.manifest.v1"
    assert manifest["diagnostics_mode"] == "debug"
    assert manifest["artifacts"] == {
        "effective_config": "effective-config.json",
        "request_summary": "request-summary.json",
        "events": "events.jsonl",
    }
    assert manifest["public_performance_claim_eligible"] is False

    effective_config = json.loads((bundle_root / "effective-config.json").read_text(encoding="utf-8"))
    assert effective_config["runtime"]["mode"] == "baseline"

    request_payload = json.loads((bundle_root / "request-summary.json").read_text(encoding="utf-8"))
    assert request_payload["prefill_chunk_size"] == 64
    assert request_payload["prefill_tokens_per_second"] == 256.0
    assert request_payload["prompt_tps"] == 256.0
    assert request_payload["generation_tps"] == 42.0
    assert request_payload["cache_hit_tokens"] == 96
    assert request_payload["cache_miss_tokens"] == 32
    assert request_payload["cache_restored_tokens"] == 64
    assert request_payload["cache_computed_tokens"] == 64
    assert request_payload["finish_reason"] == "stop"
    assert not hasattr(summary, "__dict__")

    event_rows = [
        json.loads(line)
        for line in (bundle_root / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert event_rows == [
        {
            "schema_version": "melix.serving_diagnostics.event.v1",
            "request_id": "req-1",
            "phase": "prefill",
            "event_index": 0,
            "status": "completed",
            "duration_ms": 12.5,
            "attributes": {"cache_hit_tokens": 96, "prefill_chunk_size": 64},
        }
    ]


def test_serving_diagnostics_event_empty_attributes_match_explicit_empty_mapping() -> None:
    default_event = ServingDiagnosticsEvent(
        request_id="req-empty-default",
        phase="decode",
        event_index=1,
        status="completed",
    )
    explicit_empty_event = ServingDiagnosticsEvent(
        request_id="req-empty-explicit",
        phase="decode",
        event_index=1,
        status="completed",
        attributes={},
    )

    default_payload = default_event.to_dict()
    explicit_payload = explicit_empty_event.to_dict()

    assert default_payload["attributes"] == {}
    assert explicit_payload["attributes"] == {}


def test_serving_diagnostics_bounded_queue_drops_oldest_without_blocking(
    tmp_path: Path,
) -> None:
    queue = BoundedServingDiagnosticsEventQueue(max_events=2)
    assert queue.append(
        ServingDiagnosticsEvent(request_id="req-queue", phase="prefill", event_index=0, status="completed")
    ) is True
    assert queue.append(
        ServingDiagnosticsEvent(request_id="req-queue", phase="decode", event_index=1, status="completed")
    ) is True
    assert queue.append(
        ServingDiagnosticsEvent(request_id="req-queue", phase="decode", event_index=2, status="completed")
    ) is False
    snapshot = queue.snapshot()
    assert snapshot.dropped_count == 1
    assert [event.event_index for event in snapshot.events] == [1, 2]

    summary = ServingDiagnosticsRequestSummary(
        request_id="req-queue",
        task_kind="text-generation",
        model_id="melix-dev-text",
        runtime_kind="deterministic",
        acceleration_mode="baseline",
        prompt_protocol_id="chat.completions.v1",
        prompt_digest="sha256:prompt",
        prompt_template_digest="sha256:template",
        generation_config={},
        status="completed",
        finish_reason="stop",
    )
    paths = write_serving_diagnostics_bundle(
        output_root=tmp_path,
        bundle_id="diag-queue",
        invocation={},
        effective_config={},
        model_refs={},
        request_summary=summary,
        events=snapshot,
        diagnostics_mode="debug",
    )

    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["public_performance_claim_eligible"] is False
    assert manifest["event_count"] == 2
    assert manifest["dropped_event_count"] == 1
    event_rows = [
        json.loads(line)
        for line in paths["events"].read_text(encoding="utf-8").splitlines()
    ]
    assert [row["event_index"] for row in event_rows] == [1, 2]


def test_serving_diagnostics_queue_append_uses_retained_count_without_len() -> None:
    event = ServingDiagnosticsEvent(
        request_id="req-retained-count",
        phase="decode",
        event_index=0,
        status="completed",
    )

    class NoLenBuffer:
        def __init__(self) -> None:
            self.events: list[ServingDiagnosticsEvent] = []

        def __len__(self) -> int:
            raise AssertionError(
                "append should use the retained counter, not len(_events)"
            )  # pragma: no cover

        def append(self, queued_event: ServingDiagnosticsEvent) -> None:
            self.events.append(queued_event)

    queue = BoundedServingDiagnosticsEventQueue(max_events=2)
    buffer = NoLenBuffer()
    queue._events = buffer  # type: ignore[assignment]
    queue._append_event = buffer.append  # type: ignore[method-assign]

    assert queue.append(event) is True
    assert buffer.events == [event]


def test_serving_diagnostics_event_instances_use_slots_for_debug_queue() -> None:
    event = ServingDiagnosticsEvent(
        request_id="req-slots",
        phase="decode",
        event_index=1,
        status="completed",
        duration_ms=0.25,
        attributes={"token": "***"},
    )

    assert hasattr(event, "__dict__") is False
    assert event.to_dict()["attributes"] == {"token": "***"}
    with pytest.raises(AttributeError):
        event.status = "mutated"  # type: ignore[misc]


def test_serving_diagnostics_queue_snapshot_uses_slots_for_debug_queue() -> None:
    event = ServingDiagnosticsEvent(
        request_id="req-snapshot-slots",
        phase="decode",
        event_index=1,
        status="completed",
    )
    queue = BoundedServingDiagnosticsEventQueue(max_events=1)
    queue.append(event)
    queue_snapshot = queue.snapshot()

    assert hasattr(queue_snapshot, "__dict__") is False
    assert queue_snapshot.events == (event,)


def test_serving_diagnostics_default_event_attributes_reuse_empty_mapping() -> None:
    first = ServingDiagnosticsEvent(
        request_id="req-empty-1",
        phase="decode",
        event_index=1,
        status="completed",
    )
    second = ServingDiagnosticsEvent(
        request_id="req-empty-2",
        phase="decode",
        event_index=2,
        status="completed",
    )

    assert first.attributes == {}
    assert first.to_dict()["attributes"] == {}
    assert first.attributes is second.attributes
    with pytest.raises(TypeError):
        first.attributes["late"] = "mutation"  # type: ignore[index]


def test_serving_diagnostics_empty_event_attributes_skip_stable_json_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = ServingDiagnosticsEvent(
        request_id="req-empty-fast-path",
        phase="decode",
        event_index=3,
        status="completed",
    )

    def fail_stable_json_object(_: object) -> dict[str, object]:  # pragma: no cover
        raise AssertionError("empty event attributes should not call _stable_json_object")

    monkeypatch.setattr(
        serving_diagnostics_module,
        "_stable_json_object",
        fail_stable_json_object,
    )

    assert event.to_dict()["attributes"] == {}


def test_serving_diagnostics_jsonl_fast_path_reuses_request_id_literal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    original_encoder = serving_diagnostics_module._json_string_literal

    def counting_encoder(value: str) -> str:
        calls.append(value)
        return original_encoder(value)

    monkeypatch.setattr(
        serving_diagnostics_module,
        "_json_string_literal",
        counting_encoder,
    )
    rows = tuple(
        ServingDiagnosticsEvent(
            request_id="req-shared-fast-path",
            phase="decode",
            event_index=event_index,
            status="completed",
            duration_ms=0.001,
        )
        for event_index in range(3)
    )
    path = tmp_path / "events.jsonl"

    serving_diagnostics_module._write_jsonl(path, rows)

    payloads = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [payload["event_index"] for payload in payloads] == [0, 1, 2]
    assert {payload["request_id"] for payload in payloads} == {"req-shared-fast-path"}
    assert calls == ["req-shared-fast-path"]


def test_serving_diagnostics_jsonl_fast_path_preserves_direct_helper_call() -> None:
    event = ServingDiagnosticsEvent(
        request_id="req-direct-fast-path",
        phase="decode",
        event_index=7,
        status="completed",
        duration_ms=0.001,
    )

    line = serving_diagnostics_module._empty_attribute_event_json_line(event)

    assert line is not None
    assert json.loads(line)["request_id"] == "req-direct-fast-path"


def test_serving_diagnostics_jsonl_fast_path_builds_direct_bytes() -> None:
    event = ServingDiagnosticsEvent(
        request_id="req-direct-bytes",
        phase="decode",
        event_index=11,
        status="completed",
        duration_ms=0.25,
    )

    line = serving_diagnostics_module._empty_attribute_event_json_line_bytes(event)

    assert isinstance(line, bytes)
    assert json.loads(line)["request_id"] == "req-direct-bytes"


def test_serving_diagnostics_jsonl_fast_path_reuses_duration_literal_cache() -> None:
    serving_diagnostics_module._ascii_float_literal.cache_clear()
    rows = tuple(
        ServingDiagnosticsEvent(
            request_id="req-duration-cache",
            phase="decode",
            event_index=event_index,
            status="completed",
            duration_ms=0.001,
        )
        for event_index in range(3)
    )

    for row in rows:
        line = serving_diagnostics_module._empty_attribute_event_json_line_bytes(row)
        assert line is not None
        assert json.loads(line)["duration_ms"] == 0.001

    cache_info = serving_diagnostics_module._ascii_float_literal.cache_info()
    assert cache_info.misses == 1
    assert cache_info.hits == 2


def test_serving_diagnostics_jsonl_fast_path_reuses_event_index_literal_cache() -> None:
    serving_diagnostics_module._ascii_int_literal.cache_clear()
    rows = tuple(
        ServingDiagnosticsEvent(
            request_id=f"req-index-cache-{sample_index}",
            phase="decode",
            event_index=4032,
            status="completed",
            duration_ms=0.001,
        )
        for sample_index in range(3)
    )

    for row in rows:
        line = serving_diagnostics_module._empty_attribute_event_json_line_bytes(row)
        assert line is not None
        assert json.loads(line)["event_index"] == 4032

    cache_info = serving_diagnostics_module._ascii_int_literal.cache_info()
    assert cache_info.misses == 1
    assert cache_info.hits == 2


def test_serving_diagnostics_jsonl_fast_path_preserves_generic_phase_status() -> None:
    event = ServingDiagnosticsEvent(
        request_id="req-generic-phase-status",
        phase="prefill",
        event_index=13,
        status="started",
        duration_ms=0.5,
    )

    line = serving_diagnostics_module._empty_attribute_event_json_line_bytes(event)

    assert line is not None
    assert json.loads(line) == event.to_dict()


def test_serving_diagnostics_jsonl_fast_path_direct_helper_preserves_fallback() -> None:
    event = ServingDiagnosticsEvent(
        request_id="req-direct-fallback",
        phase="decode",
        event_index=11,
        status="completed",
        duration_ms=0.25,
        attributes={"extra": True},
    )

    assert serving_diagnostics_module._empty_attribute_event_json_line(event) is None


def test_serving_diagnostics_event_to_dict_preserves_numeric_coercion() -> None:
    event = ServingDiagnosticsEvent(
        request_id="req-numeric-coercion",
        phase="decode",
        event_index=True,
        status="completed",
        duration_ms=3,
    )

    payload = event.to_dict()

    assert payload["event_index"] == 1
    assert type(payload["event_index"]) is int
    assert payload["duration_ms"] == 3.0
    assert type(payload["duration_ms"]) is float


def test_serving_diagnostics_bounded_queue_serializes_append_during_snapshot() -> None:
    first_event = ServingDiagnosticsEvent(
        request_id="req-concurrent",
        phase="prefill",
        event_index=0,
        status="completed",
    )
    second_event = ServingDiagnosticsEvent(
        request_id="req-concurrent",
        phase="decode",
        event_index=1,
        status="completed",
    )

    class InstrumentedBuffer:
        def __init__(self) -> None:
            self._events = [first_event]
            self.iteration_started = threading.Event()
            self.release_iteration = threading.Event()

        def __len__(self) -> int:
            return len(self._events)

        def append(self, event: ServingDiagnosticsEvent) -> None:
            if self.iteration_started.is_set() and not self.release_iteration.is_set():
                raise AssertionError("append entered while snapshot iteration was active")
            self._events.append(event)

        def __iter__(self):
            self.iteration_started.set()
            assert self.release_iteration.wait(timeout=2.0)
            return iter(tuple(self._events))

    queue = BoundedServingDiagnosticsEventQueue(max_events=8)
    instrumented = InstrumentedBuffer()
    queue._events = instrumented  # type: ignore[assignment]
    queue._append_event = instrumented.append  # type: ignore[method-assign]
    errors: list[BaseException] = []
    snapshots: list[tuple[int, ...]] = []

    def capture_snapshot() -> None:
        try:
            snapshot = queue.snapshot()
            snapshots.append(tuple(event.event_index for event in snapshot.events))
        except BaseException as exc:  # pragma: no cover - propagated below
            errors.append(exc)

    def append_event() -> None:
        try:
            assert queue.append(second_event) is True
        except BaseException as exc:  # pragma: no cover - propagated below
            errors.append(exc)

    snapshot_thread = threading.Thread(target=capture_snapshot)
    snapshot_thread.start()
    assert instrumented.iteration_started.wait(timeout=2.0)

    append_thread = threading.Thread(target=append_event)
    append_thread.start()
    instrumented.release_iteration.set()
    snapshot_thread.join(timeout=2.0)
    append_thread.join(timeout=2.0)

    assert snapshot_thread.is_alive() is False
    assert append_thread.is_alive() is False
    assert errors == []
    assert snapshots == [(0,)]
    assert [event.event_index for event in instrumented._events] == [0, 1]


def test_serving_diagnostics_summary_defaults_throughput_to_float_zero() -> None:
    payload = ServingDiagnosticsRequestSummary(
        request_id="req-idle",
        task_kind="text-generation",
        model_id="melix-dev-text",
        runtime_kind="deterministic",
        acceleration_mode="baseline",
        prompt_protocol_id="chat.completions.v1",
        prompt_digest="sha256:prompt",
        prompt_template_digest="sha256:template",
        generation_config={},
        status="completed",
        finish_reason="stop",
    ).to_dict()

    assert payload["prompt_tps"] == 0.0
    assert payload["generation_tps"] == 0.0
    assert isinstance(payload["prompt_tps"], float)
    assert isinstance(payload["generation_tps"], float)


@pytest.mark.parametrize("artifact_id", (".", "..", "", " nested/path", "bad\x00id"))
def test_serving_diagnostics_rejects_non_local_artifact_ids(
    tmp_path: Path,
    artifact_id: str,
) -> None:
    summary = ServingDiagnosticsRequestSummary(
        request_id="req-local",
        task_kind="text-generation",
        model_id="melix-dev-text",
        runtime_kind="deterministic",
        acceleration_mode="baseline",
        prompt_protocol_id="chat.completions.v1",
        prompt_digest="sha256:prompt",
        prompt_template_digest="sha256:template",
        generation_config={},
        status="completed",
        finish_reason="stop",
    )

    with pytest.raises(ValueError, match="path-local"):
        write_serving_diagnostics_bundle(
            output_root=tmp_path,
            bundle_id=artifact_id,
            invocation={},
            effective_config={},
            model_refs={},
            request_summary=summary,
            events=(),
            diagnostics_mode="debug",
        )


def test_serving_diagnostics_serializes_sets_as_stable_arrays(tmp_path: Path) -> None:
    summary = ServingDiagnosticsRequestSummary(
        request_id="req-set",
        task_kind="text-generation",
        model_id="melix-dev-text",
        runtime_kind="deterministic",
        acceleration_mode="baseline",
        prompt_protocol_id="chat.completions.v1",
        prompt_digest="sha256:prompt",
        prompt_template_digest="sha256:template",
        generation_config={},
        status="completed",
        finish_reason="stop",
    )
    event = ServingDiagnosticsEvent(
        request_id="req-set",
        phase="decode",
        event_index=0,
        status="completed",
        attributes={"tags": {"zeta", "alpha"}, "frozen": frozenset({3, 1, 2})},
    )

    paths = write_serving_diagnostics_bundle(
        output_root=tmp_path,
        bundle_id="diag-set",
        invocation={"modes": {"accelerated", "baseline"}},
        effective_config={},
        model_refs={},
        request_summary=summary,
        events=(event,),
        diagnostics_mode="debug",
    )

    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["invocation"]["modes"] == ["accelerated", "baseline"]
    event_payload = json.loads(paths["events"].read_text(encoding="utf-8"))
    assert event_payload["attributes"]["tags"] == ["alpha", "zeta"]
    assert event_payload["attributes"]["frozen"] == [1, 2, 3]


def test_serving_diagnostics_events_jsonl_uses_compact_stable_lines(tmp_path: Path) -> None:
    summary = ServingDiagnosticsRequestSummary(
        request_id="req-compact",
        task_kind="text-generation",
        model_id="melix-dev-text",
        runtime_kind="deterministic",
        acceleration_mode="baseline",
        prompt_protocol_id="chat.completions.v1",
        prompt_digest="sha256:prompt",
        prompt_template_digest="sha256:template",
        generation_config={},
        status="completed",
        finish_reason="stop",
    )
    event = ServingDiagnosticsEvent(
        request_id="req-compact",
        phase="decode",
        event_index=7,
        status="completed",
        attributes={"beta": 2, "alpha": 1},
    )

    paths = write_serving_diagnostics_bundle(
        output_root=tmp_path,
        bundle_id="diag-compact",
        invocation={},
        effective_config={},
        model_refs={},
        request_summary=summary,
        events=(event,),
        diagnostics_mode="debug",
    )

    line = paths["events"].read_text(encoding="utf-8")
    assert line == (
        '{"attributes":{"alpha":1,"beta":2},"duration_ms":0.0,'
        '"event_index":7,"phase":"decode","request_id":"req-compact",'
        '"schema_version":"melix.serving_diagnostics.event.v1",'
        '"status":"completed"}\n'
    )


def test_serving_diagnostics_events_jsonl_streams_default_attribute_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary = ServingDiagnosticsRequestSummary(
        request_id="req-empty-jsonl",
        task_kind="text-generation",
        model_id="melix-dev-text",
        runtime_kind="deterministic",
        acceleration_mode="baseline",
        prompt_protocol_id="chat.completions.v1",
        prompt_digest="sha256:prompt",
        prompt_template_digest="sha256:template",
        generation_config={},
        status="completed",
        finish_reason="stop",
    )
    event = ServingDiagnosticsEvent(
        request_id='req-"quoted"',
        phase="decode-音声",
        event_index=7,
        status="completed",
        duration_ms=0.001,
    )

    def fail_to_dict(_: object) -> dict[str, object]:  # pragma: no cover
        raise AssertionError("default-attribute JSONL rows should not materialize event dicts")

    monkeypatch.setattr(ServingDiagnosticsEvent, "to_dict", fail_to_dict)

    paths = write_serving_diagnostics_bundle(
        output_root=tmp_path,
        bundle_id="diag-empty-jsonl",
        invocation={},
        effective_config={},
        model_refs={},
        request_summary=summary,
        events=(event,),
        diagnostics_mode="debug",
    )

    line = paths["events"].read_text(encoding="utf-8")
    assert line == (
        '{"attributes":{},"duration_ms":0.001,"event_index":7,'
        '"phase":"decode-\\u97f3\\u58f0","request_id":"req-\\"quoted\\"",'
        '"schema_version":"melix.serving_diagnostics.event.v1",'
        '"status":"completed"}\n'
    )


def test_serving_diagnostics_events_jsonl_writes_bytearray_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    summary = ServingDiagnosticsRequestSummary(
        request_id="req-bytearray-jsonl",
        task_kind="text-generation",
        model_id="melix-dev-text",
        runtime_kind="deterministic",
        acceleration_mode="baseline",
        prompt_protocol_id="chat.completions.v1",
        prompt_digest="sha256:prompt",
        prompt_template_digest="sha256:template",
        generation_config={},
        status="completed",
        finish_reason="stop",
    )
    event = ServingDiagnosticsEvent(
        request_id="req-bytearray-jsonl",
        phase="decode",
        event_index=8,
        status="completed",
        duration_ms=0.25,
    )
    observed_payload_types: list[type[object]] = []
    original_write_bytes = Path.write_bytes

    def tracked_write_bytes(path: Path, data: bytes) -> int:
        if path.name == "events.jsonl":
            observed_payload_types.append(type(data))
        return original_write_bytes(path, data)

    monkeypatch.setattr(Path, "write_bytes", tracked_write_bytes)

    paths = write_serving_diagnostics_bundle(
        output_root=tmp_path,
        bundle_id="diag-bytearray-jsonl",
        invocation={},
        effective_config={},
        model_refs={},
        request_summary=summary,
        events=(event,),
        diagnostics_mode="debug",
    )

    assert observed_payload_types == [bytearray]
    assert paths["events"].read_text(encoding="utf-8").endswith('"status":"completed"}\n')


def test_serving_diagnostics_events_jsonl_falls_back_for_non_exact_numeric_fields(
    tmp_path: Path,
) -> None:
    summary = ServingDiagnosticsRequestSummary(
        request_id="req-fallback-jsonl",
        task_kind="text-generation",
        model_id="melix-dev-text",
        runtime_kind="deterministic",
        acceleration_mode="baseline",
        prompt_protocol_id="chat.completions.v1",
        prompt_digest="sha256:prompt",
        prompt_template_digest="sha256:template",
        generation_config={},
        status="completed",
        finish_reason="stop",
    )
    event = ServingDiagnosticsEvent(
        request_id="req-fallback",
        phase="decode",
        event_index=True,
        status="completed",
        duration_ms=1,
    )
    nonfinite_event = ServingDiagnosticsEvent(
        request_id="req-nonfinite",
        phase="decode",
        event_index=2,
        status="completed",
        duration_ms=float("inf"),
    )

    paths = write_serving_diagnostics_bundle(
        output_root=tmp_path,
        bundle_id="diag-fallback-jsonl",
        invocation={},
        effective_config={},
        model_refs={},
        request_summary=summary,
        events=(event, nonfinite_event),
        diagnostics_mode="debug",
    )

    rows = [
        json.loads(line)
        for line in paths["events"].read_text(encoding="utf-8").splitlines()
    ]
    payload = rows[0]
    assert payload["event_index"] == 1
    assert type(payload["event_index"]) is int
    assert payload["duration_ms"] == 1.0
    assert type(payload["duration_ms"]) is float
    assert rows[1]["duration_ms"] == float("inf")


@pytest.mark.parametrize("value", (0, -1, "0", "bad", None))
def test_validate_prefill_chunk_size_rejects_invalid_overrides(value: object) -> None:
    with pytest.raises(ValueError, match="prefill_chunk_size"):
        validate_prefill_chunk_size(value)


def test_validate_prefill_chunk_size_accepts_positive_integer_string() -> None:
    assert validate_prefill_chunk_size("128") == 128


def test_baseline_accelerated_evidence_requires_same_protocol_and_greedy_sampler(
    tmp_path: Path,
) -> None:
    baseline = _evidence_run(
        run_id="baseline",
        acceleration_mode="baseline",
        acceleration_admitted=False,
        fallback_reason="",
    )
    accelerated = _evidence_run(
        run_id="accelerated",
        acceleration_mode="sparse_prefill",
        acceleration_admitted=True,
        fallback_reason="",
        metrics={"prefill_ms": 7.0, "decode_ms": 20.0},
    )

    paths = write_baseline_accelerated_evidence(
        output_root=tmp_path,
        comparison_id="cmp-1",
        baseline=baseline,
        accelerated=accelerated,
    )

    payload = json.loads(paths["comparison"].read_text(encoding="utf-8"))
    assert payload["schema_version"] == "melix.serving_diagnostics.comparison.v1"
    assert payload["comparison_validity"] == "valid"
    assert payload["methodology"] == {
        "prompt_protocol_id": "chat.completions.v1",
        "prompt_digest": "sha256:prompt",
        "model_id": "melix-dev-text",
        "task_kind": "text-generation",
        "effective_temperature": 0.0,
        "effective_top_p": 1.0,
        "effective_top_k": 1,
        "sampler_is_greedy": True,
        "tier_stability_status": "stable",
    }
    assert payload["runs"]["accelerated"]["acceleration_admitted"] is True
    assert payload["runs"]["accelerated"]["fallback_reason"] == ""
    prefill_row = next(row for row in payload["phase_rows"] if row["phase"] == "prefill")
    assert prefill_row["baseline"] == 10.0
    assert prefill_row["accelerated"] == 7.0
    assert prefill_row["delta"] == -3.0

    with pytest.raises(ServingDiagnosticsComparisonError, match="prompt_protocol_id"):
        write_baseline_accelerated_evidence(
            output_root=tmp_path,
            comparison_id="cmp-mismatch",
            baseline=baseline,
            accelerated=_evidence_run(
                run_id="accelerated-mismatch",
                acceleration_mode="sparse_prefill",
                acceleration_admitted=True,
                prompt_protocol_id="responses.v1",
            ),
        )

    with pytest.raises(ServingDiagnosticsComparisonError, match="greedy"):
        write_baseline_accelerated_evidence(
            output_root=tmp_path,
            comparison_id="cmp-nongreedy",
            baseline=baseline,
            accelerated=_evidence_run(
                run_id="accelerated-nongreedy",
                acceleration_mode="sparse_prefill",
                acceleration_admitted=True,
                effective_temperature=0.7,
            ),
        )


@pytest.mark.parametrize(
    ("metrics", "match"),
    (
        ({"prefill_ms": 10.0}, "decode_ms"),
        ({"prefill_ms": 10.0, "decode_ms": float("nan")}, "finite number"),
        ({"prefill_ms": 10.0, "decode_ms": "bad"}, "finite number"),
    ),
)
def test_baseline_accelerated_evidence_rejects_invalid_phase_metrics(
    tmp_path: Path,
    metrics: dict[str, object],
    match: str,
) -> None:
    with pytest.raises(ServingDiagnosticsComparisonError, match=match):
        write_baseline_accelerated_evidence(
            output_root=tmp_path,
            comparison_id="cmp-invalid-metric",
            baseline=_evidence_run(
                run_id="baseline",
                acceleration_mode="baseline",
                acceleration_admitted=False,
                metrics=metrics,  # type: ignore[arg-type]
            ),
            accelerated=_evidence_run(
                run_id="accelerated",
                acceleration_mode="sparse_prefill",
                acceleration_admitted=True,
            ),
        )

    assert not (tmp_path / "serving-diagnostics" / "cmp-invalid-metric").exists()


def _evidence_run(
    *,
    run_id: str,
    acceleration_mode: str,
    acceleration_admitted: bool,
    fallback_reason: str = "",
    prompt_protocol_id: str = "chat.completions.v1",
    effective_temperature: float = 0.0,
    metrics: dict[str, float] | None = None,
) -> ServingEvidenceRun:
    return ServingEvidenceRun(
        run_id=run_id,
        model_id="melix-dev-text",
        task_kind="text-generation",
        prompt_protocol_id=prompt_protocol_id,
        prompt_digest="sha256:prompt",
        prompt_template_digest="sha256:template",
        generation_config={"max_output_tokens": 32},
        acceleration_mode=acceleration_mode,
        acceleration_admitted=acceleration_admitted,
        fallback_reason=fallback_reason,
        effective_temperature=effective_temperature,
        effective_top_p=1.0,
        effective_top_k=1,
        tier_stability_status="stable",
        metrics=metrics or {"prefill_ms": 10.0, "decode_ms": 20.0},
    )
