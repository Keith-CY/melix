import Foundation
import MelixControlPlaneProtocol

public enum RequestRouteSelectionReason: String, Sendable, Equatable {
    case preferredInstance = "preferred_instance"
    case residentModel = "resident_model"
    case leastActiveRequests = "least_active_requests"
    case stableTieBreak = "stable_tie_break"
    case onlyReadyCandidate = "only_ready_candidate"
}

public enum RequestRouteRejectionReason: String, Sendable, Equatable {
    case missingRequestRoutes = "missing_request_routes"
    case noRouteForTask = "no_route_for_task"
    case noRouteForModalities = "no_route_for_modalities"
    case nativeVideoRequired = "native_video_required"
    case workerFamilyUnavailable = "worker_family_unavailable"
    case multiResidencyDenied = "multi_residency_denied"
    case routeConflict = "route_conflict"
    case workerFamilyMismatch = "worker_family_mismatch"
}

public struct WorkerInstanceSnapshot: Sendable, Equatable {
    public struct ResidentModel: Sendable, Equatable {
        public let modelID: String
        public let modelHandle: String

        public init(modelID: String, modelHandle: String) {
            self.modelID = modelID
            self.modelHandle = modelHandle
        }
    }

    public let instanceID: String
    public let workerFamily: Melix_Controlplane_V1_WorkerFamily
    public let ready: Bool
    public let activeRequestCount: UInt64
    public let residentModels: [ResidentModel]

    public init(
        instanceID: String,
        workerFamily: Melix_Controlplane_V1_WorkerFamily,
        ready: Bool,
        activeRequestCount: UInt64 = 0,
        residentModels: [ResidentModel] = []
    ) {
        self.instanceID = instanceID
        self.workerFamily = workerFamily
        self.ready = ready
        self.activeRequestCount = activeRequestCount
        self.residentModels = residentModels
    }
}

public struct RouteSelectionReceipt: Sendable, Equatable {
    public let requestID: String
    public let modelID: String
    public let task: Melix_Controlplane_V1_InferenceTask
    public let requestModalities: [Melix_Controlplane_V1_RouteModality]
    public let selectedRoute: Melix_Controlplane_V1_RequestRouteDeclaration
    public let selectedWorkerInstanceID: String
    public let selectionReason: RequestRouteSelectionReason
    public let preferredWorkerInstanceID: String
    public let preferredInstanceUsed: Bool
    public let modelResidencyBefore: [String: [WorkerInstanceSnapshot.ResidentModel]]
    public let activeRequestsSnapshot: [String: UInt64]
    public let selectionSnapshotID: UInt64
    public let selectedAtUnixMs: Int64
}

public struct RequestRouteSelection: Sendable, Equatable {
    public let route: Melix_Controlplane_V1_RequestRouteDeclaration
    public let workerInstance: WorkerInstanceSnapshot
    public let receipt: RouteSelectionReceipt
}

public enum RequestRouteResolution: Sendable, Equatable {
    case selected(RequestRouteSelection)
    case rejected(Melix_Controlplane_V1_ErrorStatus)
}

public struct RequestRouteResolverInput: Sendable, Equatable {
    public let requestID: String
    public let modelID: String
    public let task: Melix_Controlplane_V1_InferenceTask
    public let requestModalities: Set<Melix_Controlplane_V1_RouteModality>
    public let routes: [Melix_Controlplane_V1_RequestRouteDeclaration]
    public let workerInstances: [WorkerInstanceSnapshot]
    public let preferredWorkerInstanceID: String?
    public let selectionSnapshotID: UInt64
    public let selectedAtUnixMs: Int64

    public init(
        requestID: String,
        modelID: String,
        task: Melix_Controlplane_V1_InferenceTask,
        requestModalities: Set<Melix_Controlplane_V1_RouteModality>,
        routes: [Melix_Controlplane_V1_RequestRouteDeclaration],
        workerInstances: [WorkerInstanceSnapshot],
        preferredWorkerInstanceID: String? = nil,
        selectionSnapshotID: UInt64 = 1,
        selectedAtUnixMs: Int64 = 0
    ) {
        self.requestID = requestID
        self.modelID = modelID
        self.task = task
        self.requestModalities = requestModalities
        self.routes = routes
        self.workerInstances = workerInstances
        self.preferredWorkerInstanceID = preferredWorkerInstanceID
        self.selectionSnapshotID = selectionSnapshotID
        self.selectedAtUnixMs = selectedAtUnixMs
    }
}

