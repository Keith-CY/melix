import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol

@Suite("Request Route Resolver")
struct RequestRouteResolverTests {
    @Test("text route declaration selects the only ready text worker")
    func textRouteDeclarationSelectsOnlyReadyTextWorker() throws {
        let route = makeRoute(
            task: .generateText,
            supportedModalities: [.text],
            workerFamily: .text
        )

        let result = RequestRouteResolver.resolve(
            RequestRouteResolverInput(
                requestID: "req-text",
                modelID: "model-text",
                task: .generateText,
                requestModalities: [.text],
                routes: [route],
                workerInstances: [
                    WorkerInstanceSnapshot(instanceID: "text-a", workerFamily: .text, ready: true),
                ],
                selectionSnapshotID: 7,
                selectedAtUnixMs: 1234
            )
        )

        let selection = try result.successValue()
        #expect(selection.route.workerFamily == .text)
        #expect(selection.workerInstance.instanceID == "text-a")
        #expect(selection.receipt.selectionReason == .onlyReadyCandidate)
        #expect(selection.receipt.requestModalities == [.text])
        #expect(selection.receipt.selectionSnapshotID == 7)
        #expect(selection.receipt.selectedAtUnixMs == 1234)
    }

    @Test("legacy route metadata without request routes is rejected")
    func legacyRouteMetadataWithoutRequestRoutesIsRejected() throws {
        let result = RequestRouteResolver.resolve(
            RequestRouteResolverInput(
                requestID: "req-legacy",
                modelID: "legacy-vlm",
                task: .generateMultimodal,
                requestModalities: [.text, .image],
                routes: [],
                workerInstances: [
                    WorkerInstanceSnapshot(instanceID: "vision-a", workerFamily: .vision, ready: true),
                ]
            )
        )

        let error = try result.failureValue()
        #expect(error.code == "route_not_supported")
        #expect(error.retriable == false)
        #expect(error.details["reason"] == "missing_request_routes")
        #expect(error.details["model_id"] == "legacy-vlm")
        #expect(error.details["task"] == "generate_multimodal")
        #expect(error.details["requested_modalities"] == "text,image")
    }

    @Test("requires-any modality supports media-only image requests")
    func requiresAnyModalitySupportsMediaOnlyImageRequests() throws {
        let route = makeRoute(
            task: .generateMultimodal,
            supportedModalities: [.text, .image, .video],
            requiresAnyModality: [.image, .video],
            workerFamily: .vision
        )

        let result = RequestRouteResolver.resolve(
            RequestRouteResolverInput(
                requestID: "req-image-only",
                modelID: "vision-model",
                task: .generateMultimodal,
                requestModalities: [.image],
                routes: [route],
                workerInstances: [
                    WorkerInstanceSnapshot(instanceID: "vision-a", workerFamily: .vision, ready: true),
                ]
            )
        )

        let selection = try result.successValue()
        #expect(selection.workerInstance.workerFamily == .vision)
        #expect(selection.receipt.requestModalities == [.image])
        #expect(selection.receipt.selectedRoute.requiresAnyModality == [.image, .video])
    }

    @Test("video routes require native video support")
    func videoRoutesRequireNativeVideoSupport() throws {
        let route = makeRoute(
            task: .generateMultimodal,
            supportedModalities: [.text, .video],
            requiresAnyModality: [.video],
            supportsNativeVideo: false,
            workerFamily: .vision
        )

        let result = RequestRouteResolver.resolve(
            RequestRouteResolverInput(
                requestID: "req-video",
                modelID: "vision-model",
                task: .generateMultimodal,
                requestModalities: [.video],
                routes: [route],
                workerInstances: [
                    WorkerInstanceSnapshot(instanceID: "vision-a", workerFamily: .vision, ready: true),
                ]
            )
        )

        let error = try result.failureValue()
        #expect(error.details["reason"] == "native_video_required")
        #expect(error.details["worker_family_candidates"] == "vision")
    }

    @Test("worker family must have a ready concrete instance")
    func workerFamilyMustHaveReadyConcreteInstance() throws {
        let route = makeRoute(
            task: .generateMultimodal,
            supportedModalities: [.text, .image],
            requiresAnyModality: [.image],
            workerFamily: .vision
        )

        let result = RequestRouteResolver.resolve(
            RequestRouteResolverInput(
                requestID: "req-no-ready-vision",
                modelID: "vision-model",
                task: .generateMultimodal,
                requestModalities: [.text, .image],
                routes: [route],
                workerInstances: [
                    WorkerInstanceSnapshot(instanceID: "vision-a", workerFamily: .vision, ready: false),
                    WorkerInstanceSnapshot(instanceID: "text-a", workerFamily: .text, ready: true),
                ]
            )
        )

        let error = try result.failureValue()
        #expect(error.details["reason"] == "worker_family_unavailable")
        #expect(error.details["worker_family_candidates"] == "vision")
    }

