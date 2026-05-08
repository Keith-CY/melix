from __future__ import annotations

import base64
import json
import sys

from packages.protocol.python.worker.v1 import common_pb2, inference_pb2, maintenance_pb2

from worker import control_plane_bridge


class FakeChannel:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeInferenceStub:
    def __init__(self) -> None:
        self.last_image_generate_timeout = None
        self.last_image_edit_timeout = None

    def Embed(self, request):
        return inference_pb2.EmbedResponse(
            embeddings=[
                inference_pb2.Embedding(values=[0.1, 0.2]),
                inference_pb2.Embedding(values=[0.3, 0.4]),
            ]
        )

    def Rerank(self, request):
        return inference_pb2.RerankResponse(
            items=[
                inference_pb2.RerankItem(index=1, score=0.9),
                inference_pb2.RerankItem(index=0, score=0.7),
            ]
        )

    def Transcribe(self, request):
        return inference_pb2.TranscribeResponse(
            text=request.audio_bytes.decode("utf-8"),
            language=request.language or "und",
            duration_seconds=0.25,
        )

    def Speak(self, request):
        return inference_pb2.SpeakResponse(
            audio_bytes=f"VOICE={request.voice or 'default'}\nFORMAT={request.format or 'wav'}\nTEXT={request.input}".encode(
                "utf-8"
            ),
            format=request.format or "wav",
        )

    def ImageGenerate(self, request, timeout=None):
        self.last_image_generate_timeout = timeout
        return inference_pb2.ImageGenerateResponse(
            images=[b"generated-image"],
            job=inference_pb2.ImageJobDescriptor(
                request_id=request.id.request_id,
                job_id=f"{request.id.request_id}::image-generate",
                model_handle=request.model_handle,
                operation="image_generate",
                state=common_pb2.IMAGE_JOB_COMPLETED,
            ),
        )

    def ImageEdit(self, request, timeout=None):
        self.last_image_edit_timeout = timeout
        return inference_pb2.ImageEditResponse(
            images=[b"edited-image"],
            job=inference_pb2.ImageJobDescriptor(
                request_id=request.id.request_id,
                job_id=f"{request.id.request_id}::image-edit",
                model_handle=request.model_handle,
                operation="image_edit",
                state=common_pb2.IMAGE_JOB_COMPLETED,
            ),
        )


