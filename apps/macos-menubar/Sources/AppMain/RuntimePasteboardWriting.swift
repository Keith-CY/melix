import AppKit

protocol RuntimePasteboardWriting: AnyObject {
    @discardableResult
    func clearContents() -> Int
    func setString(_ string: String, forType dataType: NSPasteboard.PasteboardType) -> Bool
}

extension NSPasteboard: RuntimePasteboardWriting {}
