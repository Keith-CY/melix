import Foundation
import MelixControlPlaneCore
import MelixControlPlaneProtocol
import Observation

public actor MenuBarMetricsStore {
    private var values: [String: Double] = [:]

    public init() {}

    public func record(name: String, valueMs: Double) {
        values[name] = valueMs
    }

    public func snapshot() -> [String: Double] {
        values
    }
}

public struct RuntimeModelRow: Identifiable, Equatable, Sendable {
    public let modelID: String
    public let kind: String
    public let state: Melix_Controlplane_V1_ModelState
    public let stateText: String
    public let actionTitle: String
    public let maxContext: UInt32
    public let alias: String
    public let memoryPolicyText: String
    public let accelerationModeText: String
    public let accelerationProfileID: String
    public let residencyText: String
    public let memoryText: String
    public let memoryAlertText: String

    public var id: String {
        modelID
    }

    public var isLoaded: Bool {
        switch state {
        case .modelWarm, .modelPinned:
            return true
        default:
            return false
        }
    }
}

public struct RuntimeModelInfoState: Equatable, Sendable {
    public let modelID: String
    public let modelKind: String
    public let maxContext: UInt32
    public let supportedParsers: [String]
    public let supportedModalities: [String]
}

public struct RuntimeModelOperationState: Equatable, Sendable {
    public let modelID: String
    public let operation: String
    public let jobID: String
    public let stage: String
    public let pct: Float
    public let outputPath: String
    public let manifestJson: String
}

public struct RuntimeDoctorReportState: Equatable, Sendable {
    public let markdown: String
}

public struct RuntimeAdapterPackageState: Identifiable, Equatable, Sendable {
    public let id: String
    public let adapterName: String
    public let sourceModel: String
    public let datasetURI: String
    public let statusText: String
    public let outputPath: String
    public let targetRepo: String
    public let publishedRepo: String
    public let trainingDurationText: String
    public let publishDurationText: String
}

public struct RuntimeTrainingHistoryEntryState: Identifiable, Equatable, Sendable {
    public let id: String
    public let jobID: String
    public let modelID: String
    public let adapterName: String
    public let datasetURI: String
    public let statusText: String
    public let stageText: String
    public let outputPath: String
    public let targetRepo: String
}

public struct RuntimeBenchMetricState: Identifiable, Equatable, Sendable {
    public let id: String
    public let name: String
    public let value: String

    public init(name: String, value: String) {
        self.id = name
        self.name = name
        self.value = value
    }
}

public struct RuntimeBenchReportState: Equatable, Sendable {
    public let reportPath: String
    public let markdown: String
    public let metrics: [RuntimeBenchMetricState]
}

public struct DesktopChatTranscriptEntry: Identifiable, Equatable, Sendable {
    public enum Kind: String, Sendable {
        case user
        case assistant
        case reasoning
        case tool
        case error
    }

    public let id: String
    public let kind: Kind
    public let title: String
    public let body: String
    public let detail: String

    public init(id: String, kind: Kind, title: String, body: String, detail: String) {
        self.id = id
        self.kind = kind
        self.title = title
        self.body = body
        self.detail = detail
    }
}

public struct DesktopChatCapabilityRow: Identifiable, Equatable, Sendable {
    public let id: String
    public let title: String
    public let modelID: String
    public let detail: String
    public let isReady: Bool
}

@MainActor
@Observable
public final class RuntimeViewModel {
    public private(set) var statusTitle = "Melix Starting"
    public private(set) var serverStateText = "Starting"
    public private(set) var connectionStateText = "Connecting"
    public private(set) var connectionDetailText = "Awaiting handshake"
    public private(set) var models: [RuntimeModelRow] = []
    public private(set) var lastError: String?
    public private(set) var protocolVersion = "melix.controlplane.v1"
    public private(set) var serverVersion = "0.1.0"
    public private(set) var daemonInstanceID = ""
    public private(set) var features: [String] = []
    public private(set) var selectedModelInfo: RuntimeModelInfoState?
    public private(set) var lastModelOperation: RuntimeModelOperationState?
    public private(set) var lastDoctorReport: RuntimeDoctorReportState?
    public private(set) var lastBenchReport: RuntimeBenchReportState?
    public private(set) var adapterPackages: [RuntimeAdapterPackageState] = []
    public private(set) var trainingHistory: [RuntimeTrainingHistoryEntryState] = []
    public private(set) var chatTranscript: [DesktopChatTranscriptEntry] = []
    public private(set) var chatCapabilities: [DesktopChatCapabilityRow] = []
    public private(set) var chatStatusText = "Idle"
    public private(set) var lastChatUsageText = ""
    public private(set) var isChatStreaming = false
    public private(set) var lastChatRequestID = ""
    public private(set) var imageJobs: [Melix_Controlplane_V1_ImageJobSummary] = []
    public private(set) var imageStatusText = "Idle"
    public private(set) var selectedImageJobID = ""
    public var chatComposerText = ""
    public var selectedChatModelID = "melix-dev-text"
    public var imagePromptText = ""
    public var imageEditSourceURL = ""
    public var imageEditMaskURL = ""
    public var imageSize = "1024x1024"
    public var imageVariantCount: UInt32 = 1
    public var selectedImageModelID = "melix-dev-image"

    public var onStateChanged: (@MainActor @Sendable () -> Void)?

    private let client: any ControlPlaneXPCClient
    private let metrics: MenuBarMetricsStore
    private var subscriptionTask: Task<Void, Never>?
    private var lastSeenSeq: UInt64 = 0
    private var latestSnapshot = Melix_Controlplane_V1_ServerSnapshot()
    private var recentEvents: [DesktopLogEntry] = []
    private var connectionStateTransitions = 0.0
    private var chatConversationMessages: [ControlPlaneChatRequest.Message] = []
    private var activeAssistantEntryID: String?
    private var activeReasoningEntryID: String?
    private var activeToolEntryIDs: [String: String] = [:]

    public init(
        client: any ControlPlaneXPCClient,
        metrics: MenuBarMetricsStore = MenuBarMetricsStore()
    ) {
        self.client = client
        self.metrics = metrics
    }

    public var primaryModel: RuntimeModelRow? {
        models.first { $0.modelID == "melix-dev-text" } ?? models.first
    }

    public var latestAdapterPackage: RuntimeAdapterPackageState? {
        adapterPackages.first
    }

    public var imageModels: [RuntimeModelRow] {
        models.filter { $0.kind == "image" || $0.kind == "image_generation" }
    }

