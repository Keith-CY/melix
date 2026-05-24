import CryptoKit
import Foundation
import MelixWorkerProtocol

public enum MultimodalRequestNormalizationError: Error, Equatable {
    case missingValue(String)
    case invalidBase64(String)
    case unsupportedPartType(String)
    case unsupportedURIScheme(String, String)
    case unsupportedMediaFormat(String, String)
    case invalidPreprocessingBound(String, String)
    case externalMediaURLBlocked(String)
}

extension MultimodalRequestNormalizationError {
    var operatorMessage: String {
        switch self {
        case let .missingValue(field):
            return "\(field) is required."
        case let .invalidBase64(kind):
            return "\(kind)_base64 must be valid base64."
        case let .unsupportedPartType(kind):
            return "Unsupported multimodal part type: \(kind)."
        case let .unsupportedURIScheme(kind, scheme):
            return "Unsupported \(kind) URI scheme: \(scheme)."
        case let .unsupportedMediaFormat(kind, format):
            return "Unsupported \(kind) format: \(format)."
        case let .invalidPreprocessingBound(field, reason):
            return "\(field) \(reason)."
        case let .externalMediaURLBlocked(message):
            return message
        }
    }
}

public struct OpenAIMultimodalImageReference: Sendable, Codable, Equatable {
    public let url: String?
    public let data: String?
    public let detail: String?
    public let mimeType: String?
    public let format: String?
    public let filename: String?

    enum CodingKeys: String, CodingKey {
        case url
        case data
        case detail
        case mimeType = "mime_type"
        case format
        case filename
    }

    public init(
        url: String? = nil,
        data: String? = nil,
        detail: String? = nil,
        mimeType: String? = nil,
        format: String? = nil,
        filename: String? = nil
    ) {
        self.url = url
        self.data = data
        self.detail = detail
        self.mimeType = mimeType
        self.format = format
        self.filename = filename
    }
}

public struct OpenAIMultimodalAudioReference: Sendable, Codable, Equatable {
    public let data: String?
    public let url: String?
    public let format: String?
    public let mimeType: String?
    public let filename: String?

    enum CodingKeys: String, CodingKey {
        case data
        case url
        case format
        case mimeType = "mime_type"
        case filename
    }

    public init(
        data: String? = nil,
        url: String? = nil,
        format: String? = nil,
        mimeType: String? = nil,
        filename: String? = nil
    ) {
        self.data = data
        self.url = url
        self.format = format
        self.mimeType = mimeType
        self.filename = filename
    }
}

public struct OpenAIMultimodalVideoReference: Sendable, Codable, Equatable {
    public let data: String?
    public let url: String?
    public let format: String?
    public let mimeType: String?
    public let filename: String?
    public let durationMs: Int?
    public let frameBudget: Int?
    public let startMs: Int?
    public let endMs: Int?

    enum CodingKeys: String, CodingKey {
        case data
        case url
        case format
        case mimeType = "mime_type"
        case filename
        case durationMs = "duration_ms"
        case frameBudget = "frame_budget"
        case startMs = "start_ms"
        case endMs = "end_ms"
    }

    public init(
        data: String? = nil,
        url: String? = nil,
        format: String? = nil,
        mimeType: String? = nil,
        filename: String? = nil,
        durationMs: Int? = nil,
        frameBudget: Int? = nil,
        startMs: Int? = nil,
        endMs: Int? = nil
    ) {
        self.data = data
        self.url = url
        self.format = format
        self.mimeType = mimeType
        self.filename = filename
        self.durationMs = durationMs
        self.frameBudget = frameBudget
        self.startMs = startMs
        self.endMs = endMs
    }
}

