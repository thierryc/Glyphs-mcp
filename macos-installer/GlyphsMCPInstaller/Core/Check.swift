import AppKit
import Foundation
import SwiftUI

public struct CheckResult {
	public var items: [PreflightItem]

	public init(items: [PreflightItem]) {
		self.items = items
	}

	public static let empty = CheckResult(items: [])
}

public enum Check {
	public static func scan() -> CheckResult {
		var items: [PreflightItem] = []
		let fm = FileManager.default
		let runner = ProcessRunner()

		let glyphsBase = InstallerPaths.glyphsBaseDir
		let pluginsDir = InstallerPaths.glyphsPluginsDir

		items.append(.init(
			level: fm.fileExists(atPath: glyphsBase.path) ? .ok : .warn,
			title: NSLocalizedString("Glyphs base folder", comment: "Check item title"),
			details: glyphsBase.path
		))
		items.append(.init(
			level: fm.fileExists(atPath: pluginsDir.path) ? .ok : .warn,
			title: NSLocalizedString("Glyphs plugins folder", comment: "Check item title"),
			details: pluginsDir.path
		))

		let installedPlugin = pluginsDir.appendingPathComponent("Glyphs MCP.glyphsPlugin", isDirectory: true)
		if let installedVer = Preflight.readPluginVersionFromBundle(pluginBundle: installedPlugin) {
			items.append(.init(
				level: .ok,
				title: NSLocalizedString("Glyphs MCP plug‑in", comment: "Check item title"),
				details: String(format: NSLocalizedString("Installed: %@", comment: "Check item details"), installedVer)
			))
		} else {
			items.append(.init(
				level: .warn,
				title: NSLocalizedString("Glyphs MCP plug‑in", comment: "Check item title"),
				details: NSLocalizedString("Not installed.", comment: "Check item details")
			))
		}

		let pluginsCount = (try? fm.contentsOfDirectory(atPath: pluginsDir.path).filter { $0.hasSuffix(".glyphsPlugin") }.count) ?? 0
		items.append(.init(level: .ok, title: NSLocalizedString("Glyphs plugins detected", comment: "Check item title"), details: "\(pluginsCount)"))

		let codexApp = AppLocator.findApp(namedAnyOf: ["Codex"], home: InstallerPaths.home)
		items.append(.init(
			level: codexApp == nil ? .warn : .ok,
			title: NSLocalizedString("Codex app", comment: "Check item title"),
			details: codexApp ?? NSLocalizedString("Not found (searched /Applications and ~/Applications).", comment: "Check item details")
		))

		let claudeApp = AppLocator.findApp(namedAnyOf: ["Claude", "Claude Desktop"], home: InstallerPaths.home)
		items.append(.init(
			level: claudeApp == nil ? .warn : .ok,
			title: NSLocalizedString("Claude app", comment: "Check item title"),
			details: claudeApp ?? NSLocalizedString("Not found (searched /Applications and ~/Applications).", comment: "Check item details")
		))

		let codexCli = ToolLocator.findTool(named: "codex", extraCandidates: ["/opt/homebrew/bin/codex", "/usr/local/bin/codex"])
		items.append(.init(
			level: codexCli == nil ? .warn : .ok,
			title: NSLocalizedString("Codex CLI", comment: "Check item title"),
			details: codexCli ?? NSLocalizedString("Not found.", comment: "Check item details")
		))

		let claudeCli = ToolLocator.findTool(named: "claude", extraCandidates: ["/opt/homebrew/bin/claude", "/usr/local/bin/claude"])
		items.append(.init(
			level: claudeCli == nil ? .warn : .ok,
			title: NSLocalizedString("Claude CLI (Claude Code)", comment: "Check item title"),
			details: claudeCli ?? NSLocalizedString("Not found.", comment: "Check item details")
		))

		let node = ToolLocator.findTool(named: "node", extraCandidates: ["/opt/homebrew/bin/node", "/usr/local/bin/node"])
		items.append(.init(
			level: node == nil ? .warn : .ok,
			title: NSLocalizedString("Node", comment: "Check item title"),
			details: node ?? NSLocalizedString("Not found.", comment: "Check item details")
		))

		let npx = ToolLocator.findTool(named: "npx", extraCandidates: ["/opt/homebrew/bin/npx", "/usr/local/bin/npx"])
		items.append(.init(
			level: npx == nil ? .warn : .ok,
			title: NSLocalizedString("npx", comment: "Check item title"),
			details: npx ?? NSLocalizedString("Not found.", comment: "Check item details")
		))

		items.append(codexMcpStatus(codexCliPath: codexCli, runner: runner))
		items.append(claudeDesktopMcpStatus())
		items.append(antigravityMcpStatus())
		items.append(claudeCodeMcpStatus(claudeCliPath: claudeCli, runner: runner))

		return CheckResult(items: items)
	}

