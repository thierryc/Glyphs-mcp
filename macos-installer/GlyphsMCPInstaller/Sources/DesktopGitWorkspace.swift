import Foundation
import SwiftUI
import WebKit
import GlyphsMCPInstallerCore
import PierreDiffsSwift

struct DesktopGitWorkspace: View {
    @ObservedObject var model: DesktopProjectsModel
    @State private var filter = ""
    @State private var diffStyle: DiffStyle = .unified
    @State private var overflow: OverflowMode = .scroll
    @State private var overlay: GlyphOverlayMode = .both
    @State private var selectedLayerID: String?
    @State private var guides = true
    @State private var zoom = 1.0
    @State private var viewportRequest = GlyphViewportRequest(id: 0, target: .fit)
    @State private var selectedDifferenceIndex: Int?
    @State private var viewportStore = GlyphViewportSessionStore()

    var body: some View {
        Group {
            if let git = model.git {
                if git.changes.isEmpty { cleanState(git) }
                else { browser(git) }
            } else if model.inspecting {
                ProgressView("Reading local Git information…").frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ContentUnavailableView("Git information unavailable", systemImage: "exclamationmark.triangle",
                                       description: Text(model.gitMessage))
            }
        }
        .background(Color(nsColor: .windowBackgroundColor), in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color(nsColor: .separatorColor).opacity(0.55)))
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .onChange(of: model.selectedChange?.path) { _, _ in
            selectedDifferenceIndex = nil
            viewportRequest = .init(id: viewportRequest.id + 1, target: .restore)
        }
    }

    private func cleanState(_ git: GitObservation) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "checkmark.circle.fill").font(.largeTitle).foregroundStyle(.green)
            Text("Working tree is clean").font(.headline)
            Text(git.branch).foregroundStyle(.secondary)
            Button("Refresh", action: model.inspect).disabled(model.inspecting)
        }.frame(maxWidth: .infinity, minHeight: 340, maxHeight: .infinity)
    }

    private func browser(_ git: GitObservation) -> some View {
        HSplitView {
            VStack(spacing: 0) {
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(git.branch).font(.headline).lineLimit(1).truncationMode(.middle)
                        Text("\(git.changes.count) changed file\(git.changes.count == 1 ? "" : "s")")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button(action: model.inspect) { Image(systemName: "arrow.clockwise") }
                        .buttonStyle(.borderless).help("Refresh Git information")
                        .accessibilityLabel("Refresh Git information").disabled(model.inspecting)
                }.padding(12)
                Divider()
                TextField("Filter files", text: $filter).textFieldStyle(.roundedBorder).padding(10)
                Divider()
                List {
                    OutlineGroup(tree(filtered(git.changes)), children: \.children) { node in row(node) }
                }
                .listStyle(.sidebar)
                .scrollContentBackground(.hidden)
                .environment(\.defaultMinListRowHeight, 28)
            }
            .frame(minWidth: 220, idealWidth: 260, maxWidth: 380, maxHeight: .infinity)

            detail
                .frame(minWidth: 500, maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(minHeight: 410, maxHeight: .infinity)
    }

    private var detail: some View {
        VStack(spacing: 0) {
            if let change = model.selectedChange {
                header(change)
                Divider()
                if model.loadingComparison && model.comparison == nil {
                    DiffLoadingView.comparison(includesGlyphGeometry: change.isGlyphPackageGlyph)
                } else if let comparison = model.comparison {
                    comparisonView(change, comparison: comparison)
                } else {
                    ContentUnavailableView("Diff unavailable", systemImage: "doc.text.magnifyingglass",
                                           description: Text(model.comparisonMessage))
                }
            } else {
                ContentUnavailableView("Select a changed file", systemImage: "doc.text.magnifyingglass")
            }
        }
    }

    private func header(_ change: GitObservation.Change) -> some View {
        VStack(spacing: 8) {
            HStack(spacing: 8) {
                Image(systemName: icon(change.path)).foregroundStyle(.secondary)
                VStack(alignment: .leading, spacing: 2) {
                    Text(change.path).font(.headline).lineLimit(1).truncationMode(.middle).help(change.path)
                    if let original = change.originalPath { Text("from \(original)").font(.caption).foregroundStyle(.secondary) }
                }
                Spacer()
                statusBadge(change)
            }
            if !model.glyphMessage.isEmpty {
                Label(model.glyphMessage, systemImage: "info.circle").font(.caption).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }.padding(.horizontal, 12).padding(.vertical, 10)
    }

    @ViewBuilder private func comparisonView(_ change: GitObservation.Change, comparison: GitFileComparison) -> some View {
        if change.isGlyphPackageGlyph {
            VStack(spacing: 0) {
                glyphToolbar
                    .padding(10)
                Divider()
                ZStack {
                    textDiff(comparison).opacity(effectiveGlyphMode == .text ? 1 : 0)
                        .allowsHitTesting(effectiveGlyphMode == .text).accessibilityHidden(effectiveGlyphMode != .text)
                    if let document = model.glyphDiff {
                        glyphVisual(document).opacity(effectiveGlyphMode == .visual ? 1 : 0)
                            .allowsHitTesting(effectiveGlyphMode == .visual).accessibilityHidden(effectiveGlyphMode != .visual)
                    } else if model.loadingGlyphDiff && model.glyphMode == .visual {
                        DiffLoadingView.glyphGeometry
                    }
                }
            }
        } else {
            VStack(spacing: 0) {
                HStack { Spacer(); textControls }.padding(10)
                Divider()
                textDiff(comparison)
            }
        }
    }

    private var effectiveGlyphMode: DesktopGlyphDiffMode {
        model.glyphMode == .visual && (model.glyphDiff != nil || model.loadingGlyphDiff) ? .visual : .text
    }

    private var glyphModeSelection: Binding<DesktopGlyphDiffMode> {
        Binding(
            get: { effectiveGlyphMode },
            set: { mode in
                guard mode != .visual || model.glyphDiff != nil || model.loadingGlyphDiff else { return }
                model.glyphMode = mode
            }
        )
    }

    private var glyphModePicker: some View {
        Picker("Preview", selection: glyphModeSelection) {
            ForEach(DesktopGlyphDiffMode.allCases) { Text($0.rawValue).tag($0) }
        }
        .pickerStyle(.segmented)
        .labelsHidden()
        .frame(width: 150)
    }

    @ViewBuilder private var glyphToolbar: some View {
        if effectiveGlyphMode == .visual, let document = model.glyphDiff {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 12) {
                    glyphModePicker
                    Spacer(minLength: 12)
                    glyphControls(document)
                }
                VStack(alignment: .leading, spacing: 8) {
                    glyphModePicker
                    glyphControls(document)
                        .frame(maxWidth: .infinity, alignment: .trailing)
                }
            }
        } else {
            HStack(spacing: 12) {
                glyphModePicker
                Spacer(minLength: 12)
                textControls
            }
        }
    }

    private var textControls: some View {
        HStack(spacing: 10) {
            Picker("Layout", selection: $diffStyle) {
                Text("Unified").tag(DiffStyle.unified)
                Text("Split").tag(DiffStyle.split)
            }.pickerStyle(.segmented).labelsHidden().frame(width: 150)
            Toggle("Wrap Lines", isOn: Binding(get: { overflow == .wrap }, set: { overflow = $0 ? .wrap : .scroll }))
                .toggleStyle(.checkbox).fixedSize()
        }
    }

    @ViewBuilder private func textDiff(_ comparison: GitFileComparison) -> some View {
        if let old = comparison.oldContent.text, let new = comparison.newContent.text {
            PierreDiffView(
                oldContent: old,
                newContent: new,
                fileName: comparison.path,
                diffStyle: $diffStyle,
                overflowMode: $overflow,
                renderOptions: .init(theme: .pierreSoft, diffIndicators: .bars, hunkSeparators: .lineInfo,
                                     lineDiffType: .wordAlt, disableLineNumbers: false, disableFileHeader: true),
                isEditing: false,
                annotations: nil
            )
        } else {
            ContentUnavailableView("Text diff unavailable", systemImage: "doc.questionmark",
                                   description: Text(contentMessage(comparison)))
        }
    }

    private func glyphControls(_ document: GlyphDiffDocument) -> some View {
        let pair = selectedPair(document)
        let regions = pair?.difference?.regions ?? []
        return HStack(spacing: 8) {
            Picker("Layer", selection: Binding(get: {
                selectedLayerID ?? document.initialLayerID ?? ""
            }, set: {
                selectedLayerID = $0
                selectedDifferenceIndex = nil
                zoom = viewportStore.state(for: viewportKey(layerID: $0))?.magnification ?? 1
                viewportRequest = .init(id: viewportRequest.id + 1, target: .restore)
            })) {
                ForEach(document.layers) { pair in
                    Text(pair.label + (pair.changed ? "" : " · unchanged")).tag(pair.id)
                }
            }
            .frame(minWidth: 140, idealWidth: 175, maxWidth: 190)
            .layoutPriority(1)
            Picker("Overlay", selection: $overlay) {
                ForEach(GlyphOverlayMode.allCases) { Text($0.rawValue).tag($0) }
            }.pickerStyle(.segmented).labelsHidden().frame(width: 170)
            Toggle("Guides", isOn: $guides).toggleStyle(.checkbox).fixedSize()
            Button { zoom = GlyphViewportMath.stepped(zoom, direction: -1) } label: { Image(systemName: "minus") }
                .buttonStyle(.borderless).accessibilityLabel("Zoom out").help("Zoom Out (⌘−)")
            Text("\(Int((zoom * 100).rounded()))%")
                .font(.caption.monospacedDigit()).frame(minWidth: 42).fixedSize()
                .accessibilityLabel("Zoom \(Int((zoom * 100).rounded())) percent")
            Button { zoom = GlyphViewportMath.stepped(zoom, direction: 1) } label: { Image(systemName: "plus") }
                .buttonStyle(.borderless).accessibilityLabel("Zoom in").help("Zoom In (⌘+)")
            Divider().frame(height: 18)
            Button { selectDifference(regions, offset: -1) } label: { Image(systemName: "chevron.left") }
                .buttonStyle(.borderless).accessibilityLabel("Previous difference")
                .help("Zoom to previous difference").disabled(selectedDifferenceIndex == nil || selectedDifferenceIndex == 0)
            Button { resetGlyphViewport() } label: { Image(systemName: "scope") }
                .buttonStyle(.borderless).accessibilityLabel("Reset glyph zoom").help("Fit Glyph (⌘0)")
            Button { selectDifference(regions, offset: 1) } label: { Image(systemName: "chevron.right") }
                .buttonStyle(.borderless).accessibilityLabel("Next difference")
                .help("Zoom to next difference")
                .disabled(regions.isEmpty || selectedDifferenceIndex == regions.count - 1)
        }
    }

    @ViewBuilder private func glyphVisual(_ document: GlyphDiffDocument) -> some View {
        if let pair = selectedPair(document) {
            VStack(spacing: 0) {
                HStack {
                    Text(pair.changed ? "Changed layer" : "No visual geometry difference; see Text").foregroundStyle(.secondary)
                    Spacer()
                    if let before = pair.before, let after = pair.after {
                        Text("Width \(number(before.width)) → \(number(after.width))").foregroundStyle(.secondary)
                    }
                }.font(.caption).padding(.horizontal, 12).padding(.vertical, 7)
                Divider()
                GlyphDiffWebView(
                    layer: pair,
                    overlay: overlay,
                    guides: guides,
                    zoom: $zoom,
                    viewportKey: viewportKey(layerID: pair.id),
                    viewportStore: viewportStore,
                    viewportRequest: viewportRequest,
                    onReset: resetGlyphViewport
                )
            }
            .onAppear { if selectedLayerID == nil { selectedLayerID = document.initialLayerID } }
            .onChange(of: document) { _, newDocument in
                if !newDocument.layers.contains(where: { $0.id == selectedLayerID }) {
                    selectedLayerID = newDocument.initialLayerID
                }
                selectedDifferenceIndex = nil
                let layerID = selectedLayerID ?? newDocument.initialLayerID ?? ""
                zoom = viewportStore.state(for: viewportKey(layerID: layerID))?.magnification ?? 1
                viewportRequest = .init(id: viewportRequest.id + 1, target: .restore)
            }
        } else {
            ContentUnavailableView("No glyph layers", systemImage: "character.cursor.ibeam")
        }
    }

    private func selectedPair(_ document: GlyphDiffDocument) -> GlyphLayerPair? {
        document.layers.first(where: { $0.id == (selectedLayerID ?? document.initialLayerID) }) ?? document.layers.first
    }

    private func resetGlyphViewport() {
        selectedDifferenceIndex = nil
        let layerID = selectedLayerID ?? model.glyphDiff?.initialLayerID ?? ""
        viewportStore.removeValue(for: viewportKey(layerID: layerID))
        zoom = 1
        viewportRequest = .init(id: viewportRequest.id + 1, target: .fit)
    }

    private func viewportKey(layerID: String) -> String {
        [model.selectedProject ?? "", model.selectedChange?.path ?? "", layerID]
            .joined(separator: "\u{1F}")
    }

    private func selectDifference(_ regions: [GlyphDifferenceRegion], offset: Int) {
        guard !regions.isEmpty else { return }
        let proposed = (selectedDifferenceIndex ?? (offset > 0 ? -1 : regions.count)) + offset
        guard regions.indices.contains(proposed) else { return }
        selectedDifferenceIndex = proposed
        viewportRequest = .init(id: viewportRequest.id + 1, target: .region(regions[proposed]))
    }

    private func row(_ node: GitChangeTreeNode) -> some View {
        Group {
            if let change = node.change {
                Button { model.selectChange(change) } label: {
                    HStack(spacing: 7) {
                        Image(systemName: icon(change.path)).foregroundStyle(.secondary).frame(width: 16)
                        Text(node.name).lineLimit(1).truncationMode(.middle)
                        Spacer(minLength: 4)
                        statusBadge(change)
                    }.padding(.horizontal, 7).padding(.vertical, 5).contentShape(Rectangle())
                }.buttonStyle(.plain).help(change.path)
                    .background(model.selectedChange?.path == change.path ? Color.accentColor.opacity(0.18) : .clear,
                                in: RoundedRectangle(cornerRadius: 6))
                    .accessibilityAddTraits(model.selectedChange?.path == change.path ? .isSelected : [])
                    .accessibilityLabel("\(change.path), status \(change.kind.rawValue)")
                    .accessibilityIdentifier("git-change-\(change.path)")
            } else {
                Label(node.name, systemImage: "folder.fill").fontWeight(.medium).padding(.vertical, 3)
            }
        }
    }

    private func tree(_ changes: [GitObservation.Change]) -> [GitChangeTreeNode] {
        GitChangeTree.hierarchy(changes)
    }

    private func filtered(_ changes: [GitObservation.Change]) -> [GitObservation.Change] {
        GitChangeTree.filtered(changes, query: filter)
    }

    private func statusBadge(_ change: GitObservation.Change) -> some View {
        Text(change.statusLabel).font(.caption.monospaced().weight(.bold)).foregroundStyle(statusColor(change.kind))
            .frame(minWidth: 16).accessibilityLabel("Status \(change.kind.rawValue)")
    }

    private func statusColor(_ kind: GitObservation.Change.Kind) -> Color {
        switch kind {
        case .added, .untracked: return .green
        case .deleted: return .red
        case .renamed, .copied: return .blue
        case .conflicted: return .orange
        case .modified: return .secondary
        }
    }

    private func icon(_ path: String) -> String {
        if path.hasSuffix(".swift") { return "swift" }
        if path.hasSuffix(".glyph") || path.hasSuffix(".glyphs") { return "character.cursor.ibeam" }
        if path.hasSuffix(".png") || path.hasSuffix(".jpg") || path.hasSuffix(".svg") { return "photo" }
        if path.hasSuffix(".md") { return "book.closed" }
        return "doc.text"
    }

    private func contentMessage(_ comparison: GitFileComparison) -> String {
        let values = [comparison.oldContent, comparison.newContent]
        if values.contains(where: { if case .symbolicLink = $0 { true } else { false } }) { return "Symbolic links are shown only as file status and are never followed." }
        if values.contains(where: { if case .binary = $0 { true } else { false } }) { return "This file is binary or is not valid UTF-8." }
        if let size = values.compactMap({ if case .oversized(let size) = $0 { size } else { nil } }).max() {
            return "This file is \(ByteCountFormatter.string(fromByteCount: Int64(size), countStyle: .file)); the preview limit is 2 MB per side."
        }
        return model.comparisonMessage.isEmpty ? "No readable text content is available." : model.comparisonMessage
    }

    private func number(_ value: Double) -> String {
        value.rounded() == value ? String(Int(value)) : String(format: "%.2f", value)
    }
}

