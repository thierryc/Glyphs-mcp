import SwiftUI

struct DesktopInitializationStatus: View {
    @EnvironmentObject private var installer: InstallerViewModel
    @State private var expanded = false

    var body: some View {
        if installer.initializationStage != nil || installer.initializationError != nil {
            TimelineView(.periodic(from: .now, by: 1)) { context in
                VStack(alignment: .leading, spacing: 8) {
                    HStack(spacing: 12) {
                        if installer.initializationStage != nil { ProgressView().controlSize(.small) }
                        VStack(alignment: .leading, spacing: 3) {
                            Text(installer.initializationError == nil ? "Preparing Glyphs MCP…" : "Setup check needs attention")
                                .fontWeight(.semibold)
                            Text(installer.initializationStage ?? installer.initializationError ?? "")
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
                        Text(installer.initializationDetails.joined(separator: "\n"))
                            .font(.caption).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                    }
                }.padding(16).background(.bar)
            }
        }
    }
}
