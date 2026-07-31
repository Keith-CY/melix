"""MLX-backed verify step for prompt-lookup speculative decoding.

`PromptLookupDecoder` (see `prompt_lookup.py`) is deliberately MLX-free and
drives generation through an injected `step_fn`. This module supplies the real
one: a KV-cache-backed forward that returns the target model's greedy
predictions for a context plus a draft, in a single pass.

Cache position is reconciled from the authoritative context on every call
rather than tracked through accept/reject bookkeeping. The decoder always
passes the full committed context, so the step can compare it against how far
the cache has advanced and trim or extend accordingly. That makes the step
correct for any acceptance pattern — including a fully rejected draft — without
the step needing to know how many tokens the previous cycle accepted.
"""

from __future__ import annotations

from typing import Any, Sequence


class PromptLookupUnavailable(RuntimeError):
    """Raised when the MLX verify step cannot be constructed or advanced."""


class MLXPromptLookupStep:
    """Greedy `StepFn` over an mlx-lm model with an incremental prompt cache."""

    def __init__(self, model: Any, *, prefill_step_size: int = 512) -> None:
        self._model = model
        self._prefill_step_size = max(1, int(prefill_step_size))
        self._cache: Any = None
        self._cached_tokens = 0

    def __call__(self, context: Sequence[int], draft: Sequence[int]) -> list[int]:
        try:
            import mlx.core as mx
        except ImportError as exc:  # pragma: no cover - guarded at construction
            raise PromptLookupUnavailable("mlx is not installed") from exc

        context_tokens = [int(token) for token in context]
        if not context_tokens:
            return []
        # The cache must hold everything up to (but excluding) the last context
        # token; that token is the first input of this forward.
        target = len(context_tokens) - 1
        self._reconcile_cache(mx, context_tokens, target)

        inputs = context_tokens[target:] + [int(token) for token in draft]
        predictions = self._forward_argmax(mx, inputs)
        # The forward advanced the cache across every input, draft included. A
        # rejected draft leaves the cache long; the next call's reconcile trims
        # it back using the committed context.
        self._cached_tokens = target + len(inputs)
        return predictions

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _reconcile_cache(self, mx: Any, context_tokens: list[int], target: int) -> None:
        if self._cache is None:
            self._rebuild_cache()
        if self._cached_tokens > target:
            if not self._trim(self._cached_tokens - target):
                # Caches that cannot trim to an arbitrary boundary (rotating or
                # some quantized layouts) are rebuilt instead of reused, which
                # costs a re-prefill but never replays onto misaligned state.
                self._rebuild_cache()
        if self._cached_tokens < target:
            self._prefill(mx, context_tokens[self._cached_tokens : target])

    def _rebuild_cache(self) -> None:
        try:
            from mlx_lm.models.cache import make_prompt_cache
        except ImportError as exc:
            raise PromptLookupUnavailable("mlx-lm prompt cache support is unavailable") from exc
        self._cache = make_prompt_cache(self._model)
        self._cached_tokens = 0

    def _trim(self, trim_tokens: int) -> bool:
        if trim_tokens <= 0:
            return True
        try:
            from mlx_lm.models.cache import trim_prompt_cache
        except ImportError:
            return False
        try:
            trimmed = int(trim_prompt_cache(self._cache, trim_tokens))
        except Exception:
            return False
        if trimmed != trim_tokens:
            return False
        self._cached_tokens -= trim_tokens
        return True

    def _cache_eval_targets(self) -> list[Any]:
        """Collect the arrays that materialize this cache's KV state.

        Older mlx-lm caches expose `.state`; newer `KVCache` layouts expose
        `.keys`/`.values` and no `.state`. Passing a bare `getattr(layer,
        "state", None)` list straight to `mx.eval` therefore hands it `None`
        entries on those layouts, so the targets are collected the same way
        `_prefill_prompt_cache` already does it in `mlx_text_runtime`.
        """
        targets: list[Any] = []
        for layer in self._cache or ():
            state = getattr(layer, "state", None)
            if state is not None:
                targets.append(state)
                continue
            for attr in ("keys", "values"):
                value = getattr(layer, attr, None)
                if value is not None:
                    targets.append(value)
        return targets

    def _prefill(self, mx: Any, tokens: list[int]) -> None:
        if not tokens:
            return
        step = self._prefill_step_size
        for start in range(0, len(tokens), step):
            chunk = tokens[start : start + step]
            self._model(mx.array([chunk]), cache=self._cache)
            eval_targets = self._cache_eval_targets()
            if eval_targets:
                mx.eval(eval_targets)
            self._cached_tokens += len(chunk)

    def _forward_argmax(self, mx: Any, inputs: list[int]) -> list[int]:
        logits = self._model(mx.array([inputs]), cache=self._cache)
        predictions = mx.argmax(logits[0], axis=-1)
        mx.eval(predictions)
        return [int(token) for token in predictions.tolist()]


def build_mlx_step(model: Any, *, prefill_step_size: int = 512) -> MLXPromptLookupStep:
    """Construct the verify step, failing fast when MLX is unusable.

    Raising here (rather than mid-generation) lets the runtime fall back to the
    standard decode path before a single token has been emitted.
    """
    try:
        import mlx.core  # noqa: F401
        from mlx_lm.models.cache import make_prompt_cache  # noqa: F401
    except ImportError as exc:
        raise PromptLookupUnavailable("mlx-lm prompt cache support is unavailable") from exc
    if not callable(model):
        raise PromptLookupUnavailable("model is not callable")
    return MLXPromptLookupStep(model, prefill_step_size=prefill_step_size)
