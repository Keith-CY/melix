import Foundation
import MelixWorkerProtocol

struct TextDecodeSamplingKey: Hashable, Sendable {
    let temperature: Float
    let topP: Float
    let topK: UInt32
    let frequencyPenalty: Float
    let presencePenalty: Float
    let maxOutputTokens: UInt32
    let stop: [String]
    let seed: UInt32

    init(_ sampling: Melix_Worker_V1_SamplingConfig) {
        self.temperature = sampling.temperature
        self.topP = sampling.topP
        self.topK = sampling.topK
        self.frequencyPenalty = sampling.frequencyPenalty
        self.presencePenalty = sampling.presencePenalty
        self.maxOutputTokens = sampling.maxOutputTokens
        self.stop = sampling.stop
        self.seed = sampling.seed
    }
}

struct TextDecodeAccelerationKey: Hashable, Sendable {
    let mode: Melix_Worker_V1_AccelerationMode
    let profileID: String
    let draftModelID: String
    let prefillHint: String
    let activeKVQuantProfile: String
    let allowBaselineFallback: Bool
    let numDraftTokens: UInt32
    let ext: [String]

    init(_ acceleration: Melix_Worker_V1_AccelerationPolicy) {
        self.mode = acceleration.mode
        self.profileID = acceleration.profileID
        self.draftModelID = acceleration.draftModelID
        self.prefillHint = acceleration.prefillHint
        self.activeKVQuantProfile = acceleration.activeKvQuantProfile
        self.allowBaselineFallback = acceleration.allowBaselineFallback
        self.numDraftTokens = acceleration.numDraftTokens
        self.ext = acceleration.ext
            .map { "\($0.key)=\($0.value)" }
            .sorted()
    }
}

struct TextDecodeBatchEligibilityKey: Hashable, Sendable {
    let modelHandle: String
    let lane: String
    let sampling: TextDecodeSamplingKey
    let acceleration: TextDecodeAccelerationKey
    let maxOutputTokens: UInt32
    let decodeStepSize: UInt32
    let prefillToken: String
}

struct TextDecodeBatchCandidate: @unchecked Sendable {
    let requestID: String
    let key: TextDecodeBatchEligibilityKey
    let maxBatchSize: Int
    let session: WorkerDecodeSession
    let sampling: Melix_Worker_V1_SamplingConfig
    let maxOutputTokens: UInt32
    let decodeStepSize: UInt32
    let prefillToken: String
    let acceleration: Melix_Worker_V1_AccelerationPolicy
    let shouldAbort: @Sendable () -> Bool

    var workerItem: WorkerDecodeBatchItem {
        WorkerDecodeBatchItem(
            session: session,
            sampling: sampling,
            maxOutputTokens: maxOutputTokens,
            decodeStepSize: decodeStepSize,
            prefillToken: prefillToken,
            acceleration: acceleration,
            shouldAbort: shouldAbort
        )
    }
}

enum TextDecodeBatchAssignment: Sendable {
    case single
    case batched(stream: AsyncThrowingStream<TextGenerationEvent, Error>, batchSize: Int)
}

actor TextDecodeBatchCoordinator {
    private struct PendingItem: @unchecked Sendable {
        let candidate: TextDecodeBatchCandidate
        let continuation: CheckedContinuation<TextDecodeBatchAssignment, Never>
    }

    private struct PendingCohort: @unchecked Sendable {
        var capacity: Int
        var items: [PendingItem]
    }

    private let registry: WorkerRuntimeRegistry
    private let pendingWindowNanos: UInt64
    private var pendingByKey: [TextDecodeBatchEligibilityKey: PendingCohort] = [:]

    init(
        registry: WorkerRuntimeRegistry,
        pendingWindowNanos: UInt64 = 2_000_000
    ) {
        self.registry = registry
        self.pendingWindowNanos = pendingWindowNanos
    }

    func enqueue(_ candidate: TextDecodeBatchCandidate) async -> TextDecodeBatchAssignment {
        await withCheckedContinuation { continuation in
            let item = PendingItem(candidate: candidate, continuation: continuation)
            var cohort = pendingByKey[candidate.key] ?? PendingCohort(
                capacity: max(2, candidate.maxBatchSize),
                items: []
            )
            cohort.capacity = max(2, min(cohort.capacity, candidate.maxBatchSize))
            cohort.items.append(item)

            if cohort.items.count >= cohort.capacity {
                pendingByKey[candidate.key] = nil
                dispatch(cohort)
                return
            }

            let shouldScheduleFlush = cohort.items.count == 1
            pendingByKey[candidate.key] = cohort

            if shouldScheduleFlush {
                scheduleFlush(for: candidate.key)
            }
        }
    }

    private func scheduleFlush(for key: TextDecodeBatchEligibilityKey) {
        Task { [pendingWindowNanos] in
            if pendingWindowNanos > 0 {
                try? await Task.sleep(nanoseconds: pendingWindowNanos)
            }
            self.flush(key: key)
        }
    }

    private func flush(key: TextDecodeBatchEligibilityKey) {
        guard let cohort = pendingByKey.removeValue(forKey: key) else {
            return
        }
        dispatch(cohort)
    }

    private func dispatch(_ cohort: PendingCohort) {
        guard cohort.items.count > 1 else {
            cohort.items.first?.continuation.resume(returning: .single)
            return
        }

        let streams = cohort.items.map { _ in
            AsyncThrowingStream<TextGenerationEvent, Error>.makeStream()
        }
        for (index, item) in cohort.items.enumerated() {
            item.continuation.resume(returning: .batched(
                stream: streams[index].stream,
                batchSize: cohort.items.count
            ))
        }

        let items = cohort.items.map(\.candidate)
        let continuations = streams.map(\.continuation)
        let registry = self.registry
        Task {
            do {
                let runtimeStream = try await registry.decodeBatchEvents(
                    items: items.map(\.workerItem)
                )
                for try await event in runtimeStream {
                    switch event {
                    case .token(let requestIndex, let text):
                        guard continuations.indices.contains(requestIndex) else {
                            continue
                        }
                        continuations[requestIndex].yield(.token(text))
                    case .summary(let requestIndex, let summary):
                        guard continuations.indices.contains(requestIndex) else {
                            continue
                        }
                        continuations[requestIndex].yield(.summary(summary))
                    case .batchSummary:
                        continue
                    }
                }
                continuations.forEach { $0.finish() }
            } catch {
                continuations.forEach { $0.finish(throwing: error) }
            }
        }
    }
}
