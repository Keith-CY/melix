import Foundation
import MelixWorkerProtocol

func resolvedRestoreSnapshotID(
    from request: Melix_Worker_V1_RestoreBoundarySnapshotRequest
) -> String {
    if !request.snapshotID.isEmpty {
        return request.snapshotID
    }
    return request.restoreBoundary.snapshot.snapshotID
}

func makeRestoreBoundaryRef(
    snapshot: Melix_Worker_V1_SnapshotRef,
    blockTable: Melix_Worker_V1_BlockTable,
    boundaryKind: String = "boundary_snapshot"
) -> Melix_Worker_V1_RestoreBoundaryRef {
    var boundary = Melix_Worker_V1_RestoreBoundaryRef()
    boundary.snapshot = snapshot
    boundary.cacheKey = blockTable.cacheKey
    boundary.scopeID = effectiveScopeID(for: blockTable)
    boundary.boundaryKind = boundaryKind
    return boundary
}

func makeCacheRestorePlan(
    snapshot: Melix_Worker_V1_SnapshotRef,
    blockTableID: String,
    blockTable: Melix_Worker_V1_BlockTable,
    tier: String,
    cacheMode: Melix_Worker_V1_CacheMode = .tiered,
    partial: Bool = false,
    boundaryKind: String = "boundary_snapshot"
) -> Melix_Worker_V1_CacheRestorePlan {
    let normalizedTable = normalizedBlockTable(blockTable)

    var plan = Melix_Worker_V1_CacheRestorePlan()
    plan.planID = blockTableID.isEmpty ? "restore-\(snapshot.snapshotID)" : "restore-\(blockTableID)"
    plan.boundary = makeRestoreBoundaryRef(
        snapshot: snapshot,
        blockTable: normalizedTable,
        boundaryKind: boundaryKind
    )
    plan.blockTableID = blockTableID
    plan.blockTable = normalizedTable
    plan.pages = normalizedTable.pages
    plan.restoredTokenCount = normalizedTable.totalTokenCount
    plan.partial = partial
    plan.tier = tier
    plan.cacheMode = cacheMode
    return plan
}

func makeWalkedBackCacheRestorePlan(
    snapshot: Melix_Worker_V1_SnapshotRef,
    blockTableID: String,
    blockTable: Melix_Worker_V1_BlockTable,
    cachedMessages: [Melix_Worker_V1_ChatMessage],
    requestMessages: [Melix_Worker_V1_ChatMessage],
    tier: String,
    cacheMode: Melix_Worker_V1_CacheMode = .tiered
) -> Melix_Worker_V1_CacheRestorePlan? {
    let normalizedTable = normalizedBlockTable(blockTable)
    if requestMessages.isEmpty {
        return makeCacheRestorePlan(
            snapshot: snapshot,
            blockTableID: blockTableID,
            blockTable: normalizedTable,
            tier: tier,
            cacheMode: cacheMode
        )
    }

    let sharedPromptTokens = sharedReusablePromptTokens(
        cachedMessages: cachedMessages,
        requestMessages: requestMessages
    )
    guard sharedPromptTokens > 0 else {
        return nil
    }

    let safeBoundary = safeReusableTokenBoundary(
        in: normalizedTable,
        sharedPromptTokens: sharedPromptTokens
    )
    guard safeBoundary > 0 else {
        return nil
    }

    if safeBoundary >= normalizedTable.totalTokenCount {
        return makeCacheRestorePlan(
            snapshot: snapshot,
            blockTableID: blockTableID,
            blockTable: normalizedTable,
            tier: tier,
            cacheMode: cacheMode
        )
    }

    let truncatedTable = truncatedBlockTable(
        normalizedTable,
        throughTokenBoundary: safeBoundary
    )
    guard !truncatedTable.pages.isEmpty else {
        return nil
    }

    return makeCacheRestorePlan(
        snapshot: snapshot,
        blockTableID: "\(blockTableID)::walkback-\(safeBoundary)",
        blockTable: truncatedTable,
        tier: tier,
        cacheMode: cacheMode,
        partial: true,
        boundaryKind: "partial_prefix_walk_back"
    )
}

func makeBoundarySafePrefillChunkBoundaries(
    messages: [Melix_Worker_V1_ChatMessage],
    chunkTokenTarget: UInt32,
    restoredTokenCount: UInt32 = 0
) -> [UInt32] {
    guard chunkTokenTarget > 0 else {
        return []
    }

    let fragments = promptReuseFragments(from: messages)
    guard !fragments.isEmpty else {
        return []
    }

    var boundaries: [UInt32] = []
    var processedTokens: UInt32 = 0
    var nextBoundary = max(chunkTokenTarget, restoredTokenCount &+ chunkTokenTarget)

    for fragment in fragments {
        processedTokens += fragment.tokenCount
        guard processedTokens > restoredTokenCount else {
            continue
        }

        if processedTokens >= nextBoundary {
            boundaries.append(processedTokens)
            nextBoundary = processedTokens &+ chunkTokenTarget
        }
    }

    if processedTokens > restoredTokenCount,
       boundaries.last != processedTokens {
        boundaries.append(processedTokens)
    }

    return boundaries
}

