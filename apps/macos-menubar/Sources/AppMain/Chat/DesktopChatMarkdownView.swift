import Foundation
import Markdown
import AppKit
import SwiftUI
import MelixControlPlaneCore

enum DesktopChatMarkdownLayoutMetrics {
    static let blockSpacing: CGFloat = MelixDesignTokens.Spacing.sm
    static let listRowSpacing: CGFloat = 4
    static let codeBlockPadding: CGFloat = MelixDesignTokens.Spacing.md
    static let codeBlockHeaderSpacing: CGFloat = MelixDesignTokens.Spacing.sm
    static let codeBlockLineSpacing: CGFloat = 3
    static let codeBlockBackgroundOpacity: Double = 0.03
    static let codeBlockBorderOpacity: Double = 0.05
    static let codeBlockBadgeBackgroundOpacity: Double = 0.055
    static let tableSurfaceBackgroundOpacity: Double = 0.018
    static let tableHeaderBackgroundOpacity: Double = 0.035
    static let tableRowSeparatorOpacity: Double = 0.04
    static let tableColumnSeparatorOpacity: Double = 0.035
    static let tableCellHorizontalPadding: CGFloat = MelixDesignTokens.Spacing.sm
    static let tableCellVerticalPadding: CGFloat = 6
    static let tableColumnMinWidth: CGFloat = 88
    static let tableColumnMaxWidth: CGFloat = 260
    static let tableCellMaximumLineCount: Int = 4
    static let tableCellTruncationCharacterCount: Int = 96
    static let lazyRenderBlockThreshold: Int = 96
    static let lazyRenderCharacterThreshold: Int = 24_000
    static let renderChunkTargetCharacterCount: Int = 2_000
}

enum DesktopChatMarkdownTableAlignment: Equatable, Sendable {
    case none
    case leading
    case center
    case trailing
}

struct DesktopChatMarkdownListItem: Equatable, Sendable {
    let text: String
    let children: [DesktopChatMarkdownBlock]

    init(text: String, children: [DesktopChatMarkdownBlock] = []) {
        self.text = text
        self.children = children
    }
}

indirect enum DesktopChatMarkdownBlock: Equatable, Sendable {
    case paragraph(String)
    case heading(level: Int, text: String)
    case blockQuote([DesktopChatMarkdownBlock])
    case unorderedList([DesktopChatMarkdownListItem])
    case orderedList(start: Int, items: [DesktopChatMarkdownListItem])
    case codeBlock(language: String, code: String)
    case table(header: [String], alignments: [DesktopChatMarkdownTableAlignment], rows: [[String]])
    case thematicBreak
}

struct DesktopChatMarkdownCacheStats: Equatable, Sendable {
    let parseHitCount: Int
    let parseMissCount: Int
    let inlineHitCount: Int
    let inlineMissCount: Int
    let chunkHitCount: Int
    let chunkMissCount: Int
    let stableChunkReuseCount: Int
    let evictionCount: Int
    let latestParseDurationMS: Double
}

enum DesktopChatMarkdownRenderPlanMode: Equatable, Sendable {
    case complete
    case streaming
}

struct DesktopChatMarkdownRenderChunk: Equatable, Sendable {
    let source: String
    let blocks: [DesktopChatMarkdownBlock]
    let isStable: Bool
}

struct DesktopChatMarkdownRenderPlan: Equatable, Sendable {
    let chunks: [DesktopChatMarkdownRenderChunk]
    let usesLazyRendering: Bool

    var blocks: [DesktopChatMarkdownBlock] {
        chunks.flatMap(\.blocks)
    }
}

struct DesktopChatMarkdownCodeBlockPresentation: Equatable, Sendable {
    let languageBadge: String
    let copyAccessibilityLabel: String
    let highlightedCode: AttributedString

    init(language: String, code: String) {
        self.languageBadge = DesktopChatMarkdownCodeLanguage.badge(for: language)
        self.copyAccessibilityLabel = "Copy code"
        self.highlightedCode = DesktopChatMarkdownCodeSyntaxHighlighter.attributedString(
            code: code,
            language: language
        )
    }
}

enum DesktopChatMarkdownCodeBlockClipboard {
    static func copy(_ code: String, to pasteboard: NSPasteboard = .general) {
        pasteboard.clearContents()
        pasteboard.setString(code, forType: .string)
    }
}

struct DesktopChatMarkdownTableLayout: Equatable, Sendable {
    let columnWidths: [CGFloat]

    init(header: [String], rows: [[String]]) {
        let columnCount = max(header.count, rows.map(\.count).max() ?? 0, 1)
        self.columnWidths = (0..<columnCount).map { column in
            let cells = [header[safe: column] ?? ""] + rows.map { $0[safe: column] ?? "" }
            let longest = cells.map(\.count).max() ?? 0
            let rawWidth = CGFloat(longest * 7) + (DesktopChatMarkdownLayoutMetrics.tableCellHorizontalPadding * 2)
            return min(
                max(rawWidth, DesktopChatMarkdownLayoutMetrics.tableColumnMinWidth),
                DesktopChatMarkdownLayoutMetrics.tableColumnMaxWidth
            )
        }
    }

    func lineLimit(for text: String) -> Int? {
        text.count > DesktopChatMarkdownLayoutMetrics.tableCellTruncationCharacterCount
            ? DesktopChatMarkdownLayoutMetrics.tableCellMaximumLineCount
            : nil
    }
}

enum DesktopChatMarkdownInlineFormatter {
    static func attributedString(from rawText: String) -> AttributedString {
        attributedString(fromSanitized: RichOutputSanitizer.sanitized(rawText))
    }

