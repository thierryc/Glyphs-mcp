import AppKit
import Foundation
import SwiftUI

public struct PreflightItem: Identifiable {
	public enum Level {
		case ok
		case warn
		case bad

		public var symbolName: String {
			switch self {
			case .ok: return "checkmark.circle.fill"
			case .warn: return "exclamationmark.triangle.fill"
			case .bad: return "xmark.octagon.fill"
			}
		}

		public var color: Color {
			switch self {
			case .ok: return .green
			case .warn: return .orange
			case .bad: return .red
			}
		}
	}

	public let id = UUID()
	public let level: Level
	public let title: String
	public let details: String
}

public struct PythonCandidate: Hashable {
	public let path: String
	public let version: String
	public let source: String
}

public struct PreflightResult {
	public var items: [PreflightItem]
	public var glyphsPipPath: String?
	public var glyphsPipVersion: String?
	public var glyphsSelectedPythonFrameworkPath: String?
	public var glyphsSelectedPythonVersion: String?
	public var customPythons: [PythonCandidate]
	public var customPythonTooOldCount: Int
	public var customPythonTooNewCount: Int
	public var customPythonUnknownCount: Int
	public var codexPath: String?
	public var claudePath: String?
	public var nodePath: String?

	public init(items: [PreflightItem], glyphsPipPath: String?, glyphsPipVersion: String?, glyphsSelectedPythonFrameworkPath: String?, glyphsSelectedPythonVersion: String?, customPythons: [PythonCandidate], customPythonTooOldCount: Int, customPythonTooNewCount: Int, customPythonUnknownCount: Int, codexPath: String?, claudePath: String?, nodePath: String?) {
		self.items = items
		self.glyphsPipPath = glyphsPipPath
		self.glyphsPipVersion = glyphsPipVersion
		self.glyphsSelectedPythonFrameworkPath = glyphsSelectedPythonFrameworkPath
		self.glyphsSelectedPythonVersion = glyphsSelectedPythonVersion
		self.customPythons = customPythons
		self.customPythonTooOldCount = customPythonTooOldCount
		self.customPythonTooNewCount = customPythonTooNewCount
		self.customPythonUnknownCount = customPythonUnknownCount
		self.codexPath = codexPath
		self.claudePath = claudePath
		self.nodePath = nodePath
	}

	public static let empty = PreflightResult(items: [], glyphsPipPath: nil, glyphsPipVersion: nil, glyphsSelectedPythonFrameworkPath: nil, glyphsSelectedPythonVersion: nil, customPythons: [], customPythonTooOldCount: 0, customPythonTooNewCount: 0, customPythonUnknownCount: 0, codexPath: nil, claudePath: nil, nodePath: nil)
}

