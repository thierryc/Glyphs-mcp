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
		.commands {
			CommandGroup(after: .toolbar) {
				Toggle(
					"Advanced Mode",
					isOn: Binding(
						get: { model.isAdvancedModeEnabled },
						set: { model.setAdvancedModeEnabled($0) }
					)
				)
			}
		}
	}
}
