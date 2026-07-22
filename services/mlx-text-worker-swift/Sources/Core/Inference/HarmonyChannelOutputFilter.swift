import Foundation
import MelixWorkerProtocol

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

    enum Framing: Equatable, Sendable {
        case markerTerminatedHeader
        case newlineDelimitedBody
    }

    private static let openMarker = "<|channel>"
    private static let headerCloseMarker = "<channel|>"
    private static let hiddenChannels: Set<String> = ["analysis", "thought", "reasoning"]
    private static let visibleChannels: Set<String> = ["commentary", "final"]

    private let framing: Framing
    private var mode: Mode = .visible
    private var buffer = ""
    private var isInsideChannelBody = false
    private var mayConsumeLeadingHeader = false

    init(framing: Framing = .markerTerminatedHeader) {
        self.framing = framing
    }

    init(
        execution: Melix_Worker_V1_ExecutionMetadata,
        fallbackExecution: Melix_Worker_V1_ExecutionMetadata? = nil,
        fallbackParserMode: String? = nil
    ) {
        self.framing = Self.framing(
            for: execution,
            fallbackExecution: fallbackExecution,
            fallbackParserMode: fallbackParserMode
        )
        // Gemma's thinking template activates reasoning in the system turn but
        // leaves the model turn without a prefilled channel opener. The model
        // can therefore begin with reasoning body text and emit only the close
        // marker before its public answer. The execution receipt establishes
        // that initial channel without changing non-thinking requests.
        if framing == .newlineDelimitedBody,
           execution.reasoning.enabled || fallbackExecution?.reasoning.enabled == true {
            mode = .hidden
            isInsideChannelBody = true
            mayConsumeLeadingHeader = true
        }
    }

    static func framing(
        for execution: Melix_Worker_V1_ExecutionMetadata,
        fallbackExecution: Melix_Worker_V1_ExecutionMetadata? = nil,
        fallbackParserMode: String? = nil
    ) -> Framing {
        var candidates = parserModes(from: execution)
        if let fallbackExecution {
            candidates.append(contentsOf: parserModes(from: fallbackExecution))
        }
        if let fallbackParserMode {
            candidates.append(fallbackParserMode)
        }
        return candidates.contains(where: isGemmaParserMode)
            ? .newlineDelimitedBody
            : .markerTerminatedHeader
    }

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
        switch framing {
        case .markerTerminatedHeader:
            return drainMarkerTerminatedHeader(final: final)
        case .newlineDelimitedBody:
            return drainNewlineDelimitedBody(final: final)
        }
    }

    private mutating func drainMarkerTerminatedHeader(final: Bool) -> Output {
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

    private mutating func drainNewlineDelimitedBody(final: Bool) -> Output {
        var output = Output()

        while !buffer.isEmpty {
            if isInsideChannelBody {
                if mayConsumeLeadingHeader {
                    if buffer.count < Self.openMarker.count,
                       Self.openMarker.hasPrefix(buffer),
                       final == false {
                        break
                    }
                    if buffer.hasPrefix(Self.openMarker) {
                        let headerStart = buffer.index(
                            buffer.startIndex,
                            offsetBy: Self.openMarker.count
                        )
                        guard let newline = buffer[headerStart...].firstIndex(of: "\n") else {
                            if final {
                                buffer.removeAll(keepingCapacity: true)
                            }
                            break
                        }
                        mode = Self.mode(for: String(buffer[headerStart..<newline]))
                        buffer.removeSubrange(buffer.startIndex...newline)
                        mayConsumeLeadingHeader = false
                        continue
                    }
                    mayConsumeLeadingHeader = false
                }

                if let closeRange = buffer.range(of: Self.headerCloseMarker) {
                    append(String(buffer[..<closeRange.lowerBound]), to: &output)
                    buffer.removeSubrange(buffer.startIndex..<closeRange.upperBound)
                    isInsideChannelBody = false
                    mode = .visible
                    continue
                }

                let heldSuffix = Self.partialMarkerSuffix(
                    in: buffer,
                    marker: Self.headerCloseMarker
                )
                let prefixEnd = buffer.index(buffer.endIndex, offsetBy: -heldSuffix.count)
                append(String(buffer[..<prefixEnd]), to: &output)
                buffer = final ? "" : heldSuffix
                break
            }

            guard let markerRange = buffer.range(of: Self.openMarker) else {
                let heldSuffix = Self.partialMarkerSuffix(in: buffer, marker: Self.openMarker)
                let prefixEnd = buffer.index(buffer.endIndex, offsetBy: -heldSuffix.count)
                append(String(buffer[..<prefixEnd]), to: &output)
                buffer = final ? "" : heldSuffix
                break
            }

            if markerRange.lowerBound > buffer.startIndex {
                append(String(buffer[..<markerRange.lowerBound]), to: &output)
                buffer.removeSubrange(..<markerRange.lowerBound)
                continue
            }

            let headerStart = buffer.index(buffer.startIndex, offsetBy: Self.openMarker.count)
            guard let newline = buffer[headerStart...].firstIndex(of: "\n") else {
                if final {
                    buffer.removeAll(keepingCapacity: true)
                }
                break
            }

            mode = Self.mode(for: String(buffer[headerStart..<newline]))
            buffer.removeSubrange(buffer.startIndex...newline)
            isInsideChannelBody = true
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
        partialMarkerSuffix(in: text, marker: openMarker)
    }

    private static func partialMarkerSuffix(in text: String, marker: String) -> String {
        guard !text.isEmpty else {
            return ""
        }
        var candidate = ""
        for length in 1..<marker.count {
            let start = text.index(text.endIndex, offsetBy: -min(length, text.count))
            let suffix = String(text[start...])
            if marker.hasPrefix(suffix) {
                candidate = suffix
            }
        }
        return candidate
    }

    private static func parserModes(
        from execution: Melix_Worker_V1_ExecutionMetadata
    ) -> [String] {
        [
            execution.scope.parserMode,
            execution.scope.toolParserMode,
            execution.ext["melix.tool_parser.mode"],
        ].compactMap { $0 }
    }

    private static func isGemmaParserMode(_ value: String) -> Bool {
        let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return normalized == "gemma"
            || normalized.hasPrefix("gemma-")
            || normalized.hasPrefix("gemma_")
            || normalized.hasPrefix("gemma4")
    }
}
