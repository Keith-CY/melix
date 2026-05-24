#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import omlx_melix_compare_benchmark as base


ENDPOINT_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
DEFAULT_RUN_ROOT = Path(".runtime/three-way-gemma31b128k")


def parse_endpoint_headers(values: Iterable[str]) -> dict[str, dict[str, str]]:
    grouped: dict[str, dict[str, str]] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"Endpoint header must use '<endpoint>=Name: value' format: {value}")
        endpoint_name, header_value = value.split("=", 1)
        endpoint_name = endpoint_name.strip()
        _validate_endpoint_name(endpoint_name)
        grouped.setdefault(endpoint_name, {}).update(base.parse_header_values([header_value]))
    return grouped


def parse_endpoint_spec(spec: str, *, headers: dict[str, str]) -> base.EndpointConfig:
    if "=" not in spec or "::" not in spec:
        raise ValueError(f"Endpoint must use '<name>=<base-url>::<model>' format: {spec}")
    name, rest = spec.split("=", 1)
    name = name.strip()
    _validate_endpoint_name(name)
    base_url, model = rest.split("::", 1)
    base_url = base_url.strip()
    model = model.strip()
    if not base_url:
        raise ValueError(f"Endpoint base URL is empty: {spec}")
    if not model:
        raise ValueError(f"Endpoint model is empty: {spec}")
    return base.EndpointConfig(
        name=name,
        base_url=base.normalize_base_url(base_url),
        model=model,
        headers=headers,
    )


def _validate_endpoint_name(name: str) -> None:
    if not name or ENDPOINT_NAME_RE.fullmatch(name) is None:
        raise ValueError("endpoint name may only contain letters, numbers, underscores, and hyphens")


