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
        if let text = try? String(contentsOf: InstallerPaths.codexConfig, encoding: .utf8),
           CodexTomlInspector.readServerConfig(toml: text, serverName: InstallerConstants.codexServerName) != nil {
            log("Keeping the existing Codex connection and authentication settings."); return
        }

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
        let (root, _) = try JsonConfig.loadJSON(at: InstallerPaths.claudeCodeConfig)
        if (root["mcpServers"] as? [String: Any])?[InstallerConstants.claudeCodeServerName] != nil {
            log("Keeping the existing Claude Code connection and authentication settings."); return
        }

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

        let (root, _) = try JsonConfig.loadJSON(at: InstallerPaths.claudeDesktopConfig)
        if (root["mcpServers"] as? [String: Any])?[InstallerConstants.claudeDesktopServerName] != nil {
            log("Keeping the existing Claude Desktop connection and authentication settings."); return
        }

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
    public enum Outcome: String { case installed, current, retired, preservedConflict = "preserved-conflict" }
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
        return "This skill references retired typed-interface tools (\(retired.joined(separator: ", "))); the selected payload uses the lean seven-tool interface."
    }

	private func itemExists(at url: URL) -> Bool {
		FileManager.default.fileExists(atPath: url.path) || ((try? url.checkResourceIsReachable()) ?? false)
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