class FakeMaintenanceStub:
    def GetModelInfo(self, request):
        return maintenance_pb2.GetModelInfoResponse(
            ok=True,
            model_kind="text",
            max_context=8192,
            supported_parsers=["text"],
        )

    def ConvertModel(self, request):
        if request.ext.get("operation") == "download":
            yield maintenance_pb2.ConvertModelEvent(
                started=maintenance_pb2.ConvertStarted(job_id="download-job-1")
            )
            yield maintenance_pb2.ConvertModelEvent(
                progress=maintenance_pb2.ConvertProgress(stage="download", pct=0.5)
            )
            yield maintenance_pb2.ConvertModelEvent(
                manifest=maintenance_pb2.ConvertManifest(
                    manifest_json=json.dumps(
                        {
                            "schema_version": "melix.download_job.v1",
                            "status": "running",
                            "terminal_state": "running",
                            "selected_mirror": "https://mirror.example/hf",
                            "downloaded_bytes": 512,
                            "total_bytes": 1024,
                        },
                        sort_keys=True,
                    )
                )
            )
            yield maintenance_pb2.ConvertModelEvent(
                completed=maintenance_pb2.ConvertCompleted(output_path="/tmp/model-ops/download.artifact")
            )
            return

        yield maintenance_pb2.ConvertModelEvent(
            started=maintenance_pb2.ConvertStarted(job_id="job-1")
        )
        yield maintenance_pb2.ConvertModelEvent(
            completed=maintenance_pb2.ConvertCompleted(output_path="/tmp/model-ops/quantize.artifact")
        )

    def RunDoctor(self, request):
        return maintenance_pb2.RunDoctorResponse(
            ok=True,
            report_markdown=f"# Melix Doctor\n\n- model_handle: {request.model_handle}\n",
        )

    def RunBench(self, request):
        yield maintenance_pb2.RunBenchEvent(
            started=maintenance_pb2.BenchStarted(job_id="bench-1")
        )
        yield maintenance_pb2.RunBenchEvent(
            metric=maintenance_pb2.BenchMetric(name="bench.smoke.ttft_ms", value=24.45, unit="ms")
        )
        yield maintenance_pb2.RunBenchEvent(
            completed=maintenance_pb2.BenchCompleted(
                report_path="/tmp/model-ops/bench-report.md",
                evidence_path="/tmp/model-ops/run-evidence.json",
            )
        )

    def RunBenchMatrix(self, request):
        response = maintenance_pb2.RunBenchMatrixResponse()
        response.job.schema_version = "melix.benchmark_matrix_job.v1"
        response.job.job_id = "bench-matrix-1"
        response.job.model_id = request.model_handle.split("::", 1)[0] if request.model_handle else "melix-dev-text"
        response.job.task_kind = request.task_kind or "text-generation"
        response.job.source_repo = request.source_repo or "melix-dev-text"
        response.job.suite_ids.extend(request.suite_ids)
        response.job.benchmark_mode = "matrix"
        response.job.status = "completed"
        response.job.output_dir = "/tmp/model-ops/bench/matrix-runs/bench-matrix-1"
        row = response.summary_rows.add()
        row.job_id = "bench-matrix-1"
        row.task_kind = response.job.task_kind
        row.source_repo = response.job.source_repo
        row.model_id = response.job.model_id
        row.suite_id = request.suite_ids[0] if request.suite_ids else "smoke"
        row.context_length = request.context_lengths[0] if request.context_lengths else 1024
        row.generation_length = request.generation_lengths[0] if request.generation_lengths else 128
        row.batch_size = request.batch_sizes[0] if request.batch_sizes else 2
        row.cache_profile = request.cache_profiles[0] if request.cache_profiles else "cold"
        row.reasoning_mode = request.reasoning_modes[0] if request.reasoning_modes else "enabled"
        row.structured_output_mode = request.structured_output_modes[0] if request.structured_output_modes else "plain_text"
        row.concurrency_level = request.concurrency_levels[0] if request.concurrency_levels else 1
        row.repeats = request.repeats or 1
        row.requests = request.requests
        row.duration_seconds = request.duration_seconds
        row.ttft_mean_ms = 24.45
        return response

    def RunEvaluation(self, request):
        response = maintenance_pb2.RunEvaluationResponse(ok=True)
        response.job.schema_version = "melix.evaluation_job.v1"
        response.job.job_id = "eval-1"
        response.job.model_id = request.model_handle.split("::", 1)[0] if request.model_handle else "melix-dev-text"
        response.job.suite_id = request.suite_id
        response.job.dataset_id = request.dataset_id
        response.job.sample_size = request.sample_size
        response.job.parameters.update(request.parameters)
        response.job.status = "completed"
        result = response.results.add()
        result.schema_version = "melix.evaluation_result.v1"
        result.job_id = "eval-1"
        result.suite_id = request.suite_id
        result.dataset_id = request.dataset_id
        result.sample_size = request.sample_size
        metric = result.metrics.add()
        metric.name = f"eval.{request.suite_id}.accuracy"
        metric.value = 1.0
        result.report_path = "/tmp/model-ops/evaluation-result.json"
        result.evidence_path = "/tmp/model-ops/evaluation-run-evidence.json"
        return response

    def SearchHubModels(self, request):
        response = maintenance_pb2.SearchHubModelsResponse(ok=True, next_cursor="cursor:page-2")
        model = response.models.add()
        model.repo_id = "mlx-community/Qwen2.5-7B-Instruct-4bit"
        model.author = "mlx-community"
        model.model_name = "Qwen2.5-7B-Instruct-4bit"
        model.summary = f"query={request.query}"
        model.pipeline_tag = "text-generation"
        model.tags.extend(["mlx", "chat"])
        model.downloads = 321
        model.likes = 12
        model.mlx_compatible = True
        model.library_name = "transformers"
        model.sibling_files.extend(["README.md", "config.json"])
        model.last_modified = "2025-01-26T19:49:28Z"
        return response

    def GetHubModelCard(self, request):
        response = maintenance_pb2.GetHubModelCardResponse(ok=True)
        response.card.repo_id = request.repo_id
        response.card.author = "mlx-community"
        response.card.model_name = "Qwen2.5-7B-Instruct-4bit"
        response.card.summary = "MLX text-generation build"
        response.card.license = "apache-2.0"
        response.card.pipeline_tag = "text-generation"
        response.card.tags.extend(["mlx", "chat"])
        response.card.downloads = 321
        response.card.likes = 12
        response.card.mlx_compatible = True
        response.card.library_name = "transformers"
        response.card.sibling_files.extend(["README.md", "config.json", "model.safetensors"])
        response.card.base_models.extend(["Qwen/Qwen2.5-7B-Instruct"])
        response.card.last_modified = "2025-01-26T19:49:28Z"
        return response

    def ExportResults(self, request):
        return maintenance_pb2.ExportResultsResponse(
            ok=True,
            export_json=json.dumps(
                {
                    "output_dir": request.output_dir,
                    "kind": "benchmark",
                },
                sort_keys=True,
            ),
            export_path="/tmp/model-ops/export.json",
        )

    def SubmitResults(self, request):
        return maintenance_pb2.SubmitResultsResponse(
            ok=True,
            submission_json=json.dumps(
                {
                    "output_dir": request.output_dir,
                    "device_metadata": dict(request.device_metadata),
                },
                sort_keys=True,
            ),
        )