def peer_comparisons(
    summaries: list[base.ScenarioSummary],
    *,
    target_endpoint: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[tuple[int, int, int, str, str], list[base.ScenarioSummary]] = {}
    for summary in summaries:
        key = (
            summary.prompt_token_target,
            summary.max_tokens,
            summary.concurrency,
            summary.cache_profile,
            summary.prompt_style,
        )
        grouped.setdefault(key, []).append(summary)

    comparisons: list[dict[str, Any]] = []
    hints: list[dict[str, Any]] = []
    for key, rows in sorted(grouped.items()):
        rows_by_endpoint = {row.endpoint: row for row in rows}
        target = rows_by_endpoint.get(target_endpoint)
        if target is None:
            continue
        prompt_token_target, max_tokens, concurrency, cache_profile, prompt_style = key
        scenario = {
            "prompt_token_target": prompt_token_target,
            "max_tokens": max_tokens,
            "concurrency": concurrency,
            "cache_profile": cache_profile,
            "prompt_style": prompt_style,
        }
        winners = _scenario_winners(rows)
        comparisons.append({
            "scenario": scenario,
            "winners": winners,
            "endpoints": {
                row.endpoint: {
                    "error_count": row.error_count,
                    "median_ttft_ms": row.median_ttft_ms,
                    "median_total_ms": row.median_total_ms,
                    "median_decode_tokens_per_second": row.median_decode_tokens_per_second,
                    "median_aggregate_output_tokens_per_second": row.median_aggregate_output_tokens_per_second,
                }
                for row in rows
            },
        })
        if target.error_count:
            hints.append({
                "scenario": scenario,
                "area": "reliability",
                "severity": "high",
                "message": f"{target_endpoint} returned errors in this scenario.",
                "target_error_count": target.error_count,
            })
            continue
        best_latency_peer = _best_peer(rows, target_endpoint, "median_ttft_ms", lower_is_better=True)
        if best_latency_peer and _latency_gap(target.median_ttft_ms, best_latency_peer.median_ttft_ms):
            hints.append(_hint(
                scenario,
                area="ttft",
                message="Melix median TTFT is slower than the best peer; inspect request shaping, queue wait, prompt rendering, and prefill.",
                best_peer=best_latency_peer,
                target_value=target.median_ttft_ms,
                peer_value=best_latency_peer.median_ttft_ms,
            ))
        best_total_peer = _best_peer(rows, target_endpoint, "median_total_ms", lower_is_better=True)
        if best_total_peer and _latency_gap(target.median_total_ms, best_total_peer.median_total_ms):
            hints.append(_hint(
                scenario,
                area="end_to_end_latency",
                message="Melix median total latency is slower than the best peer; inspect stream assembly and lifecycle overhead.",
                best_peer=best_total_peer,
                target_value=target.median_total_ms,
                peer_value=best_total_peer.median_total_ms,
            ))
        best_decode_peer = _best_peer(
            rows,
            target_endpoint,
            "median_decode_tokens_per_second",
            lower_is_better=False,
        )
        if best_decode_peer and _throughput_gap(
            target.median_decode_tokens_per_second,
            best_decode_peer.median_decode_tokens_per_second,
        ):
            hints.append(_hint(
                scenario,
                area="decode_throughput",
                message="Melix median decode throughput is lower than the best peer; inspect worker decode loop, KV settings, and token streaming cadence.",
                best_peer=best_decode_peer,
                target_value=target.median_decode_tokens_per_second,
                peer_value=best_decode_peer.median_decode_tokens_per_second,
            ))
        best_aggregate_peer = _best_peer(
            rows,
            target_endpoint,
            "median_aggregate_output_tokens_per_second",
            lower_is_better=False,
        )
        if concurrency > 1 and best_aggregate_peer and _throughput_gap(
            target.median_aggregate_output_tokens_per_second,
            best_aggregate_peer.median_aggregate_output_tokens_per_second,
        ):
            hints.append(_hint(
                scenario,
                area="concurrency_aggregate_throughput",
                message="Melix aggregate throughput is lower under concurrency; inspect scheduler admission and continuous batching.",
                best_peer=best_aggregate_peer,
                target_value=target.median_aggregate_output_tokens_per_second,
                peer_value=best_aggregate_peer.median_aggregate_output_tokens_per_second,
            ))
    return comparisons, hints


def _scenario_winners(rows: list[base.ScenarioSummary]) -> dict[str, str | None]:
    return {
        "median_ttft_ms": _winner(rows, "median_ttft_ms", lower_is_better=True),
        "median_total_ms": _winner(rows, "median_total_ms", lower_is_better=True),
        "median_decode_tokens_per_second": _winner(
            rows,
            "median_decode_tokens_per_second",
            lower_is_better=False,
        ),
        "median_aggregate_output_tokens_per_second": _winner(
            rows,
            "median_aggregate_output_tokens_per_second",
            lower_is_better=False,
        ),
    }


def _winner(
    rows: list[base.ScenarioSummary],
    metric: str,
    *,
    lower_is_better: bool,
) -> str | None:
    clean = [row for row in rows if getattr(row, metric) is not None and row.error_count == 0]
    if not clean:
        return None
    winner = (
        min(clean, key=lambda row: getattr(row, metric))
        if lower_is_better
        else max(clean, key=lambda row: getattr(row, metric))
    )
    return winner.endpoint


def _best_peer(
    rows: list[base.ScenarioSummary],
    target_endpoint: str,
    metric: str,
    *,
    lower_is_better: bool,
) -> base.ScenarioSummary | None:
    clean = [
        row for row in rows
        if row.endpoint != target_endpoint and row.error_count == 0 and getattr(row, metric) is not None
    ]
    if not clean:
        return None
    return min(clean, key=lambda row: getattr(row, metric)) if lower_is_better else max(clean, key=lambda row: getattr(row, metric))


def _latency_gap(target_value: float | None, peer_value: float | None) -> bool:
    if target_value is None or peer_value is None:
        return False
    return target_value > peer_value * 1.03 and (target_value - peer_value) > 25.0


def _throughput_gap(target_value: float | None, peer_value: float | None) -> bool:
    if target_value is None or peer_value is None or peer_value <= 0:
        return False
    return target_value < peer_value * 0.97


def _hint(
    scenario: dict[str, Any],
    *,
    area: str,
    message: str,
    best_peer: base.ScenarioSummary,
    target_value: float | None,
    peer_value: float | None,
) -> dict[str, Any]:
    return {
        "scenario": scenario,
        "area": area,
        "severity": "high" if scenario["prompt_token_target"] >= 131072 else "medium",
        "message": message,
        "best_peer": best_peer.endpoint,
        "target_value": target_value,
        "best_peer_value": peer_value,
    }


def runtime_base_url(openai_base_url: str) -> str:
    """Return the service root for a /v1 OpenAI-compatible endpoint."""
    parsed = urllib.parse.urlsplit(base.normalize_base_url(openai_base_url))
    path = parsed.path.rstrip("/")
    if path == "/v1":
        path = ""
    elif path.endswith("/v1"):
        path = path[:-3].rstrip("/")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def request_optional_json(base_url: str, path: str, *, headers: dict[str, str], timeout_seconds: float) -> dict[str, Any]:
    url = base.endpoint_url(base_url, path)
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
            payload = json.loads(body) if body else {}
            return {"ok": True, "status_code": int(response.status), "url": url, "payload": payload}
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "status_code": int(exc.code),
            "url": url,
            "payload": base._decode_json_body(exc.read()),
        }
    except Exception as exc:
        return {"ok": False, "status_code": 0, "url": url, "error": f"{type(exc).__name__}: {exc}"}