    public var selectedImageJob: Melix_Controlplane_V1_ImageJobSummary? {
        guard !selectedImageJobID.isEmpty else {
            return imageJobs.first
        }
        return imageJobs.first(where: { $0.jobID == selectedImageJobID }) ?? imageJobs.first
    }

    public var desktopFoundationState: DesktopFoundationState {
        DesktopFoundationState.build(
            statusTitle: statusTitle,
            serverStateText: serverStateText,
            connectionStateText: connectionStateText,
            connectionDetailText: connectionDetailText,
            snapshot: latestSnapshot,
            protocolVersion: protocolVersion,
            serverVersion: serverVersion,
            daemonInstanceID: daemonInstanceID,
            features: features,
            lastError: lastError,
            recentEvents: recentEvents
        )
    }

    public func start() async {
        await transitionConnectionState(to: "Connecting", detail: "Awaiting handshake")
        let handshakeStartedAt = Date()

        do {
            let response = try await client.handshake()
            protocolVersion = response.protocolVersion
            serverVersion = response.serverVersion
            daemonInstanceID = response.daemonInstanceID
            features = response.features
            await metrics.record(
                name: "menu.handshake_ms",
                valueMs: Date().timeIntervalSince(handshakeStartedAt) * 1_000
            )

            let hydrationStartedAt = Date()
            apply(snapshot: response.snapshot)
            await metrics.record(
                name: "menu.hydration_ms",
                valueMs: Date().timeIntervalSince(hydrationStartedAt) * 1_000
            )
            await startSubscription(lastSeenSeq: lastSeenSeq, isReconnect: false)
        } catch {
            await transitionConnectionState(to: "Degraded", detail: "Handshake failed")
            lastError = String(describing: error)
            statusTitle = "Melix Error"
            notifyStateChanged()
        }
    }

    public func refreshDesktopFoundation() async {
        let startedAt = Date()

        do {
            let snapshot = try await client.serverSnapshot()
            apply(snapshot: snapshot)
            let elapsedMs = Date().timeIntervalSince(startedAt) * 1_000
            await metrics.record(
                name: "menu.foundation_refresh_ms",
                valueMs: elapsedMs
            )
            if snapshot.imageJobs.isEmpty == false {
                await metrics.record(name: "desktop.image_refresh_ms", valueMs: elapsedMs)
            }
        } catch {
            recordLocalError(String(describing: error))
            notifyStateChanged()
        }
    }

