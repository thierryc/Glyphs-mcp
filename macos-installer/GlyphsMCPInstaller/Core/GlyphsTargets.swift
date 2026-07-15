import AppKit
import Foundation

public struct GlyphsApplicationInfo: Identifiable, Equatable, Sendable {
	public let majorVersion: GlyphsMajorVersion
	public let appURL: URL
	public let bundleIdentifier: String
	public let shortVersion: String?
	public let displayName: String
	public let isBeta: Bool

	public var id: GlyphsMajorVersion { majorVersion }

	public init(
		majorVersion: GlyphsMajorVersion,
		appURL: URL,
		bundleIdentifier: String,
		shortVersion: String?,
		displayName: String,
		isBeta: Bool
	) {
		self.majorVersion = majorVersion
		self.appURL = appURL
		self.bundleIdentifier = bundleIdentifier
		self.shortVersion = shortVersion
		self.displayName = displayName
		self.isBeta = isBeta
	}
}

public enum GlyphsApplicationDetector {
	private static let ambiguousBetaBundleIdentifier = "com.GeorgSeifert.GlyphsBeta"

	public static func detect(
		home: URL = InstallerPaths.home,
		workspace: NSWorkspace = .shared
	) -> [GlyphsApplicationInfo] {
		var candidateURLs: Set<URL> = []
		let bundleIdentifiers = GlyphsMajorVersion.allCases.flatMap(\.bundleIdentifiers) + [ambiguousBetaBundleIdentifier]
		for bundleIdentifier in bundleIdentifiers {
			if let appURL = workspace.urlForApplication(withBundleIdentifier: bundleIdentifier) {
				candidateURLs.insert(appURL.standardizedFileURL)
			}
		}

		let roots = [
			URL(fileURLWithPath: "/Applications", isDirectory: true),
			home.appendingPathComponent("Applications", isDirectory: true),
		]
		for root in roots {
			guard let entries = try? FileManager.default.contentsOfDirectory(
				at: root,
				includingPropertiesForKeys: [.isDirectoryKey],
				options: [.skipsHiddenFiles]
			) else { continue }
			for entry in entries where entry.pathExtension.caseInsensitiveCompare("app") == .orderedSame {
				if entry.deletingPathExtension().lastPathComponent.lowercased().hasPrefix("glyphs") {
					candidateURLs.insert(entry.standardizedFileURL)
				}
			}
		}

		return detect(candidates: Array(candidateURLs))
	}

	public static func detect(candidates: [URL]) -> [GlyphsApplicationInfo] {
		let applications = candidates.compactMap(applicationInfo(at:))
		var bestByVersion: [GlyphsMajorVersion: GlyphsApplicationInfo] = [:]
		for application in applications {
			guard let current = bestByVersion[application.majorVersion] else {
				bestByVersion[application.majorVersion] = application
				continue
			}
			if sortKey(application) < sortKey(current) {
				bestByVersion[application.majorVersion] = application
			}
		}
		return GlyphsMajorVersion.allCases.compactMap { bestByVersion[$0] }
	}

	public static func classify(
		bundleIdentifier: String?,
		shortVersion: String?,
		displayName: String?,
		fileName: String?
	) -> GlyphsMajorVersion? {
		if let bundleIdentifier {
			for version in GlyphsMajorVersion.allCases where version.bundleIdentifiers.contains(bundleIdentifier) {
				return version
			}
		}

		let names = [displayName, fileName]
			.compactMap { $0?.lowercased() }
			.joined(separator: " ")
		if names.contains("glyphs 3") || names.contains("glyphs3") { return .v3 }
		if names.contains("glyphs 4") || names.contains("glyphs4") { return .v4 }

		// A generic beta bundle does not identify its major version. Only use the
		// app version as a discriminator after confirming this is a Glyphs bundle
		// or a Glyphs-named application, so unrelated 3.x/4.x apps are ignored.
		let isAmbiguousBetaBundle = bundleIdentifier == ambiguousBetaBundleIdentifier
		guard isAmbiguousBetaBundle || names.contains("glyphs") else { return nil }
		let trimmedVersion = shortVersion?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
		if trimmedVersion.hasPrefix("3") { return .v3 }
		if trimmedVersion.hasPrefix("4") { return .v4 }
		return nil
	}

