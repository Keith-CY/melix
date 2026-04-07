import AppKit
import Foundation

enum MelixBranding {
    static let productName = "Melix"
    static let workspaceLogoResourceName = "melix-logo-workspace"
    static let trayTemplateResourceName = "melix-status-template"
    static let appIconFileName = "MelixAppIcon.icns"

    static func workspaceLogo() -> NSImage {
        loadImage(named: workspaceLogoResourceName)
    }

    static func trayTemplateIcon() -> NSImage {
        let image = loadImage(named: trayTemplateResourceName)
        image.isTemplate = true
        return image
    }

    private static func loadImage(named resourceName: String) -> NSImage {
        guard
            let resourceURL = Bundle.module.url(forResource: resourceName, withExtension: "png"),
            let image = NSImage(contentsOf: resourceURL)
        else {
            fatalError("Missing Melix branding resource: \(resourceName).png")
        }

        return image
    }
}
