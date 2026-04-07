import AppKit
import Foundation

enum MelixBranding {
    static let productName = "Melix"
    static let workspaceLogoResourceName = "melix-logo-workspace"
    static let trayTemplateResourceName = "melix-status-template"
    static let appIconFileName = "MelixAppIcon.icns"
    private static let cachedTrayTemplateIcon = makeTrimmedTrayTemplateIcon()

    static func workspaceLogo() -> NSImage {
        loadImage(named: workspaceLogoResourceName)
    }

    static func trayTemplateIcon() -> NSImage {
        (cachedTrayTemplateIcon.copy() as? NSImage) ?? cachedTrayTemplateIcon
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

    private static func makeTrimmedTrayTemplateIcon() -> NSImage {
        let image = loadImage(named: trayTemplateResourceName)
        let trimmed = trimTransparentPadding(from: image)
        trimmed.isTemplate = true
        return trimmed
    }

    private static func trimTransparentPadding(from image: NSImage) -> NSImage {
        guard let bounds = alphaBounds(for: image) else {
            return image
        }

        let trimmed = NSImage(size: bounds.size)
        trimmed.lockFocus()
        image.draw(at: .zero, from: bounds, operation: .copy, fraction: 1)
        trimmed.unlockFocus()
        return trimmed
    }

    private static func alphaBounds(for image: NSImage) -> NSRect? {
        guard
            let tiffRepresentation = image.tiffRepresentation,
            let bitmap = NSBitmapImageRep(data: tiffRepresentation)
        else {
            return nil
        }

        var minX = bitmap.pixelsWide
        var minY = bitmap.pixelsHigh
        var maxX = -1
        var maxY = -1

        for y in 0..<bitmap.pixelsHigh {
            for x in 0..<bitmap.pixelsWide {
                guard let color = bitmap.colorAt(x: x, y: y), color.alphaComponent > 0 else {
                    continue
                }
                minX = min(minX, x)
                minY = min(minY, y)
                maxX = max(maxX, x)
                maxY = max(maxY, y)
            }
        }

        guard maxX >= minX, maxY >= minY else {
            return nil
        }

        return NSRect(
            x: minX,
            y: minY,
            width: maxX - minX + 1,
            height: maxY - minY + 1
        )
    }
}
