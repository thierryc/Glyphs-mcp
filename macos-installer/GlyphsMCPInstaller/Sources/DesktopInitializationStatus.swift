import SwiftUI

struct DesktopInitializationStatus: View {
    @EnvironmentObject private var installer: InstallerViewModel
    @State private var expanded = false

    var body: some View {
        if !installer.checkingPython && installer.pythonSetupError == nil &&
            (installer.initializationStage != nil || installer.initializationError != nil) {
            TimelineView(.periodic(from: .now, by: 1)) { context in
                VStack(alignment: .leading, spacing: 8) {
                    HStack(spacing: 12) {
                        if installer.initializationStage != nil { ProgressView().controlSize(.small) }
                        VStack(alignment: .leading, spacing: 3) {
                            Text(installer.initializationError == nil ? "Preparing Glyphs MCP…" : "Setup check needs attention")
                                .fontWeight(.semibold)
                            Text(installer.initializationStage ?? "")
                                .font(.callout).textSelection(.enabled)
                            if installer.initializationStage != nil && context.date.timeIntervalSince(installer.initializationStartedAt) >= 5 {
                                Text("This check is still running. You can continue browsing while it finishes.")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                        }
                        Spacer()
                        if installer.initializationError != nil && installer.initializationStage == nil {
                            Button("Retry") { installer.refresh(resetFailures: true) }
                        }
                        Button("View Logs") { installer.showTroubleshootingLogs?() }
                    }
                    DisclosureGroup("Initialization details", isExpanded: $expanded) {
                        if let error = installer.initializationError {
                            Text(error).font(.caption).textSelection(.enabled)
                        }
                        Text(installer.initializationDetails.joined(separator: "\n"))
                            .font(.caption).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                    }
                }.padding(16).modifier(DesktopCardSurface())
            }
        }
    }
}

struct DesktopPythonSetup: View {
    @EnvironmentObject private var installer: InstallerViewModel

    private var statusTitle: String {
        switch installer.pythonCheck {
        case .notChecked: return "Set up Python in Glyphs"
        case .checking: return "Checking Glyphs Python…"
        case .ready: return "Glyphs Python is ready"
        case .failed: return "Python check needs attention"
        case .skipped: return "Python check skipped"
        }
    }

    private var tone: DesktopStatus.Tone {
        if installer.checkingPython { return .progress }
        if installer.pythonReady { return .installed }
        if installer.pythonSetupError != nil { return .attention }
        return .neutral
    }

    var body: some View {
        DesktopCard {
            VStack(alignment: .leading, spacing: 12) {
                if installer.hasMultipleGlyphsCopies {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Glyphs 4 application").font(.headline)
                        Picker("Glyphs 4 application", selection: Binding(
                            get: { installer.application?.appURL.path ?? "" },
                            set: { installer.selectGlyphsApplication($0) }
                        )) {
                            ForEach(installer.applications, id: \.appURL) { copy in
                                Text(verbatim: "\(copy.displayName) · \(copy.shortVersion ?? "") · \(copy.appURL.path)")
                                    .tag(copy.appURL.path)
                            }
                        }
                        .pickerStyle(.menu).labelsHidden()
                        .disabled(!installer.canSelectGlyphsCopy)
                        Text("Python checks and setup use the selected copy.")
                            .font(.caption).foregroundStyle(.secondary)
                        Text("Components are shared by Glyphs 4 copies on this Mac.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Divider()
                }
                HStack(alignment: .firstTextBaseline) {
                    Text("Glyphs Python").font(.headline)
                    Spacer()
                    if let version = installer.pythonVersion ?? installer.pythonDetection?.nativeVersion {
                        Text("Python \(version)").font(.caption).foregroundStyle(.secondary)
                    }
                }
                if let copy = installer.application {
                    Text(verbatim: "\(copy.displayName) · \(copy.shortVersion ?? "") · \(copy.appURL.path)")
                        .font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                }
                DesktopStatus(title: statusTitle, tone: tone,
                    symbol: installer.pythonReady ? "checkmark.circle" : "exclamationmark.triangle",
                    spinning: installer.checkingPython)
                if let detection = installer.pythonDetection, let path = detection.path {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(LocalizedStringKey(detection.isGlyphsModule ? "Glyphs Python module" : "Selected Python"))
                            .font(.callout)
                        Text(verbatim: path).font(.caption).foregroundStyle(.secondary)
                            .textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
                    }
                }
                if installer.checkingPython {
                    if let stage = installer.initializationStage {
                        Text(LocalizedStringKey(stage)).font(.caption).foregroundStyle(.secondary)
                    }
                } else if installer.pythonCheck.isSkipped {
                    Text("Installation is enabled for this session. Python features may need setup afterward.")
                        .font(.callout).foregroundStyle(.secondary)
                } else if installer.pythonCheck.canSkip {
                    Text("The check could not confirm Python. If the Glyphs Python module is installed and working, you can allow installation anyway.")
                        .font(.callout).foregroundStyle(.secondary)
                } else if !installer.pythonReady {
                    Text("Install Python from Window → Plugin Manager → Modules in Glyphs. Relaunch Glyphs, select the Python marked ‘(Glyphs)’ in Settings → Addons, then relaunch again.")
                        .font(.callout).foregroundStyle(.secondary)
                }
                if !installer.pythonReady {
                    DisclosureGroup("Check details") {
                        VStack(alignment: .leading, spacing: 8) {
                            if let error = installer.pythonSetupError {
                                Text(error).textSelection(.enabled)
                            }
                            Text(installer.initializationDetails.joined(separator: "\n"))
                                .textSelection(.enabled)
                            Button("View Logs") { installer.showTroubleshootingLogs?() }
                        }.font(.caption).frame(maxWidth: .infinity, alignment: .leading)
                    }.font(.caption).foregroundStyle(.secondary)
                }
                if !installer.checkingPython {
                    ViewThatFits(in: .horizontal) {
                        HStack(spacing: 10) { actions }
                        VStack(alignment: .leading, spacing: 10) { actions }
                    }.disabled(installer.operationsBusy)
                }
            }
        }
    }

    @ViewBuilder private var actions: some View {
        if installer.pythonCheck.canSkip {
            DesktopActionButton(title: "Allow installation anyway", action: installer.allowInstallationWithoutPythonCheck)
        }
        DesktopActionButton(title: "Check again", action: installer.checkGlyphsPython)
        if !installer.pythonReady {
            DesktopActionButton(title: "Open Python in Plugin Manager", action: installer.openPythonInPluginManager)
        }
    }
}