    static func attributedString(fromSanitized text: String) -> AttributedString {
        DesktopChatMarkdownRenderer.cachedInlineAttributedString(fromSanitized: text)
    }
}

enum DesktopChatMarkdownCodeLanguage {
    static func badge(for language: String) -> String {
        let normalized = language
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        switch normalized {
        case "swift":
            return "Swift"
        case "json":
            return "JSON"
        case "js", "javascript":
            return "JavaScript"
        case "ts", "typescript":
            return "TypeScript"
        case "sh", "shell", "bash", "zsh":
            return "Shell"
        case "py", "python":
            return "Python"
        case "diff", "patch":
            return "Diff"
        case "":
            return "Plain Text"
        default:
            return normalized.uppercased()
        }
    }
}

enum DesktopChatMarkdownCodeSyntaxHighlighter {
    private static let swiftKeywords: Set<String> = [
        "actor", "as", "async", "await", "case", "catch", "class", "else",
        "enum", "false", "for", "func", "guard", "if", "import", "in",
        "let", "nil", "private", "public", "return", "static", "struct",
        "switch", "throw", "throws", "true", "try", "var", "while",
    ]

    private static let shellKeywords: Set<String> = [
        "awk", "bun", "cd", "curl", "echo", "export", "git", "grep",
        "make", "mkdir", "rg", "sed", "swift", "xcrun",
    ]

    static func attributedString(code: String, language: String) -> AttributedString {
        let normalized = language.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if normalized == "json" {
            return highlightedJSON(code)
        }
        if ["sh", "shell", "bash", "zsh"].contains(normalized) {
            return highlightedWords(code, keywords: shellKeywords)
        }
        if ["swift", "js", "javascript", "ts", "typescript", "py", "python"].contains(normalized) {
            return highlightedWords(code, keywords: swiftKeywords)
        }
        if ["diff", "patch"].contains(normalized) {
            return highlightedDiff(code)
        }
        return AttributedString(code)
    }

    private static func highlightedJSON(_ code: String) -> AttributedString {
        build(code) { token in
            if token.hasPrefix("\"") {
                return .teal
            }
            if ["true", "false", "null"].contains(token) || token.first?.isNumber == true {
                return .purple
            }
            return nil
        }
    }

    private static func highlightedWords(
        _ code: String,
        keywords: Set<String>
    ) -> AttributedString {
        build(code) { token in
            if token.hasPrefix("//") || token.hasPrefix("#") {
                return .secondary
            }
            if token.hasPrefix("\"") || token.hasPrefix("'") {
                return .teal
            }
            if keywords.contains(token) {
                return .purple
            }
            if token.first?.isNumber == true {
                return .orange
            }
            return nil
        }
    }

    private static func highlightedDiff(_ code: String) -> AttributedString {
        var result = AttributedString()
        let lines = code.split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
        for (index, lineText) in lines.enumerated() {
            var segment = AttributedString(lineText)
            if lineText.hasPrefix("+") {
                segment.foregroundColor = .green
            } else if lineText.hasPrefix("-") {
                segment.foregroundColor = .red
            } else if lineText.hasPrefix("@@") {
                segment.foregroundColor = .purple
            }
            result += segment
            if index < lines.count - 1 {
                result += AttributedString("\n")
            }
        }
        return result
    }

    private static func build(
        _ code: String,
        colorForToken: (String) -> Color?
    ) -> AttributedString {
        var result = AttributedString()
        var current = ""
        var currentIsToken: Bool?

        func appendCurrent() {
            guard current.isEmpty == false else {
                return
            }
            var segment = AttributedString(current)
            if currentIsToken == true, let color = colorForToken(current) {
                segment.foregroundColor = color
            }
            result += segment
            current = ""
        }

        for scalar in code.unicodeScalars {
            let character = Character(scalar)
            let isToken = CharacterSet.alphanumerics.contains(scalar)
                || scalar == "_"
                || scalar == "\""
                || scalar == "'"
                || scalar == "/"
                || scalar == "#"
            if currentIsToken == nil {
                currentIsToken = isToken
            } else if currentIsToken != isToken {
                appendCurrent()
                currentIsToken = isToken
            }
            current.append(character)
        }
        appendCurrent()

        return result
    }
}

enum DesktopChatMarkdownRenderer {
    private static let cache = DesktopChatMarkdownRenderCache()

    static func usesMarkdown(for kind: DesktopChatTranscriptEntry.Kind) -> Bool {
        switch kind {
        case .assistant, .reasoning:
            return true
        case .user, .tool, .error:
            return false
        }
    }

    static func blocks(from rawText: String) -> [DesktopChatMarkdownBlock] {
        let sanitized = RichOutputSanitizer.sanitized(rawText)
        return cache.blocks(for: sanitized) {
            parseBlocks(fromSanitized: sanitized)
        }
    }

    static func renderPlan(
        from rawText: String,
        mode: DesktopChatMarkdownRenderPlanMode = .complete
    ) -> DesktopChatMarkdownRenderPlan {
        let sanitized = RichOutputSanitizer.sanitized(rawText)
        let sourceChunks = DesktopChatMarkdownChunker.chunks(from: sanitized, mode: mode)
        let renderChunks = sourceChunks.map { sourceChunk in
            let blocks = cache.chunkBlocks(
                for: sourceChunk.source,
                isStable: sourceChunk.isStable
            ) {
                parseBlocks(fromSanitized: sourceChunk.source)
            }
            return DesktopChatMarkdownRenderChunk(
                source: sourceChunk.source,
                blocks: blocks,
                isStable: sourceChunk.isStable
            )
        }
        let blockCount = renderChunks.reduce(0) { count, chunk in
            count + chunk.blocks.count
        }
        return DesktopChatMarkdownRenderPlan(
            chunks: renderChunks,
            usesLazyRendering: renderChunks.count > 1
                || blockCount >= DesktopChatMarkdownLayoutMetrics.lazyRenderBlockThreshold
                || sanitized.count >= DesktopChatMarkdownLayoutMetrics.lazyRenderCharacterThreshold
        )
    }