enum GlyphOverlayMode: String, CaseIterable, Identifiable {
    case before = "Before"
    case both = "Both"
    case after = "After"
    var id: String { rawValue }
}

private enum GlyphViewportTarget: Equatable {
    case fit
    case region(GlyphDifferenceRegion)
    case restore
}

private struct GlyphViewportRequest: Equatable {
    let id: Int
    let target: GlyphViewportTarget
}

private enum GlyphCanvasAction {
    case step(Int, CGPoint)
    case smoothZoom(Double, CGPoint)
    case magnify(Double, CGPoint)
    case pan(CGPoint)
    case fillPreview(Bool)
    case fit
    case actualSize
}

private final class GlyphViewportSessionStore {
    private var states: [String: GlyphViewportState] = [:]
    func state(for key: String) -> GlyphViewportState? { states[key] }
    func set(_ state: GlyphViewportState, for key: String) { states[key] = state }
    func removeValue(for key: String) { states.removeValue(forKey: key) }
}

private final class GlyphDiffCanvasWebView: WKWebView {
    var actionHandler: ((GlyphCanvasAction) -> Void)?
    private var zoomToolActive = false
    private var optionActive = false
    private var fillPreviewActive = false

    override var acceptsFirstResponder: Bool { true }

    override func performKeyEquivalent(with event: NSEvent) -> Bool {
        let flags = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
        guard flags.contains(.command), let key = event.charactersIgnoringModifiers?.lowercased() else {
            return super.performKeyEquivalent(with: event)
        }
        if key == "+" || key == "=" {
            actionHandler?(.step(1, CGPoint(x: bounds.midX, y: bounds.midY)))
            return true
        }
        if key == "-" {
            actionHandler?(.step(-1, CGPoint(x: bounds.midX, y: bounds.midY)))
            return true
        }
        if key == "0" {
            actionHandler?(flags.contains(.option) ? .actualSize : .fit)
            return true
        }
        return super.performKeyEquivalent(with: event)
    }