def capture_runtime_snapshots(
    endpoints: list[base.EndpointConfig],
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    snapshots: dict[str, Any] = {}
    for endpoint in endpoints:
        service_root = runtime_base_url(endpoint.base_url)
        snapshots[endpoint.name] = {
            "openai_base_url": endpoint.base_url,
            "service_root_url": service_root,
            "health": request_optional_json(
                service_root,
                "/health",
                headers=endpoint.headers,
                timeout_seconds=timeout_seconds,
            ),
            "metrics": request_optional_json(
                service_root,
                "/metrics",
                headers=endpoint.headers,
                timeout_seconds=timeout_seconds,
            ),
        }
    return snapshots


def prompt_token_evidence(observations: list[base.RequestObservation]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, int, int, int, str, str], list[base.RequestObservation]] = {}
    for observation in observations:
        key = (
            observation.endpoint,
            observation.prompt_token_target,
            observation.max_tokens,
            observation.concurrency,
            observation.cache_profile,
            observation.prompt_style,
        )
        grouped.setdefault(key, []).append(observation)

    evidence: list[dict[str, Any]] = []
    for key, rows in sorted(grouped.items()):
        endpoint, prompt_token_target, max_tokens, concurrency, cache_profile, prompt_style = key
        successes = [row for row in rows if row.status == "ok"]
        prompt_tokens = [row.prompt_tokens for row in successes]
        evidence.append({
            "endpoint": endpoint,
            "prompt_token_target": prompt_token_target,
            "max_tokens": max_tokens,
            "concurrency": concurrency,
            "cache_profile": cache_profile,
            "prompt_style": prompt_style,
            "request_count": len(rows),
            "success_count": len(successes),
            "prompt_token_sources": sorted({row.prompt_token_source for row in successes}),
            "min_prompt_tokens": min(prompt_tokens) if prompt_tokens else None,
            "median_prompt_tokens": base.median(prompt_tokens),
            "max_prompt_tokens": max(prompt_tokens) if prompt_tokens else None,
        })
    return evidence


