from __future__ import annotations

from collections.abc import Iterable
from copy import copy
from dataclasses import dataclass
from dataclasses import replace
import importlib.util
import inspect
import json
import os
from pathlib import Path
import re
import time
from typing import Any

from worker.runtime.mlx_executor import MLXRuntimeExecutor
from worker.runtime.prefix_block_store import (
    LCPResult as _LCPResult,
    clone_cache_snapshot as _clone_cache_snapshot,
    get_store as _get_prefix_store,
)
from worker.runtime.runtime_utils import (
    callable_accepts_kwarg as _callable_accepts_kwarg,
    estimate_model_weight_resident_bytes as _estimate_model_weight_resident_bytes,
    first_declared_kwarg as _first_declared_kwarg,
    installed_package_version as _installed_package_version,
)
from worker.runtime.text_family_adapters import resolve_text_family_config


class RuntimeUnavailableError(RuntimeError):
    pass


@dataclass(slots=True)
class NativeMTPBatchTimings:
    """MTP-specific timing and counter metrics — only populated on terminal events."""

    cycle_count: int | None
    mtp_head_ms: float | None
    sample_ms: float | None
    cache_ops_ms: float | None
    insert_ms: float | None
    prepare_ms: float | None
    prompt_encode_ms: float | None
    prefill_ms: float | None
    batch_insert_ms: float | None
    first_response_ms: float | None
    first_visible_ms: float | None


@dataclass(slots=True)
class RuntimeTokenEvent:
    text: str
    raw_text: str | None = None
    token_ids: tuple[int, ...] = ()
    token_logprobs: tuple[float, ...] = ()
    token_bytes: bytes | None = None
    parser_observation: str = ""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    prompt_tps: float | None = None
    generation_tps: float | None = None
    peak_memory: float | None = None
    finish_reason: str | None = None
    speculative_acceptance_rate: float | None = None
    speculative_rollback_rate: float | None = None
    speculative_accepted_tokens: int | None = None
    speculative_rejected_tokens: int | None = None
    speculative_fallback_count: int | None = None
    speculative_num_draft_tokens: int | None = None
    speculative_draft_model_configured: bool | None = None
    speculative_draft_propose_ms: float | None = None
    speculative_target_verify_ms: float | None = None
    native_mtp_timings: NativeMTPBatchTimings | None = None
    dflash_enabled: bool | None = None
    dflash_block_size: int | None = None
    dflash_rollback_count: int | None = None
    dflash_target_hidden_layers: int | None = None
    cache_hit_mode: str | None = None
    recovered_prefix_tokens: int | None = None
    cache_fallback_reason: str | None = None


@dataclass(slots=True)
class RuntimeToolCallEvent:
    call_id: str
    tool_name: str
    arguments_json_fragment: str


@dataclass(slots=True)
class RuntimeAnnotationEvent:
    annotation_id: str
    kind: str
    start_offset: int
    end_offset: int
    payload_json: str


@dataclass(slots=True)
class RuntimeToolResultEvent:
    call_id: str
    status: str
    result_json: str


_REWARD_SCORE_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)")


@dataclass(frozen=True)
class ResolvedTextStopContract:
    sequences: tuple[str, ...]
    resolved_stop_token_count: int
    source: str


def _normalized_ext_value(model_spec, key: str) -> str:
    return str(getattr(model_spec, "ext", {}).get(key, "") or "").strip()


def _reward_score_ext(
    loaded_model: Any,
    execution_ext: dict[str, str] | None,
) -> dict[str, str]:
    ext: dict[str, str] = {}
    if isinstance(loaded_model, dict):
        for key in ("model_ext", "metadata", "ext"):
            if isinstance(raw_ext := loaded_model.get(key), dict):
                ext.update({str(raw_key): str(raw_value) for raw_key, raw_value in raw_ext.items()})
    if execution_ext:
        ext.update({str(raw_key): str(raw_value) for raw_key, raw_value in execution_ext.items()})
    return ext


def _reward_score_prompt(
    loaded_model: Any,
    *,
    prompt: str,
    response: str,
    execution_ext: dict[str, str] | None,
) -> str:
    ext = _reward_score_ext(loaded_model, execution_ext)
    template = (
        ext.get("melix.reward_model.score_prompt_template")
        or ext.get("melix.reward_model.scoring_prompt_template")
        or ""
    )
    if template.strip():
        return template.replace("{prompt}", prompt).replace("{response}", response)

    return (
        "Score the assistant response for helpfulness and correctness on a 0 to 1 scale.\n"
        "Return only one decimal number between 0 and 1.\n\n"
        f"User prompt:\n{prompt}\n\n"
        f"Assistant response:\n{response}\n\n"
        "Score:"
    )


def _reward_score_max_tokens(
    loaded_model: Any,
    execution_ext: dict[str, str] | None,
) -> int:
    ext = _reward_score_ext(loaded_model, execution_ext)
    for key in ("melix.reward_model.score_max_tokens", "melix.reward_model.max_tokens"):
        raw_value = str(ext.get(key, "") or "").strip()
        if not raw_value:
            continue
        try:
            value = int(raw_value)
        except ValueError:
            continue
        if value > 0:
            return value
    return 8


def _parse_reward_score_text(text: str) -> float:
    for match in _REWARD_SCORE_RE.finditer(text):
        value = float(match.group(0))
        if 0.0 <= value <= 1.0:
            return value
        if 1.0 < value <= 100.0:
            return value / 100.0
    raise RuntimeUnavailableError("Reward model did not return a numeric score between 0 and 1.")


_TEXT_STOP_SEQUENCE_KEYS = (
    "melix.stop_sequences",
    "melix.turn_boundary.stop_sequences",
    "stop_sequences",
)
_STREAM_STOP_KWARG_NAMES = ("stop", "stop_words", "stop_sequences")
_SAMPLER_PENALTY_KWARG_NAMES = ("frequency_penalty", "presence_penalty")
_STOP_CONTRACT_CACHE_FIELD = "_melix.resolved_text_stop_contract_cache"
_STOP_KWARGS_CACHE_FIELD = "_melix.resolved_text_stop_kwargs_cache"
_NATIVE_MTP_ENABLED_EXT_KEY = "melix.native_mtp.enabled"
_NATIVE_MTP_TEXT_BATCH_PREFILL_STEP_SIZE_ENV = "MELIX_TEXT_NATIVE_MTP_PREFILL_STEP_SIZE"
_NATIVE_MTP_TEXT_BATCH_DEFAULT_PREFILL_STEP_SIZE = 2048
_NATIVE_MTP_TEXT_ACTIVE_FIELD = "_melix.native_mtp_text_active"
_NATIVE_MTP_TEXT_BATCH_GENERATOR_FIELD = "_melix.native_mtp_text_batch_generator"
_NATIVE_MTP_TEXT_BATCH_GENERATOR_CONFIG_FIELD = "_melix.native_mtp_text_batch_generator_config"
_NATIVE_MTP_TEXT_DETOKENIZER_FIELD = "_melix.native_mtp_text_detokenizer"


