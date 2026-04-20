from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


REAL_SMALL_TEXT_MODEL_ID = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
REAL_SMALL_TEXT_MODEL_PATH_ENV = "MELIX_PHASE8_REAL_SMALL_MODEL_PATH"
REAL_SMALL_TEXT_MODEL_E2E_ENV = "MELIX_PHASE8_REAL_SMALL_MODEL_E2E"
_MANAGED_MODEL_ROOT_ENV = "MELIX_MANAGED_MODEL_ROOT"


@dataclass(frozen=True, slots=True)
class RealSmallTextModelSource:
    model_id: str
    live: bool
    local_model_path: str
    source_resolution_mode: str
    warnings: tuple[str, ...] = ()

    @property
    def model_path_for_runtime(self) -> str:
        return self.local_model_path or self.model_id


@dataclass(frozen=True, slots=True)
class _HuggingFaceCacheModelPath:
    path: Path
    warnings: tuple[str, ...] = ()


def resolve_real_small_text_model_source(
    *,
    model_id: str = "",
    local_model_path: str = "",
    live: bool = False,
    environment: Mapping[str, str] | None = None,
    allow_managed_root: bool = True,
    allow_hf_cache: bool = False,
) -> RealSmallTextModelSource:
    env = dict(os.environ if environment is None else environment)
    resolved_model_id = model_id.strip() or REAL_SMALL_TEXT_MODEL_ID
    warnings: list[str] = []

    if live:
        return RealSmallTextModelSource(
            model_id=resolved_model_id,
            live=True,
            local_model_path="",
            source_resolution_mode="explicit_live_hub",
        )

    if local_model_path.strip():
        return RealSmallTextModelSource(
            model_id=resolved_model_id,
            live=False,
            local_model_path=str(Path(local_model_path).expanduser().resolve()),
            source_resolution_mode="explicit_local_path",
        )

    configured_path = env.get(REAL_SMALL_TEXT_MODEL_PATH_ENV, "").strip()
    if configured_path:
        resolved_path = Path(configured_path).expanduser().resolve()
        if resolved_path.is_dir():
            return RealSmallTextModelSource(
                model_id=resolved_model_id,
                live=False,
                local_model_path=str(resolved_path),
                source_resolution_mode="env_local_path",
            )
        warnings.append(
            f"Ignored {REAL_SMALL_TEXT_MODEL_PATH_ENV} because it does not point to an existing directory: {resolved_path}"
        )

    if allow_managed_root:
        managed_path = _managed_huggingface_model_path(resolved_model_id, env)
        if managed_path is not None:
            return RealSmallTextModelSource(
                model_id=resolved_model_id,
                live=False,
                local_model_path=str(managed_path),
                source_resolution_mode="managed_model_path",
                warnings=tuple(warnings),
            )

    if allow_hf_cache:
        cached_path = _huggingface_cache_model_path(resolved_model_id, env)
        if cached_path is not None:
            warnings.extend(cached_path.warnings)
            return RealSmallTextModelSource(
                model_id=resolved_model_id,
                live=False,
                local_model_path=str(cached_path.path),
                source_resolution_mode="hf_cache_snapshot",
                warnings=tuple(warnings),
            )

    return RealSmallTextModelSource(
        model_id=resolved_model_id,
        live=True,
        local_model_path="",
        source_resolution_mode="env_invalid_hub_fallback" if warnings else "hub_fallback",
        warnings=tuple(warnings),
    )


def resolve_real_small_text_model_path(
    *,
    environment: Mapping[str, str] | None = None,
    allow_managed_root: bool = True,
    allow_hf_cache: bool = False,
) -> Path | None:
    source = resolve_real_small_text_model_source(
        environment=environment,
        allow_managed_root=allow_managed_root,
        allow_hf_cache=allow_hf_cache,
    )
    if not source.local_model_path:
        return None
    return Path(source.local_model_path)


def _managed_huggingface_model_path(model_id: str, environment: Mapping[str, str]) -> Path | None:
    managed_root = environment.get(_MANAGED_MODEL_ROOT_ENV, "").strip()
    if not managed_root:
        return None
    candidate = Path(managed_root).expanduser().resolve() / "huggingface" / Path(model_id) / "main"
    if candidate.is_dir():
        return candidate
    return None


def _huggingface_cache_model_path(
    model_id: str,
    environment: Mapping[str, str],
) -> _HuggingFaceCacheModelPath | None:
    cache_root = _huggingface_cache_root(environment)
    repo_cache = cache_root / f"models--{model_id.replace('/', '--')}"
    ref_path = repo_cache / "refs" / "main"
    if ref_path.is_file():
        revision = ref_path.read_text(encoding="utf-8").strip()
        snapshot = repo_cache / "snapshots" / revision
        if snapshot.is_dir():
            return _HuggingFaceCacheModelPath(path=snapshot.resolve())

    snapshots_root = repo_cache / "snapshots"
    if not snapshots_root.is_dir():
        return None
    snapshots = sorted(path for path in snapshots_root.iterdir() if path.is_dir())
    if not snapshots:
        return None
    fallback = snapshots[-1].resolve()
    return _HuggingFaceCacheModelPath(
        path=fallback,
        warnings=(
            "Hugging Face cache refs/main was unavailable for "
            f"{model_id}; using lexicographically last snapshot directory {fallback}.",
        ),
    )


def _huggingface_cache_root(environment: Mapping[str, str]) -> Path:
    explicit_cache = environment.get("HUGGINGFACE_HUB_CACHE", "").strip()
    if explicit_cache:
        return Path(explicit_cache).expanduser().resolve()
    hf_home = environment.get("HF_HOME", "").strip()
    if hf_home:
        return (Path(hf_home).expanduser().resolve() / "hub")
    return (Path.home() / ".cache" / "huggingface" / "hub").resolve()