public struct OpenAIMultimodalContentPart: Sendable, Codable, Equatable {
    public enum PartType: String, Sendable, Codable, Equatable {
        case text = "text"
        case inputText = "input_text"
        case image = "image"
        case imageURL = "image_url"
        case inputImage = "input_image"
        case audio = "audio"
        case audioURL = "audio_url"
        case inputAudio = "input_audio"
        case video = "video"
        case videoURL = "video_url"
        case inputVideo = "input_video"

        public init(from decoder: Decoder) throws {
            let container = try decoder.singleValueContainer()
            let rawValue = try container.decode(String.self)
            guard let value = PartType(rawValue: rawValue) else {
                throw MultimodalRequestNormalizationError.unsupportedPartType(rawValue)
            }
            self = value
        }

        public func encode(to encoder: Encoder) throws {
            var container = encoder.singleValueContainer()
            try container.encode(rawValue)
        }
    }

    public let type: PartType
    public let text: String?
    public let imageURL: OpenAIMultimodalImageReference?
    public let inputImage: OpenAIMultimodalImageReference?
    public let inputAudio: OpenAIMultimodalAudioReference?
    public let inputVideo: OpenAIMultimodalVideoReference?

    enum CodingKeys: String, CodingKey {
        case type
        case text
        case imageURL = "image_url"
        case image
        case inputImage = "input_image"
        case audio
        case audioURL = "audio_url"
        case inputAudio = "input_audio"
        case video
        case videoURL = "video_url"
        case inputVideo = "input_video"
        case imageBase64 = "image_base64"
        case audioBase64 = "audio_base64"
        case videoBase64 = "video_base64"
        case mimeType = "mime_type"
        case format
        case detail
        case filename
        case durationMs = "duration_ms"
        case frameBudget = "frame_budget"
        case startMs = "start_ms"
        case endMs = "end_ms"
    }

