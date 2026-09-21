import Foundation

// MARK: - Codex

public struct CodexConfigurator {
	let runner: ProcessRunner
	let log: (String) -> Void
	let endpointURL: URL

	public init(runner: ProcessRunner, endpointURL: URL = InstallerConstants.endpointURL, log: @escaping (String) -> Void) {
		self.runner = runner
		self.endpointURL = endpointURL
		self.log = log
	}

	public func configure() async throws {
		log("Configuring Codex…")
		try patchCodexToml(at: InstallerPaths.codexConfig)
		log("Codex configured.")
	}

	private func hasDesiredCodexConfig(at url: URL) -> Bool {
		guard FileManager.default.fileExists(atPath: url.path),
		      let toml = try? String(contentsOf: url, encoding: .utf8),
		      let server = CodexTomlInspector.readServerConfig(toml: toml, serverName: InstallerConstants.codexServerName) else {
			return false
		}
		return server.url == endpointURL.absoluteString
	}

	private func patchCodexToml(at url: URL) throws {
		let desired = CodexTomlBlock(
			header: "[mcp_servers.\(InstallerConstants.codexServerName)]",
			entries: [
				("url", "\"\(endpointURL.absoluteString)\""),
				("enabled", "true"),
				("startup_timeout_sec", "30"),
				("tool_timeout_sec", "120"),
			]
		)

		let existing = (try? String(contentsOf: url, encoding: .utf8)) ?? ""
		let updated = CodexTomlPatcher.patch(toml: existing, block: desired)
		_ = try FileIO.backupIfExists(url)
		try FileIO.writeUTF8Atomically(updated, to: url)
		log("Wrote: \(url.path)")
	}
}

public struct CodexTomlBlock {
	public let header: String
	public let entries: [(String, String)]

	public init(header: String, entries: [(String, String)]) {
		self.header = header
		self.entries = entries
	}
}

public enum CodexTomlPatcher {
	public static func patch(toml: String, block: CodexTomlBlock) -> String {
		var lines = toml.split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
		let header = block.header

		if let headerIndex = lines.firstIndex(where: { $0.trimmingCharacters(in: .whitespacesAndNewlines) == header }) {
			let endIndex = nextHeaderIndex(lines: lines, start: headerIndex + 1) ?? lines.count
			var body = Array(lines[(headerIndex + 1)..<endIndex])

			for (key, value) in block.entries {
				if let i = body.firstIndex(where: { $0.trimmingCharacters(in: .whitespaces).hasPrefix("\(key) ") || $0.trimmingCharacters(in: .whitespaces).hasPrefix("\(key)=") || $0.trimmingCharacters(in: .whitespaces).hasPrefix("\(key)\t") || $0.trimmingCharacters(in: .whitespaces).hasPrefix("\(key) =") }) {
					body[i] = "\(key) = \(value)"
				} else {
					body.append("\(key) = \(value)")
				}
			}

			lines.replaceSubrange((headerIndex + 1)..<endIndex, with: body)
		} else {
			if !lines.isEmpty && !(lines.last ?? "").isEmpty {
				lines.append("")
			}
			lines.append(header)
			for (key, value) in block.entries {
				lines.append("\(key) = \(value)")
			}
			lines.append("")
		}

		return lines.joined(separator: "\n")
	}

	private static func nextHeaderIndex(lines: [String], start: Int) -> Int? {
		guard start < lines.count else { return nil }
		for i in start..<lines.count {
			if lines[i].hasPrefix("[") {
				return i
			}
		}
		return nil
	}
}

// MARK: - Claude Code

public struct ClaudeCodeConfigurator {
	let runner: ProcessRunner
	let log: (String) -> Void
	let endpointURL: URL

	public init(runner: ProcessRunner, endpointURL: URL = InstallerConstants.endpointURL, log: @escaping (String) -> Void) {
		self.runner = runner
		self.endpointURL = endpointURL
		self.log = log
	}

	public func configureIfAvailable() async throws {
		try patchClaudeCodeConfig(at: InstallerPaths.claudeCodeConfig)
		log("Claude Code configured.")
	}

	private func hasDesiredClaudeConfig(at url: URL) -> Bool {
		guard FileManager.default.fileExists(atPath: url.path),
		      let json = try? String(contentsOf: url, encoding: .utf8),
		      let server = ClaudeConfigInspector.readServerConfig(json: json, serverName: InstallerConstants.claudeCodeServerName) else {
			return false
		}
		return server.url == endpointURL.absoluteString
	}