    static func cachedInlineAttributedString(fromSanitized text: String) -> AttributedString {
        cache.inlineAttributedString(for: text) {
            let renderer = DesktopChatMarkdownInlineAttributedRenderer()
            return renderer.attributedString(from: Document(parsing: text))
        }
    }

    static func resetCacheForTesting(capacity: Int = 128) {
        cache.reset(capacity: capacity)
    }

    static func cacheStatsForTesting() -> DesktopChatMarkdownCacheStats {
        cache.stats()
    }

    private static func parseBlocks(fromSanitized text: String) -> [DesktopChatMarkdownBlock] {
        let document = Document(parsing: text)
        var visitor = DesktopChatMarkdownBlockVisitor()
        return visitor.visit(document)
    }
}

private struct DesktopChatMarkdownSourceChunk: Equatable, Sendable {
    let source: String
    let isStable: Bool
}

struct DesktopChatMarkdownPerformanceReport: Equatable, Sendable {
    let samples: [DesktopChatMarkdownPerformanceSample]
}

struct DesktopChatMarkdownPerformanceSample: Equatable, Sendable {
    let targetByteCount: Int
    let blockCount: Int
    let chunkCount: Int
    let firstParseDurationMS: Double
    let cachedParseDurationMS: Double
    let cacheHitDelta: Int
    let cacheMissDelta: Int
    let evictionDelta: Int
}

enum DesktopChatMarkdownPerformanceProbe {
    static func measure(sampleSizes: [Int]) -> DesktopChatMarkdownPerformanceReport {
        let samples = sampleSizes.map { targetSize in
            let source = makeSampleMarkdown(targetByteCount: targetSize)
            let before = DesktopChatMarkdownRenderer.cacheStatsForTesting()

            let firstStartedAt = Date()
            let firstPlan = DesktopChatMarkdownRenderer.renderPlan(from: source, mode: .complete)
            let firstDuration = Date().timeIntervalSince(firstStartedAt) * 1000
            let afterFirst = DesktopChatMarkdownRenderer.cacheStatsForTesting()

            let cachedStartedAt = Date()
            _ = DesktopChatMarkdownRenderer.renderPlan(from: source, mode: .complete)
            let cachedDuration = Date().timeIntervalSince(cachedStartedAt) * 1000
            let afterCached = DesktopChatMarkdownRenderer.cacheStatsForTesting()

            return DesktopChatMarkdownPerformanceSample(
                targetByteCount: targetSize,
                blockCount: firstPlan.blocks.count,
                chunkCount: firstPlan.chunks.count,
                firstParseDurationMS: max(0, firstDuration),
                cachedParseDurationMS: max(0, cachedDuration),
                cacheHitDelta: afterCached.chunkHitCount - afterFirst.chunkHitCount,
                cacheMissDelta: afterFirst.chunkMissCount - before.chunkMissCount,
                evictionDelta: afterCached.evictionCount - before.evictionCount
            )
        }
        return DesktopChatMarkdownPerformanceReport(samples: samples)
    }

    private static func makeSampleMarkdown(targetByteCount: Int) -> String {
        let section = """
        ## Benchmark Section

        A paragraph with **strong text**, _emphasis_, `inline code`, and a readable [label](https://example.com).

        - Alpha item
          - Nested beta item
        - Gamma item

        ```swift
        let value = 42
        print(value)
        ```

        | Metric | Value | Note |
        | :--- | ---: | :---: |
        | TTFT | 12 ms | cached |
        | TPS | 41 | steady |

        """
        var text = ""
        while text.utf8.count < targetByteCount {
            text += section
        }
        return text
    }
}

private enum DesktopChatMarkdownChunker {
    static func chunks(
        from sanitized: String,
        mode: DesktopChatMarkdownRenderPlanMode
    ) -> [DesktopChatMarkdownSourceChunk] {
        guard sanitized.count > DesktopChatMarkdownLayoutMetrics.renderChunkTargetCharacterCount else {
            return [
                DesktopChatMarkdownSourceChunk(source: sanitized, isStable: mode == .complete),
            ]
        }

        var chunks: [DesktopChatMarkdownSourceChunk] = []
        var current = ""
        var insideFence = false
        let lines = sanitized.split(separator: "\n", omittingEmptySubsequences: false).map(String.init)

        for (index, line) in lines.enumerated() {
            let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.hasPrefix("```") || trimmed.hasPrefix("~~~") {
                insideFence.toggle()
            }

            if current.isEmpty == false {
                current += "\n"
            }
            current += line

            let isLastLine = index == lines.count - 1
            if insideFence == false,
               current.count >= DesktopChatMarkdownLayoutMetrics.renderChunkTargetCharacterCount,
               trimmed.isEmpty,
               isLastLine == false {
                chunks.append(DesktopChatMarkdownSourceChunk(source: current, isStable: true))
                current = ""
            }
        }

        if current.isEmpty == false || chunks.isEmpty {
            chunks.append(
                DesktopChatMarkdownSourceChunk(
                    source: current,
                    isStable: mode == .complete
                )
            )
        }

        if mode == .streaming, let last = chunks.indices.last {
            chunks[last] = DesktopChatMarkdownSourceChunk(source: chunks[last].source, isStable: false)
        }

        return chunks
    }
}

