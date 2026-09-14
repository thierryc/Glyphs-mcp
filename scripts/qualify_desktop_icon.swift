import AppKit

// Offscreen AppKit rendering of the bundled template, at standard and Retina
// densities. This does not change system appearance or open an application UI.
let arguments = CommandLine.arguments
guard arguments.count == 3, let image = NSImage(contentsOfFile: arguments[1]) else { fatalError("Supply the menu PDF and output folder") }
image.isTemplate = true; image.size = NSSize(width: 18, height: 18)
let output = URL(fileURLWithPath: arguments[2], isDirectory: true)
try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
let canvas = NSImage(size: NSSize(width: 480, height: 150))
canvas.lockFocus()
NSColor.white.setFill(); NSRect(x: 0, y: 0, width: 480, height: 150).fill()
for (index, appearance) in [NSAppearance.Name.aqua, .darkAqua].enumerated() {
    for scale in 1...2 {
        let view = NSImageView(frame: NSRect(x: 0, y: 0, width: 18, height: 18))
        view.image = image; view.imageScaling = .scaleProportionallyUpOrDown
        view.appearance = NSAppearance(named: appearance)
        view.contentTintColor = index == 0 ? .black : .white
        let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 18*scale, pixelsHigh: 18*scale,
            bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
        rep.size = NSSize(width: 18, height: 18)
        view.cacheDisplay(in: view.bounds, to: rep)
        let name = "\(index == 0 ? "light" : "dark")-\(scale)x"
        try rep.representation(using: .png, properties: [:])!.write(to: output.appendingPathComponent(name+".png"))
        let x = CGFloat(index*240+(scale-1)*120)
        (index == 0 ? NSColor.white : NSColor(calibratedWhite: 0.12, alpha: 1)).setFill()
        NSRect(x: x, y: 0, width: 120, height: 150).fill()
        let rendered = NSImage(size: NSSize(width: 18, height: 18)); rendered.addRepresentation(rep)
        NSGraphicsContext.current?.imageInterpolation = .none
        rendered.draw(in: NSRect(x: x+24, y: 46, width: 72, height: 72))
        (name as NSString).draw(at: NSPoint(x: x+20, y: 15), withAttributes: [.foregroundColor: index == 0 ? NSColor.black : NSColor.white, .font: NSFont.systemFont(ofSize: 12)])
    }
}
canvas.unlockFocus()
try NSBitmapImageRep(data: canvas.tiffRepresentation!)!.representation(using: .png, properties: [:])!.write(to: output.appendingPathComponent("icon-rendering.png"))
print("Rendered unchanged vector template at 1x and 2x in light and dark appearances")