public enum Preflight {
	public static func scan() -> PreflightResult {
		var items: [PreflightItem] = []
		let runner = ProcessRunner()

		let glyphsBase = InstallerPaths.glyphsBaseDir
		let pluginsDir = InstallerPaths.glyphsPluginsDir
		items.append(.init(level: .ok, title: NSLocalizedString("Glyphs base folder", comment: "Preflight item title"), details: glyphsBase.path))
		items.append(.init(level: .ok, title: NSLocalizedString("Glyphs plugins folder", comment: "Preflight item title"), details: pluginsDir.path))

		// Payload + installed plugin versions (best-effort; payload exists only in the built app).
		let payloadInfo = Preflight.readPluginVersion(bundle: .main, pluginBundleURL: nil)
		switch payloadInfo {
		case .some(let v):
			items.append(.init(level: .ok, title: NSLocalizedString("Payload plugin version", comment: "Preflight item title"), details: v))
		case .none:
			items.append(.init(
				level: .warn,
				title: NSLocalizedString("Payload plugin version", comment: "Preflight item title"),
				details: NSLocalizedString("Unavailable (payload not found yet).", comment: "Preflight item details")
			))
		}

		let installedPlugin = pluginsDir.appendingPathComponent("Glyphs MCP.glyphsPlugin", isDirectory: true)
		if let installedVer = Preflight.readPluginVersionFromBundle(pluginBundle: installedPlugin) {
			items.append(.init(level: .ok, title: NSLocalizedString("Installed plugin version", comment: "Preflight item title"), details: installedVer))
		} else {
			items.append(.init(
				level: .warn,
				title: NSLocalizedString("Installed plugin version", comment: "Preflight item title"),
				details: NSLocalizedString("Not installed (yet).", comment: "Preflight item details")
			))
		}

		let glyphsPip = InstallerPaths.glyphsPythonPip3()
		let glyphsPipVersion: String? = {
			guard let glyphsPip else { return nil }
			let python3 = glyphsPip.deletingLastPathComponent().appendingPathComponent("python3")
			let res = runner.runSyncWithStderr(executable: python3, args: ["-c", "import sys; print(sys.version.split()[0])"])
			guard res.exitCode == 0 else { return nil }
			let v = res.stdout.trimmingCharacters(in: .whitespacesAndNewlines)
			return v.isEmpty ? nil : v
		}()
		if let pip = glyphsPip {
			let details = glyphsPipVersion.map { "\(pip.path) (\($0))" } ?? pip.path
			items.append(.init(level: .ok, title: NSLocalizedString("Glyphs Python pip3", comment: "Preflight item title"), details: details))
		} else {
			items.append(.init(
				level: .warn,
				title: NSLocalizedString("Glyphs Python pip3", comment: "Preflight item title"),
				details: NSLocalizedString("Not found (install GlyphsPythonPlugin in Glyphs → Settings → Addons)", comment: "Preflight item details")
			))
		}

		let glyphsSelectedFramework = GlyphsPreferences.pythonFrameworkPath()
		let glyphsSelectedVersion: String? = {
			guard let glyphsSelectedFramework else { return nil }
			let python3 = URL(fileURLWithPath: glyphsSelectedFramework, isDirectory: true).appendingPathComponent("bin/python3")
			let res = runner.runSyncWithStderr(executable: python3, args: ["-c", "import sys; print(sys.version.split()[0])"])
			guard res.exitCode == 0 else { return GlyphsPreferences.pythonFrameworkMajorMinor(from: glyphsSelectedFramework) }
			let v = res.stdout.trimmingCharacters(in: .whitespacesAndNewlines)
			return v.isEmpty ? GlyphsPreferences.pythonFrameworkMajorMinor(from: glyphsSelectedFramework) : v
		}()

		if let glyphsSelectedFramework {
			let detail = glyphsSelectedVersion != nil
				? "Selected: \(glyphsSelectedVersion!) (\(glyphsSelectedFramework))"
				: "Selected framework: \(glyphsSelectedFramework)"
			items.append(.init(level: .ok, title: NSLocalizedString("Glyphs Python setting", comment: "Preflight item title"), details: detail))
		} else {
			items.append(.init(
				level: .warn,
				title: NSLocalizedString("Glyphs Python setting", comment: "Preflight item title"),
				details: NSLocalizedString("Unknown (could not read Glyphs preferences).", comment: "Preflight item details")
			))
		}

		let scan = PythonDetector.scanCustomPythons()
		let customPythons = scan.good
		let summary = PythonDetector.formatSummary(scan: scan)
		items.append(.init(level: customPythons.isEmpty ? .warn : .ok, title: NSLocalizedString("Custom Python", comment: "Preflight item title"), details: summary))

		let codex = ToolLocator.findTool(named: "codex", extraCandidates: ["/opt/homebrew/bin/codex", "/usr/local/bin/codex"])
		items.append(.init(
			level: codex == nil ? .warn : .ok,
			title: NSLocalizedString("Codex CLI", comment: "Preflight item title"),
			details: codex ?? NSLocalizedString("Not found (will patch ~/.codex/config.toml instead).", comment: "Preflight item details")
		))

		let claude = ToolLocator.findTool(named: "claude", extraCandidates: ["/opt/homebrew/bin/claude", "/usr/local/bin/claude"])
		items.append(.init(
			level: claude == nil ? .warn : .ok,
			title: NSLocalizedString("Claude CLI", comment: "Preflight item title"),
			details: claude ?? NSLocalizedString("Not found (Claude Code will not be auto-configured).", comment: "Preflight item details")
		))

		return PreflightResult(
			items: items,
			glyphsPipPath: glyphsPip?.path,
			glyphsPipVersion: glyphsPipVersion,
			glyphsSelectedPythonFrameworkPath: glyphsSelectedFramework,
			glyphsSelectedPythonVersion: glyphsSelectedVersion,
			customPythons: customPythons,
			customPythonTooOldCount: scan.tooOldCount,
			customPythonTooNewCount: scan.tooNewCount,
			customPythonUnknownCount: scan.unknownCount,
			codexPath: codex,
			claudePath: claude,
			nodePath: nil
		)
	}

	static func readPluginVersion(bundle: Bundle, pluginBundleURL: URL?) -> String? {
		if let pluginBundleURL {
			return readPluginVersionFromBundle(pluginBundle: pluginBundleURL)
		}
		// In the built app, the plugin is placed under Resources/Payload/Glyphs MCP.glyphsPlugin.
		if let payload = try? InstallerPayload.resolve(bundle: bundle) {
			return readPluginVersionFromBundle(pluginBundle: payload.pluginBundle)
		}
		return nil
	}

	public static func readPluginVersionFromBundle(pluginBundle: URL) -> String? {
		let info = pluginBundle.appendingPathComponent("Contents/Info.plist")
		guard let data = try? Data(contentsOf: info) else { return nil }
		guard let obj = try? PropertyListSerialization.propertyList(from: data, format: nil) as? [String: Any] else { return nil }
		let short = obj["CFBundleShortVersionString"] as? String
		let build = obj["CFBundleVersion"] as? String
		if let short, let build, short != build {
			return "\(short) (\(build))"
		}
		return short ?? build
	}
}

public struct GlyphsPythonStatus: Equatable {
	public enum Source: String, Equatable {
		case glyphsSetting
		case glyphsBundled
	}

	public let source: Source?
	public let version: String?
	public let pythonPath: String?
	public let pipPath: String?
	public let summary: String
	public let installFailureReason: String?

	public var canInstall: Bool {
		installFailureReason == nil && makeSelection() != nil
	}