public enum RequestRouteResolver {
    public static func resolve(
        _ input: RequestRouteResolverInput
    ) -> RequestRouteResolution {
        guard !input.routes.isEmpty else {
            return .rejected(routeError(input: input, reason: .missingRequestRoutes, candidateRoutes: []))
        }

        let taskRoutes = input.routes.filter { $0.task == input.task }
        guard !taskRoutes.isEmpty else {
            return .rejected(routeError(input: input, reason: .noRouteForTask, candidateRoutes: []))
        }

        let modalityRoutes = taskRoutes.filter { route in
            requestModalities(input.requestModalities, match: route)
        }
        guard !modalityRoutes.isEmpty else {
            return .rejected(routeError(input: input, reason: .noRouteForModalities, candidateRoutes: taskRoutes))
        }

        if input.requestModalities.contains(.video),
           modalityRoutes.allSatisfy({ !$0.supportsNativeVideo }) {
            return .rejected(routeError(input: input, reason: .nativeVideoRequired, candidateRoutes: modalityRoutes))
        }

        let nativeCompatibleRoutes = input.requestModalities.contains(.video)
            ? modalityRoutes.filter(\.supportsNativeVideo)
            : modalityRoutes
        let distinctRouteKeys = Set(nativeCompatibleRoutes.map(routeConflictKey))
        guard distinctRouteKeys.count == nativeCompatibleRoutes.count else {
            return .rejected(routeError(input: input, reason: .routeConflict, candidateRoutes: nativeCompatibleRoutes))
        }
        guard nativeCompatibleRoutes.count == 1, let selectedRoute = nativeCompatibleRoutes.first else {
            return .rejected(routeError(input: input, reason: .routeConflict, candidateRoutes: nativeCompatibleRoutes))
        }

        let readyCandidates = input.workerInstances
            .filter { $0.workerFamily == selectedRoute.workerFamily && $0.ready }
            .sorted { lhs, rhs in lhs.instanceID < rhs.instanceID }
        guard !readyCandidates.isEmpty else {
            return .rejected(routeError(input: input, reason: .workerFamilyUnavailable, candidateRoutes: [selectedRoute]))
        }

        let (selectedInstance, reason, preferredUsed) = selectInstance(
            candidates: readyCandidates,
            modelID: input.modelID,
            preferredWorkerInstanceID: normalizedPreference(input.preferredWorkerInstanceID)
        )

        let receipt = RouteSelectionReceipt(
            requestID: input.requestID,
            modelID: input.modelID,
            task: input.task,
            requestModalities: canonicalModalities(input.requestModalities),
            selectedRoute: selectedRoute,
            selectedWorkerInstanceID: selectedInstance.instanceID,
            selectionReason: reason,
            preferredWorkerInstanceID: normalizedPreference(input.preferredWorkerInstanceID) ?? "",
            preferredInstanceUsed: preferredUsed,
            modelResidencyBefore: modelResidencySnapshot(from: readyCandidates),
            activeRequestsSnapshot: activeRequestSnapshot(from: readyCandidates),
            selectionSnapshotID: input.selectionSnapshotID,
            selectedAtUnixMs: input.selectedAtUnixMs
        )
        return .selected(
            RequestRouteSelection(
                route: selectedRoute,
                workerInstance: selectedInstance,
                receipt: receipt
            )
        )
    }

    private static func requestModalities(
        _ requestModalities: Set<Melix_Controlplane_V1_RouteModality>,
        match route: Melix_Controlplane_V1_RequestRouteDeclaration
    ) -> Bool {
        let supported = Set(route.supportedModalities.filter { $0 != .unspecified })
        guard requestModalities.isSubset(of: supported) else {
            return false
        }
        let required = Set(route.requiresAnyModality.filter { $0 != .unspecified })
        return required.isEmpty || !requestModalities.isDisjoint(with: required)
    }

