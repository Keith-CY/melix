#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from worker.runtime.tool_registry import (  # noqa: E402
    ToolSelectionInput,
    ToolRegistryError,
    built_in_tool_config,
    built_in_tool_registry,
    select_agentic_tools_for_turn,
)

_SELECTIONS: tuple[tuple[str, ...], ...] = (
    ("visit", "image_crop", "visit"),
    ("text_search", "image_search", "local_compute"),
    ("layout_parse", "visit"),
    ("image_crop",),
)


def _measure(iterations: int, sample_count: int) -> dict[str, float]:
    registry = built_in_tool_registry()
    full_selection = list(registry.names())
    elapsed_samples: list[float] = []
    full_list_self_samples: list[float] = []
    full_config_template_elapsed_samples: list[float] = []
    full_config_template_samples: list[float] = []
    raw_single_config_elapsed_samples: list[float] = []
    missing_selection_elapsed_samples: list[float] = []
    missing_selection_error_samples: list[float] = []
    selector_planning_elapsed_samples: list[float] = []
    selector_selected_schema_bytes_samples: list[float] = []
    current_capacity_planning_elapsed_samples: list[float] = []
    current_capacity_selected_schema_bytes_samples: list[float] = []
    always_only_planning_elapsed_samples: list[float] = []
    always_only_selected_schema_bytes_samples: list[float] = []
    checksum = 0

    for _ in range(sample_count):
        full_list_self_count = 0
        started = time.perf_counter()
        for index in range(iterations):
            if index % 5 == 0:
                selected = registry.select(full_selection)
                if selected is registry:
                    full_list_self_count += 1
            else:
                selected = registry.select(_SELECTIONS[index % len(_SELECTIONS)])
            checksum += len(selected.tools)
        elapsed_samples.append((time.perf_counter() - started) * 1000.0)
        full_list_self_samples.append(float(full_list_self_count))

        full_config_iterations = iterations // 5
        full_config_template_count = 0
        full_config_started = time.perf_counter()
        for _index in range(full_config_iterations):
            config = built_in_tool_config(full_selection)
            full_config_template_count += 1
            checksum += len(config.tools)
        full_config_template_elapsed_samples.append(
            (time.perf_counter() - full_config_started) * 1000.0
        )
        full_config_template_samples.append(float(full_config_template_count))

        raw_single_config_started = time.perf_counter()
        for _index in range(full_config_iterations):
            config = built_in_tool_config((" image_crop ",))
            checksum += len(config.tools)
        raw_single_config_elapsed_samples.append(
            (time.perf_counter() - raw_single_config_started) * 1000.0
        )

        missing_selection_started = time.perf_counter()
        missing_selection_count = 0
        for index in range(full_config_iterations):
            try:
                registry.select((f"missing_tool_{index}",))
            except ToolRegistryError:
                missing_selection_count += 1
        missing_selection_elapsed_samples.append(
            (time.perf_counter() - missing_selection_started) * 1000.0
        )
        missing_selection_error_samples.append(float(missing_selection_count))
        checksum += missing_selection_count

        selector_iterations = max(1, iterations // 10)
        selector_schema_bytes = 0
        selector_started = time.perf_counter()
        for index in range(selector_iterations):
            if index % 3 == 0:
                selection_result = select_agentic_tools_for_turn(
                    ToolSelectionInput(
                        current_user_turn="Search local evidence, then calculate the answer.",
                        vector_selected_tool_ids=("text_search",),
                        vector_available=True,
                        max_selected_tools=3,
                    )
                )
            elif index % 3 == 1:
                selection_result = select_agentic_tools_for_turn(
                    ToolSelectionInput(
                        current_user_turn="Open fixture://docs/provider-contract.",
                        vector_available=False,
                        max_selected_tools=4,
                    )
                )
            else:
                selection_result = select_agentic_tools_for_turn(
                    ToolSelectionInput(
                        current_user_turn="Use two results this time.",
                        recent_user_turns=("Search the local text evidence.",),
                        vector_available=False,
                        max_selected_tools=4,
                    )
                )
            selector_schema_bytes += int(selection_result.receipt["selected_schema_bytes"])
        selector_planning_elapsed_samples.append(
            (time.perf_counter() - selector_started) * 1000.0
        )
        selector_selected_schema_bytes_samples.append(
            float(selector_schema_bytes / selector_iterations)
        )
        checksum += selector_schema_bytes

        current_capacity_schema_bytes = 0
        current_capacity_started = time.perf_counter()
        for _index in range(selector_iterations):
            selection_result = select_agentic_tools_for_turn(
                ToolSelectionInput(
                    current_user_turn="Search the local text evidence.",
                    recent_user_turns=("Visit fixture://docs/provider-contract.",),
                    vector_available=False,
                    max_selected_tools=2,
                )
            )
            current_capacity_schema_bytes += int(selection_result.receipt["selected_schema_bytes"])
        current_capacity_planning_elapsed_samples.append(
            (time.perf_counter() - current_capacity_started) * 1000.0
        )
        current_capacity_selected_schema_bytes_samples.append(
            float(current_capacity_schema_bytes / selector_iterations)
        )
        checksum += current_capacity_schema_bytes

        always_only_schema_bytes = 0
        always_only_started = time.perf_counter()
        for _index in range(selector_iterations):
            selection_result = select_agentic_tools_for_turn(
                ToolSelectionInput(
                    current_user_turn="Search local evidence, crop the image, and visit fixture://docs/provider-contract.",
                    recent_user_turns=("Search the local text evidence.",),
                    vector_selected_tool_ids=("text_search", "visit", "image_crop"),
                    vector_available=True,
                    max_selected_tools=1,
                )
            )
            always_only_schema_bytes += int(selection_result.receipt["selected_schema_bytes"])
        always_only_planning_elapsed_samples.append(
            (time.perf_counter() - always_only_started) * 1000.0
        )
        always_only_selected_schema_bytes_samples.append(
            float(always_only_schema_bytes / selector_iterations)
        )
        checksum += always_only_schema_bytes

    return {
        "elapsed_ms_mean": statistics.fmean(elapsed_samples),
        "select_calls_mean": float(iterations),
        "full_list_self_hits_mean": statistics.fmean(full_list_self_samples),
        "full_config_template_elapsed_ms_mean": statistics.fmean(
            full_config_template_elapsed_samples
        ),
        "full_config_template_hits_mean": statistics.fmean(full_config_template_samples),
        "raw_single_config_elapsed_ms_mean": statistics.fmean(
            raw_single_config_elapsed_samples
        ),
        "missing_selection_elapsed_ms_mean": statistics.fmean(
            missing_selection_elapsed_samples
        ),
        "missing_selection_errors_mean": statistics.fmean(missing_selection_error_samples),
        "selector_planning_elapsed_ms_mean": statistics.fmean(selector_planning_elapsed_samples),
        "selector_selected_schema_bytes_mean": statistics.fmean(
            selector_selected_schema_bytes_samples
        ),
        "current_capacity_planning_elapsed_ms_mean": statistics.fmean(
            current_capacity_planning_elapsed_samples
        ),
        "current_capacity_selected_schema_bytes_mean": statistics.fmean(
            current_capacity_selected_schema_bytes_samples
        ),
        "always_only_planning_elapsed_ms_mean": statistics.fmean(
            always_only_planning_elapsed_samples
        ),
        "always_only_selected_schema_bytes_mean": statistics.fmean(
            always_only_selected_schema_bytes_samples
        ),
        "checksum": float(checksum),
        "iterations": float(iterations),
        "sample_count": float(sample_count),
        "selection_case_count": float(len(_SELECTIONS) + 1),
    }


def main() -> int:
    iterations = int(os.environ.get("MELIX_TOOL_REGISTRY_SELECT_ITERATIONS", "80000"))
    sample_count = int(os.environ.get("MELIX_TOOL_REGISTRY_SELECT_SAMPLES", "5"))
    print(json.dumps(_measure(iterations, sample_count), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