def test_bridge_helper_forwards_phase5_unary_and_streaming_commands(monkeypatch, capsys) -> None:
    monkeypatch.setattr(control_plane_bridge.grpc, "insecure_channel", lambda target: FakeChannel())
    monkeypatch.setattr(control_plane_bridge.inference_pb2_grpc, "InferenceServiceStub", lambda channel: FakeInferenceStub())
    monkeypatch.setattr(control_plane_bridge.maintenance_pb2_grpc, "MaintenanceServiceStub", lambda channel: FakeMaintenanceStub())

    embed_request = inference_pb2.EmbedRequest(
        id=common_pb2.RequestIdentity(request_id="embed-bridge"),
        model_handle="melix-dev-embed::bridge",
        inputs=["alpha", "beta"],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "control_plane_bridge.py",
            "embed",
            "--socket-path",
            "/tmp/unused.sock",
            "--request-b64",
            base64.b64encode(embed_request.SerializeToString()).decode("ascii"),
        ],
    )
    control_plane_bridge.main()
    embed_line = json.loads(capsys.readouterr().out.strip())
    embed_payload = inference_pb2.EmbedResponse.FromString(base64.b64decode(embed_line["message_b64"]))
    assert len(embed_payload.embeddings) == 2

    rerank_request = inference_pb2.RerankRequest(
        id=common_pb2.RequestIdentity(request_id="rerank-bridge"),
        model_handle="melix-dev-rerank::bridge",
        query="swift worker",
        documents=["python bridge", "swift worker"],
        top_k=2,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "control_plane_bridge.py",
            "rerank",
            "--socket-path",
            "/tmp/unused.sock",
            "--request-b64",
            base64.b64encode(rerank_request.SerializeToString()).decode("ascii"),
        ],
    )
    control_plane_bridge.main()
    rerank_line = json.loads(capsys.readouterr().out.strip())
    rerank_payload = inference_pb2.RerankResponse.FromString(base64.b64decode(rerank_line["message_b64"]))
    assert [item.index for item in rerank_payload.items] == [1, 0]

    info_request = maintenance_pb2.GetModelInfoRequest(source_model="melix-dev-text")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "control_plane_bridge.py",
            "get-model-info",
            "--socket-path",
            "/tmp/unused.sock",
            "--request-b64",
            base64.b64encode(info_request.SerializeToString()).decode("ascii"),
        ],
    )
    control_plane_bridge.main()
    info_line = json.loads(capsys.readouterr().out.strip())
    info_payload = maintenance_pb2.GetModelInfoResponse.FromString(base64.b64decode(info_line["message_b64"]))
    assert info_payload.ok is True
    assert info_payload.model_kind == "text"

    convert_request = maintenance_pb2.ConvertModelRequest(
        source_model="melix-dev-text",
        output_dir="/tmp/model-ops",
        ext={"operation": "quantize"},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "control_plane_bridge.py",
            "convert-model",
            "--socket-path",
            "/tmp/unused.sock",
            "--request-b64",
            base64.b64encode(convert_request.SerializeToString()).decode("ascii"),
        ],
    )
    control_plane_bridge.main()
    convert_lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    first_payload = maintenance_pb2.ConvertModelEvent.FromString(base64.b64decode(convert_lines[0]["message_b64"]))
    last_payload = maintenance_pb2.ConvertModelEvent.FromString(base64.b64decode(convert_lines[-1]["message_b64"]))
    assert first_payload.started.job_id == "job-1"
    assert last_payload.completed.output_path == "/tmp/model-ops/quantize.artifact"

    doctor_request = maintenance_pb2.RunDoctorRequest(model_handle="melix-dev-text::1")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "control_plane_bridge.py",
            "run-doctor",
            "--socket-path",
            "/tmp/unused.sock",
            "--request-b64",
            base64.b64encode(doctor_request.SerializeToString()).decode("ascii"),
        ],
    )
    control_plane_bridge.main()
    doctor_line = json.loads(capsys.readouterr().out.strip())
    doctor_payload = maintenance_pb2.RunDoctorResponse.FromString(base64.b64decode(doctor_line["message_b64"]))
    assert doctor_payload.ok is True
    assert "melix-dev-text::1" in doctor_payload.report_markdown

    bench_request = maintenance_pb2.RunBenchRequest(model_handle="melix-dev-text::1", suites=["smoke"])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "control_plane_bridge.py",
            "run-bench",
            "--socket-path",
            "/tmp/unused.sock",
            "--request-b64",
            base64.b64encode(bench_request.SerializeToString()).decode("ascii"),
        ],
    )
    control_plane_bridge.main()
    bench_lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    bench_started = maintenance_pb2.RunBenchEvent.FromString(base64.b64decode(bench_lines[0]["message_b64"]))
    bench_completed = maintenance_pb2.RunBenchEvent.FromString(base64.b64decode(bench_lines[-1]["message_b64"]))
    assert bench_started.started.job_id == "bench-1"
    assert bench_completed.completed.report_path == "/tmp/model-ops/bench-report.md"
    assert bench_completed.completed.evidence_path == "/tmp/model-ops/run-evidence.json"

    matrix_request = maintenance_pb2.RunBenchMatrixRequest(
        model_handle="melix-dev-text::1",
        task_kind="text-generation",
        source_repo="melix-dev-text",
        suite_ids=["smoke"],
        context_lengths=[1024],
        generation_lengths=[128],
        batch_sizes=[2],
        cache_profiles=["cold"],
        reasoning_modes=["enabled"],
        structured_output_modes=["plain_text"],
        concurrency_levels=[1],
        repeats=2,
        requests=8,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "control_plane_bridge.py",
            "run-bench-matrix",
            "--socket-path",
            "/tmp/unused.sock",
            "--request-b64",
            base64.b64encode(matrix_request.SerializeToString()).decode("ascii"),
        ],
    )
    control_plane_bridge.main()
    matrix_line = json.loads(capsys.readouterr().out.strip())
    matrix_payload = maintenance_pb2.RunBenchMatrixResponse.FromString(base64.b64decode(matrix_line["message_b64"]))
    assert matrix_payload.job.job_id == "bench-matrix-1"
    assert matrix_payload.summary_rows[0].suite_id == "smoke"
    assert matrix_payload.summary_rows[0].ttft_mean_ms == 24.45

    evaluation_request = maintenance_pb2.RunEvaluationRequest(
        model_handle="melix-dev-text::1",
        suite_id="mmlu",
        dataset_id="qa_smoke.dev.v1",
        sample_size=8,
        parameters={"judge": "deterministic"},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "control_plane_bridge.py",
            "run-evaluation",
            "--socket-path",
            "/tmp/unused.sock",
            "--request-b64",
            base64.b64encode(evaluation_request.SerializeToString()).decode("ascii"),
        ],
    )
    control_plane_bridge.main()
    eval_line = json.loads(capsys.readouterr().out.strip())
    eval_payload = maintenance_pb2.RunEvaluationResponse.FromString(base64.b64decode(eval_line["message_b64"]))
    assert eval_payload.ok is True
    assert eval_payload.job.suite_id == "mmlu"
    assert eval_payload.job.dataset_id == "qa_smoke.dev.v1"
    assert eval_payload.results[0].metrics[0].name == "eval.mmlu.accuracy"
    assert eval_payload.results[0].evidence_path == "/tmp/model-ops/evaluation-run-evidence.json"

    search_request = maintenance_pb2.SearchHubModelsRequest(
        query="qwen",
        page_size=5,
        cursor="cursor:page-1",
        mlx_only=True,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "control_plane_bridge.py",
            "search-hub-models",
            "--socket-path",
            "/tmp/unused.sock",
            "--request-b64",
            base64.b64encode(search_request.SerializeToString()).decode("ascii"),
        ],
    )
    control_plane_bridge.main()
    search_line = json.loads(capsys.readouterr().out.strip())
    search_payload = maintenance_pb2.SearchHubModelsResponse.FromString(base64.b64decode(search_line["message_b64"]))
    assert search_payload.ok is True
    assert search_payload.next_cursor == "cursor:page-2"
    assert search_payload.models[0].repo_id == "mlx-community/Qwen2.5-7B-Instruct-4bit"
    assert search_payload.models[0].summary == "query=qwen"

    card_request = maintenance_pb2.GetHubModelCardRequest(
        repo_id="mlx-community/Qwen2.5-7B-Instruct-4bit",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "control_plane_bridge.py",
            "get-hub-model-card",
            "--socket-path",
            "/tmp/unused.sock",
            "--request-b64",
            base64.b64encode(card_request.SerializeToString()).decode("ascii"),
        ],
    )
    control_plane_bridge.main()
    card_line = json.loads(capsys.readouterr().out.strip())
    card_payload = maintenance_pb2.GetHubModelCardResponse.FromString(base64.b64decode(card_line["message_b64"]))
    assert card_payload.ok is True
    assert card_payload.card.repo_id == "mlx-community/Qwen2.5-7B-Instruct-4bit"
    assert card_payload.card.license == "apache-2.0"
    assert card_payload.card.base_models == ["Qwen/Qwen2.5-7B-Instruct"]

    export_request = maintenance_pb2.ExportResultsRequest(output_dir="/tmp/model-ops/export")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "control_plane_bridge.py",
            "export-results",
            "--socket-path",
            "/tmp/unused.sock",
            "--request-b64",
            base64.b64encode(export_request.SerializeToString()).decode("ascii"),
        ],
    )
    control_plane_bridge.main()
    export_line = json.loads(capsys.readouterr().out.strip())
    export_payload = maintenance_pb2.ExportResultsResponse.FromString(base64.b64decode(export_line["message_b64"]))
    assert export_payload.ok is True
    assert export_payload.export_path == "/tmp/model-ops/export.json"
    assert json.loads(export_payload.export_json)["output_dir"] == "/tmp/model-ops/export"

    submit_request = maintenance_pb2.SubmitResultsRequest(
        output_dir="/tmp/model-ops/export",
        device_metadata={"chip": "M4 Max"},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "control_plane_bridge.py",
            "submit-results",
            "--socket-path",
            "/tmp/unused.sock",
            "--request-b64",
            base64.b64encode(submit_request.SerializeToString()).decode("ascii"),
        ],
    )
    control_plane_bridge.main()
    submit_line = json.loads(capsys.readouterr().out.strip())
    submit_payload = maintenance_pb2.SubmitResultsResponse.FromString(base64.b64decode(submit_line["message_b64"]))
    assert submit_payload.ok is True
    assert json.loads(submit_payload.submission_json)["device_metadata"] == {"chip": "M4 Max"}


