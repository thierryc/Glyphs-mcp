import XCTest
import Foundation
@testable import GlyphsMCPInstallerCore

final class GlyphsMCPInstallerTests: XCTestCase {
	private struct FakeHTTPClient: HTTPClienting {
		let dataToReturn: Data
		var onRequest: (() -> Void)?

		func data(from url: URL, timeout: TimeInterval) async throws -> Data {
			_ = url
			_ = timeout
			onRequest?()
			return dataToReturn
		}
	}

	func testTomlPatcherAddsBlockWhenMissing() {
		let toml = "model = \"x\"\n\n[mcp_servers.other]\nurl = \"http://example.com\"\n"
		let block = CodexTomlBlock(header: "[mcp_servers.glyphs-mcp-server]", entries: [("url", "\"http://127.0.0.1:9680/mcp/\""), ("enabled", "true")])
		let out = CodexTomlPatcher.patch(toml: toml, block: block)
		XCTAssertTrue(out.contains("[mcp_servers.glyphs-mcp-server]"))
		XCTAssertTrue(out.contains("url = \"http://127.0.0.1:9680/mcp/\""))
		XCTAssertTrue(out.contains("enabled = true"))
		XCTAssertTrue(out.contains("[mcp_servers.other]"))
	}

	func testTomlPatcherUpdatesExistingBlock() {
		let toml = """
model = "x"

[mcp_servers.glyphs-mcp-server]
url = "http://old"
enabled = false

[mcp_servers.other]
url = "http://example.com"
"""
		let block = CodexTomlBlock(header: "[mcp_servers.glyphs-mcp-server]", entries: [("url", "\"http://127.0.0.1:9680/mcp/\""), ("enabled", "true")])
		let out = CodexTomlPatcher.patch(toml: toml, block: block)
		XCTAssertTrue(out.contains("url = \"http://127.0.0.1:9680/mcp/\""))
		XCTAssertTrue(out.contains("enabled = true"))
		XCTAssertTrue(out.contains("[mcp_servers.other]"))
	}

	func testStarterFolderNamingDoesNotOverwrite() throws {
		let tmp = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
		try FileManager.default.createDirectory(at: tmp, withIntermediateDirectories: true, attributes: nil)
		let first = tmp.appendingPathComponent("Glyphs MCP Project", isDirectory: true)
		try FileManager.default.createDirectory(at: first, withIntermediateDirectories: true, attributes: nil)

		let creator = StarterProjectCreator(log: { _ in })
		let templateDir = tmp.appendingPathComponent("Starter", isDirectory: true)
		try FileManager.default.createDirectory(at: templateDir, withIntermediateDirectories: true, attributes: nil)
		let template = templateDir.appendingPathComponent("AGENTS.md")
		try "# test\n".write(to: template, atomically: true, encoding: .utf8)

		let created = try creator.createStarterProject(in: tmp, templateURL: template)
		XCTAssertTrue(created.lastPathComponent.hasPrefix("Glyphs MCP Project ("))
		XCTAssertTrue(FileManager.default.fileExists(atPath: created.appendingPathComponent("AGENTS.md").path))
	}

	func testCodexTomlInspectorReadsServerUrl() {
		let toml = """
[mcp_servers.glyphs-mcp-server]
url = "http://127.0.0.1:9680/mcp/"
enabled = true

[mcp_servers.other]
url = "http://example.com"
"""
		let cfg = CodexTomlInspector.readServerConfig(toml: toml, serverName: "glyphs-mcp-server")
		XCTAssertEqual(cfg?.url, "http://127.0.0.1:9680/mcp/")
		XCTAssertEqual(cfg?.enabled, true)
	}

	func testClaudeDesktopInspectorDetectsConfiguredServer() {
		let root: [String: Any] = [
			"mcpServers": [
				"glyphs-mcp-server": [
					"command": "npx",
					"args": ["mcp-remote", "http://127.0.0.1:9680/mcp/"],
					"env": ["PATH": "/usr/bin:/bin"],
				],
			],
		]
		let status = ClaudeDesktopInspector.inspect(root: root, serverName: "glyphs-mcp-server", endpointURL: "http://127.0.0.1:9680/mcp/")
		XCTAssertEqual(status.level, .ok)
	}