    override func keyDown(with event: NSEvent) {
        let flags = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
        if event.charactersIgnoringModifiers == " ",
           !flags.contains(.command), !flags.contains(.control), !flags.contains(.option) {
            if !fillPreviewActive {
                fillPreviewActive = true
                actionHandler?(.fillPreview(true))
            }
            return
        }
        if event.charactersIgnoringModifiers?.lowercased() == "z",
           !flags.contains(.command), !flags.contains(.control) {
            zoomToolActive = true
            optionActive = flags.contains(.option)
            window?.invalidateCursorRects(for: self)
            return
        }
        super.keyDown(with: event)
    }

    override func keyUp(with event: NSEvent) {
        if event.charactersIgnoringModifiers == " " {
            endFillPreview()
            return
        }
        if event.charactersIgnoringModifiers?.lowercased() == "z" {
            zoomToolActive = false
            window?.invalidateCursorRects(for: self)
            return
        }
        super.keyUp(with: event)
    }

    override func flagsChanged(with event: NSEvent) {
        optionActive = event.modifierFlags.contains(.option)
        if zoomToolActive { window?.invalidateCursorRects(for: self) }
        super.flagsChanged(with: event)
    }

    override func mouseDown(with event: NSEvent) {
        window?.makeFirstResponder(self)
        guard zoomToolActive else {
            super.mouseDown(with: event)
            return
        }
        actionHandler?(.step(event.modifierFlags.contains(.option) ? -1 : 1, canvasPoint(event)))
    }

