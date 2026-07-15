import Foundation

public enum UninstallComponentKind: String, CaseIterable, Sendable {
	case plugin
	case skill
	case client
}

public enum UninstallSafetyState: Equatable, Sendable {
	case removable
	case missing
	case preserved
	case blocked

	public var isSelectable: Bool { self == .removable }
}

public enum UninstallClientKind: String, CaseIterable, Sendable {
	case codex
	case claudeDesktop
	case claudeCode

	public var displayName: String {
		switch self {
		case .codex: return "Codex"
		case .claudeDesktop: return "Claude Desktop"
		case .claudeCode: return "Claude Code"
		}
	}
}

public struct UninstallCandidate: Identifiable, Equatable, Sendable {
	public let id: String
	public let component: UninstallComponentKind
	public let title: String
	public let location: URL
	public let safetyState: UninstallSafetyState
	public let detail: String
	public let glyphsVersion: GlyphsMajorVersion?
	public let clientKind: UninstallClientKind?

	public init(
		id: String,
		component: UninstallComponentKind,
		title: String,
		location: URL,
		safetyState: UninstallSafetyState,
		detail: String,
		glyphsVersion: GlyphsMajorVersion? = nil,
		clientKind: UninstallClientKind? = nil
	) {
		self.id = id
		self.component = component
		self.title = title
		self.location = location
		self.safetyState = safetyState
		self.detail = detail
		self.glyphsVersion = glyphsVersion
		self.clientKind = clientKind
	}
}

public struct GlyphsUninstallPlan: Equatable, Sendable {
	public let candidates: [UninstallCandidate]
	public let selectedCandidateIDs: Set<String>

	public init(candidates: [UninstallCandidate], selectedCandidateIDs: Set<String>? = nil) {
		self.candidates = candidates
		self.selectedCandidateIDs = selectedCandidateIDs
			?? Set(candidates.filter { $0.safetyState.isSelectable }.map(\.id))
	}

	public var selectedCandidates: [UninstallCandidate] {
		candidates.filter { selectedCandidateIDs.contains($0.id) && $0.safetyState.isSelectable }
	}

	public var hasRemovableItems: Bool { candidates.contains { $0.safetyState.isSelectable } }

	public func selecting(_ identifiers: Set<String>) -> GlyphsUninstallPlan {
		GlyphsUninstallPlan(
			candidates: candidates,
			selectedCandidateIDs: identifiers.intersection(Set(candidates.filter { $0.safetyState.isSelectable }.map(\.id)))
		)
	}
}

public enum GlyphsUninstallSelectionPolicy {
	public static func selectedPluginVersions(plan: GlyphsUninstallPlan) -> Set<GlyphsMajorVersion> {
		Set(plan.selectedCandidates.compactMap { candidate in
			candidate.component == .plugin ? candidate.glyphsVersion : nil
		})
	}

	public static func selectedGlyphsAreRunning(
		plan: GlyphsUninstallPlan,
		runningVersions: Set<GlyphsMajorVersion>
	) -> Bool {
		!selectedPluginVersions(plan: plan).isDisjoint(with: runningVersions)
	}

	public static func canExecute(
		plan: GlyphsUninstallPlan,
		hasAcknowledged: Bool,
		runningVersions: Set<GlyphsMajorVersion>,
		isBusy: Bool
	) -> Bool {
		!plan.selectedCandidates.isEmpty
			&& hasAcknowledged
			&& !selectedGlyphsAreRunning(plan: plan, runningVersions: runningVersions)
			&& !isBusy
	}
}

public enum UninstallOutcomeStatus: Equatable, Sendable {
	case removed
	case skipped
	case failed
}

public struct UninstallOutcome: Identifiable, Equatable, Sendable {
	public let candidate: UninstallCandidate
	public let status: UninstallOutcomeStatus
	public let message: String

	public var id: String { candidate.id }
}

public struct GlyphsUninstallReport: Equatable, Sendable {
	public let outcomes: [UninstallOutcome]

	public var removedCount: Int { outcomes.filter { $0.status == .removed }.count }
	public var failedCount: Int { outcomes.filter { $0.status == .failed }.count }
	public var skippedCount: Int { outcomes.filter { $0.status == .skipped }.count }
	public var isPartialFailure: Bool { removedCount > 0 && failedCount > 0 }
	public var succeeded: Bool { failedCount == 0 }
}

public struct GlyphsUninstallLocations: Sendable {
	public let pluginBundles: [GlyphsMajorVersion: URL]
	public let codexSkillsRoot: URL
	public let claudeCodeSkillsRoot: URL
	public let codexConfig: URL
	public let claudeDesktopConfig: URL
	public let claudeCodeConfig: URL

