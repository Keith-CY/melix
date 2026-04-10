import Darwin
import Foundation
import Testing

@testable import AppMain
import MelixCLICore
import MelixControlPlaneCore

@Suite("Melix CLI Subprocess Runner", .serialized)
struct MelixCLISubprocessRunnerTests {
    @Test("foundation process launcher drains large stdout and stderr before waiting for exit")
    func foundationProcessLauncherDrainsLargePipesBeforeWaitingForExit() async throws {
        let launcher = FoundationMelixCLIProcessLauncher()
        let pidFileURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-cli-launcher-\(UUID().uuidString).pid")
        let payloadBytes = 1_048_576
        let script = #"""
        import os
        import sys

        pid_file = sys.argv[1]
        payload_bytes = int(sys.argv[2])

        with open(pid_file, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))

        payload = "x" * payload_bytes
        sys.stdout.write(payload)
        sys.stdout.flush()
        sys.stderr.write(payload)
        sys.stderr.flush()
        """#

        let task = Task {
            try await launcher.run(
                executable: "/usr/bin/python3",
                arguments: [
                    "-c",
                    script,
                    pidFileURL.path,
                    String(payloadBytes),
                ],
                environment: ProcessInfo.processInfo.environment
            )
        }

        do {
            let result = try await withTaskTimeout(.seconds(2)) {
                try await task.value
            }
            #expect(result.exitStatus == 0)
            #expect(result.stdout.count == payloadBytes)
            #expect(result.stderr.count == payloadBytes)
        } catch {
            terminateRecordedProcess(at: pidFileURL)
            task.cancel()
            throw error
        }
    }

    @Test("subprocess runner maps benchmark commands to melix arguments and decodes JSON output")
    func subprocessRunnerMapsBenchmarkCommands() async throws {
        let launcher = RecordingMelixCLIProcessLauncher(
            stdout: #"""
            {
              "report_path": "/tmp/bench-report.md",
              "report_markdown": "# Bench",
              "metrics": {
                "bench.smoke.ttft_ms": 24.45
              }
            }
            """#,
            stderr: "",
            exitStatus: 0
        )
        let runner = MelixCLISubprocessRunner(
            environment: [
                "MELIX_CLI_EXECUTABLE": "/tmp/melix-stub",
                "MELIX_HOME": "/tmp/melix-home",
            ],
            launcher: launcher
        )

        let result = try await runner.runBenchmark(
            .init(
                hfRepoID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                suites: ["smoke"],
                contextLengths: [4096, 1024],
                generationLength: 256,
                batchSizes: [4, 1],
                repeats: 3,
                cacheProfile: "warm",
                reasoningMode: "enabled",
                structuredOutputMode: "json_object",
                parameters: [
                    "sample_size": "8",
                    "batch_factor": "2",
                ]
            )
        )

        #expect(result.reportPath == "/tmp/bench-report.md")
        #expect(result.reportMarkdown == "# Bench")
        #expect(result.metrics["bench.smoke.ttft_ms"] == 24.45)
        let snapshot = await launcher.snapshot()
        #expect(snapshot.recordedExecutable == "/tmp/melix-stub")
        #expect(
            snapshot.recordedArguments == [
                "bench",
                "run",
                "--repo-id", "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                "--suite", "smoke",
                "--context-length", "1024",
                "--context-length", "4096",
                "--generation-length", "256",
                "--batch-size", "1",
                "--batch-size", "4",
                "--repeats", "3",
                "--cache-profile", "warm",
                "--reasoning-mode", "enabled",
                "--structured-output-mode", "json_object",
                "--sample-size", "8",
                "--batch-factor", "2",
                "--json",
            ]
        )
        #expect(snapshot.recordedEnvironment["MELIX_HOME"] == "/tmp/melix-home")
    }

    @Test("subprocess runner surfaces non-zero exit status and stderr")
    func subprocessRunnerSurfacesProcessFailure() async throws {
        let launcher = RecordingMelixCLIProcessLauncher(
            stdout: "",
            stderr: "benchmark exploded",
            exitStatus: 17
        )
        let runner = MelixCLISubprocessRunner(
            environment: ["MELIX_CLI_EXECUTABLE": "/tmp/melix-stub"],
            launcher: launcher
        )

        await #expect(throws: MelixCLIProcessLaunchError.self) {
            _ = try await runner.runBenchmark(
                .init(
                    modelID: "melix-dev-text",
                    suites: ["smoke"]
                )
            )
        }
    }

    @Test("subprocess runner resolves the executable from MELIX_CLI when the explicit subprocess path is absent")
    func subprocessRunnerResolvesExecutableFromMelixCLIEnvironment() async throws {
        let launcher = RecordingMelixCLIProcessLauncher(
            stdout: #"""
            {
              "report_path": "/tmp/bench-report.md",
              "report_markdown": "# Bench",
              "metrics": {
                "bench.smoke.ttft_ms": 24.45
              }
            }
            """#,
            stderr: "",
            exitStatus: 0
        )
        let runner = MelixCLISubprocessRunner(
            environment: [
                "MELIX_CLI": "/tmp/melix-cli-from-env",
                "MELIX_HOME": "/tmp/melix-home",
            ],
            launcher: launcher
        )

        _ = try await runner.runBenchmark(
            .init(
                hfRepoID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                suites: ["smoke"]
            )
        )

        let snapshot = await launcher.snapshot()
        #expect(snapshot.recordedExecutable == "/tmp/melix-cli-from-env")
    }

    @Test("subprocess runner prefers MELIX_CLI over MELIX_CLI_EXECUTABLE when both are present")
    func subprocessRunnerPrefersMelixCLIOverCLIExecutableFallback() async throws {
        let launcher = RecordingMelixCLIProcessLauncher(
            stdout: #"""
            {
              "report_path": "/tmp/bench-report.md",
              "report_markdown": "# Bench",
              "metrics": {
                "bench.smoke.ttft_ms": 24.45
              }
            }
            """#,
            stderr: "",
            exitStatus: 0
        )
        let runner = MelixCLISubprocessRunner(
            environment: [
                "MELIX_CLI": "/tmp/melix-cli-preferred",
                "MELIX_CLI_EXECUTABLE": "/tmp/melix-cli-stale",
                "MELIX_HOME": "/tmp/melix-home",
            ],
            launcher: launcher
        )

        _ = try await runner.runBenchmark(
            .init(
                hfRepoID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                suites: ["smoke"]
            )
        )

        let snapshot = await launcher.snapshot()
        #expect(snapshot.recordedExecutable == "/tmp/melix-cli-preferred")
    }

    @Test("subprocess runner uses the shared inferred repo-root cli path contract")
    func subprocessRunnerUsesSharedInferredRepoRootCLIPathContract() async throws {
        let repoRoot = FileManager.default.currentDirectoryPath
        let expectedExecutable = MenuBarBootstrapEnvironment.inferCLIExecutablePath(repoRoot: repoRoot)
        let launcher = RecordingMelixCLIProcessLauncher(
            stdout: #"""
            {
              "report_path": "/tmp/bench-report.md",
              "report_markdown": "# Bench",
              "metrics": {
                "bench.smoke.ttft_ms": 24.45
              }
            }
            """#,
            stderr: "",
            exitStatus: 0
        )
        let runner = MelixCLISubprocessRunner(
            environment: [
                "MELIX_REPO_ROOT": repoRoot,
                "MELIX_HOME": "/tmp/melix-home",
            ],
            launcher: launcher
        )

        _ = try await runner.runBenchmark(
            .init(
                hfRepoID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                suites: ["smoke"]
            )
        )

        let snapshot = await launcher.snapshot()
        #expect(snapshot.recordedExecutable == expectedExecutable)
    }

    @Test("subprocess runner maps benchmark matrix commands to melix arguments and decodes JSON output")
    func subprocessRunnerMapsBenchmarkMatrixCommands() async throws {
        let launcher = RecordingMelixCLIProcessLauncher(
            stdout: #"""
            {
              "job": {
                "schema_version": "melix.benchmark_matrix_job.v1",
                "job_id": "matrix-1",
                "model_id": "melix-dev-text-lora",
                "task_kind": "text-generation",
                "source_repo": "databricks/databricks-dolly-15k",
                "suite_ids": ["smoke"],
                "benchmark_mode": "matrix",
                "status": "completed",
                "output_dir": "/tmp/matrix-1",
                "created_at_unix_ms": 1712250000000,
                "updated_at_unix_ms": 1712250005000
              },
              "summary_rows": [
                {
                  "job_id": "matrix-1",
                  "task_kind": "text-generation",
                  "source_repo": "databricks/databricks-dolly-15k",
                  "model_id": "melix-dev-text-lora",
                  "suite_id": "smoke",
                  "context_length": 1024,
                  "generation_length": 128,
                  "batch_size": 2,
                  "cache_profile": "warm",
                  "reasoning_mode": "enabled",
                  "structured_output_mode": "json_schema",
                  "concurrency_level": 1,
                  "repeats": 4,
                  "requests": 12,
                  "duration_seconds": 0,
                  "ttft_mean_ms": 21.4,
                  "ttft_std_ms": 0.9,
                  "request_latency_mean_ms": 29.1,
                  "request_latency_std_ms": 0.8,
                  "prefill_tokens_per_second_mean": 340.0,
                  "decode_tokens_per_second_mean": 66.0,
                  "throughput_requests_per_second": 5.4,
                  "throughput_tokens_per_second": 284.0,
                  "success_rate": 1.0,
                  "peak_memory_bytes_max": 1984000000,
                  "queue_wait_mean_ms": 1.8,
                  "queue_wait_p95_ms": 2.4,
                  "created_at_unix_ms": 1712250000000
                }
              ]
            }
            """#,
            stderr: "",
            exitStatus: 0
        )
        let runner = MelixCLISubprocessRunner(
            environment: ["MELIX_CLI_EXECUTABLE": "/tmp/melix-stub"],
            launcher: launcher
        )

        let result = try await runner.runBenchmarkMatrix(
            .init(
                modelID: "melix-dev-text-lora",
                taskKind: "text-generation",
                suites: ["smoke"],
                contextLengths: [1024],
                generationLengths: [128],
                batchSizes: [2],
                cacheProfiles: ["warm"],
                reasoningModes: ["enabled"],
                structuredOutputModes: ["json_schema"],
                concurrencyLevels: [1],
                repeats: 4,
                requests: 12
            )
        )

        #expect(result.job.jobID == "matrix-1")
        #expect(result.summaryRows.count == 1)
        let snapshot = await launcher.snapshot()
        #expect(
            snapshot.recordedArguments == [
                "bench",
                "matrix",
                "run",
                "--model-id", "melix-dev-text-lora",
                "--task-kind", "text-generation",
                "--suite", "smoke",
                "--context-length", "1024",
                "--generation-length", "128",
                "--batch-size", "2",
                "--cache-profile", "warm",
                "--reasoning-mode", "enabled",
                "--structured-output-mode", "json_schema",
                "--concurrency", "1",
                "--repeats", "4",
                "--requests", "12",
                "--json",
            ]
        )
    }

    @Test("subprocess runner maps evaluation commands to melix arguments and decodes JSON output")
    func subprocessRunnerMapsEvaluationCommands() async throws {
        let launcher = RecordingMelixCLIProcessLauncher(
            stdout: #"""
            [
              {
                "job": {
                  "schema_version": "melix.evaluation_job.v1",
                  "job_id": "eval-1",
                  "model_id": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                  "task_kind": "text-generation",
                  "source_repo": "cais/mmlu",
                  "suite_id": "mmlu",
                  "dataset_id": "mmlu.dev.v1",
                  "sample_size": 8,
                  "scoring_mode": "multiple_choice_accuracy",
                  "parameters": {
                    "batch_factor": "2",
                    "few_shot": "3",
                    "seed": "7"
                  },
                  "status": "completed",
                  "output_dir": "/tmp/eval-1",
                  "created_at_unix_ms": 1712300000000,
                  "updated_at_unix_ms": 1712300005000
                },
                "results": [
                  {
                    "schema_version": "melix.evaluation_result.v1",
                    "job_id": "eval-1",
                    "suite_id": "mmlu",
                    "dataset_id": "mmlu.dev.v1",
                    "sample_size": 8,
                    "report_path": "/tmp/eval-1/report.md",
                    "metrics": [
                      {
                        "name": "eval.mmlu.multiple_choice_accuracy",
                        "value": 0.75,
                        "unit": "ratio"
                      }
                    ]
                  }
                ]
              }
            ]
            """#,
            stderr: "",
            exitStatus: 0
        )
        let runner = MelixCLISubprocessRunner(
            environment: ["MELIX_CLI_EXECUTABLE": "/tmp/melix-stub"],
            launcher: launcher
        )

        let result = try await runner.runEvaluations(
            .init(
                hfRepoID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                suites: ["mmlu"],
                sampleSize: 8,
                parameters: [
                    "batch_factor": "2",
                    "seed": "7",
                    "few_shot": "3",
                    "scoring_mode": "multiple_choice_accuracy",
                    "code_exec_policy": "forbid",
                ]
            )
        )

        #expect(result.count == 1)
        #expect(result.first?.job.jobID == "eval-1")
        let snapshot = await launcher.snapshot()
        #expect(
            snapshot.recordedArguments == [
                "eval",
                "run",
                "--repo-id", "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                "--suite", "mmlu",
                "--sample-size", "8",
                "--batch-factor", "2",
                "--seed", "7",
                "--few-shot", "3",
                "--scoring-mode", "multiple_choice_accuracy",
                "--code-exec-policy", "forbid",
                "--json",
            ]
        )
    }

    @Test("subprocess runner rebuilds the export bundle from public cli list and export commands")
    func subprocessRunnerRebuildsExportBundleFromPublicCLICommands() async throws {
        let fixtureBundle = try ControlPlaneBenchmarkExportBundle.decode(json: makeBenchmarkExportBundleJSON())
        let outputDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-cli-bundle-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: outputDirectory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: outputDirectory) }

        let launcher = ScriptedMelixCLIProcessLauncher { arguments, _ in
            try makeSyntheticBundleResponse(
                arguments: arguments,
                outputDirectory: outputDirectory,
                fixtureBundle: fixtureBundle
            )
        }
        let runner = MelixCLISubprocessRunner(
            environment: [
                "MELIX_CLI_EXECUTABLE": "/tmp/melix-stub",
                "MELIX_HOME": outputDirectory.path,
            ],
            launcher: launcher
        )

        let bundle = try await runner.fetchBenchmarkExportBundle(outputDir: outputDirectory.path)

        #expect(bundle.benchmarkHistoryEntries() == fixtureBundle.benchmarkHistoryEntries())
        #expect(bundle.benchmarkCSVRows() == fixtureBundle.benchmarkCSVRows())
        #expect(bundle.benchmarkMatrixSummaryCSVRows() == fixtureBundle.benchmarkMatrixSummaryCSVRows())
        #expect(bundle.benchmarkMatrixRequestRows() == fixtureBundle.benchmarkMatrixRequestRows())
        #expect(bundle.evaluationHistoryEntries() == fixtureBundle.evaluationHistoryEntries())
        #expect(bundle.evaluationSummaryCSVRows() == fixtureBundle.evaluationSummaryCSVRows())
        #expect(bundle.evaluationSampleRows() == fixtureBundle.evaluationSampleRows())

        let snapshot = await launcher.snapshot()
        let recordedCommands = snapshot.recordedArguments.map { $0.joined(separator: " ") }
        #expect(recordedCommands.contains("bench list --json"))
        #expect(recordedCommands.contains(where: { $0.hasPrefix("bench export-csv --job-id bench-newer --output ") }))
        #expect(recordedCommands.contains("bench matrix list --json"))
        #expect(recordedCommands.contains(where: { $0.hasPrefix("bench matrix export-summary-csv --job-id matrix-newer --output ") }))
        #expect(recordedCommands.contains(where: { $0.hasPrefix("bench matrix export-requests-csv --job-id matrix-newer --output ") }))
        #expect(recordedCommands.contains("eval list --json"))
        #expect(recordedCommands.contains(where: { $0.hasPrefix("eval export-summary-csv --job-id eval-newer --output ") }))
        #expect(recordedCommands.contains(where: { $0.hasPrefix("eval export-samples-jsonl --job-id eval-newer --output ") }))
    }

}

private enum TaskTimeoutError: Error, Equatable {
    case exceeded
}

private func withTaskTimeout<T: Sendable>(
    _ timeout: Duration,
    operation: @escaping @Sendable () async throws -> T
) async throws -> T {
    let result = await withCheckedContinuation { (continuation: CheckedContinuation<Result<T, Error>, Never>) in
        let box = TimeoutResultBox(continuation: continuation)
        let operationTask = Task {
            do {
                await box.resolve(.success(try await operation()))
            } catch {
                if Task.isCancelled {
                    return
                }
                await box.resolve(.failure(error))
            }
        }
        Task {
            try? await Task.sleep(for: timeout)
            operationTask.cancel()
            await box.resolve(.failure(TaskTimeoutError.exceeded))
        }
    }
    return try result.get()
}

private func terminateRecordedProcess(at pidFileURL: URL) {
    guard let pidString = try? String(contentsOf: pidFileURL, encoding: .utf8)
        .trimmingCharacters(in: .whitespacesAndNewlines),
          let pid = Int32(pidString)
    else {
        return
    }
    _ = kill(pid, SIGKILL)
}

private actor TimeoutResultBox<T: Sendable> {
    private var continuation: CheckedContinuation<Result<T, Error>, Never>?

    init(continuation: CheckedContinuation<Result<T, Error>, Never>) {
        self.continuation = continuation
    }

    func resolve(_ result: Result<T, Error>) {
        guard let continuation else {
            return
        }
        self.continuation = nil
        continuation.resume(returning: result)
    }
}

private actor RecordingMelixCLIProcessLauncher: MelixCLIProcessLaunching {
    private let stdout: String
    private let stderr: String
    private let exitStatus: Int32
    private let sideEffect: (@Sendable (String, [String], [String: String]) throws -> Void)?

    private(set) var recordedExecutable = ""
    private(set) var recordedArguments: [String] = []
    private(set) var recordedEnvironment: [String: String] = [:]

    init(
        stdout: String,
        stderr: String,
        exitStatus: Int32,
        sideEffect: (@Sendable (String, [String], [String: String]) throws -> Void)? = nil
    ) {
        self.stdout = stdout
        self.stderr = stderr
        self.exitStatus = exitStatus
        self.sideEffect = sideEffect
    }

    func run(
        executable: String,
        arguments: [String],
        environment: [String: String]
    ) async throws -> MelixCLIProcessResult {
        recordedExecutable = executable
        recordedArguments = arguments
        recordedEnvironment = environment
        try sideEffect?(executable, arguments, environment)
        return MelixCLIProcessResult(
            stdout: stdout,
            stderr: stderr,
            exitStatus: exitStatus
        )
    }

    func snapshot() -> (recordedExecutable: String, recordedArguments: [String], recordedEnvironment: [String: String]) {
        (recordedExecutable, recordedArguments, recordedEnvironment)
    }
}

private actor ScriptedMelixCLIProcessLauncher: MelixCLIProcessLaunching {
    private let responder: @Sendable ([String], [String: String]) throws -> MelixCLIProcessResult
    private(set) var recordedExecutable = ""
    private(set) var recordedArguments: [[String]] = []
    private(set) var recordedEnvironment: [[String: String]] = []

    init(
        responder: @escaping @Sendable ([String], [String: String]) throws -> MelixCLIProcessResult
    ) {
        self.responder = responder
    }

    func run(
        executable: String,
        arguments: [String],
        environment: [String: String]
    ) async throws -> MelixCLIProcessResult {
        recordedExecutable = executable
        recordedArguments.append(arguments)
        recordedEnvironment.append(environment)
        return try responder(arguments, environment)
    }

    func snapshot() -> (
        recordedExecutable: String,
        recordedArguments: [[String]],
        recordedEnvironment: [[String: String]]
    ) {
        (recordedExecutable, recordedArguments, recordedEnvironment)
    }
}

private func makeSyntheticBundleResponse(
    arguments: [String],
    outputDirectory: URL,
    fixtureBundle: ControlPlaneBenchmarkExportBundle
) throws -> MelixCLIProcessResult {
    switch arguments {
    case ["bench", "list", "--json"]:
        let data = try JSONEncoder().encode(fixtureBundle.benchmarkHistoryEntries())
        return MelixCLIProcessResult(stdout: String(decoding: data, as: UTF8.self), stderr: "", exitStatus: 0)
    case ["bench", "matrix", "list", "--json"]:
        let data = try JSONEncoder().encode(fixtureBundle.benchmarkMatrixHistoryEntries())
        return MelixCLIProcessResult(stdout: String(decoding: data, as: UTF8.self), stderr: "", exitStatus: 0)
    case ["eval", "list", "--json"]:
        let data = try JSONEncoder().encode(fixtureBundle.evaluationHistoryEntries())
        return MelixCLIProcessResult(stdout: String(decoding: data, as: UTF8.self), stderr: "", exitStatus: 0)
    default:
        break
    }

    guard let outputIndex = arguments.firstIndex(of: "--output"),
          arguments.indices.contains(outputIndex + 1),
          let jobIndex = arguments.firstIndex(of: "--job-id"),
          arguments.indices.contains(jobIndex + 1) else {
        throw TestCommandError.invalidArguments(arguments)
    }

    let jobID = arguments[jobIndex + 1]
    let outputURL = URL(fileURLWithPath: arguments[outputIndex + 1])
    try FileManager.default.createDirectory(at: outputURL.deletingLastPathComponent(), withIntermediateDirectories: true)

    let response: String
    switch Array(arguments.prefix(3)) {
    case ["bench", "export-csv", "--job-id"]:
        response = fixtureBundle.benchmarkCSV(jobID: jobID)
    case ["bench", "matrix", "export-summary-csv"]:
        response = fixtureBundle.benchmarkMatrixSummaryCSV(jobID: jobID)
    case ["bench", "matrix", "export-requests-csv"]:
        response = fixtureBundle.benchmarkMatrixRequestsCSV(jobID: jobID)
    case ["eval", "export-summary-csv", "--job-id"]:
        response = fixtureBundle.evaluationSummaryCSV(jobID: jobID)
    case ["eval", "export-samples-jsonl", "--job-id"]:
        response = try fixtureBundle.evaluationSamplesJSONL(jobID: jobID)
    default:
        throw TestCommandError.invalidArguments(arguments)
    }

    try response.write(to: outputURL, atomically: true, encoding: .utf8)
    let payload = [
        "job_id": jobID,
        "output_path": outputURL.path,
        "row_count": 1,
    ] as [String: Any]
    let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    return MelixCLIProcessResult(stdout: String(decoding: data, as: UTF8.self), stderr: "", exitStatus: 0)
}

private enum TestCommandError: Error {
    case invalidArguments([String])
}