    override func scrollWheel(with event: NSEvent) {
        window?.makeFirstResponder(self)
        if event.modifierFlags.contains(.option) {
            let delta = event.scrollingDeltaY == 0 ? event.scrollingDeltaX : event.scrollingDeltaY
            // AppKit reports wheel deltas in the opposite direction from the
            // zoom convention used by Glyphs' edit view.
            if delta != 0 { actionHandler?(.smoothZoom(-delta, canvasPoint(event))) }
        } else {
            // Move the canvas opposite to the physical scroll gesture, matching
            // the directional convention requested for the Glyphs diff view.
            actionHandler?(.pan(CGPoint(x: -event.scrollingDeltaX, y: -event.scrollingDeltaY)))
        }
    }

    override func magnify(with event: NSEvent) {
        window?.makeFirstResponder(self)
        actionHandler?(.magnify(max(0.01, 1 + event.magnification), canvasPoint(event)))
    }

    override func resetCursorRects() {
        super.resetCursorRects()
        addCursorRect(bounds, cursor: zoomToolActive ? zoomCursor : .arrow)
    }

    private var zoomCursor: NSCursor {
        if #available(macOS 15.0, *) { return optionActive ? .zoomOut : .zoomIn }
        return .crosshair
    }

    override func resignFirstResponder() -> Bool {
        zoomToolActive = false
        endFillPreview()
        window?.invalidateCursorRects(for: self)
        return super.resignFirstResponder()
    }

    private func endFillPreview() {
        guard fillPreviewActive else { return }
        fillPreviewActive = false
        actionHandler?(.fillPreview(false))
    }

    private func canvasPoint(_ event: NSEvent) -> CGPoint {
        let point = convert(event.locationInWindow, from: nil)
        return CGPoint(x: point.x, y: isFlipped ? point.y : bounds.height - point.y)
    }

}

private struct GlyphDiffWebView: NSViewRepresentable {
    let layer: GlyphLayerPair
    let overlay: GlyphOverlayMode
    let guides: Bool
    @Binding var zoom: Double
    let viewportKey: String
    let viewportStore: GlyphViewportSessionStore
    let viewportRequest: GlyphViewportRequest
    let onReset: () -> Void
    @Environment(\.colorScheme) private var colorScheme

    private static let contentWorld = WKContentWorld.world(name: "GlyphDiffCamera")

    func makeCoordinator() -> Coordinator {
        Coordinator(zoom: $zoom, viewportStore: viewportStore, onReset: onReset)
    }

    func makeNSView(context: Context) -> GlyphDiffCanvasWebView {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        configuration.defaultWebpagePreferences.allowsContentJavaScript = true
        configuration.userContentController.addUserScript(WKUserScript(
            source: Self.cameraScript,
            injectionTime: .atDocumentEnd,
            forMainFrameOnly: true,
            in: Self.contentWorld
        ))
        configuration.userContentController.add(context.coordinator, contentWorld: Self.contentWorld,
                                                name: "viewportState")
        let view = GlyphDiffCanvasWebView(frame: .zero, configuration: configuration)
        view.navigationDelegate = context.coordinator
        view.allowsMagnification = false
        view.setValue(false, forKey: "drawsBackground")
        view.actionHandler = { [weak view, weak coordinator = context.coordinator] action in
            guard let view else { return }
            coordinator?.perform(action, in: view)
        }
        return view
    }

    static func dismantleNSView(_ webView: GlyphDiffCanvasWebView, coordinator: Coordinator) {
        webView.configuration.userContentController.removeScriptMessageHandler(
            forName: "viewportState", contentWorld: Self.contentWorld
        )
    }

    func updateNSView(_ webView: GlyphDiffCanvasWebView, context: Context) {
        context.coordinator.zoomBinding = $zoom
        context.coordinator.onReset = onReset
        let fullViewBox = canvasViewBox()
        let requestChanged = context.coordinator.requestID != viewportRequest.id
        context.coordinator.requestID = viewportRequest.id
        context.coordinator.fullViewBox = fullViewBox
        context.coordinator.viewportKey = viewportKey
        context.coordinator.presentation = presentation
        let signature = "\(viewportKey):\(String(reflecting: layer)):\(fullViewBox)"
        if context.coordinator.signature != signature {
            context.coordinator.signature = signature
            context.coordinator.loaded = false
            context.coordinator.pendingState = targetState(fullViewBox, viewport: webView.bounds.size,
                                                            honorRequest: requestChanged)
            webView.loadHTMLString(html(viewBox: fullViewBox), baseURL: nil)
        } else if context.coordinator.loaded {
            context.coordinator.sendPresentation(to: webView)
            if requestChanged {
                context.coordinator.setCamera(targetState(fullViewBox, viewport: webView.bounds.size,
                                                          honorRequest: true), in: webView)
            } else if abs(context.coordinator.currentState.magnification - zoom) > 0.000_001 {
                context.coordinator.command("setZoom", payload: ["magnification": zoom], in: webView)
            }
        }
    }

    private func targetState(_ fullViewBox: CGRect, viewport: CGSize, honorRequest: Bool) -> GlyphViewportState {
        let measuredViewport = viewport.width > 0 && viewport.height > 0
            ? viewport
            : CGSize(width: 1_000, height: 700)
        if honorRequest, case .region(let region) = viewportRequest.target,
           let target = GlyphViewportMath.focusRect(for: region.bounds) {
            let svgTarget = CGRect(x: target.minX, y: -target.maxY, width: target.width, height: target.height)
            return GlyphViewportMath.focused(viewport: measuredViewport, viewBox: fullViewBox, target: svgTarget)
        }
        if (!honorRequest || viewportRequest.target == .restore),
           let saved = viewportStore.state(for: viewportKey),
           GlyphViewportMath.isRestorable(saved, in: fullViewBox) { return saved }
        return GlyphViewportMath.fitted(fullViewBox)
    }