	private func patchClaudeCodeConfig(at url: URL) throws {
        let (existing, _) = try JsonConfig.loadJSON(at: url)
        var root = existing
        _ = try FileIO.backupIfExists(url)

		var mcpServers = root["mcpServers"] as? [String: Any] ?? [:]
		var server = mcpServers[InstallerConstants.claudeCodeServerName] as? [String: Any] ?? [:]
		server["type"] = "http"
		server["url"] = endpointURL.absoluteString
		mcpServers[InstallerConstants.claudeCodeServerName] = server
		root["mcpServers"] = mcpServers

		let data = try JSONSerialization.data(withJSONObject: root, options: [.prettyPrinted, .sortedKeys])
		try FileIO.writeAtomically(data, to: url)
		log("Wrote: \(url.path)")
	}
}

public struct ClaudeDesktopConfigurator {
	let log: (String) -> Void
	let endpointURL: URL

	let proxyCommand: [String]?
    public init(endpointURL: URL = InstallerConstants.endpointURL, proxyCommand: [String]? = nil, log: @escaping (String) -> Void) {
        self.endpointURL = endpointURL; self.proxyCommand = proxyCommand; self.log = log
    }

    public func configure() throws {
		log("Configuring Claude Desktop…")

		try patchClaudeDesktopConfig(at: InstallerPaths.claudeDesktopConfig)
		log("Claude Desktop configured.")
	}

	private func hasDesiredClaudeDesktopConfig(at url: URL) -> Bool {
		guard FileManager.default.fileExists(atPath: url.path),
		      let json = try? String(contentsOf: url, encoding: .utf8),
		      let server = ClaudeConfigInspector.readServerConfig(json: json, serverName: InstallerConstants.claudeDesktopServerName) else {
			return false
		}
		return server.url == endpointURL.absoluteString
	}

	func patchClaudeDesktopConfig(at url: URL) throws {
		let (existingRoot, _) = try JsonConfig.loadJSON(at: url)
		var root = existingRoot
		if FileManager.default.fileExists(atPath: url.path) {
			_ = try FileIO.backupIfExists(url)
		}

		var mcpServers = root["mcpServers"] as? [String: Any] ?? [:]
		var server = mcpServers[InstallerConstants.claudeDesktopServerName] as? [String: Any] ?? [:]
		var env = server["env"] as? [String: Any] ?? [:]
		env["PATH"] = ToolRuntimeEnvironment.mergedPath()
		if let proxyCommand, let command = proxyCommand.first {
            server["command"] = command
            server["args"] = Array(proxyCommand.dropFirst()) + [endpointURL.absoluteString]
            env["PYTHONDONTWRITEBYTECODE"] = "1"; env["PYTHONNOUSERSITE"] = "1"
        } else {
            server["command"] = "npx"
            server["args"] = ["mcp-remote", endpointURL.absoluteString]
        }
		server["env"] = env
		mcpServers[InstallerConstants.claudeDesktopServerName] = server
		root["mcpServers"] = mcpServers

		try JsonConfig.writeJSON(root, to: url)
		log("Wrote: \(url.path)")
	}
}

// MARK: - Agent skills

public struct SkillInstallationResult: Equatable {
    public enum Outcome: String { case installed, current, removed, retired, preservedConflict = "preserved-conflict" }
    public struct Entry: Equatable {
        public let name: String
        public let path: String
        public let outcome: Outcome
        public var compatibilityIssue: String? = nil
        public var backupPath: String? = nil
        public var repairAction: String? {
            guard outcome == .preservedConflict else { return nil }
            return (compatibilityIssue.map { $0 + " " } ?? "")
                + "Review \(path), then use Replace preserved skills (backup)."
        }
    }
    public var entries: [Entry] = []
    public var conflicts: [Entry] { entries.filter { $0.outcome == .preservedConflict } }
    public var summary: String {
        entries.map { "\($0.outcome.rawValue): \($0.path)\($0.backupPath.map { " — backup: " + $0 } ?? "")\($0.repairAction.map { " — " + $0 } ?? "")" }.joined(separator: "\n")
    }
}

public struct AgentSkillBundleInstaller {
	let log: (String) -> Void

	public init(log: @escaping (String) -> Void) {
		self.log = log
	}