	private static func codexMcpStatus(codexCliPath: String?, runner: ProcessRunner) -> PreflightItem {
		let endpoint = InstallerConstants.endpointURL.absoluteString
		var sources: [String] = []
		var ok = false
		var warnOnly = false

		if let codexCliPath {
			let res = runner.runSyncWithStderr(executable: URL(fileURLWithPath: codexCliPath), args: ["mcp", "list", "--json"])
			let combined = (res.stdout + "\n" + res.stderr).trimmingCharacters(in: .whitespacesAndNewlines)
			if res.exitCode == 0, let parsed = McpCliInspector.containsServer(jsonLikeText: combined, serverName: InstallerConstants.codexServerName, endpointURL: endpoint) {
				ok = parsed.isConfigured
				sources.append(parsed.details)
			} else if res.exitCode == 0 {
				sources.append("CLI: list succeeded but could not parse output.")
				warnOnly = true
			} else {
				sources.append("CLI: list failed (\(res.exitCode)).")
				warnOnly = true
			}
		} else {
			sources.append("CLI: not installed.")
		}

		let tomlURL = InstallerPaths.codexConfig
		if FileManager.default.fileExists(atPath: tomlURL.path),
		   let toml = try? String(contentsOf: tomlURL, encoding: .utf8) {
			if let server = CodexTomlInspector.readServerConfig(toml: toml, serverName: InstallerConstants.codexServerName) {
				if server.url == endpoint {
					ok = true
					sources.append("config.toml: url matches.")
				} else {
					sources.append("config.toml: url mismatch (\(server.url ?? "missing")).")
					warnOnly = true
				}
			} else {
				sources.append("config.toml: server block missing.")
				warnOnly = true
			}
		} else {
			sources.append("config.toml: missing.")
		}

			let level: PreflightItem.Level = ok ? .ok : (warnOnly ? .warn : .bad)
			return .init(
				level: level,
				title: NSLocalizedString("Codex MCP settings", comment: "Check item title"),
				details: sources.joined(separator: " ")
			)
		}

	private static func claudeDesktopMcpStatus() -> PreflightItem {
		let endpoint = InstallerConstants.endpointURL.absoluteString
		let url = InstallerPaths.claudeDesktopConfig
		do {
				let (root, raw) = try JsonConfig.loadJSON(at: url)
				guard raw != nil else {
					return .init(
						level: .warn,
						title: NSLocalizedString("Claude Desktop MCP settings", comment: "Check item title"),
						details: String(format: NSLocalizedString("Config not found: %@", comment: "Check item details"), url.path)
					)
				}
				let status = ClaudeDesktopInspector.inspect(root: root, serverName: InstallerConstants.codexServerName, endpointURL: endpoint)
				return .init(
					level: status.level,
					title: NSLocalizedString("Claude Desktop MCP settings", comment: "Check item title"),
					details: status.details + " (\(url.path))"
				)
			} catch {
				return .init(
					level: .bad,
					title: NSLocalizedString("Claude Desktop MCP settings", comment: "Check item title"),
					details: String(format: NSLocalizedString("Failed to read/parse JSON: %@", comment: "Check item details"), url.path)
				)
			}
		}

	private static func antigravityMcpStatus() -> PreflightItem {
		let endpoint = InstallerConstants.endpointURL.absoluteString
		let url = InstallerPaths.antigravityConfig
		do {
				let (root, raw) = try JsonConfig.loadJSON(at: url)
				guard raw != nil else {
					return .init(
						level: .warn,
						title: NSLocalizedString("Antigravity MCP settings", comment: "Check item title"),
						details: String(format: NSLocalizedString("Config not found: %@", comment: "Check item details"), url.path)
					)
				}
				let status = AntigravityInspector.inspect(root: root, serverName: InstallerConstants.codexServerName, endpointURL: endpoint)
				return .init(
					level: status.level,
					title: NSLocalizedString("Antigravity MCP settings", comment: "Check item title"),
					details: status.details + " (\(url.path))"
				)
			} catch {
				return .init(
					level: .bad,
					title: NSLocalizedString("Antigravity MCP settings", comment: "Check item title"),
					details: String(format: NSLocalizedString("Failed to read/parse JSON: %@", comment: "Check item details"), url.path)
				)
			}
		}

