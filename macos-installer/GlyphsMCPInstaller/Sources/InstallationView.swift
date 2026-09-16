import AppKit
import SwiftUI
import GlyphsMCPInstallerCore

struct InstallationView: View {
    @EnvironmentObject private var model: InstallerViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header.padding(.bottom, 22)
            Divider()
            ScrollEdgeShadowView {
                VStack(alignment: .leading, spacing: 20) {
                    switch model.stage {
                    case .choose: choices
                    case .install:
                        ProgressView().frame(maxWidth: .infinity).padding(.top, 44)
                        Text(model.message).frame(maxWidth: .infinity).padding(.bottom, 44)
                    case .ready:
                        Label(model.completionTitle, systemImage: model.notice.isFailure ? "exclamationmark.triangle" : "checkmark.circle").font(.title2)
                        Text(model.message).foregroundStyle(model.notice.isFailure ? Color.red : Color.primary)
                        if model.selectedVersion == .v3 || !model.installed.isEmpty {
                            if model.selectedVersion == .v3 {
                                Text("In Glyphs, open Edit → Glyphs MCP Server to manage the server.").foregroundStyle(.secondary)
                            } else {
                                if model.installed.contains("mcp") {
                                    Text("Start or stop the MCP server in Overview. Change its port in Settings.").foregroundStyle(.secondary)
                                }
                                if !model.inspectorInstructions.isEmpty { Text(model.inspectorInstructions).foregroundStyle(.secondary) }
                            }
                            Button("Open Glyphs", action: model.openGlyphs).buttonStyle(.borderedProminent)
                        }
                        Button("Manage Components") { model.stage = .choose; model.notice = .none }
                    }
                    if model.stage == .choose && !model.message.isEmpty {
                        if model.notice.isFailure {
                            Label(model.message, systemImage: "exclamationmark.circle").foregroundStyle(.red).textSelection(.enabled)
                        } else {
                            Text(model.message).foregroundStyle(.secondary).textSelection(.enabled)
                        }
                    }
                    if !model.skillConflicts.isEmpty {
                        Text(model.skillConflicts.map(\.path).joined(separator: "\n")).font(.caption).textSelection(.enabled)
                        Button("Replace preserved skills (backup)", action: model.replacePreservedSkills).disabled(model.busy)
                    }
                    DisclosureGroup("Troubleshooting", isExpanded: $model.troubleshooting) {
                        VStack(alignment: .leading, spacing: 10) {
                            if let receipt = model.receiptURL {
                                Button("Show Installation Receipt") { NSWorkspace.shared.activateFileViewerSelecting([receipt]) }
                            }
                            Text(model.log.isEmpty ? "No diagnostic messages." : model.log)
                                .font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                            Button("Detect Applications Again", action: model.refresh).disabled(model.busy)
                        }.padding(.top, 8)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.vertical, 22)
            }
            Divider()
            HStack {
                Link("Documentation", destination: DesktopIdentity.documentation)
                Text("·").foregroundStyle(.secondary)
                Link("Report an Issue", destination: URL(string: "https://github.com/thierryc/Glyphs-mcp/issues")!)
                Spacer()
                if model.stage == .choose {
                    Button(model.installButtonTitle, action: model.install).buttonStyle(.borderedProminent)
                        .disabled(!model.canInstall).keyboardShortcut(.defaultAction)
                }
            }
            .padding(.top, 22)
        }
        .padding(28)
        .frame(minWidth: 560, idealWidth: 610, minHeight: 600, idealHeight: 660)
        .onChange(of: model.selectedVersion) { _, _ in model.refreshRunning() }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 22) {
            VStack(alignment: .leading, spacing: 5) {
                Text("Components").font(.largeTitle.bold())
                Text(model.versionLabel).font(.caption).foregroundStyle(.secondary)
            }
            HStack(spacing: 12) {
                ForEach(InstallerViewModel.Stage.allCases, id: \.self) { step in
                    Text(step.rawValue).font(.subheadline.weight(model.stage == step ? .semibold : .regular))
                        .foregroundStyle(model.stage == step ? Color.accentColor : .secondary)
                    if step != .ready { Image(systemName: "chevron.right").font(.caption).foregroundStyle(.tertiary) }
                }
                Spacer()
                if model.running {
                    Button("Quit Glyphs", action: model.quitGlyphs)
                        .buttonStyle(.borderedProminent).tint(.orange)
                        .disabled(model.busy)
                        .help("Close Glyphs using its normal save prompt before changing components.")
                }
            }
        }
    }

    private var choices: some View {
        VStack(alignment: .leading, spacing: 20) {
            if model.applications.isEmpty {
                Text("Install Glyphs first, then refresh the detected applications.")
            } else {
                Picker("Glyphs version", selection: $model.selectedVersion) {
                    ForEach(model.applications) { app in Text(app.displayName).tag(app.majorVersion) }
                }
                if model.running && model.notice != .waitingForGlyphs {
                    Text("Quit Glyphs before changing components. You can save unsaved fonts when prompted.")
                        .font(.callout).foregroundStyle(.secondary)
                }
                if model.selectedVersion == .v4 {
                    Text("Select the components to keep installed. Applying changes installs the selected versions and removes unchecked installed components.")
                        .font(.callout).foregroundStyle(.secondary)
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 210), spacing: 16)], spacing: 16) {
                        ForEach(DesktopComponent.all) { component in
                            ComponentCard(component: component) {
                                Toggle(component.title, isOn: model.componentBinding(component.id))
                                    .toggleStyle(.checkbox).font(.headline)
                            } action: {
                                Text(model.componentPlan.action(for: component.id))
                                    .font(.callout.weight(.medium))
                                    .foregroundStyle(model.componentPlan.removals.contains(component.id) ? Color.red : Color.secondary)
                            }
                        }
                    }.disabled(model.busy)
                } else {
                    Text("Glyphs 3 uses Glyphs MCP 1.11.0 and its existing Python setup.")
                        .foregroundStyle(.secondary)
                }
                if !model.detectedClients.isEmpty {
                    VStack(alignment: .leading, spacing: 10) {
                        Text("AI connections (optional)").fontWeight(.medium)
                        if !model.canConnectClients { Text("Install Glyphs MCP to connect an AI assistant.").foregroundStyle(.secondary) }
                        ForEach(model.detectedClients, id: \.self) { client in
                            Toggle(client.displayName,
                                   isOn: model.clientBinding(client)).disabled(!model.canConnectClients)
                        }
                    }
                }
            }
        }
    }
}