	@discardableResult
	public func installCodexSkills(payload: InstallerPayload, overwriteExisting: Bool) throws -> SkillInstallationResult {
		try installManagedSkills(from: payload, to: InstallerPaths.codexSkillsDir, clientName: "Codex", overwriteExisting: overwriteExisting)
	}

	@discardableResult
	public func installClaudeCodeSkills(payload: InstallerPayload, overwriteExisting: Bool) throws -> SkillInstallationResult {
		try installManagedSkills(from: payload, to: InstallerPaths.claudeCodeSkillsDir, clientName: "Claude Code", overwriteExisting: overwriteExisting)
	}

	@discardableResult
	func installManagedSkills(
		from payload: InstallerPayload,
		to destRoot: URL,
		clientName: String,
		overwriteExisting: Bool
	) throws -> SkillInstallationResult {
		let managedSkills = payload.managedSkillDirectories()
		guard !managedSkills.isEmpty else {
			throw InstallerError.userFacing("Installer payload does not contain Glyphs MCP skills.")
		}

		let fm = FileManager.default
		try fm.createDirectory(at: destRoot, withIntermediateDirectories: true)

        let ownershipURL = destRoot.appendingPathComponent(".glyphs-mcp-skills.json")
        let previous = (try? Data(contentsOf: ownershipURL)).flatMap { try? JSONDecoder().decode([String: String].self, from: $0) } ?? [:]
        var ownership = previous
        var result = SkillInstallationResult()

		if overwriteExisting {
			for legacyName in InstallerPayload.legacyManagedSkillNames {
				let legacyDest = destRoot.appendingPathComponent(legacyName, isDirectory: true)
				if itemExists(at: legacyDest) {
                    _ = try backupSkill(legacyDest)
					try fm.removeItem(at: legacyDest)
				}
			}
		}

		for skillDir in managedSkills {
			let dest = destRoot.appendingPathComponent(skillDir.lastPathComponent, isDirectory: true)
            let name = skillDir.lastPathComponent
            let sourceIdentity = try InstallerPayloadManifestResolver.treeIdentity(skillDir)
            let currentIdentity = try? InstallerPayloadManifestResolver.treeIdentity(dest)
            if itemExists(at: dest) {
                if currentIdentity == sourceIdentity {
                    // Identical contents do not grant ownership of an unowned skill.
                    if overwriteExisting || previous[name] == currentIdentity { ownership[name] = sourceIdentity }
                    result.entries.append(.init(name: name, path: dest.path, outcome: .current))
                    continue
                }
                if overwriteExisting || currentIdentity != nil && previous[name] == currentIdentity {
					_ = try backupSkill(dest)
					try fm.removeItem(at: dest)
				} else {
					result.entries.append(.init(name: name, path: dest.path, outcome: .preservedConflict,
                        compatibilityIssue: retiredInterfaceIssue(source: skillDir, destination: dest)))
					continue
				}
			}

			try fm.copyItem(at: skillDir, to: dest)
			ownership[name] = sourceIdentity
			result.entries.append(.init(name: name, path: dest.path, outcome: .installed))
		}

        // Retirement uses the existing hash ledger and explicit replacement action.
        // Legacy markers alone cannot establish that a skill was not user-modified.
        var retiredBackups: [(destination: URL, backup: URL)] = []
        do {
            for dest in retiredPrivateSkillDestinations(from: payload, under: destRoot) {
                let name = dest.lastPathComponent
                let identity = try? InstallerPayloadManifestResolver.treeIdentity(dest)
                guard overwriteExisting || identity != nil && previous[name] == identity else {
                    result.entries.append(.init(name: name, path: dest.path, outcome: .preservedConflict,
                        compatibilityIssue: "Retired private typed-v2 instructions; this family is absent from the lean payload. Replacement archives this folder outside skill discovery; it does not add feature support."))
                    continue
                }
                let backup = try backupSkill(dest)
                retiredBackups.append((dest, backup))
                try fm.removeItem(at: dest)
                ownership.removeValue(forKey: name)
                result.entries.append(.init(name: name, path: dest.path, outcome: .retired, backupPath: backup.path))
            }
            try FileIO.writeAtomically(try JSONEncoder().encode(ownership), to: ownershipURL)
        } catch {
            // Restore only the folders just retired if removal/ledger writing fails.
            // Never overwrite a surviving folder. Exact backups remain available.
            for item in retiredBackups.reversed() {
                do {
                    if !itemExists(at: item.destination) {
                        try fm.copyItem(at: item.backup, to: item.destination)
                    }
                    guard try InstallerPayloadManifestResolver.treeIdentity(item.destination)
                        == InstallerPayloadManifestResolver.treeIdentity(item.backup) else {
                        throw InstallerError.userFacing("Retired skill restoration differs from its backup.")
                    }
                } catch let restoreError {
                    throw InstallerError.userFacing("Skill retirement failed: \(error.localizedDescription). Restore \(item.destination.path) from \(item.backup.path): \(restoreError.localizedDescription)")
                }
            }
            throw error
        }
        log("Glyphs MCP skills for \(clientName):\n" + result.summary)
        return result
	}

