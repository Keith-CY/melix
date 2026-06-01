import Foundation
import MelixWorkerProtocol

struct DeterministicVisionBackend: TextRuntimeBackend {
    let runtimeName: String = "deterministic-vision"
    private let tokenDelayNanos: UInt64
    private let probe = DeterministicVisionProbeStore()

    init(tokenDelayNanos: UInt64 = 20_000_000) {
        self.tokenDelayNanos = tokenDelayNanos
    }

    func runtimeStatsOverlay() async -> Melix_Worker_V1_RuntimeStats? {
        await probe.stats()
    }

    func loadModel(spec: Melix_Worker_V1_ModelSpec) async throws -> LoadedTextModel {
        LoadedTextModel(
            storage: DeterministicVisionModel(spec: spec),
            residentBytesHint: spec.modelKind == "ocr" ? 3_072 : 4_096
        )
    }

    func prefill(
        model: LoadedTextModel,
        messages: [Melix_Worker_V1_ChatMessage],
        prefillStepSize: UInt32,
        resumeHint: String,
        acceleration: Melix_Worker_V1_AccelerationPolicy,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> RuntimePrefillResult {
        try throwIfTextRuntimeCancellationRequested(shouldAbort)
        let visionModel = try resolvedVisionModel(from: model)
        let request = try DeterministicVisionRequest(messages: messages, model: visionModel)
        try throwIfTextRuntimeCancellationRequested(shouldAbort)
        let promptTokens = max(1, request.promptTokenCount)
        await probe.record(request: request, model: visionModel, firstTokenLatencyMs: 0)

        return RuntimePrefillResult(
            context: TextPrefillContext(
                storage: DeterministicVisionPrefillStorage(
                    request: request,
                    model: visionModel,
                    resumeHint: resumeHint
                ),
                promptTokens: promptTokens
            ),
            promptTokens: promptTokens,
            requestedPrefillStepTokens: Int(clamping: prefillStepSize),
            effectivePrefillWindowTokens: Int(clamping: max(prefillStepSize, 1)),
            appliedAcceleration: normalizedAccelerationPolicy(acceleration),
            acceleratedPrefillGainPct: 0,
            activeKVQuantizationRatio: activeKVQuantizationRatioPercent(for: acceleration)
        )
    }

    func generateEvents(
        model: LoadedTextModel,
        messages: [Melix_Worker_V1_ChatMessage],
        sampling: Melix_Worker_V1_SamplingConfig,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> AsyncThrowingStream<TextGenerationEvent, Error> {
        let visionModel = try resolvedVisionModel(from: model)
        let request = try DeterministicVisionRequest(messages: messages, model: visionModel)
        let response = responseText(for: request, model: visionModel, sampling: sampling)
        return stream(
            response: response,
            promptTokens: max(1, request.promptTokenCount),
            request: request,
            model: visionModel,
            shouldAbort: shouldAbort
        )
    }

    func decodeEvents(
        model: LoadedTextModel,
        draftModel: LoadedTextModel? = nil,
        context: TextPrefillContext,
        sampling: Melix_Worker_V1_SamplingConfig,
        maxOutputTokens: UInt32,
        decodeStepSize: UInt32,
        prefillToken: String,
        acceleration: Melix_Worker_V1_AccelerationPolicy,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> AsyncThrowingStream<TextGenerationEvent, Error> {
        guard let storage = context.storage as? DeterministicVisionPrefillStorage else {
            throw RuntimeUnavailableError(message: "Vision decode requires a Swift vision prefill context.")
        }
        let response = responseText(for: storage.request, model: storage.model, sampling: sampling)
        return stream(
            response: response,
            promptTokens: max(1, context.promptTokens),
            request: storage.request,
            model: storage.model,
            shouldAbort: shouldAbort
        )
    }

    private func stream(
        response: String,
        promptTokens: Int,
        request: DeterministicVisionRequest,
        model: DeterministicVisionModel,
        shouldAbort: @escaping @Sendable () -> Bool
    ) -> AsyncThrowingStream<TextGenerationEvent, Error> {
        AsyncThrowingStream { continuation in
            Task {
                let startedAt = ContinuousClock.now
                let chunks = deterministicVisionChunks(from: response)
                var emitted = 0
                var firstTokenLatencyMs: Double = 0

                for chunk in chunks {
                    if shouldAbort() {
                        break
                    }
                    if tokenDelayNanos > 0 {
                        try? await Task.sleep(nanoseconds: tokenDelayNanos)
                    }
                    if shouldAbort() {
                        break
                    }
                    emitted += 1
                    if emitted == 1 {
                        firstTokenLatencyMs = elapsedMillisecondsDouble(since: startedAt)
                    }
                    continuation.yield(.token(chunk))
                }

                let elapsed = startedAt.duration(to: .now)
                let elapsedSeconds = max(
                    Double(elapsed.components.seconds)
                        + Double(elapsed.components.attoseconds) / 1_000_000_000_000_000_000,
                    0.000_001
                )
                await probe.record(
                    request: request,
                    model: model,
                    firstTokenLatencyMs: firstTokenLatencyMs
                )
                continuation.yield(.summary(
                    TextGenerationSummary(
                        promptTokens: promptTokens,
                        completionTokens: emitted,
                        tokensPerSecond: emitted > 0 ? Double(emitted) / elapsedSeconds : 0
                    )
                ))
                continuation.finish()
            }
        }
    }
}

private struct DeterministicVisionModel: Sendable {
    let modelID: String
    let modelKind: String
    let metadata: [String: String]

    init(spec: Melix_Worker_V1_ModelSpec) {
        self.modelID = spec.modelID
        self.modelKind = spec.modelKind
        var metadata = spec.ext
        metadata.merge(spec.settings.ext) { current, _ in current }
        self.metadata = metadata
    }

    var isOCR: Bool {
        modelKind.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() == "ocr"
    }
}

private struct DeterministicVisionPrefillStorage: Sendable {
    let request: DeterministicVisionRequest
    let model: DeterministicVisionModel
    let resumeHint: String
}

private struct DeterministicVisionRequest: Sendable {
    let promptText: String
    let images: [DeterministicVisionImage]
    let videos: [DeterministicVisionVideo]
    let preprocessInputBytes: Int
    let preprocessLatencyMs: Double
    let promptTokenCount: Int

    init(
        messages: [Melix_Worker_V1_ChatMessage],
        model: DeterministicVisionModel
    ) throws {
        let startedAt = Date()
        var promptSegments: [String] = []
        var images: [DeterministicVisionImage] = []
        var videos: [DeterministicVisionVideo] = []
        var inputBytes = 0

        for message in messages {
            for part in message.parts {
                switch part.part {
                case .text(let text):
                    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
                    if !trimmed.isEmpty {
                        promptSegments.append(trimmed)
                    }
                case .imageBytes(let bytes):
                    let image = DeterministicVisionImage(
                        bytes: Data(bytes),
                        reference: "inline:image",
                        filename: part.media.filename.isEmpty ? "inline-image" : part.media.filename,
                        format: part.media.format,
                        mimeType: part.media.mimeType
                    )
                    images.append(image)
                    inputBytes += bytes.count
                case .imageUri(let uri):
                    let image = try DeterministicVisionImage(
                        uri: uri,
                        filename: part.media.filename,
                        format: part.media.format,
                        mimeType: part.media.mimeType
                    )
                    images.append(image)
                    inputBytes += image.bytes.count
                case .videoBytes(let bytes):
                    let video = try DeterministicVisionVideo(
                        bytes: Data(bytes),
                        reference: "inline:video",
                        metadata: part.media
                    )
                    videos.append(video)
                    inputBytes += bytes.count
                case .videoUri(let uri):
                    let video = try DeterministicVisionVideo(uri: uri, metadata: part.media)
                    videos.append(video)
                    inputBytes += video.byteLength
                case .audioUri, .audioBytes:
                    throw RuntimeUnavailableError(message: "Swift vision worker does not support audio message parts.")
                case nil:
                    continue
                }
            }
        }

        if model.isOCR {
            guard images.count == 1, videos.isEmpty else {
                throw RuntimeUnavailableError(message: "OCR only supports single-image requests.")
            }
        } else if images.isEmpty && videos.isEmpty {
            throw RuntimeUnavailableError(message: "No image or video input provided.")
        }

        let promptText = promptSegments.joined(separator: "\n")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        self.promptText = promptText
        self.images = images
        self.videos = videos
        self.preprocessInputBytes = inputBytes
        self.preprocessLatencyMs = max(0, Date().timeIntervalSince(startedAt) * 1_000.0)
        self.promptTokenCount = whitespaceTokenCount(promptText)
            + images.reduce(0) { $0 + max(1, $1.bytes.count / 8) }
            + videos.reduce(0) { $0 + max(1, $1.byteLength / 8) }
    }

    var effectiveVideoFrameCount: Int {
        videos.reduce(0) { $0 + $1.effectiveFrameCount }
    }

    var requestedVideoFrameBudget: Int {
        videos.reduce(0) { $0 + $1.requestedFrameBudget }
    }

    var effectiveVideoWindowMs: Int {
        videos.reduce(0) { $0 + $1.clipDurationMs }
    }

    var tempMediaArtifactCount: Int {
        images.filter { !$0.bytes.isEmpty }.count + videos.filter { !$0.bytes.isEmpty }.count
    }

    var tempMediaArtifactBytes: Int {
        images.reduce(0) { $0 + $1.bytes.count }
            + videos.reduce(0) { $0 + $1.bytes.count }
    }
}

private struct DeterministicVisionImage: Sendable {
    let bytes: Data
    let reference: String
    let filename: String
    let format: String
    let mimeType: String

    init(
        bytes: Data,
        reference: String,
        filename: String,
        format: String,
        mimeType: String
    ) {
        self.bytes = bytes
        self.reference = reference
        self.filename = filename
        self.format = format
        self.mimeType = mimeType
    }

    init(
        uri: String,
        filename: String,
        format: String,
        mimeType: String
    ) throws {
        let trimmed = uri.trimmingCharacters(in: .whitespacesAndNewlines)
        let resolvedURL: URL
        if let url = URL(string: trimmed), let scheme = url.scheme, !scheme.isEmpty {
            switch scheme.lowercased() {
            case "file":
                resolvedURL = url
            case "http", "https":
                throw RuntimeUnavailableError(message: "External image URL fetch is not implemented in the Swift vision worker.")
            default:
                throw RuntimeUnavailableError(message: "Unsupported image URI scheme: \(scheme)")
            }
        } else {
            resolvedURL = URL(fileURLWithPath: trimmed)
        }

        do {
            let bytes = try Data(contentsOf: resolvedURL)
            let resolvedFilename = filename.isEmpty ? resolvedURL.lastPathComponent : filename
            self.init(
                bytes: bytes,
                reference: trimmed,
                filename: resolvedFilename.isEmpty ? "local-image" : resolvedFilename,
                format: format.isEmpty ? resolvedURL.pathExtension : format,
                mimeType: mimeType
            )
        } catch {
            throw RuntimeUnavailableError(message: "Missing local image input: \(trimmed)")
        }
    }

    func decodedText() -> String {
        String(data: bytes, encoding: .utf8)?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    }
}

private struct DeterministicVisionVideo: Sendable {
    let bytes: Data
    let reference: String
    let filename: String
    let format: String
    let mimeType: String
    let byteLength: Int
    let durationMs: Int
    let requestedFrameBudget: Int
    let effectiveFrameCount: Int
    let clipStartMs: Int
    let clipEndMs: Int
    let clipDurationMs: Int

    init(
        bytes: Data,
        reference: String,
        metadata: Melix_Worker_V1_MediaMetadata
    ) throws {
        let resolvedFormat = try resolveVideoFormat(metadata: metadata, filename: metadata.filename, reference: reference)
        let startMs = max(0, Int(metadata.startMs))
        let endMs = effectiveClipEndMs(startMs: startMs, durationMs: Int(metadata.durationMs), endMs: Int(metadata.endMs))
        let clipDurationMs = max(0, endMs - startMs)
        let frameBudget = max(0, Int(metadata.frameBudget))
        self.bytes = bytes
        self.reference = reference
        self.filename = metadata.filename.isEmpty ? "inline-video.\(resolvedFormat)" : metadata.filename
        self.format = resolvedFormat
        self.mimeType = metadata.mimeType
        self.byteLength = bytes.count
        self.durationMs = Int(metadata.durationMs)
        self.requestedFrameBudget = frameBudget
        self.effectiveFrameCount = frameBudget > 0 ? frameBudget : defaultFrameCount(clipDurationMs: clipDurationMs)
        self.clipStartMs = startMs
        self.clipEndMs = endMs
        self.clipDurationMs = clipDurationMs
    }

    init(
        uri: String,
        metadata: Melix_Worker_V1_MediaMetadata
    ) throws {
        let trimmed = uri.trimmingCharacters(in: .whitespacesAndNewlines)
        if let url = URL(string: trimmed), let scheme = url.scheme, !scheme.isEmpty {
            switch scheme.lowercased() {
            case "file":
                let resolvedFormat = try resolveVideoFormat(
                    metadata: metadata,
                    filename: metadata.filename.isEmpty ? url.lastPathComponent : metadata.filename,
                    reference: trimmed
                )
                let startMs = max(0, Int(metadata.startMs))
                let endMs = effectiveClipEndMs(
                    startMs: startMs,
                    durationMs: Int(metadata.durationMs),
                    endMs: Int(metadata.endMs)
                )
                let clipDurationMs = max(0, endMs - startMs)
                let frameBudget = max(0, Int(metadata.frameBudget))
                let bytes = (try? Data(contentsOf: url)) ?? Data()
                self.bytes = bytes
                self.reference = trimmed
                self.filename = metadata.filename.isEmpty ? url.lastPathComponent : metadata.filename
                self.format = resolvedFormat
                self.mimeType = metadata.mimeType
                self.byteLength = bytes.isEmpty ? Int(metadata.byteLength) : bytes.count
                self.durationMs = Int(metadata.durationMs)
                self.requestedFrameBudget = frameBudget
                self.effectiveFrameCount = frameBudget > 0 ? frameBudget : defaultFrameCount(clipDurationMs: clipDurationMs)
                self.clipStartMs = startMs
                self.clipEndMs = endMs
                self.clipDurationMs = clipDurationMs
            case "http", "https":
                throw RuntimeUnavailableError(message: "Unsupported video URI scheme: \(scheme).")
            default:
                throw RuntimeUnavailableError(message: "Unsupported video URI scheme: \(scheme).")
            }
        } else {
            let fileURL = URL(fileURLWithPath: trimmed)
            let resolvedFormat = try resolveVideoFormat(
                metadata: metadata,
                filename: metadata.filename.isEmpty ? fileURL.lastPathComponent : metadata.filename,
                reference: trimmed
            )
            let startMs = max(0, Int(metadata.startMs))
            let endMs = effectiveClipEndMs(
                startMs: startMs,
                durationMs: Int(metadata.durationMs),
                endMs: Int(metadata.endMs)
            )
            let clipDurationMs = max(0, endMs - startMs)
            let frameBudget = max(0, Int(metadata.frameBudget))
            let bytes = (try? Data(contentsOf: fileURL)) ?? Data()
            self.bytes = bytes
            self.reference = trimmed
            self.filename = metadata.filename.isEmpty ? fileURL.lastPathComponent : metadata.filename
            self.format = resolvedFormat
            self.mimeType = metadata.mimeType
            self.byteLength = bytes.isEmpty ? Int(metadata.byteLength) : bytes.count
            self.durationMs = Int(metadata.durationMs)
            self.requestedFrameBudget = frameBudget
            self.effectiveFrameCount = frameBudget > 0 ? frameBudget : defaultFrameCount(clipDurationMs: clipDurationMs)
            self.clipStartMs = startMs
            self.clipEndMs = endMs
            self.clipDurationMs = clipDurationMs
        }
    }
}

private actor DeterministicVisionProbeStore {
    private var statsOverlay = Melix_Worker_V1_RuntimeStats()

    func record(
        request: DeterministicVisionRequest,
        model: DeterministicVisionModel,
        firstTokenLatencyMs: Double
    ) {
        statsOverlay.lastProbeKind = model.isOCR ? "ocr" : "vlm"
        statsOverlay.lastPreprocessLatencyMs = request.preprocessLatencyMs
        statsOverlay.lastPreprocessInputBytes = UInt64(max(0, request.preprocessInputBytes))
        statsOverlay.lastPreprocessPeakMemoryBytes = UInt64(max(0, request.preprocessInputBytes))
        statsOverlay.lastFirstTokenLatencyMs = firstTokenLatencyMs
        statsOverlay.lastVideoEffectiveFrameCount = UInt64(max(0, request.effectiveVideoFrameCount))
        statsOverlay.lastVideoRequestedFrameBudget = UInt64(max(0, request.requestedVideoFrameBudget))
        statsOverlay.lastVideoWindowMs = UInt64(max(0, request.effectiveVideoWindowMs))
        statsOverlay.lastTempMediaArtifactCount = UInt64(max(0, request.tempMediaArtifactCount))
        statsOverlay.lastTempMediaArtifactBytes = UInt64(max(0, request.tempMediaArtifactBytes))
        statsOverlay.lastTempMediaCleanupLatencyMs = 0
        statsOverlay.lastTempMediaCleanupFailureCount = 0
        statsOverlay.lastMultimodalDecodeMode = "baseline"
        statsOverlay.lastMultimodalFallbackReason = "not_reported"
        statsOverlay.lastMultimodalDecodeSyncMode = "baseline"
    }

    func stats() -> Melix_Worker_V1_RuntimeStats {
        statsOverlay
    }
}

private func resolvedVisionModel(from model: LoadedTextModel) throws -> DeterministicVisionModel {
    guard let visionModel = model.storage as? DeterministicVisionModel else {
        throw RuntimeUnavailableError(message: "Loaded model is not a Swift vision model container.")
    }
    return visionModel
}

private func responseText(
    for request: DeterministicVisionRequest,
    model: DeterministicVisionModel,
    sampling: Melix_Worker_V1_SamplingConfig
) -> String {
    if model.isOCR, let image = request.images.first {
        return applyStopSequences(
            to: image.decodedText(),
            stopSequences: effectiveOCRStopSequences(model: model, sampling: sampling)
        )
    }

    let promptText = request.promptText.isEmpty ? "Describe the image." : request.promptText
    if !request.videos.isEmpty && request.images.isEmpty {
        if request.videos.count == 1, let video = request.videos.first {
            return """
            Video content: \(video.filename)
            Frame policy: uniform_sample \(video.effectiveFrameCount) frame(s) from \(video.clipStartMs)ms to \(video.clipEndMs)ms
            Prompt: \(promptText)
            """
        }
        var lines = request.videos.enumerated().map { index, video in
            "Video \(index + 1): \(video.filename) [frames=\(video.effectiveFrameCount);start_ms=\(video.clipStartMs);end_ms=\(video.clipEndMs)]"
        }
        lines.append("Prompt: \(promptText)")
        return lines.joined(separator: "\n")
    }

    if request.images.count == 1, request.videos.isEmpty, let image = request.images.first {
        return "Image content: \(image.decodedText())\nPrompt: \(promptText)"
    }

    var lines = request.images.enumerated().map { index, image in
        "Image \(index + 1) content: \(image.decodedText())"
    }
    lines += request.videos.enumerated().map { index, video in
        "Video \(index + 1): \(video.filename) [frames=\(video.effectiveFrameCount);start_ms=\(video.clipStartMs);end_ms=\(video.clipEndMs)]"
    }
    lines.append("Prompt: \(promptText)")
    return lines.joined(separator: "\n")
}

private func effectiveOCRStopSequences(
    model: DeterministicVisionModel,
    sampling: Melix_Worker_V1_SamplingConfig
) -> [String] {
    let samplingStop = sampling.stop
        .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
        .filter { !$0.isEmpty }
    if !samplingStop.isEmpty {
        return samplingStop
    }
    return (model.metadata["ocr_stop_sequences"] ?? "")
        .split(separator: ",")
        .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
        .filter { !$0.isEmpty }
}

private func applyStopSequences(
    to text: String,
    stopSequences: [String]
) -> String {
    var stopIndex: String.Index?
    for sequence in stopSequences where !sequence.isEmpty {
        guard let candidate = text.range(of: sequence)?.lowerBound else {
            continue
        }
        if stopIndex == nil || candidate < stopIndex! {
            stopIndex = candidate
        }
    }
    guard let stopIndex else {
        return text
    }
    return String(text[..<stopIndex])
}

private func resolveVideoFormat(
    metadata: Melix_Worker_V1_MediaMetadata,
    filename: String,
    reference: String
) throws -> String {
    let format = metadata.format.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    if !format.isEmpty {
        guard supportedVideoFormats.contains(format) else {
            throw RuntimeUnavailableError(message: "Unsupported video format: \(format).")
        }
        return format
    }
    let mimeType = metadata.mimeType.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    if !mimeType.isEmpty {
        guard let resolved = supportedVideoMimeTypes[mimeType] else {
            throw RuntimeUnavailableError(message: "Unsupported video format: \(mimeType).")
        }
        return resolved
    }
    let suffix = URL(fileURLWithPath: filename.isEmpty ? reference : filename).pathExtension.lowercased()
    if supportedVideoFormats.contains(suffix) {
        return suffix
    }
    throw RuntimeUnavailableError(message: "input_video.format or input_video.mime_type is required.")
}

private func effectiveClipEndMs(
    startMs: Int,
    durationMs: Int,
    endMs: Int
) -> Int {
    if endMs > 0 {
        return endMs
    }
    if durationMs > 0 {
        return durationMs
    }
    return 0
}

private func defaultFrameCount(clipDurationMs: Int) -> Int {
    if clipDurationMs <= 0 {
        return 8
    }
    return min(16, max(4, Int((Double(clipDurationMs) / 4_000.0).rounded(.up))))
}

private func deterministicVisionChunks(from response: String) -> [String] {
    guard !response.isEmpty else {
        return []
    }
    return [response]
}

private func whitespaceTokenCount(_ value: String) -> Int {
    let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else {
        return 0
    }
    return max(1, trimmed.split(whereSeparator: \.isWhitespace).count)
}

private func elapsedMillisecondsDouble(since startedAt: ContinuousClock.Instant) -> Double {
    let elapsed = startedAt.duration(to: .now)
    return max(
        0,
        (Double(elapsed.components.seconds) * 1_000.0)
            + (Double(elapsed.components.attoseconds) / 1_000_000_000_000_000.0)
    )
}

private let supportedVideoFormats: Set<String> = ["mp4", "mov", "m4v", "webm"]
private let supportedVideoMimeTypes: [String: String] = [
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "video/x-m4v": "m4v",
    "video/webm": "webm",
]
