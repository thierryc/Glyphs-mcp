import AppKit
import Foundation
import GlyphsMCPInstallerCore

enum GlyphsRuntime {
	private static let bundleIDs = GlyphsRunningProcessDetector.supportedBundleIdentifiers
	private static let bundleIDSet = Set(bundleIDs)

	static func runningVersions() -> Set<GlyphsMajorVersion> {
		Set(glyphsRunningApps().compactMap { majorVersion(for: $0) })
	}

	static func isGlyphsRunning() -> Bool {
		!glyphsRunningApps().isEmpty
	}

	static func isGlyphsRunning(versions: Set<GlyphsMajorVersion>) -> Bool {
		!glyphsRunningApps(versions: versions).isEmpty
	}

	enum QuitError: LocalizedError {
		case processChanged, cancelled, automationDenied, timedOut, requestFailed(Int)

		var errorDescription: String? {
			switch self {
			case .processChanged:
				return NSLocalizedString("A new copy of Glyphs 4 opened. Review the running copies before continuing.", comment: "Quit consent expired")
			case .cancelled:
				return NSLocalizedString("The quit request was cancelled in Glyphs 4.", comment: "Glyphs quit cancelled")
			case .automationDenied:
				return NSLocalizedString("Allow Glyphs MCP to control Glyphs 4 in System Settings → Privacy & Security → Automation, or save and quit Glyphs 4 yourself.", comment: "Apple Events permission")
			case .timedOut:
				return NSLocalizedString("Glyphs 4 is still open. Check for a save dialog and finish quitting before continuing.", comment: "Timed out waiting for Glyphs")
			case .requestFailed(let code):
				return String(format: NSLocalizedString("Glyphs 4 could not complete the quit request (error %ld). Save your work and quit Glyphs 4 before continuing.", comment: "Glyphs quit failure"), code)
			}
		}
	}

	static func runningGlyphs4PIDs() -> Set<pid_t> {
		Set(glyphsRunningApps(versions: [.v4]).map(\.processIdentifier))
	}

	/// Consent applies only to the processes displayed when the user chose a quit action.
	@MainActor
	static func quitGlyphs4(confirmedPIDs: Set<pid_t>, saveChanges: Bool) async throws {
		let targets = glyphsRunningApps(versions: [.v4])
		guard targets.allSatisfy({ confirmedPIDs.contains($0.processIdentifier) }) else {
			throw QuitError.processChanged
		}
		let deadline = ContinuousClock.now + .seconds(120)
		for target in targets {
			try Task.checkCancellation()
			let running = runningGlyphs4PIDs()
			guard running.isSubset(of: confirmedPIDs) else { throw QuitError.processChanged }
			let pid = target.processIdentifier
			guard running.contains(pid), !target.isTerminated else { continue }
			if saveChanges {
				// Keep the main run loop responsive while the receiver or macOS prompts.
				let remaining = ContinuousClock.now.duration(to: deadline).components
				guard remaining.seconds > 0 else { throw QuitError.timedOut }
				try await sendSaveAndQuit(to: pid, timeout: Double(remaining.seconds))
			} else if !target.terminate() && !target.isTerminated {
				throw QuitError.requestFailed(Int(errAEEventFailed))
			}
		}

		while true {
			try Task.checkCancellation()
			let running = runningGlyphs4PIDs()
			guard running.isSubset(of: confirmedPIDs) else { throw QuitError.processChanged }
			if running.isEmpty && targets.allSatisfy(\.isTerminated) { return }
			guard ContinuousClock.now < deadline else { throw QuitError.timedOut }
			try await Task.sleep(for: .milliseconds(250))
		}
	}

	// Nonisolated async so the blocking send runs off the main actor. A PID address
	// identifies one running instance and cannot launch another copy.
	private static func sendSaveAndQuit(to pid: pid_t, timeout: TimeInterval) async throws {
		try Task.checkCancellation()
		let event = NSAppleEventDescriptor(
			eventClass: AEEventClass(kCoreEventClass),
			eventID: AEEventID(kAEQuitApplication),
			targetDescriptor: NSAppleEventDescriptor(processIdentifier: pid),
			returnID: AEReturnID(kAutoGenerateReturnID),
			transactionID: AETransactionID(kAnyTransactionID)
		)
		event.setParam(NSAppleEventDescriptor(enumCode: OSType(kAEYes)), forKeyword: AEKeyword(keyAESaveOptions))
		let code: Int
		do {
			let reply = try event.sendEvent(options: [.waitForReply, .canInteract, .canSwitchLayer], timeout: timeout)
			code = Int(reply.paramDescriptor(forKeyword: AEKeyword(keyErrorNumber))?.int32Value ?? 0)
		} catch {
			code = (error as NSError).code
		}
		switch code {
		// Some apps exit before replying. The caller still verifies process exit.
		case 0, Int(procNotFound), Int(connectionInvalid): return
		case Int(userCanceledErr): throw QuitError.cancelled
		case Int(errAEEventNotPermitted), Int(errAEEventWouldRequireUserConsent): throw QuitError.automationDenied
		case Int(errAETimeout): throw QuitError.timedOut
		default: throw QuitError.requestFailed(code)
		}
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
			if let bundleID = app.bundleIdentifier, bundleIDSet.contains(bundleID) {
				byPID[app.processIdentifier] = app
			}
		}

		return byPID.values.filter { app in
			if app.isTerminated || app.processIdentifier == selfPID { return false }
			if let selfBundleID, app.bundleIdentifier == selfBundleID { return false }
			guard let version = majorVersion(for: app) else { return false }
			return versions?.contains(version) ?? true
		}
	}

	private static func majorVersion(for app: NSRunningApplication) -> GlyphsMajorVersion? {
		let shortVersion = app.bundleURL
			.flatMap(Bundle.init(url:))?
			.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
		return GlyphsRunningProcessDetector.classify(GlyphsRunningProcessInfo(
			bundleIdentifier: app.bundleIdentifier,
			shortVersion: shortVersion,
			displayName: app.localizedName,
			fileName: app.bundleURL?.deletingPathExtension().lastPathComponent
		))
	}
}