    /// A sibling of the discovery root, never a selectable skill directory.
    static func skillBackupRoot(for discoveryRoot: URL) -> URL {
        discoveryRoot.deletingLastPathComponent().appendingPathComponent("glyphs-mcp-skill-backups")
    }

    @discardableResult
    func backupSkill(_ source: URL) throws -> URL {
        let identity = try InstallerPayloadManifestResolver.treeIdentity(source)
        let root = Self.skillBackupRoot(for: source.deletingLastPathComponent())
            .appendingPathComponent(UUID().uuidString.lowercased())
        let destination = root.appendingPathComponent(source.lastPathComponent)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        // Write restoration coordinates before copying. Never remove the source here.
        let record = ["source": source.path, "backup": destination.path, "identity": identity]
        try FileIO.writeAtomically(try JSONEncoder().encode(record), to: root.appendingPathComponent("backup.json"))
        try FileManager.default.copyItem(at: source, to: destination)
        guard try InstallerPayloadManifestResolver.treeIdentity(destination) == identity else {
            throw InstallerError.userFacing("Skill backup verification failed: \(destination.path)")
        }
        log("Skill backup: \(source.path) → \(destination.path)")
        return destination
    }

	public func existingManagedSkillDestinations(from payload: InstallerPayload, under destRoot: URL) -> [URL] {
		let current = payload.managedSkillDirectories().compactMap { skillDir in
			let dest = destRoot.appendingPathComponent(skillDir.lastPathComponent, isDirectory: true)
			return itemExists(at: dest) ? dest : nil
		}
		let legacy = InstallerPayload.legacyManagedSkillNames.compactMap { skillName in
			let dest = destRoot.appendingPathComponent(skillName, isDirectory: true)
			return itemExists(at: dest) ? dest : nil
		}
		return (current + legacy + retiredPrivateSkillDestinations(from: payload, under: destRoot)).sorted { $0.lastPathComponent < $1.lastPathComponent }
	}

    @discardableResult
    public func removeOwnedSkills(from payload: InstallerPayload, under destRoot: URL) throws -> SkillInstallationResult {
        let ownershipURL = destRoot.appendingPathComponent(".glyphs-mcp-skills.json")
        var ownership = (try? Data(contentsOf: ownershipURL))
            .flatMap { try? JSONDecoder().decode([String: String].self, from: $0) } ?? [:]
        var result = SkillInstallationResult()
        for source in payload.managedSkillDirectories() {
            let name = source.lastPathComponent
            let destination = destRoot.appendingPathComponent(name, isDirectory: true)
            guard itemExists(at: destination) else {
                ownership.removeValue(forKey: name)
                continue
            }
            guard let ownedIdentity = ownership[name],
                  let currentIdentity = try? InstallerPayloadManifestResolver.treeIdentity(destination),
                  currentIdentity == ownedIdentity else {
                result.entries.append(.init(name: name, path: destination.path, outcome: .preservedConflict,
                    compatibilityIssue: "This managed skill is modified or unowned and was preserved."))
                continue
            }
            let backup = try backupSkill(destination)
            try FileManager.default.removeItem(at: destination)
            ownership.removeValue(forKey: name)
            result.entries.append(.init(name: name, path: destination.path, outcome: .removed, backupPath: backup.path))
        }
        if !ownership.isEmpty {
            try FileIO.writeAtomically(try JSONEncoder().encode(ownership), to: ownershipURL)
        } else if FileManager.default.fileExists(atPath: ownershipURL.path) {
            try FileManager.default.removeItem(at: ownershipURL)
        }
        return result
    }

