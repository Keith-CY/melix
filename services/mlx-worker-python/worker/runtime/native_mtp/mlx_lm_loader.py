from __future__ import annotations

import importlib.util
import json
import logging
import os
from pathlib import Path
from typing import Any, Callable, Type

logger = logging.getLogger(__name__)

_PATCHED = False
_MTP_WEIGHT_KEY_PREFIXES = ("language_model.mtp.", "mtp.")


def _load_json_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_bytes())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _is_mtp_weight_key(key: Any) -> bool:
    if isinstance(key, str):
        return key.startswith(_MTP_WEIGHT_KEY_PREFIXES)
    return str(key).startswith(_MTP_WEIGHT_KEY_PREFIXES)


def _model_safetensor_files(model_path: Path) -> list[str]:
    """Return top-level ``model*.safetensors`` paths without glob allocation."""

    weight_files: list[str] = []
    append_weight_file = weight_files.append
    try:
        with os.scandir(model_path) as entries:
            for entry in entries:
                name = entry.name
                if name.startswith("model") and name.endswith(".safetensors"):
                    append_weight_file(entry.path)
    except FileNotFoundError:
        return []
    weight_files.sort()
    return weight_files


def extra_mtp_safetensor_files(model_path: Path) -> list[Path]:
    index_payload = _load_json_payload(model_path / "model.safetensors.index.json")
    weight_map = index_payload.get("weight_map")
    if not isinstance(weight_map, dict):
        return []

    extra_files: list[Path] = []
    append_extra_file = extra_files.append
    seen: set[str] = set()
    seen_add = seen.add
    model_path_text = os.fspath(model_path)
    path_join = os.path.join
    path_exists = os.path.exists
    path_basename = os.path.basename
    mtp_key_prefixes = _MTP_WEIGHT_KEY_PREFIXES
    for key, file_name in weight_map.items():
        if not key.startswith(mtp_key_prefixes):
            continue
        file_name_text = str(file_name)
        if file_name_text in seen:
            continue
        seen_add(file_name_text)
        if not file_name_text.endswith(".safetensors") or path_basename(
            file_name_text
        ).startswith("model"):
            continue
        path_text = path_join(model_path_text, file_name_text)
        if not path_exists(path_text):
            logger.warning("MTP shard listed in index is missing: %s", path_text)
            continue
        append_extra_file(Path(path_text))
    return extra_files


def apply() -> bool:
    """Patch mlx-lm load_model so native-MTP sidecar shards are loaded."""
    global _PATCHED
    if _PATCHED:
        return True

    try:
        import mlx.core as mx
        import mlx.nn as nn
        import mlx_lm.utils as utils
        from mlx_lm.utils import (
            _get_classes,
            _transform_awq_weights,
            load_config,
        )
    except ImportError:
        logger.debug("mlx-lm loader utilities unavailable; skipping MTP loader patch")
        return False

    original_load_model = utils.load_model

    def patched_load_model(
        model_path: Path,
        lazy: bool = False,
        strict: bool = True,
        model_config: dict[str, Any] | None = None,
        get_model_classes: Callable[[dict], tuple[Type[nn.Module], Type]] = _get_classes,
    ) -> tuple[nn.Module, dict]:
        model_path = Path(model_path)
        extra_files = extra_mtp_safetensor_files(model_path)
        if not extra_files:
            return original_load_model(
                model_path,
                lazy=lazy,
                strict=strict,
                model_config=model_config,
                get_model_classes=get_model_classes,
            )

        config = load_config(model_path)
        if model_config is not None:
            config.update(model_config)

        weight_files = _model_safetensor_files(model_path)
        if not weight_files and strict:
            raise FileNotFoundError(f"No safetensors found in {model_path}")

        weights = {}
        for wf in [*weight_files, *(str(path) for path in extra_files)]:
            weights.update(mx.load(wf))

        if (model_file := config.get("model_file")) is not None:
            spec = importlib.util.spec_from_file_location(
                "custom_model",
                model_path / model_file,
            )
            arch = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(arch)
            model_class, model_args_class = arch.Model, arch.ModelArgs
        else:
            model_class, model_args_class = get_model_classes(config=config)

        if "quantization_config" not in config:
            text_config = config.get("text_config", {})
            if "quantization_config" in text_config:
                config["quantization_config"] = text_config["quantization_config"]

        model_args = model_args_class.from_dict(config)
        model = model_class(model_args)

        if hasattr(model, "sanitize"):
            weights = model.sanitize(weights)

        def _quantize(quantization):
            def class_predicate(p, m):
                if p in config["quantization"]:
                    return config["quantization"][p]
                if not hasattr(m, "to_quantized"):
                    return False
                return f"{p}.scales" in weights

            nn.quantize(
                model,
                group_size=quantization["group_size"],
                bits=quantization["bits"],
                mode=quantization.get("mode", "affine"),
                class_predicate=class_predicate,
            )

        if (quantization := config.get("quantization", None)) is not None:
            _quantize(quantization)

        elif quantization_config := config.get("quantization_config", False):
            quant_method = quantization_config["quant_method"]
            if quant_method == "bitnet":
                from mlx_lm.models.bitlinear_layers import bitnet_quantize

                model = bitnet_quantize(model, quantization_config)
            elif quant_method == "mxfp4":
                quantization = {"group_size": 32, "bits": 4, "mode": "mxfp4"}
                config["quantization"] = quantization
                config["quantization_config"] = quantization
                _quantize(quantization)
            elif quant_method == "compressed-tensors":
                quantization = {"group_size": 32, "bits": 4, "mode": "affine"}
                config["quantization"] = quantization
                config["quantization_config"] = quantization
                _quantize(quantization)
            elif quant_method in ("awq", "gptq"):
                weights, quantization = _transform_awq_weights(
                    weights,
                    quantization_config,
                )
                config["quantization"] = quantization
                config["quantization_config"] = quantization
                _quantize(quantization)

        if config.get("quantize_activations", False):

            def _maybe_qq(m):
                if isinstance(m, nn.QuantizedLinear):
                    if m.mode not in ("nvfp4", "mxfp8"):
                        raise ValueError(
                            "Mode ({m.mode}) does not support activation quantization"
                        )
                    if m.get("bias", False):
                        raise ValueError(
                            "Linear layer with bias does not support activation quantization"
                        )
                    out_dims, in_dims = m.weight.shape
                    in_dims *= 32 // m.bits
                    return nn.QQLinear(in_dims, out_dims, m.group_size, m.bits, m.mode)
                return m

            leaves = utils.tree_map(
                _maybe_qq,
                model.leaf_modules(),
                is_leaf=nn.Module.is_module,
            )
            model.update_modules(leaves)

        model.eval()
        model.load_weights(list(weights.items()), strict=strict)

        if not lazy:
            mx.eval(model.parameters())

        return model, config

    utils.load_model = patched_load_model
    _PATCHED = True
    logger.info("mlx-lm native MTP loader patch applied.")
    return True
