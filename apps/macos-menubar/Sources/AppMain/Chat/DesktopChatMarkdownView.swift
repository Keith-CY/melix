import Foundation
import Markdown
import SwiftUI
import MelixControlPlaneCore

enum DesktopChatMarkdownLayoutMetrics {
    static let blockSpacing: CGFloat = MelixDesignTokens.Spacing.sm
    static let listRowSpacing: CGFloat = 4
    static let codeBlockPadding: CGFloat = MelixDesignTokens.Spacing.md
    static let codeBlockLineSpacing: CGFloat = 3
    static let codeBlockBackgroundOpacity: Double = 0.03
    static let codeBlockBorderOpacity: Double = 0.05
    static let tableSurfaceBackgroundOpacity: Double = 0.018
    static let tableHeaderBackgroundOpacity: Double = 0.035
    static let tableRowSeparatorOpacity: Double = 0.04
    static let tableColumnSeparatorOpacity: Double = 0.035
    static let tableCellHorizontalPadding: CGFloat = MelixDesignTokens.Spacing.sm
    static let tableCellVerticalPadding: CGFloat = 6
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
    let evictionCount: Int
    let latestParseDurationMS: Double
}

enum DesktopChatMarkdownInlineFormatter {
    static func attributedString(from rawText: String) -> AttributedString {
        attributedString(fromSanitized: RichOutputSanitizer.sanitized(rawText))
    }

    static func attributedString(fromSanitized text: String) -> AttributedString {
        DesktopChatMarkdownRenderer.cachedInlineAttributedString(fromSanitized: text)
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

private final class DesktopChatMarkdownRenderCache: @unchecked Sendable {
    private let lock = NSLock()
    private var capacity: Int
    private var parsedBlocks: [String: [DesktopChatMarkdownBlock]]
    private var parsedBlockOrder: [String]
    private var inlineAttributedStrings: [String: AttributedString]
    private var inlineAttributedStringOrder: [String]
    private var parseHitCount: Int
    private var parseMissCount: Int
    private var inlineHitCount: Int
    private var inlineMissCount: Int
    private var evictionCount: Int
    private var latestParseDurationMS: Double

    init(capacity: Int = 128) {
        self.capacity = max(1, capacity)
        self.parsedBlocks = [:]
        self.parsedBlockOrder = []
        self.inlineAttributedStrings = [:]
        self.inlineAttributedStringOrder = []
        self.parseHitCount = 0
        self.parseMissCount = 0
        self.inlineHitCount = 0
        self.inlineMissCount = 0
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
        inlineAttributedStrings.removeAll()
        inlineAttributedStringOrder.removeAll()
        parseHitCount = 0
        parseMissCount = 0
        inlineHitCount = 0
        inlineMissCount = 0
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

    private var blocks: [DesktopChatMarkdownBlock] {
        DesktopChatMarkdownRenderer.blocks(from: rawText)
    }

    var body: some View {
        DesktopChatMarkdownBlocksView(blocks: blocks)
            .frame(maxWidth: .infinity, alignment: .leading)
            .textSelection(.enabled)
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
            .lineSpacing(2)
            .padding(.top, level == 1 ? MelixDesignTokens.Spacing.xs : 0)
    }

    private func blockQuoteView(_ children: [DesktopChatMarkdownBlock]) -> some View {
        HStack(alignment: .top, spacing: MelixDesignTokens.Spacing.sm) {
            Rectangle()
                .fill(Color.secondary.opacity(0.28))
                .frame(width: 3)
            DesktopChatMarkdownBlocksView(blocks: children)
        }
        .padding(.vertical, 2)
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
        HStack(alignment: .top, spacing: 8) {
            SwiftUI.Text(marker)
                .font(.body.monospacedDigit())
                .foregroundStyle(.secondary)
                .frame(minWidth: 18, alignment: .trailing)
            VStack(alignment: .leading, spacing: DesktopChatMarkdownLayoutMetrics.listRowSpacing) {
                if item.text.isEmpty == false {
                    SwiftUI.Text(DesktopChatMarkdownInlineFormatter.attributedString(fromSanitized: item.text))
                        .font(.body)
                        .lineSpacing(2)
                }
                if item.children.isEmpty == false {
                    DesktopChatMarkdownBlocksView(blocks: item.children)
                        .padding(.top, 1)
                }
            }
        }
    }

    private func codeBlockView(language: String, code: String) -> some View {
        VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.xs) {
            if language.isEmpty == false {
                SwiftUI.Text(language)
                    .font(.caption2.monospaced())
                    .foregroundStyle(.secondary)
            }
            SwiftUI.Text(code.isEmpty ? " " : code)
                .font(.caption.monospaced())
                .lineSpacing(DesktopChatMarkdownLayoutMetrics.codeBlockLineSpacing)
                .frame(maxWidth: .infinity, alignment: .leading)
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
        return Grid(alignment: .leading, horizontalSpacing: 0, verticalSpacing: 0) {
            GridRow {
                ForEach(0..<columnCount, id: \.self) { column in
                    tableCellView(
                        text: header[safe: column] ?? "",
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
                            alignment: normalizedAlignments[column],
                            isHeader: false,
                            showsTrailingSeparator: column < columnCount - 1,
                            showsBottomSeparator: rowIndex < rows.count - 1
                        )
                    }
                }
            }
        }
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

    private func tableCellView(
        text: String,
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
                .padding(.horizontal, DesktopChatMarkdownLayoutMetrics.tableCellHorizontalPadding)
                .padding(.vertical, DesktopChatMarkdownLayoutMetrics.tableCellVerticalPadding)
                .frame(maxWidth: .infinity, alignment: alignment.frameAlignment)
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
            return .headline
        case 2:
            return .subheadline.weight(.semibold)
        default:
            return .caption.weight(.semibold)
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
