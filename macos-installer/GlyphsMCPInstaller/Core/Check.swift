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

		let codexCli = ToolLocator.findTool(named: "codex", extraCandidates: ["/opt/homebrew/bin/codex", "/usr/local/bin/codex"])
		items.append(.init(
			level: codexCli == nil ? .warn : .ok,
			title: NSLocalizedString("Codex CLI", comment: "Check item title"),
			details: codexCli ?? NSLocalizedString("Not found.", comment: "Check item details")
		))

		let claudeCli = ToolLocator.findTool(named: "claude", extraCandidates: ["/opt/homebrew/bin/claude", "/usr/local/bin/claude"])
		let claudeApp = AppLocator.findApp(namedAnyOf: ["Claude"], home: InstallerPaths.home)
		items.append(.init(
			level: claudeApp == nil ? .warn : .ok,
			title: NSLocalizedString("Claude app", comment: "Check item title"),
			details: claudeApp ?? NSLocalizedString("Not found (searched /Applications and ~/Applications).", comment: "Check item details")
		))
		items.append(.init(
			level: claudeCli == nil ? .warn : .ok,
			title: NSLocalizedString("Claude Code CLI", comment: "Check item title"),
			details: claudeCli ?? NSLocalizedString("Not found.", comment: "Check item details")
		))

		items.append(codexMcpStatus(codexAppPath: codexApp, codexCliPath: codexCli, runner: runner))
		items.append(claudeCodeMcpStatus(claudeAppPath: claudeApp, claudeCliPath: claudeCli, runner: runner))

		return CheckResult(items: items)
	}

	private static func codexMcpStatus(codexAppPath: String?, codexCliPath: String?, runner: ProcessRunner) -> PreflightItem {
		let endpoint = InstallerConstants.endpointURL.absoluteString
		let hasCodexInstall = codexAppPath != nil || codexCliPath != nil
		var cliConfigured = false

		if let codexCliPath {
			let exe = URL(fileURLWithPath: codexCliPath)
			let tryArgs: [[String]] = [
				["mcp", "list", "--json"],
				["mcp", "list"],
			]

			for args in tryArgs {
				let res = runner.runSyncWithStderr(executable: exe, args: args)
				guard res.exitCode == 0 else { continue }

				let combined = (res.stdout + "\n" + res.stderr).trimmingCharacters(in: .whitespacesAndNewlines)
				if let parsed = McpCliInspector.containsServer(jsonLikeText: combined, serverName: InstallerConstants.codexServerName, endpointURL: endpoint) {
					cliConfigured = parsed.isConfigured
					break
				}
			}
		}

		let tomlURL = InstallerPaths.codexConfig
		var configMatches = false
		var configExists = false
		if FileManager.default.fileExists(atPath: tomlURL.path),
		   let toml = try? String(contentsOf: tomlURL, encoding: .utf8) {
			configExists = true
			if let server = CodexTomlInspector.readServerConfig(toml: toml, serverName: InstallerConstants.codexServerName) {
				if server.url == endpoint {
					configMatches = true
				}
			}
		}

		let summary: String
		let level: PreflightItem.Level
		if configMatches {
			summary = "Configured"
			level = .ok
		} else if configExists || cliConfigured {
			summary = "Not configured"
			level = .warn
		} else if hasCodexInstall {
			summary = "Missing"
			level = .warn
		} else {
			summary = "Missing"
			level = .warn
		}

		return .init(
			level: level,
			title: NSLocalizedString("Codex MCP settings", comment: "Check item title"),
			details: summary
		)
	}

	private static func claudeCodeMcpStatus(claudeAppPath: String?, claudeCliPath: String?, runner: ProcessRunner) -> PreflightItem {
		let endpoint = InstallerConstants.endpointURL.absoluteString
		let hasClaudeInstall = claudeAppPath != nil || claudeCliPath != nil
		var cliConfigured = false

		if let claudeCliPath {
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
					cliConfigured = parsed.isConfigured
					break
				}
			}
		}

		let configURL = InstallerPaths.claudeCodeConfig
		var configMatches = false
		var configExists = false
		if FileManager.default.fileExists(atPath: configURL.path),
		   let json = try? String(contentsOf: configURL, encoding: .utf8) {
			configExists = true
			if let server = ClaudeConfigInspector.readServerConfig(json: json, serverName: InstallerConstants.claudeCodeServerName) {
				if server.url == endpoint {
					configMatches = true
				}
			}
		}

		let summary: String
		let level: PreflightItem.Level
		if configMatches {
			summary = "Configured"
			level = .ok
		} else if configExists || cliConfigured {
			summary = configExists ? "Not configured" : "Missing"
			level = .warn
		} else if hasClaudeInstall {
			summary = "Missing"
			level = .warn
		} else {
			summary = "Missing"
			level = .warn
		}

		return .init(
			level: level,
			title: NSLocalizedString("Claude Code MCP settings", comment: "Check item title"),
			details: summary
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

public enum ClaudeCliAddInspector {
	public static func wasAlreadyConfigured(output: String) -> Bool {
		let lowered = output.lowercased()
		return lowered.contains("already exists") || lowered.contains("exists in user config")
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

public enum ClaudeConfigInspector {
	public struct ServerConfig: Equatable {
		public let url: String?
	}

	public static func readServerConfig(json: String, serverName: String) -> ServerConfig? {
		guard let data = json.data(using: .utf8),
		      let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
		      let mcpServers = object["mcpServers"] as? [String: Any],
		      let server = mcpServers[serverName] as? [String: Any] else {
			return nil
		}

		if let url = server["url"] as? String {
			return ServerConfig(url: url)
		}
		if let transport = server["transport"] as? [String: Any], let url = transport["url"] as? String {
			return ServerConfig(url: url)
		}
		return ServerConfig(url: nil)
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
		return containsServerInPlainTextList(output: trimmed, serverName: serverName, endpointURL: endpointURL)
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

	private static func containsServerInPlainTextList(output: String, serverName: String, endpointURL: String) -> Result? {
		let lines = output
			.split(separator: "\n", omittingEmptySubsequences: false)
			.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
			.filter { !$0.isEmpty }

		let looksLikeListOutput = lines.contains(where: { $0.hasPrefix("Name") && ($0.contains("Url") || $0.contains("Command")) })
		guard looksLikeListOutput else { return nil }

		if let matchingLine = lines.first(where: { $0.contains(serverName) }) {
			let matches = matchingLine.contains(endpointURL)
			return Result(
				isConfigured: matches,
				details: "CLI: server found in list (\(matches ? "url matches" : "url mismatch"))."
			)
		}

		if lines.contains(where: { $0.contains(endpointURL) }) {
			return Result(isConfigured: true, details: "CLI: endpoint found in list (name omitted by parser).")
		}

		return Result(isConfigured: false, details: "CLI: server not found.")
	}
}