	private static func claudeCodeMcpStatus(claudeCliPath: String?, runner: ProcessRunner) -> PreflightItem {
			let endpoint = InstallerConstants.endpointURL.absoluteString
			guard let claudeCliPath else {
				return .init(
					level: .warn,
					title: NSLocalizedString("Claude Code MCP settings", comment: "Check item title"),
					details: NSLocalizedString("Claude CLI not installed; cannot verify.", comment: "Check item details")
				)
			}

		let exe = URL(fileURLWithPath: claudeCliPath)
		let tryArgs: [[String]] = [
			["mcp", "list", "--json"],
			["mcp", "list"],
		]
		for args in tryArgs {
			let res = runner.runSyncWithStderr(executable: exe, args: args)
			if res.exitCode != 0 { continue }
				let combined = (res.stdout + "\n" + res.stderr).trimmingCharacters(in: .whitespacesAndNewlines)
				if let parsed = McpCliInspector.containsServer(jsonLikeText: combined, serverName: InstallerConstants.claudeCodeServerName, endpointURL: endpoint) {
					return .init(
						level: parsed.isConfigured ? .ok : .warn,
						title: NSLocalizedString("Claude Code MCP settings", comment: "Check item title"),
						details: parsed.details
					)
				}
				if let noServers = ClaudeCliListInspector.detectNoServersConfigured(output: combined) {
					return .init(
						level: .warn,
						title: NSLocalizedString("Claude Code MCP settings", comment: "Check item title"),
						details: "\(noServers) Run: claude mcp add --scope user --transport http \(InstallerConstants.claudeCodeServerName) \(endpoint)"
					)
				}
				if combined.contains(InstallerConstants.claudeCodeServerName) || combined.contains(endpoint) {
					return .init(
						level: .ok,
						title: NSLocalizedString("Claude Code MCP settings", comment: "Check item title"),
						details: NSLocalizedString("CLI output contains the server; verification is heuristic.", comment: "Check item details")
					)
				}
				return .init(
					level: .warn,
					title: NSLocalizedString("Claude Code MCP settings", comment: "Check item title"),
					details: NSLocalizedString("CLI list succeeded but server not found.", comment: "Check item details")
				)
			}

			return .init(
				level: .warn,
				title: NSLocalizedString("Claude Code MCP settings", comment: "Check item title"),
				details: NSLocalizedString("Claude CLI present, but cannot verify MCP configuration (no supported list command).", comment: "Check item details")
			)
		}
	}

public enum ClaudeCliListInspector {
	public static func detectNoServersConfigured(output: String) -> String? {
		let lowered = output.lowercased()
		if lowered.contains("no mcp servers configured") {
			return "No MCP servers configured."
		}
		if lowered.contains("use `claude mcp add`") || lowered.contains("use 'claude mcp add'") {
			return "No MCP servers configured."
		}
		return nil
	}
}

enum AppLocator {
	static func findApp(namedAnyOf names: [String], home: URL) -> String? {
		let fm = FileManager.default
		let appRoots = [
			URL(fileURLWithPath: "/Applications", isDirectory: true),
			home.appendingPathComponent("Applications", isDirectory: true),
		]

		for name in names {
			for root in appRoots {
				let candidate = root.appendingPathComponent("\(name).app", isDirectory: true)
				if fm.fileExists(atPath: candidate.path) {
					return candidate.path
				}
			}
		}
		return nil
	}
}

public enum CodexTomlInspector {
	public struct ServerConfig: Equatable {
		public let url: String?
		public let enabled: Bool?
	}

