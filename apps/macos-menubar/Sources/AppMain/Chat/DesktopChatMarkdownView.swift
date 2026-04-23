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

enum DesktopChatMarkdownBlock: Equatable, Sendable {
    case paragraph(String)
    case unorderedList([String])
    case orderedList([String])
    case codeBlock(language: String, code: String)
    case table(header: [String], rows: [[String]])
}

enum DesktopChatMarkdownInlineFormatter {
    static func attributedString(from rawText: String) -> AttributedString {
        attributedString(fromSanitized: RichOutputSanitizer.sanitized(rawText))
    }

    static func attributedString(fromSanitized text: String) -> AttributedString {
        let options = AttributedString.MarkdownParsingOptions(
            interpretedSyntax: .inlineOnlyPreservingWhitespace
        )
        if var attributed = try? AttributedString(markdown: text, options: options) {
            let ranges = attributed.runs.map(\.range)
            for range in ranges {
                attributed[range].link = nil
            }
            return attributed
        }
        return AttributedString(text)
    }
}

enum DesktopChatMarkdownRenderer {
    static func usesMarkdown(for kind: DesktopChatTranscriptEntry.Kind) -> Bool {
        switch kind {
        case .assistant, .reasoning:
            return true
        case .user, .tool, .error:
            return false
        }
    }

    static func blocks(from rawText: String) -> [DesktopChatMarkdownBlock] {
        parseBlocks(from: RichOutputSanitizer.sanitized(rawText))
    }

    private static func parseBlocks(from text: String) -> [DesktopChatMarkdownBlock] {
        let lines = text.components(separatedBy: .newlines)
        var blocks: [DesktopChatMarkdownBlock] = []
        var index = 0

        while index < lines.count {
            if lines[index].trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                index += 1
                continue
            }

            if let codeBlock = parseCodeBlock(lines: lines, index: &index) {
                blocks.append(codeBlock)
                continue
            }
            if let table = parseTable(lines: lines, index: &index) {
                blocks.append(table)
                continue
            }
            if let list = parseUnorderedList(lines: lines, index: &index) {
                blocks.append(list)
                continue
            }
            if let list = parseOrderedList(lines: lines, index: &index) {
                blocks.append(list)
                continue
            }
            blocks.append(parseParagraph(lines: lines, index: &index))
        }

        if blocks.isEmpty, text.isEmpty == false {
            return [.paragraph(text)]
        }
        return blocks
    }

    private static func parseCodeBlock(lines: [String], index: inout Int) -> DesktopChatMarkdownBlock? {
        let trimmed = lines[index].trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.hasPrefix("```") else {
            return nil
        }

        let language = String(trimmed.dropFirst(3)).trimmingCharacters(in: .whitespacesAndNewlines)
        index += 1

        var codeLines: [String] = []
        while index < lines.count {
            let candidate = lines[index].trimmingCharacters(in: .whitespacesAndNewlines)
            if candidate.hasPrefix("```") {
                index += 1
                break
            }
            codeLines.append(lines[index])
            index += 1
        }

        return .codeBlock(language: language, code: codeLines.joined(separator: "\n"))
    }

    private static func parseTable(lines: [String], index: inout Int) -> DesktopChatMarkdownBlock? {
        guard isTableStart(lines: lines, index: index) else {
            return nil
        }

        let header = tableCells(from: lines[index])
        index += 2

        var rows: [[String]] = []
        while index < lines.count {
            let trimmed = lines[index].trimmingCharacters(in: .whitespacesAndNewlines)
            guard trimmed.isEmpty == false else {
                break
            }
            let cells = tableCells(from: lines[index])
            guard cells.isEmpty == false, isTableSeparator(cells) == false else {
                break
            }
            rows.append(cells)
            index += 1
        }

        return .table(header: header, rows: rows)
    }

    private static func isTableStart(lines: [String], index: Int) -> Bool {
        guard index + 1 < lines.count else {
            return false
        }
        let header = tableCells(from: lines[index])
        let separator = tableCells(from: lines[index + 1])
        return header.isEmpty == false
        && separator.count == header.count
        && isTableSeparator(separator)
    }

    private static func tableCells(from line: String) -> [String] {
        var core = line.trimmingCharacters(in: .whitespacesAndNewlines)
        guard core.contains("|") else {
            return []
        }
        if core.first == "|" {
            core.removeFirst()
        }
        if core.last == "|" {
            core.removeLast()
        }
        return core.split(separator: "|", omittingEmptySubsequences: false).map { cell in
            cell.trimmingCharacters(in: .whitespacesAndNewlines)
        }
    }

    private static func isTableSeparator(_ cells: [String]) -> Bool {
        guard cells.isEmpty == false else {
            return false
        }
        return cells.allSatisfy { cell in
            let trimmed = cell.trimmingCharacters(in: .whitespacesAndNewlines)
            guard trimmed.contains("-") else {
                return false
            }
            return trimmed.allSatisfy { character in
                character == "-" || character == ":" || character.isWhitespace
            }
        }
    }

    private static func parseUnorderedList(lines: [String], index: inout Int) -> DesktopChatMarkdownBlock? {
        guard unorderedListItemText(from: lines[index]) != nil else {
            return nil
        }

        var items: [String] = []
        while index < lines.count, let item = unorderedListItemText(from: lines[index]) {
            items.append(item)
            index += 1
        }
        return .unorderedList(items)
    }

    private static func unorderedListItemText(from line: String) -> String? {
        let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
        for marker in ["- ", "* ", "+ "] where trimmed.hasPrefix(marker) {
            return String(trimmed.dropFirst(marker.count)).trimmingCharacters(in: .whitespacesAndNewlines)
        }
        return nil
    }

    private static func parseOrderedList(lines: [String], index: inout Int) -> DesktopChatMarkdownBlock? {
        guard orderedListItemText(from: lines[index]) != nil else {
            return nil
        }

        var items: [String] = []
        while index < lines.count, let item = orderedListItemText(from: lines[index]) {
            items.append(item)
            index += 1
        }
        return .orderedList(items)
    }

    private static func orderedListItemText(from line: String) -> String? {
        let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let dotIndex = trimmed.firstIndex(of: ".") else {
            return nil
        }
        let number = trimmed[..<dotIndex]
        guard number.isEmpty == false, number.allSatisfy(\.isNumber) else {
            return nil
        }
        let afterDot = trimmed.index(after: dotIndex)
        guard afterDot < trimmed.endIndex, trimmed[afterDot].isWhitespace else {
            return nil
        }
        let itemStart = trimmed.index(after: afterDot)
        return String(trimmed[itemStart...]).trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func parseParagraph(lines: [String], index: inout Int) -> DesktopChatMarkdownBlock {
        var paragraphLines: [String] = []
        while index < lines.count {
            let trimmed = lines[index].trimmingCharacters(in: .whitespacesAndNewlines)
            guard trimmed.isEmpty == false, isBlockStart(lines: lines, index: index) == false else {
                break
            }
            paragraphLines.append(lines[index])
            index += 1
        }
        return .paragraph(paragraphLines.joined(separator: "\n"))
    }

    private static func isBlockStart(lines: [String], index: Int) -> Bool {
        let trimmed = lines[index].trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.hasPrefix("```")
        || isTableStart(lines: lines, index: index)
        || unorderedListItemText(from: lines[index]) != nil
        || orderedListItemText(from: lines[index]) != nil
    }
}