	public init(
		pluginBundles: [GlyphsMajorVersion: URL],
		codexSkillsRoot: URL,
		claudeCodeSkillsRoot: URL,
		codexConfig: URL,
		claudeDesktopConfig: URL,
		claudeCodeConfig: URL
	) {
		self.pluginBundles = pluginBundles
		self.codexSkillsRoot = codexSkillsRoot
		self.claudeCodeSkillsRoot = claudeCodeSkillsRoot
		self.codexConfig = codexConfig
		self.claudeDesktopConfig = claudeDesktopConfig
		self.claudeCodeConfig = claudeCodeConfig
	}

	public static var live: GlyphsUninstallLocations {
		GlyphsUninstallLocations(
			pluginBundles: Dictionary(uniqueKeysWithValues: GlyphsMajorVersion.allCases.map { version in
				(version, InstallerPaths.glyphsPluginsDir(glyphsVersion: version).appendingPathComponent("Glyphs MCP.glyphsPlugin", isDirectory: true))
			}),
			codexSkillsRoot: InstallerPaths.codexSkillsDir,
			claudeCodeSkillsRoot: InstallerPaths.claudeCodeSkillsDir,
			codexConfig: InstallerPaths.codexConfig,
			claudeDesktopConfig: InstallerPaths.claudeDesktopConfig,
			claudeCodeConfig: InstallerPaths.claudeCodeConfig
		)
	}
}

public enum ConfigRemovalInspection: Equatable, Sendable {
	case removable(String)
	case missing(String)
	case preserved(String)
	case blocked(String)

	public var safetyState: UninstallSafetyState {
		switch self {
		case .removable: return .removable
		case .missing: return .missing
		case .preserved: return .preserved
		case .blocked: return .blocked
		}
	}

	public var detail: String {
		switch self {
		case .removable(let value), .missing(let value), .preserved(let value), .blocked(let value): return value
		}
	}
}

public enum CodexTomlUninstaller {
	public static func inspect(toml: String, serverName: String = InstallerConstants.codexServerName) -> ConfigRemovalInspection {
		guard let range = blockRange(toml: toml, serverName: serverName) else {
			return .missing(NSLocalizedString("No matching Glyphs MCP entry.", comment: "Uninstall missing client config"))
		}
		let block = String(toml[range])
		guard let config = CodexTomlInspector.readServerConfig(toml: block, serverName: serverName),
			  config.url == InstallerConstants.endpointURL.absoluteString else {
			return .preserved(NSLocalizedString("A same-named entry has different settings and will be preserved.", comment: "Uninstall preserves custom client config"))
		}
		return .removable(NSLocalizedString("Matching Glyphs MCP client entry.", comment: "Uninstall matching client config"))
	}

	public static func removingMatchingEntry(toml: String, serverName: String = InstallerConstants.codexServerName) -> String? {
		guard case .removable = inspect(toml: toml, serverName: serverName),
			  let range = blockRange(toml: toml, serverName: serverName) else { return nil }
		return String(toml[..<range.lowerBound]) + String(toml[range.upperBound...])
	}

	private static func blockRange(toml: String, serverName: String) -> Range<String.Index>? {
		let header = "[mcp_servers.\(serverName)]"
		let lines = toml.split(separator: "\n", omittingEmptySubsequences: false)
		guard let startLine = lines.firstIndex(where: { $0.trimmingCharacters(in: .whitespacesAndNewlines) == header }) else { return nil }

		var characterOffset = 0
		for index in 0..<startLine {
			characterOffset += lines[index].count + 1
		}
		let start = toml.index(toml.startIndex, offsetBy: min(characterOffset, toml.count))

		var endLine = lines.count
		if startLine + 1 < lines.count {
			for index in (startLine + 1)..<lines.count where lines[index].trimmingCharacters(in: .whitespaces).hasPrefix("[") {
				endLine = index
				break
			}
		}
		characterOffset = 0
		for index in 0..<endLine {
			characterOffset += lines[index].count + 1
		}
		let end = toml.index(toml.startIndex, offsetBy: min(characterOffset, toml.count))
		return start..<end
	}
}