	public func makeSelection() -> PythonSelection? {
		guard installFailureReason == nil else { return nil }
		switch source {
		case .glyphsSetting:
			guard let pythonPath else { return nil }
			return .custom(python3: URL(fileURLWithPath: pythonPath))
		case .glyphsBundled:
			guard let pipPath, let pythonPath else { return nil }
			return .glyphs(pip3: URL(fileURLWithPath: pipPath), python3: URL(fileURLWithPath: pythonPath))
		case .none:
			return nil
		}
	}
}

public enum GlyphsPythonResolver {
	public static func resolve(preflight: PreflightResult) -> GlyphsPythonStatus {
		if let frameworkPath = preflight.glyphsSelectedPythonFrameworkPath, !frameworkPath.isEmpty {
			let pythonPath = URL(fileURLWithPath: frameworkPath, isDirectory: true)
				.appendingPathComponent("bin/python3")
				.path
			let version = normalizedVersion(preflight.glyphsSelectedPythonVersion, fallbackPath: frameworkPath)
			if !FileManager.default.fileExists(atPath: pythonPath) {
				return GlyphsPythonStatus(
					source: .glyphsSetting,
					version: version,
					pythonPath: pythonPath,
					pipPath: nil,
					summary: "Glyphs is set to Python \(version ?? "unknown") at \(frameworkPath)",
					installFailureReason: "Glyphs is set to a Python framework, but \(pythonPath) was not found. Re-select the Python version in Glyphs and restart Glyphs."
				)
			}
			guard let version else {
				return GlyphsPythonStatus(
					source: .glyphsSetting,
					version: nil,
					pythonPath: pythonPath,
					pipPath: nil,
					summary: "Glyphs is set to Python at \(frameworkPath)",
					installFailureReason: "Glyphs is set to a Python framework, but its version could not be determined. Re-select the Python version in Glyphs and restart Glyphs."
				)
			}
			guard VersionGate.isSupported(version: version) else {
				return GlyphsPythonStatus(
					source: .glyphsSetting,
					version: version,
					pythonPath: pythonPath,
					pipPath: nil,
					summary: "Glyphs is set to Python \(version) at \(frameworkPath)",
					installFailureReason: "Glyphs is set to Python \(version), but Glyphs MCP supports Python 3.11–3.13. Change the Python version in Glyphs and restart Glyphs."
				)
			}
			return GlyphsPythonStatus(
				source: .glyphsSetting,
				version: version,
				pythonPath: pythonPath,
				pipPath: nil,
				summary: "Using Glyphs-selected Python \(version)",
				installFailureReason: nil
			)
		}

		if let pipPath = preflight.glyphsPipPath, !pipPath.isEmpty {
			let pythonPath = URL(fileURLWithPath: pipPath).deletingLastPathComponent().appendingPathComponent("python3").path
			if !FileManager.default.fileExists(atPath: pythonPath) {
				return GlyphsPythonStatus(
					source: .glyphsBundled,
					version: preflight.glyphsPipVersion,
					pythonPath: pythonPath,
					pipPath: pipPath,
					summary: "Using Glyphs bundled Python",
					installFailureReason: "Glyphs bundled Python was found, but \(pythonPath) is missing. Reinstall Glyphs Python from Glyphs → Settings → Addons."
				)
			}
			if let version = preflight.glyphsPipVersion, !VersionGate.isSupported(version: version) {
				return GlyphsPythonStatus(
					source: .glyphsBundled,
					version: version,
					pythonPath: pythonPath,
					pipPath: pipPath,
					summary: "Using Glyphs bundled Python \(version)",
					installFailureReason: "Glyphs bundled Python is \(version), but Glyphs MCP supports Python 3.11–3.13. Update Glyphs Python and restart Glyphs."
				)
			}
			let summaryVersion = preflight.glyphsPipVersion.map { " \($0)" } ?? ""
			return GlyphsPythonStatus(
				source: .glyphsBundled,
				version: preflight.glyphsPipVersion,
				pythonPath: pythonPath,
				pipPath: pipPath,
				summary: "Using Glyphs bundled Python\(summaryVersion)",
				installFailureReason: nil
			)
		}

		return GlyphsPythonStatus(
			source: nil,
			version: nil,
			pythonPath: nil,
			pipPath: nil,
			summary: "No usable Glyphs Python detected",
			installFailureReason: "Set a Python version in Glyphs → Settings → Addons, restart Glyphs, and try again."
		)
	}

	private static func normalizedVersion(_ version: String?, fallbackPath: String) -> String? {
		let trimmed = version?.trimmingCharacters(in: .whitespacesAndNewlines)
		if let trimmed, !trimmed.isEmpty {
			return trimmed
		}
		return GlyphsPreferences.pythonFrameworkMajorMinor(from: fallbackPath)
	}
}

public enum InstallerSimpleUI {
	public static func installButtonTitle(installedPluginVersion: PluginBundleVersion?) -> String {
		installedPluginVersion == nil ? "Install Glyphs MCP Server" : "Update Glyphs MCP Server"
	}

	public static func skillButtonTitle(hasExistingManagedSkills: Bool) -> String {
		hasExistingManagedSkills ? "Update Skill" : "Install Skill"
	}

