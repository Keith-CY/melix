import Darwin.Mach
import Foundation
import MelixWorkerProtocol

struct LoadedTextModel: @unchecked Sendable {
    let storage: Any
    let residentBytesHint: UInt64

    init(storage: Any, residentBytesHint: UInt64 = 0) {
        self.storage = storage
        self.residentBytesHint = residentBytesHint
    }
}

struct RuntimeLoadResult: Sendable {
    let model: LoadedTextModel
    let estimatedResidentBytes: UInt64
}

protocol TextRuntimeBackend: Sendable {
    var runtimeName: String { get }
    func loadModel(spec: Melix_Worker_V1_ModelSpec) async throws -> LoadedTextModel
    func unloadModel(_ model: LoadedTextModel) async
}

extension TextRuntimeBackend {
    func unloadModel(_ model: LoadedTextModel) async {}
}

struct TextRuntime: Sendable {
    let backend: any TextRuntimeBackend
    private let residentMemoryReader: @Sendable () -> UInt64

    init(
        backend: some TextRuntimeBackend = AutoSwiftMLXBackend(),
        residentMemoryReader: @escaping @Sendable () -> UInt64 = processResidentMemoryBytes
    ) {
        self.backend = backend
        self.residentMemoryReader = residentMemoryReader
    }

    var runtimeName: String {
        backend.runtimeName
    }

    func loadModel(spec: Melix_Worker_V1_ModelSpec) async throws -> RuntimeLoadResult {
        let residentBefore = residentMemoryReader()
        let loadedModel = try await backend.loadModel(spec: spec)
        let residentAfter = residentMemoryReader()
        let residentDelta = residentAfter >= residentBefore ? residentAfter - residentBefore : 0
        return RuntimeLoadResult(
            model: loadedModel,
            estimatedResidentBytes: max(residentDelta, loadedModel.residentBytesHint)
        )
    }

    func unloadModel(_ model: LoadedTextModel) async {
        await backend.unloadModel(model)
    }
}

private func processResidentMemoryBytes() -> UInt64 {
    var info = mach_task_basic_info()
    var count = mach_msg_type_number_t(MemoryLayout<mach_task_basic_info_data_t>.size / MemoryLayout<natural_t>.size)
    let result: kern_return_t = withUnsafeMutablePointer(to: &info) { pointer in
        pointer.withMemoryRebound(to: integer_t.self, capacity: Int(count)) { rebound in
            task_info(mach_task_self_, task_flavor_t(MACH_TASK_BASIC_INFO), rebound, &count)
        }
    }

    guard result == KERN_SUCCESS else {
        return 0
    }
    return UInt64(info.resident_size)
}
