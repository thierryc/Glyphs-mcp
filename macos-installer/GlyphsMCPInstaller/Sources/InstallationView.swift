import AppKit
import SwiftUI
import GlyphsMCPInstallerCore

struct InstallationView: View {
    enum Section { case overview, companions, agents }
    var section: Section = .overview
    @EnvironmentObject private var model: InstallerViewModel
    @State private var pendingRemoval: RemovalTarget?
    @State private var showingBeztraceSetup = false

    var body: some View {
        VStack(alignment: .leading, spacing: 26) {
            if section == .overview { setupActions }
            if !model.message.isEmpty { setupNotice }
            if section != .agents { components }
            if section != .companions { connections }
            if section != .agents && !model.inspectorInstructions.isEmpty {
                Text(model.inspectorInstructions).font(.callout).foregroundStyle(.secondary)
            }
        }
        .confirmationDialog(
            pendingRemoval?.title ?? "Remove item?",
            isPresented: Binding(
                get: { pendingRemoval != nil },
                set: { if !$0 { pendingRemoval = nil } }
            ),
            titleVisibility: .visible,
            presenting: pendingRemoval
        ) { target in
            Button("Remove", role: .destructive) {
                pendingRemoval = nil
                switch target.kind {
                case .component(let id): model.removeComponent(id)
                case .connector(let client): model.removeConnector(client)
                }
            }
            Button("Cancel", role: .cancel) { pendingRemoval = nil }
        } message: { target in
            Text(target.message)
        }
        .sheet(isPresented: $showingBeztraceSetup) {
            BeztraceSetupView()
        }
    }

    private var setupActions: some View {
        HStack(alignment: .center, spacing: 16) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Glyphs components and agent connections")
                    .font(.title3.weight(.semibold))
                Text("Install the bundled v2 components, then configure every supported agent.")
                    .font(.callout).foregroundStyle(.secondary)
            }
            Spacer()
            Button(LocalizedStringKey(model.bulkActionTitle), action: model.installAll)
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(!model.canRunBulkAction)
                .keyboardShortcut(.defaultAction)
        }
    }

    @ViewBuilder private var setupNotice: some View {
        Label(model.message, systemImage: model.notice.isFailure ? "exclamationmark.triangle" : "info.circle")
            .font(.callout)
            .foregroundStyle(model.notice.isFailure ? Color.red : Color.secondary)
            .textSelection(.enabled)
    }

    private var components: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Components").font(.title3.bold())
            SetupCardGrid {
                ForEach(DesktopComponent.all.filter { section != .companions || $0.id != "mcp" }) { component in
                    ComponentSetupCard(
                        component: component,
                        state: model.state(for: component),
                        disabled: !model.canChangeComponents,
                        pythonReady: model.pythonReady,
                        install: { model.installComponent(component.id) },
                        update: { model.updateComponent(component.id) },
                        remove: { pendingRemoval = .component(component) },
                        retry: { model.retryComponent(component.id) }
                    )
                }
                BeztraceSetupCard { showingBeztraceSetup = true }
            }
        }
    }

    private var connections: some View {
        VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Connections").font(.title3.bold())
                Text(section == .overview ? LocalizedStringKey("Install All configures every connection, even when its host app is not detected.") : LocalizedStringKey("Choose Install or Update for the agent you want to connect."))
                    .font(.callout).foregroundStyle(.secondary)
            }
            SetupCardGrid {
                ForEach(InstallerClientKind.allCases) { client in
                    ConnectorSetupCard(
                        client: client,
                        state: model.state(for: client),
                        detected: model.detectedClients.contains(client),
                        version: model.connectorVersions[client],
                        guidance: model.connectorGuidance(client),
                        logoAsset: model.connectorLogoAsset(client),
                        disabled: model.operationsBusy,
                        install: { model.installConnector(client) },
                        update: { model.updateConnector(client) },
                        remove: { pendingRemoval = .connector(client) },
                        retry: { model.retryConnector(client) }
                    )
                }
            }
        }
    }
}

private struct BeztraceSetupCard: View {
    let showSetup: () -> Void
    private let companion = ExternalGlyphsCompanion.beztrace

    var body: some View {
        SetupCard {
            Image(systemName: "pencil.and.outline")
                .font(.system(size: 36)).foregroundStyle(Color.accentColor)
        } title: {
            Text(companion.title).font(.headline)
        } detail: {
            Text(LocalizedStringKey(companion.detail))
        } status: {
            Label(LocalizedStringKey(companion.availability), systemImage: "hammer")
                .font(.caption.weight(.medium)).foregroundStyle(.secondary)
        } actions: {
            HStack {
                Button("Setup details…", action: showSetup)
                    .accessibilityLabel("Beztrace setup details")
                Spacer()
            }
        } footer: {
            Link("Documentation", destination: companion.documentation).font(.caption)
                .accessibilityLabel("Beztrace documentation")
        }
    }
}