    // Known removed private families only; names or owner markers alone do not
    // select a folder. In particular, separate v1 instructions are preserved.
    private func retiredPrivateSkillDestinations(from payload: InstallerPayload, under root: URL) -> [URL] {
        let managed = payload.managedSkillDirectories()
        guard let entry = managed.first(where: { $0.lastPathComponent == "glyphs" }),
              let lean = try? String(contentsOf: entry.appendingPathComponent("SKILL.md"), encoding: .utf8),
              lean.contains("`get_status`"), lean.contains("`read_entities`") else { return [] }
        let names = ["glyphs-mcp-icon-font", "glyphs-mcp-litsquare-metadata", "glyphs-mcp-color-font",
                     "glyphs-mcp-variable-font", "glyphs-mcp-production-audit",
                     "glyphs-mcp-unicode-semantics", "glyphs-mcp-export-validation"]
        let managedNames = Set(managed.map(\.lastPathComponent))
        return names.filter { !managedNames.contains($0) }.compactMap { name in
            let dest = root.appendingPathComponent(name, isDirectory: true)
            guard let text = try? String(contentsOf: dest.appendingPathComponent("SKILL.md"), encoding: .utf8),
                  text.hasPrefix("---\n"),
                  let end = text.dropFirst(4).range(of: "\n---"),
                  text[ text.index(text.startIndex, offsetBy: 4)..<end.lowerBound ]
                    .split(separator: "\n").contains(where: { $0.trimmingCharacters(in: .whitespaces) == "surface: glyphs-mcp-v2" }),
                  text.contains("get_server_info"), text.contains("apiMajor == 2"),
                  !(text.contains("`get_status`") && text.contains("`read_entities`")) else { return nil }
            return dest
        }
    }

    private func retiredInterfaceIssue(source: URL, destination: URL) -> String? {
        guard let shipped = try? String(contentsOf: source.appendingPathComponent("SKILL.md"), encoding: .utf8),
              shipped.contains("`get_status`"), shipped.contains("`read_entities`"),
              let current = try? String(contentsOf: destination.appendingPathComponent("SKILL.md"), encoding: .utf8)
        else { return nil }
        // A lean routing skill may mention retired tools only to reject them.
        // Preserve such edits with the generic conflict action, without guessing.
        guard !(current.contains("`get_status`") && current.contains("`read_entities`")) else { return nil }
        let retired = ["read_document", "execute_python", "preview_change"].filter {
            current.contains("`" + $0 + "`") || current.contains("`" + $0 + "(")
        }
        guard !retired.isEmpty else { return nil }
        return "This skill references retired typed-interface tools (\(retired.joined(separator: ", "))); the selected payload uses the lean nine-tool interface."
    }

	private func itemExists(at url: URL) -> Bool {
		FileManager.default.fileExists(atPath: url.path) || ((try? url.checkResourceIsReachable()) ?? false)
	}
}

// MARK: - Cursor local plug-in

public enum CursorPluginState: Equatable, Sendable {
    case missing
    case installed(version: String)
    case conflict(String)
}

public struct CursorPluginOwnershipReceipt: Codable, Equatable, Sendable {
    public let schemaVersion: Int
    public let owner: String
    public let destination: String
    public let version: String
    public let identity: String

    public init(destination: URL, version: String, identity: String) {
        self.schemaVersion = 1
        self.owner = "glyphs-mcp-installer"
        self.destination = destination.standardizedFileURL.path
        self.version = version
        self.identity = identity
    }
}

public struct CursorPluginInstaller {
    public let source: URL
    public let destination: URL
    public let receiptURL: URL
    public let expectedIdentity: String
    public let version: String
    private let fileManager: FileManager
    private let log: (String) -> Void

    public init(
        source: URL,
        destination: URL = InstallerPaths.cursorPluginDir,
        receiptURL: URL = InstallerPaths.cursorPluginReceipt,
        expectedIdentity: String,
        version: String,
        fileManager: FileManager = .default,
        log: @escaping (String) -> Void
    ) {
        self.source = source
        self.destination = destination
        self.receiptURL = receiptURL
        self.expectedIdentity = expectedIdentity
        self.version = version
        self.fileManager = fileManager
        self.log = log
    }

