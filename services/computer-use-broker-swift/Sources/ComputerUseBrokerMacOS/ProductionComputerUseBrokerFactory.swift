import AppKit
import ComputerUseBrokerCore
import Foundation

public enum ProductionComputerUseBrokerFactory {
    @MainActor
    public static func prepareProcessForDesktopServices() {
        // ScreenCaptureKit's SCContentFilter reaches SkyLight and aborts a
        // command-line process that has not initialized AppKit. Keep the broker
        // headless while establishing the native GUI-session connection before
        // any target inventory request can arrive.
        let application = NSApplication.shared
        _ = application.setActivationPolicy(.prohibited)
    }

    public static func make(artifactRoot: URL) -> DefaultComputerUseBroker {
        DefaultComputerUseBroker(
            frameCapture: ScreenCaptureKitFrameCaptureAdapter(),
            accessibility: AXUIElementAccessibilityAdapter(),
            evidenceSink: FileComputerUseEvidenceSink(),
            clock: SystemComputerUseClock(),
            identityGenerator: UUIDComputerUseIdentityGenerator(),
            artifactRoot: artifactRoot
        )
    }
}
