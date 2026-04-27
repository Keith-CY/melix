from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from dataclasses import dataclass
from queue import Empty, Full, Queue
from threading import Event, Lock, get_ident
import time
from typing import Any, Callable, Iterable, Iterator, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class MLXExecutorSnapshot:
    generation_stream_owner_mode: str
    worker_thread_init_latency_ms: float
    stream_sync_fallback_count: int


class MLXRuntimeExecutor:
    def __init__(
        self,
        *,
        stream_factory: Callable[[], Any] | None = None,
        stream_context_factory: Callable[[Any], Any] | None = None,
        synchronize_fn: Callable[[Any | None], None] | None = None,
        fallback_synchronize_fn: Callable[[], None] | None = None,
        thread_name_prefix: str = "melix-mlx-runtime",
    ) -> None:
        self._stream_factory = stream_factory
        self._stream_context_factory = stream_context_factory
        self._synchronize_fn = synchronize_fn
        self._fallback_synchronize_fn = fallback_synchronize_fn
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=thread_name_prefix)
        self._lock = Lock()
        self._closed = False
        self._initialized = False
        self._owner_thread_id = 0
        self._stream: Any | None = None
        self._generation_stream_owner_mode = "uninitialized"
        self._worker_thread_init_latency_ms = 0.0
        self._stream_sync_fallback_count = 0

    def run(self, fn: Callable[[], T]) -> T:
        """Run work on the executor-owned thread.

        Nested calls from that same owner thread execute inline, so callers
        must keep any re-entrant submission chain bounded.
        """
        if self._is_owner_thread():
            return self._run_on_owner(fn)
        return self._submit(lambda: self._run_on_owner(fn))

    def iterate(self, producer: Callable[[], Iterable[T]]) -> Iterator[T]:
        output: Queue[tuple[str, T | BaseException | None]] = Queue(maxsize=16)
        stop_requested = Event()

        def publish(kind: str, payload: T | BaseException | None) -> bool:
            while True:
                if stop_requested.is_set():
                    return False
                try:
                    output.put((kind, payload), timeout=0.05)
                    return True
                except Full:
                    continue

        def pump() -> None:
            producer_iter: Iterator[T] | None = None
            try:
                self._ensure_initialized()
                context = self._stream_context()
                with context:
                    producer_iter = iter(producer())
                    for item in producer_iter:
                        if not publish("item", item):
                            return
            except BaseException as exc:
                publish("error", exc)
                if not isinstance(exc, Exception):
                    raise
            finally:
                if producer_iter is not None:
                    close = getattr(producer_iter, "close", None)
                    if callable(close):
                        close()
                publish("done", None)

        future = self._submit_async(pump)
        try:
            while True:
                kind, payload = output.get()
                if kind == "item":
                    yield payload  # type: ignore[misc]
                elif kind == "error":
                    raise payload  # type: ignore[misc]
                else:
                    # Cleanup is intentionally synchronous and unbounded here so
                    # the next task never reuses the single-owner executor while
                    # the current producer is still tearing down MLX state.
                    future.result()
                    break
        finally:
            stop_requested.set()
            while True:
                try:
                    output.get_nowait()
                except Empty:
                    break
            # Keep close() semantics aligned with the normal completion path:
            # do not release the owner thread until producer teardown finishes.
            future.result()

    def synchronize(self) -> None:
        self.run(self._synchronize_on_owner)

    def snapshot(self) -> MLXExecutorSnapshot:
        with self._lock:
            return MLXExecutorSnapshot(
                generation_stream_owner_mode=self._generation_stream_owner_mode,
                worker_thread_init_latency_ms=self._worker_thread_init_latency_ms,
                stream_sync_fallback_count=self._stream_sync_fallback_count,
            )

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
        self._executor.shutdown(wait=True, cancel_futures=True)

    def _submit(self, fn: Callable[[], T]) -> T:
        return self._submit_async(fn).result()

    def _submit_async(self, fn: Callable[[], T]):
        with self._lock:
            if self._closed:
                raise RuntimeError("MLX runtime executor is shut down.")
        return self._executor.submit(fn)

    def _run_on_owner(self, fn: Callable[[], T]) -> T:
        self._ensure_initialized()
        context = self._stream_context()
        with context:
            return fn()

    def _ensure_initialized(self) -> None:
        # Only callable from the executor-owned thread. We keep the MLX stream
        # discovery and lazy callback binding here so future callers do not
        # accidentally initialize stream state from an arbitrary gRPC thread.
        with self._lock:
            if self._initialized:
                return

        started_at = time.perf_counter()
        owner_thread_id = get_ident()
        try:
            stream, stream_context_factory, synchronize_fn = self._make_stream()
            generation_stream_owner_mode = (
                "executor_owned" if stream is not None else "executor_owned_no_stream"
            )
        except Exception:
            stream = None
            stream_context_factory = self._stream_context_factory
            synchronize_fn = self._synchronize_fn
            generation_stream_owner_mode = "executor_owned_stream_init_failed"
        worker_thread_init_latency_ms = max(0.0, (time.perf_counter() - started_at) * 1000.0)
        with self._lock:
            if self._initialized:
                return
            self._owner_thread_id = owner_thread_id
            self._stream = stream
            self._stream_context_factory = stream_context_factory
            self._synchronize_fn = synchronize_fn
            self._generation_stream_owner_mode = generation_stream_owner_mode
            self._worker_thread_init_latency_ms = worker_thread_init_latency_ms
            self._initialized = True

    def _make_stream(
        self,
    ) -> tuple[
        Any | None,
        Callable[[Any], Any] | None,
        Callable[[Any | None], None] | None,
    ]:
        if self._stream_factory is not None:
            return self._stream_factory(), self._stream_context_factory, self._synchronize_fn

        try:
            import mlx.core as mx
        except ModuleNotFoundError:
            return None, self._stream_context_factory, self._synchronize_fn

        stream = mx.new_stream(mx.gpu)
        mx.set_default_stream(stream)
        return stream, mx.stream, mx.synchronize

    def _stream_context(self):
        if self._stream is None or self._stream_context_factory is None:
            return nullcontext()
        return self._stream_context_factory(self._stream)

    def _synchronize_on_owner(self) -> None:
        self._ensure_initialized()
        try:
            if self._synchronize_fn is None:
                return
            self._synchronize_fn(self._stream)
        except Exception:
            with self._lock:
                self._stream_sync_fallback_count += 1
            if self._fallback_synchronize_fn is not None:
                self._fallback_synchronize_fn()
                return
            try:
                import mlx.core as mx
            except ModuleNotFoundError:
                return
            mx.synchronize()

    def _is_owner_thread(self) -> bool:
        with self._lock:
            return self._initialized and self._owner_thread_id == get_ident()