    public func loadModel(modelID: String) async {
        let startedAt = Date()
        do {
            let model = try await client.loadModel(modelID: modelID)
            await metrics.record(
                name: "menu.model_load_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            upsert(model: model)
        } catch {
            recordLocalError(String(describing: error))
        }
        notifyStateChanged()
    }

    public func submitChatPrompt() async {
        let prompt = chatComposerText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !prompt.isEmpty else {
            return
        }
        guard !isChatStreaming else {
            return
        }

        let modelID = resolvedChatModelID()
        chatComposerText = ""
        let startedAt = Date()
        let userMessage = ControlPlaneChatRequest.Message(role: "user", content: prompt)
        chatConversationMessages.append(userMessage)
        appendChatEntry(
            id: "user-\(UUID().uuidString)",
            kind: .user,
            title: "User",
            body: prompt,
            detail: modelID
        )
        chatStatusText = "Preparing"
        lastChatUsageText = ""
        isChatStreaming = true
        notifyStateChanged()

        if models.contains(where: { $0.modelID == modelID && $0.isLoaded }) == false {
            await loadModel(modelID: modelID)
        }

        do {
            let execution = try await client.startChat(
                ControlPlaneChatRequest(
                    modelID: modelID,
                    messages: chatConversationMessages
                )
            )
            lastChatRequestID = execution.requestID
            await metrics.record(
                name: "menu.chat_submit_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )

            var recordedFirstDelta = false
            var reasoningDeltaCount = 0
            var toolDeltaCount = 0

            for try await event in execution.stream {
                if recordedFirstDelta == false {
                    switch event {
                    case .tokenDelta, .reasoningDelta, .toolCallDelta:
                        recordedFirstDelta = true
                        await metrics.record(
                            name: "menu.chat_first_delta_ms",
                            valueMs: Date().timeIntervalSince(startedAt) * 1_000
                        )
                    default:
                        break
                    }
                }

                switch event {
                case .queued(let lane, let queuePosition, _):
                    chatStatusText = "Queued • \(lane) • #\(queuePosition)"
                case .admitted(let lane, let workerID, _):
                    chatStatusText = "Admitted • \(lane) • \(workerID)"
                case .prefillStarted(let inputTokens):
                    chatStatusText = "Prefill • \(inputTokens) tokens"
                case .decodeStarted(let decodeHandle, _):
                    chatStatusText = decodeHandle.isEmpty ? "Decode" : "Decode • \(decodeHandle)"
                case .tokenDelta(let text):
                    appendAssistantDelta(text, requestID: execution.requestID)
                case .reasoningDelta(let text):
                    reasoningDeltaCount += 1
                    appendReasoningDelta(text, requestID: execution.requestID)
                case .toolCallDelta(let callID, let toolName, let argumentsFragment):
                    toolDeltaCount += 1
                    appendToolDelta(callID: callID, toolName: toolName, argumentsFragment: argumentsFragment)
                case .usage(let promptTokens, let completionTokens):
                    lastChatUsageText = "\(promptTokens) prompt • \(completionTokens) completion"
                case .completed(let finishReason, let assistantText, let reasoningText):
                    chatStatusText = finishReason.isEmpty ? "Completed" : "Completed • \(finishReason)"
                    finalizeAssistantText(assistantText, requestID: execution.requestID)
                    finalizeReasoningText(reasoningText, requestID: execution.requestID)
                case .failed(let code, let message):
                    chatStatusText = code.isEmpty ? "Failed" : "Failed • \(code)"
                    let failureMessage = message.isEmpty ? "Chat request failed." : message
                    lastError = failureMessage
                    appendChatEntry(
                        id: "error-\(UUID().uuidString)",
                        kind: .error,
                        title: "Error",
                        body: failureMessage,
                        detail: code
                    )
                case .heartbeat:
                    chatStatusText = "Streaming"
                }

                notifyStateChanged()
            }

            await metrics.record(
                name: "menu.chat_stream_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            await metrics.record(
                name: "menu.chat_reasoning_delta_count",
                valueMs: Double(reasoningDeltaCount)
            )
            await metrics.record(
                name: "menu.chat_tool_delta_count",
                valueMs: Double(toolDeltaCount)
            )
            commitAssistantMessageIfNeeded()
        } catch {
            lastError = String(describing: error)
            chatStatusText = "Failed"
            appendChatEntry(
                id: "error-\(UUID().uuidString)",
                kind: .error,
                title: "Error",
                body: String(describing: error),
                detail: modelID
            )
        }

        isChatStreaming = false
        activeAssistantEntryID = nil
        activeReasoningEntryID = nil
        activeToolEntryIDs.removeAll()
        notifyStateChanged()
    }

    public func clearChatTranscript() {
        chatTranscript = []
        chatConversationMessages = []
        chatStatusText = "Idle"
        lastChatUsageText = ""
        lastChatRequestID = ""
        activeAssistantEntryID = nil
        activeReasoningEntryID = nil
        activeToolEntryIDs.removeAll()
        notifyStateChanged()
    }

    public func selectImageJob(jobID: String) {
        selectedImageJobID = jobID
        notifyStateChanged()
    }

    public func submitImageGeneration() async {
        let prompt = imagePromptText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !prompt.isEmpty else {
            return
        }

        let modelID = resolvedImageModelID()
        if models.contains(where: { $0.modelID == modelID && $0.isLoaded }) == false {
            await loadModel(modelID: modelID)
        }

        let startedAt = Date()
        imageStatusText = "Submitting"
        notifyStateChanged()

        do {
            let job = try await client.generateImage(
                ControlPlaneImageGenerationRequest(
                    modelID: modelID,
                    prompt: prompt,
                    size: imageSize,
                    n: max(1, imageVariantCount)
                )
            )
            upsert(imageJob: job)
            imageStatusText = Self.imageStatusText(for: job)
            imagePromptText = ""
            await metrics.record(
                name: "desktop.image_action_latency_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
        } catch {
            imageStatusText = "Failed"
            recordLocalError(String(describing: error))
        }

        notifyStateChanged()
    }

    public func submitImageEdit() async {
        let sourceURL = imageEditSourceURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !sourceURL.isEmpty else {
            imageStatusText = "Failed"
            recordLocalError("Image edit source is required.")
            notifyStateChanged()
            return
        }

        let modelID = resolvedImageModelID()
        if models.contains(where: { $0.modelID == modelID && $0.isLoaded }) == false {
            await loadModel(modelID: modelID)
        }

        let startedAt = Date()
        imageStatusText = "Submitting"
        notifyStateChanged()

        do {
            let job = try await client.editImage(
                ControlPlaneImageEditRequest(
                    modelID: modelID,
                    prompt: imagePromptText.trimmingCharacters(in: .whitespacesAndNewlines),
                    imageURL: sourceURL,
                    maskURL: imageEditMaskURL.trimmingCharacters(in: .whitespacesAndNewlines),
                    strength: 1,
                    size: imageSize,
                    n: max(1, imageVariantCount)
                )
            )
            upsert(imageJob: job)
            imageStatusText = Self.imageStatusText(for: job)
            imagePromptText = ""
            await metrics.record(
                name: "desktop.image_action_latency_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
        } catch {
            imageStatusText = "Failed"
            recordLocalError(String(describing: error))
        }

        notifyStateChanged()
    }

    public func cancelSelectedImageJob() async {
        guard let job = selectedImageJob, !job.requestID.isEmpty, job.cancelable else {
            return
        }

        let startedAt = Date()
        imageStatusText = "Canceling"
        notifyStateChanged()

        do {
            _ = try await client.cancelRequest(requestID: job.requestID)
            await metrics.record(
                name: "desktop.image_cancel_latency_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
        } catch {
            imageStatusText = "Failed"
            recordLocalError(String(describing: error))
        }

        notifyStateChanged()
    }

    public func loadPrimaryModel() async {
        guard let modelID = primaryModel?.modelID else {
            return
        }
        await loadModel(modelID: modelID)
    }

    public func unloadModel(modelID: String) async {
        let startedAt = Date()
        do {
            let model = try await client.unloadModel(modelID: modelID)
            await metrics.record(
                name: "menu.model_unload_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            upsert(model: model)
        } catch {
            recordLocalError(String(describing: error))
        }
        notifyStateChanged()
    }

    public func unloadPrimaryModel() async {
        guard let modelID = primaryModel?.modelID else {
            return
        }
        await unloadModel(modelID: modelID)
    }

    public func updateModelSettings(
        modelID: String,
        alias: String,
        pinOnLoad: Bool,
        memoryPolicy: String,
        accelerationMode: String,
        accelerationProfileID: String
    ) async {
        let startedAt = Date()
        do {
            let model = try await client.updateModelSettings(
                modelID: modelID,
                values: [
                    "alias": alias,
                    "pin_on_load": pinOnLoad ? "true" : "false",
                    "memory_policy": memoryPolicy,
                    "default_acceleration_mode": accelerationMode,
                    "acceleration_profile_id": accelerationProfileID,
                ]
            )
            await metrics.record(
                name: "menu.model_settings_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            upsert(model: model)
        } catch {
            recordLocalError(String(describing: error))
        }
        notifyStateChanged()
    }

    public func updatePrimaryModelForLatency() async {
        guard let model = primaryModel else {
            return
        }
        await updateModelSettings(
            modelID: model.modelID,
            alias: model.alias.isEmpty ? "Melix Text Turbo" : model.alias,
            pinOnLoad: true,
            memoryPolicy: "pinned",
            accelerationMode: "speculative_decode",
            accelerationProfileID: "draft-q4"
        )
    }

    public func fetchModelInfo(modelID: String) async {
        let startedAt = Date()
        do {
            let info = try await client.modelInfo(modelID: modelID)
            await metrics.record(
                name: "menu.model_info_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            selectedModelInfo = RuntimeModelInfoState(
                modelID: modelID,
                modelKind: info.modelKind,
                maxContext: info.maxContext,
                supportedParsers: info.supportedParsers,
                supportedModalities: info.supportedModalities
            )
        } catch {
            recordLocalError(String(describing: error))
        }
        notifyStateChanged()
    }

    public func inspectPrimaryModel() async {
        guard let modelID = primaryModel?.modelID else {
            return
        }
        await fetchModelInfo(modelID: modelID)
    }

    public func runModelOperation(
        modelID: String,
        operation: String,
        outputDir: String,
        weightQuant: String = "",
        kvQuant: String = "",
        ext: [String: String] = [:],
        refreshProductToolingState: Bool = false
    ) async {
        let startedAt = Date()
        do {
            let result = try await client.runModelOperation(
                modelID: modelID,
                operation: operation,
                outputDir: outputDir,
                weightQuant: weightQuant,
                kvQuant: kvQuant,
                ext: ext
            )
            await metrics.record(
                name: "menu.model_operation_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            lastModelOperation = RuntimeModelOperationState(
                modelID: modelID,
                operation: result.operation,
                jobID: result.jobID,
                stage: result.stage,
                pct: result.pct,
                outputPath: result.outputPath,
                manifestJson: result.manifestJson
            )
            if refreshProductToolingState {
                await refreshModelOpsProductState(modelID: modelID, notify: false)
            }
        } catch {
            recordLocalError(String(describing: error))
        }
        notifyStateChanged()
    }

    public func quantizePrimaryModel() async {
        guard let modelID = primaryModel?.modelID else {
            return
        }
        await runModelOperation(
            modelID: modelID,
            operation: "quantize",
            outputDir: "/tmp/melix-quantize",
            weightQuant: "q4",
            kvQuant: "q8"
        )
    }

    public func downloadPrimaryModel() async {
        guard let modelID = primaryModel?.modelID else {
            return
        }
        await runModelOperation(
            modelID: modelID,
            operation: "download",
            outputDir: "/tmp/melix-download"
        )
    }

    public func uploadPrimaryModel() async {
        guard let modelID = primaryModel?.modelID else {
            return
        }
        await runModelOperation(
            modelID: modelID,
            operation: "upload",
            outputDir: "/tmp/melix-upload",
            ext: ["target_repo": "melix/upload-target"]
        )
    }

    public func trainPrimaryModel() async {
        guard let modelID = primaryModel?.modelID else {
            return
        }
        await runModelOperation(
            modelID: modelID,
            operation: "train_lora",
            outputDir: "/tmp/melix-train-lora",
            ext: [
                "adapter_name": "melix-dev-adapter",
                "dataset_uri": "datasets/melix-dev",
                "target_repo": "melix/adapters/melix-dev-adapter",
            ],
            refreshProductToolingState: true
        )
    }

    public func refreshModelOpsProductState() async {
        guard let modelID = primaryModel?.modelID else {
            return
        }
        await refreshModelOpsProductState(modelID: modelID, notify: true)
    }

    public func publishLatestAdapter() async {
        guard let modelID = primaryModel?.modelID, let adapter = latestAdapterPackage else {
            return
        }

        await runModelOperation(
            modelID: modelID,
            operation: "upload",
            outputDir: "/tmp/melix-upload-adapter",
            ext: [
                "target_repo": adapter.targetRepo.isEmpty ? "melix/adapters/\(adapter.adapterName)" : adapter.targetRepo,
                "artifact_kind": "adapter",
                "artifact_path": adapter.outputPath,
                "adapter_name": adapter.adapterName,
            ],
            refreshProductToolingState: true
        )
    }

    public func runDoctor() async {
        let startedAt = Date()
        do {
            let report = try await client.runDoctor()
            await metrics.record(
                name: "menu.ops_doctor_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            lastDoctorReport = RuntimeDoctorReportState(markdown: report)
        } catch {
            recordLocalError(String(describing: error))
        }
        notifyStateChanged()
    }

    public func runBench() async {
        let startedAt = Date()
        do {
            let result = try await client.runBench()
            await metrics.record(
                name: "menu.ops_bench_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            for (name, value) in result.metrics {
                latestSnapshot.metrics.values[name] = value
            }
            lastBenchReport = RuntimeBenchReportState(
                reportPath: result.reportPath,
                markdown: result.reportMarkdown,
                metrics: result.metrics.keys.sorted().map { key in
                    RuntimeBenchMetricState(name: key, value: String(format: "%.2f", result.metrics[key] ?? 0))
                }
            )
        } catch {
            recordLocalError(String(describing: error))
        }
        notifyStateChanged()
    }

    private func refreshModelOpsProductState(modelID: String, notify: Bool) async {
        let startedAt = Date()
        do {
            let result = try await client.runModelOperation(
                modelID: modelID,
                operation: "registry_snapshot",
                outputDir: "/tmp/melix-model-ops-registry",
                weightQuant: "",
                kvQuant: "",
                ext: [:]
            )
            await metrics.record(
                name: "menu.model_ops_refresh_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            applyModelOpsSnapshot(manifestJSON: result.manifestJson)
        } catch {
            recordLocalError(String(describing: error))
        }
        if notify {
            notifyStateChanged()
        }
    }

    private func applyModelOpsSnapshot(manifestJSON: String) {
        guard
            let data = manifestJSON.data(using: .utf8),
            let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            recordLocalError("Model operations registry snapshot could not be decoded.")
            return
        }

        let adapters = (payload["adapters"] as? [[String: Any]]) ?? []
        let jobs = (payload["jobs"] as? [[String: Any]]) ?? []
        adapterPackages = adapters.map(Self.makeAdapterPackageState)
        trainingHistory = jobs
            .filter { Self.stringValue("operation", from: $0) == "train_lora" }
            .map(Self.makeTrainingHistoryEntryState)
    }

    private func consume(event: Melix_Controlplane_V1_ControlPlaneEvent) async {
        handle(event: event)
    }

    private func handle(event: Melix_Controlplane_V1_ControlPlaneEvent) {
        lastSeenSeq = max(lastSeenSeq, event.seq)
        record(event: event)

        switch event.payload {
        case .serverState(let serverStateChanged):
            latestSnapshot.serverState = serverStateChanged.state
            serverStateText = Self.serverStateText(serverStateChanged.state)
            statusTitle = "Melix \(serverStateText)"
        case .modelState(let stateChanged):
            var model = existingModelSummary(for: stateChanged.modelID)
            model.modelID = stateChanged.modelID
            model.state = stateChanged.state
            upsert(model: model)
        case .sessionState(let sessionStateChanged):
            upsert(session: sessionStateChanged.state)
        case .cacheStats(let cacheStats):
            latestSnapshot.cache = cacheStats.summary
        case .resourcePressure(let resourcePressure):
            latestSnapshot.resources = resourcePressure.resources
        case .log(let logEvent):
            if logEvent.level.lowercased() == "error" {
                lastError = logEvent.message
            }
        case .imageJob(let imageJobChanged):
            upsert(imageJob: imageJobChanged.job)
            imageStatusText = Self.imageStatusText(for: imageJobChanged.job)
        default:
            break
        }

        refreshChatCapabilities()

        notifyStateChanged()
    }

    private func apply(snapshot: Melix_Controlplane_V1_ServerSnapshot) {
        latestSnapshot = snapshot
        serverStateText = Self.serverStateText(snapshot.serverState)
        statusTitle = "Melix \(serverStateText)"
        models = snapshot.models
            .sorted { $0.modelID < $1.modelID }
            .map(makeRuntimeModelRow)
        refreshImageState()
        refreshChatCapabilities()
        notifyStateChanged()
    }

    private func upsert(model: Melix_Controlplane_V1_ModelSummary) {
        let row = makeRuntimeModelRow(model)
        var modelSummary = model
        if modelSummary.features.isEmpty {
            modelSummary.features = ["chat"]
        }
        if let snapshotIndex = latestSnapshot.models.firstIndex(where: { $0.modelID == model.modelID }) {
            latestSnapshot.models[snapshotIndex] = modelSummary
        } else {
            latestSnapshot.models.append(modelSummary)
            latestSnapshot.models.sort { $0.modelID < $1.modelID }
        }
        if let index = models.firstIndex(where: { $0.modelID == model.modelID }) {
            models[index] = row
        } else {
            models.append(row)
            models.sort { $0.modelID < $1.modelID }
        }
        refreshImageState()
        refreshChatCapabilities()
    }

    private func upsert(session: Melix_Controlplane_V1_SessionState) {
        var summary = Melix_Controlplane_V1_SessionSummary()
        summary.sessionID = session.sessionID
        summary.activeBranchID = session.activeBranchID
        summary.branchCount = UInt32(session.branches.count)
        summary.latestRequestID = session.latestRequestID
        summary.latestSnapshotID = session.latestSnapshotID

        if let index = latestSnapshot.sessions.firstIndex(where: { $0.sessionID == session.sessionID }) {
            latestSnapshot.sessions[index] = summary
        } else {
            latestSnapshot.sessions.append(summary)
            latestSnapshot.sessions.sort { $0.sessionID < $1.sessionID }
        }
    }

    private func existingModelSummary(for modelID: String) -> Melix_Controlplane_V1_ModelSummary {
        if let model = latestSnapshot.models.first(where: { $0.modelID == modelID }) {
            return model
        }

        if let row = models.first(where: { $0.modelID == modelID }) {
            var model = Melix_Controlplane_V1_ModelSummary()
            model.modelID = row.modelID
            model.kind = row.kind
            model.state = row.state
            model.maxContext = row.maxContext
            model.features = ["chat"]
            return model
        }

        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = modelID
        model.kind = "text"
        model.state = .modelDiscovered
        model.maxContext = 8192
        model.features = ["chat"]
        return model
    }

    private func upsert(imageJob: Melix_Controlplane_V1_ImageJobSummary) {
        if let index = latestSnapshot.imageJobs.firstIndex(where: { $0.jobID == imageJob.jobID }) {
            latestSnapshot.imageJobs[index] = imageJob
        } else {
            latestSnapshot.imageJobs.append(imageJob)
        }
        refreshImageState(preferredJobID: imageJob.jobID)
    }

    private func recordLocalError(_ message: String) {
        lastError = message
        recentEvents.insert(
            DesktopLogEntry(kind: "error", message: message, detail: "local", level: "error"),
            at: 0
        )
        trimRecentEvents()
    }

    private func record(event: Melix_Controlplane_V1_ControlPlaneEvent) {
        let entry = DesktopLogEntry(
            kind: event.eventType,
            message: Self.eventMessage(for: event),
            detail: event.source.isEmpty ? "control-plane" : event.source,
            level: Self.eventLevel(for: event)
        )
        recentEvents.insert(entry, at: 0)
        trimRecentEvents()
    }

    private func resolvedChatModelID() -> String {
        if models.contains(where: { $0.modelID == selectedChatModelID && $0.kind == "text" }) {
            return selectedChatModelID
        }
        if let textModel = models.first(where: { $0.kind == "text" }) {
            selectedChatModelID = textModel.modelID
            return textModel.modelID
        }
        return selectedChatModelID
    }

    private func resolvedImageModelID() -> String {
        if models.contains(where: { $0.modelID == selectedImageModelID && Self.isImageModelKind($0.kind) }) {
            return selectedImageModelID
        }
        if let imageModel = models.first(where: { Self.isImageModelKind($0.kind) }) {
            selectedImageModelID = imageModel.modelID
            return imageModel.modelID
        }
        return selectedImageModelID
    }

    private func refreshImageState(preferredJobID: String? = nil) {
        if models.contains(where: { $0.modelID == selectedImageModelID && Self.isImageModelKind($0.kind) }) == false,
           let imageModel = models.first(where: { Self.isImageModelKind($0.kind) }) {
            selectedImageModelID = imageModel.modelID
        }

        imageJobs = latestSnapshot.imageJobs.sorted { lhs, rhs in
            if lhs.updatedAtUnixMs == rhs.updatedAtUnixMs {
                return lhs.jobID > rhs.jobID
            }
            return lhs.updatedAtUnixMs > rhs.updatedAtUnixMs
        }

        if let preferredJobID, imageJobs.contains(where: { $0.jobID == preferredJobID }) {
            selectedImageJobID = preferredJobID
        } else if imageJobs.contains(where: { $0.jobID == selectedImageJobID }) == false {
            selectedImageJobID = imageJobs.first?.jobID ?? ""
        }

        if imageJobs.isEmpty, imageStatusText != "Failed" {
            imageStatusText = "Idle"
        }
    }

    private func refreshChatCapabilities() {
        if models.contains(where: { $0.modelID == selectedChatModelID }) == false {
            if let textModel = models.first(where: { $0.kind == "text" }) {
                selectedChatModelID = textModel.modelID
            }
        }

        let capabilitySpecs: [(String, String, [String])] = [
            ("text", "Interactive Text", ["chat"]),
            ("ocr", "OCR", ["ocr"]),
            ("vlm", "Vision Analysis", ["vlm", "vision"]),
            ("transcription", "Transcription", ["transcription"]),
            ("speech", "Speech", ["speech"]),
        ]

        chatCapabilities = capabilitySpecs.compactMap { capabilityID, title, featureHints in
            guard let model = latestSnapshot.models.first(where: { summary in
                summary.kind == capabilityID || summary.features.contains(where: { featureHints.contains($0.lowercased()) })
            }) else {
                return nil
            }
            let stateText = Self.modelStateText(model.state)
            return DesktopChatCapabilityRow(
                id: capabilityID,
                title: title,
                modelID: model.modelID,
                detail: "\(model.modelID) • \(stateText)",
                isReady: model.state == .modelWarm || model.state == .modelPinned
            )
        }
    }

    private func appendAssistantDelta(_ text: String, requestID: String) {
        guard !text.isEmpty else { return }
        let entryID = activeAssistantEntryID ?? "assistant-\(requestID)"
        activeAssistantEntryID = entryID
        appendBody(text, toEntryID: entryID, kind: .assistant, title: "Assistant", detail: requestID)
    }

    private func appendReasoningDelta(_ text: String, requestID: String) {
        guard !text.isEmpty else { return }
        let entryID = activeReasoningEntryID ?? "reasoning-\(requestID)"
        activeReasoningEntryID = entryID
        appendBody(text, toEntryID: entryID, kind: .reasoning, title: "Reasoning", detail: requestID)
    }

    private func appendToolDelta(callID: String, toolName: String, argumentsFragment: String) {
        let normalizedCallID = callID.isEmpty ? UUID().uuidString : callID
        let entryID = activeToolEntryIDs[normalizedCallID] ?? "tool-\(normalizedCallID)"
        activeToolEntryIDs[normalizedCallID] = entryID
        let title = toolName.isEmpty ? "Tool Call" : "Tool • \(toolName)"
        appendBody(argumentsFragment, toEntryID: entryID, kind: .tool, title: title, detail: normalizedCallID)
    }

    private func finalizeAssistantText(_ assistantText: String, requestID: String) {
        guard !assistantText.isEmpty else { return }
        let entryID = activeAssistantEntryID ?? "assistant-\(requestID)"
        activeAssistantEntryID = entryID
        replaceBodyIfEmpty(assistantText, entryID: entryID, kind: .assistant, title: "Assistant", detail: requestID)
    }

    private func finalizeReasoningText(_ reasoningText: String, requestID: String) {
        guard !reasoningText.isEmpty else { return }
        let entryID = activeReasoningEntryID ?? "reasoning-\(requestID)"
        activeReasoningEntryID = entryID
        replaceBodyIfEmpty(reasoningText, entryID: entryID, kind: .reasoning, title: "Reasoning", detail: requestID)
    }

    private func commitAssistantMessageIfNeeded() {
        guard
            let entryID = activeAssistantEntryID,
            let entry = chatTranscript.first(where: { $0.id == entryID }),
            !entry.body.isEmpty
        else {
            return
        }

        if chatConversationMessages.last != ControlPlaneChatRequest.Message(role: "assistant", content: entry.body) {
            chatConversationMessages.append(.init(role: "assistant", content: entry.body))
        }
    }

    private func appendChatEntry(
        id: String,
        kind: DesktopChatTranscriptEntry.Kind,
        title: String,
        body: String,
        detail: String
    ) {
        chatTranscript.append(
            DesktopChatTranscriptEntry(
                id: id,
                kind: kind,
                title: title,
                body: body,
                detail: detail
            )
        )
    }

    private func appendBody(
        _ text: String,
        toEntryID entryID: String,
        kind: DesktopChatTranscriptEntry.Kind,
        title: String,
        detail: String
    ) {
        if let index = chatTranscript.firstIndex(where: { $0.id == entryID }) {
            let existing = chatTranscript[index]
            chatTranscript[index] = DesktopChatTranscriptEntry(
                id: existing.id,
                kind: existing.kind,
                title: existing.title,
                body: existing.body + text,
                detail: existing.detail
            )
            return
        }

        appendChatEntry(id: entryID, kind: kind, title: title, body: text, detail: detail)
    }

    private func replaceBodyIfEmpty(
        _ text: String,
        entryID: String,
        kind: DesktopChatTranscriptEntry.Kind,
        title: String,
        detail: String
    ) {
        if let index = chatTranscript.firstIndex(where: { $0.id == entryID }) {
            let existing = chatTranscript[index]
            guard existing.body.isEmpty else {
                return
            }
            chatTranscript[index] = DesktopChatTranscriptEntry(
                id: existing.id,
                kind: existing.kind,
                title: existing.title,
                body: text,
                detail: existing.detail
            )
            return
        }

        appendChatEntry(id: entryID, kind: kind, title: title, body: text, detail: detail)
    }

    private func trimRecentEvents() {
        if recentEvents.count > 40 {
            recentEvents.removeSubrange(40...)
        }
    }

    private func startSubscription(lastSeenSeq: UInt64, isReconnect: Bool) async {
        let startedAt = Date()
        let stream = await client.subscribe(lastSeenSeq: lastSeenSeq)

        if isReconnect {
            recentEvents.insert(
                DesktopLogEntry(
                    kind: "reconnect",
                    message: "Reconnected event stream",
                    detail: lastSeenSeq == 0 ? "live" : "seq \(lastSeenSeq)",
                    level: "info"
                ),
                at: 0
            )
            trimRecentEvents()
            await metrics.record(
                name: "desktop.reconnect_success_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
        }

        await transitionConnectionState(
            to: "Connected",
            detail: lastSeenSeq == 0 ? "Live event stream" : "Resumed from seq \(lastSeenSeq)"
        )

        subscriptionTask = Task { [weak self] in
            guard let self else {
                return
            }
            for await event in stream {
                await self.consume(event: event)
            }
            if Task.isCancelled {
                return
            }
            await self.handleUnexpectedSubscriptionTermination()
        }
    }

    private func handleUnexpectedSubscriptionTermination() async {
        subscriptionTask = nil
        recentEvents.insert(
            DesktopLogEntry(
                kind: "reconnect",
                message: "Event stream ended; reconnecting",
                detail: lastSeenSeq == 0 ? "live" : "seq \(lastSeenSeq)",
                level: "warning"
            ),
            at: 0
        )
        trimRecentEvents()
        await transitionConnectionState(
            to: "Reconnecting",
            detail: lastSeenSeq == 0 ? "Retrying event stream" : "Retrying from seq \(lastSeenSeq)"
        )

        let startedAt = Date()
        do {
            let snapshot = try await client.serverSnapshot()
            apply(snapshot: snapshot)
            await metrics.record(
                name: "desktop.reconnect_attempt_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            await startSubscription(lastSeenSeq: lastSeenSeq, isReconnect: true)
        } catch {
            await metrics.record(name: "desktop.reconnect_failure_count", valueMs: 1)
            await transitionConnectionState(to: "Degraded", detail: "Reconnect failed")
            recordLocalError("Reconnect failed: \(error)")
            notifyStateChanged()
        }
    }

    private func transitionConnectionState(to state: String, detail: String) async {
        guard connectionStateText != state || connectionDetailText != detail else {
            return
        }
        connectionStateText = state
        connectionDetailText = detail
        connectionStateTransitions += 1
        await metrics.record(
            name: "desktop.connection_state_transitions",
            valueMs: connectionStateTransitions
        )
        notifyStateChanged()
    }

    private func notifyStateChanged() {
        onStateChanged?()
    }

    private static func serverStateText(_ state: Melix_Controlplane_V1_ServerState) -> String {
        switch state {
        case .serverBooting:
            return "Booting"
        case .serverReady:
            return "Ready"
        case .serverDegraded:
            return "Degraded"
        case .serverDraining:
            return "Draining"
        case .serverStopped:
            return "Stopped"
        case .serverFailed:
            return "Failed"
        default:
            return "Unknown"
        }
    }

    private static func modelStateText(_ state: Melix_Controlplane_V1_ModelState) -> String {
        switch state {
        case .modelDiscovered:
            return "Discovered"
        case .modelWarm:
            return "Warm"
        case .modelPinned:
            return "Pinned"
        case .modelUnloaded:
            return "Unloaded"
        case .modelLoading:
            return "Loading"
        case .modelEvicting:
            return "Evicting"
        case .modelFailed:
            return "Failed"
        default:
            return "Unknown"
        }
    }

    private static func actionTitle(for state: Melix_Controlplane_V1_ModelState) -> String {
        switch state {
        case .modelWarm, .modelPinned:
            return "Unload"
        default:
            return "Load"
        }
    }

    private static func eventLevel(for event: Melix_Controlplane_V1_ControlPlaneEvent) -> String {
        switch event.payload {
        case .log(let logEvent):
            return logEvent.level
        case .resourcePressure:
            return "warning"
        default:
            return "info"
        }
    }

    private static func eventMessage(for event: Melix_Controlplane_V1_ControlPlaneEvent) -> String {
        switch event.payload {
        case .serverState(let serverStateChanged):
            return "Server is now \(serverStateText(serverStateChanged.state))"
        case .modelState(let modelStateChanged):
            return "\(modelStateChanged.modelID) -> \(modelStateText(modelStateChanged.state))"
        case .requestProgress(let progress):
            return "\(progress.requestID) \(String(describing: progress.phase).lowercased())"
        case .sessionState(let sessionStateChanged):
            return "Session \(sessionStateChanged.state.sessionID) updated"
        case .cacheStats:
            return "Cache summary updated"
        case .log(let logEvent):
            return logEvent.message
        case .resourcePressure(let resourcePressure):
            return "Resource pressure in \(resourcePressure.scope)"
        case .imageJob(let imageJobChanged):
            return "\(imageJobChanged.job.jobID) \(imageJobChanged.job.progress.stage)"
        case .heartbeat:
            return "Heartbeat"
        default:
            return event.eventType
        }
    }

    private static func imageStatusText(for job: Melix_Controlplane_V1_ImageJobSummary) -> String {
        switch job.state {
        case .imageJobQueued:
            return "Queued • \(job.operation)"
        case .imageJobRunning:
            return "Running • \(job.operation)"
        case .imageJobCompleted:
            return "Completed • \(job.operation)"
        case .imageJobCanceled:
            return "Canceled • \(job.operation)"
        case .imageJobFailed:
            return "Failed • \(job.operation)"
        default:
            return job.operation.isEmpty ? "Idle" : job.operation
        }
    }

    private static func makeAdapterPackageState(from payload: [String: Any]) -> RuntimeAdapterPackageState {
        RuntimeAdapterPackageState(
            id: stringValue("adapter_id", from: payload),
            adapterName: stringValue("adapter_name", from: payload),
            sourceModel: stringValue("source_model", from: payload),
            datasetURI: stringValue("dataset_uri", from: payload),
            statusText: humanizeStatus(stringValue("status", from: payload)),
            outputPath: stringValue("output_path", from: payload),
            targetRepo: stringValue("target_repo", from: payload),
            publishedRepo: stringValue("published_repo", from: payload),
            trainingDurationText: formatDuration(milliseconds: doubleValue("training_duration_ms", from: payload)),
            publishDurationText: formatDuration(milliseconds: doubleValue("adapter_publish_ms", from: payload))
        )
    }

    private static func makeTrainingHistoryEntryState(from payload: [String: Any]) -> RuntimeTrainingHistoryEntryState {
        RuntimeTrainingHistoryEntryState(
            id: stringValue("job_id", from: payload),
            jobID: stringValue("job_id", from: payload),
            modelID: stringValue("source_model", from: payload),
            adapterName: stringValue("adapter_name", from: payload["manifest"] as? [String: Any] ?? [:]),
            datasetURI: stringValue("dataset_uri", from: payload["manifest"] as? [String: Any] ?? [:]),
            statusText: humanizeStatus(stringValue("status", from: payload)),
            stageText: "\(stringValue("stage", from: payload)) • \(String(format: "%.0f%%", doubleValue("pct", from: payload) * 100))",
            outputPath: stringValue("output_path", from: payload),
            targetRepo: stringValue("target_repo", from: payload["manifest"] as? [String: Any] ?? [:])
        )
    }

    private static func stringValue(_ key: String, from payload: [String: Any]) -> String {
        payload[key] as? String ?? ""
    }

    private static func doubleValue(_ key: String, from payload: [String: Any]) -> Double {
        if let value = payload[key] as? Double {
            return value
        }
        if let number = payload[key] as? NSNumber {
            return number.doubleValue
        }
        return 0
    }

    private static func humanizeStatus(_ status: String) -> String {
        guard status.isEmpty == false else {
            return "Unknown"
        }
        let separatorNormalized = status.replacingOccurrences(of: "_", with: " ")
        guard let first = separatorNormalized.first else {
            return "Unknown"
        }
        return String(first).uppercased() + separatorNormalized.dropFirst()
    }

    private static func formatDuration(milliseconds: Double) -> String {
        guard milliseconds > 0 else {
            return "n/a"
        }
        if milliseconds >= 1_000 {
            return String(format: "%.2fs", milliseconds / 1_000)
        }
        return String(format: "%.0fms", milliseconds)
    }

    private static func isImageModelKind(_ kind: String) -> Bool {
        kind == "image" || kind == "image_generation"
    }
}

func makeRuntimeModelRow(_ model: Melix_Controlplane_V1_ModelSummary) -> RuntimeModelRow {
    RuntimeModelRow(
        modelID: model.modelID,
        kind: model.kind,
        state: model.state,
        stateText: runtimeModelStateText(
            model.state,
            transitionReason: model.residency.transitionReason
        ),
        actionTitle: runtimeActionTitle(for: model.state),
        maxContext: model.maxContext,
        alias: model.settings.alias,
        memoryPolicyText: runtimeMemoryPolicyText(model.settings.memoryPolicy),
        accelerationModeText: runtimeAccelerationModeText(model.settings.defaultAccelerationMode),
        accelerationProfileID: model.settings.accelerationProfileID,
        residencyText: runtimeResidencyText(for: model),
        memoryText: runtimeMemoryText(for: model),
        memoryAlertText: runtimeMemoryAlertText(for: model)
    )
}

private func runtimeModelStateText(
    _ state: Melix_Controlplane_V1_ModelState,
    transitionReason: String = ""
) -> String {
    let base = switch state {
    case .modelDiscovered:
        "Discovered"
    case .modelWarm:
        "Warm"
    case .modelPinned:
        "Pinned"
    case .modelUnloaded:
        "Unloaded"
    case .modelLoading:
        "Loading"
    case .modelEvicting:
        "Evicting"
    case .modelFailed:
        "Failed"
    default:
        "Unknown"
    }

    guard !transitionReason.isEmpty else {
        return base
    }
    switch state {
    case .modelEvicting, .modelUnloaded, .modelFailed:
        return "\(base) • \(runtimeTransitionReasonText(transitionReason))"
    default:
        return base
    }
}

private func runtimeTransitionReasonText(_ reason: String) -> String {
    let separatorNormalized = reason.replacingOccurrences(of: "_", with: " ")
    guard let first = separatorNormalized.first else {
        return "Unknown"
    }
    return String(first).uppercased() + separatorNormalized.dropFirst()
}

private func runtimeActionTitle(for state: Melix_Controlplane_V1_ModelState) -> String {
    switch state {
    case .modelWarm, .modelPinned:
        return "Unload"
    default:
        return "Load"
    }
}

private func runtimeMemoryPolicyText(_ policy: Melix_Controlplane_V1_MemoryResidencyPolicy) -> String {
    switch policy {
    case .memoryResidencyPinned:
        return "Pinned"
    case .memoryResidencyTtl:
        return "TTL"
    case .memoryResidencyEvictable:
        return "Evictable"
    default:
        return "Unspecified"
    }
}

private func runtimeAccelerationModeText(_ mode: Melix_Controlplane_V1_AccelerationMode) -> String {
    switch mode {
    case .speculativeDecode:
        return "Speculative Decode"
    case .acceleratedPrefill:
        return "Accelerated Prefill"
    case .activeKvQuantized:
        return "Active KV Quantized"
    case .baseline:
        return "Baseline"
    default:
        return "Unspecified"
    }
}

private func runtimeResidencyText(for model: Melix_Controlplane_V1_ModelSummary) -> String {
    let residencyState = resolvedResidencyState(for: model)
    let policy = resolvedResidencyPolicy(for: model)
    let pinRequested = resolvedPinRequested(for: model)
    let pinned = resolvedPinned(for: model)
    let ttlSeconds = resolvedTTLSeconds(for: model)

    var parts = [
        runtimeResidencyStateText(residencyState),
        runtimeMemoryPolicyText(policy),
    ]
    if pinRequested && !pinned {
        parts.append("Pin requested")
    }
    if ttlSeconds > 0 {
        parts.append("TTL \(ttlSeconds)s")
    }
    return parts.joined(separator: " • ")
}

private func runtimeMemoryText(for model: Melix_Controlplane_V1_ModelSummary) -> String {
    var parts: [String] = []
    if model.estimatedBytes > 0 {
        parts.append("\(runtimeFormatBytes(model.estimatedBytes)) estimated")
    }
    if model.inflightRequests > 0 {
        parts.append("\(model.inflightRequests) inflight")
    }
    if parts.isEmpty {
        return "No live footprint reported"
    }
    return parts.joined(separator: " • ")
}

private func runtimeMemoryAlertText(for model: Melix_Controlplane_V1_ModelSummary) -> String {
    let reason = model.residency.transitionReason.trimmingCharacters(in: .whitespacesAndNewlines)
    guard runtimeIsMemoryProtectionReason(reason) else {
        return ""
    }
    return "Memory protection • \(runtimeTransitionReasonText(reason))"
}

private func resolvedResidencyState(
    for model: Melix_Controlplane_V1_ModelSummary
) -> Melix_Controlplane_V1_ResidencyState {
    if model.residency.state != .unspecified {
        return model.residency.state
    }
    switch model.state {
    case .modelDiscovered:
        return .discovered
    case .modelLoading:
        return .loading
    case .modelWarm:
        return .warm
    case .modelPinned:
        return .pinned
    case .modelEvicting:
        return .evicting
    case .modelUnloaded:
        return .unloaded
    case .modelFailed:
        return .failed
    default:
        return .unspecified
    }
}

private func resolvedResidencyPolicy(
    for model: Melix_Controlplane_V1_ModelSummary
) -> Melix_Controlplane_V1_MemoryResidencyPolicy {
    if model.residency.policy != .unspecified {
        return model.residency.policy
    }
    if model.settings.pinOnLoad {
        return .memoryResidencyPinned
    }
    if model.settings.memoryPolicy != .unspecified {
        return model.settings.memoryPolicy
    }
    if model.settings.ttlSeconds > 0 {
        return .memoryResidencyTtl
    }
    return .memoryResidencyEvictable
}

private func resolvedPinRequested(for model: Melix_Controlplane_V1_ModelSummary) -> Bool {
    model.residency.pinRequested || model.settings.pinOnLoad
}

private func resolvedPinned(for model: Melix_Controlplane_V1_ModelSummary) -> Bool {
    model.residency.pinned || model.pinned || model.state == .modelPinned
}

private func resolvedTTLSeconds(for model: Melix_Controlplane_V1_ModelSummary) -> UInt32 {
    max(model.residency.ttlSeconds, model.settings.ttlSeconds)
}

private func runtimeResidencyStateText(_ state: Melix_Controlplane_V1_ResidencyState) -> String {
    switch state {
    case .discovered:
        return "Discovered"
    case .loading:
        return "Loading"
    case .warm:
        return "Warm"
    case .pinned:
        return "Pinned"
    case .evicting:
        return "Evicting"
    case .unloaded:
        return "Unloaded"
    case .failed:
        return "Failed"
    default:
        return "Unknown"
    }
}

private func runtimeIsMemoryProtectionReason(_ reason: String) -> Bool {
    let normalized = reason.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    guard !normalized.isEmpty else {
        return false
    }
    return normalized.contains("memory_budget")
        || normalized.contains("prefill_memory_guard")
        || normalized.contains("quadratic_prefill_guard")
}

private func runtimeFormatBytes(_ bytes: UInt64) -> String {
    let formatter = ByteCountFormatter()
    formatter.countStyle = .binary
    formatter.allowedUnits = [.useKB, .useMB, .useGB]
    formatter.includesUnit = true
    formatter.includesCount = true
    return formatter.string(fromByteCount: Int64(bytes))
}
