import SwiftUI
import GlyphsMCPInstallerCore

@main
struct GlyphsMCPInstallerApp: App {
    @NSApplicationDelegateAdaptor(DesktopAppDelegate.self) private var delegate
    var body: some Scene {
        Settings { DesktopSettings(updates: delegate.updates).environmentObject(delegate.desktop) }
            .commands {
                CommandGroup(replacing: .appInfo) {
                    Button("About Glyphs MCP") { delegate.showWelcome() }
                }
                CommandGroup(after: .appInfo) {
                    Button("Check for Updates…") { delegate.updates.check() }
                }
                CommandGroup(replacing: .newItem) {
                    Button("Open Glyphs MCP") { delegate.showDashboard() }.keyboardShortcut("0")
                }
                CommandGroup(replacing: .help) {
                    Button("Glyphs MCP Documentation") { NSWorkspace.shared.open(DesktopIdentity.documentation) }
                    Button("Report an Issue") { NSWorkspace.shared.open(DesktopIdentity.issues) }
                    Button("Welcome & Support") { delegate.showWelcome() }
                }
            }
    }
}