def run_comparison(args: argparse.Namespace) -> dict[str, Any]:
    header_groups = parse_endpoint_headers(args.endpoint_header)
    endpoints = [
        parse_endpoint_spec(spec, headers=header_groups.get(spec.split("=", 1)[0].strip(), {}))
        for spec in args.endpoint
    ]
    scenarios = base.build_scenarios(
        prompt_token_targets=args.prompt_token_targets,
        max_tokens=args.max_tokens,
        concurrency_values=args.concurrency,
        cache_profile=args.cache_profile,
        prompt_style=args.prompt_style,
        repeats=args.repeats,
    )
    run_id = args.run_id or datetime.now(timezone.utc).strftime("three-way-gemma31b128k-%Y%m%d-%H%M%S")
    staging_dir = args.staging_root.expanduser() / run_id
    measurement_profile = base.measurement_profile_metadata(
        requested_profile=args.measurement_profile,
        warmup_requests=args.warmup_requests,
        operator_note=args.measurement_profile_note,
    )

    if args.dry_run:
        preflight = [
            {
                "endpoint": endpoint.name,
                "base_url": endpoint.base_url,
                "status_code": "dry-run",
                "ok": None,
                "model": endpoint.model,
                "model_listed": None,
                "model_count": 0,
                "models": [],
                "error": None,
                "attempt_count": 0,
                "elapsed_seconds": 0.0,
            }
            for endpoint in endpoints
        ]
        runtime_snapshots: dict[str, Any] = {}
        warmups: list[base.RequestObservation] = []
        observations: list[base.RequestObservation] = []
    else:
        preflight = base.preflight_endpoints(
            endpoints,
            timeout_seconds=args.preflight_timeout_seconds,
            wait_seconds=args.preflight_wait_seconds,
            retry_interval_seconds=args.preflight_retry_interval_seconds,
        )
        runtime_snapshots = capture_runtime_snapshots(
            endpoints,
            timeout_seconds=args.preflight_timeout_seconds,
        )
        failed = [item for item in preflight if item["ok"] is not True]
        if failed and not args.allow_failed_preflight:
            raise RuntimeError(
                "Endpoint preflight failed; rerun with --allow-failed-preflight to collect failure observations. "
                + json.dumps(failed, sort_keys=True)
            )
        if args.preflight_only:
            warmups = []
            observations = []
        else:
            warmups = base.run_warmups(
                endpoints,
                request_count=args.warmup_requests,
                prompt_token_target=args.warmup_prompt_token_target,
                max_tokens=args.warmup_max_tokens,
                prompt_style=args.prompt_style,
                include_usage=args.include_usage,
                temperature=args.temperature,
                timeout_seconds=args.timeout_seconds,
            )
            observations = []
            for scenario in scenarios:
                for endpoint in endpoints:
                    observations.extend(
                        base.run_group(
                            endpoint,
                            scenario,
                            include_usage=args.include_usage,
                            temperature=args.temperature,
                            timeout_seconds=args.timeout_seconds,
                        )
                    )

    metrics_snapshot = base.load_melix_metrics_snapshot(
        control_plane_path=args.melix_control_plane_metrics,
        swift_text_worker_path=args.melix_swift_text_worker_metrics,
    )
    summaries = base.summarize_observations(observations)
    prompt_evidence = prompt_token_evidence(observations)
    comparisons, peer_hints = peer_comparisons(summaries, target_endpoint=args.target_endpoint)
    hints = base.enrich_hints_with_metrics(peer_hints, metrics_snapshot)
    warmup_settings = {
        "request_count_per_endpoint": args.warmup_requests,
        "prompt_token_target": args.warmup_prompt_token_target,
        "max_tokens": args.warmup_max_tokens,
        "prompt_style": args.prompt_style,
    }
    artifact_paths = write_artifacts(
        staging_dir=staging_dir,
        endpoints=endpoints,
        scenarios=scenarios,
        preflight=preflight,
        runtime_snapshots=runtime_snapshots,
        warmups=warmups,
        warmup_settings=warmup_settings,
        metrics_snapshot=metrics_snapshot,
        observations=observations,
        summaries=summaries,
        prompt_evidence=prompt_evidence,
        comparisons=comparisons,
        hints=hints,
        dry_run=args.dry_run,
        target_endpoint=args.target_endpoint,
        measurement_profile=measurement_profile,
    )
    exported_to = None if args.no_export else export_bundle(staging_dir, args.export_dir)
    return {
        "run_id": run_id,
        "staging_dir": str(staging_dir),
        "exported_to": str(exported_to) if exported_to else None,
        "endpoint_count": len(endpoints),
        "preflight": preflight,
        "scenario_count": len(scenarios),
        "warmup_count": len(warmups),
        "measurement_profile": measurement_profile["profile"],
        "observation_count": len(observations),
        "summary_count": len(summaries),
        "comparison_count": len(comparisons),
        "optimization_hint_count": len(hints),
        "artifacts": artifact_paths,
    }