def test_bridge_helper_forwards_download_stream_manifest_events(monkeypatch, capsys) -> None:
    monkeypatch.setattr(control_plane_bridge.grpc, "insecure_channel", lambda target: FakeChannel())
    monkeypatch.setattr(control_plane_bridge.maintenance_pb2_grpc, "MaintenanceServiceStub", lambda channel: FakeMaintenanceStub())

    convert_request = maintenance_pb2.ConvertModelRequest(
        source_model="mlx-community/demo-repo",
        output_dir="/tmp/model-ops",
        generate_manifest=True,
        ext={"operation": "download"},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "control_plane_bridge.py",
            "convert-model",
            "--socket-path",
            "/tmp/unused.sock",
            "--request-b64",
            base64.b64encode(convert_request.SerializeToString()).decode("ascii"),
        ],
    )

    control_plane_bridge.main()
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    payloads = [
        maintenance_pb2.ConvertModelEvent.FromString(base64.b64decode(line["message_b64"]))
        for line in lines
    ]
    manifest_json = next(event.manifest.manifest_json for event in payloads if event.HasField("manifest"))

    assert payloads[0].started.job_id == "download-job-1"
    assert payloads[1].progress.stage == "download"
    assert json.loads(manifest_json)["selected_mirror"] == "https://mirror.example/hf"
    assert payloads[-1].completed.output_path == "/tmp/model-ops/download.artifact"