public enum ClaudeJSONUninstaller {
	public static func inspect(
		json: Data,
		client: UninstallClientKind,
		serverName: String,
		endpoint: String = InstallerConstants.endpointURL.absoluteString
	) -> ConfigRemovalInspection {
		let root: [String: Any]
		do {
			guard let value = try JSONSerialization.jsonObject(with: json) as? [String: Any] else {
				return .blocked(NSLocalizedString("The configuration root is not a JSON object.", comment: "Uninstall malformed client config"))
			}
			root = value
		} catch {
			return .blocked(NSLocalizedString("The configuration could not be parsed and will not be changed.", comment: "Uninstall malformed client config"))
		}
		guard let servers = root["mcpServers"] as? [String: Any], let serverValue = servers[serverName] else {
			return .missing(NSLocalizedString("No matching Glyphs MCP entry.", comment: "Uninstall missing client config"))
		}
		guard let server = serverValue as? [String: Any] else {
			return .preserved(NSLocalizedString("A same-named entry has different settings and will be preserved.", comment: "Uninstall preserves custom client config"))
		}

		let matches: Bool
		switch client {
		case .claudeCode:
			matches = server["type"] as? String == "http" && server["url"] as? String == endpoint
		case .claudeDesktop:
			let args = server["args"] as? [String] ?? []
			matches = server["command"] as? String == "npx" && args.contains("mcp-remote") && args.contains(endpoint)
		case .codex:
			matches = false
		}
		return matches
			? .removable(NSLocalizedString("Matching Glyphs MCP client entry.", comment: "Uninstall matching client config"))
			: .preserved(NSLocalizedString("A same-named entry has different settings and will be preserved.", comment: "Uninstall preserves custom client config"))
	}

	public static func removingMatchingEntry(
		json: Data,
		client: UninstallClientKind,
		serverName: String
	) throws -> Data? {
		guard case .removable = inspect(json: json, client: client, serverName: serverName),
			  var root = try JSONSerialization.jsonObject(with: json) as? [String: Any],
			  var servers = root["mcpServers"] as? [String: Any] else { return nil }
		servers.removeValue(forKey: serverName)
		root["mcpServers"] = servers
		var data = try JSONSerialization.data(withJSONObject: root, options: [.prettyPrinted, .sortedKeys])
		data.append(Data("\n".utf8))
		return data
	}
}

public enum GlyphsUninstallScanner {
	public static func scan(
		managedSkillNames: [String],
		locations: GlyphsUninstallLocations = .live,
		fileManager: FileManager = .default
	) -> GlyphsUninstallPlan {
		var candidates: [UninstallCandidate] = []
		for version in GlyphsMajorVersion.allCases.sorted() {
			guard let path = locations.pluginBundles[version] else { continue }
			let inspection = PluginInstaller.inspectInstalledPlugin(at: path)
			let isInstalled = inspection.mode != .notInstalled
			candidates.append(UninstallCandidate(
				id: "plugin-\(version.rawValue)",
				component: .plugin,
				title: String(format: NSLocalizedString("%@ plug-in", comment: "Uninstall plugin item title"), version.displayName),
				location: path,
				safetyState: isInstalled ? .removable : .missing,
				detail: isInstalled
					? (inspection.isSymlink
						? NSLocalizedString("Development symlink; only the link will be removed.", comment: "Uninstall symlink detail")
						: NSLocalizedString("Installed plug-in bundle.", comment: "Uninstall bundle detail"))
					: NSLocalizedString("Not installed.", comment: "Uninstall missing item"),
				glyphsVersion: version
			))
		}

		let skillRoots: [(String, URL)] = [
			("Codex", locations.codexSkillsRoot),
			("Claude Code", locations.claudeCodeSkillsRoot),
		]
		for (clientName, root) in skillRoots {
			for skillName in Array(Set(managedSkillNames)).sorted() {
				let path = root.appendingPathComponent(skillName, isDirectory: true)
				let exists = itemExists(at: path, fileManager: fileManager)
				candidates.append(UninstallCandidate(
					id: "skill-\(clientName.replacingOccurrences(of: " ", with: "-").lowercased())-\(skillName)",
					component: .skill,
					title: "\(clientName): \(skillName)",
					location: path,
					safetyState: exists ? .removable : .missing,
					detail: exists
						? NSLocalizedString("Exact managed skill destination.", comment: "Uninstall managed skill detail")
						: NSLocalizedString("Not installed.", comment: "Uninstall missing item")
				))
			}
		}

		let clientSpecs: [(UninstallClientKind, URL, String)] = [
			(.codex, locations.codexConfig, InstallerConstants.codexServerName),
			(.claudeDesktop, locations.claudeDesktopConfig, InstallerConstants.claudeDesktopServerName),
			(.claudeCode, locations.claudeCodeConfig, InstallerConstants.claudeCodeServerName),
		]
		for (kind, path, serverName) in clientSpecs {
			let inspection = inspectClient(kind: kind, path: path, serverName: serverName, fileManager: fileManager)
			candidates.append(UninstallCandidate(
				id: "client-\(kind.rawValue)",
				component: .client,
				title: String(format: NSLocalizedString("%@ MCP entry", comment: "Uninstall client item title"), kind.displayName),
				location: path,
				safetyState: inspection.safetyState,
				detail: inspection.detail,
				clientKind: kind
			))
		}

		return GlyphsUninstallPlan(candidates: candidates)
	}