    public func inspect() -> CursorPluginState {
        guard itemExists(destination) else { return .missing }
        guard recognizedPlugin(at: destination) else {
            return .conflict("An unrecognized item occupies \(destination.path).")
        }
        guard let receipt = readReceipt(), receipt.destination == destination.standardizedFileURL.path else {
            return .conflict("The existing Glyphs MCP Cursor plug-in is not owned by this installer.")
        }
        guard let currentIdentity = try? InstallerPayloadManifestResolver.treeIdentity(destination),
              currentIdentity == receipt.identity else {
            return .conflict("The installer-owned Cursor plug-in was modified and has been preserved.")
        }
        return .installed(version: receipt.version)
    }

    @discardableResult
    public func installOrUpdate() throws -> URL? {
        guard recognizedPlugin(at: source) else {
            throw InstallerError.userFacing("The packaged Cursor plug-in is not recognized.")
        }
        let sourceIdentity = try InstallerPayloadManifestResolver.treeIdentity(source)
        guard sourceIdentity == expectedIdentity else {
            throw InstallerError.userFacing("The packaged Cursor plug-in failed its integrity check.")
        }
        guard manifestVersion(at: source) == version else {
            throw InstallerError.userFacing("The packaged Cursor plug-in version does not match the installer.")
        }

        let existing = itemExists(destination)
        if existing, case .conflict(let message) = inspect() {
            throw InstallerError.userFacing(message)
        }
        try fileManager.createDirectory(at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
        let stage = destination.deletingLastPathComponent()
            .appendingPathComponent(".glyphs-mcp-stage-\(UUID().uuidString)", isDirectory: true)
        let displaced = destination.deletingLastPathComponent()
            .appendingPathComponent(".glyphs-mcp-previous-\(UUID().uuidString)", isDirectory: true)
        try fileManager.copyItem(at: source, to: stage)
        defer {
            if itemExists(stage) { try? fileManager.removeItem(at: stage) }
        }
        guard try InstallerPayloadManifestResolver.treeIdentity(stage) == sourceIdentity else {
            throw InstallerError.userFacing("The staged Cursor plug-in failed its integrity check.")
        }

        let backup = existing ? try verifiedBackup(of: destination) : nil
        let previousReceipt = try? Data(contentsOf: receiptURL)
        _ = try FileIO.backupIfExists(receiptURL)
        do {
            if existing { try fileManager.moveItem(at: destination, to: displaced) }
            try fileManager.moveItem(at: stage, to: destination)
            let receipt = CursorPluginOwnershipReceipt(destination: destination, version: version, identity: sourceIdentity)
            try FileIO.writeAtomically(try JSONEncoder().encode(receipt), to: receiptURL)
            if itemExists(displaced) { try fileManager.removeItem(at: displaced) }
            log("Cursor plug-in \(existing ? "updated" : "installed"): \(destination.path)")
            if let backup { log("Cursor plug-in backup: \(backup.path)") }
            return backup
        } catch {
            if itemExists(destination) { try? fileManager.removeItem(at: destination) }
            if itemExists(displaced) { try? fileManager.moveItem(at: displaced, to: destination) }
            if let previousReceipt {
                try? FileIO.writeAtomically(previousReceipt, to: receiptURL)
            } else if fileManager.fileExists(atPath: receiptURL.path) {
                try? fileManager.removeItem(at: receiptURL)
            }
            throw error
        }
    }

    @discardableResult
    public func remove() throws -> URL? {
        guard itemExists(destination) else { return nil }
        guard case .installed = inspect() else {
            let detail: String
            if case .conflict(let message) = inspect() { detail = message }
            else { detail = "The Cursor plug-in is not installer-owned." }
            throw InstallerError.userFacing(detail)
        }
        let backup = try verifiedBackup(of: destination)
        try fileManager.removeItem(at: destination)
        if fileManager.fileExists(atPath: receiptURL.path) { try fileManager.removeItem(at: receiptURL) }
        log("Cursor plug-in removed. Backup: \(backup.path)")
        return backup
    }

    private func verifiedBackup(of source: URL) throws -> URL {
        let identity = try InstallerPayloadManifestResolver.treeIdentity(source)
        let root = source.deletingLastPathComponent()
            .appendingPathComponent(".glyphs-mcp-backups/\(FileIO.timestampString())-\(UUID().uuidString)", isDirectory: true)
        let backup = root.appendingPathComponent(source.lastPathComponent, isDirectory: true)
        try fileManager.createDirectory(at: root, withIntermediateDirectories: true)
        try fileManager.copyItem(at: source, to: backup)
        guard try InstallerPayloadManifestResolver.treeIdentity(backup) == identity else {
            throw InstallerError.userFacing("Cursor plug-in backup verification failed.")
        }
        return backup
    }

    private func readReceipt() -> CursorPluginOwnershipReceipt? {
        guard let data = try? Data(contentsOf: receiptURL),
              let receipt = try? JSONDecoder().decode(CursorPluginOwnershipReceipt.self, from: data),
              receipt.schemaVersion == 1, receipt.owner == "glyphs-mcp-installer" else { return nil }
        return receipt
    }

    private func recognizedPlugin(at url: URL) -> Bool {
        manifestName(at: url) == "glyphs-mcp"
    }

    private func manifestName(at url: URL) -> String? {
        let manifest = url.appendingPathComponent(".cursor-plugin/plugin.json")
        guard let data = try? Data(contentsOf: manifest),
              let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        return root["name"] as? String
    }

    private func manifestVersion(at url: URL) -> String? {
        let manifest = url.appendingPathComponent(".cursor-plugin/plugin.json")
        guard let data = try? Data(contentsOf: manifest),
              let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        return root["version"] as? String
    }

    private func itemExists(_ url: URL) -> Bool {
        fileManager.fileExists(atPath: url.path) || ((try? url.checkResourceIsReachable()) ?? false)
    }
}

public enum ConnectorConfigurationRemover {
    public static func removeCodex(
        at url: URL = InstallerPaths.codexConfig,
        endpoint: URL = InstallerConstants.endpointURL
    ) throws {
        guard FileManager.default.fileExists(atPath: url.path) else { return }
        let current = try String(contentsOf: url, encoding: .utf8)
        guard let updated = CodexTomlUninstaller.removingMatchingEntry(
            toml: current,
            serverName: InstallerConstants.codexServerName,
            endpoint: endpoint.absoluteString
        ) else {
            throw InstallerError.userFacing("The Codex Glyphs MCP entry is modified and was preserved.")
        }
        _ = try FileIO.backupIfExists(url)
        try FileIO.writeUTF8Atomically(updated, to: url)
    }

