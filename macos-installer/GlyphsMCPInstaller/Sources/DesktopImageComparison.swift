import AppKit
import SwiftUI
import GlyphsMCPInstallerCore

/// Shared by the glyph and raster toolbars so native controls stay identical.
enum GlyphOverlayMode: String, CaseIterable, Identifiable {
    case before = "Before", both = "Both", after = "After"
    var id: String { rawValue }
}

struct DesktopDiffOverlayPicker: View {
    @Binding var selection: GlyphOverlayMode
    var bothAvailable = true
    var body: some View {
        Picker("Overlay", selection: Binding(get: { selection }, set: { value in
            if value != .both || bothAvailable { selection = value }
        })) {
            ForEach(GlyphOverlayMode.allCases.filter { bothAvailable || $0 != .both }) { option in
                Text(LocalizedStringKey(option.rawValue)).tag(option)
            }
        }.pickerStyle(.segmented).labelsHidden().frame(width: 170)
    }
}

/// Raster-only comparison; all bytes come from the bounded, read-only Git reader.
struct DesktopImageComparison: View {
    let comparison: GitImageComparison
    private let previousImage: NSImage?
    private let currentImage: NSImage?
    @State private var mode: GlyphOverlayMode
    @State private var fraction = 0.5
    @State private var zoom: Double?
    @State private var viewport = CGSize.zero

    init(comparison: GitImageComparison) {
        self.comparison = comparison
        previousImage = comparison.previous.image.flatMap { NSImage(data: $0.previewData) }
        currentImage = comparison.current.image.flatMap { NSImage(data: $0.previewData) }
        _mode = State(initialValue: comparison.canCompare ? .both : comparison.current.image != nil ? .after : .before)
    }

