import AppKit

enum GlyphsRuntime {
	static let bundleID = "com.GeorgSeifert.Glyphs3"
	private static let otherBundleIDs = [
		"com.GeorgSeifert.Glyphs3Beta",
		"com.GeorgSeifert.GlyphsBeta",
	]

	static func isGlyphsRunning() -> Bool {
		!glyphsRunningApps().isEmpty
	}

	static func quitGlyphsWithConfirmation() {
		let targets = glyphsRunningApps()
		guard !targets.isEmpty else { return }

		let alert = NSAlert()
		alert.messageText = "Quit Glyphs?"
		alert.informativeText = "Glyphs appears to be running. Quitting Glyphs may be required to load the updated plug‑in.\n\nQuit Glyphs now?"
		alert.addButton(withTitle: "Quit Glyphs")
		alert.addButton(withTitle: "Cancel")
		guard alert.runModal() == .alertFirstButtonReturn else { return }

		for app in targets {
			_ = app.terminate()
		}
	}

	private static func glyphsRunningApps() -> [NSRunningApplication] {
		let selfBundleID = Bundle.main.bundleIdentifier
		let selfPID = ProcessInfo.processInfo.processIdentifier

		// Prefer bundle identifiers (most reliable).
		var apps: [NSRunningApplication] = []
		for id in [bundleID] + otherBundleIDs {
			apps.append(contentsOf: NSRunningApplication.runningApplications(withBundleIdentifier: id))
		}
		apps = apps.filter { $0.bundleIdentifier != selfBundleID && $0.processIdentifier != selfPID }
		if !apps.isEmpty {
			return apps
		}

		// Fallback: match by bundle identifier prefix / exact app name.
		// IMPORTANT: avoid matching this installer (localizedName starts with "Glyphs").
		let names = Set(["glyphs", "glyphs 3"])
		return NSWorkspace.shared.runningApplications.filter { app in
			if app.processIdentifier == selfPID { return false }
			if let selfBundleID, app.bundleIdentifier == selfBundleID { return false }

			let bundleID = (app.bundleIdentifier ?? "").lowercased()
			if bundleID.hasPrefix("com.georgseifert.glyphs") { return true }

			let name = (app.localizedName ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
			return names.contains(name)
		}
	}
}