    public static func removeClaude(
        client: InstallerClientKind,
        at url: URL,
        serverName: String,
        endpoint: URL = InstallerConstants.endpointURL
    ) throws {
        guard FileManager.default.fileExists(atPath: url.path) else { return }
        let data = try Data(contentsOf: url)
        guard var root = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              var servers = root["mcpServers"] as? [String: Any],
              let server = servers[serverName] as? [String: Any] else { return }
        let matches: Bool
        switch client {
        case .claudeCode:
            matches = server["type"] as? String == "http" && server["url"] as? String == endpoint.absoluteString
        case .claudeDesktop:
            let args = server["args"] as? [String] ?? []
            let command = server["command"] as? String ?? ""
            matches = args.contains(endpoint.absoluteString)
                && ((command == "npx" && args.contains("mcp-remote")) || command.hasSuffix("/python3"))
        case .codex, .cursor:
            matches = false
        }
        guard matches else {
            throw InstallerError.userFacing("The \(client.displayName) Glyphs MCP entry is modified and was preserved.")
        }
        servers.removeValue(forKey: serverName)
        root["mcpServers"] = servers
        _ = try FileIO.backupIfExists(url)
        try JsonConfig.writeJSON(root, to: url)
    }
}

// MARK: - Installer event logs

public enum InstallerLogSource: String, CaseIterable, Identifiable, Sendable {
    case all
    case installer
    case server
    case sidecar
    case sidecarError

    public var id: String { rawValue }
    public var displayName: String {
        switch self {
        case .all: return "All"
        case .installer: return "Installer"
        case .server: return "Server"
        case .sidecar: return "sidecar.log"
        case .sidecarError: return "sidecar-error.log"
        }
    }
}

public final class InstallerEventLogger: @unchecked Sendable {
    public let fileURL: URL
    private let maximumBytes: Int
    private let lock = NSLock()

    public init(
        directory: URL = InstallerPaths.installerLogDirectory,
        fileName: String = "installer-events.log",
        maximumBytes: Int = 1_000_000
    ) {
        self.fileURL = directory.appendingPathComponent(fileName)
        self.maximumBytes = maximumBytes
    }

