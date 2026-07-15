import AppKit
import Foundation
import GlyphsMCPInstallerCore

enum GlyphsRuntime {
	private static let bundleIDs = GlyphsMajorVersion.allCases.flatMap(\.bundleIdentifiers) + [
		"com.GeorgSeifert.GlyphsBeta",
	]

	static func runningVersions() -> Set<GlyphsMajorVersion> {
		Set(glyphsRunningApps().compactMap { majorVersion(for: $0) })
	}

	static func isGlyphsRunning() -> Bool {
		!glyphsRunningApps().isEmpty
	}

	static func isGlyphsRunning(versions: Set<GlyphsMajorVersion>) -> Bool {
		!glyphsRunningApps(versions: versions).isEmpty
	}

	static func quitGlyphsWithConfirmation() {
		quitGlyphsWithConfirmation(versions: Set(GlyphsMajorVersion.allCases))
	}

	static func quitGlyphsWithConfirmation(versions: Set<GlyphsMajorVersion>, reason: String? = nil) {
		let targets = glyphsRunningApps(versions: versions)
		guard !targets.isEmpty else { return }

		let names = targets.compactMap { majorVersion(for: $0)?.displayName }.sorted()
		let targetLabel = Array(Set(names)).sorted().joined(separator: " and ")
		let alert = NSAlert()
		alert.messageText = NSLocalizedString("Quit Glyphs?", comment: "Quit Glyphs confirmation title")
		if let reason {
			alert.informativeText = String(
				format: NSLocalizedString("%@ %@\n\nQuit now?", comment: "Quit selected Glyphs versions with action-specific reason"),
				targetLabel.isEmpty ? "Glyphs" : targetLabel,
				reason
			)
		} else {
			alert.informativeText = String(
				format: NSLocalizedString(
					"%@ must be closed so the plug-in can update cleanly.\n\nQuit now?",
					comment: "Quit selected Glyphs versions confirmation body"
				),
				targetLabel.isEmpty ? "Glyphs" : targetLabel
			)
		}
		alert.addButton(withTitle: NSLocalizedString("Quit Glyphs", comment: "Quit Glyphs button"))
		alert.addButton(withTitle: NSLocalizedString("Cancel", comment: "Cancel button"))
		guard alert.runModal() == .alertFirstButtonReturn else { return }

		for app in targets {
			_ = app.terminate()
		}
	}

	private static func glyphsRunningApps(versions: Set<GlyphsMajorVersion>? = nil) -> [NSRunningApplication] {
		let selfBundleID = Bundle.main.bundleIdentifier
		let selfPID = ProcessInfo.processInfo.processIdentifier
		var byPID: [pid_t: NSRunningApplication] = [:]

		for bundleID in bundleIDs {
			for app in NSRunningApplication.runningApplications(withBundleIdentifier: bundleID) {
				byPID[app.processIdentifier] = app
			}
		}
		for app in NSWorkspace.shared.runningApplications {
			if let bundleID = app.bundleIdentifier?.lowercased(), bundleID.hasPrefix("com.georgseifert.glyphs") {
				byPID[app.processIdentifier] = app
				continue
			}
			let name = (app.localizedName ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
			if ["glyphs", "glyphs 3", "glyphs 4", "glyphs3", "glyphs4"].contains(name) {
				byPID[app.processIdentifier] = app
			}
		}

		return byPID.values.filter { app in
			if app.processIdentifier == selfPID { return false }
			if let selfBundleID, app.bundleIdentifier == selfBundleID { return false }
			guard let version = majorVersion(for: app) else { return false }
			return versions?.contains(version) ?? true
		}
	}

	private static func majorVersion(for app: NSRunningApplication) -> GlyphsMajorVersion? {
		let shortVersion = app.bundleURL
			.flatMap(Bundle.init(url:))?
			.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
		return GlyphsApplicationDetector.classify(
			bundleIdentifier: app.bundleIdentifier,
			shortVersion: shortVersion,
			displayName: app.localizedName,
			fileName: app.bundleURL?.deletingPathExtension().lastPathComponent
		)
	}
}
