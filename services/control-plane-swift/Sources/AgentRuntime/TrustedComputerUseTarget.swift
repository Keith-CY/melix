import CryptoKit
import Foundation
import MelixControlPlaneProtocol

public enum TrustedComputerUseTargetError: Error, Sendable, Equatable {
    case invalidIdentity
    case targetIDMismatch
}

/// A live broker-discovered window identity frozen into one Agent run. Model
/// output may refer to this identity, but it cannot create or widen it.
public struct TrustedComputerUseTarget: Sendable, Hashable {
    public let targetID: String
    public let bundleID: String
    public let processID: Int32
    public let processLaunchIdentity: String
    public let windowID: UInt32
    public let windowTitle: String
    public let applicationName: String

    public init(
        targetID: String = "",
        bundleID: String,
        processID: Int32,
        processLaunchIdentity: String,
        windowID: UInt32,
        windowTitle: String,
        applicationName: String
    ) throws {
        let bundleID = bundleID.trimmingCharacters(in: .whitespacesAndNewlines)
        let launchIdentity = processLaunchIdentity.trimmingCharacters(
            in: .whitespacesAndNewlines
        )
        let title = windowTitle.trimmingCharacters(in: .whitespacesAndNewlines)
        let appName = applicationName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !bundleID.isEmpty,
              bundleID.utf8.count <= 256,
              processID > 0,
              !launchIdentity.isEmpty,
              launchIdentity.utf8.count <= 256,
              windowID > 0,
              title.utf8.count <= 512,
              appName.utf8.count <= 256
        else {
            throw TrustedComputerUseTargetError.invalidIdentity
        }
        let expectedID = Self.makeTargetID(
            bundleID: bundleID,
            processID: processID,
            processLaunchIdentity: launchIdentity,
            windowID: windowID,
            windowTitle: title,
            applicationName: appName
        )
        let suppliedID = targetID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard suppliedID.isEmpty || suppliedID == expectedID else {
            throw TrustedComputerUseTargetError.targetIDMismatch
        }
        self.targetID = expectedID
        self.bundleID = bundleID
        self.processID = processID
        self.processLaunchIdentity = launchIdentity
        self.windowID = windowID
        self.windowTitle = title
        self.applicationName = appName
    }

    public init(_ target: Melix_Controlplane_V1_AgentComputerUseTarget) throws {
        try self.init(
            targetID: target.targetID,
            bundleID: target.bundleID,
            processID: target.processID,
            processLaunchIdentity: target.processLaunchIdentity,
            windowID: target.windowID,
            windowTitle: target.windowTitle,
            applicationName: target.applicationName
        )
    }

    public var protocolValue: Melix_Controlplane_V1_AgentComputerUseTarget {
        var target = Melix_Controlplane_V1_AgentComputerUseTarget()
        target.targetID = targetID
        target.bundleID = bundleID
        target.processID = processID
        target.processLaunchIdentity = processLaunchIdentity
        target.windowID = windowID
        target.windowTitle = windowTitle
        target.applicationName = applicationName
        return target
    }

    public var jsonObject: [String: Any] {
        [
            "bundle_id": bundleID,
            "process_id": processID,
            "process_launch_identity": processLaunchIdentity,
            "window_id": windowID,
            "window_title": windowTitle,
            "application_name": applicationName,
        ]
    }

    public func matchesAuthoritativeIdentity(_ value: [String: Any]) -> Bool {
        Self.string(value["bundle_id"]) == bundleID
            && Self.int64(value["process_id"]) == Int64(processID)
            && Self.string(value["process_launch_identity"])
                == processLaunchIdentity
            && Self.int64(value["window_id"]) == Int64(windowID)
    }

    private static func makeTargetID(
        bundleID: String,
        processID: Int32,
        processLaunchIdentity: String,
        windowID: UInt32,
        windowTitle: String,
        applicationName: String
    ) -> String {
        let fields = [
            bundleID,
            String(processID),
            processLaunchIdentity,
            String(windowID),
            windowTitle,
            applicationName,
        ]
        let canonical = fields.map { "\($0.utf8.count):\($0)" }.joined(separator: "|")
        let digest = SHA256.hash(data: Data(canonical.utf8))
            .map { String(format: "%02x", $0) }
            .joined()
        return "window-\(digest.prefix(24))"
    }

    private static func string(_ value: Any?) -> String? {
        value as? String
    }

    private static func int64(_ value: Any?) -> Int64? {
        if let number = value as? NSNumber {
            return number.int64Value
        }
        return value as? Int64
    }
}