def _truthy_string(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _load_json_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _native_mtp_model_type(config_payload: dict[str, Any]) -> str:
    text_config = config_payload.get("text_config")
    if isinstance(text_config, dict):
        value = text_config.get("model_type") or config_payload.get("model_type")
    else:
        value = config_payload.get("model_type")
    return str(value or "").strip().lower()


def _native_mtp_layer_count(config_payload: dict[str, Any]) -> int:
    candidates: list[Any] = []
    text_config = config_payload.get("text_config")
    if isinstance(text_config, dict):
        candidates.append(text_config.get("mtp_num_hidden_layers"))
    candidates.append(config_payload.get("mtp_num_hidden_layers"))
    for value in candidates:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            continue
    return 0


def _native_mtp_weight_presence(model_dir: Path) -> tuple[bool, int]:
    index_payload = _load_json_payload(model_dir / "model.safetensors.index.json")
    weight_map = index_payload.get("weight_map")
    if not isinstance(weight_map, dict):
        return False, 0
    count = sum(
        1
        for key in weight_map
        if str(key).startswith("language_model.mtp.") or str(key).startswith("mtp.")
    )
    return count > 0, count


def maybe_apply_native_mtp_text_preload_patches(
    model_path: str,
    *,
    metadata: dict[str, str],
) -> dict[str, str]:
    enabled = _truthy_string(metadata.get(_NATIVE_MTP_ENABLED_EXT_KEY, ""))
    model_dir = Path(model_path)
    config_payload = _load_json_payload(model_dir / "config.json")
    model_type = _native_mtp_model_type(config_payload)
    mtp_layers = _native_mtp_layer_count(config_payload)
    compatible = model_type in {"qwen3_5", "qwen3_5_text"} and mtp_layers > 0
    weights_present, weight_count = _native_mtp_weight_presence(model_dir)

    active = False
    patch_applied = False
    reason = "disabled"
    try:
        from worker.runtime import native_mtp

        native_mtp.set_mtp_active(False)
        native_mtp.set_mtp_weight_attachment(False)
        if compatible:
            native_mtp.set_mtp_weight_attachment(weights_present)
            patch_applied = native_mtp.apply_native_mtp_patches()
            if not patch_applied:
                reason = "patch_failed"
            elif not enabled:
                reason = "disabled"
            elif not weights_present:
                reason = "missing_mtp_weights"
            else:
                active = True
                reason = ""
        elif enabled:
            reason = "unsupported_model"
        native_mtp.set_mtp_active(active)
    except Exception:
        reason = "patch_error"
        try:
            native_mtp.set_mtp_active(False)
            native_mtp.set_mtp_weight_attachment(False)
        except Exception:
            pass

    return {
        "melix.native_mtp.enabled": "true" if enabled else "false",
        "melix.native_mtp.compatible": "true" if compatible else "false",
        "melix.native_mtp.weights_present": "true" if weights_present else "false",
        "melix.native_mtp.weight_count": str(weight_count),
        "melix.native_mtp.patch_applied": "true" if patch_applied else "false",
        "melix.native_mtp.active": "true" if active else "false",
        "melix.native_mtp.reason": reason,
    }


def _load_mlx_batch_generator_class():
    from mlx_lm.generate import BatchGenerator

    return BatchGenerator


def _native_mtp_text_parts_active(metadata: Any, model: Any) -> bool:
    if not isinstance(metadata, dict) or not _truthy_string(metadata.get("melix.native_mtp.active")):
        return False
    inner = getattr(model, "language_model", model)
    if not hasattr(model, "mtp_forward") and not hasattr(inner, "mtp_forward"):
        return False
    return bool(hasattr(inner, "mtp") and getattr(inner, "mtp", None) is not None)


def _native_mtp_text_model_active(loaded_model: Any) -> bool:
    if not isinstance(loaded_model, dict):
        return False
    return _native_mtp_text_parts_active(loaded_model.get("metadata"), loaded_model.get("model"))


def _cached_native_mtp_text_model_active(loaded_model: Any) -> bool:
    if not isinstance(loaded_model, dict):
        return _native_mtp_text_model_active(loaded_model)
    active = loaded_model.get(_NATIVE_MTP_TEXT_ACTIVE_FIELD)
    if isinstance(active, bool):
        return active
    active = _native_mtp_text_model_active(loaded_model)
    loaded_model[_NATIVE_MTP_TEXT_ACTIVE_FIELD] = active
    return active


def _native_mtp_text_prefill_step_size() -> int:
    raw_value = os.environ.get(_NATIVE_MTP_TEXT_BATCH_PREFILL_STEP_SIZE_ENV, "").strip()
    if raw_value:
        try:
            value = int(raw_value)
        except ValueError:
            value = 0
        if value > 0:
            return value
    return _NATIVE_MTP_TEXT_BATCH_DEFAULT_PREFILL_STEP_SIZE


def _close_native_mtp_text_batch_generator(loaded_model: Any) -> None:
    if not isinstance(loaded_model, dict):
        return
    batch_generator = loaded_model.pop(_NATIVE_MTP_TEXT_BATCH_GENERATOR_FIELD, None)
    loaded_model.pop(_NATIVE_MTP_TEXT_BATCH_GENERATOR_CONFIG_FIELD, None)
    close = getattr(batch_generator, "close", None)
    if callable(close):
        close()


def _has_static_attribute(value: Any, name: str) -> bool:
    try:
        inspect.getattr_static(value, name)
    except AttributeError:
        return False
    return True


def _copyable_native_mtp_text_detokenizer(loaded_model: Any, tokenizer: Any) -> Any | None:
    if not isinstance(loaded_model, dict):
        return getattr(tokenizer, "detokenizer", None)

    template = loaded_model.get(_NATIVE_MTP_TEXT_DETOKENIZER_FIELD)
    if template is None:
        template = getattr(tokenizer, "detokenizer", None)
        if template is None:
            return None
        loaded_model[_NATIVE_MTP_TEXT_DETOKENIZER_FIELD] = template

    try:
        detokenizer = copy(template)
    except Exception:
        loaded_model.pop(_NATIVE_MTP_TEXT_DETOKENIZER_FIELD, None)
        return getattr(tokenizer, "detokenizer", None)
    if detokenizer is template:
        loaded_model.pop(_NATIVE_MTP_TEXT_DETOKENIZER_FIELD, None)
        return getattr(tokenizer, "detokenizer", None)
    return detokenizer


def _native_mtp_prefill_prompt_cache(
    model: Any,
    prompt_tokens: list[int],
    *,
    prefill_step_size: int,
    stream: Any,
    restore_cache: Any = None,
    restore_token_count: int = 0,
) -> tuple[list[Any], list[int], list[int]]:
    try:
        import mlx.core as mx
        from mlx_lm.models.cache import make_prompt_cache
    except ModuleNotFoundError as exc:  # pragma: no cover - guarded by native MTP availability.
        raise RuntimeUnavailableError("mlx-lm prompt cache support is not installed") from exc

    if restore_cache is not None:
        prompt_cache = restore_cache
        suffix_tokens = list(prompt_tokens[restore_token_count:])
        if len(suffix_tokens) <= 1:
            last_token = suffix_tokens if suffix_tokens else [int(prompt_tokens[-1])]
            return prompt_cache, last_token, list(prompt_tokens[:restore_token_count])
        prefill_tokens = suffix_tokens[:-1]
        last_token = [int(suffix_tokens[-1])]
        step_size = max(1, int(prefill_step_size or 1))

        def run_suffix_prefill() -> None:
            input_arr = mx.array(prefill_tokens)[None]
            while input_arr.shape[1] > 0:
                n_to_process = min(step_size, input_arr.shape[1])
                model(input_arr[:, :n_to_process], cache=prompt_cache)
                # Eval via .state (older) or .keys/.values (newer KVCache)
                eval_targets = []
                for c in prompt_cache:
                    s = getattr(c, "state", None)
                    if s is not None:
                        eval_targets.append(s)
                    else:  # pragma: no cover - newer KVCache interface
                        for attr in ("keys", "values"):
                            v = getattr(c, attr, None)
                            if v is not None:
                                eval_targets.append(v)
                if eval_targets:
                    mx.eval(eval_targets)
                input_arr = input_arr[:, n_to_process:]

        if stream is None:
            run_suffix_prefill()
        else:  # pragma: no cover - mirrors the non-restore stream path
            with mx.stream(stream):
                run_suffix_prefill()
        return prompt_cache, last_token, list(prompt_tokens[:restore_token_count]) + prefill_tokens

    prompt_cache = make_prompt_cache(model)
    if len(prompt_tokens) <= 1:
        return prompt_cache, list(prompt_tokens), []

    prefill_tokens = list(prompt_tokens[:-1])
    last_token = [int(prompt_tokens[-1])]
    step_size = max(1, int(prefill_step_size or 1))

    def run_prefill() -> None:
        input_arr = mx.array(prefill_tokens)[None]
        while input_arr.shape[1] > 0:
            n_to_process = min(step_size, input_arr.shape[1])
            model(input_arr[:, :n_to_process], cache=prompt_cache)
            mx.eval([cache.state for cache in prompt_cache])
            mx.clear_cache()
            input_arr = input_arr[:, n_to_process:]

    if stream is None:
        run_prefill()
    else:
        with mx.stream(stream):
            run_prefill()

    return prompt_cache, last_token, prefill_tokens


def _trim_restored_cache(prompt_cache: Any, trim_tokens: int) -> bool:
    """Trim `trim_tokens` from the end of a restored prompt cache.

    A restored snapshot holds KV state for the full stored prompt. On a partial
    LCP hit only `recovered_prefix_tokens` of that state is valid, so the stale
    tail must be trimmed before the new suffix is replayed. Returns True only
    when exactly `trim_tokens` were trimmed across the cache; any shortfall
    (e.g. a rotating cache that cannot trim that far) returns False so the caller
    can fall back to a cold prefill rather than reuse misaligned state.
    """
    if trim_tokens <= 0:
        return True
    try:
        from mlx_lm.models.cache import trim_prompt_cache
    except (ModuleNotFoundError, ImportError):  # pragma: no cover - guarded by mlx-lm availability
        return False
    try:
        trimmed = trim_prompt_cache(prompt_cache, trim_tokens)
    except Exception:
        return False
    try:
        return int(trimmed) == trim_tokens
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return False


def _estimate_cache_bytes(prompt_cache: Any) -> int:
    if not isinstance(prompt_cache, list):
        return 0
    total = 0
    for layer_cache in prompt_cache:
        # Support both .state (older mlx-lm) and .keys/.values (newer KVCache)
        tensors: list[Any] = []
        state = getattr(layer_cache, "state", None)
        if state is not None:
            if isinstance(state, list | tuple):
                tensors.extend(state)
            else:
                tensors.append(state)
        else:  # pragma: no cover - newer KVCache interface
            keys = getattr(layer_cache, "keys", None)
            values = getattr(layer_cache, "values", None)
            if keys is not None:
                tensors.append(keys)
            if values is not None:
                tensors.append(values)
        for tensor in tensors:
            nbytes = getattr(tensor, "nbytes", None)
            if nbytes is None:
                size = getattr(tensor, "size", None)
                itemsize = getattr(tensor, "itemsize", None)
                if size is not None and itemsize is not None:
                    nbytes = int(size) * int(itemsize)
            if nbytes is not None:
                total += int(nbytes)
    return total


def _tokenizer_eos_stop_tokens(tokenizer: Any) -> list[list[int]] | None:
    eos_token_ids = getattr(tokenizer, "eos_token_ids", None)
    if eos_token_ids is None:
        eos_token_ids = getattr(tokenizer, "eos_token_id", None)
    if eos_token_ids is None:
        return None
    if isinstance(eos_token_ids, list | tuple | set):
        values = eos_token_ids
    else:
        values = (eos_token_ids,)
    stop_tokens: list[list[int]] = []
    for value in values:
        try:
            token_id = int(value)
        except (TypeError, ValueError):
            continue
        stop_tokens.append([token_id])
    return stop_tokens or None


def _mlx_peak_memory_gb(mx: Any) -> float | None:
    try:
        if hasattr(mx, "get_peak_memory"):
            return float(mx.get_peak_memory() / 1e9)
        metal = getattr(mx, "metal", None)
        if metal is not None and hasattr(metal, "get_peak_memory"):
            return float(metal.get_peak_memory() / 1e9)
    except Exception:
        return None
    return None


def _split_stop_sequence_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, list):
                return [str(item).strip() for item in payload if str(item).strip()]
        return [part.strip() for part in stripped.split(",") if part.strip()]
    if isinstance(value, list | tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _loaded_model_metadata(loaded_model: Any) -> list[dict[str, Any]]:
    if not isinstance(loaded_model, dict):
        return []
    metadata: list[dict[str, Any]] = []
    for key in ("metadata", "model_ext", "ext"):
        value = loaded_model.get(key)
        if isinstance(value, dict):
            metadata.append(value)
    metadata.append(loaded_model)
    return metadata


def _tokenizer_eos_token_ids(tokenizer: Any) -> tuple[str, ...]:
    eos_token_id = getattr(tokenizer, "eos_token_id", None)
    if eos_token_id is None:
        return ()
    if isinstance(eos_token_id, list | tuple | set):
        return tuple(str(item) for item in eos_token_id if str(item).strip())
    return (str(eos_token_id),) if str(eos_token_id).strip() else ()


def _tokenizer_eos_cache_key(tokenizer: Any) -> tuple[str, object]:
    eos_token = str(getattr(tokenizer, "eos_token", "") or "").strip() if tokenizer is not None else ""
    eos_token_id = getattr(tokenizer, "eos_token_id", None)
    if isinstance(eos_token_id, set):
        eos_id_key: object = tuple(sorted(str(item) for item in eos_token_id if str(item).strip()))
    elif isinstance(eos_token_id, list | tuple):
        eos_id_key = tuple(str(item) for item in eos_token_id if str(item).strip())
    elif eos_token_id is None:
        eos_id_key = ""
    else:
        eos_id_key = str(eos_token_id).strip()
    return eos_token, eos_id_key


def _stop_contract_cache_key(
    loaded_model: Any,
    sampling: Any,
    execution_ext: dict[str, str] | None,
) -> tuple[object, ...] | None:
    if execution_ext is not None or not isinstance(loaded_model, dict):
        return None

    request_stop = tuple(str(item) for item in getattr(sampling, "stop", ()))
    metadata_values: list[tuple[str, str, str]] = []
    for source_key in ("model_ext", "metadata", "ext"):
        metadata = loaded_model.get(source_key)
        if isinstance(metadata, dict):
            metadata_values.extend(
                (source_key, key, str(metadata.get(key, "") or ""))
                for key in _TEXT_STOP_SEQUENCE_KEYS
            )
    metadata_values.extend(
        ("loaded_model", key, str(loaded_model.get(key, "") or ""))
        for key in _TEXT_STOP_SEQUENCE_KEYS
    )
    return (
        request_stop,
        tuple(metadata_values),
        _tokenizer_eos_cache_key(loaded_model.get("tokenizer")),
    )


def _cached_resolve_text_stop_contract(
    loaded_model: Any,
    sampling: Any,
    execution_ext: dict[str, str] | None,
) -> ResolvedTextStopContract:
    cache_key = _stop_contract_cache_key(loaded_model, sampling, execution_ext)
    if cache_key is None:
        return resolve_text_stop_contract(loaded_model, sampling, execution_ext)

    cache = loaded_model.get(_STOP_CONTRACT_CACHE_FIELD)
    if not isinstance(cache, dict):
        cache = {}
        loaded_model[_STOP_CONTRACT_CACHE_FIELD] = cache
    contract = cache.get(cache_key)
    if contract is None:
        contract = resolve_text_stop_contract(loaded_model, sampling, execution_ext)
        cache[cache_key] = contract
    return contract


def _cached_stream_stop_kwargs(
    loaded_model: Any,
    sampling: Any,
    execution_ext: dict[str, str] | None,
    stream_stop_kwarg: str,
) -> dict[str, Any]:
    if not stream_stop_kwarg:
        return {}
    cache_key = _stop_contract_cache_key(loaded_model, sampling, execution_ext)
    if cache_key is None or not isinstance(loaded_model, dict):
        contract = resolve_text_stop_contract(loaded_model, sampling, execution_ext)
        return {stream_stop_kwarg: list(contract.sequences)} if contract.sequences else {}

    cache = loaded_model.get(_STOP_KWARGS_CACHE_FIELD)
    if not isinstance(cache, dict):
        cache = {}
        loaded_model[_STOP_KWARGS_CACHE_FIELD] = cache
    kwargs = cache.get((stream_stop_kwarg, cache_key))
    if kwargs is None:
        contract = _cached_resolve_text_stop_contract(loaded_model, sampling, execution_ext)
        kwargs = {stream_stop_kwarg: list(contract.sequences)} if contract.sequences else {}
        cache[(stream_stop_kwarg, cache_key)] = kwargs
    return kwargs


def _int_tuple(value: Any) -> tuple[int, ...]:
    if value is None:
        return ()
    if isinstance(value, list | tuple | set):
        result: list[int] = []
        for item in value:
            try:
                result.append(int(item))
            except (TypeError, ValueError):
                continue
        return tuple(result)
    try:
        return (int(value),)
    except (TypeError, ValueError):
        return ()


def _float_tuple(value: Any) -> tuple[float, ...]:
    if value is None:
        return ()
    if isinstance(value, list | tuple | set):
        result: list[float] = []
        for item in value:
            try:
                result.append(float(item))
            except (TypeError, ValueError):
                continue
        return tuple(result)
    try:
        return (float(value),)
    except (TypeError, ValueError):
        return ()


def _bytes_value(value: Any) -> bytes | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value or None
    if isinstance(value, bytearray):
        return bytes(value) or None
    return None


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _normalize_chat_template_messages(
    chat_messages: list[dict[str, str]],
) -> tuple[list[dict[str, str]], int]:
    instruction_parts: list[str] = []
    normalized_messages: list[dict[str, str]] = []
    saw_non_instruction = False
    non_leading_instruction_count = 0

    for message in chat_messages:
        role = str(message.get("role", "")).strip().lower()
        content = str(message.get("content", "") or "").strip()
        if role in {"system", "developer"}:
            if saw_non_instruction:
                non_leading_instruction_count += 1
            if content:
                instruction_parts.append(content)
            continue
        saw_non_instruction = True
        normalized_messages.append(message)

    if instruction_parts:
        normalized_messages.insert(
            0,
            {
                "role": "system",
                "content": "\n\n".join(instruction_parts),
            },
        )
    return normalized_messages, non_leading_instruction_count


def _native_template_tools(execution_ext: dict[str, str] | None) -> list[dict[str, Any]]:
    if execution_ext is None:
        return []
    raw_value = str(execution_ext.get("melix.tool_config.tools_json", "") or "").strip()
    if not raw_value:
        return []
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]