def write_artifacts(
    *,
    staging_dir: Path,
    endpoints: list[base.EndpointConfig],
    scenarios: list[base.BenchmarkScenario],
    preflight: list[dict[str, Any]],
    runtime_snapshots: dict[str, Any],
    warmups: list[base.RequestObservation],
    warmup_settings: dict[str, Any],
    metrics_snapshot: dict[str, Any] | None,
    observations: list[base.RequestObservation],
    summaries: list[base.ScenarioSummary],
    prompt_evidence: list[dict[str, Any]],
    comparisons: list[dict[str, Any]],
    hints: list[dict[str, Any]],
    dry_run: bool,
    target_endpoint: str,
    measurement_profile: dict[str, Any],
) -> dict[str, str]:
    staging_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()
    paths = {
        "manifest": staging_dir / "manifest.json",
        "observations": staging_dir / "observations.jsonl",
        "summary_json": staging_dir / "summary.json",
        "summary_csv": staging_dir / "summary.csv",
        "summary_markdown": staging_dir / "summary.md",
        "runtime_snapshots": staging_dir / "runtime-snapshots.json",
    }
    if warmups:
        paths["warmups"] = staging_dir / "warmups.jsonl"
    if metrics_snapshot is not None:
        paths["melix_metrics"] = staging_dir / "melix-metrics.json"

    manifest = {
        "schema_version": 1,
        "generated_at": generated_at,
        "dry_run": dry_run,
        "target_endpoint": target_endpoint,
        "measurement_profile": measurement_profile,
        "endpoints": [
            {
                "name": endpoint.name,
                "base_url": endpoint.base_url,
                "model": endpoint.model,
                "header_names": sorted(endpoint.headers.keys()),
            }
            for endpoint in endpoints
        ],
        "scenario_count": len(scenarios),
        "scenario_settings": {
            "prompt_style": scenarios[0].prompt_style if scenarios else None,
        },
        "warmup_count": len(warmups),
        "warmup_settings": warmup_settings,
        "observation_count": len(observations),
        "preflight": preflight,
        "artifacts": {key: path.name for key, path in paths.items()},
    }
    paths["manifest"].write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    paths["runtime_snapshots"].write_text(
        json.dumps(runtime_snapshots, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if metrics_snapshot is not None:
        paths["melix_metrics"].write_text(
            json.dumps(metrics_snapshot, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if warmups:
        with paths["warmups"].open("w", encoding="utf-8") as handle:
            for observation in warmups:
                handle.write(json.dumps(asdict(observation), sort_keys=True) + "\n")
    with paths["observations"].open("w", encoding="utf-8") as handle:
        for observation in observations:
            handle.write(json.dumps(asdict(observation), sort_keys=True) + "\n")
    summary_payload = {
        "schema_version": 1,
        "generated_at": generated_at,
        "target_endpoint": target_endpoint,
        "measurement_profile": measurement_profile,
        "runtime_snapshots": runtime_snapshots,
        "melix_metrics_snapshot": metrics_snapshot,
        "warmups": [asdict(observation) for observation in warmups],
        "prompt_token_evidence": prompt_evidence,
        "summaries": [asdict(summary) for summary in summaries],
        "peer_comparisons": comparisons,
        "optimization_hints": hints,
    }
    paths["summary_json"].write_text(
        json.dumps(summary_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    base.write_summary_csv(paths["summary_csv"], summaries)
    paths["summary_markdown"].write_text(
        render_markdown_summary(
            summaries,
            comparisons,
            hints,
            preflight=preflight,
            runtime_snapshots=runtime_snapshots,
            prompt_evidence=prompt_evidence,
            warmups=warmups,
            metrics_snapshot=metrics_snapshot,
            dry_run=dry_run,
            target_endpoint=target_endpoint,
            measurement_profile=measurement_profile,
        ),
        encoding="utf-8",
    )
    return {key: str(path) for key, path in paths.items()}


def render_markdown_summary(
    summaries: list[base.ScenarioSummary],
    comparisons: list[dict[str, Any]],
    hints: list[dict[str, Any]],
    *,
    preflight: list[dict[str, Any]],
    runtime_snapshots: dict[str, Any],
    prompt_evidence: list[dict[str, Any]],
    warmups: list[base.RequestObservation],
    metrics_snapshot: dict[str, Any] | None,
    dry_run: bool,
    target_endpoint: str,
    measurement_profile: dict[str, Any],
) -> str:
    lines = ["# Three-Way Gemma 4 31B 128K Serving Comparison", ""]
    lines.append(f"- Dry run: `{str(dry_run).lower()}`")
    lines.append(f"- Target endpoint: `{target_endpoint}`")
    lines.append(f"- Measurement profile: `{measurement_profile.get('profile', 'unknown')}`")
    if measurement_profile.get("operator_note"):
        lines.append(f"- Measurement note: {measurement_profile['operator_note']}")
    lines.append("")
    lines.append("## Preflight")
    lines.append("")
    lines.append("| Endpoint | Status | Model | Model Listed | Model Count |")
    lines.append("|---|---:|---|---:|---:|")
    for item in preflight:
        lines.append(
            "| {endpoint} | {status_code} | `{model}` | {model_listed} | {model_count} |".format(
                endpoint=item.get("endpoint", ""),
                status_code=item.get("status_code", "n/a"),
                model=item.get("model", ""),
                model_listed=item.get("model_listed", "n/a"),
                model_count=item.get("model_count", 0),
            )
        )
    lines.append("")
    lines.append("## Scenario Summary")
    lines.append("")
    lines.append(
        "| Endpoint | Prompt Target | Style | Prompt Source | Completion Source | Max Tokens | "
        "Concurrency | Errors | Median TTFT ms | Median Total ms | Median Decode tok/s | "
        "Median Aggregate tok/s |"
    )
    lines.append("|---|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for summary in summaries:
        lines.append(
            "| {endpoint} | {prompt} | {style} | {prompt_source} | {completion_source} | {max_tokens} | {concurrency} | {errors} | {ttft} | {total} | {decode} | {aggregate} |".format(
                endpoint=summary.endpoint,
                prompt=summary.prompt_token_target,
                style=summary.prompt_style,
                prompt_source=summary.prompt_token_sources,
                completion_source=summary.completion_token_sources,
                max_tokens=summary.max_tokens,
                concurrency=summary.concurrency,
                errors=summary.error_count,
                ttft=base._fmt(summary.median_ttft_ms),
                total=base._fmt(summary.median_total_ms),
                decode=base._fmt(summary.median_decode_tokens_per_second),
                aggregate=base._fmt(summary.median_aggregate_output_tokens_per_second),
            )
        )
    lines.append("")
    lines.append("## Prompt Token Evidence")
    lines.append("")
    if prompt_evidence:
        lines.append("| Endpoint | Prompt Target | Style | Max Tokens | Concurrency | Source | Min | Median | Max |")
        lines.append("|---|---:|---|---:|---:|---|---:|---:|---:|")
        for item in prompt_evidence:
            lines.append(
                "| {endpoint} | {target} | {style} | {max_tokens} | {concurrency} | {source} | {minimum} | {median} | {maximum} |".format(
                    endpoint=item.get("endpoint", ""),
                    target=item.get("prompt_token_target", ""),
                    style=item.get("prompt_style", ""),
                    max_tokens=item.get("max_tokens", ""),
                    concurrency=item.get("concurrency", ""),
                    source=",".join(item.get("prompt_token_sources", [])),
                    minimum=base._fmt(item.get("min_prompt_tokens")),
                    median=base._fmt(item.get("median_prompt_tokens")),
                    maximum=base._fmt(item.get("max_prompt_tokens")),
                )
            )
    else:
        lines.append("No prompt token evidence was collected.")
    lines.append("")
    lines.append("## Peer Winners")
    lines.append("")
    if comparisons:
        lines.append("| Scenario | TTFT | Total | Decode tok/s | Aggregate tok/s |")
        lines.append("|---|---|---|---|---|")
        for comparison in comparisons:
            scenario = comparison["scenario"]
            winners = comparison["winners"]
            lines.append(
                "| pt={prompt} out={out} c={concurrency} | {ttft} | {total} | {decode} | {aggregate} |".format(
                    prompt=scenario["prompt_token_target"],
                    out=scenario["max_tokens"],
                    concurrency=scenario["concurrency"],
                    ttft=winners.get("median_ttft_ms") or "n/a",
                    total=winners.get("median_total_ms") or "n/a",
                    decode=winners.get("median_decode_tokens_per_second") or "n/a",
                    aggregate=winners.get("median_aggregate_output_tokens_per_second") or "n/a",
                )
            )
    else:
        lines.append("No peer comparison rows were generated.")
    lines.append("")
    lines.append("## Runtime Snapshots")
    lines.append("")
    if runtime_snapshots:
        lines.append("| Endpoint | Health | Metrics |")
        lines.append("|---|---:|---:|")
        for endpoint, snapshot in sorted(runtime_snapshots.items()):
            health = snapshot.get("health", {}) if isinstance(snapshot, dict) else {}
            metrics = snapshot.get("metrics", {}) if isinstance(snapshot, dict) else {}
            lines.append(
                f"| {endpoint} | {health.get('status_code', 'n/a')} | {metrics.get('status_code', 'n/a')} |"
            )
    else:
        lines.append("No runtime snapshots were captured.")
    lines.append("")
    if metrics_snapshot is not None:
        lines.append("## Melix Metrics Snapshot")
        lines.append("")
        if metrics_snapshot.get("ok") is True:
            values = metrics_snapshot.get("values", {})
            lines.append("| Metric | Value |")
            lines.append("|---|---:|")
            for key in (
                "scheduler.multimodal_continuous_batch_enabled",
                "scheduler.multimodal_continuous_batch_requested_capacity",
                "scheduler.multimodal_continuous_batch_effective_capacity",
                "scheduler.multimodal_continuous_batch_blocked_count",
                "scheduler.multimodal_continuous_batch_blocked_reason_code",
                "scheduler.continuous_batch_size",
                "control_plane.text_first_load_ms",
                "control_plane.text_first_load_estimated_resident_bytes",
                "control_plane.text_first_load_resident_bytes",
                "swift_text.prefill_ms",
                "swift_text.prefill_prompt_tokens",
                "swift_text.decode_ttft_ms",
                "swift_text.decode_ms",
                "swift_text.decode_tokens_per_second",
                "vision.text_batch_generator.peak_active_batch_size",
                "vision.text_batch_generator.queue_wait_ms_total",
                "vision.text_batch_generator.executor_step_ms_total",
                "http.ttfd_ms",
            ):
                lines.append(f"| `{key}` | {base._fmt_metric(values.get(key) if isinstance(values, dict) else None)} |")
        else:
            lines.append(f"Metrics snapshot unavailable: `{metrics_snapshot.get('error', 'unknown')}`")
        lines.append("")
    lines.append("## Optimization Hints")
    lines.append("")
    if hints:
        for hint in hints:
            lines.append(
                "- `{area}` {message} scenario={scenario}".format(
                    area=hint.get("area", "unknown"),
                    message=hint.get("message", ""),
                    scenario=json.dumps(hint.get("scenario", {}), sort_keys=True),
                )
            )
    else:
        lines.append("No target endpoint bottleneck hints were generated.")
    lines.append("")
    return "\n".join(lines)


def export_bundle(staging_dir: Path, export_dir: Path | None) -> Path | None:
    if export_dir is None:
        return None
    export_dir = export_dir.expanduser()
    export_dir.mkdir(parents=True, exist_ok=True)
    destination = export_dir / staging_dir.name
    if destination.exists():
        suffix = datetime.now(timezone.utc).strftime("%H%M%S")
        destination = export_dir / f"{staging_dir.name}-{suffix}"
    shutil.copytree(staging_dir, destination)
    return destination


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare three or more OpenAI-compatible streaming serving endpoints.",
    )
    parser.add_argument(
        "--endpoint",
        action="append",
        default=[],
        help="Endpoint spec '<name>=<base-url>::<model>'. Repeat for Melix, OMLX, SwiftLM.",
    )
    parser.add_argument(
        "--endpoint-header",
        action="append",
        default=[],
        help="Endpoint-scoped header '<endpoint>=Name: value'. Repeat as needed.",
    )
    parser.add_argument("--target-endpoint", default="melix")
    parser.add_argument(
        "--prompt-token-targets",
        type=int,
        nargs="+",
        default=[8192, 32768, 131072],
    )
    parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--warmup-requests", type=int, default=0)
    parser.add_argument("--warmup-prompt-token-target", type=int, default=1024)
    parser.add_argument("--warmup-max-tokens", type=int, default=16)
    parser.add_argument("--concurrency", type=int, nargs="+", default=[1])
    parser.add_argument("--cache-profile", choices=["cold_unique", "repeated"], default="cold_unique")
    parser.add_argument("--prompt-style", choices=base.PROMPT_STYLES, default="concise")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--include-usage", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=3600.0)
    parser.add_argument("--preflight-timeout-seconds", type=float, default=10.0)
    parser.add_argument("--preflight-wait-seconds", type=float, default=0.0)
    parser.add_argument("--preflight-retry-interval-seconds", type=float, default=2.0)
    parser.add_argument("--melix-control-plane-metrics", type=Path, default=None)
    parser.add_argument("--melix-swift-text-worker-metrics", type=Path, default=None)
    parser.add_argument(
        "--measurement-profile",
        choices=base.MEASUREMENT_PROFILES,
        default="auto",
        help="Label measured scenarios as cold, warm, or mixed. 'auto' uses warm when warmups are run, otherwise cold.",
    )
    parser.add_argument(
        "--measurement-profile-note",
        default="",
        help="Optional note describing how endpoint residency was prepared before measurement.",
    )
    parser.add_argument("--allow-failed-preflight", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--staging-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--export-dir", type=Path, default=Path("~/Downloads"))
    parser.add_argument("--no-export", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if len(args.endpoint) < 2:
        raise ValueError("Pass at least two --endpoint values.")
    endpoint_names = [spec.split("=", 1)[0].strip() for spec in args.endpoint if "=" in spec]
    if len(endpoint_names) != len(set(endpoint_names)):
        raise ValueError("Endpoint names must be unique.")
    if args.target_endpoint not in endpoint_names:
        raise ValueError("--target-endpoint must match one endpoint name.")
    if args.repeats < 1:
        raise ValueError("--repeats must be at least 1")
    if args.max_tokens < 1:
        raise ValueError("--max-tokens must be at least 1")
    if args.warmup_requests < 0:
        raise ValueError("--warmup-requests must be at least 0")
    if args.warmup_prompt_token_target < 1:
        raise ValueError("--warmup-prompt-token-target must be positive")
    if args.warmup_max_tokens < 1:
        raise ValueError("--warmup-max-tokens must be at least 1")
    if any(value < 1 for value in args.prompt_token_targets):
        raise ValueError("--prompt-token-targets values must be positive")
    if any(value < 1 for value in args.concurrency):
        raise ValueError("--concurrency values must be positive")
    if args.timeout_seconds <= 0 or args.preflight_timeout_seconds <= 0:
        raise ValueError("Timeout values must be positive")
    if args.preflight_wait_seconds < 0:
        raise ValueError("--preflight-wait-seconds must be at least 0")
    if args.preflight_retry_interval_seconds <= 0:
        raise ValueError("--preflight-retry-interval-seconds must be positive")


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        validate_args(args)
        started_at = time.perf_counter()
        result = run_comparison(args)
        result["elapsed_seconds"] = round(time.perf_counter() - started_at, 3)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        json.dump(result, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print(f"Run id: {result['run_id']}")
        print(f"Staging dir: {result['staging_dir']}")
        if result["exported_to"]:
            print(f"Exported to: {result['exported_to']}")
        print(f"Endpoints: {result['endpoint_count']}")
        print(f"Scenarios: {result['scenario_count']}")
        print(f"Observations: {result['observation_count']}")
        print(f"Optimization hints: {result['optimization_hint_count']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
