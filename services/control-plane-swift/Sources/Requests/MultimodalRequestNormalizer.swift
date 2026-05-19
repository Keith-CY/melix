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
        case imageURL = "image_url"
        case inputImage = "input_image"
        case inputAudio = "input_audio"
        case inputVideo = "input_video"
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
        case inputImage = "input_image"
        case inputAudio = "input_audio"
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
        case .imageURL:
            text = nil
            inputImage = nil
            inputAudio = nil
            inputVideo = nil
            if let inlineURL = try? container.decode(String.self, forKey: .imageURL) {
                imageURL = OpenAIMultimodalImageReference(
                    url: inlineURL,
                    detail: topLevelDetail,
                    mimeType: topLevelMimeType,
                    format: topLevelFormat,
                    filename: topLevelFilename
                )
            } else if let decoded = try container.decodeIfPresent(OpenAIMultimodalImageReference.self, forKey: .imageURL) {
                imageURL = OpenAIMultimodalImageReference(
                    url: decoded.url,
                    data: decoded.data,
                    detail: decoded.detail ?? topLevelDetail,
                    mimeType: decoded.mimeType ?? topLevelMimeType,
                    format: decoded.format ?? topLevelFormat,
                    filename: decoded.filename ?? topLevelFilename
                )
            } else {
                throw MultimodalRequestNormalizationError.missingValue("image_url")
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
        case .inputAudio:
            text = nil
            imageURL = nil
            inputImage = nil
            inputVideo = nil
            if let decoded = try container.decodeIfPresent(OpenAIMultimodalAudioReference.self, forKey: .inputAudio) {
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
                throw MultimodalRequestNormalizationError.missingValue("input_audio")
            }
        case .inputVideo:
            text = nil
            imageURL = nil
            inputImage = nil
            inputAudio = nil
            if let decoded = try container.decodeIfPresent(OpenAIMultimodalVideoReference.self, forKey: .inputVideo) {
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
                throw MultimodalRequestNormalizationError.missingValue("input_video")
            }
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(type, forKey: .type)

        switch type {
        case .text, .inputText:
            try container.encodeIfPresent(text, forKey: .text)
        case .imageURL:
            try container.encodeIfPresent(imageURL, forKey: .imageURL)
        case .inputImage:
            try container.encodeIfPresent(inputImage, forKey: .inputImage)
        case .inputAudio:
            try container.encodeIfPresent(inputAudio, forKey: .inputAudio)
        case .inputVideo:
            try container.encodeIfPresent(inputVideo, forKey: .inputVideo)
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
        case .imageURL:
            return try normalizeImage(part.imageURL, inlineOnly: false)
        case .inputImage:
            return try normalizeImage(part.inputImage, inlineOnly: true)
        case .inputAudio:
            return try normalizeAudio(part.inputAudio)
        case .inputVideo:
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
}