def resolve_text_stop_contract(
    loaded_model: Any,
    sampling: Any,
    execution_ext: dict[str, str] | None = None,
) -> ResolvedTextStopContract:
    ordered_sequences: list[str] = []
    seen_sequences: set[str] = set()
    sources: list[str] = []

    def add_sequences(values: Iterable[str], source: str) -> None:
        added = False
        for value in values:
            sequence = str(value).strip()
            if not sequence or sequence in seen_sequences:
                continue
            seen_sequences.add(sequence)
            ordered_sequences.append(sequence)
            added = True
        if added and source not in sources:
            sources.append(source)

    add_sequences((str(item) for item in getattr(sampling, "stop", [])), "request")

    metadata_sources = _loaded_model_metadata(loaded_model)
    if execution_ext:
        metadata_sources.append(dict(execution_ext))
    for metadata in metadata_sources:
        for key in _TEXT_STOP_SEQUENCE_KEYS:
            add_sequences(_split_stop_sequence_value(metadata.get(key)), "model_metadata")

    tokenizer = loaded_model.get("tokenizer") if isinstance(loaded_model, dict) else None
    eos_token_ids = _tokenizer_eos_token_ids(tokenizer)
    eos_token = str(getattr(tokenizer, "eos_token", "") or "").strip() if tokenizer is not None else ""
    if eos_token:
        add_sequences((eos_token,), "tokenizer_eos")
    elif eos_token_ids and "tokenizer_eos" not in sources:
        sources.append("tokenizer_eos")

    return ResolvedTextStopContract(
        sequences=tuple(ordered_sequences),
        resolved_stop_token_count=len(ordered_sequences) + len(eos_token_ids),
        source="+".join(sources) if sources else "none",
    )


