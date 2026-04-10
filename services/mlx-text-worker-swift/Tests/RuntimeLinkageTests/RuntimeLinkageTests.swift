import Foundation
import Testing

@Suite("Runtime Linkage")
struct RuntimeLinkageTests {
    @Test("production executable links the MLX LLM trampoline model factory")
    func productionExecutableLinksMLXLLMTrampolineModelFactory() throws {
        let executablePath = try #require(resolveBootstrapExecutablePath())
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/nm")
        process.arguments = ["-jU", executablePath]

        let stdout = Pipe()
        process.standardOutput = stdout
        process.standardError = FileHandle.nullDevice
        try process.run()
        let data = stdout.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        let output = String(decoding: data, as: UTF8.self)
        #expect(process.terminationStatus == 0)
        #expect(output.contains("OBJC_CLASS_$_"))
        #expect(output.contains("TrampolineModelFactory"))
    }

    @Test("mlx-swift-lm model factory includes qwen3_5 registration")
    func mlxSwiftLMModelFactoryIncludesQwen35Registration() throws {
        let modelFactoryPath = try #require(resolveMLXLLMModelFactoryPath())
        let source = try String(contentsOfFile: modelFactoryPath, encoding: .utf8)
        #expect(source.contains("qwen3_5"))
    }

    private func resolveBootstrapExecutablePath() -> String? {
        let bundleDirectory = Bundle.main.bundleURL.deletingLastPathComponent()
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let candidates = [
            bundleDirectory.appendingPathComponent("melix-text-worker-swift").path,
            packageRoot.appendingPathComponent(".build/debug/melix-text-worker-swift").path,
            packageRoot.appendingPathComponent(".build/arm64-apple-macosx/debug/melix-text-worker-swift").path,
        ]

        for absolutePath in candidates {
            if FileManager.default.isExecutableFile(atPath: absolutePath) {
                return absolutePath
            }
        }

        return nil
    }

    private func resolveMLXLLMModelFactoryPath() -> String? {
        let packageRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let candidates = [
            packageRoot.appendingPathComponent(
                ".build/checkouts/mlx-swift-lm/Libraries/MLXLLM/LLMModelFactory.swift"
            ).path,
            packageRoot.appendingPathComponent(
                ".build/checkouts/mlx-swift-lm/Sources/MLXLLM/LLMModelFactory.swift"
            ).path,
        ]

        for absolutePath in candidates where FileManager.default.fileExists(atPath: absolutePath) {
            return absolutePath
        }

        return nil
    }
}
