from __future__ import annotations

from pathlib import Path
import re
from typing import Any


_CHECKPOINT_STEP_RE = re.compile(r"checkpoint-(\d+)")
_NUMERIC_TOKEN_RE = re.compile(r"\d+")
_CHECKPOINT_STEP_SORT_WIDTH = 10


def build_checkpoint_selection_receipt_fields(
    *,
    latest_checkpoint_path: str | Path,
    loss_best: Any = None,
    loss_final: Any = None,
) -> dict[str, object]:
    selected_checkpoint_path = _str_value(latest_checkpoint_path)
    checkpoint_step = checkpoint_step_from_path(selected_checkpoint_path)
    selected_checkpoint_loss_source = ""
    if selected_checkpoint_path:
        selected_checkpoint_loss_source = _checkpoint_loss_source(
            loss_best=loss_best,
            loss_final=loss_final,
        )
    return {
        "checkpoint_step": checkpoint_step,
        "checkpoint_sort_key": checkpoint_sort_key(
            checkpoint_step=checkpoint_step,
            selected_checkpoint_path=selected_checkpoint_path,
        ),
        "selected_checkpoint_path": selected_checkpoint_path,
        "selected_checkpoint_loss_source": selected_checkpoint_loss_source,
    }


def checkpoint_step_from_path(path: str | Path) -> int:
    path_text = _str_value(path)
    if not path_text:
        return 0
    path_parts = Path(path_text).parts
    for part in reversed(path_parts):
        part_stem = Path(part).stem
        if part_stem.startswith("checkpoint"):
            match = _CHECKPOINT_STEP_RE.search(part_stem)
            return int(match.group(1)) if match else -1
    filename_tokens = _NUMERIC_TOKEN_RE.findall(Path(path_text).stem)
    return int(filename_tokens[-1]) if filename_tokens else -1


def checkpoint_sort_key(
    *,
    checkpoint_step: int,
    selected_checkpoint_path: str,
) -> str:
    if not selected_checkpoint_path:
        return ""
    if checkpoint_step < 0:
        return "no_numeric_step"
    return f"{checkpoint_step:0{_CHECKPOINT_STEP_SORT_WIDTH}d}"


def _checkpoint_loss_source(*, loss_best: Any, loss_final: Any) -> str:
    if _optional_float(loss_best) is not None:
        return "loss_best"
    if _optional_float(loss_final) is not None:
        return "loss_final"
    return ""


def _optional_float(raw_value: Any) -> float | None:
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return None


def _str_value(raw_value: Any) -> str:
    return str(raw_value or "").strip()