# String constants for the ext-field activation_mode signal. Kept as the
# backward-compatible surface — existing manifests, CLI ext overrides, and
# external callers can keep passing these strings. The new authoritative
# signal is the typed ``worker.v1.RuntimeMode`` enum on ``ModelSpec``; this
# module reads the enum first and falls back to the ext string only when the
# enum is unspecified.
ACTIVATION_MODE_ADAPTER_BACKED = "adapter_backed_runtime"
ACTIVATION_MODE_FUSED_DERIVED = "fused_derived_model"


def _runtime_mode_adapter_backed_value() -> int:
    """Return ``worker.v1.RuntimeMode.RUNTIME_MODE_ADAPTER_BACKED`` at call time.

    Lazy import avoids paying a proto dependency at runtime-module load for
    the non-LoRA inference path, and — crucially — avoids the drift hazard
    of hardcoding the enum integer: if the proto ever renumbers the enum,
    this function stays correct without test scaffolding.
    """
    from packages.protocol.python.worker.v1 import common_pb2

    return int(common_pb2.RUNTIME_MODE_ADAPTER_BACKED)


def _runtime_mode_fused_value() -> int:
    from packages.protocol.python.worker.v1 import common_pb2

    return int(common_pb2.RUNTIME_MODE_FUSED_DERIVED_MODEL)


@dataclass(frozen=True)
class AdapterBackedLoadContract:
    """Typed adapter-backed load spec resolved from a ModelSpec.

    All fields are required. Callers that need adapter-backed inference get a
    fully-validated contract or a ``RuntimeError`` describing the missing
    piece. This is the replacement for the prior dict-of-strings return from
    ``_resolve_adapter_backed_metadata``.
    """

    adapter_manifest_path: str
    adapter_weights_path: str
    adapter_dir: str
    adapter_set_hash: str
    derived_from_model_id: str

    def to_runtime_metadata(self) -> dict[str, str]:
        """Return the legacy flat dict shape consumed by ``load_model`` callers."""
        return {
            "activation_mode": ACTIVATION_MODE_ADAPTER_BACKED,
            "adapter_manifest_path": self.adapter_manifest_path,
            "adapter_weights_path": self.adapter_weights_path,
            "adapter_dir": self.adapter_dir,
            "derived_from_model_id": self.derived_from_model_id,
            "adapter_set_hash": self.adapter_set_hash,
        }


def _is_adapter_backed_spec(model_spec) -> bool:
    """Return True iff the ModelSpec declares adapter-backed runtime.

    Prefers the typed ``runtime_mode`` enum when set. Falls back to the
    legacy ``ext["melix.activation_mode"]`` string only when the enum is
    ``RUNTIME_MODE_UNSPECIFIED`` — that is, on pre-enum payloads.
    """
    runtime_mode = int(getattr(model_spec, "runtime_mode", 0) or 0)
    if runtime_mode == _runtime_mode_adapter_backed_value():
        return True
    if runtime_mode == _runtime_mode_fused_value():
        return False
    # Enum unspecified — fall back to the ext string.
    return _normalized_ext_value(model_spec, "melix.activation_mode") == ACTIVATION_MODE_ADAPTER_BACKED


def _resolve_adapter_backed_contract(model_spec) -> AdapterBackedLoadContract | None:
    """Build a validated ``AdapterBackedLoadContract`` from the ModelSpec.

    Returns ``None`` when the spec is NOT adapter-backed (fused or base
    models). Raises ``RuntimeError`` when the spec declares adapter-backed
    mode but is missing required metadata — the error is treated as a hard
    contract violation rather than a silent fallback to base-only load.
    """
    if not _is_adapter_backed_spec(model_spec):
        return None

    adapter_manifest_path = _normalized_ext_value(model_spec, "melix.adapter_manifest_path")
    if not adapter_manifest_path:
        raise RuntimeError(
            "Adapter-backed runtime model is missing adapter_manifest_path metadata."
        )

    adapter_weights_path = _normalized_ext_value(model_spec, "melix.adapter_weights_path")
    if not adapter_weights_path:
        manifest_path = Path(adapter_manifest_path).expanduser()
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        if isinstance(payload, dict):
            adapter_weights_path = str(payload.get("weights_path", "") or "").strip()

    if not adapter_weights_path:
        raise RuntimeError(
            "Adapter-backed runtime model is missing adapter_weights_path metadata."
        )

    adapter_dir = Path(adapter_weights_path).expanduser().resolve().parent
    return AdapterBackedLoadContract(
        adapter_manifest_path=adapter_manifest_path,
        adapter_weights_path=adapter_weights_path,
        adapter_dir=str(adapter_dir),
        adapter_set_hash=_normalized_ext_value(model_spec, "melix.adapter_set_hash"),
        derived_from_model_id=_normalized_ext_value(model_spec, "melix.derived_from_model_id"),
    )


def _resolve_adapter_backed_metadata(model_spec) -> dict[str, str]:
    """Legacy flat-dict surface kept for backward compatibility.

    New callers should prefer ``_resolve_adapter_backed_contract`` to get
    typed fields; this wrapper returns ``{}`` for non-adapter-backed specs
    and the legacy dict shape otherwise.
    """
    contract = _resolve_adapter_backed_contract(model_spec)
    if contract is None:
        return {}
    return contract.to_runtime_metadata()


def _is_mlx_lm_unmatched_weight_error(exc: ValueError) -> bool:
    return "parameters not in model" in str(exc).lower()


