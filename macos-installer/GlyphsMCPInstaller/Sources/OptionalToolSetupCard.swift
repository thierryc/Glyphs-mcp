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

    var body: some View {
        let state = installer.optionalStates[id]
        let active = installer.optionalOperation == id
        SetupCard {
            Image(systemName: symbol).font(.system(size: 36)).foregroundStyle(Color.accentColor)
        } title: {
            Text(title).font(.headline)
        } detail: {
            Text(detail)
        } status: {
            if active { Label("Working…", systemImage: "hourglass") }
            else { Text(state?.label ?? "Checking optional setup…").font(.caption).foregroundStyle(.secondary) }
            if let error = installer.optionalErrors[id] {
                Text(error).font(.caption).foregroundStyle(.red).textSelection(.enabled)
            }
            if let error = installer.optionalDiscoveryError {
                Text(error).font(.caption).foregroundStyle(.red).textSelection(.enabled)
            }
        } actions: {
            HStack {
                if installer.optionalDiscoveryError != nil {
                    Button("Retry") { installer.refreshOptionalTools() }
                        .disabled(installer.operationsBusy)
                } else if installer.optionalErrors[id] != nil {
                    Button("Retry") { installer.changeOptionalTool(id, action: lastAction) }
                        .disabled(!installer.canChangeOptionalTool(id))
                } else {
                    Button(state?.installed == true ? "Update" : "Install") {
                        lastAction = state?.installed == true ? "update" : "install"
                        installer.changeOptionalTool(id, action: lastAction)
                    }.disabled(state?.available != true || !installer.canChangeOptionalTool(id))
                }
                if state?.installed == true {
                    Button("Remove", role: .destructive) { removing = true }
                        .disabled(!installer.canChangeOptionalTool(id))
                }
                Spacer()
            }
        } footer: {
            if state?.available != true {
                Text(state?.reason ?? "This optional distribution awaits release qualification.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Button("Setup details…", action: details).font(.caption)
        }
        .confirmationDialog("Remove \(title)?", isPresented: $removing, titleVisibility: .visible) {
            Button("Remove", role: .destructive) {
                lastAction = "remove"
                installer.changeOptionalTool(id, action: "remove")
            }
        } message: {
            Text("Remove the managed installation. Fonts, user settings and shared Beztrace engines are preserved.")
        }
    }
}
