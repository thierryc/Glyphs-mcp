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
            Text(detail)
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
            if state?.available != true {
                Text(state?.reason ?? "This optional distribution awaits release qualification.")
                    .font(.caption).foregroundStyle(.secondary)
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