    public init(
        type: PartType,
        text: String? = nil,
        imageURL: OpenAIMultimodalImageReference? = nil,
        inputImage: OpenAIMultimodalImageReference? = nil,
        inputAudio: OpenAIMultimodalAudioReference? = nil,
        inputVideo: OpenAIMultimodalVideoReference? = nil
    ) {
        self.type = type
        self.text = text
        self.imageURL = imageURL
        self.inputImage = inputImage
        self.inputAudio = inputAudio
        self.inputVideo = inputVideo
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        type = try container.decode(PartType.self, forKey: .type)

        let topLevelMimeType = try container.decodeIfPresent(String.self, forKey: .mimeType)
        let topLevelFormat = try container.decodeIfPresent(String.self, forKey: .format)
        let topLevelDetail = try container.decodeIfPresent(String.self, forKey: .detail)
        let topLevelFilename = try container.decodeIfPresent(String.self, forKey: .filename)
        let topLevelDurationMs = try container.decodeIfPresent(Int.self, forKey: .durationMs)
        let topLevelFrameBudget = try container.decodeIfPresent(Int.self, forKey: .frameBudget)
        let topLevelStartMs = try container.decodeIfPresent(Int.self, forKey: .startMs)
        let topLevelEndMs = try container.decodeIfPresent(Int.self, forKey: .endMs)

        switch type {
        case .text, .inputText:
            text = try container.decodeIfPresent(String.self, forKey: .text)
            imageURL = nil
            inputImage = nil
            inputAudio = nil
            inputVideo = nil
        case .image, .imageURL:
            text = nil
            inputImage = nil
            inputAudio = nil
            inputVideo = nil
            let imageKey: CodingKeys = type == .image ? .image : .imageURL
            if let inlineURL = try? container.decode(String.self, forKey: imageKey) {
                imageURL = OpenAIMultimodalImageReference(
                    url: inlineURL,
                    detail: topLevelDetail,
                    mimeType: topLevelMimeType,
                    format: topLevelFormat,
                    filename: topLevelFilename
                )
            } else if let decoded = try container.decodeIfPresent(OpenAIMultimodalImageReference.self, forKey: imageKey) {
                imageURL = OpenAIMultimodalImageReference(
                    url: decoded.url,
                    data: decoded.data,
                    detail: decoded.detail ?? topLevelDetail,
                    mimeType: decoded.mimeType ?? topLevelMimeType,
                    format: decoded.format ?? topLevelFormat,
                    filename: decoded.filename ?? topLevelFilename
                )
            } else {
                throw MultimodalRequestNormalizationError.missingValue(type.rawValue)
            }
        case .inputImage:
            text = nil
            imageURL = nil
            inputAudio = nil
            inputVideo = nil
            if let decoded = try container.decodeIfPresent(OpenAIMultimodalImageReference.self, forKey: .inputImage) {
                inputImage = OpenAIMultimodalImageReference(
                    url: decoded.url,
                    data: decoded.data,
                    detail: decoded.detail ?? topLevelDetail,
                    mimeType: decoded.mimeType ?? topLevelMimeType,
                    format: decoded.format ?? topLevelFormat,
                    filename: decoded.filename ?? topLevelFilename
                )
            } else if let imageBase64 = try container.decodeIfPresent(String.self, forKey: .imageBase64) {
                inputImage = OpenAIMultimodalImageReference(
                    data: imageBase64,
                    detail: topLevelDetail,
                    mimeType: topLevelMimeType,
                    format: topLevelFormat,
                    filename: topLevelFilename
                )
            } else {
                throw MultimodalRequestNormalizationError.missingValue("input_image")
            }
        case .audio, .audioURL, .inputAudio:
            text = nil
            imageURL = nil
            inputImage = nil
            inputVideo = nil
            let audioKey: CodingKeys = switch type {
            case .audio:
                .audio
            case .audioURL:
                .audioURL
            default:
                .inputAudio
            }
            if let inlineURL = try? container.decode(String.self, forKey: audioKey) {
                inputAudio = OpenAIMultimodalAudioReference(
                    url: inlineURL,
                    format: topLevelFormat,
                    mimeType: topLevelMimeType,
                    filename: topLevelFilename
                )
            } else if let decoded = try container.decodeIfPresent(OpenAIMultimodalAudioReference.self, forKey: audioKey) {
                inputAudio = OpenAIMultimodalAudioReference(
                    data: decoded.data,
                    url: decoded.url,
                    format: decoded.format ?? topLevelFormat,
                    mimeType: decoded.mimeType ?? topLevelMimeType,
                    filename: decoded.filename ?? topLevelFilename
                )
            } else if let audioBase64 = try container.decodeIfPresent(String.self, forKey: .audioBase64) {
                inputAudio = OpenAIMultimodalAudioReference(
                    data: audioBase64,
                    format: topLevelFormat,
                    mimeType: topLevelMimeType,
                    filename: topLevelFilename
                )
            } else {
                throw MultimodalRequestNormalizationError.missingValue(type.rawValue)
            }
        case .video, .videoURL, .inputVideo:
            text = nil
            imageURL = nil
            inputImage = nil
            inputAudio = nil
            let videoKey: CodingKeys = switch type {
            case .video:
                .video
            case .videoURL:
                .videoURL
            default:
                .inputVideo
            }
            if let inlineURL = try? container.decode(String.self, forKey: videoKey) {
                inputVideo = OpenAIMultimodalVideoReference(
                    url: inlineURL,
                    format: topLevelFormat,
                    mimeType: topLevelMimeType,
                    filename: topLevelFilename,
                    durationMs: topLevelDurationMs,
                    frameBudget: topLevelFrameBudget,
                    startMs: topLevelStartMs,
                    endMs: topLevelEndMs
                )
            } else if let decoded = try container.decodeIfPresent(OpenAIMultimodalVideoReference.self, forKey: videoKey) {
                inputVideo = OpenAIMultimodalVideoReference(
                    data: decoded.data,
                    url: decoded.url,
                    format: decoded.format ?? topLevelFormat,
                    mimeType: decoded.mimeType ?? topLevelMimeType,
                    filename: decoded.filename ?? topLevelFilename,
                    durationMs: decoded.durationMs ?? topLevelDurationMs,
                    frameBudget: decoded.frameBudget ?? topLevelFrameBudget,
                    startMs: decoded.startMs ?? topLevelStartMs,
                    endMs: decoded.endMs ?? topLevelEndMs
                )
            } else if let videoBase64 = try container.decodeIfPresent(String.self, forKey: .videoBase64) {
                inputVideo = OpenAIMultimodalVideoReference(
                    data: videoBase64,
                    format: topLevelFormat,
                    mimeType: topLevelMimeType,
                    filename: topLevelFilename,
                    durationMs: topLevelDurationMs,
                    frameBudget: topLevelFrameBudget,
                    startMs: topLevelStartMs,
                    endMs: topLevelEndMs
                )
            } else {
                throw MultimodalRequestNormalizationError.missingValue(type.rawValue)
            }
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(type, forKey: .type)

        switch type {
        case .text, .inputText:
            try container.encodeIfPresent(text, forKey: .text)
        case .image, .imageURL:
            let imageKey: CodingKeys = type == .image ? .image : .imageURL
            try container.encodeIfPresent(imageURL, forKey: imageKey)
        case .inputImage:
            try container.encodeIfPresent(inputImage, forKey: .inputImage)
        case .audio, .audioURL, .inputAudio:
            let audioKey: CodingKeys = switch type {
            case .audio:
                .audio
            case .audioURL:
                .audioURL
            default:
                .inputAudio
            }
            try container.encodeIfPresent(inputAudio, forKey: audioKey)
        case .video, .videoURL, .inputVideo:
            let videoKey: CodingKeys = switch type {
            case .video:
                .video
            case .videoURL:
                .videoURL
            default:
                .inputVideo
            }
            try container.encodeIfPresent(inputVideo, forKey: videoKey)
        }
    }
}

public struct OpenAIMultimodalMessage: Sendable, Codable, Equatable {
    public let role: String
    public let name: String?
    public let content: [OpenAIMultimodalContentPart]