	public static func wizardButtonTitle(installedPluginVersion: PluginBundleVersion?, skills: [InstallerSkillTargetSnapshot]) -> String {
		let hasExistingSkills = skills.contains(where: \.hasInstalledSkills)
		return (installedPluginVersion != nil || hasExistingSkills) ? "Update Setup" : "Complete Setup"
	}

	public static func versionLine(installed: PluginBundleVersion?, payload: PluginBundleVersion?) -> String {
		"Installed: \(installed?.displayString ?? "Not installed") • This app: \(payload?.displayString ?? "Unknown")"
	}
}

public enum InstallerAdvancedModePolicy {
	public static let preferenceKey = "cx.ap.glyphsMcpInstaller.advancedModeEnabled"
	public static let allTabIDs = ["wizard", "install", "link", "skill", "status", "help"]
	public static let advancedTabIDs: Set<String> = ["install", "link", "skill"]

	public static func visibleTabIDs(isAdvancedModeEnabled: Bool) -> [String] {
		isAdvancedModeEnabled ? allTabIDs : allTabIDs.filter { !advancedTabIDs.contains($0) }
	}

	public static func fallbackTabID(currentTabID: String, isAdvancedModeEnabled: Bool) -> String {
		guard !isAdvancedModeEnabled, advancedTabIDs.contains(currentTabID) else {
			return currentTabID
		}
		return "wizard"
	}
}

public enum InstallerAdvancedModePreferences {
	public static func load(from defaults: UserDefaults = .standard) -> Bool {
		defaults.bool(forKey: InstallerAdvancedModePolicy.preferenceKey)
	}

	public static func save(_ isEnabled: Bool, to defaults: UserDefaults = .standard) {
		defaults.set(isEnabled, forKey: InstallerAdvancedModePolicy.preferenceKey)
	}
}

public enum InstallerClientKind: Int, CaseIterable, Identifiable {
	case codex
	case claudeCode

	public var id: Int { rawValue }

	public var displayName: String {
		switch self {
		case .codex: return "Codex"
		case .claudeCode: return "Claude Code"
		}
	}
}

public struct InstallerClientDescriptor: Equatable {
	public let kind: InstallerClientKind
	public let isDetected: Bool

	public init(kind: InstallerClientKind, isDetected: Bool) {
		self.kind = kind
		self.isDetected = isDetected
	}
}

public enum InstallerClientOrdering {
	public static func ordered(_ descriptors: [InstallerClientDescriptor]) -> [InstallerClientDescriptor] {
		descriptors.sorted {
			if $0.isDetected != $1.isDetected {
				return $0.isDetected && !$1.isDetected
			}
			return $0.kind.rawValue < $1.kind.rawValue
		}
	}
}

public struct InstallerClientStatusSnapshot: Identifiable, Equatable {
	public enum CardState: Equatable {
		case configured
		case partial
		case notDetected

		public var summaryText: String {
			switch self {
			case .configured: return "Configured"
			case .partial: return "Partially available"
			case .notDetected: return "Not detected"
			}
		}
	}

	public struct Probe: Equatable {
		public let label: String
		public let summary: String
		public let detail: String?
	}

	public let kind: InstallerClientKind
	public let detected: Bool
	public let cardState: CardState
	public let statusText: String
	public let detailText: String?
	public let appStatus: Probe
	public let cliStatus: Probe
	public let configStatus: Probe

	public var id: InstallerClientKind { kind }
	public var name: String { kind.displayName }
}

public struct InstallerSkillTargetSnapshot: Identifiable, Equatable {
	public enum Kind: Int, CaseIterable, Identifiable {
		case codex
		case claudeCode

		public var id: Int { rawValue }

		public var displayName: String {
			switch self {
			case .codex: return "Codex"
			case .claudeCode: return "Claude Code"
			}
		}

		public var destinationPath: String {
			switch self {
			case .codex: return InstallerPaths.codexSkillsDir.path
			case .claudeCode: return InstallerPaths.claudeCodeSkillsDir.path
			}
		}
	}

	public let kind: Kind
	public let installedSkillNames: [String]

	public var id: Kind { kind }
	public var name: String { kind.displayName }
	public var hasInstalledSkills: Bool { !installedSkillNames.isEmpty }
	public var statusText: String {
		hasInstalledSkills ? "Installed: \(installedSkillNames.joined(separator: ", "))" : "Not installed"
	}
	public var destinationPath: String { kind.destinationPath }
}

public enum InstallerSkillTargetDetector {
	public static func detect(
		payload: InstallerPayload?,
		codexRoot: URL = InstallerPaths.codexSkillsDir,
		claudeCodeRoot: URL = InstallerPaths.claudeCodeSkillsDir
	) -> [InstallerSkillTargetSnapshot] {
		let installer = AgentSkillBundleInstaller(log: { _ in })
		let codexInstalled = payload.map { installer.existingManagedSkillDestinations(from: $0, under: codexRoot) } ?? []
		let claudeInstalled = payload.map { installer.existingManagedSkillDestinations(from: $0, under: claudeCodeRoot) } ?? []

		return [
			InstallerSkillTargetSnapshot(kind: .codex, installedSkillNames: codexInstalled.map(\.lastPathComponent).sorted()),
			InstallerSkillTargetSnapshot(kind: .claudeCode, installedSkillNames: claudeInstalled.map(\.lastPathComponent).sorted()),
		]
	}
}

