import Foundation
import MelixCLICore

public protocol LoraTrainingJobStoring: Sendable {
    func list() throws -> [LoraTrainingJobRecord]
    func get(id: String) throws -> LoraTrainingJobRecord?
    func save(_ record: LoraTrainingJobRecord) throws -> LoraTrainingJobRecord
    func createDraft(title: String, config: LoraTrainingJobConfig) throws -> LoraTrainingJobRecord
    func duplicate(id: String) throws -> LoraTrainingJobRecord
    func delete(id: String) throws
    func importConfig(from fileURL: URL) throws -> LoraTrainingJobConfig
    func exportConfig(_ config: LoraTrainingJobConfig, to fileURL: URL) throws
}

extension LoraTrainingJobStore: LoraTrainingJobStoring {}

public struct NullLoraTrainingJobStore: LoraTrainingJobStoring {
    public init() {}

    public func list() throws -> [LoraTrainingJobRecord] {
        []
    }

    public func get(id: String) throws -> LoraTrainingJobRecord? {
        _ = id
        return nil
    }

    public func save(_ record: LoraTrainingJobRecord) throws -> LoraTrainingJobRecord {
        record
    }

    public func createDraft(title: String, config: LoraTrainingJobConfig) throws -> LoraTrainingJobRecord {
        let now = Date()
        return LoraTrainingJobRecord(
            id: "lora-job-\(UUID().uuidString.prefix(8).lowercased())",
            title: title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? config.adapterName : title,
            config: config,
            status: .draft,
            createdAt: now,
            updatedAt: now
        )
    }

    public func duplicate(id: String) throws -> LoraTrainingJobRecord {
        throw MelixCLIError.missingRequired("LoRA training job \(id) was not found.")
    }

    public func delete(id: String) throws {
        _ = id
    }

    public func importConfig(from fileURL: URL) throws -> LoraTrainingJobConfig {
        let data = try Data(contentsOf: fileURL)
        return try JSONDecoder().decode(LoraTrainingJobConfig.self, from: data)
    }

    public func exportConfig(_ config: LoraTrainingJobConfig, to fileURL: URL) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        try encoder.encode(config).write(to: fileURL)
    }
}