    public init(role: String, name: String? = nil, content: [OpenAIMultimodalContentPart]) {
        self.role = role
        self.name = name
        self.content = content
    }
}

public struct NormalizedMediaPartSummary: Sendable, Codable, Equatable {
    public let mediaKind: String
    public let sourceKind: String
    public let source: String
    public let turnIndex: Int
    public let partIndex: Int
    public let byteLength: UInt64?
    public let filename: String?
    public let format: String?
    public let stableDigest: String?

    enum CodingKeys: String, CodingKey {
        case mediaKind = "media_kind"
        case sourceKind = "source_kind"
        case source
        case turnIndex = "turn_index"
        case partIndex = "part_index"
        case byteLength = "byte_length"
        case filename
        case format
        case stableDigest = "stable_digest"
    }

    public init(
        mediaKind: String,
        sourceKind: String,
        source: String,
        turnIndex: Int,
        partIndex: Int,
        byteLength: UInt64? = nil,
        filename: String? = nil,
        format: String? = nil,
        stableDigest: String? = nil
    ) {
        self.mediaKind = mediaKind
        self.sourceKind = sourceKind
        self.source = source
        self.turnIndex = turnIndex
        self.partIndex = partIndex
        self.byteLength = byteLength
        self.filename = Self.nilIfEmpty(filename)
        self.format = Self.nilIfEmpty(format)
        self.stableDigest = Self.nilIfEmpty(stableDigest)
    }

    private static func nilIfEmpty(_ value: String?) -> String? {
        guard let value else {
            return nil
        }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}

public struct NormalizedMediaPartsSummary: Sendable, Codable, Equatable {
    public let parts: [NormalizedMediaPartSummary]

    public init(parts: [NormalizedMediaPartSummary] = []) {
        self.parts = parts
    }

