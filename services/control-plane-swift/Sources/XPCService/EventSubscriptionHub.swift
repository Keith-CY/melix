import Foundation
import MelixControlPlaneProtocol

public struct ControlPlaneSubscription: Sendable {
    public let subscriptionID: String
    public let stream: AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent>

    public init(
        subscriptionID: String,
        stream: AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent>
    ) {
        self.subscriptionID = subscriptionID
        self.stream = stream
    }
}

public actor EventSubscriptionHub {
    private struct Subscriber {
        var nextSequence: UInt64
        let continuation: AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent>.Continuation
    }

    private var subscribers: [String: Subscriber] = [:]
    private var nextSubscriptionNumber: UInt64 = 1

    public init() {}

    public func subscribe(lastSeenSeq: UInt64 = 0) -> ControlPlaneSubscription {
        let subscriptionID = "sub-\(nextSubscriptionNumber)"
        nextSubscriptionNumber += 1

        let stream = AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent> { continuation in
            subscribers[subscriptionID] = Subscriber(
                nextSequence: lastSeenSeq,
                continuation: continuation
            )
            continuation.onTermination = { _ in
                Task {
                    await self.unsubscribe(subscriptionID)
                }
            }
        }

        return ControlPlaneSubscription(subscriptionID: subscriptionID, stream: stream)
    }

    public func unsubscribe(_ subscriptionID: String) {
        guard let subscriber = subscribers.removeValue(forKey: subscriptionID) else {
            return
        }
        subscriber.continuation.finish()
    }

    public func publish(_ event: Melix_Controlplane_V1_ControlPlaneEvent) {
        for subscriptionID in subscribers.keys.sorted() {
            guard var subscriber = subscribers[subscriptionID] else {
                continue
            }
            subscriber.nextSequence += 1
            subscribers[subscriptionID] = subscriber

            var deliveredEvent = event
            deliveredEvent.subscriptionID = subscriptionID
            deliveredEvent.seq = subscriber.nextSequence
            subscriber.continuation.yield(deliveredEvent)
        }
    }
}
