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
				try await runner.runStreaming(executable: exe, args: ["mcp", "add", "--url", InstallerConstants.endpointURL.absoluteString, InstallerConstants.codexServerName], onLine: log)
			}
			do {
				try await runner.runStreaming(executable: exe, args: ["mcp", "list", "--json"], onLine: log)
				log("Codex configured via CLI.")
				return
			} catch {
				log("Codex CLI verify failed; falling back to config.toml patch.")
			}
		} else {
			log("Codex CLI not found; patching ~/.codex/config.toml.")
		}

		try patchCodexToml(at: InstallerPaths.codexConfig)
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

// MARK: - Claude Desktop

public struct ClaudeDesktopConfigurator {
	let log: (String) -> Void

	public init(log: @escaping (String) -> Void) {
		self.log = log
	}

	public func configure() throws {
		let url = InstallerPaths.claudeDesktopConfig
		log("Configuring Claude Desktop: \(url.path)")
		let (root, _) = try JsonConfig.loadJSON(at: url)

		var mutated = root
		var mcpServers = (mutated["mcpServers"] as? [String: Any]) ?? [:]

		let pathEnv = ClaudeDesktopConfigurator.computePathEnv()
		mcpServers[InstallerConstants.codexServerName] = [
			"command": "npx",
			"args": ["mcp-remote", InstallerConstants.endpointURL.absoluteString],
			"env": ["PATH": pathEnv],
		]
		mutated["mcpServers"] = mcpServers

		_ = try FileIO.backupIfExists(url)
		try JsonConfig.writeJSON(mutated, to: url)
		log("Wrote: \(url.path)")
	}

	public static func computePathEnv() -> String {
		let base = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
		if let node = ToolLocator.findTool(named: "node", extraCandidates: ["/opt/homebrew/bin/node", "/usr/local/bin/node"]) {
			let dir = URL(fileURLWithPath: node).deletingLastPathComponent().path
			if base.contains(dir) { return base }
			return "\(dir):\(base)"
		}
		return base
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
		guard let claude else {
			log("Claude CLI not found; skipping Claude Code auto-config. Command to run manually:")
			log("  claude mcp add --scope user --transport http \(InstallerConstants.claudeCodeServerName) \(InstallerConstants.endpointURL.absoluteString)")
			return
		}
		log("Configuring Claude Code via CLI…")
		try await runner.runStreaming(
			executable: URL(fileURLWithPath: claude),
			args: ["mcp", "add", "--scope", "user", "--transport", "http", InstallerConstants.claudeCodeServerName, InstallerConstants.endpointURL.absoluteString],
			onLine: log
		)
		log("Claude Code configured via CLI.")
	}
}

// MARK: - Antigravity

public struct AntigravityConfigurator {
	let log: (String) -> Void

	public init(log: @escaping (String) -> Void) {
		self.log = log
	}

	public func configure() throws {
		let url = InstallerPaths.antigravityConfig
		log("Configuring Antigravity: \(url.path)")
		let (root, _) = try JsonConfig.loadJSON(at: url)
		var mutated = root
		var mcpServers = (mutated["mcpServers"] as? [String: Any]) ?? [:]

		var entry = (mcpServers[InstallerConstants.codexServerName] as? [String: Any]) ?? [:]
		entry["serverUrl"] = InstallerConstants.endpointURL.absoluteString
		mcpServers[InstallerConstants.codexServerName] = entry
		mutated["mcpServers"] = mcpServers

		_ = try FileIO.backupIfExists(url)
		try JsonConfig.writeJSON(mutated, to: url)
		log("Wrote: \(url.path)")
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