public struct InstallerStatusSnapshot: Equatable {
	public let pluginInspection: PluginInstaller.InstalledPluginInspection
	public let installedPluginVersion: PluginBundleVersion?
	public let payloadPluginVersion: PluginBundleVersion?
	public let pluginStatusSummary: String
	public let installedPluginIsSymlink: Bool
	public let installedPluginSymlinkTarget: String?
	public let devPluginWarning: String?
	public let showsDevPluginReplacementOption: Bool
	public let versionLine: String
	public let glyphsRunning: Bool
	public let pythonStatus: GlyphsPythonStatus
	public let wizardButtonTitle: String
	public let installButtonTitle: String
	public let installMessage: String?
	public let canInstall: Bool
	public let clients: [InstallerClientStatusSnapshot]
	public let detectedClientsSummary: String
	public let skills: [InstallerSkillTargetSnapshot]
}

public enum InstallerStatusSnapshotBuilder {
	public static func build(
		preflight: PreflightResult,
		check: CheckResult,
		installedPluginVersion: PluginBundleVersion?,
		payloadPluginVersion: PluginBundleVersion?,
		glyphsRunning: Bool,
		pluginInspection: PluginInstaller.InstalledPluginInspection = .notInstalled()
	) -> InstallerStatusSnapshot {
		let effectiveInstalledPluginVersion = installedPluginVersion ?? pluginInspection.version
		let pythonStatus = GlyphsPythonResolver.resolve(preflight: preflight)
		let installMessage: String? = glyphsRunning
			? "Quit Glyphs before installing or updating the plug-in."
			: pythonStatus.installFailureReason
		let orderedClients = buildClientStatuses(preflight: preflight, check: check)
		let detectedNames = orderedClients.filter { $0.detected }.map(\.name)
		let skillTargets = InstallerSkillTargetDetector.detect(payload: try? InstallerPayload.resolve())
		let devPluginWarning = pluginInspection.isSymlink
			? buildDevPluginWarning(inspection: pluginInspection)
			: nil

		return InstallerStatusSnapshot(
			pluginInspection: pluginInspection,
			installedPluginVersion: effectiveInstalledPluginVersion,
			payloadPluginVersion: payloadPluginVersion,
			pluginStatusSummary: pluginInspection.statusSummary,
			installedPluginIsSymlink: pluginInspection.isSymlink,
			installedPluginSymlinkTarget: pluginInspection.symlinkTargetPath,
			devPluginWarning: devPluginWarning,
			showsDevPluginReplacementOption: pluginInspection.isSymlink,
			versionLine: InstallerSimpleUI.versionLine(installed: effectiveInstalledPluginVersion, payload: payloadPluginVersion),
			glyphsRunning: glyphsRunning,
			pythonStatus: pythonStatus,
			wizardButtonTitle: InstallerSimpleUI.wizardButtonTitle(installedPluginVersion: effectiveInstalledPluginVersion, skills: skillTargets),
			installButtonTitle: InstallerSimpleUI.installButtonTitle(installedPluginVersion: effectiveInstalledPluginVersion),
			installMessage: installMessage,
			canInstall: installMessage == nil,
			clients: orderedClients,
			detectedClientsSummary: detectedNames.isEmpty ? "No compatible clients detected on this Mac yet." : "Detected: " + detectedNames.joined(separator: ", "),
			skills: skillTargets
		)
	}

	private static func buildClientStatuses(preflight: PreflightResult, check: CheckResult) -> [InstallerClientStatusSnapshot] {
		let descriptors = InstallerClientOrdering.ordered([
			.init(kind: .codex, isDetected: isCodexDetected(check: check)),
			.init(kind: .claudeCode, isDetected: isClaudeCodeDetected(preflight: preflight, check: check)),
		])

		return descriptors.map { descriptor in
			let appStatus = appStatus(for: descriptor.kind, check: check)
			let cliStatus = cliStatus(for: descriptor.kind, check: check, preflight: preflight)
			let configStatus = configStatus(for: descriptor.kind, check: check)
			let cardState = cardState(appStatus: appStatus, cliStatus: cliStatus, configStatus: configStatus)
			return InstallerClientStatusSnapshot(
				kind: descriptor.kind,
				detected: descriptor.isDetected,
				cardState: cardState,
				statusText: cardState.summaryText,
				detailText: detailText(for: descriptor.kind),
				appStatus: appStatus,
				cliStatus: cliStatus,
				configStatus: configStatus
			)
		}
	}

	private static func isCodexDetected(check: CheckResult) -> Bool {
		itemLevel(title: "Codex MCP settings", check: check) == .ok
			|| itemLevel(title: "Codex app", check: check) == .ok
			|| itemLevel(title: "Codex CLI", check: check) == .ok
	}

	private static func buildDevPluginWarning(inspection: PluginInstaller.InstalledPluginInspection) -> String {
		var parts = ["The installed plug-in is a development symlink."]
		if let symlinkTargetPath = inspection.symlinkTargetPath {
			parts.append("Target: \(symlinkTargetPath)")
		}
		parts.append("Leave replacement off to keep it, or turn replacement on to install the latest GitHub plug-in.")
		return parts.joined(separator: " ")
	}