struct DesktopChatMarkdownBodyView: View {
    let rawText: String

    private var blocks: [DesktopChatMarkdownBlock] {
        DesktopChatMarkdownRenderer.blocks(from: rawText)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: DesktopChatMarkdownLayoutMetrics.blockSpacing) {
            ForEach(Array(blocks.enumerated()), id: \.offset) { _, block in
                switch block {
                case .paragraph(let text):
                    paragraphView(text)
                case .unorderedList(let items):
                    unorderedListView(items)
                case .orderedList(let items):
                    orderedListView(items)
                case .codeBlock(let language, let code):
                    codeBlockView(language: language, code: code)
                case .table(let header, let rows):
                    tableView(header: header, rows: rows)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .textSelection(.enabled)
    }

    private func paragraphView(_ text: String) -> some View {
        Text(DesktopChatMarkdownInlineFormatter.attributedString(fromSanitized: text))
            .font(.body)
            .lineSpacing(2)
    }

    private func unorderedListView(_ items: [String]) -> some View {
        VStack(alignment: .leading, spacing: DesktopChatMarkdownLayoutMetrics.listRowSpacing) {
            ForEach(items.indices, id: \.self) { index in
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text("•")
                        .font(.body)
                    Text(DesktopChatMarkdownInlineFormatter.attributedString(fromSanitized: items[index]))
                        .font(.body)
                        .lineSpacing(2)
                }
            }
        }
    }

    private func orderedListView(_ items: [String]) -> some View {
        VStack(alignment: .leading, spacing: DesktopChatMarkdownLayoutMetrics.listRowSpacing) {
            ForEach(items.indices, id: \.self) { index in
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text("\(index + 1).")
                        .font(.body.monospacedDigit())
                        .foregroundStyle(.secondary)
                    Text(DesktopChatMarkdownInlineFormatter.attributedString(fromSanitized: items[index]))
                        .font(.body)
                        .lineSpacing(2)
                }
            }
        }
    }

    private func codeBlockView(language: String, code: String) -> some View {
        VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.xs) {
            if language.isEmpty == false {
                Text(language)
                    .font(.caption2.monospaced())
                    .foregroundStyle(.secondary)
            }
            Text(code.isEmpty ? " " : code)
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

    private func tableView(header: [String], rows: [[String]]) -> some View {
        let columnCount = max(header.count, 1)
        return Grid(alignment: .leading, horizontalSpacing: 0, verticalSpacing: 0) {
            GridRow {
                ForEach(0..<columnCount, id: \.self) { column in
                    tableCellView(
                        text: header[safe: column] ?? "",
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
        isHeader: Bool,
        showsTrailingSeparator: Bool,
        showsBottomSeparator: Bool
    ) -> some View {
        ZStack(alignment: .topLeading) {
            if isHeader {
                Rectangle()
                    .fill(Color.primary.opacity(DesktopChatMarkdownLayoutMetrics.tableHeaderBackgroundOpacity))
            }
            Text(DesktopChatMarkdownInlineFormatter.attributedString(fromSanitized: text))
                .font(isHeader ? .caption.weight(.semibold) : .caption)
                .padding(.horizontal, DesktopChatMarkdownLayoutMetrics.tableCellHorizontalPadding)
                .padding(.vertical, DesktopChatMarkdownLayoutMetrics.tableCellVerticalPadding)
                .frame(maxWidth: .infinity, alignment: .leading)
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

    private func normalizedTableRow(_ row: [String], columnCount: Int) -> [String] {
        if row.count >= columnCount {
            return Array(row.prefix(columnCount))
        }
        return row + Array(repeating: "", count: columnCount - row.count)
    }
}

private extension Array {
    subscript(safe index: Index) -> Element? {
        indices.contains(index) ? self[index] : nil
    }
}