/// Both surfaces use the same card and image slot. A bundled preview asset can
/// replace the native illustration without changing installation behavior.
struct ComponentCard<Selection: View, Action: View>: View {
    let component: DesktopComponent
    @ViewBuilder var selection: () -> Selection
    @ViewBuilder var action: () -> Action

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            preview.frame(maxWidth: .infinity).frame(height: 100)
                .background(Color.accentColor.opacity(0.06), in: RoundedRectangle(cornerRadius: 10))
                .clipShape(RoundedRectangle(cornerRadius: 10)).accessibilityHidden(true)
            selection()
            Text(component.detail).font(.callout).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, minHeight: 58, alignment: .topLeading)
            action()
            Link("Documentation", destination: component.documentation).font(.caption)
                .accessibilityLabel("\(component.title) documentation")
        }.padding(16).frame(maxWidth: .infinity, alignment: .topLeading)
            .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 14))
            .overlay(RoundedRectangle(cornerRadius: 14).strokeBorder(Color.primary.opacity(0.08)))
    }

    @ViewBuilder private var preview: some View {
        if let image = NSImage(named: component.previewAsset) {
            Image(nsImage: image).resizable().scaledToFill()
        } else if component.id == "mcp" {
            Image(nsImage: NSApp.applicationIconImage).resizable().scaledToFit().padding(12)
        } else {
            Image(systemName: component.symbol).font(.system(size: 38)).foregroundStyle(Color.accentColor)
        }
    }
}

/// Keep the native scrollbar and let content reach the adjacent dividers.
/// Geometry observation also updates when content expands or the window resizes.
private struct ScrollEdgeShadowView<Content: View>: View {
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.colorSchemeContrast) private var contrast
    @State private var coordinateSpace = UUID()
    @State private var contentFrame: CGRect = .zero
    @ViewBuilder var content: () -> Content

    private let shadowDepth: CGFloat = 12

    var body: some View {
        GeometryReader { viewport in
            ScrollView {
                content()
                    .onGeometryChange(for: CGRect.self) { geometry in
                        geometry.frame(in: .named(coordinateSpace))
                    } action: { contentFrame = $0 }
            }
            .coordinateSpace(name: coordinateSpace)
            .overlay(alignment: .top) {
                edgeShadow(hiddenDistance: -contentFrame.minY, top: true)
            }
            .overlay(alignment: .bottom) {
                edgeShadow(hiddenDistance: contentFrame.maxY - viewport.size.height, top: false)
            }
        }
    }

    private func edgeShadow(hiddenDistance: CGFloat, top: Bool) -> some View {
        let opacity = colorScheme == .dark ? 0.24 : 0.07
        let strength = min(max(hiddenDistance, 0) / shadowDepth, 1)
        return LinearGradient(
            stops: [
                .init(color: .black.opacity(contrast == .increased ? opacity * 1.6 : opacity), location: 0),
                .init(color: .black.opacity(opacity * 0.3), location: 0.4),
                .init(color: .clear, location: 1)
            ],
            startPoint: top ? .top : .bottom,
            endPoint: top ? .bottom : .top
        )
        .frame(height: shadowDepth)
        .opacity(strength)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}
