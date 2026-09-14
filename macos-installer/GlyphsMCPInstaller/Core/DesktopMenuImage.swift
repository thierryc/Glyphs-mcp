import AppKit
import QuartzCore

public enum DesktopMenuImage {
    /// Center the idle logo; leave room beside it only while indicating work.
    /// The fixed canvas keeps neighboring items still. AppKit tints only the logo.
    public static func make(logo: NSImage, active: Bool) -> NSImage {
        let image = NSImage(size: NSSize(width: 24, height: 18), flipped: false) { _ in
            logo.draw(in: NSRect(x: active ? 0 : 3, y: 0, width: 18, height: 18))
            return true
        }
        image.isTemplate = true
        return image
    }
}

/// Separate from the template image so menu-bar tinting preserves the dot color.
public final class DesktopActivityDot: NSView {
    static let fillColor = NSColor(srgbRed: 0, green: 187 / 255.0, blue: 208 / 255.0, alpha: 1)

    public override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
    }
    public required init?(coder: NSCoder) {
        super.init(coder: coder)
        wantsLayer = true
    }

    public override var allowsVibrancy: Bool { false }
    public override func hitTest(_ point: NSPoint) -> NSView? { nil }
    public override var wantsUpdateLayer: Bool { true }

    public override func updateLayer() {
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        defer { CATransaction.commit() }
        layer?.backgroundColor = Self.fillColor.cgColor
        layer?.cornerRadius = min(bounds.width, bounds.height) / 2
    }
}