private final class DesktopChatMarkdownRenderCache: @unchecked Sendable {
    private let lock = NSLock()
    private var capacity: Int
    private var parsedBlocks: [String: [DesktopChatMarkdownBlock]]
    private var parsedBlockOrder: [String]
    private var parsedChunkBlocks: [String: [DesktopChatMarkdownBlock]]
    private var parsedChunkBlockOrder: [String]
    private var inlineAttributedStrings: [String: AttributedString]
    private var inlineAttributedStringOrder: [String]
    private var parseHitCount: Int
    private var parseMissCount: Int
    private var inlineHitCount: Int
    private var inlineMissCount: Int
    private var chunkHitCount: Int
    private var chunkMissCount: Int
    private var stableChunkReuseCount: Int
    private var evictionCount: Int
    private var latestParseDurationMS: Double

    init(capacity: Int = 128) {
        self.capacity = max(1, capacity)
        self.parsedBlocks = [:]
        self.parsedBlockOrder = []
        self.parsedChunkBlocks = [:]
        self.parsedChunkBlockOrder = []
        self.inlineAttributedStrings = [:]
        self.inlineAttributedStringOrder = []
        self.parseHitCount = 0
        self.parseMissCount = 0
        self.inlineHitCount = 0
        self.inlineMissCount = 0
        self.chunkHitCount = 0
        self.chunkMissCount = 0
        self.stableChunkReuseCount = 0
        self.evictionCount = 0
        self.latestParseDurationMS = 0
    }

    func blocks(
        for key: String,
        build: () -> [DesktopChatMarkdownBlock]
    ) -> [DesktopChatMarkdownBlock] {
        lock.lock()
        if let cached = parsedBlocks[key] {
            parseHitCount += 1
            touch(key, in: &parsedBlockOrder)
            lock.unlock()
            return cached
        }
        lock.unlock()

        let startedAt = Date()
        let rendered = build()
        let duration = max(0, Date().timeIntervalSince(startedAt) * 1000)

        lock.lock()
        parseMissCount += 1
        latestParseDurationMS = duration
        parsedBlocks[key] = rendered
        touch(key, in: &parsedBlockOrder)
        evictIfNeeded()
        lock.unlock()

        return rendered
    }

    func chunkBlocks(
        for key: String,
        isStable: Bool,
        build: () -> [DesktopChatMarkdownBlock]
    ) -> [DesktopChatMarkdownBlock] {
        if isStable {
            lock.lock()
            if let cached = parsedChunkBlocks[key] {
                chunkHitCount += 1
                stableChunkReuseCount += 1
                touch(key, in: &parsedChunkBlockOrder)
                lock.unlock()
                return cached
            }
            lock.unlock()
        }

        let startedAt = Date()
        let rendered = build()
        let duration = max(0, Date().timeIntervalSince(startedAt) * 1000)

        lock.lock()
        chunkMissCount += 1
        latestParseDurationMS = duration
        if isStable {
            parsedChunkBlocks[key] = rendered
            touch(key, in: &parsedChunkBlockOrder)
            evictIfNeeded()
        }
        lock.unlock()

        return rendered
    }

    func inlineAttributedString(
        for key: String,
        build: () -> AttributedString
    ) -> AttributedString {
        lock.lock()
        if let cached = inlineAttributedStrings[key] {
            inlineHitCount += 1
            touch(key, in: &inlineAttributedStringOrder)
            lock.unlock()
            return cached
        }
        lock.unlock()

        let rendered = build()

        lock.lock()
        inlineMissCount += 1
        inlineAttributedStrings[key] = rendered
        touch(key, in: &inlineAttributedStringOrder)
        evictIfNeeded()
        lock.unlock()

        return rendered
    }

    func reset(capacity: Int) {
        lock.lock()
        self.capacity = max(1, capacity)
        parsedBlocks.removeAll()
        parsedBlockOrder.removeAll()
        parsedChunkBlocks.removeAll()
        parsedChunkBlockOrder.removeAll()
        inlineAttributedStrings.removeAll()
        inlineAttributedStringOrder.removeAll()
        parseHitCount = 0
        parseMissCount = 0
        inlineHitCount = 0
        inlineMissCount = 0
        chunkHitCount = 0
        chunkMissCount = 0
        stableChunkReuseCount = 0
        evictionCount = 0
        latestParseDurationMS = 0
        lock.unlock()
    }

    func stats() -> DesktopChatMarkdownCacheStats {
        lock.lock()
        let snapshot = DesktopChatMarkdownCacheStats(
            parseHitCount: parseHitCount,
            parseMissCount: parseMissCount,
            inlineHitCount: inlineHitCount,
            inlineMissCount: inlineMissCount,
            chunkHitCount: chunkHitCount,
            chunkMissCount: chunkMissCount,
            stableChunkReuseCount: stableChunkReuseCount,
            evictionCount: evictionCount,
            latestParseDurationMS: latestParseDurationMS
        )
        lock.unlock()
        return snapshot
    }

    private func touch(_ key: String, in order: inout [String]) {
        order.removeAll { $0 == key }
        order.append(key)
    }

