import Foundation

public struct TextModelSamplingRecommendation: Sendable, Equatable {
    public let temperature: Double?
    public let topP: Double?
    public let maxTokens: UInt32?

    public init(
        temperature: Double? = nil,
        topP: Double? = nil,
        maxTokens: UInt32? = nil
    ) {
        self.temperature = temperature
        self.topP = topP
        self.maxTokens = maxTokens
    }

    public var isEmpty: Bool {
        temperature == nil && topP == nil && maxTokens == nil
    }
}

public struct TextModelPolicyCatalog: Sendable, Equatable {
    public struct Entry: Sendable, Equatable {
        public let canonicalModelID: String
        public let aliases: [String]
        public let sampling: TextModelSamplingRecommendation
        public let sourceURL: String

        public init(
            canonicalModelID: String,
            aliases: [String] = [],
            sampling: TextModelSamplingRecommendation,
            sourceURL: String
        ) {
            self.canonicalModelID = canonicalModelID.trimmingCharacters(in: .whitespacesAndNewlines)
            self.aliases = aliases.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty }
            self.sampling = sampling
            self.sourceURL = sourceURL.trimmingCharacters(in: .whitespacesAndNewlines)
        }
    }

    public struct LookupResult: Sendable, Equatable {
        public let canonicalModelID: String
        public let matchedAlias: String
        public let sampling: TextModelSamplingRecommendation
        public let sourceURL: String
    }

    public static let empty = TextModelPolicyCatalog(entries: [])

    // Start empty until production entries have source-verified recommendations.
    public static let `default` = TextModelPolicyCatalog(entries: [])

    private let entriesByIdentity: [String: LookupResult]

    public init(entries: [Entry]) {
        var indexed: [String: LookupResult] = [:]
        for entry in entries where !entry.canonicalModelID.isEmpty && !entry.sampling.isEmpty {
            let identities = [entry.canonicalModelID] + entry.aliases
            for identity in identities {
                let result = LookupResult(
                    canonicalModelID: entry.canonicalModelID,
                    matchedAlias: identity,
                    sampling: entry.sampling,
                    sourceURL: entry.sourceURL
                )
                for key in Self.identityKeys(for: identity) where indexed[key] == nil {
                    indexed[key] = result
                }
            }
        }
        self.entriesByIdentity = indexed
    }

    public func lookup(identities: [String]) -> LookupResult? {
        for identity in identities {
            for key in Self.identityKeys(for: identity) {
                if let result = entriesByIdentity[key] {
                    return result
                }
            }
        }
        return nil
    }

    public static func identityKeys(for rawValue: String) -> [String] {
        let normalized = rawValue
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: "\\", with: "/")
            .lowercased()
        guard !normalized.isEmpty else {
            return []
        }

        var keys: [String] = []
        func appendUnique(_ key: String) {
            guard !key.isEmpty, !keys.contains(key) else {
                return
            }
            keys.append(key)
        }

        appendUnique(normalized)

        if let lastComponent = normalized.split(separator: "/").last {
            appendUnique(String(lastComponent))
        }
        if let handlePrefix = normalized.split(separator: "::").first {
            appendUnique(String(handlePrefix))
        }

        return keys
    }
}