def test_bridge_helper_forwards_phase6_audio_unary_commands(monkeypatch, capsys) -> None:
    monkeypatch.setattr(control_plane_bridge.grpc, "insecure_channel", lambda target: FakeChannel())
    monkeypatch.setattr(control_plane_bridge.inference_pb2_grpc, "InferenceServiceStub", lambda channel: FakeInferenceStub())

    transcribe_request = inference_pb2.TranscribeRequest(
        id=common_pb2.RequestIdentity(request_id="transcribe-bridge"),
        model_handle="melix-dev-transcribe::bridge",
        audio_bytes=b"hello audio",
        format="wav",
        language="en",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "control_plane_bridge.py",
            "transcribe",
            "--socket-path",
            "/tmp/unused.sock",
            "--request-b64",
            base64.b64encode(transcribe_request.SerializeToString()).decode("ascii"),
        ],
    )
    control_plane_bridge.main()
    transcribe_line = json.loads(capsys.readouterr().out.strip())
    transcribe_payload = inference_pb2.TranscribeResponse.FromString(base64.b64decode(transcribe_line["message_b64"]))
    assert transcribe_payload.text == "hello audio"
    assert transcribe_payload.language == "en"
    assert transcribe_payload.duration_seconds == 0.25

    speak_request = inference_pb2.SpeakRequest(
        id=common_pb2.RequestIdentity(request_id="speak-bridge"),
        model_handle="melix-dev-speech::bridge",
        input="hello speech",
        voice="alloy",
        format="wav",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "control_plane_bridge.py",
            "speak",
            "--socket-path",
            "/tmp/unused.sock",
            "--request-b64",
            base64.b64encode(speak_request.SerializeToString()).decode("ascii"),
        ],
    )
    control_plane_bridge.main()
    speak_line = json.loads(capsys.readouterr().out.strip())
    speak_payload = inference_pb2.SpeakResponse.FromString(base64.b64decode(speak_line["message_b64"]))
    assert speak_payload.audio_bytes == b"VOICE=alloy\nFORMAT=wav\nTEXT=hello speech"
    assert speak_payload.format == "wav"