    private var presentation: Presentation {
        Presentation(overlay: overlay.rawValue.lowercased(), guides: guides,
                     background: colorScheme == .dark ? "#171717" : "#ffffff",
                     neutral: colorScheme == .dark ? "#e8e8e8" : "#242424",
                     control: colorScheme == .dark ? "#a8a8a8" : "#858585",
                     handle: colorScheme == .dark ? "#707070" : "#b8b8b8",
                     guide: colorScheme == .dark ? "#66594d" : "#d7b28a",
                     hasBefore: layer.before != nil, hasAfter: layer.after != nil)
    }

    private func canvasViewBox() -> CGRect {
        let snapshots = [layer.before, layer.after].compactMap { $0 }
        let points = snapshots.flatMap { $0.outline + $0.openOutline }.flatMap(\.points).filter { $0.count >= 2 }
        let metrics = snapshots.first?.metrics ?? .init(ascender: 800, capHeight: 700, xHeight: 500, descender: -200)
        let widths = snapshots.map(\.width)
        let minX = min(points.map { $0[0] }.min() ?? 0, 0) - 80
        let maxX = max(points.map { $0[0] }.max() ?? 600, widths.max() ?? 600) + 80
        let minY = min(points.map { $0[1] }.min() ?? metrics.descender, metrics.descender) - 80
        let maxY = max(points.map { $0[1] }.max() ?? metrics.ascender, metrics.ascender) + 80
        return CGRect(x: minX, y: -maxY, width: maxX - minX, height: maxY - minY)
    }

    private func html(viewBox: CGRect) -> String {
        let minX = viewBox.minX, maxX = viewBox.maxX
        let maxY = -viewBox.minY, minY = maxY - viewBox.height
        let snapshots = [layer.before, layer.after].compactMap { $0 }
        let metrics = snapshots.first?.metrics ?? .init(ascender: 800, capHeight: 700, xHeight: 500, descender: -200)
        var metricGuides = ""
        for (name, value) in [("Ascender", metrics.ascender), ("Cap Height", metrics.capHeight),
                              ("x-Height", metrics.xHeight), ("Baseline", 0), ("Descender", metrics.descender)] {
            metricGuides += "<line class='guide' x1='\(minX)' y1='\(-value)' x2='\(maxX)' y2='\(-value)'/><g class='fixed-position-label fixed-guide-label' data-x='\(maxX)' data-y='\(-value)'><text class='label' x='-12' y='-10'>\(name)</text></g>"
        }
        metricGuides += "<line class='origin-advance advance guide-dependent' x1='0' y1='\(-metrics.ascender)' x2='0' y2='\(-metrics.descender)'/>"
        let before = layer.before.map(neutralSnapshot) ?? ""
        let after = layer.after.map(neutralSnapshot) ?? ""
        let pieces = layer.difference.map { deltaPieces($0, minY: minY, maxY: maxY) }
        return """
        <!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'none'">
        <style>:root{--background:#fff;--neutral:#242424;--control:#858585;--handle:#b8b8b8;--guide:#d7b28a;--outline-stroke:.5;--delta-stroke:.65;--detail-stroke:.25;--inverse-zoom:1}html,body{margin:0;width:100%;height:100%;overflow:hidden;background:var(--background);user-select:none}svg{width:100%;height:100%;min-width:520px;min-height:420px}.guide{stroke:var(--guide);stroke-width:1;vector-effect:non-scaling-stroke;opacity:.72}.label{fill:var(--guide);font:500 12px -apple-system;text-anchor:end}.neutral{fill:none;stroke:var(--neutral);stroke-width:var(--outline-stroke);fill-rule:evenodd;vector-effect:non-scaling-stroke}.neutral-node,.neutral-control{fill:none;stroke:var(--control);stroke-width:var(--detail-stroke);vector-effect:non-scaling-stroke}.neutral-handle{stroke:var(--handle);stroke-width:var(--detail-stroke);vector-effect:non-scaling-stroke}.open{fill:none}.advance{stroke-dasharray:5 4;opacity:.55}.origin-advance{stroke:var(--guide);stroke-width:1.25;stroke-dasharray:6 4;stroke-linecap:round;opacity:.9;vector-effect:non-scaling-stroke}.delta{fill:#3fd1e25c;stroke:none;fill-rule:evenodd}.width-change{fill:#3fd1e25c}.reference-change{fill:none;stroke:#3fe2a6;stroke-width:var(--delta-stroke);vector-effect:non-scaling-stroke}.current-change{fill:none;stroke:#3fd1e2;stroke-width:var(--delta-stroke);vector-effect:non-scaling-stroke}.reference-handle,.current-handle{stroke-width:var(--detail-stroke);opacity:.72;vector-effect:non-scaling-stroke}.reference-handle{stroke:#3fe2a6}.current-handle{stroke:var(--handle)}.reference-node,.reference-control{fill:none;stroke:#3fe2a6;stroke-width:var(--detail-stroke);vector-effect:non-scaling-stroke}.current-node,.current-control{fill:none;stroke:var(--control);stroke-width:var(--detail-stroke);vector-effect:non-scaling-stroke}.anchor-link{stroke:#3fd1e2;stroke-width:var(--detail-stroke);opacity:.65;vector-effect:non-scaling-stroke}.anchor{stroke-width:var(--detail-stroke);fill:none;vector-effect:non-scaling-stroke}.anchor-label{font:12px -apple-system}.reference-change.anchor-label{fill:#3fe2a6;stroke:none;text-anchor:end}.current-change.anchor-label{fill:#3fd1e2;stroke:none;text-anchor:start}.fixed-control{transform-box:fill-box;transform-origin:center;transform:scale(var(--inverse-zoom))}.fill-preview path.neutral:not(.open){fill:#000;stroke:#000}.fill-preview .neutral-node,.fill-preview .neutral-control,.fill-preview .neutral-handle,.fill-preview .advance,.fill-preview #delta-fill,.fill-preview #reference-changes,.fill-preview #current-changes{display:none}</style></head>
        <body><svg id="glyph-canvas" role="img" aria-label="Read-only glyph difference for \(escape(layer.label))" viewBox="\(viewBox.minX) \(viewBox.minY) \(viewBox.width) \(viewBox.height)" preserveAspectRatio="xMidYMid meet"><g id="camera"><g id="metric-guides" class="guide-dependent">\(metricGuides)</g><g id="before-neutral">\(before)</g><g id="after-neutral">\(after)</g><g id="delta-fill">\(pieces?.fill ?? "")</g><g id="reference-changes">\(pieces?.reference ?? "")</g><g id="current-changes">\(pieces?.current ?? "")</g></g></svg></body></html>
        """
    }

