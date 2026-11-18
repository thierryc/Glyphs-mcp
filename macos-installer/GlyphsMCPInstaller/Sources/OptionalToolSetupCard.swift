import SwiftUI
import GlyphsMCPInstallerCore

struct BeztraceSetupCard: View {
    @EnvironmentObject private var installer: InstallerViewModel
    let showSetup: () -> Void

    private let companion = ExternalGlyphsCompanion.beztrace
    private var state: OptionalToolState? { installer.optionalStates[companion.id] }

    var body: some View {
        DesktopCatalogCard {
            Image(systemName: "pencil.and.outline").font(.system(size: 36))
                .foregroundStyle(Color.accentColor).accessibilityHidden(true)
        } title: {
            Text(companion.title).font(.headline)
        } detail: {
            Text(LocalizedStringKey(companion.detail))
        } status: {
            DesktopStatus(title: statusTitle,
                          tone: pairInstalled ? .installed : active ? .progress : .neutral,
                          symbol: pairInstalled ? "checkmark.circle.fill" : "circle",
                          spinning: active || (state == nil && installer.optionalDiscoveryError == nil))
        } actions: {
            DesktopActionButton(title: actionTitle, emphasis: installer.running && pairInstalled ? .secondary : .primary,
                                action: performAction)
                .disabled(active)
        } footer: {
            if state?.available == false && state?.installed != true && state?.protectedInstallation != true {
                Text(LocalizedStringKey(state?.availabilityMessage ?? "Beztrace is unavailable on this Mac."))
                    .font(.caption).foregroundStyle(.secondary)
            } else if installer.running && pairInstalled {
                Text("In Glyphs, choose Path → Beztrace…").font(.caption).foregroundStyle(.secondary)
            } else if state?.available == true && state?.installed == false && state?.protectedInstallation == false {
                Text("Includes the plugin and its tracing engine.").font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private var active: Bool { installer.optionalOperation == companion.id }
    private var pairInstalled: Bool {
        guard let state, state.installed, !state.protectedInstallation, !installer.beztraceNeedsRestart(state) else { return false }
        if state.engineConflictPath != nil && state.engineStatus != .custom { return false }
        return state.engineStatus == .managed || state.engineStatus == .custom
    }

    private var statusTitle: String {
        if active { return "Setting up Beztrace…" }
        if installer.optionalErrors[companion.id] != nil || installer.optionalDiscoveryError != nil { return "Beztrace needs attention" }
        guard let state else { return "Checking Beztrace…" }
        if state.protectedInstallation { return "Existing Beztrace found" }
        if state.engineConflictPath != nil && (!pairInstalled || state.updateAvailable == true) { return "Beztrace setup needs attention" }
        if state.updateAvailable == true { return "Beztrace update available" }
        if installer.beztraceNeedsRestart(state) { return "Reopen Glyphs to use Beztrace" }
        if pairInstalled { return installer.running ? "Installed" : "Open Glyphs to use Beztrace" }
        if state.installed { return "Beztrace setup needs attention" }
        return state.available ? "Not installed" : "Unavailable on this Mac"
    }

    private var actionTitle: String {
        if state?.protectedInstallation == true { return "Check existing setup…" }
        if state?.engineConflictPath != nil && (!pairInstalled || state?.updateAvailable == true) { return "Check existing setup…" }
        if state?.updateAvailable == true { return "Update Beztrace…" }
        if pairInstalled { return installer.running ? "Beztrace quick start…" : "Open Glyphs" }
        return "Set up Beztrace…"
    }

    private func performAction() {
        if actionTitle == "Open Glyphs" { installer.openGlyphs() }
        else { showSetup() }
    }
}

struct BeztraceSetupView: View {
    @EnvironmentObject private var installer: InstallerViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var confirmingRemoval = false
    @State private var requestedClose = false

    private let companion = ExternalGlyphsCompanion.beztrace
    private var state: OptionalToolState? { installer.optionalStates[companion.id] }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text("Beztrace for Glyphs").font(.title2.bold()).accessibilityAddTraits(.isHeader)
                Spacer()
                Button("Done") { dismiss() }.keyboardShortcut(.cancelAction)
            }
            Text(LocalizedStringKey(companion.detail))
            nextStep
            if requestedClose && installer.notice.isFailure {
                Text(installer.message).foregroundStyle(.orange).textSelection(.enabled)
            }
            if let error = installer.optionalErrors[companion.id] {
                Text(error).foregroundStyle(.orange).textSelection(.enabled)
            }
            Divider()
            DisclosureGroup("About Beztrace") {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Requires Apple silicon, macOS 26.6.2 or later, and Glyphs 4.1 (build 4107 or later) with Glyphs Python.")
                    Text("Beztrace installs separately from the Glyphs MCP components and works directly in Glyphs.")
                    if let state, let version = state.version, let build = state.build {
                        Text("Detected plugin \(version), build \(build)")
                    }
                    DesktopTextLink("Engine release notes", destination: companion.engineRelease)
                }.foregroundStyle(.secondary).padding(.vertical, 6)
            }
            DesktopTextLink("Beztrace setup and troubleshooting", destination: companion.documentation)
        }
        .font(.callout)
        .padding(24)
        .frame(width: 490)
        .task(id: installer.application?.appURL) {
            if installer.pythonCheck == .notChecked { installer.checkGlyphsPython() }
        }
        .confirmationDialog("Remove Beztrace?", isPresented: $confirmingRemoval, titleVisibility: .visible) {
            Button("Remove Beztrace", role: .destructive) { installer.changeOptionalTool(companion.id, action: "remove") }
        } message: {
            Text("Your fonts, engine files, and personal settings stay in place.")
        }
    }

    @ViewBuilder private var nextStep: some View {
        if installer.optionalOperation == companion.id {
            ProgressView("Setting up Beztrace…").controlSize(.small)
        } else if let error = installer.optionalDiscoveryError {
            Text(error).foregroundStyle(.orange).textSelection(.enabled)
            DesktopActionButton(title: "Check again", action: installer.refreshOptionalTools)
                .disabled(installer.operationsBusy)
        } else if let state {
            if state.protectedInstallation {
                Text("Glyphs already has a copy of Beztrace. Open Glyphs and look for Beztrace in the Path menu. Glyphs MCP leaves this copy in place.")
                DesktopActionButton(title: "Open Glyphs", action: installer.openGlyphs)
                    .disabled(installer.application == nil)
            } else if state.available == false && !state.installed {
                Text(LocalizedStringKey(state.availabilityMessage ?? "Beztrace is unavailable on this Mac."))
            } else if let path = state.engineConflictPath, state.engineStatus != .custom || state.updateAvailable == true {
                Text("Move this engine folder to a backup location, then check again to continue Beztrace setup.")
                Text(path).font(.caption.monospaced()).textSelection(.enabled)
                DesktopActionButton(title: "Check again", action: installer.refreshOptionalTools)
                    .disabled(installer.operationsBusy)
                if state.installed { removeButton }
            } else if state.updateAvailable == true || !state.installed || state.engineStatus == .repair {
                installStep(state)
            } else if state.engineStatus == .invalidSettings || state.engineStatus == .missingCustom || state.engineStatus == .manual {
                engineHelp(state)
                removeButton
            } else {
                quickStart(state)
                removeButton
            }
        } else {
            ProgressView("Checking Beztrace…").controlSize(.small)
        }
    }

    @ViewBuilder private func installStep(_ state: OptionalToolState) -> some View {
        Text("Setup installs the Glyphs plugin and connects it to the included Beztrace engine.")
        if installer.application == nil || !installer.glyphsSupportsBeztrace {
            Text("Install Glyphs 4.1 (build 4107 or later), open it once, then return here.")
            DesktopActionButton(title: "Check again") { installer.refresh() }
                .disabled(installer.operationsBusy)
        } else if installer.checkingPython {
            ProgressView("Checking Glyphs Python…").controlSize(.small)
        } else if !installer.pythonReady {
            Text("Install Python from the Modules tab in Glyphs’ Plugin Manager. Reopen Glyphs, then check again.")
            DesktopActionRow {
                DesktopActionButton(title: "Open Python in Plugin Manager", action: installer.openPythonInPluginManager)
                DesktopActionButton(title: "Check again", action: installer.checkGlyphsPython)
            }.disabled(installer.operationsBusy)
        } else if installer.running {
            closeGlyphs
        } else {
            let title = state.updateAvailable == true ? "Update Beztrace" : state.installed ? "Repair Beztrace" : "Install Beztrace"
            DesktopActionButton(title: title, emphasis: .primary) {
                installer.changeOptionalTool(companion.id, action: state.installed ? "update" : "install")
            }.disabled(!installer.canChangeOptionalTool(companion.id) || !state.available)
        }
    }

    @ViewBuilder private var closeGlyphs: some View {
        Text("Close Glyphs to continue. Glyphs will prompt you to save any open fonts.")
        DesktopActionButton(title: "Quit Glyphs", emphasis: .primary) {
            requestedClose = true
            installer.quitGlyphs()
        }.disabled(installer.operationsBusy)
    }

    @ViewBuilder private func quickStart(_ state: OptionalToolState) -> some View {
        if installer.beztraceNeedsRestart(state) {
            closeGlyphs
        } else {
            Text("Open a glyph in Edit view. Choose Path → Beztrace…, select an image and click Update Preview.")
            if state.engineStatus == .custom {
                Text("Beztrace is set to use the engine you selected previously.").foregroundStyle(.secondary)
            }
            DesktopActionButton(title: "Open Glyphs", emphasis: .primary, action: installer.openGlyphs)
                .disabled(installer.application == nil)
        }
    }

    @ViewBuilder private func engineHelp(_ state: OptionalToolState) -> some View {
        if state.engineStatus == .missingCustom {
            Text("The engine previously selected in Beztrace is missing. See troubleshooting to restore it or switch to the included engine.")
        } else if state.engineStatus == .invalidSettings {
            Text("Beztrace could not read its engine settings. See troubleshooting for recovery steps.")
        } else {
            Text("This older Beztrace installation requires manual engine selection. Update Glyphs MCP to get a working plugin and engine pair.")
        }
    }

    @ViewBuilder private var removeButton: some View {
        Button("Remove Beztrace…") { confirmingRemoval = true }
            .buttonStyle(.link).disabled(!installer.canChangeOptionalTool(companion.id))
    }
}

private extension OptionalToolState {
    var availabilityMessage: String? {
        if let reason, reason.hasPrefix("This optional distribution requires macOS ") {
            let minimum = reason.dropFirst("This optional distribution requires macOS ".count).dropLast(" or later".count)
            return AppLocalization.format("Requires macOS %@ or later.", String(minimum))
        }
        if reason == "This optional distribution is not qualified for x86_64" {
            return "Available on Apple Silicon only."
        }
        return nil
    }
}