    public func append(_ message: String, now: Date = Date()) {
        lock.lock()
        defer { lock.unlock() }
        do {
            try FileManager.default.createDirectory(at: fileURL.deletingLastPathComponent(), withIntermediateDirectories: true)
            if let size = try? fileURL.resourceValues(forKeys: [.fileSizeKey]).fileSize,
               size >= maximumBytes {
                let rotated = fileURL.appendingPathExtension("1")
                try? FileManager.default.removeItem(at: rotated)
                try FileManager.default.moveItem(at: fileURL, to: rotated)
            }
            let formatter = ISO8601DateFormatter()
            let line = "[\(formatter.string(from: now))] \(message)\n"
            if !FileManager.default.fileExists(atPath: fileURL.path) {
                try FileIO.writeUTF8Atomically(line, to: fileURL)
            } else {
                let handle = try FileHandle(forWritingTo: fileURL)
                try handle.seekToEnd()
                try handle.write(contentsOf: Data(line.utf8))
                try handle.close()
            }
        } catch {
            // Logging must never make an installation operation fail.
        }
    }
}

public struct InstallerLogCollector: Sendable {
    public let logDirectory: URL
    public let maximumBytesPerSource: Int

    public init(logDirectory: URL = InstallerPaths.installerLogDirectory, maximumBytesPerSource: Int = 512_000) {
        self.logDirectory = logDirectory
        self.maximumBytesPerSource = maximumBytesPerSource
    }

    public func collect(source: InstallerLogSource, serverEvents: [String] = []) -> String {
        let sections: [(InstallerLogSource, String)] = [
            (.installer, readTail(logDirectory.appendingPathComponent("installer-events.log"))),
            (.server, serverEvents.joined(separator: "\n")),
            (.sidecar, readTail(logDirectory.appendingPathComponent("sidecar.log"))),
            (.sidecarError, readTail(logDirectory.appendingPathComponent("sidecar-error.log"))),
        ]
        let selected = source == .all ? sections : sections.filter { $0.0 == source }
        return selected.map { item in
            let body = item.1.isEmpty ? "No log entries available." : item.1
            return "--- \(item.0.displayName) ---\n\(body)"
        }.joined(separator: "\n\n")
    }

    public func redactedDiagnosticReport(_ text: String) -> String {
        var result = text
        let patterns = [
            "(?i)(authorization\\s*[:=]\\s*)(bearer\\s+)?[^\\s\\\"']+",
            "(?i)((?:api[_-]?key|token|secret|password|credential)\\s*[:=]\\s*)[^\\s,;\\\"']+",
            "(?i)(\\\"(?:api[_-]?key|token|secret|password|credential)\\\"\\s*:\\s*\\\")[^\\\"]+",
        ]
        for pattern in patterns {
            guard let expression = try? NSRegularExpression(pattern: pattern) else { continue }
            let range = NSRange(result.startIndex..<result.endIndex, in: result)
            result = expression.stringByReplacingMatches(in: result, range: range, withTemplate: "$1[REDACTED]")
        }
        return result
    }

    private func readTail(_ url: URL) -> String {
        guard let handle = try? FileHandle(forReadingFrom: url) else { return "" }
        defer { try? handle.close() }
        do {
            let end = try handle.seekToEnd()
            let start = end > UInt64(maximumBytesPerSource) ? end - UInt64(maximumBytesPerSource) : 0
            try handle.seek(toOffset: start)
            var data = try handle.readToEnd() ?? Data()
            if start > 0, let newline = data.firstIndex(of: 0x0A) { data.removeSubrange(...newline) }
            return String(decoding: data, as: UTF8.self)
        } catch {
            return "Unable to read \(url.lastPathComponent): \(error.localizedDescription)"
        }
    }
}

// MARK: - JSON helpers

enum JsonConfig {
	static func loadJSON(at url: URL) throws -> ([String: Any], Data?) {
		if !FileManager.default.fileExists(atPath: url.path) {
			return ([:], nil)
		}
		let data = try Data(contentsOf: url)
		if data.isEmpty {
			return ([:], data)
		}
		do {
			let obj = try JSONSerialization.jsonObject(with: data)
			return ((obj as? [String: Any]) ?? [:], data)
		} catch {
			throw InstallerError.userFacing("Failed to parse JSON: \(url.path)")
		}
	}

	static func writeJSON(_ obj: [String: Any], to url: URL) throws {
		var data = try JSONSerialization.data(withJSONObject: obj, options: [.prettyPrinted, .sortedKeys])
		data.append(Data("\n".utf8))
		try FileIO.writeAtomically(data, to: url)
	}
}
