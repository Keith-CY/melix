import AppKit
import Foundation

enum MelixBranding {
    static let productName = "Melix"
    static let workspaceLogoResourceName = "melix-logo-workspace"
    static let trayTemplateResourceName = "melix-status-template"
    static let appIconResourceName = "MelixAppIcon"
    static let appIconFileName = "MelixAppIcon.icns"
    @MainActor
    private static let cachedTrayTemplateIcon = makeTrimmedTrayTemplateIcon()

    @MainActor
    static func workspaceLogo() -> NSImage {
        loadImage(named: workspaceLogoResourceName)
    }

    @MainActor
    static func appIcon() -> NSImage {
        loadImage(named: appIconResourceName, fileExtension: "icns")
    }

    @MainActor
    static func trayTemplateIcon() -> NSImage {
        (cachedTrayTemplateIcon.copy() as? NSImage) ?? cachedTrayTemplateIcon
    }

    @MainActor
    private static func loadImage(named resourceName: String, fileExtension: String = "png") -> NSImage {
        guard
            let resourceURL = Bundle.module.url(forResource: resourceName, withExtension: fileExtension),
            let image = NSImage(contentsOf: resourceURL)
        else {
            fatalError("Missing Melix branding resource: \(resourceName).\(fileExtension)")
        }

        return image
    }

    @MainActor
    private static func makeTrimmedTrayTemplateIcon() -> NSImage {
        let image = loadImage(named: trayTemplateResourceName)
        let trimmed = trimTransparentPadding(from: image)
        trimmed.isTemplate = true
        return trimmed
    }

    @MainActor
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

    @MainActor
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

    private static func darkPixelBounds(for image: NSImage) -> NSRect? {
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
                guard
                    let color = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB),
                    color.alphaComponent > 0.5,
                    Self.relativeLuminance(color) < 0.35
                else {
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

    private static func backgroundSample(for image: NSImage) -> (alpha: CGFloat, luminance: CGFloat)? {
        guard
            let tiffRepresentation = image.tiffRepresentation,
            let bitmap = NSBitmapImageRep(data: tiffRepresentation)
        else {
            return nil
        }

        let x = min(max(Int(Double(bitmap.pixelsWide) * 0.12), 0), bitmap.pixelsWide - 1)
        let y = min(max(Int(Double(bitmap.pixelsHigh) * 0.12), 0), bitmap.pixelsHigh - 1)
        guard let color = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB) else {
            return nil
        }
        return (color.alphaComponent, Self.relativeLuminance(color))
    }

    private static func relativeLuminance(_ color: NSColor) -> CGFloat {
        (0.2126 * color.redComponent) + (0.7152 * color.greenComponent) + (0.0722 * color.blueComponent)
    }

#if DEBUG
    struct IconPixelMetrics: Equatable {
        let darkGlyphBounds: NSRect
        let backgroundAlpha: CGFloat
        let backgroundLuminance: CGFloat
    }

    @MainActor
    static func _testTrimTransparentPadding(from image: NSImage) -> NSImage {
        trimTransparentPadding(from: image)
    }

    @MainActor
    static func _testAlphaBounds(for image: NSImage) -> NSRect? {
        alphaBounds(for: image)
    }

    @MainActor
    static func _testIconPixelMetrics(for image: NSImage) -> IconPixelMetrics? {
        guard
            let darkGlyphBounds = darkPixelBounds(for: image),
            let background = backgroundSample(for: image)
        else {
            return nil
        }
        return IconPixelMetrics(
            darkGlyphBounds: darkGlyphBounds,
            backgroundAlpha: background.alpha,
            backgroundLuminance: background.luminance
        )
    }
#endif
}