	func testAntigravityInspectorDetectsConfiguredServerUrl() {
		let root: [String: Any] = [
			"mcpServers": [
				"glyphs-mcp-server": [
					"serverUrl": "http://127.0.0.1:9680/mcp/",
					"headers": ["X-Test": "1"],
				],
			],
		]
		let status = AntigravityInspector.inspect(root: root, serverName: "glyphs-mcp-server", endpointURL: "http://127.0.0.1:9680/mcp/")
		XCTAssertEqual(status.level, .ok)
	}

	func testClaudeCliListInspectorDetectsNoServersConfigured() {
		let output = "No MCP servers configured. Use `claude mcp add` to add a server."
		XCTAssertEqual(ClaudeCliListInspector.detectNoServersConfigured(output: output), "No MCP servers configured.")
	}

	func testPythonPreflightSummaryShowsGoodAndIgnoredCounts() {
		let scan = PythonDetector.PythonScanResult(
			good: [
				PythonCandidate(path: "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12", version: "3.12.3", source: "python.org"),
				PythonCandidate(path: "/opt/homebrew/bin/python3.11", version: "3.11.9", source: "homebrew"),
			],
			tooOldCount: 2,
			tooNewCount: 1,
			unknownCount: 3
		)

		let summary = PythonDetector.formatSummary(scan: scan)
		XCTAssertTrue(summary.contains("Good candidates: 2"), summary)
		XCTAssertTrue(summary.contains("Ignored: 2 too old, 1 too new, 3 unknown"), summary)
		XCTAssertTrue(summary.contains("Top: 3.12.3 (python.org)"), summary)
		XCTAssertTrue(summary.contains("Candidates:"), summary)
	}

	func testPythonPreflightSummaryHandlesNoSupportedInterpreters() {
		let scan = PythonDetector.PythonScanResult(good: [], tooOldCount: 1, tooNewCount: 0, unknownCount: 0)
		let summary = PythonDetector.formatSummary(scan: scan)
		XCTAssertTrue(summary.contains("No supported interpreters"), summary)
		XCTAssertTrue(summary.contains("Ignored: 1 too old"), summary)
	}

	func testPluginVersionKeyComparesNumericTuples() {
		let a = PluginVersionKey("1.0.5")
		let b = PluginVersionKey("1.0.12")
		XCTAssertTrue(a < b)
		XCTAssertFalse(b < a)
	}

	func testPluginVersionKeyIgnoresSuffix() {
		let a = PluginVersionKey("1.2.3-beta1")
		let b = PluginVersionKey("1.2.4")
		XCTAssertTrue(a < b)
	}

	func testPluginVersionReaderParsesInfoPlist() throws {
		let plist = """
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleShortVersionString</key>
  <string>1.0.5</string>
  <key>CFBundleVersion</key>
  <string>1.0.5</string>
</dict>
</plist>
"""
		let data = try XCTUnwrap(plist.data(using: .utf8))
		let v = try XCTUnwrap(PluginVersionReader.readInfoPlist(data: data))
		XCTAssertEqual(v.shortVersion, "1.0.5")
		XCTAssertEqual(v.buildVersion, "1.0.5")
		XCTAssertEqual(v.displayString, "1.0.5")
	}

	func testStarterProjectFallsBackToBuiltInTemplateWhenResourceMissing() throws {
		let tmp = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
		try FileManager.default.createDirectory(at: tmp, withIntermediateDirectories: true, attributes: nil)

		let creator = StarterProjectCreator(log: { _ in })
		let created = try creator.createStarterProject(in: tmp, projectName: "My Fonts", bundle: Bundle(for: Self.self))

		let agents = created.appendingPathComponent("AGENTS.md")
		let content = try String(contentsOf: agents, encoding: .utf8)
		XCTAssertTrue(content.contains("My Fonts"), content)
		XCTAssertTrue(content.contains(InstallerConstants.codexServerName), content)
		XCTAssertTrue(content.contains(InstallerConstants.endpointURL.absoluteString), content)
	}

	func testFileIOWriteUTF8AtomicallyAddsTrailingNewline() throws {
		let tmp = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
		try FileManager.default.createDirectory(at: tmp, withIntermediateDirectories: true, attributes: nil)
		let file = tmp.appendingPathComponent("x.txt")

		try FileIO.writeUTF8Atomically("hello", to: file)
		let out = try String(contentsOf: file, encoding: .utf8)
		XCTAssertEqual(out, "hello\n")
	}