def _load_adapter_backed_model_without_strict(
    *,
    model_spec: Any,
    adapter_metadata: dict[str, str],
    trust_remote_code: bool,
) -> tuple[Any, Any]:
    try:
        from mlx_lm.utils import _download, load_adapters, load_model, load_tokenizer
    except ModuleNotFoundError:
        raise

    download_kwargs: dict[str, Any] = {"revision": model_spec.revision or None}
    if trust_remote_code and _callable_accepts_kwarg(_download, "trust_remote_code"):
        download_kwargs["trust_remote_code"] = True
    model_path = _download(str(model_spec.model_path), **download_kwargs)
    load_kwargs: dict[str, Any] = {
        "lazy": False,
        "strict": False,
    }
    if trust_remote_code and _callable_accepts_kwarg(load_model, "trust_remote_code"):
        load_kwargs["trust_remote_code"] = True
    model, config = load_model(model_path, **load_kwargs)
    model = load_adapters(model, adapter_metadata["adapter_dir"])
    model.eval()
    tokenizer = load_tokenizer(
        model_path,
        None,
        eos_token_ids=config.get("eos_token_id", None) if isinstance(config, dict) else None,
    )
    return model, tokenizer


def _declared_kwargs(callable_obj: Any, names: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(name for name in names if _callable_accepts_kwarg(callable_obj, name))


class AutoMLXBackend:
    runtime_name = "mlx-unavailable"

    def __init__(
        self,
        *,
        load_fn=None,
        stream_generate_fn=None,
        sampler_factory=None,
    ) -> None:
        self._stream_stop_kwarg = ""
        self._sampler_penalty_kwargs: tuple[str, ...] = ()
        if load_fn is not None and stream_generate_fn is not None and sampler_factory is not None:
            self._available = True
            self._error = None
            self._load_fn = load_fn
            self._stream_generate_fn = stream_generate_fn
            self._sampler_factory = sampler_factory
            self._stream_stop_kwarg = _first_declared_kwarg(stream_generate_fn, _STREAM_STOP_KWARG_NAMES)
            self._sampler_penalty_kwargs = _declared_kwargs(sampler_factory, _SAMPLER_PENALTY_KWARG_NAMES)
            self.runtime_name = "mlx-lm"
            return

        self._load_fn = None
        self._stream_generate_fn = None
        self._sampler_factory = None
        self._available = importlib.util.find_spec("mlx_lm") is not None
        self._error = None if self._available else ModuleNotFoundError("mlx_lm is not installed")
        if self._available:
            self.runtime_name = "mlx-lm"

    def _ensure_runtime(self) -> None:
        if self._load_fn is not None and self._stream_generate_fn is not None and self._sampler_factory is not None:
            return
        try:
            import mlx_lm
            from mlx_lm import load, stream_generate
            from mlx_lm.sample_utils import make_sampler
        except ModuleNotFoundError as exc:
            self._available = False
            self._error = exc
            self.runtime_name = "mlx-unavailable"
            raise RuntimeUnavailableError("mlx-lm is not installed") from exc
        else:
            self._available = True
            self._error = None
            self.runtime_name = "mlx-lm"
            self._load_fn = load
            self._stream_generate_fn = stream_generate
            self._sampler_factory = make_sampler
            self._stream_stop_kwarg = _first_declared_kwarg(stream_generate, _STREAM_STOP_KWARG_NAMES)
            self._sampler_penalty_kwargs = _declared_kwargs(make_sampler, _SAMPLER_PENALTY_KWARG_NAMES)

    def load_model(self, model_spec, *, trust_remote_code: bool = False) -> dict[str, Any]:
        if not self._available:
            raise RuntimeUnavailableError("mlx-lm is not installed") from self._error
        self._ensure_runtime()
        adapter_metadata = _resolve_adapter_backed_metadata(model_spec)
        metadata = dict(model_spec.ext)
        native_mtp_metadata = maybe_apply_native_mtp_text_preload_patches(
            model_spec.model_path,
            metadata=metadata,
        )
        metadata.update(native_mtp_metadata)
        load_kwargs: dict[str, Any] = {"lazy": False}
        if trust_remote_code and not _callable_accepts_kwarg(self._load_fn, "trust_remote_code"):
            raise RuntimeError("mlx-lm loader cannot honor trust_remote_code.")
        if trust_remote_code:
            load_kwargs["trust_remote_code"] = True
        if adapter_metadata:
            load_kwargs["adapter_path"] = adapter_metadata["adapter_dir"]
        try:
            loaded = self._load_fn(model_spec.model_path, **load_kwargs)
        except ValueError as exc:
            if not adapter_metadata or not _is_mlx_lm_unmatched_weight_error(exc):
                raise
            model, tokenizer = _load_adapter_backed_model_without_strict(
                model_spec=model_spec,
                adapter_metadata=adapter_metadata,
                trust_remote_code=trust_remote_code,
            )
            loaded = (model, tokenizer)
        model, tokenizer = loaded[:2]
        family_config = resolve_text_family_config(
            dict(metadata),
            model_path=model_spec.model_path,
            default_route_kind=metadata.get("melix.capability.route_kind", "swift_text") or "swift_text",
        )
        native_mtp_active = _truthy_string(metadata.get("melix.native_mtp.active"))
        for target in (model, getattr(model, "language_model", None)):
            if target is None:
                continue
            try:
                setattr(target, "_melix_native_mtp_active", native_mtp_active)
            except Exception:
                pass
        loaded_model = {
            "model_id": model_spec.model_id,
            "model_path": model_spec.model_path,
            "model_ext": dict(metadata),
            "metadata": dict(metadata),
            "model": model,
            "tokenizer": tokenizer,
            "mlx_version": _installed_package_version("mlx"),
            "mlx_lm_version": _installed_package_version("mlx-lm"),
            **adapter_metadata,
            **family_config.runtime_metadata(),
        }
        loaded_model[_NATIVE_MTP_TEXT_ACTIVE_FIELD] = _native_mtp_text_parts_active(
            loaded_model["metadata"],
            model,
        )
        return loaded_model

    def estimate_resident_bytes(self, model_spec) -> int:
        return _estimate_model_weight_resident_bytes(str(getattr(model_spec, "model_path", "") or ""))

    def close_loaded_model(self, loaded_model: Any) -> None:
        _close_native_mtp_text_batch_generator(loaded_model)

    def score_response(
        self,
        loaded_model,
        prompt: str,
        response: str,
        execution_ext: dict[str, str] | None = None,
    ) -> float:
        if not self._available:
            raise RuntimeUnavailableError("mlx-lm is not installed") from self._error
        self._ensure_runtime()
        sampler = self._sampler_factory(temp=0.0, top_p=1.0, top_k=1)
        score_prompt = _reward_score_prompt(
            loaded_model,
            prompt=prompt,
            response=response,
            execution_ext=execution_ext,
        )
        score_text = "".join(
            str(getattr(chunk, "text", ""))
            for chunk in self._stream_generate_fn(
                loaded_model["model"],
                loaded_model["tokenizer"],
                score_prompt,
                max_tokens=_reward_score_max_tokens(loaded_model, execution_ext),
                sampler=sampler,
            )
        )
        return _parse_reward_score_text(score_text)

    def generate_tokens(
        self,
        loaded_model,
        prompt: str,
        sampling,
        cancel_event,
        execution_ext: dict[str, str] | None = None,
    ) -> Iterable[str]:
        if not self._available:
            raise RuntimeUnavailableError("mlx-lm is not installed") from self._error
        self._ensure_runtime()
        sampler_kwargs: dict[str, Any] = {
            "temp": float(sampling.temperature),
            "top_p": float(sampling.top_p),
            "top_k": int(sampling.top_k),
        }
        for penalty_name in self._sampler_penalty_kwargs:
            sampler_kwargs[penalty_name] = float(getattr(sampling, penalty_name, 0.0))
        sampler = self._sampler_factory(**sampler_kwargs)
        max_tokens = int(sampling.max_output_tokens) if int(sampling.max_output_tokens) > 0 else 256
        stream_kwargs = _cached_stream_stop_kwargs(
            loaded_model,
            sampling,
            execution_ext,
            self._stream_stop_kwarg,
        )

        if loaded_model.get(_NATIVE_MTP_TEXT_ACTIVE_FIELD) is True:
            yield from self._generate_native_mtp_batch_tokens(
                loaded_model,
                prompt,
                sampler=sampler,
                max_tokens=max_tokens,
                cancel_event=cancel_event,
                execution_ext=execution_ext,
            )
            return

        cumulative_raw_text = ""
        for response in self._stream_generate_fn(
            loaded_model["model"],
            loaded_model["tokenizer"],
            prompt,
            max_tokens=max_tokens,
            sampler=sampler,
            **stream_kwargs,
        ):
            if cancel_event.is_set():
                return
            text = getattr(response, "text", "")
            finish_reason = getattr(response, "finish_reason", None)
            if not text and finish_reason is None:
                continue
            response_raw_text = getattr(response, "raw_text", None)
            if response_raw_text is None:
                cumulative_raw_text += str(text or "")
                raw_text = cumulative_raw_text
            else:
                raw_text = response_raw_text
            yield RuntimeTokenEvent(
                text=text,
                raw_text=raw_text,
                token_ids=_int_tuple(
                    _first_present(
                        getattr(response, "token_ids", None),
                        getattr(response, "tokens", None),
                        getattr(response, "token", None),
                        getattr(response, "token_id", None),
                    )
                ),
                token_logprobs=_float_tuple(
                    _first_present(
                        getattr(response, "token_logprobs", None),
                        getattr(response, "logprobs", None),
                        getattr(response, "logprob", None),
                    )
                ),
                token_bytes=_bytes_value(
                    _first_present(
                        getattr(response, "token_bytes", None),
                        getattr(response, "byte_fallback_bytes", None),
                    )
                ),
                parser_observation=str(getattr(response, "parser_observation", "") or ""),
                prompt_tokens=getattr(response, "prompt_tokens", None),
                completion_tokens=getattr(response, "generation_tokens", None),
                prompt_tps=getattr(response, "prompt_tps", None),
                generation_tps=getattr(response, "generation_tps", None),
                peak_memory=getattr(response, "peak_memory", None),
                finish_reason=finish_reason,
                speculative_acceptance_rate=getattr(response, "speculative_acceptance_rate", None),
                speculative_rollback_rate=getattr(response, "speculative_rollback_rate", None),
                speculative_accepted_tokens=getattr(response, "speculative_accepted_tokens", None),
                speculative_rejected_tokens=getattr(response, "speculative_rejected_tokens", None),
                speculative_fallback_count=getattr(response, "speculative_fallback_count", None),
                speculative_num_draft_tokens=getattr(response, "speculative_num_draft_tokens", None),
                speculative_draft_model_configured=getattr(
                    response,
                    "speculative_draft_model_configured",
                    None,
                ),
                speculative_draft_propose_ms=getattr(response, "speculative_draft_propose_ms", None),
                speculative_target_verify_ms=getattr(response, "speculative_target_verify_ms", None),
                dflash_enabled=getattr(response, "dflash_enabled", None),
                dflash_block_size=getattr(response, "dflash_block_size", None),
                dflash_rollback_count=getattr(response, "dflash_rollback_count", None),
                dflash_target_hidden_layers=getattr(response, "dflash_target_hidden_layers", None),
            )

    def _generate_native_mtp_batch_tokens(
        self,
        loaded_model,
        prompt: str,
        *,
        sampler,
        max_tokens: int,
        cancel_event,
        execution_ext: dict[str, str] | None = None,
    ) -> Iterable[RuntimeTokenEvent]:
        try:
            import mlx.core as mx
        except ModuleNotFoundError as exc:  # pragma: no cover - guarded by mlx-lm availability.
            raise RuntimeUnavailableError("mlx is not installed") from exc

        prepare_started_at = time.perf_counter()
        tokenizer = loaded_model["tokenizer"]
        if not hasattr(tokenizer, "encode"):
            raise RuntimeUnavailableError("Native MTP text path requires a tokenizer with encode().")
        try:
            from mlx_lm.tokenizer_utils import TokenizerWrapper
        except ModuleNotFoundError:
            TokenizerWrapper = ()  # type: ignore[assignment]

        if (
            TokenizerWrapper
            and not isinstance(tokenizer, TokenizerWrapper)
            and not _has_static_attribute(tokenizer, "detokenizer")
        ):
            tokenizer = TokenizerWrapper(tokenizer)
            loaded_model["tokenizer"] = tokenizer

        add_special_tokens = getattr(tokenizer, "bos_token", None) is None or not prompt.startswith(
            str(getattr(tokenizer, "bos_token", "") or "")
        )
        encode_started_at = time.perf_counter()
        prompt_tokens = list(tokenizer.encode(prompt, add_special_tokens=add_special_tokens))
        prompt_encode_ms = (time.perf_counter() - encode_started_at) * 1000.0
        if not prompt_tokens:
            return

        detokenizer = _copyable_native_mtp_text_detokenizer(loaded_model, tokenizer)
        if detokenizer is None:
            raise RuntimeUnavailableError("Native MTP text path requires a streaming detokenizer.")
        reset = getattr(detokenizer, "reset", None)
        if callable(reset):
            reset()

        _ext = execution_ext or {}
        _session_id = str(_ext.get("_melix.session_id", "") or "")
        _model_id = str(_ext.get("_melix.model_id", "") or "")
        _model_revision = str(_ext.get("_melix.model_revision", "") or "")
        try:
            _block_size = max(1, int(_ext.get("_melix.block_size", "64") or "64"))
        except (ValueError, TypeError):
            _block_size = 64
        _acceleration_mode = str(_ext.get("_melix.acceleration_mode", "") or "")
        # Cache mode flows from the request; unspecified ("", "0") stores as a
        # standard tiered cache. A rotating value is preserved so find_lcp's
        # rotating-exclusion gate can reject the stored entry on the next turn.
        _cache_mode = str(_ext.get("_melix.cache_mode", "") or "")
        if not _cache_mode or _cache_mode in ("0", "CACHE_MODE_UNSPECIFIED"):
            _cache_mode = "CACHE_MODE_TIERED"
        _force_fallback = _ext.get("_test.force_cache_fallback", "").lower() in ("1", "true", "yes")
        _prefix_store = _get_prefix_store()

        _lcp: _LCPResult | None = None
        if _session_id:
            _lcp = _prefix_store.find_lcp(
                prompt_tokens,
                _model_id,
                _model_revision,
                _block_size,
                acceleration_mode=_acceleration_mode,
                force_fallback=_force_fallback,
            )

        # find_lcp may have acquired an active ref on the matched entry; track it
        # before any code that can raise so the finally block always releases it.
        _lcp_entry_to_release = _lcp.entry if _lcp is not None else None
        batch_generator: Any = None
        uid: int | None = None
        generation_started_at = time.perf_counter()
        first_response_ms: float | None = None
        first_visible_ms: float | None = None
        prompt_tps: float | None = None
        cumulative_raw_text = ""
        try:
            batch_generator = self._native_mtp_batch_generator(
                loaded_model,
                sampler=sampler,
                max_tokens=max_tokens,
                stop_tokens=_tokenizer_eos_stop_tokens(tokenizer),
                prefill_step_size=_native_mtp_text_prefill_step_size(),
            )
            prepare_ms = (time.perf_counter() - prepare_started_at) * 1000.0
            insert_started_at = time.perf_counter()
            prefill_started_at = time.perf_counter()

            _use_lcp = (
                _lcp is not None
                and _lcp.mode != "none"
                and _lcp.entry is not None
                and _lcp.entry.cache_snapshot is not None
            )
            _restored = None
            if _use_lcp:
                assert _lcp is not None and _lcp.entry is not None
                _restored = _clone_cache_snapshot(_lcp.entry.cache_snapshot)
                # The snapshot holds KV state for the full stored prompt; on a
                # partial hit, trim the tail beyond the validated common prefix
                # so the suffix replays onto correctly aligned state.
                _trim_tokens = len(_lcp.entry.token_ids) - _lcp.recovered_prefix_tokens
                _trim_ok = True
                if _restored is not None and _trim_tokens > 0:
                    _trim_ok = _trim_restored_cache(_restored, _trim_tokens)
                if _restored is None or not _trim_ok:
                    _use_lcp = False
                    _restored = None
                    # Clear the tracker before releasing so the finally block can
                    # never double-release even if release() raises here.
                    _entry = _lcp_entry_to_release
                    _lcp_entry_to_release = None
                    if _entry is not None:
                        _prefix_store.release(_entry)

            if _use_lcp:
                assert _lcp is not None and _lcp.entry is not None
                suffix_tokens = _lcp.suffix_token_ids
                if suffix_tokens:
                    prompt_cache, last_token, cached_tokens = _native_mtp_prefill_prompt_cache(
                        loaded_model["model"],
                        list(prompt_tokens),
                        prefill_step_size=_native_mtp_text_prefill_step_size(),
                        stream=getattr(batch_generator, "stream", None),
                        restore_cache=_restored,
                        restore_token_count=_lcp.recovered_prefix_tokens,
                    )
                else:
                    prompt_cache = _restored
                    last_token = [int(prompt_tokens[-1])] if prompt_tokens else []
                    cached_tokens = list(prompt_tokens[:-1]) if len(prompt_tokens) > 1 else []
            else:
                prompt_cache, last_token, cached_tokens = _native_mtp_prefill_prompt_cache(
                    loaded_model["model"],
                    prompt_tokens,
                    prefill_step_size=_native_mtp_text_prefill_step_size(),
                    stream=getattr(batch_generator, "stream", None),
                )

            prefill_ms = (time.perf_counter() - prefill_started_at) * 1000.0

            if _session_id:
                # Always update store with the full prompt_tokens so multi-turn
                # conversations accumulate context even after an LCP warm hit.
                _snapshot = _clone_cache_snapshot(prompt_cache)
                if _snapshot is not None:
                    _prefix_store.put(
                        session_id=_session_id,
                        token_ids=list(prompt_tokens),
                        cache_snapshot=_snapshot,
                        cache_mode=_cache_mode,
                        model_id=_model_id,
                        model_revision=_model_revision,
                        block_size=_block_size,
                        total_bytes=_estimate_cache_bytes(prompt_cache),
                        acceleration_mode=_acceleration_mode,
                    )

            batch_insert_started_at = time.perf_counter()
            inserted = batch_generator.insert(
                [last_token],
                max_tokens=[max_tokens],
                caches=[prompt_cache],
                all_tokens=[cached_tokens],
                samplers=[sampler],
            )
            batch_insert_ms = (time.perf_counter() - batch_insert_started_at) * 1000.0
            insert_ms = (time.perf_counter() - insert_started_at) * 1000.0
            uid = int(inserted[0])
            while not cancel_event.is_set():
                responses = batch_generator.next_generated()
                if not responses:
                    break
                observed_response_ms = (time.perf_counter() - generation_started_at) * 1000.0
                if first_response_ms is None:
                    first_response_ms = observed_response_ms
                for response in responses:
                    if int(getattr(response, "uid", uid)) != uid:
                        continue
                    token_id = int(getattr(response, "token"))
                    detokenizer.add_token(token_id)
                    finish_reason = getattr(response, "finish_reason", None)
                    if finish_reason is not None:
                        finalize = getattr(detokenizer, "finalize", None)
                        if callable(finalize):
                            finalize()
                    text = str(getattr(detokenizer, "last_segment", "") or "")
                    cumulative_raw_text += text
                    if text and first_visible_ms is None:
                        first_visible_ms = (time.perf_counter() - generation_started_at) * 1000.0
                    token_count = len(getattr(detokenizer, "tokens", ()) or ())
                    generation_tps = None
                    if finish_reason is not None:
                        elapsed = max(time.perf_counter() - generation_started_at, 1e-9)
                        generation_tps = token_count / elapsed
                    if prompt_tps is None and token_count > 0:
                        prompt_tps = None
                    peak_memory = _mlx_peak_memory_gb(mx) if finish_reason is not None else None
                    # Cache-reuse metrics only travel on the terminal event.
                    if finish_reason is not None:
                        _cache_hit_mode = _lcp.mode if _lcp is not None else "none"
                        _recovered_prefix_tokens = _lcp.recovered_prefix_tokens if _lcp is not None else 0
                        _cache_fallback_reason = _lcp.fallback_reason if _lcp is not None else ""
                    else:
                        _cache_hit_mode = None
                        _recovered_prefix_tokens = None
                        _cache_fallback_reason = None
                    yield RuntimeTokenEvent(
                        text=text,
                        raw_text=cumulative_raw_text,
                        token_ids=(token_id,),
                        token_logprobs=(),
                        prompt_tokens=len(prompt_tokens),
                        completion_tokens=token_count,
                        prompt_tps=prompt_tps,
                        generation_tps=generation_tps,
                        peak_memory=peak_memory,
                        finish_reason=finish_reason,
                        speculative_acceptance_rate=getattr(response, "speculative_acceptance_rate", None),
                        speculative_rollback_rate=getattr(response, "speculative_rollback_rate", None),
                        speculative_accepted_tokens=getattr(response, "speculative_accepted_tokens", None),
                        speculative_rejected_tokens=getattr(response, "speculative_rejected_tokens", None),
                        speculative_fallback_count=0,
                        speculative_num_draft_tokens=getattr(response, "speculative_num_draft_tokens", None),
                        speculative_draft_model_configured=getattr(
                            response,
                            "speculative_draft_model_configured",
                            None,
                        ),
                        speculative_target_verify_ms=getattr(response, "speculative_backbone_ms", None),
                        native_mtp_timings=NativeMTPBatchTimings(
                            cycle_count=getattr(response, "speculative_cycle_count", None),
                            mtp_head_ms=getattr(response, "speculative_mtp_head_ms", None),
                            sample_ms=getattr(response, "speculative_sample_ms", None),
                            cache_ops_ms=getattr(response, "speculative_cache_ops_ms", None),
                            insert_ms=insert_ms,
                            prepare_ms=prepare_ms,
                            prompt_encode_ms=prompt_encode_ms,
                            prefill_ms=prefill_ms,
                            batch_insert_ms=batch_insert_ms,
                            first_response_ms=first_response_ms,
                            first_visible_ms=first_visible_ms,
                        )
                        if finish_reason is not None
                        else None,
                        cache_hit_mode=_cache_hit_mode,
                        recovered_prefix_tokens=_recovered_prefix_tokens,
                        cache_fallback_reason=_cache_fallback_reason,
                    )
                    if finish_reason is not None:
                        return
        finally:
            if uid is not None and batch_generator is not None:
                remove = getattr(batch_generator, "remove", None)
                if callable(remove):
                    try:
                        remove([uid])
                    except Exception:
                        pass
            if _lcp_entry_to_release is not None:
                try:
                    _prefix_store.release(_lcp_entry_to_release)
                except Exception:
                    pass
                _lcp_entry_to_release = None
            _prefix_store.flush_deferred_clear()

    def _native_mtp_batch_generator(
        self,
        loaded_model: dict[str, Any],
        *,
        sampler,
        max_tokens: int,
        stop_tokens: list[list[int]] | None,
        prefill_step_size: int,
    ):
        config = (tuple(tuple(token) for token in stop_tokens or ()), 1, 1, prefill_step_size)
        cached_config = loaded_model.get(_NATIVE_MTP_TEXT_BATCH_GENERATOR_CONFIG_FIELD)
        cached_generator = loaded_model.get(_NATIVE_MTP_TEXT_BATCH_GENERATOR_FIELD)
        if cached_generator is not None and cached_config == config:
            return cached_generator
        _close_native_mtp_text_batch_generator(loaded_model)
        BatchGenerator = _load_mlx_batch_generator_class()
        batch_generator = BatchGenerator(
            loaded_model["model"],
            max_tokens=max_tokens,
            stop_tokens=stop_tokens,
            sampler=sampler,
            prefill_batch_size=1,
            completion_batch_size=1,
            prefill_step_size=prefill_step_size,
        )
        loaded_model[_NATIVE_MTP_TEXT_BATCH_GENERATOR_FIELD] = batch_generator
        loaded_model[_NATIVE_MTP_TEXT_BATCH_GENERATOR_CONFIG_FIELD] = config
        return batch_generator


class MLXTextRuntime:
    def __init__(self, backend: Any | None = None, executor: MLXRuntimeExecutor | None = None) -> None:
        self._backend = backend or AutoMLXBackend()
        self._executor = executor

    @property
    def runtime_name(self) -> str:
        return getattr(self._backend, "runtime_name", "unknown-runtime")

    @property
    def supports_trust_policy(self) -> bool:
        explicit_support = getattr(self._backend, "supports_trust_policy", None)
        if explicit_support is not None:
            return bool(explicit_support)
        runtime_name = self.runtime_name.strip().lower().replace("-", "_")
        return runtime_name in {"mlx_lm", "mlx_unavailable", "mlx_lm_unavailable"}

    def load_model(self, model_spec, *, trust_remote_code: bool = False):
        def load_backend():
            if _callable_accepts_kwarg(self._backend.load_model, "trust_remote_code"):
                return self._backend.load_model(model_spec, trust_remote_code=trust_remote_code)
            if trust_remote_code:
                raise RuntimeError("Text runtime backend cannot honor trust_remote_code.")
            return self._backend.load_model(model_spec)

        if self._executor is None:
            return load_backend()
        return self._executor.run(load_backend)

    def estimate_resident_bytes(self, model_spec) -> int:
        return int(self._backend.estimate_resident_bytes(model_spec))

    def close_loaded_model(self, loaded_model) -> None:
        close_loaded_model = getattr(self._backend, "close_loaded_model", None)
        if callable(close_loaded_model):
            if self._executor is None:
                close_loaded_model(loaded_model)
            else:
                self._executor.run(lambda: close_loaded_model(loaded_model))

    def score_response(
        self,
        loaded_model,
        prompt: str,
        response: str,
        execution_ext: dict[str, str] | None = None,
    ) -> float:
        scorer = getattr(self._backend, "score_response", None)
        if not callable(scorer):
            raise RuntimeUnavailableError("Text runtime backend does not support reward scoring.")

        def call_scorer() -> float:
            if _callable_accepts_kwarg(scorer, "execution_ext"):
                value = scorer(
                    loaded_model,
                    prompt,
                    response,
                    execution_ext=execution_ext,
                )
            else:
                value = scorer(loaded_model, prompt, response)
            return float(value)

        if self._executor is None:
            return call_scorer()
        return self._executor.run(call_scorer)

    def render_prompt(
        self,
        messages,
        loaded_model: Any | None = None,
        template_kwargs: dict[str, Any] | None = None,
        execution_ext: dict[str, str] | None = None,
    ) -> str:
        if self._executor is not None:
            return self._executor.run(
                lambda: self._render_prompt(
                    messages,
                    loaded_model=loaded_model,
                    template_kwargs=template_kwargs,
                    execution_ext=execution_ext,
                )
            )
        return self._render_prompt(
            messages,
            loaded_model=loaded_model,
            template_kwargs=template_kwargs,
            execution_ext=execution_ext,
        )

    def _render_prompt(
        self,
        messages,
        loaded_model: Any | None = None,
        template_kwargs: dict[str, Any] | None = None,
        execution_ext: dict[str, str] | None = None,
    ) -> str:
        _ = execution_ext
        tokenizer = None
        if isinstance(loaded_model, dict):
            tokenizer = loaded_model.get("tokenizer")
        if tokenizer is not None and hasattr(tokenizer, "apply_chat_template"):
            chat_messages: list[dict[str, str]] = []
            for message in messages:
                text_parts = [part.text for part in message.parts if part.WhichOneof("part") == "text"]
                chat_message = {
                    "role": message.role,
                    "content": "\n".join(text_parts),
                }
                if message.name:
                    chat_message["name"] = message.name
                chat_messages.append(chat_message)
            chat_messages, normalized_count = _normalize_chat_template_messages(chat_messages)
            if execution_ext is not None:
                execution_ext["melix.response_history.normalized_count"] = str(normalized_count)
            resolved_template_kwargs: dict[str, Any] = {
                "tokenize": False,
                "add_generation_prompt": True,
            }
            if template_kwargs:
                resolved_template_kwargs.update(template_kwargs)
            native_tools = _native_template_tools(execution_ext)
            if native_tools and "tools" not in resolved_template_kwargs:
                resolved_template_kwargs["tools"] = native_tools
                if execution_ext is not None:
                    execution_ext["melix.tool_config.native_template_tools"] = "injected"
            return tokenizer.apply_chat_template(chat_messages, **resolved_template_kwargs)

        chunks: list[str] = []
        for message in messages:
            for part in message.parts:
                if part.WhichOneof("part") == "text":
                    chunks.append(part.text)
        return "\n".join(chunks)

    def generate_tokens(
        self,
        loaded_model,
        prompt: str,
        sampling,
        cancel_event,
        execution_ext: dict[str, str] | None = None,
    ):
        stop_contract = resolve_text_stop_contract(loaded_model, sampling, execution_ext)
        if self._executor is None:
            item_iterable = self._backend_generate_tokens(
                loaded_model,
                prompt,
                sampling,
                cancel_event,
                execution_ext,
            )
        else:
            item_iterable = self._executor.iterate(
                lambda: self._backend_generate_tokens(
                    loaded_model,
                    prompt,
                    sampling,
                    cancel_event,
                    execution_ext,
                )
            )
        try:
            normalized_events = (
                item if isinstance(
                    item,
                    (
                        RuntimeTokenEvent,
                        RuntimeToolCallEvent,
                        RuntimeAnnotationEvent,
                        RuntimeToolResultEvent,
                    ),
                )
                else RuntimeTokenEvent(text=str(item))
                for item in item_iterable
            )
            yield from self._apply_stop_sequences(normalized_events, stop_contract.sequences)
        finally:
            close = getattr(item_iterable, "close", None)
            if callable(close):
                close()

    def _backend_generate_tokens(
        self,
        loaded_model,
        prompt: str,
        sampling,
        cancel_event,
        execution_ext: dict[str, str] | None,
    ):
        if _callable_accepts_kwarg(self._backend.generate_tokens, "execution_ext"):
            return self._backend.generate_tokens(
                loaded_model,
                prompt,
                sampling,
                cancel_event,
                execution_ext=execution_ext,
            )
        return self._backend.generate_tokens(loaded_model, prompt, sampling, cancel_event)

    def _apply_stop_sequences(
        self,
        events: Iterable[
            RuntimeTokenEvent
            | RuntimeToolCallEvent
            | RuntimeAnnotationEvent
            | RuntimeToolResultEvent
        ],
        stop_sequences: tuple[str, ...],
    ):
        if not stop_sequences:
            yield from events
            return

        max_stop_prefix_length = _stop_sequence_max_prefix_length(stop_sequences)
        stop_prefixes = _stop_sequence_prefixes(stop_sequences, max_stop_prefix_length)
        pending = ""
        last_token_event: RuntimeTokenEvent | None = None
        for event in events:
            if isinstance(event, (RuntimeToolCallEvent, RuntimeAnnotationEvent, RuntimeToolResultEvent)):
                if pending and last_token_event is not None:
                    yield replace(last_token_event, text=pending, raw_text=pending, finish_reason=None)
                    pending = ""
                yield event
                continue

            last_token_event = event
            candidate = f"{pending}{event.text}"
            stop_index = _first_stop_sequence_index(candidate, stop_sequences)
            if stop_index is not None:
                visible = candidate[:stop_index]
                if visible:
                    yield replace(event, text=visible, raw_text=visible, finish_reason=None)
                yield replace(event, text="", raw_text="", finish_reason="stop_sequence")
                return

            held_suffix = _viable_stop_prefix_suffix(candidate, stop_sequences, max_stop_prefix_length, stop_prefixes)
            if held_suffix:
                visible = candidate[: -len(held_suffix)]
                pending = held_suffix
            else:
                visible = candidate
                pending = ""

            if visible:
                if not pending and event.raw_text is None:
                    yield event
                else:
                    raw_text = event.raw_text if visible == event.text else visible
                    yield replace(
                        event,
                        text=visible,
                        raw_text=raw_text,
                        finish_reason=None if pending else event.finish_reason,
                    )
            elif event.finish_reason and not pending:
                yield event

        if pending and last_token_event is not None:
            yield replace(last_token_event, text=pending, raw_text=pending)


def _first_stop_sequence_index(text: str, stop_sequences: tuple[str, ...]) -> int | None:
    first_index: int | None = None
    for sequence in stop_sequences:
        index = text.find(sequence)
        if index < 0:
            continue
        if first_index is None or index < first_index:
            first_index = index
            if first_index == 0:
                break
    return first_index


def _stop_sequence_max_prefix_length(stop_sequences: tuple[str, ...]) -> int:
    return max((len(sequence) for sequence in stop_sequences), default=0) - 1


def _stop_sequence_prefixes(stop_sequences: tuple[str, ...], max_stop_prefix_length: int) -> frozenset[str]:
    if max_stop_prefix_length <= 0:
        return frozenset()
    return frozenset(
        sequence[:length]
        for sequence in stop_sequences
        for length in range(1, min(len(sequence), max_stop_prefix_length) + 1)
    )


def _viable_stop_prefix_suffix(
    text: str,
    stop_sequences: tuple[str, ...],
    max_stop_prefix_length: int | None = None,
    stop_prefixes: frozenset[str] | None = None,
) -> str:
    if max_stop_prefix_length is None:
        max_stop_prefix_length = _stop_sequence_max_prefix_length(stop_sequences)
    if stop_prefixes is None:
        stop_prefixes = _stop_sequence_prefixes(stop_sequences, max_stop_prefix_length)
    max_prefix_length = min(len(text), max_stop_prefix_length)
    for length in range(max_prefix_length, 0, -1):
        suffix = text[-length:]
        if suffix in stop_prefixes:
            return suffix
    return ""