    private func neutralSnapshot(_ value: GlyphLayerSnapshot) -> String {
        var result = "<path class='neutral' d='\(path(value.outline))'/><path class='neutral open' d='\(path(value.openOutline))'/>"
        result += "<line class='neutral advance guide-dependent' x1='\(value.width)' y1='\(-value.metrics.ascender)' x2='\(value.width)' y2='\(-value.metrics.descender)'/>"
        result += pathDetails(value.outline, css: "neutral")
        result += pathDetails(value.openOutline, css: "neutral")
        return result
    }

    private struct DeltaPieces { let fill: String; let reference: String; let current: String }

    private func deltaPieces(_ value: GlyphLayerDifference, minY: Double, maxY: Double) -> DeltaPieces {
        var fill = "", reference = "", current = ""
        if value.outlineChanged {
            fill += "<path class='delta' d='\(path(value.referenceOutline)) \(path(value.currentOutline))'/>"
        }
        if let width = value.width, width.count >= 2 {
            let before = width[0], after = width[1]
            if let before, let after {
                fill += "<rect class='width-change' x='\(min(before, after))' y='\(-maxY)' width='\(abs(after-before))' height='\(maxY-minY)'/>"
            }
            if let before {
                reference += "<line class='reference-change' x1='\(before)' y1='\(-maxY)' x2='\(before)' y2='\(-minY)'/>"
            }
            if let after {
                current += "<line class='current-change' x1='\(after)' y1='\(-maxY)' x2='\(after)' y2='\(-minY)'/>"
            }
        }
        reference += changedSegments(value.referenceSegments, css: "reference")
        current += changedSegments(value.currentSegments, css: "current")
        for anchor in value.anchors {
            if let before = anchor.before, let after = anchor.after,
               before.count >= 2, after.count >= 2 {
                fill += "<line class='anchor-link' x1='\(before[0])' y1='\(-before[1])' x2='\(after[0])' y2='\(-after[1])'/>"
            }
            if let before = anchor.before, before.count >= 2 {
                reference += changedAnchor(anchor.name, point: before, css: "reference")
            }
            if let after = anchor.after, after.count >= 2 {
                current += changedAnchor(anchor.name, point: after, css: "current")
            }
        }
        return DeltaPieces(fill: fill, reference: reference, current: current)
    }

    private func changedAnchor(_ name: String, point: [Double], css: String) -> String {
        let labelX = css == "reference" ? -8 : 8
        let labelY = css == "reference" ? -8 : 14
        return "<circle class='\(css)-change anchor fixed-control' cx='\(point[0])' cy='\(-point[1])' r='5'/><g class='fixed-position-label fixed-anchor-label' data-x='\(point[0])' data-y='\(-point[1])'><text class='\(css)-change anchor-label' x='\(labelX)' y='\(labelY)'>\(escape(name))</text></g>"
    }

    private func changedSegments(_ values: [GlyphPathElement], css: String) -> String {
        values.map { segment in
            "<path class='\(css)-change' d='\(segmentPath(segment))'/>" + segmentDetails(segment, css: css)
        }.joined()
    }

    private func segmentPath(_ segment: GlyphPathElement) -> String {
        switch segment.kind {
        case 1 where segment.points.count >= 2:
            return "M \(point(segment.points[0])) L \(point(segment.points[1]))"
        case 2 where segment.points.count >= 4:
            return "M \(point(segment.points[0])) C \(point(segment.points[1])) \(point(segment.points[2])) \(point(segment.points[3]))"
        default:
            return ""
        }
    }

    private func segmentDetails(_ segment: GlyphPathElement, css: String) -> String {
        guard segment.points.count >= 2 else { return "" }
        var result = onCurve(segment.points[0], css: css) + onCurve(segment.points.last!, css: css)
        if segment.kind == 2, segment.points.count >= 4 {
            result += handle(from: segment.points[0], to: segment.points[1], css: css)
            result += handle(from: segment.points[3], to: segment.points[2], css: css)
            result += control(segment.points[1], css: css) + control(segment.points[2], css: css)
        }
        return result
    }

    private func path(_ elements: [GlyphPathElement]) -> String {
        elements.map { element in
            switch element.kind {
            case 0 where element.points.count >= 1: return "M \(point(element.points[0]))"
            case 1 where element.points.count >= 1: return "L \(point(element.points[0]))"
            case 2 where element.points.count >= 3: return "C \(point(element.points[0])) \(point(element.points[1])) \(point(element.points[2]))"
            case 3: return "Z"
            default: return ""
            }
        }.joined(separator: " ")
    }

    private func pathDetails(_ elements: [GlyphPathElement], css: String) -> String {
        var result = "", cursor: [Double]?
        for element in elements {
            switch element.kind {
            case 0 where !element.points.isEmpty, 1 where !element.points.isEmpty:
                cursor = element.points[0]
                result += onCurve(element.points[0], css: css)
            case 2 where element.points.count >= 3:
                let first = element.points[0], second = element.points[1], end = element.points[2]
                if let cursor { result += handle(from: cursor, to: first, css: css) }
                result += handle(from: end, to: second, css: css)
                result += control(first, css: css) + control(second, css: css) + onCurve(end, css: css)
                cursor = end
            default: break
            }
        }
        return result
    }

    private func handle(from: [Double], to: [Double], css: String) -> String {
        guard from.count >= 2, to.count >= 2 else { return "" }
        return "<line class='\(css)-handle' x1='\(from[0])' y1='\(-from[1])' x2='\(to[0])' y2='\(-to[1])'/>"
    }

    private func onCurve(_ value: [Double], css: String) -> String {
        guard value.count >= 2 else { return "" }
        return "<rect class='\(css)-node fixed-control' x='\(value[0]-3.5)' y='\(-value[1]-3.5)' width='7' height='7'/>"
    }

    private func control(_ value: [Double], css: String) -> String {
        guard value.count >= 2 else { return "" }
        return "<circle class='\(css)-control fixed-control' cx='\(value[0])' cy='\(-value[1])' r='3'/>"
    }