    private func evictIfNeeded() {
        while parsedBlockOrder.count > capacity, let key = parsedBlockOrder.first {
            parsedBlockOrder.removeFirst()
            parsedBlocks.removeValue(forKey: key)
            evictionCount += 1
        }

        while parsedChunkBlockOrder.count > capacity, let key = parsedChunkBlockOrder.first {
            parsedChunkBlockOrder.removeFirst()
            parsedChunkBlocks.removeValue(forKey: key)
            evictionCount += 1
        }

        while inlineAttributedStringOrder.count > capacity, let key = inlineAttributedStringOrder.first {
            inlineAttributedStringOrder.removeFirst()
            inlineAttributedStrings.removeValue(forKey: key)
            evictionCount += 1
        }
    }
}

private struct DesktopChatMarkdownBlockVisitor: MarkupVisitor {
    typealias Result = [DesktopChatMarkdownBlock]

    mutating func defaultVisit(_ markup: Markup) -> [DesktopChatMarkdownBlock] {
        var blocks: [DesktopChatMarkdownBlock] = []
        for child in markup.children {
            blocks.append(contentsOf: visit(child))
        }
        return blocks
    }

    mutating func visitDocument(_ document: Document) -> [DesktopChatMarkdownBlock] {
        defaultVisit(document)
    }

    mutating func visitParagraph(_ paragraph: Paragraph) -> [DesktopChatMarkdownBlock] {
        let text = DesktopChatMarkdownInlineSourceRenderer.string(from: paragraph)
        guard text.isEmpty == false else {
            return []
        }
        return [.paragraph(text)]
    }

    mutating func visitHeading(_ heading: Heading) -> [DesktopChatMarkdownBlock] {
        let text = DesktopChatMarkdownInlineSourceRenderer.string(from: heading)
        guard text.isEmpty == false else {
            return []
        }
        return [.heading(level: heading.level, text: text)]
    }

    mutating func visitBlockQuote(_ blockQuote: BlockQuote) -> [DesktopChatMarkdownBlock] {
        let children = defaultVisit(blockQuote)
        guard children.isEmpty == false else {
            return []
        }
        return [.blockQuote(children)]
    }

    mutating func visitUnorderedList(_ unorderedList: UnorderedList) -> [DesktopChatMarkdownBlock] {
        let items = listItems(from: unorderedList)
        guard items.isEmpty == false else {
            return []
        }
        return [.unorderedList(items)]
    }

    mutating func visitOrderedList(_ orderedList: OrderedList) -> [DesktopChatMarkdownBlock] {
        let items = listItems(from: orderedList)
        guard items.isEmpty == false else {
            return []
        }
        return [.orderedList(start: Int(orderedList.startIndex), items: items)]
    }

    mutating func visitCodeBlock(_ codeBlock: CodeBlock) -> [DesktopChatMarkdownBlock] {
        [
            .codeBlock(
                language: codeBlock.language?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "",
                code: normalizedCodeBlockText(codeBlock.code)
            ),
        ]
    }

    mutating func visitThematicBreak(_ thematicBreak: ThematicBreak) -> [DesktopChatMarkdownBlock] {
        [.thematicBreak]
    }

    mutating func visitHTMLBlock(_ html: HTMLBlock) -> [DesktopChatMarkdownBlock] {
        []
    }

    mutating func visitTable(_ table: Markdown.Table) -> [DesktopChatMarkdownBlock] {
        let header = Array(table.head.cells.map { DesktopChatMarkdownInlineSourceRenderer.string(from: $0) })
        let rows = table.body.children.compactMap { child -> [String]? in
            guard let row = child as? Markdown.Table.Row else {
                return nil
            }
            return Array(row.cells.map { DesktopChatMarkdownInlineSourceRenderer.string(from: $0) })
        }
        let alignments = table.columnAlignments.map(DesktopChatMarkdownTableAlignment.init)

        return [
            .table(
                header: header,
                alignments: DesktopChatMarkdownTableAlignment.normalized(alignments, count: header.count),
                rows: rows
            ),
        ]
    }

    private mutating func listItems(from list: some ListItemContainer) -> [DesktopChatMarkdownListItem] {
        list.children.compactMap { child in
            guard let item = child as? ListItem else {
                return nil
            }
            return listItem(from: item)
        }
    }

    private mutating func listItem(from item: ListItem) -> DesktopChatMarkdownListItem {
        var textParts: [String] = []
        var childBlocks: [DesktopChatMarkdownBlock] = []

        for child in item.children {
            if let paragraph = child as? Paragraph {
                let text = DesktopChatMarkdownInlineSourceRenderer.string(from: paragraph)
                if text.isEmpty == false {
                    textParts.append(text)
                }
            } else {
                childBlocks.append(contentsOf: visit(child))
            }
        }

        return DesktopChatMarkdownListItem(
            text: textParts.joined(separator: "\n"),
            children: childBlocks
        )
    }

    private func normalizedCodeBlockText(_ code: String) -> String {
        if code.hasSuffix("\r\n") {
            return String(code.dropLast(2))
        }
        if code.hasSuffix("\n") {
            return String(code.dropLast())
        }
        return code
    }
}

private struct DesktopChatMarkdownInlineSourceRenderer: MarkupVisitor {
    typealias Result = String