    private static func selectInstance(
        candidates: [WorkerInstanceSnapshot],
        modelID: String,
        preferredWorkerInstanceID: String?
    ) -> (WorkerInstanceSnapshot, RequestRouteSelectionReason, Bool) {
        if let preferredWorkerInstanceID,
           let preferred = candidates.first(where: { $0.instanceID == preferredWorkerInstanceID }) {
            return (preferred, .preferredInstance, true)
        }
        if candidates.count == 1, let only = candidates.first {
            return (only, .onlyReadyCandidate, false)
        }
        let resident = candidates.filter { candidate in
            candidate.residentModels.contains(where: { $0.modelID == modelID })
        }
        if let selectedResident = resident.sorted(by: instanceLoadThenID).first {
            return (selectedResident, .residentModel, false)
        }
        let sorted = candidates.sorted(by: instanceLoadThenID)
        guard let selected = sorted.first else {
            preconditionFailure("selectInstance requires at least one candidate")
        }
        let sameLoadCount = sorted.filter { $0.activeRequestCount == selected.activeRequestCount }.count
        return (selected, sameLoadCount > 1 ? .stableTieBreak : .leastActiveRequests, false)
    }

    private static func instanceLoadThenID(
        lhs: WorkerInstanceSnapshot,
        rhs: WorkerInstanceSnapshot
    ) -> Bool {
        if lhs.activeRequestCount != rhs.activeRequestCount {
            return lhs.activeRequestCount < rhs.activeRequestCount
        }
        return lhs.instanceID < rhs.instanceID
    }

    private static func routeError(
        input: RequestRouteResolverInput,
        reason: RequestRouteRejectionReason,
        candidateRoutes: [Melix_Controlplane_V1_RequestRouteDeclaration]
    ) -> Melix_Controlplane_V1_ErrorStatus {
        var error = Melix_Controlplane_V1_ErrorStatus()
        error.code = "route_not_supported"
        error.retriable = false
        error.message = "Request route admission failed for model \(input.modelID) with reason \(reason.rawValue)."
        error.details = [
            "model_id": input.modelID,
            "task": canonicalName(input.task),
            "requested_modalities": canonicalModalities(input.requestModalities).map(canonicalName).joined(separator: ","),
            "required_modality_suite": "",
            "available_routes": availableRoutesJSON(candidateRoutes),
            "available_modality_suites": availableModalitySuites(candidateRoutes),
            "worker_family_candidates": workerFamilyCandidates(candidateRoutes),
            "reason": reason.rawValue,
        ]
        return error
    }

    private static func routeConflictKey(_ route: Melix_Controlplane_V1_RequestRouteDeclaration) -> String {
        [
            canonicalName(route.task),
            canonicalModalities(Set(route.supportedModalities)).map(canonicalName).joined(separator: ","),
            canonicalModalities(Set(route.requiresAnyModality)).map(canonicalName).joined(separator: ","),
        ].joined(separator: "|")
    }