    @Test("instance selection is deterministic and honors preferred resident load then stable id")
    func instanceSelectionIsDeterministic() throws {
        let route = makeRoute(
            task: .generateText,
            supportedModalities: [.text],
            workerFamily: .text
        )
        let instances = [
            WorkerInstanceSnapshot(
                instanceID: "text-c",
                workerFamily: .text,
                ready: true,
                activeRequestCount: 0,
                residentModels: [.init(modelID: "other", modelHandle: "other::c")]
            ),
            WorkerInstanceSnapshot(
                instanceID: "text-b",
                workerFamily: .text,
                ready: true,
                activeRequestCount: 9,
                residentModels: [.init(modelID: "model-text", modelHandle: "model-text::b")]
            ),
            WorkerInstanceSnapshot(
                instanceID: "text-a",
                workerFamily: .text,
                ready: true,
                activeRequestCount: 0
            ),
        ]

        let residentResult = RequestRouteResolver.resolve(
            RequestRouteResolverInput(
                requestID: "req-resident",
                modelID: "model-text",
                task: .generateText,
                requestModalities: [.text],
                routes: [route],
                workerInstances: instances
            )
        )
        let residentSelection = try residentResult.successValue()
        #expect(residentSelection.workerInstance.instanceID == "text-b")
        #expect(residentSelection.receipt.selectionReason == .residentModel)

        let preferredResult = RequestRouteResolver.resolve(
            RequestRouteResolverInput(
                requestID: "req-preferred",
                modelID: "model-text",
                task: .generateText,
                requestModalities: [.text],
                routes: [route],
                workerInstances: instances,
                preferredWorkerInstanceID: "text-a"
            )
        )
        let preferredSelection = try preferredResult.successValue()
        #expect(preferredSelection.workerInstance.instanceID == "text-a")
        #expect(preferredSelection.receipt.selectionReason == .preferredInstance)
        #expect(preferredSelection.receipt.preferredInstanceUsed)

        let stableResult = RequestRouteResolver.resolve(
            RequestRouteResolverInput(
                requestID: "req-stable",
                modelID: "cold-model",
                task: .generateText,
                requestModalities: [.text],
                routes: [route],
                workerInstances: instances
            )
        )
        let stableSelection = try stableResult.successValue()
        #expect(stableSelection.workerInstance.instanceID == "text-a")
        #expect(stableSelection.receipt.selectionReason == .stableTieBreak)
    }
}

private func makeRoute(
    task: Melix_Controlplane_V1_InferenceTask,
    supportedModalities: [Melix_Controlplane_V1_RouteModality],
    requiresAnyModality: [Melix_Controlplane_V1_RouteModality] = [],
    supportsNativeVideo: Bool = false,
    workerFamily: Melix_Controlplane_V1_WorkerFamily,
    modelFamilyTarget: String = "fixture.target",
    residencyPolicy: Melix_Controlplane_V1_RouteResidencyPolicy = .singleResidency,
    isTextCompanion: Bool = false
) -> Melix_Controlplane_V1_RequestRouteDeclaration {
    var route = Melix_Controlplane_V1_RequestRouteDeclaration()
    route.task = task
    route.supportedModalities = supportedModalities
    route.requiresAnyModality = requiresAnyModality
    route.supportsNativeVideo = supportsNativeVideo
    route.workerFamily = workerFamily
    route.modelFamilyTarget = modelFamilyTarget
    route.residencyPolicy = residencyPolicy
    route.isTextCompanion = isTextCompanion
    return route
}

private extension RequestRouteResolution {
    func successValue() throws -> RequestRouteSelection {
        switch self {
        case .selected(let value):
            return value
        case .rejected(let error):
            Issue.record("Expected route selection, got \(error)")
            throw TestFailure()
        }
    }

    func failureValue() throws -> Melix_Controlplane_V1_ErrorStatus {
        switch self {
        case .selected(let value):
            Issue.record("Expected route rejection, got \(value)")
            throw TestFailure()
        case .rejected(let error):
            return error
        }
    }
}

private struct TestFailure: Error {}
