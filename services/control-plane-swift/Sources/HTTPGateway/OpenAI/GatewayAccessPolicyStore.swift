import MelixControlPlaneProtocol

public actor GatewayAccessPolicyStore {
    private var policy: GatewayAccessPolicy
    private var serverSessionID: String?

    public init(_ policy: GatewayAccessPolicy = .localTrust) {
        self.policy = policy
        self.serverSessionID = nil
    }

    public func currentPolicy() -> GatewayAccessPolicy {
        policy
    }

    public func currentServerSessionID() -> String? {
        serverSessionID
    }

    @discardableResult
    public func replace(with policy: GatewayAccessPolicy, serverSessionID: String?) -> GatewayAccessPolicy {
        self.policy = policy
        self.serverSessionID = serverSessionID
        return policy
    }

    public func summary() -> Melix_Controlplane_V1_GatewayAccessSummary {
        policy.summary
    }
}
