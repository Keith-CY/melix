import Foundation
import Testing

@testable import MelixCLICore

@Suite("Benchmark Repeat Limit")
struct BenchmarkRepeatLimitTests {
    @Test("public benchmark option builders normalize omitted repeat counts")
    func publicBenchmarkOptionBuildersNormalizeOmittedRepeatCounts() {
        let benchOptions = BenchRunOptions(repeats: 0)
        let matrixOptions = BenchMatrixRunOptions(repeats: 0)

        #expect(benchOptions.repeats == 1)
        #expect(matrixOptions.repeats == 1)
    }

    @Test("CLI parser accepts benchmark repeat counts at the product limit")
    func cliParserAcceptsBenchmarkRepeatCountsAtTheProductLimit() throws {
        let benchCommand = try MelixCLIParser.parse([
            "bench",
            "run",
            "--model-id", "melix-dev-text",
            "--suite", "smoke",
            "--repeats", "20",
        ])
        let matrixCommand = try MelixCLIParser.parse([
            "bench",
            "matrix",
            "run",
            "--model-id", "melix-dev-text",
            "--suite", "smoke",
            "--context-length", "1024",
            "--generation-length", "128",
            "--batch-size", "1",
            "--cache-profile", "cold",
            "--reasoning-mode", "disabled",
            "--structured-output-mode", "disabled",
            "--concurrency", "1",
            "--repeats", "20",
            "--requests", "4",
        ])

        guard case .benchRun(let benchOptions) = benchCommand else {
            Issue.record("Expected bench run command, got \(benchCommand).")
            return
        }
        guard case .benchMatrixRun(let matrixOptions) = matrixCommand else {
            Issue.record("Expected bench matrix run command, got \(matrixCommand).")
            return
        }
        #expect(benchOptions.repeats == 20)
        #expect(matrixOptions.repeats == 20)
    }

    @Test("CLI parser rejects benchmark repeat counts above the product limit")
    func cliParserRejectsBenchmarkRepeatCountsAboveTheProductLimit() throws {
        try assertParserError(
            for: [
                "bench",
                "run",
                "--model-id", "melix-dev-text",
                "--suite", "smoke",
                "--repeats", "21",
            ],
            equals: .usage("Invalid value for --repeats. Expected an integer between 1 and 20.")
        )

        try assertParserError(
            for: [
                "bench",
                "matrix",
                "run",
                "--model-id", "melix-dev-text",
                "--suite", "smoke",
                "--context-length", "1024",
                "--generation-length", "128",
                "--batch-size", "1",
                "--cache-profile", "cold",
                "--reasoning-mode", "disabled",
                "--structured-output-mode", "disabled",
                "--concurrency", "1",
                "--repeats", "21",
                "--requests", "4",
            ],
            equals: .usage("Invalid value for --repeats. Expected an integer between 1 and 20.")
        )

        try assertParserError(
            for: [
                "batch",
                "run",
                "--models", "/tmp/models.txt",
                "--bench-repeats", "21",
                "--dry-run",
            ],
            equals: .usage("Invalid value for --bench-repeats. Expected an integer between 1 and 20.")
        )
    }

    @Test("batch run rejects benchmark repeat counts above the product limit from config and environment")
    func batchRunRejectsBenchmarkRepeatCountsAboveTheProductLimitFromConfigAndEnvironment() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let modelList = root.appendingPathComponent("models.txt")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try "mlx-community/Qwen3.5-9B-MLX-4bit\n".write(to: modelList, atomically: true, encoding: .utf8)

        let config = root.appendingPathComponent("repeat-limit.yaml")
        try """
        model_list: \(modelList.path)
        bench_repeats: 21
        """.write(to: config, atomically: true, encoding: .utf8)

        let runner = MelixCLIRunner(environment: ["HOME": root.path])
        let configMessage = try await requireUsageError {
            _ = try await runner.run(.batchRun(.init(modelListPath: "", configPath: config.path, dryRun: true)))
        }
        #expect(configMessage == "Invalid value for --bench-repeats: 21. Expected an integer between 1 and 20.")

        let envRunner = MelixCLIRunner(environment: [
            "HOME": root.path,
            "MELIX_BENCH_REPEATS": "21",
        ])
        let envMessage = try await requireUsageError {
            _ = try await envRunner.run(.batchRun(.init(modelListPath: modelList.path, dryRun: true)))
        }
        #expect(envMessage == "Invalid value for --bench-repeats: 21. Expected an integer between 1 and 20.")
    }

    @Test("batch run accepts benchmark repeat counts at the product limit")
    func batchRunAcceptsBenchmarkRepeatCountsAtTheProductLimit() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let modelList = root.appendingPathComponent("models.txt")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try "mlx-community/Qwen3.5-9B-MLX-4bit\n".write(to: modelList, atomically: true, encoding: .utf8)

        let runner = MelixCLIRunner(environment: ["HOME": root.path])
        _ = try await runner.run(.batchRun(.init(modelListPath: modelList.path, benchRepeats: 20, dryRun: true)))
    }
}

private func assertParserError(
    for arguments: [String],
    equals expected: MelixCLIError
) throws {
    #expect(throws: expected) {
        try MelixCLIParser.parse(arguments)
    }
}

private func requireUsageError(_ body: () async throws -> Void) async throws -> String {
    do { try await body() } catch let MelixCLIError.usage(message) {
        return message
    }
    Issue.record("Expected MelixCLIError.usage to be thrown.")
    return ""
}