    private func point(_ value: [Double]) -> String { "\(value[0]) \(-value[1])" }
    private func escape(_ value: String) -> String {
        value.replacingOccurrences(of: "&", with: "&amp;").replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;").replacingOccurrences(of: "\"", with: "&quot;")
    }

    struct Presentation: Equatable {
        let overlay: String
        let guides: Bool
        let background: String
        let neutral: String
        let control: String
        let handle: String
        let guide: String
        let hasBefore: Bool
        let hasAfter: Bool

        var payload: [String: Any] {
            ["overlay": overlay, "guides": guides, "background": background,
             "neutral": neutral, "control": control, "handle": handle, "guide": guide,
             "hasBefore": hasBefore, "hasAfter": hasAfter]
        }
    }

    private static let cameraScript = """
    (() => {
      const svg = document.getElementById('glyph-canvas');
      const camera = document.getElementById('camera');
      if (!svg || !camera) return;
      const box = svg.viewBox.baseVal;
      const full = {x: box.x, y: box.y, width: box.width, height: box.height,
                    midX: box.x + box.width / 2, midY: box.y + box.height / 2};
      let key = '';
      let state = {centerX: full.midX, centerY: full.midY, magnification: 1};
      var frame = 0;
      let finishTimer = 0;
      let lastPost = 0;
      const clamp = value => Math.min(32, Math.max(0.25, value));
      const finite = value => typeof value === 'number' && Number.isFinite(value);
      const fixedLabels = Array.from(document.querySelectorAll('.fixed-position-label')).map(element => ({
        element, x: Number(element.dataset.x), y: Number(element.dataset.y)
      })).filter(item => finite(item.x) && finite(item.y));
      const displayScale = () => {
        const matrix = svg.getScreenCTM();
        const scale = matrix ? Math.hypot(matrix.a, matrix.b) : 1;
        return finite(scale) && scale > 0 ? scale : 1;
      };
      const visible = (id, show) => {
        const element = document.getElementById(id);
        if (element) element.style.display = show ? '' : 'none';
      };
      const post = force => {
        const now = performance.now();
        if (!force && now - lastPost < 66) return;
        lastPost = now;
        window.webkit.messageHandlers.viewportState.postMessage({
          key, centerX: state.centerX, centerY: state.centerY,
          magnification: state.magnification, final: force
        });
      };
      const apply = () => {
        frame = 0;
        const z = state.magnification;
        const tx = full.midX - z * state.centerX;
        const ty = full.midY - z * state.centerY;
        const inverse = 1 / (z * displayScale());
        camera.setAttribute('transform', `matrix(${z} 0 0 ${z} ${tx} ${ty})`);
        fixedLabels.forEach(item => {
          item.element.setAttribute('transform', `translate(${item.x} ${item.y}) scale(${inverse})`);
        });
        svg.style.setProperty('--inverse-zoom', String(inverse));
        post(false);
        clearTimeout(finishTimer);
        finishTimer = setTimeout(() => post(true), 90);
      };
      const schedule = () => { if (!frame) frame = requestAnimationFrame(apply); };
      new ResizeObserver(schedule).observe(svg);
      const screenToRoot = (x, y) => {
        const point = svg.createSVGPoint(); point.x = x; point.y = y;
        const matrix = svg.getScreenCTM();
        return matrix ? point.matrixTransform(matrix.inverse()) : {x: full.midX, y: full.midY};
      };
      const zoomAt = (next, x, y) => {
        const root = screenToRoot(x, y);
        const old = state.magnification;
        const contentX = state.centerX + (root.x - full.midX) / old;
        const contentY = state.centerY + (root.y - full.midY) / old;
        const z = clamp(next);
        state = {centerX: contentX - (root.x - full.midX) / z,
                 centerY: contentY - (root.y - full.midY) / z, magnification: z};
        schedule();
      };
      const setPresentation = payload => {
        const both = payload.overlay === 'both';
        visible('before-neutral', payload.overlay === 'before' || (both && !payload.hasAfter && payload.hasBefore));
        visible('after-neutral', payload.overlay === 'after' || (both && payload.hasAfter));
        visible('delta-fill', both);
        visible('reference-changes', payload.overlay !== 'after');
        visible('current-changes', payload.overlay !== 'before');
        document.querySelectorAll('.guide-dependent').forEach(element => {
          element.style.display = payload.guides ? '' : 'none';
        });
        document.documentElement.style.setProperty('--background', payload.background);
        document.documentElement.style.setProperty('--neutral', payload.neutral);
        document.documentElement.style.setProperty('--control', payload.control);
        document.documentElement.style.setProperty('--handle', payload.handle);
        document.documentElement.style.setProperty('--guide', payload.guide);
      };
      globalThis.glyphCamera = {
        command(name, payload) {
          if (!payload || typeof payload !== 'object') return false;
          if (name === 'initialize') {
            key = String(payload.key || '');
            if (finite(payload.centerX) && finite(payload.centerY) && finite(payload.magnification)) {
              state = {centerX: payload.centerX, centerY: payload.centerY,
                       magnification: clamp(payload.magnification)};
            }
            setPresentation(payload.presentation || {});
            schedule();
            return true;
          }
          if (name === 'setPresentation') { setPresentation(payload); return true; }
          if (name === 'setFillPreview' && typeof payload.active === 'boolean') {
            svg.classList.toggle('fill-preview', payload.active); return true;
          }
          if (name === 'setCamera' && finite(payload.centerX) && finite(payload.centerY) && finite(payload.magnification)) {
            state = {centerX: payload.centerX, centerY: payload.centerY,
                     magnification: clamp(payload.magnification)};
            schedule(); return true;
          }
          if (name === 'setZoom' && finite(payload.magnification)) {
            state.magnification = clamp(payload.magnification); schedule(); return true;
          }
          if (name === 'zoomAt' && finite(payload.magnification) && finite(payload.x) && finite(payload.y)) {
            zoomAt(payload.magnification, payload.x, payload.y); return true;
          }
          if (name === 'smoothZoom' && finite(payload.delta) && finite(payload.x) && finite(payload.y)) {
            zoomAt(state.magnification * Math.exp(payload.delta * 0.0025), payload.x, payload.y); return true;
          }
          if (name === 'magnify' && finite(payload.factor) && finite(payload.x) && finite(payload.y)) {
            zoomAt(state.magnification * payload.factor, payload.x, payload.y); return true;
          }
          if (name === 'panBy' && finite(payload.x) && finite(payload.y)) {
            const origin = screenToRoot(0, 0), delta = screenToRoot(payload.x, payload.y);
            state.centerX += (delta.x - origin.x) / state.magnification;
            state.centerY += (delta.y - origin.y) / state.magnification;
            schedule(); return true;
          }
          return false;
        }
      };
    })();
    """

    final class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
        var signature = ""
        var requestID = -1
        var fullViewBox = CGRect(x: 0, y: -880, width: 760, height: 1160)
        var viewportKey = ""
        var presentation = Presentation(overlay: "both", guides: true, background: "#fff",
                                        neutral: "#242424", control: "#858585", handle: "#b8b8b8",
                                        guide: "#d7b28a",
                                        hasBefore: true, hasAfter: true)
        var sentPresentation: Presentation?
        var currentState = GlyphViewportState(centerX: 380, centerY: -300, magnification: 1)
        var pendingState: GlyphViewportState?
        var loaded = false
        var zoomBinding: Binding<Double>
        let viewportStore: GlyphViewportSessionStore
        var onReset: () -> Void

        init(zoom: Binding<Double>, viewportStore: GlyphViewportSessionStore,
             onReset: @escaping () -> Void) {
            zoomBinding = zoom
            self.viewportStore = viewportStore
            self.onReset = onReset
        }

        func perform(_ action: GlyphCanvasAction, in webView: GlyphDiffCanvasWebView) {
            switch action {
            case .step(let direction, let point):
                command("zoomAt", payload: ["magnification": GlyphViewportMath.stepped(currentState.magnification,
                                                                                         direction: direction),
                                            "x": point.x, "y": point.y], in: webView)
            case .smoothZoom(let delta, let point):
                command("smoothZoom", payload: ["delta": delta, "x": point.x, "y": point.y], in: webView)
            case .magnify(let factor, let point):
                command("magnify", payload: ["factor": factor, "x": point.x, "y": point.y], in: webView)
            case .pan(let delta):
                command("panBy", payload: ["x": delta.x, "y": delta.y], in: webView)
            case .fillPreview(let active):
                command("setFillPreview", payload: ["active": active], in: webView)
            case .fit:
                onReset()
            case .actualSize:
                let value = GlyphViewportMath.actualSizeMagnification(viewport: webView.bounds.size, viewBox: fullViewBox)
                command("setZoom", payload: ["magnification": value], in: webView)
            }
        }

        func setCamera(_ state: GlyphViewportState, in webView: GlyphDiffCanvasWebView) {
            currentState = state
            viewportStore.set(state, for: viewportKey)
            if abs(zoomBinding.wrappedValue - state.magnification) > 0.000_001 {
                zoomBinding.wrappedValue = state.magnification
            }
            command("setCamera", payload: state.payload, in: webView)
        }

        func sendPresentation(to webView: GlyphDiffCanvasWebView) {
            guard sentPresentation != presentation else { return }
            sentPresentation = presentation
            command("setPresentation", payload: presentation.payload, in: webView)
        }

        func command(_ name: String, payload: [String: Any], in webView: GlyphDiffCanvasWebView) {
            guard loaded else { return }
            webView.callAsyncJavaScript(
                "return globalThis.glyphCamera?.command(command, payload) === true;",
                arguments: ["command": name, "payload": payload],
                in: nil,
                in: GlyphDiffWebView.contentWorld,
                completionHandler: nil
            )
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            guard let webView = webView as? GlyphDiffCanvasWebView else { return }
            loaded = true
            sentPresentation = presentation
            let state = pendingState ?? GlyphViewportMath.fitted(fullViewBox)
            pendingState = nil
            currentState = state
            viewportStore.set(state, for: viewportKey)
            zoomBinding.wrappedValue = state.magnification
            var payload = state.payload
            payload["key"] = viewportKey
            payload["presentation"] = presentation.payload
            command("initialize", payload: payload, in: webView)
        }

        func userContentController(_ userContentController: WKUserContentController,
                                   didReceive message: WKScriptMessage) {
            guard message.name == "viewportState", let body = message.body as? [String: Any],
                  body["key"] as? String == viewportKey,
                  let centerX = (body["centerX"] as? NSNumber)?.doubleValue,
                  let centerY = (body["centerY"] as? NSNumber)?.doubleValue,
                  let magnification = (body["magnification"] as? NSNumber)?.doubleValue else { return }
            let final = body["final"] as? Bool ?? false
            let state = GlyphViewportState(centerX: centerX, centerY: centerY, magnification: magnification)
            guard GlyphViewportMath.isRestorable(state, in: fullViewBox) else { return }
            currentState = state
            viewportStore.set(state, for: viewportKey)
            if final || abs(zoomBinding.wrappedValue - magnification) >= 0.005 {
                zoomBinding.wrappedValue = magnification
            }
        }

        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            let scheme = navigationAction.request.url?.scheme
            decisionHandler(scheme == nil || scheme == "about" ? .allow : .cancel)
        }
    }
}

