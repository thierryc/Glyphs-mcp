import Foundation

public struct StarterProjectCreator {
	let log: (String) -> Void

	public init(log: @escaping (String) -> Void) {
		self.log = log
	}

	public func createStarterProject(in parent: URL, projectName: String? = nil, bundle: Bundle = .main) throws -> URL {
		let template =
			bundle.url(forResource: "AGENTS", withExtension: "md", subdirectory: "Starter")
			?? bundle.url(forResource: "AGENTS", withExtension: "md")
		if let template {
			return try createStarterProject(in: parent, projectName: projectName, templateURL: template)
		}

		log("WARN: Missing bundled Starter/AGENTS.md resource. Using built‑in template.")
		return try createStarterProject(in: parent, projectName: projectName, templateContent: Self.builtinTemplate)
	}

	public func createStarterProject(in parent: URL, projectName: String? = nil, templateURL: URL) throws -> URL {
		let content = try String(contentsOf: templateURL, encoding: .utf8)
		return try createStarterProject(in: parent, projectName: projectName, templateContent: content)
	}

	private func createStarterProject(in parent: URL, projectName: String? = nil, templateContent: String) throws -> URL {
		let baseNameRaw = (projectName ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
		let baseName = baseNameRaw.isEmpty ? "Glyphs MCP Project" : baseNameRaw
		let fm = FileManager.default
		var target = parent.appendingPathComponent(baseName, isDirectory: true)
		if fm.fileExists(atPath: target.path) {
			var i = 2
			while fm.fileExists(atPath: parent.appendingPathComponent("\(baseName) (\(i))", isDirectory: true).path) {
				i += 1
			}
			target = parent.appendingPathComponent("\(baseName) (\(i))", isDirectory: true)
		}

		try fm.createDirectory(at: target, withIntermediateDirectories: true, attributes: nil)
		let agentsDest = target.appendingPathComponent("AGENTS.md")
		var content = renderTemplate(templateContent, projectName: baseName, serverName: InstallerConstants.codexServerName, endpointURL: InstallerConstants.endpointURL.absoluteString)
		if !content.hasSuffix("\n") { content += "\n" }
		try FileIO.writeUTF8Atomically(content, to: agentsDest)
		log("Wrote: \(agentsDest.path)")
		return target
	}

	private func renderTemplate(_ raw: String, projectName: String, serverName: String, endpointURL: String) -> String {
		raw
			.replacingOccurrences(of: "{{PROJECT_NAME}}", with: projectName)
			.replacingOccurrences(of: "{{SERVER_NAME}}", with: serverName)
			.replacingOccurrences(of: "{{ENDPOINT_URL}}", with: endpointURL)
	}

	private static let builtinTemplate = """
# {{PROJECT_NAME}} — Project directives (Glyphs MCP)

This project assumes the **Glyphs MCP** plug-in is installed and the server is running in Glyphs.

## MCP server
- Server name: `{{SERVER_NAME}}`
- Endpoint: `{{ENDPOINT_URL}}`

## Rules for agents
- Use the `{{SERVER_NAME}}` MCP tools for all Glyphs/font operations; do not guess state.
- Run a connectivity check by calling `tools/list` (or `list_open_fonts`). If it fails, retry once after forcing a new Streamable HTTP session (new SSE connection / new `Mcp-Session-Id`). If you can’t re-handshake in this client, tell me explicitly and I’ll start a new chat.
- If a task might change a font, first call `list_open_fonts` and any relevant read-only tools to collect context.
- Prefer tools that support `dry_run` first; only mutate when explicitly requested and when the tool requires `confirm=true`.
- If connection fails, instruct the user to open Glyphs and run **Edit → Start MCP Server**, then retry.
- If tokens/tool lists are large, select a narrower Tool Profile in **Edit → Glyphs MCP Server Status…** before reconnecting the client.
"""
}
