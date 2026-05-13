import Foundation

struct HarmonyChannelOutputFilter: Sendable {
    struct Output: Equatable {
        var visibleText: String = ""
        var reasoningText: String = ""
    }

    enum Mode: Equatable {
        case visible
        case hidden
        case unknown
    }

    private static let openMarker = "<|channel>"
    private static let headerCloseMarker = "<channel|>"
    private static let hiddenChannels: Set<String> = ["analysis", "thought", "reasoning"]
    private static let visibleChannels: Set<String> = ["commentary", "final"]

    private var mode: Mode = .visible
    private var buffer = ""

    mutating func accept(_ text: String, final: Bool = false) -> Output {
        guard !text.isEmpty || final else {
            return Output()
        }
        buffer += text
        return drain(final: final)
    }

    mutating func finish() -> Output {
        drain(final: true)
    }

    private mutating func drain(final: Bool) -> Output {
        var output = Output()

        while !buffer.isEmpty {
            guard let markerRange = buffer.range(of: Self.openMarker) else {
                let heldSuffix = final ? "" : Self.partialOpenMarkerSuffix(in: buffer)
                if !heldSuffix.isEmpty {
                    let prefixEnd = buffer.index(buffer.endIndex, offsetBy: -heldSuffix.count)
                    let prefix = String(buffer[..<prefixEnd])
                    append(prefix, to: &output)
                    buffer = heldSuffix
                    break
                }
                append(buffer, to: &output)
                buffer.removeAll(keepingCapacity: true)
                break
            }

            if markerRange.lowerBound > buffer.startIndex {
                let prefix = String(buffer[..<markerRange.lowerBound])
                append(prefix, to: &output)
                buffer.removeSubrange(..<markerRange.lowerBound)
                continue
            }

            guard let headerCloseRange = buffer.range(
                of: Self.headerCloseMarker,
                range: buffer.index(buffer.startIndex, offsetBy: Self.openMarker.count)..<buffer.endIndex
            ) else {
                if final {
                    buffer.removeAll(keepingCapacity: true)
                }
                break
            }

            let headerStart = buffer.index(buffer.startIndex, offsetBy: Self.openMarker.count)
            let header = String(buffer[headerStart..<headerCloseRange.lowerBound])
            mode = Self.mode(for: header)
            buffer.removeSubrange(buffer.startIndex..<headerCloseRange.upperBound)
        }

        return output
    }

    private mutating func append(_ text: String, to output: inout Output) {
        switch mode {
        case .visible:
            output.visibleText += text
        case .hidden:
            output.reasoningText += text
        case .unknown:
            break
        }
    }

    private static func mode(for header: String) -> Mode {
        guard let channel = header
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .split(whereSeparator: { $0.isWhitespace })
            .first?
            .lowercased()
        else {
            return .unknown
        }
        if visibleChannels.contains(channel) {
            return .visible
        }
        if hiddenChannels.contains(channel) {
            return .hidden
        }
        return .unknown
    }

    private static func partialOpenMarkerSuffix(in text: String) -> String {
        guard !text.isEmpty else {
            return ""
        }
        var candidate = ""
        for length in 1..<openMarker.count {
            let start = text.index(text.endIndex, offsetBy: -min(length, text.count))
            let suffix = String(text[start...])
            if openMarker.hasPrefix(suffix) {
                candidate = suffix
            }
        }
        return candidate
    }
}