	private static func applicationInfo(at appURL: URL) -> GlyphsApplicationInfo? {
		let infoURL = appURL.appendingPathComponent("Contents/Info.plist")
		guard
			let data = try? Data(contentsOf: infoURL),
			let plist = try? PropertyListSerialization.propertyList(from: data, format: nil) as? [String: Any]
		else { return nil }

		let bundleIdentifier = plist["CFBundleIdentifier"] as? String
		let shortVersion = plist["CFBundleShortVersionString"] as? String
		let displayName = (plist["CFBundleDisplayName"] as? String)
			?? (plist["CFBundleName"] as? String)
			?? appURL.deletingPathExtension().lastPathComponent
		guard let majorVersion = classify(
			bundleIdentifier: bundleIdentifier,
			shortVersion: shortVersion,
			displayName: displayName,
			fileName: appURL.deletingPathExtension().lastPathComponent
		) else { return nil }

		let identifier = bundleIdentifier ?? ""
		return GlyphsApplicationInfo(
			majorVersion: majorVersion,
			appURL: appURL.standardizedFileURL,
			bundleIdentifier: identifier,
			shortVersion: shortVersion,
			displayName: displayName,
			isBeta: identifier.lowercased().contains("beta") || displayName.lowercased().contains("beta")
		)
	}

	private static func sortKey(_ application: GlyphsApplicationInfo) -> String {
		let stableRank = application.bundleIdentifier == application.majorVersion.stableBundleIdentifier ? "0" : "1"
		let systemRank = application.appURL.path.hasPrefix("/Applications/") ? "0" : "1"
		return stableRank + systemRank + application.appURL.path.lowercased()
	}
}

public struct GlyphsTargetStatusSnapshot: Identifiable, Equatable {
	public let version: GlyphsMajorVersion
	public let application: GlyphsApplicationInfo?
	public let baseDirectory: URL
	public let pluginsDirectory: URL
	public let pluginInspection: PluginInstaller.InstalledPluginInspection
	public let payloadPluginVersion: PluginBundleVersion?
	public let pythonStatus: GlyphsPythonStatus
	public let isRunning: Bool

	public var id: GlyphsMajorVersion { version }
	public var isDetected: Bool { application != nil }
	public var installedPluginVersion: PluginBundleVersion? { pluginInspection.version }
	public var pluginStatusSummary: String { pluginInspection.statusSummary }
	public var installedPluginIsSymlink: Bool { pluginInspection.isSymlink }
	public var installedPluginSymlinkTarget: String? { pluginInspection.symlinkTargetPath }
	public var versionLine: String {
		InstallerSimpleUI.versionLine(installed: installedPluginVersion, payload: payloadPluginVersion)
	}

	public var installFailureReason: String? {
		guard isDetected else { return "\(version.displayName) was not detected on this Mac." }
		if isRunning { return "Quit \(version.displayName) before installing or updating the plug-in." }
		if let reason = pythonStatus.installFailureReason { return "\(version.displayName): \(reason)" }
		return nil
	}

	public var canInstall: Bool {
		installFailureReason == nil && pythonStatus.canInstall
	}

	public var devPluginWarning: String? {
		guard pluginInspection.isSymlink else { return nil }
		var parts = ["\(version.displayName) uses a development symlinked plug-in."]
		if let target = pluginInspection.symlinkTargetPath {
			parts.append("Target: \(target)")
		}
		parts.append("Leave replacement off to keep it, or enable replacement to install the latest GitHub plug-in.")
		return parts.joined(separator: " ")
	}

	public init(
		version: GlyphsMajorVersion,
		application: GlyphsApplicationInfo?,
		baseDirectory: URL,
		pluginsDirectory: URL,
		pluginInspection: PluginInstaller.InstalledPluginInspection,
		payloadPluginVersion: PluginBundleVersion?,
		pythonStatus: GlyphsPythonStatus,
		isRunning: Bool
	) {
		self.version = version
		self.application = application
		self.baseDirectory = baseDirectory
		self.pluginsDirectory = pluginsDirectory
		self.pluginInspection = pluginInspection
		self.payloadPluginVersion = payloadPluginVersion
		self.pythonStatus = pythonStatus
		self.isRunning = isRunning
	}
}

