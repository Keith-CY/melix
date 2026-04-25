from __future__ import annotations

import builtins
import sys
from contextlib import contextmanager
from types import ModuleType
from threading import get_ident

import pytest

from worker.runtime.mlx_executor import MLXRuntimeExecutor


def test_executor_initializes_stream_and_runs_work_on_owned_thread() -> None:
    main_thread_id = get_ident()
    stream_init_thread_ids: list[int] = []

    def stream_factory() -> object:
        stream_init_thread_ids.append(get_ident())
        return object()

    executor = MLXRuntimeExecutor(stream_factory=stream_factory)
    try:
        first_thread_id = executor.run(get_ident)
        second_thread_id = executor.run(get_ident)
        snapshot = executor.snapshot()
    finally:
        executor.shutdown()

    assert first_thread_id == second_thread_id
    assert first_thread_id != main_thread_id
    assert stream_init_thread_ids == [first_thread_id]
    assert snapshot.generation_stream_owner_mode == "executor_owned"
    assert snapshot.worker_thread_init_latency_ms >= 0.0
    assert snapshot.stream_sync_fallback_count == 0


def test_executor_streams_items_and_propagates_generator_errors_from_owned_thread() -> None:
    executor = MLXRuntimeExecutor(stream_factory=lambda: object())
    producer_thread_ids: list[int] = []

    def producer():
        producer_thread_ids.append(get_ident())
        yield "first"
        producer_thread_ids.append(get_ident())
        raise RuntimeError("stream failed")

    try:
        iterator = executor.iterate(producer)
        assert next(iterator) == "first"
        with pytest.raises(RuntimeError, match="stream failed"):
            list(iterator)
        executor_thread_id = executor.run(get_ident)
    finally:
        executor.shutdown()

    assert producer_thread_ids == [executor_thread_id, executor_thread_id]


def test_executor_nested_run_executes_inline_on_owner_thread() -> None:
    executor = MLXRuntimeExecutor(stream_factory=lambda: object())
    try:
        owner_thread_id = executor.run(get_ident)
        nested_thread_id = executor.run(lambda: executor.run(get_ident))
    finally:
        executor.shutdown()

    assert nested_thread_id == owner_thread_id


def test_executor_rejects_work_after_shutdown() -> None:
    executor = MLXRuntimeExecutor(stream_factory=lambda: object())
    executor.shutdown()

    with pytest.raises(RuntimeError, match="shut down"):
        executor.run(lambda: "late")


def test_executor_uses_stream_context_and_synchronize_hook_on_owner_thread() -> None:
    stream = object()
    events: list[tuple[str, int, object]] = []

    @contextmanager
    def stream_context(active_stream):
        events.append(("enter", get_ident(), active_stream))
        try:
            yield
        finally:
            events.append(("exit", get_ident(), active_stream))

    def synchronize(active_stream) -> None:
        events.append(("sync", get_ident(), active_stream))

    executor = MLXRuntimeExecutor(
        stream_factory=lambda: stream,
        stream_context_factory=stream_context,
        synchronize_fn=synchronize,
    )
    try:
        owner_thread_id = executor.run(get_ident)
        executor.synchronize()
    finally:
        executor.shutdown()

    assert events == [
        ("enter", owner_thread_id, stream),
        ("exit", owner_thread_id, stream),
        ("enter", owner_thread_id, stream),
        ("sync", owner_thread_id, stream),
        ("exit", owner_thread_id, stream),
    ]


def test_executor_records_stream_initialization_failure_and_sync_fallback() -> None:
    fallback_calls: list[int] = []

    def fail_stream() -> object:
        raise RuntimeError("stream unavailable")

    def fail_sync(_stream) -> None:
        raise RuntimeError("sync unavailable")

    executor = MLXRuntimeExecutor(
        stream_factory=fail_stream,
        synchronize_fn=fail_sync,
        fallback_synchronize_fn=lambda: fallback_calls.append(get_ident()),
    )
    try:
        owner_thread_id = executor.run(get_ident)
        executor.synchronize()
        snapshot = executor.snapshot()
    finally:
        executor.shutdown()

    assert snapshot.generation_stream_owner_mode == "executor_owned_stream_init_failed"
    assert snapshot.stream_sync_fallback_count == 1
    assert fallback_calls == [owner_thread_id]


def test_executor_synchronize_noops_without_synchronize_hook() -> None:
    executor = MLXRuntimeExecutor(stream_factory=lambda: object())
    try:
        executor.synchronize()
        snapshot = executor.snapshot()
    finally:
        executor.shutdown()

    assert snapshot.stream_sync_fallback_count == 0


def test_executor_synchronize_uses_discoverable_mlx_fallback(monkeypatch) -> None:
    fallback_calls: list[str] = []
    fake_mlx = ModuleType("mlx")
    fake_core = ModuleType("mlx.core")
    fake_core.synchronize = lambda: fallback_calls.append("fallback")
    fake_mlx.core = fake_core
    monkeypatch.setitem(sys.modules, "mlx", fake_mlx)
    monkeypatch.setitem(sys.modules, "mlx.core", fake_core)

    def fail_sync(_stream) -> None:
        raise RuntimeError("sync unavailable")

    executor = MLXRuntimeExecutor(
        stream_factory=lambda: object(),
        synchronize_fn=fail_sync,
    )
    try:
        executor.synchronize()
        snapshot = executor.snapshot()
    finally:
        executor.shutdown()

    assert snapshot.stream_sync_fallback_count == 1
    assert fallback_calls == ["fallback"]


def test_executor_without_stream_factory_uses_discoverable_mlx_module(monkeypatch) -> None:
    stream = object()
    fake_mlx = ModuleType("mlx")
    fake_core = ModuleType("mlx.core")
    fake_core.gpu = object()
    fake_core.new_stream = lambda device: stream
    fake_core.set_default_stream = lambda active_stream: None
    fake_core.synchronize = lambda active_stream=None: None

    @contextmanager
    def fake_stream_context(active_stream):
        _ = active_stream
        yield

    fake_core.stream = fake_stream_context
    fake_mlx.core = fake_core
    monkeypatch.setitem(sys.modules, "mlx", fake_mlx)
    monkeypatch.setitem(sys.modules, "mlx.core", fake_core)

    executor = MLXRuntimeExecutor()
    try:
        assert executor.run(lambda: "ok") == "ok"
        snapshot = executor.snapshot()
    finally:
        executor.shutdown()

    assert snapshot.generation_stream_owner_mode == "executor_owned"


def test_executor_without_mlx_module_runs_without_stream(monkeypatch) -> None:
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "mlx.core":
            raise ModuleNotFoundError(name)
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    executor = MLXRuntimeExecutor()
    try:
        assert executor.run(lambda: "ok") == "ok"
        snapshot = executor.snapshot()
    finally:
        executor.shutdown()

    assert snapshot.generation_stream_owner_mode == "executor_owned_no_stream"
