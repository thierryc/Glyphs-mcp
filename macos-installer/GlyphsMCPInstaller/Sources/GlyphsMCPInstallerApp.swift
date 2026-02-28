import SwiftUI

@main
struct GlyphsMCPInstallerApp: App {
	@StateObject private var model = InstallerViewModel()

	var body: some Scene {
		WindowGroup {
			ContentView()
				.environmentObject(model)
		}
		.windowStyle(.automatic)
		.windowToolbarStyle(.unifiedCompact)
	}
}
