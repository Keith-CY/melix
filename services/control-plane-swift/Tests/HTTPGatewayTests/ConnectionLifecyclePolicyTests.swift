import Foundation
import Testing

@testable import MelixControlPlaneCore

@Suite("Connection Lifecycle Policy")
struct ConnectionLifecyclePolicyTests {
    @Test("environment overrides can disable keepalive and tune lifecycle values")
    func environmentOverridesCanDisableKeepaliveAndTuneLifecycleValues() {
        let policy = ConnectionLifecyclePolicy.fromEnvironment(
            [
                "MELIX_CONNECTION_KEEPALIVE_INTERVAL_SECONDS": "0",
                "MELIX_CONNECTION_DISCONNECT_GRACE_SECONDS": "0.125",
                "MELIX_CONNECTION_RETRY_BACKOFF_SECONDS": "0.25",
                "MELIX_CONNECTION_RETRY_LIMIT": "3",
                "MELIX_CONNECTION_RESUME_BUFFER_LIMIT": "1024",
            ]
        )

        #expect(policy.keepaliveInterval == nil)
        #expect(policy.disconnectGracePeriod == 0.125)
        #expect(policy.retryBackoff == 0.25)
        #expect(policy.retryLimit == 3)
        #expect(policy.resumeBufferLimit == 1024)
    }

    @Test("invalid environment overrides fall back to repository defaults")
    func invalidEnvironmentOverridesFallBackToRepositoryDefaults() {
        let policy = ConnectionLifecyclePolicy.fromEnvironment(
            [
                "MELIX_CONNECTION_KEEPALIVE_INTERVAL_SECONDS": "invalid",
                "MELIX_CONNECTION_DISCONNECT_GRACE_SECONDS": "-1",
                "MELIX_CONNECTION_RETRY_BACKOFF_SECONDS": "0",
                "MELIX_CONNECTION_RETRY_LIMIT": "-2",
                "MELIX_CONNECTION_RESUME_BUFFER_LIMIT": "0",
            ]
        )

        #expect(policy.keepaliveInterval == 15)
        #expect(policy.disconnectGracePeriod == 5)
        #expect(policy.retryBackoff == 0.5)
        #expect(policy.retryLimit == 0)
        #expect(policy.resumeBufferLimit == 512)
    }
}