public enum GlyphsTargetStatusBuilder {
	public static func build(
		version: GlyphsMajorVersion,
		application: GlyphsApplicationInfo?,
		preflight: PreflightResult,
		payloadPluginVersion: PluginBundleVersion?,
		isRunning: Bool
	) -> GlyphsTargetStatusSnapshot {
		let baseDirectory = InstallerPaths.glyphsBaseDir(glyphsVersion: version)
		let pluginsDirectory = InstallerPaths.glyphsPluginsDir(glyphsVersion: version)
		let installedBundle = pluginsDirectory.appendingPathComponent("Glyphs MCP.glyphsPlugin", isDirectory: true)
		return GlyphsTargetStatusSnapshot(
			version: version,
			application: application,
			baseDirectory: baseDirectory,
			pluginsDirectory: pluginsDirectory,
			pluginInspection: PluginInstaller.inspectInstalledPlugin(at: installedBundle),
			payloadPluginVersion: payloadPluginVersion,
			pythonStatus: GlyphsPythonResolver.resolve(preflight: preflight),
			isRunning: isRunning
		)
	}
}

public enum InstallerTargetSelectionPolicy {
	public static func initialSelection(from targets: [GlyphsTargetStatusSnapshot]) -> Set<GlyphsMajorVersion> {
		Set(targets.filter(\.isDetected).map(\.version))
	}

	public static func reconciledSelection(
		current: Set<GlyphsMajorVersion>,
		detected: Set<GlyphsMajorVersion>,
		hasInitialized: Bool
	) -> Set<GlyphsMajorVersion> {
		hasInitialized ? current.intersection(detected) : detected
	}

	public static func installFailureReason(
		selectedVersions: Set<GlyphsMajorVersion>,
		targets: [GlyphsTargetStatusSnapshot]
	) -> String? {
		guard !selectedVersions.isEmpty else { return "Select at least one detected Glyphs version." }
		let byVersion = Dictionary(uniqueKeysWithValues: targets.map { ($0.version, $0) })
		for version in selectedVersions.sorted() {
			guard let target = byVersion[version] else { return "\(version.displayName) status is unavailable." }
			if let reason = target.installFailureReason { return reason }
		}
		return nil
	}

	public static func installButtonTitle(
		selectedVersions: Set<GlyphsMajorVersion>,
		targets: [GlyphsTargetStatusSnapshot]
	) -> String {
		let selected = targets.filter { selectedVersions.contains($0.version) }
		let installedCount = selected.filter { $0.installedPluginVersion != nil }.count
		if installedCount == 0 {
			return NSLocalizedString("Install Glyphs MCP Server", comment: "Multi-target install button")
		}
		if installedCount == selected.count {
			return NSLocalizedString("Update Glyphs MCP Server", comment: "Multi-target update button")
		}
		return NSLocalizedString("Install / Update Glyphs MCP Server", comment: "Mixed multi-target install button")
	}
}

public enum GlyphsPluginInstallStrategy: Sendable, Equatable {
	case bundledPayload
	case keepDevSymlink
	case latestFromGitHub

	public static func resolve(installedPluginIsSymlink: Bool, replaceDevSymlink: Bool) -> GlyphsPluginInstallStrategy {
		guard installedPluginIsSymlink else { return .bundledPayload }
		return replaceDevSymlink ? .latestFromGitHub : .keepDevSymlink
	}
}

public struct GlyphsInstallTargetPlan: Sendable {
	public let version: GlyphsMajorVersion
	public let pythonSelection: PythonSelection
	public let pluginsDirectory: URL
	public let pluginInstallStrategy: GlyphsPluginInstallStrategy

	public var dependencyInstallKey: String {
		switch pythonSelection {
		case .custom(let python3):
			return "custom:\(python3.standardizedFileURL.path)"
		case .glyphs(_, let python3):
			return "glyphs:\(version.rawValue):\(python3.standardizedFileURL.path)"
		}
	}

	public init(
		version: GlyphsMajorVersion,
		pythonSelection: PythonSelection,
		pluginsDirectory: URL,
		pluginInstallStrategy: GlyphsPluginInstallStrategy
	) {
		self.version = version
		self.pythonSelection = pythonSelection
		self.pluginsDirectory = pluginsDirectory
		self.pluginInstallStrategy = pluginInstallStrategy
	}
}