private struct DiffLoadingView: View {
    let title: String
    let messages: [String]
    let accessibilityStatus: String

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var messageIndex = 0

    static func comparison(includesGlyphGeometry: Bool) -> DiffLoadingView {
        DiffLoadingView(
            title: includesGlyphGeometry ? "Preparing glyph and text diff…" : "Preparing text diff…",
            messages: includesGlyphGeometry ? [
                "Reading the reference version from Git…",
                "Comparing HEAD with the working tree…",
                "Preparing text and visual changes…"
            ] : [
                "Reading the reference version from Git…",
                "Comparing HEAD with the working tree…",
                "Preparing changed lines and words…"
            ],
            accessibilityStatus: includesGlyphGeometry
                ? "Preparing the Git text and glyph comparison"
                : "Preparing the Git text comparison"
        )
    }

    static var glyphGeometry: DiffLoadingView {
        DiffLoadingView(
            title: "Rendering glyph geometry…",
            messages: [
                "Reading the reference glyph from Git…",
                "Loading layers and decomposing components…",
                "Comparing outlines, anchors, and widths…",
                "Preparing the interactive visual diff…"
            ],
            accessibilityStatus: "Rendering the visual glyph comparison"
        )
    }

    var body: some View {
        VStack(spacing: 10) {
            ProgressView()
                .controlSize(.large)
            Text(title)
                .font(.headline)
            ZStack {
                Text(messages[messageIndex])
                    .id(messageIndex)
                    .transition(reduceMotion ? .identity : .opacity)
            }
            .font(.callout)
            .foregroundStyle(.secondary)
            .multilineTextAlignment(.center)
            .frame(minHeight: 20)
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(accessibilityStatus)
        .task {
            guard messages.count > 1 else { return }
            while !Task.isCancelled {
                do { try await Task.sleep(for: .seconds(1.8)) }
                catch { return }
                withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.3)) {
                    messageIndex = (messageIndex + 1) % messages.count
                }
            }
        }
    }
}

private extension GlyphViewportState {
    var payload: [String: Any] {
        ["centerX": centerX, "centerY": centerY, "magnification": magnification]
    }
}