private struct BeztraceSetupView: View {
    @Environment(\.dismiss) private var dismiss
    private let companion = ExternalGlyphsCompanion.beztrace

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack {
                Text("Beztrace for Glyphs").font(.title2.bold())
                Spacer()
                Button("Done") { dismiss() }.keyboardShortcut(.cancelAction)
            }
            Text(LocalizedStringKey(companion.versionLabel)).foregroundStyle(.secondary)
            Text(LocalizedStringKey(companion.detail))
            VStack(alignment: .leading, spacing: 8) {
                Text("Requirements").font(.headline)
                Text(LocalizedStringKey(companion.requirements))
                Link("Engine release history", destination: companion.engineRelease)
            }
            VStack(alignment: .leading, spacing: 8) {
                Text("Plugin availability").font(.headline)
                Text("The app bundles engine 0.1.1. The separate plugin is 0.1.0 build 15, independently Developer ID-signed and notarized. Native qualification covers macOS 14.6.1 on Apple Silicon with Glyphs build 4108 and Python 3.14.6; Intel execution is untested. Install All does not install this plugin.")
                Link("Read plugin setup and verification", destination: companion.documentation)
            }
            VStack(alignment: .leading, spacing: 8) {
                Text("Using Beztrace").font(.headline)
                Text("Build 15 workflow: place a PNG or JPEG in the glyph layer, then choose Path → Beztrace…. Position the image on the canvas, choose Trace, adjust the result, then Done. See the source guide for engine verification before installing.")
                Text("The plugin works independently of the MCP server. Trace adds editable paths; Done keeps them without saving the font.")
                    .foregroundStyle(.secondary)
            }
        }
        .font(.callout)
        .fixedSize(horizontal: false, vertical: true)
        .padding(24)
        .frame(width: 540)
    }
}

// Measure each adaptive row before placing cards so shorter content fills its row.
struct SetupCardGrid: Layout {
    private let minimumWidth: CGFloat = 230
    private let spacing: CGFloat = 16

    private func metrics(width: CGFloat?, subviews: Subviews) -> (width: CGFloat, columns: Int, cardWidth: CGFloat, heights: [CGFloat]) {
        let width = max(0, width.flatMap { $0.isFinite ? $0 : nil } ?? minimumWidth)
        let columns = max(1, Int((width + spacing) / (minimumWidth + spacing)))
        let cardWidth = max(0, (width - CGFloat(columns - 1) * spacing) / CGFloat(columns))
        var heights: [CGFloat] = []
        for index in subviews.indices {
            let height = subviews[index].sizeThatFits(ProposedViewSize(width: cardWidth, height: nil)).height
            if index % columns == 0 { heights.append(height) }
            else { heights[heights.count - 1] = max(heights[heights.count - 1], height) }
        }
        return (width, columns, cardWidth, heights)
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let grid = metrics(width: proposal.width, subviews: subviews)
        return CGSize(width: grid.width,
                      height: grid.heights.reduce(0, +) + CGFloat(max(0, grid.heights.count - 1)) * spacing)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let grid = metrics(width: bounds.width, subviews: subviews)
        var y = bounds.minY
        for index in subviews.indices {
            let column = index % grid.columns
            let row = index / grid.columns
            if column == 0 && row > 0 { y += grid.heights[row - 1] + spacing }
            subviews[index].place(at: CGPoint(x: bounds.minX + CGFloat(column) * (grid.cardWidth + spacing), y: y),
                                  anchor: .topLeading,
                                  proposal: ProposedViewSize(width: grid.cardWidth, height: grid.heights[row]))
        }
    }
}

private struct ComponentSetupCard: View {
    let component: DesktopComponent
    let state: SetupItemState
    let disabled: Bool
    let pythonReady: Bool
    let install: () -> Void
    let update: () -> Void
    let remove: () -> Void
    let retry: () -> Void

    var body: some View {
        SetupCard {
            componentPreview
        } title: {
            Text(component.title).font(.headline)
        } detail: {
            Text(LocalizedStringKey(component.detail))
        } status: {
            SetupStatus(state: state)
        } actions: {
            SetupCardActions(state: state, disabled: disabled, canInstall: pythonReady, install: install, update: update, remove: remove, retry: retry)
        } footer: {
            Link("Documentation", destination: component.documentation).font(.caption)
                .accessibilityLabel("\(component.title) documentation")
        }
    }