	private static func inspectClient(kind: UninstallClientKind, path: URL, serverName: String, fileManager: FileManager) -> ConfigRemovalInspection {
		guard fileManager.fileExists(atPath: path.path) else {
			return .missing(NSLocalizedString("Configuration file not found.", comment: "Uninstall missing config file"))
		}
		do {
			switch kind {
			case .codex:
				return CodexTomlUninstaller.inspect(toml: try String(contentsOf: path, encoding: .utf8), serverName: serverName)
			case .claudeDesktop, .claudeCode:
				return ClaudeJSONUninstaller.inspect(json: try Data(contentsOf: path), client: kind, serverName: serverName)
			}
		} catch {
			return .blocked(String(format: NSLocalizedString("Could not read configuration: %@", comment: "Uninstall unreadable config"), error.localizedDescription))
		}
	}

	static func itemExists(at url: URL, fileManager: FileManager = .default) -> Bool {
		fileManager.fileExists(atPath: url.path) || (try? fileManager.destinationOfSymbolicLink(atPath: url.path)) != nil
	}
}

public struct GlyphsUninstaller {
	private let fileManager: FileManager
	private let log: (String) -> Void

	public init(fileManager: FileManager = .default, log: @escaping (String) -> Void) {
		self.fileManager = fileManager
		self.log = log
	}

	public func execute(plan: GlyphsUninstallPlan) -> GlyphsUninstallReport {
		var outcomes: [UninstallOutcome] = []
		for candidate in plan.selectedCandidates {
			do {
				let outcome: UninstallOutcome
				switch candidate.component {
				case .plugin, .skill:
					outcome = try removeFileCandidate(candidate)
				case .client:
					outcome = try removeClientCandidate(candidate)
				}
				outcomes.append(outcome)
				log("\(outcome.status == .removed ? "Removed" : "Skipped"): \(candidate.location.path)")
			} catch {
				let message = error.localizedDescription
				outcomes.append(UninstallOutcome(candidate: candidate, status: .failed, message: message))
				log("ERROR: \(candidate.title): \(message)")
			}
		}
		return GlyphsUninstallReport(outcomes: outcomes)
	}

	private func removeFileCandidate(_ candidate: UninstallCandidate) throws -> UninstallOutcome {
		guard GlyphsUninstallScanner.itemExists(at: candidate.location, fileManager: fileManager) else {
			return UninstallOutcome(candidate: candidate, status: .skipped, message: NSLocalizedString("Already absent.", comment: "Uninstall already absent"))
		}
		try fileManager.removeItem(at: candidate.location)
		return UninstallOutcome(candidate: candidate, status: .removed, message: NSLocalizedString("Removed.", comment: "Uninstall removed outcome"))
	}

	private func removeClientCandidate(_ candidate: UninstallCandidate) throws -> UninstallOutcome {
		guard let kind = candidate.clientKind, fileManager.fileExists(atPath: candidate.location.path) else {
			return UninstallOutcome(candidate: candidate, status: .skipped, message: NSLocalizedString("Already absent.", comment: "Uninstall already absent"))
		}

		switch kind {
		case .codex:
			let current = try String(contentsOf: candidate.location, encoding: .utf8)
			guard let updated = CodexTomlUninstaller.removingMatchingEntry(toml: current) else {
				return UninstallOutcome(candidate: candidate, status: .skipped, message: NSLocalizedString("The entry changed and was preserved.", comment: "Uninstall config changed"))
			}
			_ = try FileIO.backupIfExists(candidate.location)
			try FileIO.writeUTF8Atomically(updated, to: candidate.location)
		case .claudeDesktop, .claudeCode:
			let data = try Data(contentsOf: candidate.location)
			let serverName = kind == .claudeDesktop ? InstallerConstants.claudeDesktopServerName : InstallerConstants.claudeCodeServerName
			guard let updated = try ClaudeJSONUninstaller.removingMatchingEntry(json: data, client: kind, serverName: serverName) else {
				return UninstallOutcome(candidate: candidate, status: .skipped, message: NSLocalizedString("The entry changed and was preserved.", comment: "Uninstall config changed"))
			}
			_ = try FileIO.backupIfExists(candidate.location)
			try FileIO.writeAtomically(updated, to: candidate.location)
		}
		return UninstallOutcome(candidate: candidate, status: .removed, message: NSLocalizedString("Removed; configuration backup created.", comment: "Uninstall config removed outcome"))
	}
}