    static func string(from markup: Markup) -> String {
        var renderer = DesktopChatMarkdownInlineSourceRenderer()
        return renderer.visit(markup)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    mutating func defaultVisit(_ markup: Markup) -> String {
        markup.children.map { visit($0) }.joined()
    }

    mutating func visitText(_ text: Markdown.Text) -> String {
        text.string
    }

    mutating func visitSoftBreak(_ softBreak: SoftBreak) -> String {
        " "
    }

    mutating func visitLineBreak(_ lineBreak: LineBreak) -> String {
        "\n"
    }

    mutating func visitInlineCode(_ inlineCode: InlineCode) -> String {
        "`\(inlineCode.code)`"
    }

    mutating func visitStrong(_ strong: Strong) -> String {
        "**\(defaultVisit(strong))**"
    }

    mutating func visitEmphasis(_ emphasis: Emphasis) -> String {
        "_\(defaultVisit(emphasis))_"
    }

    mutating func visitStrikethrough(_ strikethrough: Strikethrough) -> String {
        "~~\(defaultVisit(strikethrough))~~"
    }

    mutating func visitLink(_ link: Markdown.Link) -> String {
        defaultVisit(link)
    }

    mutating func visitImage(_ image: Markdown.Image) -> String {
        let altText = defaultVisit(image)
        if altText.isEmpty == false {
            return altText
        }
        return image.title ?? ""
    }

    mutating func visitInlineHTML(_ inlineHTML: InlineHTML) -> String {
        ""
    }
}

private struct DesktopChatMarkdownInlineAttributedRenderer: MarkupVisitor {
    typealias Result = AttributedString

    func attributedString(from markup: Markup) -> AttributedString {
        var renderer = self
        return renderer.visit(markup)
    }

    mutating func defaultVisit(_ markup: Markup) -> AttributedString {
        var attributed = AttributedString()
        for child in markup.children {
            attributed += visit(child)
        }
        return attributed
    }

    mutating func visitText(_ text: Markdown.Text) -> AttributedString {
        AttributedString(text.string)
    }

    mutating func visitSoftBreak(_ softBreak: SoftBreak) -> AttributedString {
        AttributedString(" ")
    }

    mutating func visitLineBreak(_ lineBreak: LineBreak) -> AttributedString {
        AttributedString("\n")
    }

    mutating func visitInlineCode(_ inlineCode: InlineCode) -> AttributedString {
        adding(.code, to: AttributedString(inlineCode.code))
    }

    mutating func visitStrong(_ strong: Strong) -> AttributedString {
        adding(.stronglyEmphasized, to: defaultVisit(strong))
    }

    mutating func visitEmphasis(_ emphasis: Emphasis) -> AttributedString {
        adding(.emphasized, to: defaultVisit(emphasis))
    }

    mutating func visitStrikethrough(_ strikethrough: Strikethrough) -> AttributedString {
        adding(.strikethrough, to: defaultVisit(strikethrough))
    }

    mutating func visitLink(_ link: Markdown.Link) -> AttributedString {
        defaultVisit(link)
    }

    mutating func visitImage(_ image: Markdown.Image) -> AttributedString {
        let altText = defaultVisit(image)
        if altText.characters.isEmpty == false {
            return altText
        }
        return AttributedString(image.title ?? "")
    }

    mutating func visitInlineHTML(_ inlineHTML: InlineHTML) -> AttributedString {
        AttributedString()
    }

    private func adding(
        _ intent: InlinePresentationIntent,
        to attributed: AttributedString
    ) -> AttributedString {
        var result = attributed
        let runs = result.runs.map { run in
            (run.range, run.inlinePresentationIntent)
        }
        for (range, existingIntent) in runs {
            let mergedIntent: InlinePresentationIntent = existingIntent ?? []
            result[range].inlinePresentationIntent = mergedIntent.union(intent)
        }
        return result
    }
}

private extension DesktopChatMarkdownTableAlignment {
    init(_ alignment: Markdown.Table.ColumnAlignment?) {
        switch alignment {
        case .left:
            self = .leading
        case .center:
            self = .center
        case .right:
            self = .trailing
        case nil:
            self = .none
        }
    }

    static func normalized(
        _ alignments: [DesktopChatMarkdownTableAlignment],
        count: Int
    ) -> [DesktopChatMarkdownTableAlignment] {
        guard count > 0 else {
            return []
        }
        if alignments.count >= count {
            return Array(alignments.prefix(count))
        }
        return alignments + Array(repeating: .none, count: count - alignments.count)
    }
}

struct DesktopChatMarkdownBodyView: View {
    let rawText: String

    private var renderPlan: DesktopChatMarkdownRenderPlan {
        DesktopChatMarkdownRenderer.renderPlan(from: rawText, mode: .streaming)
    }

    var body: some View {
        DesktopChatMarkdownRenderPlanView(plan: renderPlan)
            .frame(maxWidth: .infinity, alignment: .leading)
            .textSelection(.enabled)
    }
}

private struct DesktopChatMarkdownRenderPlanView: View {
    let plan: DesktopChatMarkdownRenderPlan

    var body: some View {
        if plan.usesLazyRendering {
            LazyVStack(alignment: .leading, spacing: DesktopChatMarkdownLayoutMetrics.blockSpacing) {
                ForEach(Array(plan.chunks.enumerated()), id: \.offset) { _, chunk in
                    DesktopChatMarkdownBlocksView(blocks: chunk.blocks)
                }
            }
        } else {
            DesktopChatMarkdownBlocksView(blocks: plan.blocks)
        }
    }
}

private struct DesktopChatMarkdownBlocksView: View {
    let blocks: [DesktopChatMarkdownBlock]

    var body: some View {
        VStack(alignment: .leading, spacing: DesktopChatMarkdownLayoutMetrics.blockSpacing) {
            ForEach(Array(blocks.enumerated()), id: \.offset) { _, block in
                blockView(block)
            }
        }
    }