    public var isEmpty: Bool {
        parts.isEmpty
    }

    public var count: Int {
        parts.count
    }

    public var turnCount: Int {
        Set(parts.map(\.turnIndex)).count
    }
}

public struct MultimodalRequestNormalizer: Sendable {
    private static let supportedVideoFormats: Set<String> = ["mp4", "mov", "m4v", "webm"]
    private static let supportedVideoMimeTypes: [String: String] = [
        "video/mp4": "mp4",
        "video/quicktime": "mov",
        "video/x-m4v": "m4v",
        "video/webm": "webm",
    ]
    private static let maxVideoFrameBudget = 128

    public init() {}

    public func normalize(
        _ messages: [OpenAIMultimodalMessage]
    ) throws -> [Melix_Worker_V1_ChatMessage] {
        try messages.map(normalize)
    }

    public func mediaPartsSummary(
        for messages: [OpenAIMultimodalMessage]
    ) throws -> NormalizedMediaPartsSummary {
        var summaries: [NormalizedMediaPartSummary] = []
        for (turnIndex, message) in messages.enumerated() {
            for (partIndex, part) in message.content.enumerated() {
                let normalized = try normalize(part)
                if let summary = mediaPartSummary(
                    for: normalized,
                    turnIndex: turnIndex,
                    partIndex: partIndex
                ) {
                    summaries.append(summary)
                }
            }
        }
        return NormalizedMediaPartsSummary(parts: summaries)
    }

    public func mediaPartsSummary(
        for messages: [NormalizedTextMessage]
    ) -> NormalizedMediaPartsSummary {
        NormalizedMediaPartsSummary(
            parts: messages.enumerated().flatMap { turnIndex, message in
                message.parts.enumerated().compactMap { partIndex, part in
                    mediaPartSummary(for: part, turnIndex: turnIndex, partIndex: partIndex)
                }
            }
        )
    }

    public func normalize(
        _ message: OpenAIMultimodalMessage
    ) throws -> Melix_Worker_V1_ChatMessage {
        var normalized = Melix_Worker_V1_ChatMessage()
        normalized.role = message.role
        normalized.name = message.name ?? ""
        normalized.parts = try message.content.map(normalize)
        return normalized
    }

    public func normalize(
        _ part: OpenAIMultimodalContentPart
    ) throws -> Melix_Worker_V1_MessagePart {
        switch part.type {
        case .text, .inputText:
            return try normalizeText(part)
        case .image, .imageURL:
            return try normalizeImage(part.imageURL, inlineOnly: false)
        case .inputImage:
            return try normalizeImage(part.inputImage, inlineOnly: true)
        case .audio, .audioURL, .inputAudio:
            return try normalizeAudio(part.inputAudio)
        case .video, .videoURL, .inputVideo:
            return try normalizeVideo(part.inputVideo)
        }
    }

    private func normalizeText(
        _ part: OpenAIMultimodalContentPart
    ) throws -> Melix_Worker_V1_MessagePart {
        guard let text = part.text, !text.isEmpty else {
            throw MultimodalRequestNormalizationError.missingValue("text")
        }

        var normalized = Melix_Worker_V1_MessagePart()
        normalized.text = text
        normalized.media.mediaType = .text
        return normalized
    }