	private static func isClaudeCodeDetected(preflight: PreflightResult, check: CheckResult) -> Bool {
		itemLevel(title: "Claude Code MCP settings", check: check) == .ok
			|| itemLevel(title: "Claude app", check: check) == .ok
			|| preflight.claudePath != nil
			|| itemLevel(title: "Claude Code CLI", check: check) == .ok
	}

	private static func appStatus(for kind: InstallerClientKind, check: CheckResult) -> InstallerClientStatusSnapshot.Probe {
		switch kind {
		case .codex:
			let path = itemDetails(title: "Codex app", check: check)
			return .init(label: "App", summary: itemLevel(title: "Codex app", check: check) == .ok ? "Installed" : "Not found", detail: path)
		case .claudeCode:
			let path = itemDetails(title: "Claude app", check: check)
			return .init(label: "App", summary: itemLevel(title: "Claude app", check: check) == .ok ? "Installed" : "Not found", detail: path)
		}
	}

	private static func cliStatus(for kind: InstallerClientKind, check: CheckResult, preflight: PreflightResult) -> InstallerClientStatusSnapshot.Probe {
		switch kind {
		case .codex:
			let path = itemDetails(title: "Codex CLI", check: check)
			return .init(label: "CLI", summary: itemLevel(title: "Codex CLI", check: check) == .ok ? "Installed" : "Not found", detail: path)
		case .claudeCode:
			let path = preflight.claudePath ?? itemDetails(title: "Claude Code CLI", check: check)
			return .init(label: "CLI", summary: (preflight.claudePath != nil || itemLevel(title: "Claude Code CLI", check: check) == .ok) ? "Installed" : "Not found", detail: path)
		}
	}

	private static func configStatus(for kind: InstallerClientKind, check: CheckResult) -> InstallerClientStatusSnapshot.Probe {
		switch kind {
		case .codex:
			let summary = itemDetails(title: "Codex MCP settings", check: check) ?? "Missing"
			return .init(label: "Config", summary: summary, detail: InstallerPaths.codexConfig.path)
		case .claudeCode:
			let summary = itemDetails(title: "Claude Code MCP settings", check: check) ?? "Missing"
			return .init(label: "Config", summary: summary, detail: InstallerPaths.claudeCodeConfig.path)
		}
	}

	private static func cardState(
		appStatus: InstallerClientStatusSnapshot.Probe,
		cliStatus: InstallerClientStatusSnapshot.Probe,
		configStatus: InstallerClientStatusSnapshot.Probe
	) -> InstallerClientStatusSnapshot.CardState {
		if configStatus.summary == "Configured" {
			return .configured
		}
		if appStatus.summary == "Installed" || cliStatus.summary == "Installed" || configStatus.summary != "Missing" {
			return .partial
		}
		return .notDetected
	}

	private static func detailText(for kind: InstallerClientKind) -> String? {
		switch kind {
		case .codex:
			return "Codex app and CLI share ~/.codex/config.toml."
		case .claudeCode:
			return "Claude app and Claude Code CLI share ~/.claude.json."
		}
	}

	private static func itemLevel(title: String, check: CheckResult) -> PreflightItem.Level? {
		check.items.first(where: { $0.title == title })?.level
	}

	private static func itemDetails(title: String, check: CheckResult) -> String? {
		check.items.first(where: { $0.title == title })?.details
	}
}

enum PythonDetector {
	struct PythonScanResult {
		var good: [PythonCandidate]
		var tooOldCount: Int
		var tooNewCount: Int
		var unknownCount: Int
	}

	static func formatSummary(scan: PythonScanResult) -> String {
		let good = scan.good.count
		let ignored = scan.tooOldCount + scan.tooNewCount + scan.unknownCount

		var parts: [String] = []
		if good == 0 {
			parts.append("No supported interpreters (3.11–3.13).")
		} else if good == 1 {
			parts.append("Good candidates: 1 (3.11–3.13).")
		} else {
			parts.append("Good candidates: \(good) (3.11–3.13).")
		}

		if ignored > 0 {
			var ignoredParts: [String] = []
			if scan.tooOldCount > 0 { ignoredParts.append("\(scan.tooOldCount) too old") }
			if scan.tooNewCount > 0 { ignoredParts.append("\(scan.tooNewCount) too new") }
			if scan.unknownCount > 0 { ignoredParts.append("\(scan.unknownCount) unknown") }
			parts.append("Ignored: " + ignoredParts.joined(separator: ", ") + ".")
		}

		if let top = scan.good.first {
			parts.append("Top: \(top.version) (\(top.source)).")
		}

		if scan.good.count > 1 {
			let shown = scan.good.prefix(3).map { "\($0.version) (\($0.source))" }.joined(separator: ", ")
			parts.append("Candidates: \(shown)\(scan.good.count > 3 ? ", …" : "").")
		}

		return parts.joined(separator: " ")
	}

