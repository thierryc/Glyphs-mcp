import Foundation

public struct GitHubPluginDownloader {
	public let runner: ProcessRunner
	public let log: (String) -> Void
	public let client: HTTPClienting

	public init(runner: ProcessRunner, log: @escaping (String) -> Void, client: HTTPClienting = URLSessionHTTPClient()) {
		self.runner = runner
		self.log = log
		self.client = client
	}

	public static let zipURL = URL(string: "https://github.com/thierryc/Glyphs-mcp/archive/refs/heads/main.zip")!

	public func downloadAndExtractPluginBundle(timeout: TimeInterval = 30) async throws -> URL {
		log("Downloading latest plug‑in from GitHub…")
		let zipData = try await client.data(from: Self.zipURL, timeout: timeout)
		log("Downloaded \(zipData.count / 1024) KB")

		let tmp = FileManager.default.temporaryDirectory
		let zipPath = tmp.appendingPathComponent("glyphs-mcp-main-\(UUID().uuidString).zip")
		try zipData.write(to: zipPath, options: .atomic)

		let extractDir = tmp.appendingPathComponent("glyphs-mcp-extract-\(UUID().uuidString)", isDirectory: true)
		try FileManager.default.createDirectory(at: extractDir, withIntermediateDirectories: true, attributes: nil)

		let ditto = URL(fileURLWithPath: "/usr/bin/ditto")
		log("Extracting archive…")
		try await runner.runStreaming(executable: ditto, args: ["-x", "-k", zipPath.path, extractDir.path], onLine: { _ in })

		guard let plugin = findPluginBundle(root: extractDir) else {
			throw InstallerError.userFacing("Could not locate Glyphs MCP.glyphsPlugin in the downloaded archive.")
		}
		if let v = PluginVersionReader.readPluginVersion(pluginBundle: plugin) {
			log("GitHub plug‑in version: \(v.displayString)")
		}
		return plugin
	}

	private func findPluginBundle(root: URL) -> URL? {
		let fm = FileManager.default
		guard let e = fm.enumerator(at: root, includingPropertiesForKeys: [.isDirectoryKey], options: [.skipsHiddenFiles]) else { return nil }
		for case let url as URL in e {
			if url.lastPathComponent == "Glyphs MCP.glyphsPlugin" {
				let info = url.appendingPathComponent("Contents/Info.plist")
				if fm.fileExists(atPath: info.path) {
					return url
				}
			}
		}
		return nil
	}
}