    private func normalizeImage(
        _ reference: OpenAIMultimodalImageReference?,
        inlineOnly: Bool
    ) throws -> Melix_Worker_V1_MessagePart {
        guard let reference else {
            throw MultimodalRequestNormalizationError.missingValue(inlineOnly ? "input_image" : "image_url")
        }

        var normalized = Melix_Worker_V1_MessagePart()
        normalized.media.mediaType = .image
        normalized.media.mimeType = reference.mimeType ?? ""
        normalized.media.format = reference.format ?? ""
        normalized.media.filename = reference.filename ?? ""
        if let detail = reference.detail, !detail.isEmpty {
            normalized.media.preprocessingHints["detail"] = detail
        }

        if !inlineOnly, let url = reference.url, !url.isEmpty {
            let receipt = try mediaURLAdmissionReceipt(url, mediaKind: "image")
            normalized.imageUri = url.trimmingCharacters(in: .whitespacesAndNewlines)
            normalized.media.sourceKind = .mediaSourceUri
            apply(receipt, to: &normalized.media)
            return normalized
        }

        if inlineOnly, let url = reference.url, !url.isEmpty {
            let receipt = try mediaURLAdmissionReceipt(url, mediaKind: "image")
            normalized.imageUri = url.trimmingCharacters(in: .whitespacesAndNewlines)
            normalized.media.sourceKind = .mediaSourceUri
            apply(receipt, to: &normalized.media)
            return normalized
        }

        guard let data = reference.data, !data.isEmpty else {
            throw MultimodalRequestNormalizationError.missingValue(
                inlineOnly ? "input_image.url or input_image.data" : "image_url.url or image_url.data"
            )
        }
        guard let decoded = Data(base64Encoded: data) else {
            throw MultimodalRequestNormalizationError.invalidBase64("image")
        }
        normalized.imageBytes = decoded
        normalized.media.sourceKind = .mediaSourceInlineBytes
        normalized.media.byteLength = UInt64(decoded.count)
        return normalized
    }

    private func normalizeAudio(
        _ reference: OpenAIMultimodalAudioReference?
    ) throws -> Melix_Worker_V1_MessagePart {
        guard let reference else {
            throw MultimodalRequestNormalizationError.missingValue("input_audio")
        }

        var normalized = Melix_Worker_V1_MessagePart()
        normalized.media.mediaType = .audio
        normalized.media.mimeType = reference.mimeType ?? ""
        normalized.media.format = reference.format ?? ""
        normalized.media.filename = reference.filename ?? ""

        if let url = reference.url, !url.isEmpty {
            let receipt = try mediaURLAdmissionReceipt(url, mediaKind: "audio")
            normalized.audioUri = url.trimmingCharacters(in: .whitespacesAndNewlines)
            normalized.media.sourceKind = .mediaSourceUri
            apply(receipt, to: &normalized.media)
            return normalized
        }

        guard let data = reference.data, !data.isEmpty else {
            throw MultimodalRequestNormalizationError.missingValue("input_audio.data or input_audio.url")
        }
        guard let decoded = Data(base64Encoded: data) else {
            throw MultimodalRequestNormalizationError.invalidBase64("audio")
        }
        normalized.audioBytes = decoded
        normalized.media.sourceKind = .mediaSourceInlineBytes
        normalized.media.byteLength = UInt64(decoded.count)
        return normalized
    }

    private func normalizeVideo(
        _ reference: OpenAIMultimodalVideoReference?
    ) throws -> Melix_Worker_V1_MessagePart {
        guard let reference else {
            throw MultimodalRequestNormalizationError.missingValue("input_video")
        }

        var normalized = Melix_Worker_V1_MessagePart()
        normalized.media.mediaType = .video
        normalized.media.mimeType = reference.mimeType ?? ""
        normalized.media.format = try resolvedVideoFormat(reference)
        normalized.media.filename = resolvedVideoFilename(reference)

        if let durationMs = reference.durationMs {
            normalized.media.durationMs = try validatedPositiveBound(durationMs, field: "duration_ms")
        }
        if let frameBudget = reference.frameBudget {
            normalized.media.frameBudget = try validatedFrameBudget(frameBudget)
        }
        if let startMs = reference.startMs {
            normalized.media.startMs = try validatedNonNegativeBound(startMs, field: "start_ms")
        }
        if let endMs = reference.endMs {
            normalized.media.endMs = try validatedNonNegativeBound(endMs, field: "end_ms")
        }
        try validateVideoTimeBounds(normalized.media)

        if let url = reference.url?.trimmingCharacters(in: .whitespacesAndNewlines), !url.isEmpty {
            let receipt = try mediaURLAdmissionReceipt(url, mediaKind: "video")
            normalized.videoUri = url
            normalized.media.sourceKind = .mediaSourceUri
            apply(receipt, to: &normalized.media)
            return normalized
        }

        guard let data = reference.data, !data.isEmpty else {
            throw MultimodalRequestNormalizationError.missingValue("input_video.data or input_video.url")
        }
        guard let decoded = Data(base64Encoded: data) else {
            throw MultimodalRequestNormalizationError.invalidBase64("video")
        }
        normalized.videoBytes = decoded
        normalized.media.sourceKind = .mediaSourceInlineBytes
        normalized.media.byteLength = UInt64(decoded.count)
        return normalized
    }

