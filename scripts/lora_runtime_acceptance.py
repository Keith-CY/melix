#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services/mlx-worker-python"))

from packages.protocol.python.worker.v1 import common_pb2  # noqa: E402
from worker.model_ops.adapter_activation_pipeline import AdapterActivationPipeline  # noqa: E402
from worker.model_ops.lora_training_pipeline import LoRATrainingPipeline  # noqa: E402


DEFAULT_MODEL_ID = "unsloth/gemma-4-E4B-it-MLX-8bit"
DEFAULT_DATASET_ID = "top200.event-extraction.top20.v1"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _dialogue_prompt(row: dict[str, Any]) -> str:
    dialogue = row.get("dialogue", [])
    if isinstance(dialogue, list):
        dialogue_text = "\n".join(str(turn) for turn in dialogue)
    else:
        dialogue_text = str(dialogue)
    return (
        "Extract the structured events from the dialogue. "
        "Return only JSON with an events array.\n\n"
        f"Dialogue:\n{dialogue_text}"
    )


def build_dialogue_extraction_training_package(
    *,
    evaluation_dataset_root: Path,
    output_dir: Path,
    sample_limit: int,
) -> dict[str, Any]:
    manifest = _load_json(evaluation_dataset_root / "manifest.json")
    rows = _iter_jsonl(evaluation_dataset_root / "samples.jsonl")
    if sample_limit > 0:
        rows = rows[:sample_limit]
    if not rows:
        raise RuntimeError(f"No dialogue extraction rows found under {evaluation_dataset_root}")

    output_dir.mkdir(parents=True, exist_ok=True)
    samples_path = output_dir / "samples.jsonl"
    with samples_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            messages = [
                {
                    "role": "user",
                    "content": _dialogue_prompt(row),
                },
                {
                    "role": "assistant",
                    "content": json.dumps(
                        {"events": row.get("events", [])},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                },
            ]
            handle.write(json.dumps({"messages": messages}, ensure_ascii=False) + "\n")

    package_manifest = {
        "schema_version": "melix.training_dataset_package.v1",
        "dataset_id": f"{manifest.get('dataset_id', DEFAULT_DATASET_ID)}.lora-acceptance",
        "format": "chat_messages",
        "sample_count": len(rows),
        "version": str(manifest.get("version", "1")),
        "source_evaluation_dataset_id": manifest.get("dataset_id", ""),
        "source_evaluation_suite_id": manifest.get("suite_id", ""),
        "source_evaluation_manifest_path": str(evaluation_dataset_root / "manifest.json"),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(package_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return package_manifest


def run_acceptance(
    *,
    repo_root: Path,
    model_id: str,
    dataset_id: str,
    output_dir: Path,
    sample_limit: int,
    max_steps: int,
    skip_training: bool = False,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    dataset_root = repo_root / "services/mlx-worker-python/fixtures/evaluation" / dataset_id
    training_dataset_dir = output_dir / "training_dataset"
    training_manifest = build_dialogue_extraction_training_package(
        evaluation_dataset_root=dataset_root,
        output_dir=training_dataset_dir,
        sample_limit=sample_limit,
    )

    source_model = common_pb2.ModelSpec(
        model_id=model_id,
        model_path=model_id,
        model_kind="text",
        revision="main",
        quant_profile_id="8bit",
        max_context=2048,
    )
    source_model.ext["text_family_id"] = "gemma"
    source_model.ext["text_layer_count"] = "42"

    if skip_training:
        return {
            "ok": True,
            "skipped_training": True,
            "model_id": model_id,
            "dataset_id": dataset_id,
            "training_dataset_manifest_path": str(training_dataset_dir / "manifest.json"),
            "training_dataset_sample_count": training_manifest["sample_count"],
        }

    train_output_dir = output_dir / "train_lora"
    train_result = LoRATrainingPipeline().run(
        job_id="lora-runtime-acceptance-train",
        request_ext={
            "operation": "train_lora",
            "training_mode": "qlora",
            "adapter_name": "gemma4-dialogue-extraction-runtime-acceptance",
            "dataset_uri": str(training_dataset_dir),
            "max_steps": str(max_steps),
            "batch_size": "1",
            "epochs": "1",
            "rank": "4",
            "alpha": "8",
            "dropout": "0",
            "target_modules": "q_proj",
            "num_layers": "1",
            "max_seq_length": "1024",
            "gradient_checkpointing": "true",
            "response_only": "true",
            "mask_prompt": "true",
        },
        source_model=source_model,
        output_dir=train_output_dir,
        jobs_root=output_dir / "jobs",
    )

    activation_result = AdapterActivationPipeline().run(
        job_id="lora-runtime-acceptance-activate",
        request_ext={
            "artifact_path": str(train_result.manifest_path),
            "activation_mode": "adapter_backed_runtime",
            "derived_model_alias": "gemma4-dialogue-extraction-runtime-acceptance",
        },
        source_model=source_model,
        output_dir=output_dir / "activate_adapter",
    )

    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    evidence = {
        "ok": True,
        "skipped_training": False,
        "model_id": model_id,
        "dataset_id": dataset_id,
        "training_dataset_manifest_path": str(training_dataset_dir / "manifest.json"),
        "training_dataset_sample_count": training_manifest["sample_count"],
        "train_manifest_path": str(train_result.manifest_path),
        "activation_manifest_path": str(activation_result.manifest_path),
        "elapsed_ms": elapsed_ms,
        "train": {
            "training_mode": train_result.manifest.get("training_mode"),
            "quantization_mode": train_result.manifest.get("quantization_mode"),
            "quantized_base_detected": train_result.manifest.get("quantized_base_detected"),
            "quantized_base_kind": train_result.manifest.get("quantized_base_kind"),
            "qlora_compatibility_status": train_result.manifest.get("qlora_compatibility_status"),
            "quantized_target_module_guard": train_result.manifest.get("quantized_target_module_guard"),
            "training_backend": train_result.manifest.get("training_backend"),
            "training_duration_ms": train_result.manifest.get("training_duration_ms"),
            "tokens_seen": train_result.manifest.get("tokens_seen"),
            "adapter_set_hash": train_result.manifest.get("adapter_set_hash"),
        },
        "activation": {
            "activation_mode": activation_result.manifest.get("activation_mode"),
            "adapter_runtime_switch_mode": activation_result.manifest.get("adapter_runtime.switch_mode"),
            "adapter_runtime_sharing_policy": activation_result.manifest.get("adapter_runtime.sharing_policy"),
            "adapter_runtime_compatibility_status": activation_result.manifest.get(
                "adapter_runtime.compatibility_status"
            ),
            "adapter_runtime_base_reuse_key": activation_result.manifest.get(
                "adapter_runtime.base_reuse_key"
            ),
            "adapter_runtime_adapter_isolation_key": activation_result.manifest.get(
                "adapter_runtime.adapter_isolation_key"
            ),
            "qlora_compatibility_status": activation_result.manifest.get("qlora_compatibility_status"),
        },
    }
    evidence_path = output_dir / "lora-runtime-acceptance.json"
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    evidence["evidence_path"] = str(evidence_path)
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the real LoRA runtime acceptance workflow.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable evidence.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--dataset-id", default=DEFAULT_DATASET_ID)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / ".runtime" / "lora-runtime-acceptance",
    )
    parser.add_argument("--sample-limit", type=int, default=2)
    parser.add_argument("--max-steps", type=int, default=1)
    parser.add_argument(
        "--skip-training",
        action="store_true",
        help="Only materialize the dialogue-extraction training package.",
    )
    args = parser.parse_args()

    payload = run_acceptance(
        repo_root=args.repo_root,
        model_id=args.model_id,
        dataset_id=args.dataset_id,
        output_dir=args.output_dir,
        sample_limit=args.sample_limit,
        max_steps=args.max_steps,
        skip_training=args.skip_training,
    )
    if args.json:
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print("LoRA runtime acceptance completed.")
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