    @ViewBuilder private var componentPreview: some View {
        if let image = NSImage(named: component.previewAsset) {
            Image(nsImage: image).resizable().interpolation(.high).scaledToFill()
        } else if component.id == "mcp" {
            Image(nsImage: NSApp.applicationIconImage).resizable().interpolation(.high).scaledToFit().padding(12)
        } else {
            Image(systemName: component.symbol).font(.system(size: 36)).foregroundStyle(Color.accentColor)
        }
    }
}

private struct ConnectorSetupCard: View {
    let client: InstallerClientKind
    let state: SetupItemState
    let detected: Bool
    let version: String?
    let guidance: String
    let logoAsset: String
    let disabled: Bool
    let install: () -> Void
    let update: () -> Void
    let remove: () -> Void
    let retry: () -> Void

    var body: some View {
        SetupCard(compact: true) {
            Image(logoAsset)
                .resizable()
                .scaledToFit()
                .frame(width: 32, height: 32)
                .foregroundStyle(Color.accentColor)
        } title: {
            HStack {
                Text(client.displayName).font(.headline)
                Spacer()
                Text(LocalizedStringKey(detected ? "Detected" : "Not detected"))
                    .font(.caption2).foregroundStyle(.secondary)
            }
        } detail: {
            VStack(alignment: .leading, spacing: 4) {
                Text(LocalizedStringKey(guidance))
                if let version { Text("Managed version \(version)").font(.caption) }
            }
        } status: {
            SetupStatus(state: state)
        } actions: {
            SetupCardActions(state: state, disabled: disabled, install: install, update: update, remove: remove, retry: retry)
        } footer: {
            if !detected { Link("Download app", destination: client.downloadURL).font(.caption) }
        }
    }
}

private struct SetupCard<Preview: View, Title: View, Detail: View, Status: View, Actions: View, Footer: View>: View {
    var compact = false
    @ViewBuilder var preview: () -> Preview
    @ViewBuilder var title: () -> Title
    @ViewBuilder var detail: () -> Detail
    @ViewBuilder var status: () -> Status
    @ViewBuilder var actions: () -> Actions
    @ViewBuilder var footer: () -> Footer

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            preview()
                .frame(maxWidth: .infinity)
                .frame(height: compact ? 54 : 92)
                .background(Color.accentColor.opacity(0.06), in: RoundedRectangle(cornerRadius: 10))
                .clipShape(RoundedRectangle(cornerRadius: 10))
                .accessibilityHidden(true)
            title()
            detail().font(.callout).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, minHeight: compact ? 48 : 64, alignment: .topLeading)
            Spacer(minLength: 0)
            status()
            actions()
            footer()
        }
        .padding(16)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 14))
        .overlay(RoundedRectangle(cornerRadius: 14).strokeBorder(Color.primary.opacity(0.08)))
    }
}

private struct SetupStatus: View {
    let state: SetupItemState

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 7) {
                if state.isActive || isQueued { ProgressView().controlSize(.small) }
                Image(systemName: symbol).foregroundStyle(color)
                Text(LocalizedStringKey(state.statusLabel)).font(.caption.weight(.medium)).foregroundStyle(color)
            }
            if let failure = state.failureMessage {
                Text(failure).font(.caption).foregroundStyle(.red).textSelection(.enabled)
            }
        }
    }

    private var isQueued: Bool { if case .queued = state { return true }; return false }
    private var symbol: String {
        switch state {
        case .notInstalled: return "circle"
        case .queued: return "clock"
        case .active: return "arrow.triangle.2.circlepath"
        case .installed, .developmentLinked: return "checkmark.circle.fill"
        case .failed: return "exclamationmark.triangle.fill"
        }
    }
    private var color: Color {
        switch state {
        case .installed: return .green
        case .developmentLinked: return .accentColor
        case .failed: return .red
        default: return .secondary
        }
    }
}

private struct SetupCardActions: View {
    let state: SetupItemState
    let disabled: Bool
    var canInstall = true
    let install: () -> Void
    let update: () -> Void
    let remove: () -> Void
    let retry: () -> Void