    @ViewBuilder
    private func blockView(_ block: DesktopChatMarkdownBlock) -> some View {
        switch block {
        case .paragraph(let text):
            paragraphView(text)
        case .heading(let level, let text):
            headingView(level: level, text: text)
        case .blockQuote(let children):
            blockQuoteView(children)
        case .unorderedList(let items):
            unorderedListView(items)
        case .orderedList(let start, let items):
            orderedListView(start: start, items: items)
        case .codeBlock(let language, let code):
            codeBlockView(language: language, code: code)
        case .table(let header, let alignments, let rows):
            tableView(header: header, alignments: alignments, rows: rows)
        case .thematicBreak:
            thematicBreakView()
        }
    }

    private func paragraphView(_ text: String) -> some View {
        SwiftUI.Text(DesktopChatMarkdownInlineFormatter.attributedString(fromSanitized: text))
            .font(.body)
            .lineSpacing(2)
    }

    private func headingView(level: Int, text: String) -> some View {
        SwiftUI.Text(DesktopChatMarkdownInlineFormatter.attributedString(fromSanitized: text))
            .font(headingFont(level: level))
            .foregroundStyle(level == 1 ? .primary : .secondary)
            .lineSpacing(3)
            .padding(.top, headingTopPadding(level: level))
            .padding(.bottom, level == 1 ? 1 : 0)
    }

    private func blockQuoteView(_ children: [DesktopChatMarkdownBlock]) -> some View {
        HStack(alignment: .top, spacing: MelixDesignTokens.Spacing.sm) {
            Rectangle()
                .fill(Color.accentColor.opacity(0.35))
                .frame(width: 3)
            DesktopChatMarkdownBlocksView(blocks: children)
        }
        .padding(.vertical, MelixDesignTokens.Spacing.xs)
        .padding(.horizontal, MelixDesignTokens.Spacing.sm)
        .background(
            RoundedRectangle(cornerRadius: MelixDesignTokens.Radius.sm)
                .fill(Color.primary.opacity(DesktopChatMarkdownLayoutMetrics.tableSurfaceBackgroundOpacity))
        )
    }

    private func unorderedListView(_ items: [DesktopChatMarkdownListItem]) -> some View {
        VStack(alignment: .leading, spacing: DesktopChatMarkdownLayoutMetrics.listRowSpacing) {
            ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                listRow(marker: "•", item: item)
            }
        }
    }

    private func orderedListView(
        start: Int,
        items: [DesktopChatMarkdownListItem]
    ) -> some View {
        VStack(alignment: .leading, spacing: DesktopChatMarkdownLayoutMetrics.listRowSpacing) {
            ForEach(Array(items.enumerated()), id: \.offset) { index, item in
                listRow(marker: "\(start + index).", item: item)
            }
        }
    }

    private func listRow(
        marker: String,
        item: DesktopChatMarkdownListItem
    ) -> some View {
        HStack(alignment: .top, spacing: MelixDesignTokens.Spacing.sm) {
            SwiftUI.Text(marker)
                .font(.body.monospacedDigit())
                .foregroundStyle(.secondary)
                .frame(minWidth: 22, alignment: .trailing)
            VStack(alignment: .leading, spacing: DesktopChatMarkdownLayoutMetrics.listRowSpacing) {
                if item.text.isEmpty == false {
                    SwiftUI.Text(DesktopChatMarkdownInlineFormatter.attributedString(fromSanitized: item.text))
                        .font(.body)
                        .lineSpacing(2)
                }
                if item.children.isEmpty == false {
                    DesktopChatMarkdownBlocksView(blocks: item.children)
                        .padding(.top, 1)
                        .padding(.leading, MelixDesignTokens.Spacing.xs)
                }
            }
        }
    }

    private func codeBlockView(language: String, code: String) -> some View {
        let presentation = DesktopChatMarkdownCodeBlockPresentation(language: language, code: code)
        return VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.xs) {
            HStack(spacing: DesktopChatMarkdownLayoutMetrics.codeBlockHeaderSpacing) {
                SwiftUI.Text(presentation.languageBadge)
                    .font(.caption2.monospaced().weight(.semibold))
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, MelixDesignTokens.Spacing.xs)
                    .padding(.vertical, 3)
                    .background(
                        Capsule()
                            .fill(Color.primary.opacity(DesktopChatMarkdownLayoutMetrics.codeBlockBadgeBackgroundOpacity))
                    )
                Spacer(minLength: MelixDesignTokens.Spacing.sm)
                Button {
                    DesktopChatMarkdownCodeBlockClipboard.copy(code)
                } label: {
                    Image(systemName: "doc.on.doc")
                        .imageScale(.small)
                }
                .buttonStyle(.borderless)
                .help(presentation.copyAccessibilityLabel)
                .accessibilityLabel(presentation.copyAccessibilityLabel)
            }
            ScrollView(.horizontal, showsIndicators: true) {
                SwiftUI.Text(code.isEmpty ? AttributedString(" ") : presentation.highlightedCode)
                    .font(.caption.monospaced())
                    .lineSpacing(DesktopChatMarkdownLayoutMetrics.codeBlockLineSpacing)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .padding(DesktopChatMarkdownLayoutMetrics.codeBlockPadding)
        .background(
            RoundedRectangle(cornerRadius: MelixDesignTokens.Radius.sm)
                .fill(Color.primary.opacity(DesktopChatMarkdownLayoutMetrics.codeBlockBackgroundOpacity))
        )
        .overlay(
            RoundedRectangle(cornerRadius: MelixDesignTokens.Radius.sm)
                .stroke(
                    Color.primary.opacity(DesktopChatMarkdownLayoutMetrics.codeBlockBorderOpacity),
                    lineWidth: 1
                )
        )
    }

