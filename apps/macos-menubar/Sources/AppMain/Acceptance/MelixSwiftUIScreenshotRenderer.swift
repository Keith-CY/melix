import AppKit
import SwiftUI

public enum MelixSwiftUIScreenshotRenderError: Error, LocalizedError {
    case bitmapAllocationFailed
    case pngEncodingFailed

    public var errorDescription: String? {
        switch self {
        case .bitmapAllocationFailed:
            return "NSHostingView could not allocate a bitmap snapshot."
        case .pngEncodingFailed:
            return "Bitmap snapshot could not be encoded as PNG."
        }
    }
}

@MainActor
public struct MelixSwiftUIScreenshotRenderer {
    public init() {}

    public func render<Content: View>(
        _ rootView: Content,
        to outputURL: URL,
        size: CGSize
    ) throws {
        let hostingView = NSHostingView(
            rootView: rootView
                .frame(width: size.width, height: size.height)
        )
        hostingView.frame = CGRect(origin: .zero, size: size)
        hostingView.layoutSubtreeIfNeeded()

        guard let bitmap = hostingView.bitmapImageRepForCachingDisplay(in: hostingView.bounds) else {
            throw MelixSwiftUIScreenshotRenderError.bitmapAllocationFailed
        }
        bitmap.size = size
        hostingView.cacheDisplay(in: hostingView.bounds, to: bitmap)

        guard let data = bitmap.representation(using: .png, properties: [:]) else {
            throw MelixSwiftUIScreenshotRenderError.pngEncodingFailed
        }
        try FileManager.default.createDirectory(
            at: outputURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try data.write(to: outputURL)
    }
}
