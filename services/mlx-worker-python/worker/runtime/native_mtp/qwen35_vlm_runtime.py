# SPDX-License-Identifier: Apache-2.0
"""Runtime MTP head attachment for the mlx-vlm Qwen3.5 (dense) VLM path.

Mirror of ``qwen35_moe_vlm_runtime.py`` for the dense Qwen3.5/3.6 family
(model_type=qwen3_5, e.g. Qwen3.6-27B). The MoE variant was wired up in
PR 1180; this companion handles dense VLM checkpoints that ship MTP
heads (mtp_num_hidden_layers > 0).

It adds:

* a Multi-Token Prediction head (``MTPModule``) to
  ``mlx_vlm.models.qwen3_5.language.LanguageModel`` when the config
  declares ``mtp_num_hidden_layers > 0`` and the process-wide MTP active
  flag is on;
* a ``return_hidden=True`` mode on ``LanguageModel.__call__`` that
  returns ``(logits, pre_norm_hidden, gdn_states)`` for the speculative
  rollback path without using the stock hidden-state capture sink;
* a ``Qwen3_5GatedDeltaNet`` body matching mlx-lm cache semantics while
  preserving ``gdn_sink`` capture for rejected-draft rollback.

Outer ``Model.sanitize`` is already patched separately by
``qwen35_vlm_model.py`` (MTP-key preservation + norm +1 shift), so no
sanitize work is needed here.

Apply ordering: this patch must run *before* ``mlx_vlm.utils.load(...)`` so the
patched ``LanguageModel.__init__`` runs while mlx-vlm constructs the model.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

import mlx.core as mx
import mlx.nn as nn

logger = logging.getLogger(__name__)

_APPLIED = False


def apply() -> bool:
    """Apply the mlx-vlm Qwen3.5 (dense) runtime MTP patches. Idempotent."""
    global _APPLIED
    if _APPLIED:
        return True

    try:
        from mlx_vlm.models.qwen3_5 import config as q35_config
        from mlx_vlm.models.qwen3_5 import language as q35_lang
    except Exception as e:
        logger.debug(f"mlx_vlm.qwen3_5 not importable for MTP runtime: {e}")
        return False

    _patch_text_config(q35_config)
    _register_mtp_classes_for_vlm(q35_lang)
    _patch_attention_plain_rope(q35_lang)
    _patch_gated_delta_net(q35_lang)
    _patch_decoder_layer(q35_lang)
    _patch_qwen3_5_model(q35_lang)
    _patch_vlm_language_model(q35_lang)

    _APPLIED = True
    logger.info("mlx-vlm Qwen3.5/Qwen3.6 runtime MTP patch applied")
    return True


# ---------------------------------------------------------------------------
# TextConfig — retain mtp_num_hidden_layers as instance attribute.
# ---------------------------------------------------------------------------

def _patch_text_config(q35_config: Any) -> None:
    """Wrap ``TextConfig.from_dict`` so ``mtp_num_hidden_layers`` survives.

    mlx-vlm's ``BaseModelConfig.from_dict`` filters incoming params by the
    dataclass signature, dropping any key that isn't a declared field —
    including ``mtp_num_hidden_layers``. Without it the MTP head can't be
    sized; with it, ``LanguageModel.__init__`` knows to attach a head.
    """
    cls = q35_config.TextConfig
    if getattr(cls, "_melix_mtp_from_dict_patched", False):
        return

    original_from_dict = cls.from_dict.__func__  # unwrap classmethod

    def patched_from_dict(cls_inner, params):
        instance = original_from_dict(cls_inner, params)
        if params:
            instance.mtp_num_hidden_layers = int(
                params.get("mtp_num_hidden_layers", 0) or 0
            )
        else:
            instance.mtp_num_hidden_layers = 0
        return instance

    cls.from_dict = classmethod(patched_from_dict)
    cls._melix_mtp_from_dict_patched = True


# ---------------------------------------------------------------------------
# MTPDecoderLayer + MTPModule — dense VLM classes.
# ---------------------------------------------------------------------------

def _register_mtp_classes_for_vlm(q35_lang: Any) -> None:
    """Attach ``MTPDecoderLayer`` / ``MTPModule`` to the mlx-vlm qwen3_5
    language module. Dense uses ``Qwen3_5MLP`` (no MoE branch)."""
    if hasattr(q35_lang, "MTPModule"):
        return

    Attention = q35_lang.Qwen3_5Attention
    MLP = q35_lang.Qwen3_5MLP
    from mlx_vlm.models.qwen3_5.language import create_attention_mask

    class MTPDecoderLayer(nn.Module):
        """Full-attention transformer layer used inside the dense MTP head."""

        def __init__(self, args):
            super().__init__()
            self.self_attn = Attention(args)
            self.input_layernorm = nn.RMSNorm(args.hidden_size, eps=args.rms_norm_eps)
            self.post_attention_layernorm = nn.RMSNorm(
                args.hidden_size, eps=args.rms_norm_eps
            )
            self.mlp = MLP(args.hidden_size, args.intermediate_size)

        def __call__(self, x, mask=None, cache=None, position_ids=None):
            r = self.self_attn(self.input_layernorm(x), mask, cache, position_ids)
            h = x + r
            return h + self.mlp(self.post_attention_layernorm(h))

    class MTPModule(nn.Module):
        """Multi-Token Prediction head (mlx-lm PR 990) for dense VLM Qwen3.5/3.6.

        Predicts token t+2 by fusing the backbone pre-norm hidden state at
        position t with the embedding of the sampled main token t+1.
        """

        def __init__(self, args):
            super().__init__()
            self.pre_fc_norm_hidden = nn.RMSNorm(
                args.hidden_size, eps=args.rms_norm_eps
            )
            self.pre_fc_norm_embedding = nn.RMSNorm(
                args.hidden_size, eps=args.rms_norm_eps
            )
            self.fc = nn.Linear(args.hidden_size * 2, args.hidden_size, bias=False)
            self.layers = [
                MTPDecoderLayer(args) for _ in range(args.mtp_num_hidden_layers)
            ]
            self.norm = nn.RMSNorm(args.hidden_size, eps=args.rms_norm_eps)

        def __call__(self, hidden_states, next_token_ids, embed_tokens, cache=None):
            embeds = embed_tokens(next_token_ids)
            e = self.pre_fc_norm_embedding(embeds)
            h = self.pre_fc_norm_hidden(hidden_states)
            fused = self.fc(mx.concatenate([e, h], axis=-1))

            if cache is None:
                cache = [None] * len(self.layers)

            mask = create_attention_mask(fused, cache[0] if cache else None)
            for layer, c in zip(self.layers, cache):
                fused = layer(fused, mask, c)

            return self.norm(fused)

    q35_lang.MTPDecoderLayer = MTPDecoderLayer
    q35_lang.MTPModule = MTPModule


# ---------------------------------------------------------------------------
# Attention — pure text path uses plain 1D RoPE instead of multimodal RoPE.
# ---------------------------------------------------------------------------

_ROPE_LOCAL = threading.local()


def _force_text_only_rope_enabled() -> bool:
    return bool(getattr(_ROPE_LOCAL, "force_text_only", False))


class _ForceTextOnlyRoPE:
    def __enter__(self):
        _ROPE_LOCAL.depth = getattr(_ROPE_LOCAL, "depth", 0) + 1
        _ROPE_LOCAL.force_text_only = True
        return self

    def __exit__(self, exc_type, exc, tb):
        depth = getattr(_ROPE_LOCAL, "depth", 1) - 1
        _ROPE_LOCAL.depth = max(0, depth)
        if depth <= 0:
            _ROPE_LOCAL.force_text_only = False
        return False


def _rotate_half(x):
    half = x.shape[-1] // 2
    x1 = x[..., :half]
    x2 = x[..., half:]
    return mx.concatenate([-x2, x1], axis=-1)


def _position_ids_are_text_only(position_ids) -> bool:
    if position_ids is None:
        return True
    if position_ids.ndim < 3 or position_ids.shape[0] != 3:
        return True
    p0 = position_ids[0]
    p1 = position_ids[1]
    p2 = position_ids[2]
    return bool(mx.all(p0 == p1).item()) and bool(mx.all(p1 == p2).item())


def _patch_attention_plain_rope(q35_lang: Any) -> None:
    cls = q35_lang.Qwen3_5Attention
    if "_melix_plain_rope_patched" in cls.__dict__:
        return

    scaled_dot_product_attention = getattr(
        q35_lang,
        "scaled_dot_product_attention",
        None,
    )
    apply_multimodal_rotary_pos_emb = getattr(
        q35_lang,
        "apply_multimodal_rotary_pos_emb",
        None,
    )
    if not callable(scaled_dot_product_attention):
        try:
            from mlx_vlm.models.base import scaled_dot_product_attention
        except Exception as exc:
            logger.debug("Qwen3.5 plain-RoPE attention patch unavailable: %s", exc)
            return
    if not callable(apply_multimodal_rotary_pos_emb):
        try:
            from mlx_vlm.models.qwen3_5.language import apply_multimodal_rotary_pos_emb
        except Exception as exc:
            logger.debug("Qwen3.5 mRoPE helper unavailable: %s", exc)
            return

    def __call__(
        self,
        x,
        mask=None,
        cache=None,
        position_ids=None,
    ):
        B, L, _D = x.shape

        q_proj_output = self.q_proj(x)
        queries, gate = mx.split(
            q_proj_output.reshape(B, L, self.num_attention_heads, -1),
            2,
            axis=-1,
        )
        gate = gate.reshape(B, L, -1)

        keys, values = self.k_proj(x), self.v_proj(x)

        queries = self.q_norm(queries).transpose(0, 2, 1, 3)
        keys = self.k_norm(
            keys.reshape(B, L, self.num_key_value_heads, -1)
        ).transpose(0, 2, 1, 3)
        values = values.reshape(B, L, self.num_key_value_heads, -1).transpose(
            0,
            2,
            1,
            3,
        )

        kv_seq_len = keys.shape[-2]
        if cache is not None:
            kv_seq_len += cache.offset + 1

        if mask is not None and isinstance(mask, mx.array):
            if isinstance(kv_seq_len, mx.array):
                kv_seq_len = kv_seq_len.max().item()
            mask = mask[..., : int(kv_seq_len)]

        forced_plain = _force_text_only_rope_enabled()
        use_plain = True
        if not forced_plain and position_ids is not None:
            try:
                use_plain = _position_ids_are_text_only(position_ids)
            except Exception:
                use_plain = False

        if use_plain:
            offset = cache.offset if cache is not None and hasattr(cache, "offset") else 0
            if isinstance(offset, mx.array):
                if offset.ndim == 0:
                    offset_value = int(offset.item())
                else:
                    use_plain = False
            else:
                offset_value = int(offset)

        if use_plain:
            inv_freq = self.rotary_emb.inv_freq
            positions = mx.arange(offset_value, offset_value + L).astype(mx.float32)
            freqs = positions[:, None] * inv_freq[None, :].astype(mx.float32)
            emb = mx.concatenate([freqs, freqs], axis=-1)
            cos = mx.cos(emb)[None, None, :, :]
            sin = mx.sin(emb)[None, None, :, :]

            rotary_dim = cos.shape[-1]
            q_rot = queries[..., :rotary_dim]
            q_pass = queries[..., rotary_dim:]
            k_rot = keys[..., :rotary_dim]
            k_pass = keys[..., rotary_dim:]

            dtype = queries.dtype
            q_rot = ((q_rot * cos) + (_rotate_half(q_rot) * sin)).astype(dtype)
            k_rot = ((k_rot * cos) + (_rotate_half(k_rot) * sin)).astype(dtype)

            queries = mx.concatenate([q_rot, q_pass], axis=-1)
            keys = mx.concatenate([k_rot, k_pass], axis=-1)
        else:
            if position_ids is None:
                if cache is not None:
                    position_ids = mx.arange(cache.offset, cache.offset + L)
                else:
                    position_ids = mx.arange(L)
                position_ids = mx.expand_dims(position_ids, axis=0)
                position_ids = mx.tile(position_ids, (3, 1, 1))
            cos, sin = self.rotary_emb(values, position_ids)
            queries, keys = apply_multimodal_rotary_pos_emb(queries, keys, cos, sin)

        if cache is not None:
            keys, values = cache.update_and_fetch(keys, values)

        output = scaled_dot_product_attention(
            queries,
            keys,
            values,
            cache=cache,
            scale=self.scale,
            mask=mask,
        )
        output = output.transpose(0, 2, 1, 3).reshape(B, L, -1)
        return self.o_proj(output * mx.sigmoid(gate))

    cls.__call__ = __call__
    cls._melix_plain_rope_patched = True


# ---------------------------------------------------------------------------
# Backbone graph — gdn_sink capture for SSM rollback.
# ---------------------------------------------------------------------------

def _patch_gated_delta_net(q35_lang: Any) -> None:
    cls = q35_lang.Qwen3_5GatedDeltaNet
    if "_melix_mtp_runtime_patched" in cls.__dict__:
        return

    from mlx_lm.models.gated_delta import gated_delta_update

    try:
        from mlx.nn.layers.distributed import sum_gradients
    except Exception:  # pragma: no cover - mlx installs normally provide it.
        sum_gradients = None

    original_call = cls.__call__

    def _process_chunk(
        self,
        qkv_chunk,
        a_chunk,
        b_chunk,
        conv_state,
        ssm_state,
        ssm_mask=None,
        lengths=None,
    ):
        B, S_chunk = qkv_chunk.shape[:2]
        conv_in = mx.concatenate([conv_state, qkv_chunk], axis=1)
        n_keep = self.conv_kernel_size - 1
        if lengths is not None:
            ends = mx.clip(lengths, 0, S_chunk)
            positions = (ends[:, None] + mx.arange(n_keep))[..., None]
            new_conv_state = mx.take_along_axis(conv_in, positions, axis=1)
        else:
            new_conv_state = conv_in[:, -n_keep:]
            if hasattr(mx, "contiguous"):
                new_conv_state = mx.contiguous(new_conv_state)

        conv_out = nn.silu(self.conv1d(conv_in))
        q, k, v = [
            t.reshape(B, S_chunk, h, d)
            for t, h, d in zip(
                mx.split(conv_out, [self.key_dim, 2 * self.key_dim], -1),
                [self.num_k_heads, self.num_k_heads, self.num_v_heads],
                [self.head_k_dim, self.head_k_dim, self.head_v_dim],
            )
        ]
        inv_scale = k.shape[-1] ** -0.5
        q = (inv_scale**2) * mx.fast.rms_norm(q, None, 1e-6)
        k = inv_scale * mx.fast.rms_norm(k, None, 1e-6)

        out, new_ssm_state = gated_delta_update(
            q,
            k,
            v,
            a_chunk,
            b_chunk,
            self.A_log,
            self.dt_bias,
            ssm_state,
            ssm_mask,
            use_kernel=not self.training,
        )
        return out, new_conv_state, new_ssm_state

    def __call__(
        self,
        inputs,
        mask=None,
        cache=None,
        gdn_sink=None,
        n_confirmed: int = 0,
    ):
        B, S, _ = inputs.shape

        sharding_group = getattr(self, "sharding_group", None)
        if sharding_group is not None and sum_gradients is not None:
            inputs = sum_gradients(sharding_group)(inputs)

        qkv = self.in_proj_qkv(inputs)
        z = self.in_proj_z(inputs).reshape(B, S, self.num_v_heads, self.head_v_dim)
        b = self.in_proj_b(inputs)
        a = self.in_proj_a(inputs)

        if cache is not None and cache[0] is not None:
            conv_state = cache[0]
            if getattr(conv_state, "shape", (B,))[0] != B:
                conv_state = mx.zeros(
                    (B, self.conv_kernel_size - 1, self.conv_dim),
                    dtype=inputs.dtype,
                )
        else:
            conv_state = mx.zeros(
                (B, self.conv_kernel_size - 1, self.conv_dim),
                dtype=inputs.dtype,
            )

        ssm_state = cache[1] if cache else None
        if ssm_state is not None and getattr(ssm_state, "shape", (B,))[0] != B:
            ssm_state = None

        if mask is not None:
            if getattr(mask, "shape", (B,))[0] != B:
                mask = None
            else:
                qkv = mx.where(mask[..., None], qkv, 0)

        conv_in = mx.concatenate([conv_state, qkv], axis=1)
        n_keep = self.conv_kernel_size - 1
        if cache is not None:
            lengths = getattr(cache, "lengths", None)
            if lengths is not None:
                ends = mx.clip(lengths, 0, S)
                positions = (ends[:, None] + mx.arange(n_keep))[..., None]
                cache[0] = mx.take_along_axis(conv_in, positions, axis=1)
            else:
                cache[0] = conv_in[:, -n_keep:]
                if hasattr(mx, "contiguous"):
                    cache[0] = mx.contiguous(cache[0])

        conv_out = nn.silu(self.conv1d(conv_in))
        q, k, v = [
            t.reshape(B, S, h, d)
            for t, h, d in zip(
                mx.split(conv_out, [self.key_dim, 2 * self.key_dim], -1),
                [self.num_k_heads, self.num_k_heads, self.num_v_heads],
                [self.head_k_dim, self.head_k_dim, self.head_v_dim],
            )
        ]
        inv_scale = k.shape[-1] ** -0.5
        q = (inv_scale**2) * mx.fast.rms_norm(q, None, 1e-6)
        k = inv_scale * mx.fast.rms_norm(k, None, 1e-6)

        if gdn_sink is not None:
            gdn_sink.append(
                (
                    q,
                    k,
                    v,
                    a,
                    b,
                    self.A_log,
                    self.dt_bias,
                    ssm_state,
                    mask,
                    conv_in,
                    self.conv_kernel_size,
                )
            )

        out, ssm_f = gated_delta_update(
            q,
            k,
            v,
            a,
            b,
            self.A_log,
            self.dt_bias,
            ssm_state,
            mask,
            use_kernel=not self.training,
        )

        if cache is not None:
            cache[1] = ssm_f
            if hasattr(cache, "advance"):
                cache.advance(S)

        out = self.norm(out, z)
        out = self.out_proj(out.reshape(B, S, -1))

        if sharding_group is not None:
            out = mx.distributed.all_sum(out, group=sharding_group)

        return out

    cls._process_chunk = _process_chunk
    cls.__call__ = __call__
    cls._melix_mtp_runtime_patched = True


def _patch_decoder_layer(q35_lang: Any) -> None:
    cls = q35_lang.Qwen3_5DecoderLayer
    if "_melix_mtp_runtime_patched" in cls.__dict__:
        return

    def __call__(
        self,
        x,
        mask=None,
        cache=None,
        position_ids=None,
        gdn_sink=None,
        n_confirmed: int = 0,
    ):
        if self.is_linear:
            h_in = self.input_layernorm(x)
            if gdn_sink is not None:
                r = self.linear_attn(h_in, mask, cache, gdn_sink=gdn_sink)
            elif n_confirmed:
                r = self.linear_attn(h_in, mask, cache, n_confirmed=n_confirmed)
            else:
                r = self.linear_attn(h_in, mask, cache)
        else:
            r = self.self_attn(self.input_layernorm(x), mask, cache, position_ids)
        h = x + r
        return h + self.mlp(self.post_attention_layernorm(h))

    cls.__call__ = __call__
    cls._melix_mtp_runtime_patched = True


def _patch_qwen3_5_model(q35_lang: Any) -> None:
    cls = q35_lang.Qwen3_5Model
    if "_melix_mtp_runtime_patched" in cls.__dict__:
        return

    create_attention_mask = q35_lang.create_attention_mask
    create_ssm_mask = getattr(q35_lang, "create_ssm_mask", lambda _h, _cache=None: None)

    def __call__(
        self,
        inputs,
        inputs_embeds=None,
        mask=None,
        cache=None,
        position_ids=None,
        capture_layer_ids=None,
        hidden_sink=None,
        gdn_sink=None,
        n_confirmed: int = 0,
        return_pre_norm: bool = False,
    ):
        _ = mask
        if inputs_embeds is None:
            h = self.embed_tokens(inputs)
        else:
            h = inputs_embeds

        if cache is None:
            cache = [None] * len(self.layers)

        fa_mask = create_attention_mask(h, cache[self.fa_idx])
        ssm_mask = create_ssm_mask(h, cache[self.ssm_idx])

        capture_set = set(capture_layer_ids) if capture_layer_ids else set()
        for i, (layer, c) in enumerate(zip(self.layers, cache)):
            layer_mask = ssm_mask if layer.is_linear else fa_mask
            h = layer(
                h,
                layer_mask,
                c,
                position_ids,
                gdn_sink=gdn_sink,
                n_confirmed=n_confirmed,
            )
            if hidden_sink is not None and i in capture_set:
                hidden_sink.append(h)

        if return_pre_norm:
            return h
        return self.norm(h)

    cls.__call__ = __call__
    cls._melix_mtp_runtime_patched = True


# ---------------------------------------------------------------------------
# LanguageModel — wrap __init__, support return_hidden, add mtp_forward/cache.
# ---------------------------------------------------------------------------

def _patch_vlm_language_model(q35_lang: Any) -> None:
    cls = q35_lang.LanguageModel
    if "_melix_mtp_runtime_patched" in cls.__dict__:
        return

    from mlx_lm.models.cache import KVCache

    original_init = cls.__init__
    original_call = cls.__call__

    def __init__(self, args, config=None):
        original_init(self, args, config)
        # Always attach MTPModule when the config declares MTP heads, so
        # mlx-vlm's load_weights (which skips Model.sanitize for is_mlx_format
        # checkpoints) can place the persisted mtp.* tensors. Whether MTP
        # speculative decode is actually invoked at inference time is gated
        # downstream by ``native_mtp.batch_generator._is_mtp_eligible``,
        # which checks Melix's process-wide ``is_mtp_active`` flag.
        # Without this unconditional attach, mtp_enabled=False would fail
        # VLM load with "Received N parameters not in model" and the engine
        # pool would permanently downgrade the entry to BatchedEngine —
        # losing vision support.
        n_mtp = int(getattr(args, "mtp_num_hidden_layers", 0) or 0)
        attach_mtp = False
        try:
            from . import should_attach_mtp_head

            attach_mtp = should_attach_mtp_head()
        except Exception:
            attach_mtp = False
        if n_mtp > 0 and attach_mtp:
            self.mtp = q35_lang.MTPModule(args)

    def __call__(self, inputs, inputs_embeds=None, mask=None, cache=None, **kwargs):
        """Backbone forward with optional MTP-cycle return shape.

        With ``return_hidden=True``, returns the triple
        ``(logits, pre_norm_hidden, gdn_states)`` for the speculative decode
        cycle. ``gdn_states`` lets ``rollback_speculative_cache`` restore
        rejected drafts while avoiding the stock hidden-state capture sink.
        """
        return_hidden = kwargs.pop("return_hidden", False)
        n_confirmed = int(kwargs.pop("n_confirmed", 0) or 0)
        if not return_hidden:
            return original_call(self, inputs, inputs_embeds, mask, cache, **kwargs)

        position_ids = kwargs.pop("position_ids", None)
        pixel_values = kwargs.pop("pixel_values", None)
        image_grid_thw = kwargs.pop("image_grid_thw", None)
        video_grid_thw = kwargs.pop("video_grid_thw", None)
        kwargs.pop("capture_layer_ids", None)
        rope_deltas_kw = kwargs.pop("rope_deltas", None)

        if pixel_values is not None:
            self._rope_deltas = None
            self._position_ids = None

        if hasattr(inputs, "shape"):
            cache_offset = 0
            cache_offsets = None
            if cache and cache[self.model.fa_idx] is not None:
                c0 = cache[self.model.fa_idx]
                cache_offset = c0._idx if hasattr(c0, "_idx") else c0.offset
                mx_array_type = getattr(mx, "array", None)
                if (
                    mx_array_type is not None
                    and isinstance(c0.offset, mx_array_type)
                    and c0.offset.ndim > 0
                    and c0.offset.size > 1
                ):
                    cache_offsets = mx.maximum(c0.offset, 0)

            rope_mask = mask
            if (
                mask is not None
                and hasattr(mask, "shape")
                and mask.shape[-1] != inputs.shape[-1]
            ):
                rope_mask = None

            if (
                position_ids is None
                and (rope_mask is None or rope_mask.ndim == 2)
                and len(inputs.shape) >= 2
            ):
                batch_size, seq_length = inputs.shape
                if (
                    (
                        cache is not None
                        and cache[self.model.fa_idx] is not None
                        and (cache_offset == 0)
                    )
                    or self._rope_deltas is None
                    or cache is None
                ):
                    if (
                        self._position_ids is not None
                        and self._position_ids.shape[1] == batch_size
                        and self._position_ids.shape[-1] >= cache_offset + seq_length
                    ):
                        position_ids = self._position_ids[
                            :, :, cache_offset : cache_offset + seq_length
                        ]
                    else:
                        position_ids, rope_deltas = self.get_rope_index(
                            inputs, image_grid_thw, video_grid_thw, rope_mask
                        )
                        self._rope_deltas = rope_deltas
                        self._position_ids = position_ids
                else:
                    if cache_offsets is not None and cache_offsets.size >= batch_size:
                        offsets = cache_offsets[:batch_size]
                        rope_deltas = (
                            rope_deltas_kw
                            if rope_deltas_kw is not None
                            else self._rope_deltas
                        )
                        if rope_deltas.shape[0] > batch_size:
                            rope_deltas = rope_deltas[:batch_size]
                        delta = (offsets + rope_deltas.squeeze(-1))[:, None]
                    else:
                        delta = mx.array(
                            cache_offset + self._rope_deltas
                            if cache is not None
                            else 0
                        )
                        if delta.ndim == 0:
                            delta = mx.expand_dims(delta, axis=0)
                        if delta.shape[0] < batch_size:
                            delta = mx.tile(delta, (batch_size, 1))
                        else:
                            delta = delta[:batch_size]

                    position_ids = mx.arange(seq_length).reshape(1, -1)
                    position_ids = mx.broadcast_to(
                        position_ids, (batch_size, seq_length)
                    )
                    position_ids = mx.add(position_ids, delta)[None, ...]
                    position_ids = mx.broadcast_to(
                        position_ids, (3, batch_size, seq_length)
                    )

        gdn_states = []
        hidden_pre_norm = self.model(
            inputs,
            cache=cache,
            inputs_embeds=inputs_embeds,
            position_ids=position_ids,
            n_confirmed=n_confirmed,
            gdn_sink=gdn_states,
            return_pre_norm=True,
        )
        normed = self.model.norm(hidden_pre_norm)
        if self.args.tie_word_embeddings:
            logits = self.model.embed_tokens.as_linear(normed)
        else:
            logits = self.lm_head(normed)
        return logits, hidden_pre_norm, gdn_states

    def mtp_forward(self, hidden_states, next_token_ids, mtp_cache):
        mtp_out = self.mtp(
            hidden_states,
            next_token_ids,
            self.model.embed_tokens,
            mtp_cache,
        )
        if self.args.tie_word_embeddings:
            return self.model.embed_tokens.as_linear(mtp_out)
        return self.lm_head(mtp_out)

    def make_mtp_cache(self):
        if hasattr(self, "mtp"):
            return [KVCache() for _ in self.mtp.layers]
        return []

    @staticmethod
    def _melix_force_text_only_rope_context():
        return _ForceTextOnlyRoPE()

    cls.__init__ = __init__
    cls.__call__ = __call__
    cls.mtp_forward = mtp_forward
    cls.make_mtp_cache = make_mtp_cache
    cls._melix_force_text_only_rope_context = _melix_force_text_only_rope_context
    cls._melix_mtp_runtime_patched = True
