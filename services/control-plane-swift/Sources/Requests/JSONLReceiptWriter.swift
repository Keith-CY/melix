import Foundation

final class JSONLReceiptWriter: @unchecked Sendable {
    private let url: URL
    private let queue: DispatchQueue

    init(path: String) {
        self.url = URL(fileURLWithPath: path)
        self.queue = DispatchQueue(label: "dev.melix.receipts.jsonl.\(UUID().uuidString)", qos: .utility)
    }

    func append(_ data: Data) {
        queue.async { [url] in
            appendLine(data, to: url)
        }
    }
}

private func appendLine(_ data: Data, to url: URL) {
    do {
        try FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        if !FileManager.default.fileExists(atPath: url.path) {
            FileManager.default.createFile(atPath: url.path, contents: nil)
        }
        let handle = try FileHandle(forWritingTo: url)
        defer { try? handle.close() }
        try handle.seekToEnd()
        try handle.write(contentsOf: data)
        try handle.write(contentsOf: Data("\n".utf8))
    } catch {
        return
    }
}
