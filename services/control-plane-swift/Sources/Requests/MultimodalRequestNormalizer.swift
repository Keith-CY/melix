import Foundation
import MelixWorkerProtocol

public enum MultimodalRequestNormalizationError: Error, Equatable {
    case missingValue(String)
    case invalidBase64(String)
    case unsupportedPartType(String)
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

public struct OpenAIMultimodalContentPart: Sendable, Codable, Equatable {
    public enum PartType: String, Sendable, Codable, Equatable {
        case text = "text"
        case inputText = "input_text"
        case imageURL = "image_url"
        case inputImage = "input_image"
        case inputAudio = "input_audio"
    }

    public let type: PartType
    public let text: String?
    public let imageURL: OpenAIMultimodalImageReference?
    public let inputImage: OpenAIMultimodalImageReference?
    public let inputAudio: OpenAIMultimodalAudioReference?

    enum CodingKeys: String, CodingKey {
        case type
        case text
        case imageURL = "image_url"
        case inputImage = "input_image"
        case inputAudio = "input_audio"
        case imageBase64 = "image_base64"
        case audioBase64 = "audio_base64"
        case mimeType = "mime_type"
        case format
        case detail
        case filename
    }

    public init(
        type: PartType,
        text: String? = nil,
        imageURL: OpenAIMultimodalImageReference? = nil,
        inputImage: OpenAIMultimodalImageReference? = nil,
        inputAudio: OpenAIMultimodalAudioReference? = nil
    ) {
        self.type = type
        self.text = text
        self.imageURL = imageURL
        self.inputImage = inputImage
        self.inputAudio = inputAudio
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        type = try container.decode(PartType.self, forKey: .type)

        let topLevelMimeType = try container.decodeIfPresent(String.self, forKey: .mimeType)
        let topLevelFormat = try container.decodeIfPresent(String.self, forKey: .format)
        let topLevelDetail = try container.decodeIfPresent(String.self, forKey: .detail)
        let topLevelFilename = try container.decodeIfPresent(String.self, forKey: .filename)

        switch type {
        case .text, .inputText:
            text = try container.decodeIfPresent(String.self, forKey: .text)
            imageURL = nil
            inputImage = nil
            inputAudio = nil
        case .imageURL:
            text = nil
            inputImage = nil
            inputAudio = nil
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
            normalized.imageUri = url
            normalized.media.sourceKind = .mediaSourceUri
            return normalized
        }

        guard let data = reference.data, !data.isEmpty else {
            throw MultimodalRequestNormalizationError.missingValue(inlineOnly ? "input_image.data" : "image_url.url or image_url.data")
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
            normalized.audioUri = url
            normalized.media.sourceKind = .mediaSourceUri
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
}