	static func scanCustomPythons() -> PythonScanResult {
		let fm = FileManager.default
		let runner = ProcessRunner()
		let regex = try? NSRegularExpression(pattern: "^python3(\\.\\d+)?$", options: [])

		func iterPythonBins(in binDir: URL) -> [URL] {
			guard let regex else { return [] }
			var isDir: ObjCBool = false
			guard fm.fileExists(atPath: binDir.path, isDirectory: &isDir), isDir.boolValue else { return [] }

			let entries: [URL]
			do {
				entries = try fm.contentsOfDirectory(at: binDir, includingPropertiesForKeys: nil, options: [.skipsHiddenFiles])
			} catch {
				return []
			}

			var out: [URL] = []
			for url in entries.sorted(by: { $0.lastPathComponent < $1.lastPathComponent }) {
				let name = url.lastPathComponent
				let range = NSRange(location: 0, length: (name as NSString).length)
				guard regex.firstMatch(in: name, options: [], range: range) != nil else { continue }

				var isCandidateDir: ObjCBool = false
				guard fm.fileExists(atPath: url.path, isDirectory: &isCandidateDir), !isCandidateDir.boolValue else { continue }
				guard fm.isExecutableFile(atPath: url.path) else { continue }

				out.append(url)
			}

			return out
		}

		func pythonVersion(_ python: URL) -> String? {
			let res = runner.runSyncWithStderr(executable: python, args: ["-c", "import sys; print(sys.version.split()[0])"])
			guard res.exitCode == 0 else { return nil }
			let v = res.stdout.trimmingCharacters(in: .whitespacesAndNewlines)
			return v.isEmpty ? nil : v
		}

		var candidates: [(url: URL, source: String)] = []

		func addPythonOrgFramework(_ base: URL) {
			let versions = base.appendingPathComponent("Versions", isDirectory: true)
			let currentBin = versions.appendingPathComponent("Current/bin", isDirectory: true)
			for py in iterPythonBins(in: currentBin) { candidates.append((py, "python.org")) }

			var isDir: ObjCBool = false
			guard fm.fileExists(atPath: versions.path, isDirectory: &isDir), isDir.boolValue else { return }
			guard let versionDirs = try? fm.contentsOfDirectory(at: versions, includingPropertiesForKeys: nil, options: [.skipsHiddenFiles]) else { return }
			for vdir in versionDirs.sorted(by: { $0.lastPathComponent < $1.lastPathComponent }) {
				if vdir.lastPathComponent == "Current" { continue }
				var isVersionDir: ObjCBool = false
				guard fm.fileExists(atPath: vdir.path, isDirectory: &isVersionDir), isVersionDir.boolValue else { continue }
				for py in iterPythonBins(in: vdir.appendingPathComponent("bin", isDirectory: true)) {
					candidates.append((py, "python.org"))
				}
			}
		}

		addPythonOrgFramework(URL(fileURLWithPath: "/Library/Frameworks/Python.framework", isDirectory: true))
		addPythonOrgFramework(InstallerPaths.home.appendingPathComponent("Library/Frameworks/Python.framework", isDirectory: true))

		for brewBin in ["/opt/homebrew/bin", "/usr/local/bin"] {
			let dir = URL(fileURLWithPath: brewBin, isDirectory: true)
			for py in iterPythonBins(in: dir) { candidates.append((py, "homebrew")) }
		}

		for sysBin in ["/usr/bin", "/bin"] {
			let dir = URL(fileURLWithPath: sysBin, isDirectory: true)
			for py in iterPythonBins(in: dir) { candidates.append((py, "system")) }
		}

		if let pathEnv = ProcessInfo.processInfo.environment["PATH"] {
			for p in pathEnv.split(separator: ":").map(String.init) where !p.isEmpty {
				let dir = URL(fileURLWithPath: p, isDirectory: true)
				let source: String = {
					if p.contains("homebrew") || p.hasPrefix("/opt/homebrew") || p.hasPrefix("/usr/local") { return "homebrew" }
					if p.hasPrefix("/usr") || p.hasPrefix("/bin") { return "system" }
					return "path"
				}()
				for py in iterPythonBins(in: dir) { candidates.append((py, source)) }
			}
		}

		candidates.append((URL(fileURLWithPath: "/usr/bin/python3"), "system"))

		// Version managers (best-effort).
		let pyenv = InstallerPaths.home.appendingPathComponent(".pyenv/versions", isDirectory: true)
		if let versionDirs = try? fm.contentsOfDirectory(at: pyenv, includingPropertiesForKeys: nil, options: [.skipsHiddenFiles]) {
			for vdir in versionDirs {
				for py in iterPythonBins(in: vdir.appendingPathComponent("bin", isDirectory: true)) {
					candidates.append((py, "path"))
				}
			}
		}
		let asdf = InstallerPaths.home.appendingPathComponent(".asdf/installs/python", isDirectory: true)
		if let versionDirs = try? fm.contentsOfDirectory(at: asdf, includingPropertiesForKeys: nil, options: [.skipsHiddenFiles]) {
			for vdir in versionDirs {
				for py in iterPythonBins(in: vdir.appendingPathComponent("bin", isDirectory: true)) {
					candidates.append((py, "path"))
				}
			}
		}

		var seen = Set<String>()
		var good: [PythonCandidate] = []
		var tooOldCount = 0
		var tooNewCount = 0
		var unknownCount = 0

		for (url, source) in candidates {
			guard fm.isExecutableFile(atPath: url.path) else { continue }
			let resolved = url.resolvingSymlinksInPath()
			if seen.contains(resolved.path) { continue }
			seen.insert(resolved.path)

			guard let ver = pythonVersion(resolved) else {
				unknownCount += 1
				continue
			}
			let t = VersionGate.tuple(ver)
			if t < (3, 11, 0) {
				tooOldCount += 1
				continue
			}
			if t >= (3, 14, 0) {
				tooNewCount += 1
				continue
			}
			good.append(.init(path: resolved.path, version: ver, source: source))
		}

		good.sort {
			let c = VersionGate.compare($0.version, $1.version)
			if c != 0 { return c > 0 }
			return ($0.source == "python.org") && ($1.source != "python.org")
		}

		return PythonScanResult(good: good, tooOldCount: tooOldCount, tooNewCount: tooNewCount, unknownCount: unknownCount)
	}