    private func fitScale(in size: CGSize) -> Double {
        guard size.width > 32, size.height > 32 else { return 1 }
        return min(1, min(Double(size.width - 32) / Double(comparison.canvasWidth),
                          Double(size.height - 32) / Double(comparison.canvasHeight)))
    }
    private var displayScale: Double { zoom ?? fitScale(in: viewport) }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Spacer(minLength: 0)
                DesktopDiffOverlayPicker(selection: $mode, bothAvailable: comparison.canCompare)
                zoomControls
            }.padding(10)
            Divider()
            HStack(spacing: 8) {
                metadata("Before", side: comparison.previous)
                Spacer(minLength: 8)
                metadata("After", side: comparison.current)
            }.font(.caption).padding(.horizontal, 12).padding(.vertical, 7)
            Divider()
            GeometryReader { geometry in
                Group {
                    if (mode == .before && comparison.previous.image == nil) || (mode == .after && comparison.current.image == nil) {
                        ContentUnavailableView("No image in this version", systemImage: "photo", description: Text(LocalizedStringKey(mode == .before ? comparison.previous.message : comparison.current.message)))
                            .frame(width: geometry.size.width, height: geometry.size.height)
                    } else if comparison.previous.image != nil || comparison.current.image != nil {
                        ScrollView([.horizontal, .vertical]) {
                            canvas(in: geometry.size)
                                .padding(16)
                                .frame(minWidth: geometry.size.width, minHeight: geometry.size.height)
                        }.defaultScrollAnchor(.center)
                    } else {
                        ContentUnavailableView("Image preview unavailable", systemImage: "photo", description: Text("Select another file or refresh the comparison."))
                            .frame(width: geometry.size.width, height: geometry.size.height)
                    }
                }
                .onAppear { viewport = geometry.size }
                .onChange(of: geometry.size) { _, size in viewport = size }
            }.frame(minHeight: 100, maxHeight: .infinity)
            if mode == .both, comparison.canCompare {
                HStack(spacing: 10) {
                    Text("Before").font(.caption).foregroundStyle(.secondary)
                    Slider(value: $fraction, in: 0...1)
                        .labelsHidden().accessibilityLabel("Image comparison divider")
                        .accessibilityValue(Text("\(Int((fraction * 100).rounded())) percent before"))
                    Text("After").font(.caption).foregroundStyle(.secondary)
                }.padding(.horizontal, 12).padding(.vertical, 8)
            }
            VStack(alignment: .leading, spacing: 4) {
                if comparison.dimensionsDiffer {
                    Text("Different dimensions. Images are aligned at the top left at the same scale.")
                }
                if [comparison.previous.image, comparison.current.image].compactMap({ $0 }).contains(where: { $0.frameCount > 1 }) {
                    Text("Animated images show the first frame.")
                }
                Text("Transparency uses a checkerboard. Previews are limited to 2048 pixels on the longest side.")
            }
            .font(.caption).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 12).padding(.bottom, 12)
        }.background(Color(nsColor: .controlBackgroundColor))
    }

    private var zoomControls: some View {
        HStack(spacing: 8) {
            Button { zoom = GlyphViewportMath.stepped(displayScale, direction: -1) } label: { Image(systemName: "minus") }
                .buttonStyle(.borderless).accessibilityLabel("Zoom out").help("Zoom Out (⌘−)")
                .keyboardShortcut("-", modifiers: .command)
            Text("\(Int((displayScale * 100).rounded()))%")
                .font(.caption.monospacedDigit()).frame(minWidth: 42).fixedSize()
                .accessibilityLabel("Zoom \(Int((displayScale * 100).rounded())) percent")
            Button { zoom = GlyphViewportMath.stepped(displayScale, direction: 1) } label: { Image(systemName: "plus") }
                .buttonStyle(.borderless).accessibilityLabel("Zoom in").help("Zoom In (⌘+)")
                .keyboardShortcut("+", modifiers: .command)
            Divider().frame(height: 18)
            Button { zoom = nil } label: { Image(systemName: "scope") }
                .buttonStyle(.borderless).accessibilityLabel("Fit image").help("Fit Image (⌘0)")
                .keyboardShortcut("0", modifiers: .command)
        }.disabled(comparison.previous.image == nil && comparison.current.image == nil)
    }

    private func metadata(_ label: LocalizedStringKey, side: GitImageSide) -> some View {
        HStack(alignment: .top, spacing: 5) {
            Text(label).fontWeight(.medium)
            Text(LocalizedStringKey(side.message)).foregroundStyle(.secondary)
                .textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
        }.accessibilityElement(children: .combine)
    }

    private func canvas(in available: CGSize) -> some View {
        let scale = CGFloat(zoom ?? fitScale(in: available))
        let size = CGSize(width: CGFloat(comparison.canvasWidth) * scale, height: CGFloat(comparison.canvasHeight) * scale)
        return ZStack(alignment: .topLeading) {
            switch mode {
            case .before: plane(previousImage, raster: comparison.previous.image, size: size, scale: scale)
            case .after: plane(currentImage, raster: comparison.current.image, size: size, scale: scale)
            case .both:
                plane(currentImage, raster: comparison.current.image, size: size, scale: scale)
                // Mask the opaque background too: Before's transparent pixels
                // must never expose After's pixels underneath the comparison.
                plane(previousImage, raster: comparison.previous.image, size: size, scale: scale)
                    .mask(alignment: .leading) { Rectangle().frame(width: size.width * fraction) }
                divider(size: size)
            }
        }
        .frame(width: size.width, height: size.height).contentShape(Rectangle())
        .gesture(DragGesture(minimumDistance: 0).onChanged { value in
            if mode == .both { fraction = min(1, max(0, value.location.x / max(1, size.width))) }
        })
        .clipped()
        .overlay { Rectangle().strokeBorder(Color(nsColor: .separatorColor).opacity(0.5)) }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(mode == .both ? Text("Before and after images") : Text(LocalizedStringKey(mode.rawValue)))
    }

    private func plane(_ image: NSImage?, raster: GitRasterImage?, size: CGSize, scale: CGFloat) -> some View {
        ZStack(alignment: .topLeading) {
            ImageCheckerboard()
            if let image, let raster {
                Image(nsImage: image).resizable().interpolation(.high)
                    .frame(width: CGFloat(raster.width) * scale, height: CGFloat(raster.height) * scale)
            }
        }.frame(width: size.width, height: size.height).clipped()
    }

    private func divider(size: CGSize) -> some View {
        ZStack {
            Rectangle().fill(Color.accentColor).frame(width: 2)
            Image(systemName: "arrow.left.and.right")
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(Color.primary).frame(width: 30, height: 26)
                .background(Color(nsColor: .controlBackgroundColor), in: Capsule())
                .overlay { Capsule().strokeBorder(Color(nsColor: .separatorColor)) }
        }.frame(width: 32, height: size.height)
            .position(x: size.width * fraction, y: size.height / 2).accessibilityHidden(true)
    }
}

private struct ImageCheckerboard: View {
    // Tile one small opaque raster; never loop over the entire zoomed canvas.
    private static let tile: Image = {
        let context = CGContext(data: nil, width: 24, height: 24, bitsPerComponent: 8,
            bytesPerRow: 96, space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)!
        context.setFillColor(CGColor(gray: 0.94, alpha: 1))
        context.fill(CGRect(x: 0, y: 0, width: 24, height: 24))
        context.setFillColor(CGColor(gray: 0.84, alpha: 1))
        context.fill(CGRect(x: 0, y: 0, width: 12, height: 12))
        context.fill(CGRect(x: 12, y: 12, width: 12, height: 12))
        return Image(decorative: context.makeImage()!, scale: 1).interpolation(.none)
    }()
    var body: some View {
        // Native image tiling keeps the cell size in points. ImagePaint's
        // normalized texture coordinates can stretch when the wipe mask moves.
        Self.tile.resizable(resizingMode: .tile).accessibilityHidden(true)
    }
}
