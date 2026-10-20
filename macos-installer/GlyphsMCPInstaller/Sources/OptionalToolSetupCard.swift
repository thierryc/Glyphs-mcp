import SwiftUI

struct OptionalToolSetupCard: View {
    let id: String
    let title: String
    let symbol: String
    let detail: String
    let details: () -> Void
    @EnvironmentObject private var installer: InstallerViewModel
    @State private var removing = false
    @State private var lastAction = "install"

    private var progressTitle: String {
        switch lastAction {
        case "remove": return "Uninstalling…"
        case "update": return "Updating…"
        default: return "Installing…"
        }
    }

    var body: some View {
        let state = installer.optionalStates[id]
        let active = installer.optionalOperation == id
        DesktopCatalogCard {
            Image(systemName: symbol).font(.system(size: 36)).foregroundStyle(Color.accentColor)
        } title: {
            Text(title).font(.headline)
        } detail: {
            Text(LocalizedStringKey(detail))
        } status: {
            DesktopStatus(title: active ? progressTitle : state?.label ?? "Checking optional setup…",
                tone: active ? (lastAction == "remove" ? .neutral : .progress) : state?.installed == true ? .installed : .neutral,
                symbol: state?.installed == true ? "checkmark.circle.fill" : "circle", spinning: active || state == nil)
            if let error = installer.optionalErrors[id] {
                Text(error).font(.caption).foregroundStyle(.orange).textSelection(.enabled)
            }
            if let error = installer.optionalDiscoveryError {
                Text(error).font(.caption).foregroundStyle(.orange).textSelection(.enabled)
            }
        } actions: {
            DesktopActionRow {
                if installer.optionalDiscoveryError != nil {
                    DesktopActionButton(title: "Retry", symbol: "arrow.clockwise", emphasis: .primary) { installer.refreshOptionalTools() }
                        .disabled(installer.operationsBusy)
                } else if installer.optionalErrors[id] != nil {
                    DesktopActionButton(title: "Retry", symbol: "arrow.clockwise", emphasis: .primary) { installer.changeOptionalTool(id, action: lastAction) }
                        .disabled(!installer.canChangeOptionalTool(id))
                } else {
                    DesktopActionButton(title: state?.installed == true ? "Update" : "Install",
                        symbol: state?.installed == true ? "arrow.clockwise" : "arrow.down.to.line",
                        emphasis: state?.installed == true ? .secondary : .primary) {
                        lastAction = state?.installed == true ? "update" : "install"
                        installer.changeOptionalTool(id, action: lastAction)
                    }.disabled(state?.available != true || !installer.canChangeOptionalTool(id))
                }
                if state?.installed == true {
                    DesktopActionButton(title: "Uninstall") { removing = true }
                        .disabled(!installer.canChangeOptionalTool(id))
                }
            }
        } footer: {
            if state?.protectedInstallation == true {
                Text("Setup preserves this separate or modified installation. See Details before changing it.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if state?.available != true {
                Group {
                    if let reason = state?.reason,
                       reason.hasPrefix("This optional distribution requires macOS "), reason.hasSuffix(" or later") {
                        let minimum = String(reason.dropFirst("This optional distribution requires macOS ".count).dropLast(" or later".count))
                        Text("Requires macOS \(minimum) or later.")
                    } else if state?.reason == "This optional distribution is not qualified for x86_64" {
                        Text("Available on Apple Silicon only.")
                    } else {
                        Text(state?.reason ?? "This optional distribution awaits release qualification.")
                    }
                }.font(.caption).foregroundStyle(.secondary)
            }
            Button("Details", action: details).buttonStyle(.link).font(.caption)
        }
        .confirmationDialog("Uninstall \(title)?", isPresented: $removing, titleVisibility: .visible) {
            Button("Uninstall", role: .destructive) {
                lastAction = "remove"
                installer.changeOptionalTool(id, action: "remove")
            }
        } message: {
            Text("Remove the managed installation. Fonts, user settings and shared Beztrace engines are preserved.")
        }
    }
}