def test_bridge_helper_forwards_phase7_image_unary_commands(monkeypatch, capsys) -> None:
    monkeypatch.setattr(control_plane_bridge.grpc, "insecure_channel", lambda target: FakeChannel())
    stub = FakeInferenceStub()
    monkeypatch.setattr(control_plane_bridge.inference_pb2_grpc, "InferenceServiceStub", lambda channel: stub)

    image_generate_request = inference_pb2.ImageGenerateRequest(
        id=common_pb2.RequestIdentity(request_id="image-generate-bridge"),
        model_handle="melix-dev-image::bridge",
        prompt="red fox",
        size="256x256",
        response_format="png",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "control_plane_bridge.py",
            "image-generate",
            "--socket-path",
            "/tmp/unused.sock",
            "--request-b64",
            base64.b64encode(image_generate_request.SerializeToString()).decode("ascii"),
        ],
    )
    control_plane_bridge.main()
    generate_line = json.loads(capsys.readouterr().out.strip())
    generate_payload = inference_pb2.ImageGenerateResponse.FromString(base64.b64decode(generate_line["message_b64"]))
    assert generate_payload.job.job_id == "image-generate-bridge::image-generate"
    assert generate_payload.images == [b"generated-image"]
    assert stub.last_image_generate_timeout == 1800.0

    image_edit_request = inference_pb2.ImageEditRequest(
        id=common_pb2.RequestIdentity(request_id="image-edit-bridge"),
        model_handle="melix-dev-image::bridge",
        prompt="add glow",
        image=b"SOURCE",
        mask=b"MASK",
        size="256x256",
        response_format="png",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "control_plane_bridge.py",
            "image-edit",
            "--socket-path",
            "/tmp/unused.sock",
            "--request-b64",
            base64.b64encode(image_edit_request.SerializeToString()).decode("ascii"),
        ],
    )
    control_plane_bridge.main()
    edit_line = json.loads(capsys.readouterr().out.strip())
    edit_payload = inference_pb2.ImageEditResponse.FromString(base64.b64decode(edit_line["message_b64"]))
    assert edit_payload.job.job_id == "image-edit-bridge::image-edit"
    assert edit_payload.images == [b"edited-image"]
    assert stub.last_image_edit_timeout == 1800.0


def test_image_request_timeout_seconds_uses_env_override(monkeypatch) -> None:
    monkeypatch.setenv("MELIX_IMAGE_REQUEST_TIMEOUT_SECONDS", "42")

    assert control_plane_bridge.image_request_timeout_seconds() == 42.0
