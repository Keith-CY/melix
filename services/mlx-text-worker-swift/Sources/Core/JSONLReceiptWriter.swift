import Darwin
import Foundation

// NOTE: Keep this in sync with services/control-plane-swift/Sources/Requests/JSONLReceiptWriter.swift.
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
    } catch {
        return
    }
    let fd = open(url.path, O_WRONLY | O_CREAT | O_APPEND, 0o644)
    guard fd >= 0 else {
        return
    }
    defer {
        close(fd)
    }
    var line = data
    line.append(0x0A)
    line.withUnsafeBytes { buffer in
        guard let baseAddress = buffer.baseAddress else {
            return
        }
        var offset = 0
        while true {
            let written = Darwin.write(fd, baseAddress.advanced(by: offset), buffer.count - offset)
            if written > 0 {
                offset += written
            }
            if offset == buffer.count {
                return
            }
            if written < 0, errno == EINTR {
                continue
            }
            return
        }
    }
}