    private func resolvedVideoFormat(_ reference: OpenAIMultimodalVideoReference) throws -> String {
        let trimmedFormat = reference.format?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() ?? ""
        if !trimmedFormat.isEmpty {
            guard Self.supportedVideoFormats.contains(trimmedFormat) else {
                throw MultimodalRequestNormalizationError.unsupportedMediaFormat("video", trimmedFormat)
            }
            return trimmedFormat
        }

        let trimmedMimeType = reference.mimeType?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() ?? ""
        if !trimmedMimeType.isEmpty {
            if let resolved = Self.supportedVideoMimeTypes[trimmedMimeType] {
                return resolved
            }
            throw MultimodalRequestNormalizationError.unsupportedMediaFormat("video", trimmedMimeType)
        }

        if let filename = reference.filename,
           let inferred = inferredVideoFormat(from: filename) {
            return inferred
        }
        if let url = reference.url,
           let inferred = inferredVideoFormat(from: url) {
            return inferred
        }

        throw MultimodalRequestNormalizationError.missingValue("input_video.format or input_video.mime_type")
    }

    private func resolvedVideoFilename(_ reference: OpenAIMultimodalVideoReference) -> String {
        if let filename = reference.filename?.trimmingCharacters(in: .whitespacesAndNewlines),
           !filename.isEmpty {
            return filename
        }
        if let url = reference.url,
           let candidate = url.split(separator: "/").last,
           !candidate.isEmpty {
            return String(candidate)
        }
        return "inline-video"
    }

    private func inferredVideoFormat(from rawValue: String) -> String? {
        let trimmed = rawValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            return nil
        }
        let candidate = URL(string: trimmed)?.pathExtension.lowercased()
            ?? URL(fileURLWithPath: trimmed).pathExtension.lowercased()
        guard !candidate.isEmpty, Self.supportedVideoFormats.contains(candidate) else {
            return nil
        }
        return candidate
    }

    private func validatedPositiveBound(_ value: Int, field: String) throws -> UInt32 {
        guard value > 0 else {
            throw MultimodalRequestNormalizationError.invalidPreprocessingBound(field, "must be greater than 0")
        }
        return UInt32(value)
    }

    private func validatedNonNegativeBound(_ value: Int, field: String) throws -> UInt32 {
        guard value >= 0 else {
            throw MultimodalRequestNormalizationError.invalidPreprocessingBound(field, "must be greater than or equal to 0")
        }
        return UInt32(value)
    }

    private func validatedFrameBudget(_ value: Int) throws -> UInt32 {
        guard value > 0 else {
            throw MultimodalRequestNormalizationError.invalidPreprocessingBound("frame_budget", "must be greater than 0")
        }
        guard value <= Self.maxVideoFrameBudget else {
            throw MultimodalRequestNormalizationError.invalidPreprocessingBound(
                "frame_budget",
                "must be less than or equal to \(Self.maxVideoFrameBudget)"
            )
        }
        return UInt32(value)
    }

