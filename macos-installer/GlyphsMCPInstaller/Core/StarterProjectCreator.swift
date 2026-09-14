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

	public static let builtinTemplate = """
# {{PROJECT_NAME}}

Use $glyphs-mcp-development for a Glyphs 4 coding session: create or revise
workspace scripts/plugins using its installed offline SDK/API corpus and helper.
Offline creation and validation need no connection, open font or Save.
For OpenType source work use $glyphs-mcp-opentype-features and its native workflow.
For live font-design work use $glyphs on the {{SERVER_NAME}} MCP connection at
{{ENDPOINT_URL}}. Verify its catalog and get_status. Discover the intended font
once with list_documents; retain its connection-specific document_id for fresh
read_entities calls. Rediscover after document_not_found, target change or a
bridge/Glyphs restart, not a missing glyph. Never substitute another open font.
Prepare supported edits with start_job, review get_job, then apply_job. Native
Save accepts changes; existing Undo/Redo and discard_job remain available.
Reconcile uncertain writes with the existing job ID. There is no arbitrary MCP
Python or plugin reload tool. Native installation, execution and restart follow
the user's authorised task; use disposable fonts and preserve unrelated work.
Glyphs 3 uses its separate pinned 1.11.0 contract and skills.

"""
}