	func testFileIOBackupIfExistsCreatesCopy() throws {
		let tmp = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
		try FileManager.default.createDirectory(at: tmp, withIntermediateDirectories: true, attributes: nil)
		let file = tmp.appendingPathComponent("config.json")
		try "{\"ok\":true}\n".write(to: file, atomically: true, encoding: .utf8)

		let backup = try XCTUnwrap(FileIO.backupIfExists(file))
		XCTAssertTrue(FileManager.default.fileExists(atPath: backup.path))
		XCTAssertTrue(backup.pathExtension.hasPrefix("bak-"), backup.path)
		XCTAssertEqual(try String(contentsOf: backup, encoding: .utf8), "{\"ok\":true}\n")
	}

	func testInstallerPayloadResolveFindsPayloadInBundleResources() throws {
		let tmp = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
		let bundleURL = tmp.appendingPathComponent("Test.bundle", isDirectory: true)
		let contents = bundleURL.appendingPathComponent("Contents", isDirectory: true)
		let resources = contents.appendingPathComponent("Resources", isDirectory: true)
		let payload = resources.appendingPathComponent("Payload", isDirectory: true)
		let plugin = payload.appendingPathComponent("Glyphs MCP.glyphsPlugin", isDirectory: true)
		let req = payload.appendingPathComponent("requirements.txt")

		try FileManager.default.createDirectory(at: plugin, withIntermediateDirectories: true, attributes: nil)
		try FileManager.default.createDirectory(at: resources, withIntermediateDirectories: true, attributes: nil)

		let infoPlist = contents.appendingPathComponent("Info.plist")
		let plist = """
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleIdentifier</key>
  <string>cx.ap.tests.bundle</string>
  <key>CFBundleName</key>
  <string>Test</string>
  <key>CFBundlePackageType</key>
  <string>BNDL</string>
</dict>
</plist>
"""
		try FileManager.default.createDirectory(at: contents, withIntermediateDirectories: true, attributes: nil)
		try plist.write(to: infoPlist, atomically: true, encoding: .utf8)
		try "mcp\n".write(to: req, atomically: true, encoding: .utf8)

		let b = try XCTUnwrap(Bundle(url: bundleURL))
		let resolved = try InstallerPayload.resolve(bundle: b)
		XCTAssertEqual(resolved.pluginBundle.lastPathComponent, "Glyphs MCP.glyphsPlugin")
		XCTAssertEqual(resolved.payloadDir.lastPathComponent, "Payload")
		XCTAssertTrue(FileManager.default.fileExists(atPath: resolved.requirementsTxt.path))
	}

	func testProcessRunnerRunStreamingCapturesStdoutAndStderr() async throws {
		let runner = ProcessRunner()
		let exe = URL(fileURLWithPath: "/bin/sh")

		let lock = NSLock()
		var lines: [String] = []
		try await runner.runStreaming(executable: exe, args: ["-c", "echo out; echo err 1>&2"], onLine: { s in
			lock.lock()
			lines.append(s.trimmingCharacters(in: .whitespacesAndNewlines))
			lock.unlock()
		})

		XCTAssertTrue(lines.contains("out"), "\(lines)")
		XCTAssertTrue(lines.contains("err"), "\(lines)")
	}

	func testProcessRunnerRunStreamingThrowsOnNonzeroExit() async {
		let runner = ProcessRunner()
		let exe = URL(fileURLWithPath: "/bin/sh")

		do {
			try await runner.runStreaming(executable: exe, args: ["-c", "echo nope; exit 7"], onLine: { _ in })
			XCTFail("Expected runStreaming to throw on nonzero exit.")
		} catch {
			guard let e = error as? InstallerError else {
				return XCTFail("Expected InstallerError, got: \(type(of: error)) \(error)")
			}
			XCTAssertTrue(e.localizedDescription.contains("Command failed"), e.localizedDescription)
		}
	}

	func testGitHubPluginVersionFetcherParsesPlistViaHTTPClient() async throws {
		UserDefaults.standard.removeObject(forKey: "gmcp.githubPluginVersionFetchedAt")
		UserDefaults.standard.removeObject(forKey: "gmcp.githubPluginVersionString")

		let plist = """
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleShortVersionString</key>
  <string>9.9.9</string>
  <key>CFBundleVersion</key>
  <string>9.9.9</string>
</dict>
</plist>
"""
		let data = try XCTUnwrap(plist.data(using: .utf8))
		let client = FakeHTTPClient(dataToReturn: data, onRequest: nil)

		let res = try await GitHubPluginVersionFetcher.fetchLatestVersion(client: client, timeout: 1, cacheMaxAge: -1)
		XCTAssertEqual(res.version.displayString, "9.9.9")
	}
}