    private func validateVideoTimeBounds(_ media: Melix_Worker_V1_MediaMetadata) throws {
        if media.endMs > 0, media.startMs > media.endMs {
            throw MultimodalRequestNormalizationError.invalidPreprocessingBound(
                "end_ms",
                "must be greater than or equal to start_ms"
            )
        }
        if media.durationMs > 0, media.endMs > media.durationMs {
            throw MultimodalRequestNormalizationError.invalidPreprocessingBound(
                "end_ms",
                "must be less than or equal to duration_ms"
            )
        }
    }

    private func mediaURLAdmissionReceipt(
        _ rawURL: String,
        mediaKind: String
    ) throws -> ExternalMediaURLAdmissionReceipt {
        do {
            return try ExternalMediaURLAdmission.validate(rawURL, mediaKind: mediaKind)
        } catch let error as ExternalMediaURLAdmissionError {
            if case let .unsupportedScheme(scheme) = error {
                throw MultimodalRequestNormalizationError.unsupportedURIScheme(mediaKind, scheme)
            }
            throw MultimodalRequestNormalizationError.externalMediaURLBlocked(error.operatorMessage)
        }
    }

    private func apply(
        _ receipt: ExternalMediaURLAdmissionReceipt,
        to media: inout Melix_Worker_V1_MediaMetadata
    ) {
        media.preprocessingHints["external_url_policy"] = receipt.policy
        media.preprocessingHints["external_url_source_kind"] = receipt.sourceKind
        if !receipt.scheme.isEmpty {
            media.preprocessingHints["external_url_scheme"] = receipt.scheme
        }
        if !receipt.host.isEmpty {
            media.preprocessingHints["external_url_host"] = receipt.host
        }
        media.preprocessingHints["external_url_receipt"] = receipt.reason
    }

    private func mediaPartSummary(
        for part: Melix_Worker_V1_MessagePart,
        turnIndex: Int,
        partIndex: Int
    ) -> NormalizedMediaPartSummary? {
        let mediaKind: String
        switch part.media.mediaType {
        case .image:
            mediaKind = "image"
        case .audio:
            mediaKind = "audio"
        case .video:
            mediaKind = "video"
        default:
            return nil
        }

        let sourceKind: String
        let source: String
        let digestPayload: Data?
        let byteLength: UInt64?
        switch part.media.sourceKind {
        case .mediaSourceInlineBytes:
            sourceKind = "inline_bytes"
            source = "inline_bytes"
            if part.imageBytes.isEmpty == false {
                digestPayload = part.imageBytes
                byteLength = UInt64(part.imageBytes.count)
            } else if part.audioBytes.isEmpty == false {
                digestPayload = part.audioBytes
                byteLength = UInt64(part.audioBytes.count)
            } else if part.videoBytes.isEmpty == false {
                digestPayload = part.videoBytes
                byteLength = UInt64(part.videoBytes.count)
            } else {
                digestPayload = nil
                byteLength = part.media.byteLength > 0 ? part.media.byteLength : nil
            }
        case .mediaSourceUri:
            sourceKind = part.media.preprocessingHints["external_url_source_kind"] ?? "uri"
            source = firstNonEmpty(part.imageUri, part.audioUri, part.videoUri) ?? "uri"
            digestPayload = Data(source.utf8)
            byteLength = nil
        default:
            return nil
        }

        return NormalizedMediaPartSummary(
            mediaKind: mediaKind,
            sourceKind: sourceKind,
            source: source,
            turnIndex: turnIndex,
            partIndex: partIndex,
            byteLength: byteLength,
            filename: part.media.filename,
            format: part.media.format,
            stableDigest: digestPayload.map(Self.sha256Hex)
        )
    }

    private func firstNonEmpty(_ values: String...) -> String? {
        values.first { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }?
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func sha256Hex(_ data: Data) -> String {
        SHA256.hash(data: data)
            .map { String(format: "%02x", $0) }
            .joined()
    }
}