    private static func availableRoutesJSON(_ routes: [Melix_Controlplane_V1_RequestRouteDeclaration]) -> String {
        let payload = routes.map { route in
            [
                "task": canonicalName(route.task),
                "supported_modalities": canonicalModalities(Set(route.supportedModalities)).map(canonicalName),
                "requires_any_modality": canonicalModalities(Set(route.requiresAnyModality)).map(canonicalName),
                "worker_family": canonicalName(route.workerFamily),
                "model_family_target": route.modelFamilyTarget,
            ] as [String: Any]
        }
        guard JSONSerialization.isValidJSONObject(payload),
              let data = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]) else {
            return "[]"
        }
        return String(decoding: data, as: UTF8.self)
    }

    private static func availableModalitySuites(
        _ routes: [Melix_Controlplane_V1_RequestRouteDeclaration]
    ) -> String {
        routes
            .map { canonicalModalities(Set($0.supportedModalities)).map(canonicalName).joined(separator: "+") }
            .sorted()
            .joined(separator: ",")
    }

    private static func workerFamilyCandidates(
        _ routes: [Melix_Controlplane_V1_RequestRouteDeclaration]
    ) -> String {
        Set(routes.map(\.workerFamily).filter { $0 != .unspecified })
            .sorted(by: workerFamilyOrder)
            .map(canonicalName)
            .joined(separator: ",")
    }

    private static func modelResidencySnapshot(
        from candidates: [WorkerInstanceSnapshot]
    ) -> [String: [WorkerInstanceSnapshot.ResidentModel]] {
        Dictionary(
            uniqueKeysWithValues: candidates.map { candidate in
                (
                    candidate.instanceID,
                    candidate.residentModels.sorted {
                        if $0.modelID != $1.modelID {
                            return $0.modelID < $1.modelID
                        }
                        return $0.modelHandle < $1.modelHandle
                    }
                )
            }
        )
    }

    private static func activeRequestSnapshot(
        from candidates: [WorkerInstanceSnapshot]
    ) -> [String: UInt64] {
        Dictionary(uniqueKeysWithValues: candidates.map { ($0.instanceID, $0.activeRequestCount) })
    }

    private static func normalizedPreference(_ rawValue: String?) -> String? {
        let trimmed = rawValue?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return trimmed.isEmpty ? nil : trimmed
    }

    public static func canonicalModalities(
        _ modalities: Set<Melix_Controlplane_V1_RouteModality>
    ) -> [Melix_Controlplane_V1_RouteModality] {
        modalities.filter { $0 != .unspecified }.sorted(by: modalityOrder)
    }

    public static func canonicalName(_ task: Melix_Controlplane_V1_InferenceTask) -> String {
        switch task {
        case .generateText:
            return "generate_text"
        case .generateMultimodal:
            return "generate_multimodal"
        case .embedText:
            return "embed_text"
        case .rerankText:
            return "rerank_text"
        case .transcribeAudio:
            return "transcribe_audio"
        case .speakText:
            return "speak_text"
        case .imageGenerate:
            return "image_generate"
        case .imageEdit:
            return "image_edit"
        case .unspecified, .UNRECOGNIZED:
            return "unspecified"
        }
    }

    public static func canonicalName(_ modality: Melix_Controlplane_V1_RouteModality) -> String {
        switch modality {
        case .text:
            return "text"
        case .image:
            return "image"
        case .audio:
            return "audio"
        case .video:
            return "video"
        case .unspecified, .UNRECOGNIZED:
            return "unspecified"
        }
    }

    public static func canonicalName(_ workerFamily: Melix_Controlplane_V1_WorkerFamily) -> String {
        switch workerFamily {
        case .text:
            return "text"
        case .vision:
            return "vision"
        case .audio:
            return "audio"
        case .image:
            return "image"
        case .retrieval:
            return "retrieval"
        case .omni:
            return "omni"
        case .unspecified, .UNRECOGNIZED:
            return "unspecified"
        }
    }

    private static func canonicalName(_ policy: Melix_Controlplane_V1_RouteResidencyPolicy) -> String {
        switch policy {
        case .singleResidency:
            return "single_residency"
        case .allowMultiResidency:
            return "allow_multi_residency"
        case .unspecified, .UNRECOGNIZED:
            return "unspecified"
        }
    }

    private static func modalityOrder(
        lhs: Melix_Controlplane_V1_RouteModality,
        rhs: Melix_Controlplane_V1_RouteModality
    ) -> Bool {
        modalityRank(lhs) < modalityRank(rhs)
    }

    private static func modalityRank(_ modality: Melix_Controlplane_V1_RouteModality) -> Int {
        switch modality {
        case .text:
            return 0
        case .image:
            return 1
        case .audio:
            return 2
        case .video:
            return 3
        case .unspecified, .UNRECOGNIZED:
            return 99
        }
    }

    private static func workerFamilyOrder(
        lhs: Melix_Controlplane_V1_WorkerFamily,
        rhs: Melix_Controlplane_V1_WorkerFamily
    ) -> Bool {
        workerFamilyRank(lhs) < workerFamilyRank(rhs)
    }

    private static func workerFamilyRank(_ family: Melix_Controlplane_V1_WorkerFamily) -> Int {
        switch family {
        case .text:
            return 0
        case .vision:
            return 1
        case .audio:
            return 2
        case .image:
            return 3
        case .retrieval:
            return 4
        case .omni:
            return 5
        case .unspecified, .UNRECOGNIZED:
            return 99
        }
    }
}