	static func detectCustomPythons() -> [PythonCandidate] {
		scanCustomPythons().good
	}
}

enum VersionGate {
	static func isSupported(version: String) -> Bool {
		let t = tuple(version)
		return t >= (3, 11, 0) && t < (3, 14, 0)
	}

	static func compare(_ a: String, _ b: String) -> Int {
		let ta = tuple(a)
		let tb = tuple(b)
		if ta == tb { return 0 }
		return ta < tb ? -1 : 1
	}

	static func tuple(_ v: String) -> (Int, Int, Int) {
		let parts = v.split(separator: ".").prefix(3).map { Int($0) ?? 0 }
		let major = parts.count > 0 ? parts[0] : 0
		let minor = parts.count > 1 ? parts[1] : 0
		let patch = parts.count > 2 ? parts[2] : 0
		return (major, minor, patch)
	}
}

enum ToolLocator {
	static func findTool(
		named: String,
		extraCandidates: [String] = [],
		home: URL = InstallerPaths.home,
		pathEnv: String? = ProcessInfo.processInfo.environment["PATH"]
	) -> String? {
		let fm = FileManager.default

		var candidates: [String] = []

		// Explicit candidates first.
		candidates.append(contentsOf: extraCandidates)

		// Common user-level install locations (Finder-launched apps often have a minimal PATH).
		candidates.append(home.appendingPathComponent(".local/bin/\(named)").path)
		candidates.append(home.appendingPathComponent("bin/\(named)").path)
		candidates.append(home.appendingPathComponent(".npm/bin/\(named)").path)
		candidates.append(home.appendingPathComponent(".npm-global/bin/\(named)").path)
		candidates.append(home.appendingPathComponent(".yarn/bin/\(named)").path)
		candidates.append(home.appendingPathComponent(".config/yarn/global/node_modules/.bin/\(named)").path)
		candidates.append(home.appendingPathComponent("Library/pnpm/\(named)").path)
		candidates.append(home.appendingPathComponent(".volta/bin/\(named)").path)
		candidates.append(home.appendingPathComponent(".asdf/shims/\(named)").path)
		candidates.append(home.appendingPathComponent(".bun/bin/\(named)").path)
		candidates.append(home.appendingPathComponent(".cargo/bin/\(named)").path)
		candidates.append(home.appendingPathComponent(".claude/local/bin/\(named)").path)

		// Common system locations.
		let systemDirs = [
			"/opt/homebrew/bin",
			"/usr/local/bin",
			"/usr/bin",
			"/bin",
			"/usr/sbin",
			"/sbin",
		]
		candidates.append(contentsOf: systemDirs.map { "\($0)/\(named)" })

		// Current process PATH (may include nvm/asdf, etc when launched from a shell).
		if let pathEnv {
			let envDirs = pathEnv.split(separator: ":").map(String.init)
			candidates.append(contentsOf: envDirs.map { "\($0)/\(named)" })
		}

		// nvm installs (best-effort).
		let nvm = home.appendingPathComponent(".nvm/versions/node", isDirectory: true)
		if let nodeVers = try? fm.contentsOfDirectory(at: nvm, includingPropertiesForKeys: nil, options: [.skipsHiddenFiles]) {
			for v in nodeVers.sorted(by: { compareNodeVersionDirectories($0.lastPathComponent, $1.lastPathComponent) > 0 }) {
				candidates.append(v.appendingPathComponent("bin/\(named)").path)
			}
		}

		// De-dup while preserving order.
		var seen = Set<String>()
		for p in candidates {
			guard !seen.contains(p) else { continue }
			seen.insert(p)
			if fm.isExecutableFile(atPath: p) {
				return p
			}
		}

		return nil
	}

	private static func compareNodeVersionDirectories(_ lhs: String, _ rhs: String) -> Int {
		let a = parseVersionComponents(lhs)
		let b = parseVersionComponents(rhs)
		if a == b { return 0 }
		return a.lexicographicallyPrecedes(b) ? -1 : 1
	}

	private static func parseVersionComponents(_ raw: String) -> [Int] {
		raw
			.trimmingCharacters(in: CharacterSet(charactersIn: "vV"))
			.split(separator: ".")
			.map { component in
				let digits = component.prefix { $0.isNumber }
				return Int(digits) ?? 0
			}
	}
}