func normalizedBlockTable(
    _ blockTable: Melix_Worker_V1_BlockTable
) -> Melix_Worker_V1_BlockTable {
    var normalized = blockTable
    if normalized.pages.isEmpty {
        normalized.pages = makePageRefs(from: normalized.blocks)
    }
    if normalized.totalTokenCount == 0 {
        normalized.totalTokenCount = normalized.blocks.reduce(0) { partial, block in
            max(partial, UInt32(max(block.tokenEnd, 0)))
        }
    }
    if normalized.scopeID.isEmpty {
        normalized.scopeID = normalized.cacheKey.scopeID
    }
    return normalized
}

func makePageRefs(
    from blocks: [Melix_Worker_V1_BlockRef]
) -> [Melix_Worker_V1_PageRef] {
    blocks.map { block in
        var page = Melix_Worker_V1_PageRef()
        page.pageID = "page-\(block.blockID)"
        page.blockIds = [block.blockID]
        page.tokenStart = UInt32(max(block.tokenStart, 0))
        page.tokenEnd = UInt32(max(block.tokenEnd, 0))
        page.bytes = block.bytes
        return page
    }
}

private func effectiveScopeID(
    for blockTable: Melix_Worker_V1_BlockTable
) -> String {
    if !blockTable.scopeID.isEmpty {
        return blockTable.scopeID
    }
    return blockTable.cacheKey.scopeID
}

private func safeReusableTokenBoundary(
    in blockTable: Melix_Worker_V1_BlockTable,
    sharedPromptTokens: UInt32
) -> UInt32 {
    let normalizedTable = normalizedBlockTable(blockTable)
    if sharedPromptTokens >= normalizedTable.totalTokenCount {
        return normalizedTable.totalTokenCount
    }

    let reusablePages = normalizedTable.pages
        .sorted { lhs, rhs in
            if lhs.tokenEnd == rhs.tokenEnd {
                return lhs.pageID < rhs.pageID
            }
            return lhs.tokenEnd < rhs.tokenEnd
        }
        .filter { $0.tokenEnd <= sharedPromptTokens }

    return reusablePages.last?.tokenEnd ?? 0
}

private func truncatedBlockTable(
    _ blockTable: Melix_Worker_V1_BlockTable,
    throughTokenBoundary tokenBoundary: UInt32
) -> Melix_Worker_V1_BlockTable {
    let normalizedTable = normalizedBlockTable(blockTable)
    let pages = normalizedTable.pages.filter { $0.tokenEnd <= tokenBoundary }
    let allowedBlockIDs = Set(pages.flatMap(\.blockIds))

    var truncated = normalizedTable
    truncated.pages = pages
    truncated.blocks = normalizedTable.blocks.filter { allowedBlockIDs.contains($0.blockID) }
    truncated.totalTokenCount = pages.last?.tokenEnd ?? 0
    return truncated
}

private func sharedReusablePromptTokens(
    cachedMessages: [Melix_Worker_V1_ChatMessage],
    requestMessages: [Melix_Worker_V1_ChatMessage]
) -> UInt32 {
    let cachedFragments = promptReuseFragments(from: cachedMessages)
    let requestFragments = promptReuseFragments(from: requestMessages)

    var sharedTokens: UInt32 = 0
    for (cached, request) in zip(cachedFragments, requestFragments) {
        guard cached == request else {
            break
        }
        sharedTokens += cached.tokenCount
    }
    return sharedTokens
}

private enum PromptReuseFragment: Equatable {
    case role(String)
    case nameToken(String)
    case textToken(String)
    case imageURI(String)
    case imageBytes(Data)
    case audioURI(String)
    case audioBytes(Data)

    var tokenCount: UInt32 {
        switch self {
        case .role:
            return 0
        case .nameToken, .textToken:
            return 1
        case .imageURI, .imageBytes, .audioURI, .audioBytes:
            return 256
        }
    }
}

private func promptReuseFragments(
    from messages: [Melix_Worker_V1_ChatMessage]
) -> [PromptReuseFragment] {
    messages.flatMap { message in
        var fragments: [PromptReuseFragment] = [.role(message.role)]
        fragments += tokenFragments(from: message.name, kind: PromptReuseFragment.nameToken)
        for part in message.parts {
            switch part.part {
            case .text(let text):
                fragments += tokenFragments(from: text, kind: PromptReuseFragment.textToken)
            case .imageUri(let uri):
                fragments.append(.imageURI(uri))
            case .imageBytes(let bytes):
                fragments.append(.imageBytes(Data(bytes)))
            case .audioUri(let uri):
                fragments.append(.audioURI(uri))
            case .audioBytes(let bytes):
                fragments.append(.audioBytes(Data(bytes)))
            case .videoUri, .videoBytes:
                continue
            case nil:
                continue
            }
        }
        return fragments
    }
}

private func tokenFragments(
    from text: String,
    kind: (String) -> PromptReuseFragment
) -> [PromptReuseFragment] {
    text
        .trimmingCharacters(in: .whitespacesAndNewlines)
        .split(whereSeparator: \.isWhitespace)
        .map { kind(String($0)) }
}