    var body: some View {
        HStack {
            switch state {
            case .notInstalled:
                Button("Install", action: install).buttonStyle(.borderedProminent).disabled(disabled || !canInstall)
            case .installed:
                Button("Update", action: update).disabled(disabled || !canInstall)
                Button("Remove", role: .destructive, action: remove).disabled(disabled)
            case .developmentLinked:
                Button("Install bundled version", action: update).disabled(disabled || !canInstall)
                Button("Remove", role: .destructive, action: remove).disabled(disabled)
            case .failed(let operation, _):
                Button("Retry", action: retry).buttonStyle(.borderedProminent).disabled(disabled || (operation != .remove && !canInstall))
            case .queued, .active:
                Text(LocalizedStringKey(state.statusLabel)).font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
        }
    }
}

private struct RemovalTarget: Identifiable {
    enum Kind { case component(String), connector(InstallerClientKind) }
    let id = UUID()
    let title: String
    let message: String
    let kind: Kind

    static func component(_ component: DesktopComponent) -> RemovalTarget {
        .init(title: "Remove \(component.title)?",
              message: "The component will be removed while other components and saved preferences are preserved.",
              kind: .component(component.id))
    }

    static func connector(_ client: InstallerClientKind) -> RemovalTarget {
        .init(title: "Remove \(client.displayName) connection?",
              message: "Only installer-owned Glyphs MCP settings and managed files will be removed. Modified or unowned content is preserved as a conflict.",
              kind: .connector(client))
    }
}

struct TroubleshootingLogView: View {
    @EnvironmentObject private var installer: InstallerViewModel
    @EnvironmentObject private var desktop: DesktopModel
    @State private var source: InstallerLogSource = .all
    @State private var text = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Picker("Source", selection: $source) {
                    ForEach(InstallerLogSource.allCases) { source in
                        Text(LocalizedStringKey(source.displayName)).tag(source)
                    }
                }.frame(width: 220)
                Button("Refresh", action: refresh)
                Spacer()
                Button("Copy Selected") { NSApp.sendAction(#selector(NSText.copy(_:)), to: nil, from: nil) }
                Button("Copy All") { copy(text) }
                Button("Copy Redacted Diagnostic Report") { copy(installer.redactedDiagnostics(serverEvents: desktop.recentMessages)) }
                Button("Reveal Logs in Finder", action: installer.revealLogs)
            }
            TextEditor(text: $text)
                .font(.system(.caption, design: .monospaced))
                .textSelection(.enabled)
                .frame(minWidth: 720, minHeight: 440)
                .overlay(RoundedRectangle(cornerRadius: 6).strokeBorder(Color.primary.opacity(0.12)))
            Text("Diagnostic copies redact common authorization headers, tokens, credentials, and secrets.")
                .font(.caption).foregroundStyle(.secondary)
        }
        .padding(20)
        .onAppear(perform: refresh)
        .onChange(of: source) { _, _ in refresh() }
    }

    private func refresh() {
        text = installer.logText(source: source, serverEvents: desktop.recentMessages)
    }

    private func copy(_ value: String) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(value, forType: .string)
    }
}

/// Keep the native scrollbar and let content reach the adjacent dividers.
struct ScrollEdgeShadowView<Content: View>: View {
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.colorSchemeContrast) private var contrast
    @State private var coordinateSpace = UUID()
    @State private var contentFrame: CGRect = .zero
    @ViewBuilder var content: () -> Content
    private let shadowDepth: CGFloat = 12

    var body: some View {
        GeometryReader { viewport in
            ScrollView {
                content().onGeometryChange(for: CGRect.self) { geometry in
                    geometry.frame(in: .named(coordinateSpace))
                } action: { contentFrame = $0 }
            }
            .coordinateSpace(name: coordinateSpace)
            .overlay(alignment: .top) { edgeShadow(hiddenDistance: -contentFrame.minY, top: true) }
            .overlay(alignment: .bottom) { edgeShadow(hiddenDistance: contentFrame.maxY - viewport.size.height, top: false) }
        }
    }

    private func edgeShadow(hiddenDistance: CGFloat, top: Bool) -> some View {
        let opacity = colorScheme == .dark ? 0.24 : 0.07
        let strength = min(max(hiddenDistance, 0) / shadowDepth, 1)
        return LinearGradient(
            stops: [.init(color: .black.opacity(contrast == .increased ? opacity * 1.6 : opacity), location: 0),
                    .init(color: .black.opacity(opacity * 0.3), location: 0.4),
                    .init(color: .clear, location: 1)],
            startPoint: top ? .top : .bottom,
            endPoint: top ? .bottom : .top
        )
        .frame(height: shadowDepth).opacity(strength).allowsHitTesting(false).accessibilityHidden(true)
    }
}