	public static func readServerConfig(toml: String, serverName: String) -> ServerConfig? {
		let header = "[mcp_servers.\(serverName)]"
		let lines = toml.split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
		guard let headerIndex = lines.firstIndex(where: { $0.trimmingCharacters(in: .whitespacesAndNewlines) == header }) else {
			return nil
		}
		let endIndex = nextHeaderIndex(lines: lines, start: headerIndex + 1) ?? lines.count
		let body = Array(lines[(headerIndex + 1)..<endIndex])

		var url: String?
		var enabled: Bool?
		for raw in body {
			let line = raw.trimmingCharacters(in: .whitespacesAndNewlines)
			if line.hasPrefix("#") || line.isEmpty { continue }
			guard let eq = line.firstIndex(of: "=") else { continue }
			let key = line[..<eq].trimmingCharacters(in: .whitespacesAndNewlines)
			let valueRaw = line[line.index(after: eq)...].trimmingCharacters(in: .whitespacesAndNewlines)
			if key == "url" {
				url = valueRaw.trimmingCharacters(in: CharacterSet(charactersIn: "\""))
			} else if key == "enabled" {
				enabled = (valueRaw == "true")
			}
		}
		return ServerConfig(url: url, enabled: enabled)
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

enum McpCliInspector {
	struct Result {
		let isConfigured: Bool
		let details: String
	}

	static func containsServer(jsonLikeText: String, serverName: String, endpointURL: String) -> Result? {
		let trimmed = jsonLikeText.trimmingCharacters(in: .whitespacesAndNewlines)
		if trimmed.hasPrefix("{") || trimmed.hasPrefix("[") {
			if let data = trimmed.data(using: .utf8),
			   let obj = try? JSONSerialization.jsonObject(with: data) {
				if let found = findServer(in: obj, serverName: serverName) {
					let matches = found.contains(endpointURL)
					return Result(isConfigured: matches, details: "CLI: server found (\(matches ? "url matches" : "url mismatch")).")
				}
				return Result(isConfigured: false, details: "CLI: server not found.")
			}
		}
		return nil
	}

	private static func findServer(in obj: Any, serverName: String) -> String? {
		if let dict = obj as? [String: Any] {
			if let name = dict["name"] as? String, name == serverName {
				if let url = dict["url"] as? String { return url }
				if let serverUrl = dict["serverUrl"] as? String { return serverUrl }
				return String(describing: dict)
			}
			for (_, v) in dict {
				if let hit = findServer(in: v, serverName: serverName) { return hit }
			}
			return nil
		}
		if let arr = obj as? [Any] {
			for v in arr {
				if let hit = findServer(in: v, serverName: serverName) { return hit }
			}
		}
		return nil
	}
}

public enum ClaudeDesktopInspector {
	public struct Status: Equatable {
		public let level: PreflightItem.Level
		public let details: String

		public init(level: PreflightItem.Level, details: String) {
			self.level = level
			self.details = details
		}
	}

	public static func inspect(root: [String: Any], serverName: String, endpointURL: String) -> Status {
		guard let mcpServers = root["mcpServers"] as? [String: Any] else {
			return Status(level: .warn, details: "mcpServers missing.")
		}
		guard let entry = mcpServers[serverName] as? [String: Any] else {
			return Status(level: .warn, details: "Server entry missing.")
		}
		let command = entry["command"] as? String
		let args = entry["args"] as? [Any]
		let env = entry["env"] as? [String: Any]
		let pathEnv = (env?["PATH"] as? String) ?? ""

		let argsStrings = (args as? [String]) ?? args?.map { String(describing: $0) } ?? []
		let argsOk = argsStrings.contains("mcp-remote") && argsStrings.contains(endpointURL)
		let commandOk = (command == "npx")

		if commandOk && argsOk {
			let extra = pathEnv.isEmpty ? "PATH not set." : "PATH set."
			return Status(level: .ok, details: "Configured (npx mcp-remote). \(extra)")
		}

		return Status(level: .warn, details: "Present but does not match expected command/args.")
	}
}

public enum AntigravityInspector {
	public struct Status: Equatable {
		public let level: PreflightItem.Level
		public let details: String

		public init(level: PreflightItem.Level, details: String) {
			self.level = level
			self.details = details
		}
	}

	public static func inspect(root: [String: Any], serverName: String, endpointURL: String) -> Status {
		guard let mcpServers = root["mcpServers"] as? [String: Any] else {
			return Status(level: .warn, details: "mcpServers missing.")
		}
		guard let entry = mcpServers[serverName] as? [String: Any] else {
			return Status(level: .warn, details: "Server entry missing.")
		}
		let url = entry["serverUrl"] as? String
		if url == endpointURL {
			return Status(level: .ok, details: "Configured (serverUrl matches).")
		}
		return Status(level: .warn, details: "serverUrl mismatch (\(url ?? "missing")).")
	}
}
