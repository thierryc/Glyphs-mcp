import Foundation

// MARK: - Codex

public struct CodexConfigurator {
	let runner: ProcessRunner
	let log: (String) -> Void

	public init(runner: ProcessRunner, log: @escaping (String) -> Void) {
		self.runner = runner
		self.log = log
	}

	public func configure() async throws {
		log("Configuring Codex…")
		let codex = ToolLocator.findTool(named: "codex", extraCandidates: ["/opt/homebrew/bin/codex", "/usr/local/bin/codex"])

		if let codexPath = codex {
			let exe = URL(fileURLWithPath: codexPath)
			do {
				// Attempt 1 (older docs)
				try await runner.runStreaming(executable: exe, args: ["mcp", "add", InstallerConstants.codexServerName, "--url", InstallerConstants.endpointURL.absoluteString], onLine: log)
			} catch {
				// Attempt 2 (per codex help in current CLI)
				do {
					try await runner.runStreaming(executable: exe, args: ["mcp", "add", "--url", InstallerConstants.endpointURL.absoluteString, InstallerConstants.codexServerName], onLine: log)
				} catch {
					log("Codex CLI add failed; falling back to ~/.codex/config.toml.")
				}
			}
		} else {
			log("Codex CLI not found; patching ~/.codex/config.toml.")
		}

		if hasDesiredCodexConfig(at: InstallerPaths.codexConfig) {
			log("Codex configured.")
			return
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
		return server.url == InstallerConstants.endpointURL.absoluteString
	}

	private func patchCodexToml(at url: URL) throws {
		let desired = CodexTomlBlock(
			header: "[mcp_servers.\(InstallerConstants.codexServerName)]",
			entries: [
				("url", "\"\(InstallerConstants.endpointURL.absoluteString)\""),
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

	public init(runner: ProcessRunner, log: @escaping (String) -> Void) {
		self.runner = runner
		self.log = log
	}

	public func configureIfAvailable() async throws {
		let claude = ToolLocator.findTool(named: "claude", extraCandidates: ["/opt/homebrew/bin/claude", "/usr/local/bin/claude"])
		if let claude {
			log("Configuring Claude Code via CLI…")
			let result = runner.runSyncWithStderr(
				executable: URL(fileURLWithPath: claude),
				args: ["mcp", "add", "--scope", "user", "--transport", "http", InstallerConstants.claudeCodeServerName, InstallerConstants.endpointURL.absoluteString]
			)
			let output = (result.stdout + "\n" + result.stderr).trimmingCharacters(in: .whitespacesAndNewlines)
			if !output.isEmpty {
				for line in output.split(separator: "\n", omittingEmptySubsequences: true) {
					log(String(line))
				}
			}
			if result.exitCode == 0 || ClaudeCliAddInspector.wasAlreadyConfigured(output: output) {
				if ClaudeCliAddInspector.wasAlreadyConfigured(output: output) {
					log("Claude Code was already linked. Keeping the existing configuration.")
				}
			} else {
				log("Claude CLI add failed; falling back to ~/.claude.json.")
			}
		} else {
			log("Claude CLI not found; patching ~/.claude.json.")
		}

		if hasDesiredClaudeConfig(at: InstallerPaths.claudeCodeConfig) {
			log("Claude Code configured.")
			return
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
		return server.url == InstallerConstants.endpointURL.absoluteString
	}

	private func patchClaudeCodeConfig(at url: URL) throws {
		var root: [String: Any] = [:]
		if FileManager.default.fileExists(atPath: url.path),
		   let data = try? Data(contentsOf: url),
		   let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
			root = object
		}

		var mcpServers = root["mcpServers"] as? [String: Any] ?? [:]
		var server = mcpServers[InstallerConstants.claudeCodeServerName] as? [String: Any] ?? [:]
		server["type"] = "http"
		server["url"] = InstallerConstants.endpointURL.absoluteString
		mcpServers[InstallerConstants.claudeCodeServerName] = server
		root["mcpServers"] = mcpServers

		let data = try JSONSerialization.data(withJSONObject: root, options: [.prettyPrinted, .sortedKeys])
		try FileIO.writeAtomically(data, to: url)
		log("Wrote: \(url.path)")
	}
}

// MARK: - Agent skills

public struct AgentSkillBundleInstaller {
	let log: (String) -> Void

	public init(log: @escaping (String) -> Void) {
		self.log = log
	}

	@discardableResult
	public func installCodexSkills(payload: InstallerPayload, overwriteExisting: Bool) throws -> Bool {
		try installManagedSkills(from: payload, to: InstallerPaths.codexSkillsDir, clientName: "Codex", overwriteExisting: overwriteExisting)
	}

	@discardableResult
	public func installClaudeCodeSkills(payload: InstallerPayload, overwriteExisting: Bool) throws -> Bool {
		try installManagedSkills(from: payload, to: InstallerPaths.claudeCodeSkillsDir, clientName: "Claude Code", overwriteExisting: overwriteExisting)
	}

	@discardableResult
	func installManagedSkills(
		from payload: InstallerPayload,
		to destRoot: URL,
		clientName: String,
		overwriteExisting: Bool
	) throws -> Bool {
		let managedSkills = payload.managedSkillDirectories()
		guard !managedSkills.isEmpty else {
			throw InstallerError.userFacing("Installer payload does not contain Glyphs MCP skills.")
		}

		let fm = FileManager.default
		try fm.createDirectory(at: destRoot, withIntermediateDirectories: true)

		var installedNames: [String] = []
		var skippedNames: [String] = []

		for skillDir in managedSkills {
			let dest = destRoot.appendingPathComponent(skillDir.lastPathComponent, isDirectory: true)
			if itemExists(at: dest) {
				if overwriteExisting {
					try fm.removeItem(at: dest)
				} else {
					skippedNames.append(skillDir.lastPathComponent)
					continue
				}
			}

			try fm.copyItem(at: skillDir, to: dest)
			installedNames.append(skillDir.lastPathComponent)
		}

		if !installedNames.isEmpty {
			log("Installed Glyphs MCP skills for \(clientName): \(installedNames.joined(separator: ", "))")
			log("Destination: \(destRoot.path)")
		}
		if !skippedNames.isEmpty {
			log("Kept existing Glyphs MCP skills for \(clientName): \(skippedNames.joined(separator: ", "))")
		}
		return !installedNames.isEmpty
	}

	public func existingManagedSkillDestinations(from payload: InstallerPayload, under destRoot: URL) -> [URL] {
		payload.managedSkillDirectories().compactMap { skillDir in
			let dest = destRoot.appendingPathComponent(skillDir.lastPathComponent, isDirectory: true)
			return itemExists(at: dest) ? dest : nil
		}
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
