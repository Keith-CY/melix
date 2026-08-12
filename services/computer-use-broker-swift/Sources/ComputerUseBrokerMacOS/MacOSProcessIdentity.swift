import AppKit
import Foundation

public enum MacOSProcessIdentity {
    public static func launchIdentity(processIdentifier: Int32) -> String? {
        let application = NSRunningApplication(
            processIdentifier: processIdentifier
        )
        return launchIdentity(
            processIdentifier: processIdentifier,
            bundleIdentifier: application?.bundleIdentifier,
            launchDate: application?.launchDate
        )
    }

    static func launchIdentity(
        processIdentifier: Int32,
        bundleIdentifier: String?,
        launchDate: Date?
    ) -> String? {
        guard let bundleIdentifier, let launchDate else {
            return nil
        }
        return launchIdentity(
            processIdentifier: processIdentifier,
            bundleIdentifier: bundleIdentifier,
            launchDate: launchDate
        )
    }

    static func launchIdentity(
        processIdentifier: Int32,
        bundleIdentifier: String,
        launchDate: Date
    ) -> String {
        let launchMilliseconds = Int64(
            (launchDate.timeIntervalSince1970 * 1_000).rounded()
        )
        return "pid:\(processIdentifier):launch_ms:\(launchMilliseconds):bundle:\(bundleIdentifier)"
    }
}