    private func tableView(
        header: [String],
        alignments: [DesktopChatMarkdownTableAlignment],
        rows: [[String]]
    ) -> some View {
        let columnCount = max(header.count, rows.map(\.count).max() ?? 0, 1)
        let normalizedAlignments = DesktopChatMarkdownTableAlignment.normalized(alignments, count: columnCount)
        let layout = DesktopChatMarkdownTableLayout(header: header, rows: rows)
        return ScrollView(.horizontal, showsIndicators: true) {
            Grid(alignment: .leading, horizontalSpacing: 0, verticalSpacing: 0) {
                GridRow {
                    ForEach(0..<columnCount, id: \.self) { column in
                        tableCellView(
                            text: header[safe: column] ?? "",
                            width: layout.columnWidths[column],
                            lineLimit: layout.lineLimit(for: header[safe: column] ?? ""),
                            alignment: normalizedAlignments[column],
                            isHeader: true,
                            showsTrailingSeparator: column < columnCount - 1,
                            showsBottomSeparator: true
                        )
                    }
                }
                ForEach(rows.indices, id: \.self) { rowIndex in
                    GridRow {
                        let row = normalizedTableRow(rows[rowIndex], columnCount: columnCount)
                        ForEach(0..<columnCount, id: \.self) { column in
                            tableCellView(
                                text: row[column],
                                width: layout.columnWidths[column],
                                lineLimit: layout.lineLimit(for: row[column]),
                                alignment: normalizedAlignments[column],
                                isHeader: false,
                                showsTrailingSeparator: column < columnCount - 1,
                                showsBottomSeparator: rowIndex < rows.count - 1
                            )
                        }
                    }
                }
            }
            .fixedSize(horizontal: true, vertical: false)
            .background(
                RoundedRectangle(cornerRadius: MelixDesignTokens.Radius.sm)
                    .fill(Color.primary.opacity(DesktopChatMarkdownLayoutMetrics.tableSurfaceBackgroundOpacity))
            )
            .overlay(
                RoundedRectangle(cornerRadius: MelixDesignTokens.Radius.sm)
                    .stroke(
                        Color.primary.opacity(DesktopChatMarkdownLayoutMetrics.codeBlockBorderOpacity),
                        lineWidth: 1
                    )
            )
        }
    }

    private func tableCellView(
        text: String,
        width: CGFloat,
        lineLimit: Int?,
        alignment: DesktopChatMarkdownTableAlignment,
        isHeader: Bool,
        showsTrailingSeparator: Bool,
        showsBottomSeparator: Bool
    ) -> some View {
        ZStack(alignment: .topLeading) {
            if isHeader {
                Rectangle()
                    .fill(Color.primary.opacity(DesktopChatMarkdownLayoutMetrics.tableHeaderBackgroundOpacity))
            }
            SwiftUI.Text(DesktopChatMarkdownInlineFormatter.attributedString(fromSanitized: text))
                .font(isHeader ? .caption.weight(.semibold) : .caption)
                .multilineTextAlignment(alignment.textAlignment)
                .lineLimit(lineLimit)
                .truncationMode(.tail)
                .padding(.horizontal, DesktopChatMarkdownLayoutMetrics.tableCellHorizontalPadding)
                .padding(.vertical, DesktopChatMarkdownLayoutMetrics.tableCellVerticalPadding)
                .frame(width: width, alignment: alignment.frameAlignment)
        }
        .overlay(alignment: .bottom) {
            if showsBottomSeparator {
                Rectangle()
                    .fill(Color.primary.opacity(DesktopChatMarkdownLayoutMetrics.tableRowSeparatorOpacity))
                    .frame(height: 1)
            }
        }
        .overlay(alignment: .trailing) {
            if showsTrailingSeparator {
                Rectangle()
                    .fill(Color.primary.opacity(DesktopChatMarkdownLayoutMetrics.tableColumnSeparatorOpacity))
                    .frame(width: 1)
            }
        }
    }

    private func thematicBreakView() -> some View {
        Rectangle()
            .fill(Color.primary.opacity(DesktopChatMarkdownLayoutMetrics.tableRowSeparatorOpacity))
            .frame(height: 1)
            .padding(.vertical, MelixDesignTokens.Spacing.xs)
    }

    private func headingFont(level: Int) -> Font {
        switch level {
        case 1:
            return .title3.weight(.semibold)
        case 2:
            return .headline
        default:
            return .subheadline.weight(.semibold)
        }
    }

    private func headingTopPadding(level: Int) -> CGFloat {
        switch level {
        case 1:
            return MelixDesignTokens.Spacing.sm
        case 2:
            return MelixDesignTokens.Spacing.xs
        default:
            return 0
        }
    }

    private func normalizedTableRow(_ row: [String], columnCount: Int) -> [String] {
        if row.count >= columnCount {
            return Array(row.prefix(columnCount))
        }
        return row + Array(repeating: "", count: columnCount - row.count)
    }
}

private extension DesktopChatMarkdownTableAlignment {
    var frameAlignment: Alignment {
        switch self {
        case .none, .leading:
            return .leading
        case .center:
            return .center
        case .trailing:
            return .trailing
        }
    }

    var textAlignment: TextAlignment {
        switch self {
        case .none, .leading:
            return .leading
        case .center:
            return .center
        case .trailing:
            return .trailing
        }
    }
}

private extension Array {
    subscript(safe index: Index) -> Element? {
        indices.contains(index) ? self[index] : nil
    }
}
