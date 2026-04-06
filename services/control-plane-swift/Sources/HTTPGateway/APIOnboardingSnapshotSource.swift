import Foundation
import MelixControlPlaneProtocol

struct APIOnboardingSnapshotSource: Sendable {
    func summary() -> Melix_Controlplane_V1_APIOnboardingSummary {
        var summary = Melix_Controlplane_V1_APIOnboardingSummary()
        summary.surfaces = surfaceDefinitions.map(surfaceSummary)
        summary.endpoints = endpointDefinitions.map(endpointSummary)
        return summary
    }

    private let surfaceDefinitions: [SurfaceDefinition] = [
        SurfaceDefinition(
            id: "local_service",
            title: "Local Service",
            summary: "Readiness and operational inspection routes for same-host automation.",
            status: .shipped,
            endpointIDs: ["health", "cache_stats"]
        ),
        SurfaceDefinition(
            id: "openai_compatible",
            title: "OpenAI-Compatible",
            summary: "The primary local API surface for text, embeddings, rerank, audio, and image workflows.",
            status: .shipped,
            endpointIDs: [
                "models",
                "chat_completions",
                "completions",
                "responses",
                "embeddings",
                "rerank",
                "audio_transcriptions",
                "audio_speech",
                "images_generations",
                "images_edits",
            ]
        ),
        SurfaceDefinition(
            id: "anthropic_messages",
            title: "Anthropic Messages",
            summary: "Anthropic-style message execution over the shared local text runtime.",
            status: .shipped,
            endpointIDs: ["messages"]
        ),
        SurfaceDefinition(
            id: "ollama_compatibility",
            title: "Ollama Compatibility",
            summary: "Compatibility guidance for clients that can target Melix through a custom provider bridge.",
            status: .compatibilityOnly,
            endpointIDs: [],
            compatibilityNote: "Native /api/chat, /api/generate, /api/tags, /api/show, and /api/embeddings routes are not shipped yet. Use the OpenAI-compatible base URL only when your client can override its provider endpoint."
        ),
    ]

    private let endpointDefinitions: [EndpointDefinition] = [
        EndpointDefinition(
            id: "health",
            surfaceID: "local_service",
            method: "GET",
            path: "/health",
            summary: "Probe process readiness, listener state, and current model counts.",
            streaming: false
        ),
        EndpointDefinition(
            id: "cache_stats",
            surfaceID: "local_service",
            method: "GET",
            path: "/v1/cache/stats",
            summary: "Inspect cache usage, tier support, and persisted prefix state.",
            streaming: false
        ),
        EndpointDefinition(
            id: "models",
            surfaceID: "openai_compatible",
            method: "GET",
            path: "/v1/models",
            summary: "List local models and their current runtime state.",
            streaming: false
        ),
        EndpointDefinition(
            id: "chat_completions",
            surfaceID: "openai_compatible",
            method: "POST",
            path: "/v1/chat/completions",
            summary: "Run OpenAI-style chat completions over the shared text runtime.",
            streaming: true
        ),
        EndpointDefinition(
            id: "completions",
            surfaceID: "openai_compatible",
            method: "POST",
            path: "/v1/completions",
            summary: "Run prompt-style completions against the same text runtime.",
            streaming: true
        ),
        EndpointDefinition(
            id: "responses",
            surfaceID: "openai_compatible",
            method: "POST",
            path: "/v1/responses",
            summary: "Run Responses-style generation with reasoning and tool-call deltas when supported.",
            streaming: true
        ),
        EndpointDefinition(
            id: "embeddings",
            surfaceID: "openai_compatible",
            method: "POST",
            path: "/v1/embeddings",
            summary: "Generate embedding vectors through the Python compatibility worker.",
            streaming: false
        ),
        EndpointDefinition(
            id: "rerank",
            surfaceID: "openai_compatible",
            method: "POST",
            path: "/v1/rerank",
            summary: "Score and rerank candidate documents with a rerank-capable local model.",
            streaming: false
        ),
        EndpointDefinition(
            id: "audio_transcriptions",
            surfaceID: "openai_compatible",
            method: "POST",
            path: "/v1/audio/transcriptions",
            summary: "Transcribe uploaded audio with the local audio worker when runtime packs are installed.",
            streaming: false
        ),
        EndpointDefinition(
            id: "audio_speech",
            surfaceID: "openai_compatible",
            method: "POST",
            path: "/v1/audio/speech",
            summary: "Synthesize speech audio from local text-to-speech models.",
            streaming: false
        ),
        EndpointDefinition(
            id: "images_generations",
            surfaceID: "openai_compatible",
            method: "POST",
            path: "/v1/images/generations",
            summary: "Submit local image-generation jobs and receive artifact metadata.",
            streaming: false
        ),
        EndpointDefinition(
            id: "images_edits",
            surfaceID: "openai_compatible",
            method: "POST",
            path: "/v1/images/edits",
            summary: "Submit local image-edit jobs with source images and masks.",
            streaming: false
        ),
        EndpointDefinition(
            id: "messages",
            surfaceID: "anthropic_messages",
            method: "POST",
            path: "/v1/messages",
            summary: "Run Anthropic-style messages requests over the same shared text runtime.",
            streaming: true
        ),
    ]

    private func surfaceSummary(
        _ definition: SurfaceDefinition
    ) -> Melix_Controlplane_V1_APIOnboardingSurfaceSummary {
        var summary = Melix_Controlplane_V1_APIOnboardingSurfaceSummary()
        summary.surfaceID = definition.id
        summary.title = definition.title
        summary.summary = definition.summary
        summary.status = definition.status
        summary.endpointIds = definition.endpointIDs
        summary.compatibilityNote = definition.compatibilityNote
        return summary
    }

    private func endpointSummary(
        _ definition: EndpointDefinition
    ) -> Melix_Controlplane_V1_APIReferenceEndpointSummary {
        var summary = Melix_Controlplane_V1_APIReferenceEndpointSummary()
        summary.endpointID = definition.id
        summary.surfaceID = definition.surfaceID
        summary.method = definition.method
        summary.path = definition.path
        summary.summary = definition.summary
        summary.streaming = definition.streaming
        return summary
    }
}

private struct SurfaceDefinition: Sendable {
    let id: String
    let title: String
    let summary: String
    let status: Melix_Controlplane_V1_APIOnboardingSurfaceStatus
    let endpointIDs: [String]
    let compatibilityNote: String

    init(
        id: String,
        title: String,
        summary: String,
        status: Melix_Controlplane_V1_APIOnboardingSurfaceStatus,
        endpointIDs: [String],
        compatibilityNote: String = ""
    ) {
        self.id = id
        self.title = title
        self.summary = summary
        self.status = status
        self.endpointIDs = endpointIDs
        self.compatibilityNote = compatibilityNote
    }
}

private struct EndpointDefinition: Sendable {
    let id: String
    let surfaceID: String
    let method: String
    let path: String
    let summary: String
    let streaming: Bool
}
