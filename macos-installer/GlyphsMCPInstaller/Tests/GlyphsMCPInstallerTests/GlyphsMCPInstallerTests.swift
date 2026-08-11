import XCTest
import Foundation
import CryptoKit
@testable import GlyphsMCPInstallerCore

private final class FakeUpdateHTTPClient: UpdateHTTPClienting, @unchecked Sendable {
	private let queue = DispatchQueue(label: "FakeUpdateHTTPClient")
	private let responses: [String: Data]
	private var requests: [URL] = []

	var requestedURLs: [URL] { queue.sync { requests } }

	init(responses: [String: Data]) {
		self.responses = responses
	}

	func data(from url: URL, timeout: TimeInterval, maximumBytes: Int) async throws -> Data {
		_ = timeout
		queue.sync { requests.append(url) }
		guard let data = responses[url.absoluteString] else {
			throw UpdateStagingError("network", "Missing fake response for \(url.absoluteString)")
		}
		guard data.count <= maximumBytes else {
			throw UpdateStagingError("size_limit", "Fake response exceeded the requested limit.")
		}
		return data
	}
}

private final class UpdateOptInBox: @unchecked Sendable {
	private let lock = NSLock()
	private var values: [GlyphsMajorVersion: Bool] = [:]

	func get(_ version: GlyphsMajorVersion) -> Bool {
		lock.lock()
		defer { lock.unlock() }
		return values[version] ?? false
	}

	func set(_ version: GlyphsMajorVersion, _ enabled: Bool) {
		lock.lock()
		values[version] = enabled
		lock.unlock()
	}
}

private struct ThrowingUpdateHTTPClient: UpdateHTTPClienting {
	let error: Error

	func data(from url: URL, timeout: TimeInterval, maximumBytes: Int) async throws -> Data {
		_ = url
		_ = timeout
		_ = maximumBytes
		throw error
	}
}

private struct CancellableUpdateHTTPClient: UpdateHTTPClienting {
	func data(from url: URL, timeout: TimeInterval, maximumBytes: Int) async throws -> Data {
		_ = url
		_ = timeout
		_ = maximumBytes
		try await Task.sleep(nanoseconds: 10_000_000_000)
		return Data()
	}
}

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

	func testClaudeCliListInspectorDetectsNoServersConfigured() {
		let output = "No MCP servers configured. Use `claude mcp add` to add a server."
		XCTAssertEqual(ClaudeCliListInspector.detectNoServersConfigured(output: output), "No MCP servers configured.")
	}

	func testClaudeConfigInspectorReadsDesktopMcpRemoteEntry() {
		let json = """
{
  "mcpServers": {
    "glyphs-mcp-server": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "http://127.0.0.1:9680/mcp/"
      ]
    }
  }
}
"""

		let cfg = ClaudeConfigInspector.readServerConfig(json: json, serverName: "glyphs-mcp-server")
		XCTAssertEqual(cfg?.url, "http://127.0.0.1:9680/mcp/")
	}

	func testClaudeDesktopConfiguratorPatchesConfigWithoutRemovingPreferences() throws {
		let tmp = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
		try FileManager.default.createDirectory(at: tmp, withIntermediateDirectories: true, attributes: nil)
		let configURL = tmp.appendingPathComponent("claude_desktop_config.json")
		let initial = """
{
  "globalShortcut": "Alt+Ctrl+Cmd+*",
  "mcpServers": {
    "other": {
      "command": "npx",
      "args": ["other"]
    }
  },
  "preferences": {
    "menuBarEnabled": true
  }
}
"""
		try initial.write(to: configURL, atomically: true, encoding: .utf8)

		try ClaudeDesktopConfigurator(log: { _ in }).patchClaudeDesktopConfig(at: configURL)

		let output = try String(contentsOf: configURL, encoding: .utf8)
		XCTAssertTrue(output.contains("\"globalShortcut\""))
		XCTAssertTrue(output.contains("\"preferences\""))
		XCTAssertTrue(output.contains("\"other\""))
		XCTAssertTrue(output.contains("\"glyphs-mcp-server\""))
		XCTAssertTrue(output.contains("\"mcp-remote\""))
		XCTAssertTrue(output.contains("\"PATH\""))
		XCTAssertEqual(
			ClaudeConfigInspector.readServerConfig(json: output, serverName: "glyphs-mcp-server")?.url,
			"http://127.0.0.1:9680/mcp/"
		)
	}

	func testMcpCliInspectorDetectsCodexServerInPlainTextUrlTable() {
		let output = """
Name                 Url                                Bearer Token Env Var  Status   Auth
figma                https://mcp.figma.com/mcp          -                     enabled  OAuth
glyphs-mcp-server    http://127.0.0.1:9680/mcp/         -                     enabled  Unsupported
openaiDeveloperDocs  https://developers.openai.com/mcp  -                     enabled  Unsupported
"""

		let result = McpCliInspector.containsServer(
			jsonLikeText: output,
			serverName: "glyphs-mcp-server",
			endpointURL: "http://127.0.0.1:9680/mcp/"
		)

		XCTAssertEqual(result?.isConfigured, true)
		XCTAssertEqual(result?.details, "CLI: server found in list (url matches).")
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

	func testVersionGateAllowsPython312Through314AndBlocks315() {
		for version in ["3.12.0", "3.13.0", "3.14.0"] {
			XCTAssertTrue(VersionGate.isSupported(version: version), "\(version) should be supported")
		}
		XCTAssertFalse(VersionGate.isSupported(version: "3.15.0"))
	}

	func testRuntimeProbeDocumentDecodesABIDiagnostic() throws {
		let json = """
{
  "schemaVersion": 1,
  "mode": "preinstall",
  "status": "incompatible",
  "blocking": true,
  "runtime": {
    "executable": "/tmp/python3.14",
    "version": "3.14.2",
    "implementation": "CPython",
    "soabi": "cpython-314-darwin",
    "extensionSuffix": ".cpython-314-darwin.so",
    "architecture": "arm64"
  },
  "sitePackages": "/tmp/site-packages",
  "checks": [{
    "module": "pydantic_core",
    "present": true,
    "imported": false,
    "origin": null,
    "error": "ImportError: incompatible",
    "nativeFiles": [{
      "file": "/tmp/site-packages/pydantic_core/_pydantic_core.cpython-311-darwin.so",
      "abi": "cpython-311",
      "abiCompatible": false,
      "architectures": ["arm64"],
      "architectureCompatible": true
    }]
  }],
  "issues": [{
    "code": "incompatible_abi",
    "module": "pydantic_core",
    "file": "/tmp/site-packages/pydantic_core/_pydantic_core.cpython-311-darwin.so",
    "expected": "cpython-314 or abi3",
    "detected": "cpython-311",
    "message": "Native package was built for CPython 3.11.",
    "blocking": true
  }]
}
"""
		let document = try JSONDecoder().decode(
			RuntimeProbeDocument.self,
			from: Data(json.utf8)
		)
		XCTAssertTrue(document.blocking)
		XCTAssertEqual(document.runtime.executable, "/tmp/python3.14")
		XCTAssertEqual(document.issues.first?.code, "incompatible_abi")
		XCTAssertEqual(
			document.checks.first?.nativeFiles.first?.abi,
			"cpython-311"
		)
		let message = RuntimeProbeExecutor.failureMessage(document, mode: .preinstall)
		XCTAssertTrue(message.contains("Installation stopped before changing dependencies or the plug-in."), message)
		XCTAssertTrue(message.contains("_pydantic_core.cpython-311-darwin.so"), message)
	}

	func testGlyphsPreferencesUsesVersionSpecificDomains() {
		XCTAssertEqual(GlyphsPreferences.suiteName(), "com.GeorgSeifert.Glyphs4")
		XCTAssertEqual(GlyphsPreferences.suiteName(glyphsVersion: .v3), "com.GeorgSeifert.Glyphs3")
		XCTAssertEqual(GlyphsPreferences.suiteName(glyphsVersion: .v4), "com.GeorgSeifert.Glyphs4")
	}

	func testInstallerPathsCanTargetGlyphs3And4() {
		XCTAssertTrue(InstallerPaths.glyphsBaseDir.path.hasSuffix("Library/Application Support/Glyphs 4"))
		XCTAssertTrue(InstallerPaths.glyphsPluginsDir.path.hasSuffix("Library/Application Support/Glyphs 4/Plugins"))
		XCTAssertTrue(InstallerPaths.glyphsBaseDir(glyphsVersion: .v3).path.hasSuffix("Library/Application Support/Glyphs 3"))
		XCTAssertTrue(InstallerPaths.glyphsBaseDir(glyphsVersion: .v4).path.hasSuffix("Library/Application Support/Glyphs 4"))
		XCTAssertTrue(InstallerPaths.glyphsPluginsDir(glyphsVersion: .v3).path.hasSuffix("Library/Application Support/Glyphs 3/Plugins"))
		XCTAssertTrue(InstallerPaths.glyphsPluginsDir(glyphsVersion: .v4).path.hasSuffix("Library/Application Support/Glyphs 4/Plugins"))
		XCTAssertTrue(InstallerPaths.glyphsScriptsSitePackages(glyphsVersion: .v3).path.hasSuffix("Library/Application Support/Glyphs 3/Scripts/site-packages"))
		XCTAssertTrue(InstallerPaths.glyphsScriptsSitePackages(glyphsVersion: .v4).path.hasSuffix("Library/Application Support/Glyphs 4/Scripts/site-packages"))
	}

	func testInstallButtonTitleChangesForInstalledPlugin() {
		XCTAssertEqual(InstallerSimpleUI.installButtonTitle(installedPluginVersion: nil), "Install Glyphs MCP Server")
		XCTAssertEqual(
			InstallerSimpleUI.installButtonTitle(installedPluginVersion: PluginBundleVersion(shortVersion: "1.2.3", buildVersion: "1.2.3")),
			"Update Glyphs MCP Server"
		)
	}

	func testSkillButtonTitleChangesWhenManagedSkillsExist() {
		XCTAssertEqual(InstallerSimpleUI.skillButtonTitle(hasExistingManagedSkills: false), "Install Skill")
		XCTAssertEqual(InstallerSimpleUI.skillButtonTitle(hasExistingManagedSkills: true), "Update Skill")
	}

	func testWizardButtonTitleChangesWhenPreviousSetupExists() {
		XCTAssertEqual(
			InstallerSimpleUI.wizardButtonTitle(installedPluginVersion: nil, skills: []),
			"Complete Setup"
		)
		XCTAssertEqual(
			InstallerSimpleUI.wizardButtonTitle(
				installedPluginVersion: PluginBundleVersion(shortVersion: "1.2.3", buildVersion: "1.2.3"),
				skills: []
			),
			"Update Setup"
		)
		XCTAssertEqual(
			InstallerSimpleUI.wizardButtonTitle(
				installedPluginVersion: nil,
				skills: [.init(kind: .codex, installedSkillNames: ["glyphs"])]
			),
			"Update Setup"
		)
	}

	func testVersionLineIncludesInstalledAndPayloadVersions() {
		let line = InstallerSimpleUI.versionLine(
			installed: PluginBundleVersion(shortVersion: "1.0.0", buildVersion: "1.0.0"),
			payload: PluginBundleVersion(shortVersion: "1.1.0", buildVersion: "1.1.0")
		)
		XCTAssertEqual(line, "Installed: 1.0.0 • This app: 1.1.0")
	}

	func testGlyphsPythonResolverUsesSelectedFrameworkFirst() throws {
		let tmp = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
		let framework = tmp.appendingPathComponent("Python.framework/Versions/3.12", isDirectory: true)
		let python = framework.appendingPathComponent("bin/python3")
		try FileManager.default.createDirectory(at: python.deletingLastPathComponent(), withIntermediateDirectories: true, attributes: nil)
		try Data().write(to: python)

		let preflight = PreflightResult(
			items: [],
			glyphsPipPath: "/tmp/ignored/pip3",
			glyphsPipVersion: "3.12.1",
			glyphsSelectedPythonFrameworkPath: framework.path,
			glyphsSelectedPythonVersion: "3.12.4",
			customPythons: [],
			customPythonTooOldCount: 0,
			customPythonTooNewCount: 0,
			customPythonUnknownCount: 0,
			codexPath: nil,
			claudePath: nil,
			nodePath: nil
		)

		let status = GlyphsPythonResolver.resolve(preflight: preflight)
		XCTAssertTrue(status.canInstall)
		XCTAssertEqual(status.source, .glyphsSetting)
		XCTAssertEqual(status.version, "3.12.4")

		if case let .custom(python3)? = status.makeSelection() {
			XCTAssertEqual(python3.path, python.path)
		} else {
			XCTFail("Expected a custom Python selection")
		}
	}

	func testGlyphsPythonResolverFallsBackToGlyphsBundledPython() throws {
		let tmp = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
		let pip = tmp.appendingPathComponent("pip3")
		let python = tmp.appendingPathComponent("python3")
		try FileManager.default.createDirectory(at: tmp, withIntermediateDirectories: true, attributes: nil)
		try Data().write(to: pip)
		try Data().write(to: python)

		let preflight = PreflightResult(
			items: [],
			glyphsPipPath: pip.path,
			glyphsPipVersion: "3.11.9",
			glyphsSelectedPythonFrameworkPath: nil,
			glyphsSelectedPythonVersion: nil,
			customPythons: [],
			customPythonTooOldCount: 0,
			customPythonTooNewCount: 0,
			customPythonUnknownCount: 0,
			codexPath: nil,
			claudePath: nil,
			nodePath: nil
		)

		let status = GlyphsPythonResolver.resolve(preflight: preflight)
		XCTAssertTrue(status.canInstall)
		XCTAssertEqual(status.source, .glyphsBundled)

		if case let .glyphs(pip3, python3)? = status.makeSelection() {
			XCTAssertEqual(pip3.path, pip.path)
			XCTAssertEqual(python3.path, python.path)
		} else {
			XCTFail("Expected a Glyphs Python selection")
		}
	}

	func testGlyphsPythonResolverAllowsPython314() throws {
		let tmp = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
		let framework = tmp.appendingPathComponent("Python.framework/Versions/3.14", isDirectory: true)
		let python = framework.appendingPathComponent("bin/python3")
		try FileManager.default.createDirectory(at: python.deletingLastPathComponent(), withIntermediateDirectories: true, attributes: nil)
		try Data().write(to: python)

		let preflight = PreflightResult(
			items: [],
			glyphsPipPath: nil,
			glyphsPipVersion: nil,
			glyphsSelectedPythonFrameworkPath: framework.path,
			glyphsSelectedPythonVersion: "3.14.0",
			customPythons: [],
			customPythonTooOldCount: 0,
			customPythonTooNewCount: 0,
			customPythonUnknownCount: 0,
			codexPath: nil,
			claudePath: nil,
			nodePath: nil
		)

		let status = GlyphsPythonResolver.resolve(preflight: preflight)
		XCTAssertTrue(status.canInstall)
		XCTAssertNil(status.installFailureReason)
		XCTAssertEqual(status.version, "3.14.0")
	}

	func testGlyphsPythonResolverBlocksUnsupportedVersion() throws {
		let tmp = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
		let framework = tmp.appendingPathComponent("Python.framework/Versions/3.15", isDirectory: true)
		let python = framework.appendingPathComponent("bin/python3")
		try FileManager.default.createDirectory(at: python.deletingLastPathComponent(), withIntermediateDirectories: true, attributes: nil)
		try Data().write(to: python)

		let preflight = PreflightResult(
			items: [],
			glyphsPipPath: nil,
			glyphsPipVersion: nil,
			glyphsSelectedPythonFrameworkPath: framework.path,
			glyphsSelectedPythonVersion: "3.15.0",
			customPythons: [],
			customPythonTooOldCount: 0,
			customPythonTooNewCount: 0,
			customPythonUnknownCount: 0,
			codexPath: nil,
			claudePath: nil,
			nodePath: nil
		)

		let status = GlyphsPythonResolver.resolve(preflight: preflight)
		XCTAssertFalse(status.canInstall)
		XCTAssertNotNil(status.installFailureReason)
	}

	func testGlyphsPythonResolverBlocksWhenMissing() {
		let preflight = PreflightResult(
			items: [],
			glyphsPipPath: nil,
			glyphsPipVersion: nil,
			glyphsSelectedPythonFrameworkPath: nil,
			glyphsSelectedPythonVersion: nil,
			customPythons: [],
			customPythonTooOldCount: 0,
			customPythonTooNewCount: 0,
			customPythonUnknownCount: 0,
			codexPath: nil,
			claudePath: nil,
			nodePath: nil
		)

		let status = GlyphsPythonResolver.resolve(preflight: preflight)
		XCTAssertFalse(status.canInstall)
		XCTAssertEqual(status.summary, "No usable Glyphs Python detected")
	}

	func testInstallerStatusSnapshotBlocksInstallWhileGlyphsIsRunning() throws {
		let preflight = try makeSelectedGlyphsPythonPreflight(version: "3.12.4")
		let snapshot = InstallerStatusSnapshotBuilder.build(
			preflight: preflight,
			check: .empty,
			installedPluginVersion: nil,
			payloadPluginVersion: PluginBundleVersion(shortVersion: "1.1.0", buildVersion: "1.1.0"),
			glyphsRunning: true,
			pluginInspection: .notInstalled()
		)

		XCTAssertFalse(snapshot.canInstall)
		XCTAssertEqual(snapshot.installMessage, "Quit Glyphs before installing or updating the plug-in.")
	}

	func testInstallerStatusSnapshotEnablesInstallWhenGlyphsIsClosedAndPythonIsValid() throws {
		let preflight = try makeSelectedGlyphsPythonPreflight(version: "3.12.4")
		let snapshot = InstallerStatusSnapshotBuilder.build(
			preflight: preflight,
			check: .empty,
			installedPluginVersion: nil,
			payloadPluginVersion: PluginBundleVersion(shortVersion: "1.1.0", buildVersion: "1.1.0"),
			glyphsRunning: false,
			pluginInspection: .notInstalled()
		)

		XCTAssertTrue(snapshot.canInstall)
		XCTAssertNil(snapshot.installMessage)
		XCTAssertEqual(snapshot.installButtonTitle, "Install Glyphs MCP Server")
	}

	func testInstallerStatusSnapshotBlocksInstallWhenGlyphsPythonIsMissing() {
		let snapshot = InstallerStatusSnapshotBuilder.build(
			preflight: .empty,
			check: .empty,
			installedPluginVersion: PluginBundleVersion(shortVersion: "1.0.0", buildVersion: "1.0.0"),
			payloadPluginVersion: PluginBundleVersion(shortVersion: "1.1.0", buildVersion: "1.1.0"),
			glyphsRunning: false,
			pluginInspection: .notInstalled()
		)

		XCTAssertFalse(snapshot.canInstall)
		XCTAssertEqual(snapshot.installMessage, "Set a Python version in Glyphs → Settings → Addons, restart Glyphs, and try again.")
		XCTAssertEqual(snapshot.installButtonTitle, "Update Glyphs MCP Server")
	}

	func testInstallerStatusSnapshotSummarizesDetectedClients() {
		let check = CheckResult(items: [
			.init(level: .ok, title: "Codex app", details: "/Applications/Codex.app"),
			.init(level: .ok, title: "Codex CLI", details: "/opt/homebrew/bin/codex"),
			.init(level: .ok, title: "Codex MCP settings", details: "Configured"),
			.init(level: .ok, title: "Claude app", details: "/Applications/Claude.app"),
			.init(level: .ok, title: "Claude Desktop MCP settings", details: "Configured"),
			.init(level: .ok, title: "Claude Code CLI", details: "/opt/homebrew/bin/claude"),
			.init(level: .ok, title: "Claude Code MCP settings", details: "Configured"),
		])
		let preflight = PreflightResult(
			items: [],
			glyphsPipPath: nil,
			glyphsPipVersion: nil,
			glyphsSelectedPythonFrameworkPath: nil,
			glyphsSelectedPythonVersion: nil,
			customPythons: [],
			customPythonTooOldCount: 0,
			customPythonTooNewCount: 0,
			customPythonUnknownCount: 0,
			codexPath: "/opt/homebrew/bin/codex",
			claudePath: "/opt/homebrew/bin/claude",
			nodePath: nil
		)

		let snapshot = InstallerStatusSnapshotBuilder.build(
			preflight: preflight,
			check: check,
			installedPluginVersion: nil,
			payloadPluginVersion: nil,
			glyphsRunning: false,
			pluginInspection: .notInstalled()
		)

		let detectedKinds = snapshot.clients.filter(\.detected).map(\.kind)
		XCTAssertTrue(detectedKinds.contains(.codex))
		XCTAssertTrue(detectedKinds.contains(.claudeDesktop))
		XCTAssertTrue(detectedKinds.contains(.claudeCode))
		XCTAssertTrue(snapshot.detectedClientsSummary.contains("Codex"))
		XCTAssertTrue(snapshot.detectedClientsSummary.contains("Claude Desktop"))
		XCTAssertTrue(snapshot.detectedClientsSummary.contains("Claude Code"))
		let codex = snapshot.clients.first(where: { $0.kind == .codex })
		let claudeDesktop = snapshot.clients.first(where: { $0.kind == .claudeDesktop })
		let claudeCode = snapshot.clients.first(where: { $0.kind == .claudeCode })
		XCTAssertEqual(codex?.statusText, "Configured")
		XCTAssertEqual(codex?.appStatus.summary, "Installed")
		XCTAssertEqual(codex?.cliStatus.summary, "Installed")
		XCTAssertEqual(codex?.configStatus.summary, "Configured")
		XCTAssertEqual(codex?.detailText, "Codex app and CLI share ~/.codex/config.toml.")
		XCTAssertEqual(claudeDesktop?.statusText, "Configured")
		XCTAssertEqual(claudeDesktop?.appStatus.summary, "Installed")
		XCTAssertEqual(claudeDesktop?.cliStatus.isVisible, false)
		XCTAssertEqual(claudeDesktop?.configStatus.summary, "Configured")
		XCTAssertEqual(claudeDesktop?.detailText, "Claude Desktop uses ~/Library/Application Support/Claude/claude_desktop_config.json.")
		XCTAssertEqual(claudeCode?.statusText, "Configured")
		XCTAssertEqual(claudeCode?.appStatus.isVisible, false)
		XCTAssertEqual(claudeCode?.cliStatus.summary, "Installed")
		XCTAssertEqual(claudeCode?.configStatus.summary, "Configured")
		XCTAssertEqual(claudeCode?.detailText, "Claude Code uses ~/.claude.json.")

		let firstUndetectedIndex = snapshot.clients.firstIndex(where: { !$0.detected }) ?? snapshot.clients.endIndex
		let detectedPrefix = snapshot.clients[..<firstUndetectedIndex]
		XCTAssertTrue(detectedPrefix.allSatisfy(\.detected))
	}

	func testInstallerStatusSnapshotSeparatesClaudeDesktopFromClaudeCode() {
		let check = CheckResult(items: [
			.init(level: .ok, title: "Claude app", details: "/Applications/Claude.app"),
			.init(level: .ok, title: "Claude Desktop MCP settings", details: "Configured"),
			.init(level: .warn, title: "Claude Code CLI", details: "Not found."),
			.init(level: .warn, title: "Claude Code MCP settings", details: "Missing"),
		])

		let snapshot = InstallerStatusSnapshotBuilder.build(
			preflight: .empty,
			check: check,
			installedPluginVersion: nil,
			payloadPluginVersion: nil,
			glyphsRunning: false,
			pluginInspection: .notInstalled()
		)

		let desktop = snapshot.clients.first(where: { $0.kind == .claudeDesktop })
		let code = snapshot.clients.first(where: { $0.kind == .claudeCode })

		XCTAssertEqual(desktop?.statusText, "Configured")
		XCTAssertEqual(code?.statusText, "Not detected")
	}

	func testInstallerStatusSnapshotTreatsValidCodexConfigAsConfiguredWhenCliIsMissing() {
		let check = CheckResult(items: [
			.init(level: .warn, title: "Codex CLI", details: "Not found."),
			.init(level: .ok, title: "Codex MCP settings", details: "Configured"),
		])

		let snapshot = InstallerStatusSnapshotBuilder.build(
			preflight: .empty,
			check: check,
			installedPluginVersion: nil,
			payloadPluginVersion: nil,
			glyphsRunning: false,
			pluginInspection: .notInstalled()
		)

		let codex = snapshot.clients.first(where: { $0.kind == .codex })
		XCTAssertEqual(codex?.statusText, "Configured")
		XCTAssertEqual(codex?.appStatus.summary, "Not found")
		XCTAssertEqual(codex?.cliStatus.summary, "Not found")
		XCTAssertEqual(codex?.configStatus.summary, "Configured")
		XCTAssertEqual(codex?.detected, true)
	}

	func testInstallerStatusSnapshotHidesRawCodexCliFailureFromMainStatus() {
		let check = CheckResult(items: [
			.init(level: .ok, title: "Codex CLI", details: "/Users/thierryc/.nvm/versions/node/v24.13.0/bin/codex"),
			.init(level: .ok, title: "Codex MCP settings", details: "Configured"),
		])

		let snapshot = InstallerStatusSnapshotBuilder.build(
			preflight: .empty,
			check: check,
			installedPluginVersion: nil,
			payloadPluginVersion: nil,
			glyphsRunning: false,
			pluginInspection: .notInstalled()
		)

		let codex = snapshot.clients.first(where: { $0.kind == .codex })
		XCTAssertEqual(codex?.statusText, "Configured")
		XCTAssertEqual(codex?.cliStatus.summary, "Installed")
		XCTAssertFalse(codex?.detailText?.contains("v24.13.0") ?? false)
		XCTAssertFalse(codex?.detailText?.contains("list failed") ?? false)
	}

	func testInstallerStatusSnapshotShowsPartialStatusWhenAppInstalledButConfigMissing() {
		let check = CheckResult(items: [
			.init(level: .ok, title: "Codex app", details: "/Applications/Codex.app"),
			.init(level: .warn, title: "Codex CLI", details: "Not found."),
			.init(level: .warn, title: "Codex MCP settings", details: "Missing"),
		])

		let snapshot = InstallerStatusSnapshotBuilder.build(
			preflight: .empty,
			check: check,
			installedPluginVersion: nil,
			payloadPluginVersion: nil,
			glyphsRunning: false,
			pluginInspection: .notInstalled()
		)

		let codex = snapshot.clients.first(where: { $0.kind == .codex })
		XCTAssertEqual(codex?.statusText, "Partially available")
		XCTAssertEqual(codex?.appStatus.summary, "Installed")
		XCTAssertEqual(codex?.cliStatus.summary, "Not found")
		XCTAssertEqual(codex?.configStatus.summary, "Missing")
	}

	func testInstallerStatusSnapshotShowsNotDetectedWhenClaudeSignalsAreAllMissing() {
		let snapshot = InstallerStatusSnapshotBuilder.build(
			preflight: .empty,
			check: .empty,
			installedPluginVersion: nil,
			payloadPluginVersion: nil,
			glyphsRunning: false,
			pluginInspection: .notInstalled()
		)

		let claude = snapshot.clients.first(where: { $0.kind == .claudeCode })
		XCTAssertEqual(claude?.statusText, "Not detected")
		XCTAssertEqual(claude?.appStatus.isVisible, false)
		XCTAssertEqual(claude?.cliStatus.summary, "Not found")
		XCTAssertEqual(claude?.configStatus.summary, "Missing")
	}

	func testInstallerStatusSnapshotIncludesManagedSkillDetection() throws {
		let tmp = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
		let payloadDir = tmp.appendingPathComponent("Payload", isDirectory: true)
		let plugin = payloadDir.appendingPathComponent("Glyphs MCP.glyphsPlugin", isDirectory: true)
		let req = payloadDir.appendingPathComponent("requirements.txt")
		let skillsDir = payloadDir.appendingPathComponent("skills", isDirectory: true)
		let codexRoot = tmp.appendingPathComponent("codex-skills", isDirectory: true)
		let claudeRoot = tmp.appendingPathComponent("claude-skills", isDirectory: true)
		let codexSkill = codexRoot.appendingPathComponent("glyphs", isDirectory: true)

		try FileManager.default.createDirectory(at: plugin, withIntermediateDirectories: true, attributes: nil)
		try FileManager.default.createDirectory(at: skillsDir.appendingPathComponent("glyphs", isDirectory: true), withIntermediateDirectories: true, attributes: nil)
		try FileManager.default.createDirectory(at: skillsDir.appendingPathComponent("glyphs-mcp-development", isDirectory: true), withIntermediateDirectories: true, attributes: nil)
		try FileManager.default.createDirectory(at: skillsDir.appendingPathComponent("glyphs-mcp-spacing", isDirectory: true), withIntermediateDirectories: true, attributes: nil)
		try "mcp\n".write(to: req, atomically: true, encoding: .utf8)
		try FileManager.default.createDirectory(at: codexSkill, withIntermediateDirectories: true, attributes: nil)

		let payload = InstallerPayload(payloadDir: payloadDir, pluginBundle: plugin, requirementsTxt: req, skillsDir: skillsDir)
		let detected = InstallerSkillTargetDetector.detect(payload: payload, codexRoot: codexRoot, claudeCodeRoot: claudeRoot)

		let codexTarget = try XCTUnwrap(detected.first(where: { $0.kind == .codex }))
		let claudeTarget = try XCTUnwrap(detected.first(where: { $0.kind == .claudeCode }))
		XCTAssertEqual(codexTarget.installedSkillNames, ["glyphs"])
		XCTAssertTrue(codexTarget.hasInstalledSkills)
		XCTAssertEqual(claudeTarget.installedSkillNames, [])
		XCTAssertFalse(claudeTarget.hasInstalledSkills)
	}

	func testInstallerClientOrderingPutsDetectedClientsFirst() {
		let ordered = InstallerClientOrdering.ordered([
			.init(kind: .claudeCode, isDetected: true),
			.init(kind: .claudeDesktop, isDetected: true),
			.init(kind: .codex, isDetected: true),
		])

		XCTAssertEqual(
			ordered.map(\.kind),
			[InstallerClientKind.codex, .claudeDesktop, .claudeCode]
		)
	}

	func testClaudeCliAddInspectorTreatsAlreadyExistsAsSuccess() {
		XCTAssertTrue(ClaudeCliAddInspector.wasAlreadyConfigured(output: "MCP server glyphs-mcp already exists in user config"))
		XCTAssertTrue(ClaudeCliAddInspector.wasAlreadyConfigured(output: "already exists"))
		XCTAssertFalse(ClaudeCliAddInspector.wasAlreadyConfigured(output: "configured via CLI"))
	}

	func testInstallerTabVisibleTabsHideAdvancedTabsByDefault() {
		XCTAssertEqual(
			InstallerAdvancedModePolicy.visibleTabIDs(isAdvancedModeEnabled: false),
			["wizard", "status", "help"]
		)
	}

	func testInstallerTabVisibleTabsShowAllTabsInAdvancedMode() {
		XCTAssertEqual(
			InstallerAdvancedModePolicy.visibleTabIDs(isAdvancedModeEnabled: true),
			["wizard", "install", "link", "skill", "status", "help"]
		)
	}

	func testAdvancedModePolicyFallsBackToWizardFromAdvancedTab() {
		XCTAssertEqual(
			InstallerAdvancedModePolicy.fallbackTabID(currentTabID: "install", isAdvancedModeEnabled: false),
			"wizard"
		)
		XCTAssertEqual(
			InstallerAdvancedModePolicy.fallbackTabID(currentTabID: "link", isAdvancedModeEnabled: false),
			"wizard"
		)
		XCTAssertEqual(
			InstallerAdvancedModePolicy.fallbackTabID(currentTabID: "skill", isAdvancedModeEnabled: false),
			"wizard"
		)
	}

	func testAdvancedModePolicyKeepsSimpleTabSelection() {
		XCTAssertEqual(
			InstallerAdvancedModePolicy.fallbackTabID(currentTabID: "status", isAdvancedModeEnabled: false),
			"status"
		)
		XCTAssertEqual(
			InstallerAdvancedModePolicy.fallbackTabID(currentTabID: "wizard", isAdvancedModeEnabled: false),
			"wizard"
		)
	}

	func testAdvancedModePersistsAcrossModelInit() {
		let suiteName = "GlyphsMCPInstallerTests.\(UUID().uuidString)"
		let defaults = UserDefaults(suiteName: suiteName)!
		defer { defaults.removePersistentDomain(forName: suiteName) }

		XCTAssertFalse(InstallerAdvancedModePreferences.load(from: defaults))
		InstallerAdvancedModePreferences.save(true, to: defaults)
		XCTAssertTrue(InstallerAdvancedModePreferences.load(from: defaults))
	}

	func testToolLocatorPrefersNewestNvmVersion() throws {
		let tmpHome = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
		let oldCodex = tmpHome.appendingPathComponent(".nvm/versions/node/v24.13.0/bin/codex")
		let newCodex = tmpHome.appendingPathComponent(".nvm/versions/node/v24.14.0/bin/codex")

		try FileManager.default.createDirectory(at: oldCodex.deletingLastPathComponent(), withIntermediateDirectories: true, attributes: nil)
		try FileManager.default.createDirectory(at: newCodex.deletingLastPathComponent(), withIntermediateDirectories: true, attributes: nil)
		try "#!/bin/sh\nexit 0\n".write(to: oldCodex, atomically: true, encoding: .utf8)
		try "#!/bin/sh\nexit 0\n".write(to: newCodex, atomically: true, encoding: .utf8)
		try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: oldCodex.path)
		try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: newCodex.path)

		let found = ToolLocator.findTool(named: "codex", extraCandidates: [], home: tmpHome, pathEnv: nil)
		XCTAssertEqual(found.map { URL(fileURLWithPath: $0).standardizedFileURL.path }, newCodex.standardizedFileURL.path)
	}

	func testToolRuntimeEnvironmentPrependsExecutableDirectoryToPATH() {
		let home = URL(fileURLWithPath: "/Users/tester", isDirectory: true)
		let environment = ToolRuntimeEnvironment.mergedEnvironment(
			forExecutablePath: "/Users/tester/.nvm/versions/node/v24.14.0/bin/codex",
			home: home,
			base: ["PATH": "/usr/bin:/bin"]
		)

		let path = environment["PATH"] ?? ""
		let parts = path.split(separator: ":").map(String.init)
		XCTAssertEqual(parts.first, "/Users/tester/.nvm/versions/node/v24.14.0/bin")
		XCTAssertTrue(parts.contains("/usr/bin"))
		XCTAssertTrue(parts.contains("/bin"))
	}

	func testPluginInstallerInspectionDetectsMissingPlugin() {
		let tmp = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
		let plugin = tmp.appendingPathComponent("Glyphs MCP.glyphsPlugin", isDirectory: true)
		let inspection = PluginInstaller.inspectInstalledPlugin(at: plugin)

		XCTAssertEqual(inspection.mode, .notInstalled)
		XCTAssertNil(inspection.version)
		XCTAssertNil(inspection.symlinkTargetPath)
	}

	func testPluginInstallerInspectionDetectsNormalBundle() throws {
		let tmp = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
		let plugin = tmp.appendingPathComponent("Glyphs MCP.glyphsPlugin", isDirectory: true)
		try makePluginBundle(at: plugin, version: "1.2.3")

		let inspection = PluginInstaller.inspectInstalledPlugin(at: plugin)

		XCTAssertEqual(inspection.mode, .bundle)
		XCTAssertEqual(inspection.version?.displayString, "1.2.3")
		XCTAssertFalse(inspection.isSymlink)
	}

	func testPluginInstallerPreservesAndVerifiesCopiedBundleSignature() throws {
		let tmp = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
		let src = tmp.appendingPathComponent("Source/Glyphs MCP.glyphsPlugin", isDirectory: true)
		let pluginsDir = tmp.appendingPathComponent("Installed", isDirectory: true)
		try makePluginBundle(at: src, version: "1.2.3")

		let signature = PluginExecutableSignature(
			cdHash: "trusted-cdhash",
			teamIdentifier: PluginExecutableVerifier.expectedTeamIdentifier,
			authority: "Developer ID Application: Thierry Charbonnel (N9U29A4T8J)",
			hardenedRuntime: true,
			timestamped: true
		)
		var verified: [URL] = []
		let installer = PluginInstaller(
			log: { _ in },
			verifier: PluginExecutableVerifier { bundleURL in
				verified.append(bundleURL)
				return signature
			}
		)

		let outcome = try installer.installPluginBundle(from: src, toPluginsDir: pluginsDir, allowReplace: true)

		let dest = pluginsDir.appendingPathComponent("Glyphs MCP.glyphsPlugin", isDirectory: true)
		XCTAssertTrue(FileManager.default.fileExists(atPath: dest.path))
		XCTAssertEqual(outcome.destBundle, dest)
		XCTAssertEqual(verified.count, 3)
		XCTAssertEqual(verified.first, src)
		XCTAssertEqual(verified.last, dest)
		XCTAssertTrue(verified[1].lastPathComponent.contains(".installing-"))
	}

	func testPluginInstallerRestoresExistingBundleWhenStagedSignatureChanges() throws {
		let tmp = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
		let src = tmp.appendingPathComponent("Source/Glyphs MCP.glyphsPlugin", isDirectory: true)
		let pluginsDir = tmp.appendingPathComponent("Installed", isDirectory: true)
		let dest = pluginsDir.appendingPathComponent("Glyphs MCP.glyphsPlugin", isDirectory: true)
		try makePluginBundle(at: src, version: "2.0.0")
		try makePluginBundle(at: dest, version: "1.0.0")

		let trusted = PluginExecutableSignature(
			cdHash: "trusted",
			teamIdentifier: PluginExecutableVerifier.expectedTeamIdentifier,
			authority: "Developer ID Application: Thierry Charbonnel (N9U29A4T8J)",
			hardenedRuntime: true,
			timestamped: true
		)
		let changed = PluginExecutableSignature(
			cdHash: "changed",
			teamIdentifier: PluginExecutableVerifier.expectedTeamIdentifier,
			authority: trusted.authority,
			hardenedRuntime: true,
			timestamped: true
		)
		let installer = PluginInstaller(
			log: { _ in },
			verifier: PluginExecutableVerifier { bundleURL in
				bundleURL.lastPathComponent.contains(".installing-") ? changed : trusted
			}
		)

		XCTAssertThrowsError(
			try installer.installPluginBundle(from: src, toPluginsDir: pluginsDir, allowReplace: true)
		)
		XCTAssertEqual(PluginVersionReader.readPluginVersion(pluginBundle: dest)?.displayString, "1.0.0")
	}

	func testPluginInstallerInspectionDetectsSymlinkedBundle() throws {
		let tmp = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
		let realPlugin = tmp.appendingPathComponent("Dev/Glyphs MCP.glyphsPlugin", isDirectory: true)
		let installedPlugin = tmp.appendingPathComponent("Installed/Glyphs MCP.glyphsPlugin", isDirectory: true)
		try makePluginBundle(at: realPlugin, version: "1.2.3")
		try FileManager.default.createDirectory(at: installedPlugin.deletingLastPathComponent(), withIntermediateDirectories: true, attributes: nil)
		try FileManager.default.createSymbolicLink(at: installedPlugin, withDestinationURL: realPlugin)

		let inspection = PluginInstaller.inspectInstalledPlugin(at: installedPlugin)

		XCTAssertEqual(inspection.mode, .symlink)
		XCTAssertEqual(inspection.version?.displayString, "1.2.3")
		XCTAssertEqual(inspection.symlinkTargetPath, realPlugin.path)
		XCTAssertTrue(inspection.statusSummary.contains("Development symlink"))
	}

	func testPluginInstallerInspectionDetectsBrokenSymlink() throws {
		let tmp = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
		let installedPlugin = tmp.appendingPathComponent("Installed/Glyphs MCP.glyphsPlugin", isDirectory: true)
		let missingTarget = tmp.appendingPathComponent("Missing/Glyphs MCP.glyphsPlugin", isDirectory: true)
		try FileManager.default.createDirectory(at: installedPlugin.deletingLastPathComponent(), withIntermediateDirectories: true, attributes: nil)
		try FileManager.default.createSymbolicLink(at: installedPlugin, withDestinationURL: missingTarget)

		let inspection = PluginInstaller.inspectInstalledPlugin(at: installedPlugin)

		XCTAssertEqual(inspection.mode, .symlink)
		XCTAssertNil(inspection.version)
		XCTAssertEqual(inspection.symlinkTargetPath, missingTarget.path)
	}

	func testInstallerStatusSnapshotShowsDevPluginWarningForSymlink() throws {
		let preflight = try makeSelectedGlyphsPythonPreflight(version: "3.12.4")
		let pluginURL = URL(fileURLWithPath: "/tmp/Glyphs MCP.glyphsPlugin")
		let inspection = PluginInstaller.InstalledPluginInspection(
			bundleURL: pluginURL,
			mode: .symlink,
			version: PluginBundleVersion(shortVersion: "1.2.3", buildVersion: "1.2.3"),
			symlinkTargetPath: "/tmp/dev/Glyphs MCP.glyphsPlugin"
		)
		let snapshot = InstallerStatusSnapshotBuilder.build(
			preflight: preflight,
			check: .empty,
			installedPluginVersion: nil,
			payloadPluginVersion: PluginBundleVersion(shortVersion: "1.1.0", buildVersion: "1.1.0"),
			glyphsRunning: false,
			pluginInspection: inspection
		)

		XCTAssertTrue(snapshot.showsDevPluginReplacementOption)
		XCTAssertTrue(snapshot.installedPluginIsSymlink)
		XCTAssertEqual(snapshot.installedPluginSymlinkTarget, "/tmp/dev/Glyphs MCP.glyphsPlugin")
		XCTAssertTrue(snapshot.pluginStatusSummary.contains("Development symlink"))
		XCTAssertTrue(snapshot.devPluginWarning?.contains("development symlink") == true)
	}

	func testInstallerStatusSnapshotHidesDevPluginWarningForNormalBundle() throws {
		let preflight = try makeSelectedGlyphsPythonPreflight(version: "3.12.4")
		let inspection = PluginInstaller.InstalledPluginInspection(
			bundleURL: URL(fileURLWithPath: "/tmp/Glyphs MCP.glyphsPlugin"),
			mode: .bundle,
			version: PluginBundleVersion(shortVersion: "1.2.3", buildVersion: "1.2.3"),
			symlinkTargetPath: nil
		)
		let snapshot = InstallerStatusSnapshotBuilder.build(
			preflight: preflight,
			check: .empty,
			installedPluginVersion: nil,
			payloadPluginVersion: PluginBundleVersion(shortVersion: "1.1.0", buildVersion: "1.1.0"),
			glyphsRunning: false,
			pluginInspection: inspection
		)

		XCTAssertFalse(snapshot.showsDevPluginReplacementOption)
		XCTAssertFalse(snapshot.installedPluginIsSymlink)
		XCTAssertNil(snapshot.devPluginWarning)
	}

	private func makeSelectedGlyphsPythonPreflight(version: String) throws -> PreflightResult {
		let tmp = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
		let framework = tmp.appendingPathComponent("Python.framework/Versions/\(version.split(separator: ".").prefix(2).joined(separator: "."))", isDirectory: true)
		let python = framework.appendingPathComponent("bin/python3")
		try FileManager.default.createDirectory(at: python.deletingLastPathComponent(), withIntermediateDirectories: true, attributes: nil)
		try Data().write(to: python)

		return PreflightResult(
			items: [],
			glyphsPipPath: nil,
			glyphsPipVersion: nil,
			glyphsSelectedPythonFrameworkPath: framework.path,
			glyphsSelectedPythonVersion: version,
			customPythons: [],
			customPythonTooOldCount: 0,
			customPythonTooNewCount: 0,
			customPythonUnknownCount: 0,
			codexPath: nil,
			claudePath: nil,
			nodePath: nil
		)
	}

	private func makePluginBundle(at bundleURL: URL, version: String) throws {
		let contents = bundleURL.appendingPathComponent("Contents", isDirectory: true)
		try FileManager.default.createDirectory(at: contents, withIntermediateDirectories: true, attributes: nil)
		let plist = """
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleShortVersionString</key>
  <string>\(version)</string>
  <key>CFBundleVersion</key>
  <string>\(version)</string>
</dict>
</plist>
"""
		try plist.write(to: contents.appendingPathComponent("Info.plist"), atomically: true, encoding: .utf8)
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
		XCTAssertTrue(content.contains("tools/list"), content)
		XCTAssertTrue(content.contains("Mcp-Session-Id"), content)
		XCTAssertTrue(content.contains("catalog titles, descriptions, and safety annotations"), content)
		XCTAssertFalse(content.localizedCaseInsensitiveContains("Tool Profile"), content)
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
		let runtimeProbe = plugin.appendingPathComponent("Contents/Resources/runtime_probe.py")

		try FileManager.default.createDirectory(
			at: runtimeProbe.deletingLastPathComponent(),
			withIntermediateDirectories: true,
			attributes: nil
		)
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
		try "# probe\n".write(to: runtimeProbe, atomically: true, encoding: .utf8)

		let b = try XCTUnwrap(Bundle(url: bundleURL))
		let resolved = try InstallerPayload.resolve(bundle: b)
		XCTAssertEqual(resolved.pluginBundle.lastPathComponent, "Glyphs MCP.glyphsPlugin")
		XCTAssertEqual(resolved.payloadDir.lastPathComponent, "Payload")
		XCTAssertTrue(FileManager.default.fileExists(atPath: resolved.requirementsTxt.path))
	}

	func testInstallerPayloadResolveExtractsSignedPayloadArchive() throws {
		let tmp = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
		let bundleURL = tmp.appendingPathComponent("Archived.bundle", isDirectory: true)
		let contents = bundleURL.appendingPathComponent("Contents", isDirectory: true)
		let resources = contents.appendingPathComponent("Resources", isDirectory: true)
		let sourceRoot = tmp.appendingPathComponent("source", isDirectory: true)
		let payload = sourceRoot.appendingPathComponent("Payload", isDirectory: true)
		let plugin = payload.appendingPathComponent("Glyphs MCP.glyphsPlugin", isDirectory: true)
		let req = payload.appendingPathComponent("requirements.txt")
		let runtimeProbe = plugin.appendingPathComponent("Contents/Resources/runtime_probe.py")
		try FileManager.default.createDirectory(
			at: runtimeProbe.deletingLastPathComponent(),
			withIntermediateDirectories: true,
			attributes: nil
		)
		try "mcp\n".write(to: req, atomically: true, encoding: .utf8)
		try "# probe\n".write(to: runtimeProbe, atomically: true, encoding: .utf8)
		try FileManager.default.createDirectory(at: resources, withIntermediateDirectories: true, attributes: nil)

		let infoPlist = contents.appendingPathComponent("Info.plist")
		let plist = """
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
  <key>CFBundleIdentifier</key>
  <string>cx.ap.tests.archived-payload</string>
  <key>CFBundleName</key>
  <string>Archived</string>
  <key>CFBundlePackageType</key>
  <string>BNDL</string>
</dict>
</plist>
"""
		try plist.write(to: infoPlist, atomically: true, encoding: .utf8)
		let archive = resources.appendingPathComponent("Payload.gmcparchive")
		let process = Process()
		process.executableURL = URL(fileURLWithPath: "/usr/bin/tar")
		process.arguments = ["-czf", archive.path, "-C", sourceRoot.path, "Payload"]
		try process.run()
		process.waitUntilExit()
		XCTAssertEqual(process.terminationStatus, 0)

		let bundle = try XCTUnwrap(Bundle(url: bundleURL))
		let resolved = try InstallerPayload.resolve(bundle: bundle)
		XCTAssertEqual(resolved.pluginBundle.lastPathComponent, "Glyphs MCP.glyphsPlugin")
		XCTAssertTrue(FileManager.default.fileExists(atPath: resolved.requirementsTxt.path))
		XCTAssertNotEqual(resolved.payloadDir.path, payload.path)
	}

	func testPayloadManagedSkillDirectoriesFiltersGlyphsSkills() throws {
		let tmp = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
		let payloadDir = tmp.appendingPathComponent("Payload", isDirectory: true)
		let plugin = payloadDir.appendingPathComponent("Glyphs MCP.glyphsPlugin", isDirectory: true)
		let req = payloadDir.appendingPathComponent("requirements.txt")
		let skillsDir = payloadDir.appendingPathComponent("skills", isDirectory: true)

		try FileManager.default.createDirectory(at: plugin, withIntermediateDirectories: true, attributes: nil)
		try FileManager.default.createDirectory(at: skillsDir.appendingPathComponent("glyphs", isDirectory: true), withIntermediateDirectories: true, attributes: nil)
		try FileManager.default.createDirectory(at: skillsDir.appendingPathComponent("glyphs-mcp-development", isDirectory: true), withIntermediateDirectories: true, attributes: nil)
		try FileManager.default.createDirectory(at: skillsDir.appendingPathComponent("glyphs-mcp-spacing", isDirectory: true), withIntermediateDirectories: true, attributes: nil)
		try FileManager.default.createDirectory(at: skillsDir.appendingPathComponent("other-skill", isDirectory: true), withIntermediateDirectories: true, attributes: nil)
		try "mcp\n".write(to: req, atomically: true, encoding: .utf8)

		let payload = InstallerPayload(payloadDir: payloadDir, pluginBundle: plugin, requirementsTxt: req, skillsDir: skillsDir)
		let managed = payload.managedSkillDirectories().map(\.lastPathComponent)
		XCTAssertEqual(managed, ["glyphs", "glyphs-mcp-development", "glyphs-mcp-spacing"])
	}

	func testAgentSkillBundleInstallerOverwritesManagedSkillsOnlyWhenRequested() throws {
		let tmp = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
		let payloadDir = tmp.appendingPathComponent("Payload", isDirectory: true)
		let plugin = payloadDir.appendingPathComponent("Glyphs MCP.glyphsPlugin", isDirectory: true)
		let req = payloadDir.appendingPathComponent("requirements.txt")
		let skillsDir = payloadDir.appendingPathComponent("skills", isDirectory: true)
		let glyphs = skillsDir.appendingPathComponent("glyphs", isDirectory: true)
		let spacing = skillsDir.appendingPathComponent("glyphs-mcp-spacing", isDirectory: true)
		let destRoot = tmp.appendingPathComponent("dest", isDirectory: true)
		let installedGeneric = destRoot.appendingPathComponent("glyphs", isDirectory: true)
		let legacyConnect = destRoot.appendingPathComponent("glyphs-mcp-connect", isDirectory: true)
		let unrelated = destRoot.appendingPathComponent("third-party-skill", isDirectory: true)

		try FileManager.default.createDirectory(at: plugin, withIntermediateDirectories: true, attributes: nil)
		try FileManager.default.createDirectory(at: glyphs, withIntermediateDirectories: true, attributes: nil)
		try FileManager.default.createDirectory(at: spacing, withIntermediateDirectories: true, attributes: nil)
		try FileManager.default.createDirectory(at: legacyConnect, withIntermediateDirectories: true, attributes: nil)
		try FileManager.default.createDirectory(at: unrelated, withIntermediateDirectories: true, attributes: nil)
		try "mcp\n".write(to: req, atomically: true, encoding: .utf8)
		try "new managed\n".write(to: glyphs.appendingPathComponent("SKILL.md"), atomically: true, encoding: .utf8)
		try "new spacing\n".write(to: spacing.appendingPathComponent("SKILL.md"), atomically: true, encoding: .utf8)
		try "old connect\n".write(to: legacyConnect.appendingPathComponent("SKILL.md"), atomically: true, encoding: .utf8)
		try "keep me\n".write(to: unrelated.appendingPathComponent("SKILL.md"), atomically: true, encoding: .utf8)

		let payload = InstallerPayload(payloadDir: payloadDir, pluginBundle: plugin, requirementsTxt: req, skillsDir: skillsDir)
		let installer = AgentSkillBundleInstaller(log: { _ in })
		_ = try installer.installManagedSkills(from: payload, to: destRoot, clientName: "Codex", overwriteExisting: true)

		XCTAssertEqual(try String(contentsOf: installedGeneric.appendingPathComponent("SKILL.md"), encoding: .utf8), "new managed\n")
		XCTAssertFalse(FileManager.default.fileExists(atPath: legacyConnect.path))
		XCTAssertEqual(try String(contentsOf: destRoot.appendingPathComponent("glyphs-mcp-spacing/SKILL.md"), encoding: .utf8), "new spacing\n")
		XCTAssertEqual(try String(contentsOf: unrelated.appendingPathComponent("SKILL.md"), encoding: .utf8), "keep me\n")
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

	func testProcessRunnerRunStreamingTimesOut() async {
		let runner = ProcessRunner()
		let startedAt = Date()

		do {
			try await runner.runStreaming(
				executable: URL(fileURLWithPath: "/bin/sleep"),
				args: ["5"],
				timeout: 0.05,
				onLine: { _ in }
			)
			XCTFail("Expected runStreaming to time out.")
		} catch {
			guard let installerError = error as? InstallerError else {
				return XCTFail("Expected InstallerError, got: \(type(of: error)) \(error)")
			}
			XCTAssertTrue(installerError.localizedDescription.contains("timed out"), installerError.localizedDescription)
			XCTAssertLessThan(Date().timeIntervalSince(startedAt), 2)
		}
	}

	func testProcessRunnerRunCapturingTimesOut() async {
		let runner = ProcessRunner()
		let startedAt = Date()

		do {
			_ = try await runner.runCapturing(
				executable: URL(fileURLWithPath: "/bin/sleep"),
				args: ["5"],
				timeout: 0.05
			)
			XCTFail("Expected runCapturing to time out.")
		} catch {
			XCTAssertTrue(error.localizedDescription.contains("timed out"), error.localizedDescription)
			XCTAssertLessThan(Date().timeIntervalSince(startedAt), 2)
		}
	}

	func testRuntimeProbeExecutorUsesExactPythonAndGlyphsTargetPath() async throws {
		let root = FileManager.default.temporaryDirectory
			.appendingPathComponent("glyphs-mcp-probe-executor-\(UUID().uuidString)", isDirectory: true)
		try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
		defer { try? FileManager.default.removeItem(at: root) }

		let capture = root.appendingPathComponent("arguments.txt")
		let python = root.appendingPathComponent("selected-python")
		let probe = root.appendingPathComponent("runtime_probe.py")
		let target = root.appendingPathComponent("Glyphs 4/Scripts/site-packages")
		let json = """
{"schemaVersion":1,"mode":"preinstall","status":"incomplete","blocking":false,"runtime":{"executable":"\(python.path)","version":"3.14.2","implementation":"CPython","soabi":"cpython-314-darwin","extensionSuffix":".cpython-314-darwin.so","architecture":"arm64"},"sitePackages":"\(target.path)","checks":[],"issues":[]}
"""
		let script = """
#!/bin/sh
printf '%s\\n' "$@" > "\(capture.path)"
printf '%s\\n' '\(json)'
exit 0
"""
		try script.write(to: python, atomically: true, encoding: .utf8)
		try FileManager.default.setAttributes(
			[.posixPermissions: 0o755],
			ofItemAtPath: python.path
		)
		try "".write(to: probe, atomically: true, encoding: .utf8)

		let document = try await RuntimeProbeExecutor(
			runner: ProcessRunner(),
			log: { _ in }
		).check(
			python: python,
			probe: probe,
			sitePackages: target,
			mode: .preinstall
		)
		let arguments = try String(contentsOf: capture, encoding: .utf8)
			.split(separator: "\n")
			.map(String.init)
		XCTAssertEqual(document.runtime.executable, python.path)
		XCTAssertEqual(
			arguments,
			[
				probe.path,
				"--mode",
				"preinstall",
				"--site-packages",
				target.path,
			]
		)
	}

	func testRuntimeProbeExecutorRejectsStderrOnlyFailure() async throws {
		let root = FileManager.default.temporaryDirectory
			.appendingPathComponent("glyphs-mcp-probe-stderr-\(UUID().uuidString)", isDirectory: true)
		try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
		defer { try? FileManager.default.removeItem(at: root) }

		let python = root.appendingPathComponent("selected-python")
		let script = """
#!/bin/sh
printf '%s\\n' 'loader warning' >&2
printf '%s\\n' '{"schemaVersion":1,"mode":"postinstall","status":"ok","blocking":false,"runtime":{"executable":"\(python.path)","version":"3.14.2","implementation":"CPython","soabi":"cpython-314-darwin","extensionSuffix":".cpython-314-darwin.so","architecture":"arm64"},"sitePackages":"/tmp/site-packages","checks":[],"issues":[]}'
exit 0
"""
		try script.write(to: python, atomically: true, encoding: .utf8)
		try FileManager.default.setAttributes(
			[.posixPermissions: 0o755],
			ofItemAtPath: python.path
		)

		do {
			_ = try await RuntimeProbeExecutor(
				runner: ProcessRunner(),
				log: { _ in }
			).check(
				python: python,
				probe: root.appendingPathComponent("runtime_probe.py"),
				sitePackages: URL(fileURLWithPath: "/tmp/site-packages"),
				mode: .postinstall
			)
			XCTFail("Expected stderr-only probe output to fail.")
		} catch {
			XCTAssertTrue(
				error.localizedDescription.contains("unexpected error output"),
				error.localizedDescription
			)
		}
	}

	func testDependencyPipArgumentsReuseSatisfiedPackagesAndBoundNetworkWaits() {
		let installer = DepsInstaller(runner: ProcessRunner(), log: { _ in })
		let requirements = URL(fileURLWithPath: "/tmp/requirements.txt")
		let target = URL(fileURLWithPath: "/tmp/glyphs-mcp-site-packages")
		let args = installer.pipInstallArgs(requirementsTxt: requirements, target: target)

		XCTAssertFalse(args.contains("--force-reinstall"), "\(args)")
		XCTAssertTrue(args.contains("--upgrade"), "\(args)")
		XCTAssertTrue(args.contains("--upgrade-strategy"), "\(args)")
		XCTAssertTrue(args.contains("--disable-pip-version-check"), "\(args)")
		XCTAssertTrue(args.contains("--timeout"), "\(args)")
		XCTAssertTrue(args.contains("--retries"), "\(args)")
		XCTAssertEqual(installer.pipEnvironment(target: target)["PYTHONPATH"]?.split(separator: ":").first, Substring(target.path))
	}

	func testDependencyPreflightRecognizesSatisfiedAndMismatchedRequirements() throws {
		let installer = DepsInstaller(runner: ProcessRunner(), log: { _ in })
		let tempDirectory = FileManager.default.temporaryDirectory
			.appendingPathComponent("glyphs-mcp-requirements-\(UUID().uuidString)", isDirectory: true)
		try FileManager.default.createDirectory(at: tempDirectory, withIntermediateDirectories: true)
		defer { try? FileManager.default.removeItem(at: tempDirectory) }

		let requirements = tempDirectory.appendingPathComponent("requirements.txt")
		try "# No dependencies\n".write(to: requirements, atomically: true, encoding: .utf8)
		XCTAssertTrue(
			installer.requirementsAreSatisfied(
				python: URL(fileURLWithPath: "/usr/bin/python3"),
				requirementsTxt: requirements
			)
		)

		try "glyphs-mcp-package-that-does-not-exist==1.0\n".write(to: requirements, atomically: true, encoding: .utf8)
		XCTAssertFalse(
			installer.requirementsAreSatisfied(
				python: URL(fileURLWithPath: "/usr/bin/python3"),
				requirementsTxt: requirements
			)
		)
	}

	func testInstallerProgressTextSummarizesPipActivity() {
		XCTAssertEqual(InstallerProgressText.detail(for: "Collecting pyobjc-core==11.1"), "Resolving pyobjc-core==11.1")
		XCTAssertEqual(
			InstallerProgressText.detail(for: "Requirement already satisfied: pyobjc-core==11.1 in /tmp/site-packages"),
			"Already installed: pyobjc-core==11.1 in /tmp/site-packages"
		)
		XCTAssertEqual(InstallerProgressText.detail(for: "Installing collected packages: attrs, anyio"), "Installing resolved Python packages…")
		XCTAssertEqual(InstallerProgressText.detail(for: "Successfully installed attrs-25.3.0"), "Python dependencies are ready.")
		XCTAssertNil(InstallerProgressText.detail(for: "unrelated diagnostic output"))
		XCTAssertLessThanOrEqual(InstallerProgressText.detail(for: "Downloading " + String(repeating: "x", count: 300))?.count ?? 0, 180)
	}

	func testGitHubPluginVersionFetcherUsesPublishedReleaseMetadata() async throws {
		UserDefaults.standard.removeObject(forKey: "gmcp.githubPluginVersionFetchedAt")
		UserDefaults.standard.removeObject(forKey: "gmcp.githubPluginVersionString")

		let json = """
{
  "tag_name": "v9.9.9",
  "draft": false,
  "prerelease": false,
  "assets": []
}
"""
		let data = try XCTUnwrap(json.data(using: .utf8))
		let client = FakeHTTPClient(dataToReturn: data, onRequest: nil)

		let res = try await GitHubPluginVersionFetcher.fetchLatestVersion(client: client, timeout: 1, cacheMaxAge: -1)
		XCTAssertEqual(res.version.displayString, "9.9.9")
	}

	func testGitHubReleaseResolverRejectsPrerelease() throws {
		let json = """
{
  "tag_name": "v9.9.9",
  "draft": false,
  "prerelease": true,
  "assets": []
}
"""
		let data = try XCTUnwrap(json.data(using: .utf8))
		XCTAssertThrowsError(try GitHubReleaseResolver.parsePublishedRelease(data))
	}

	func testPublishedReleaseRequiresOneTrustedAssetURL() throws {
		let trusted = GitHubReleaseAsset(
			name: "GlyphsMCPInstaller.zip",
			browserDownloadURL: try XCTUnwrap(
				URL(string: "https://github.com/thierryc/Glyphs-mcp/releases/download/v1.5.0/GlyphsMCPInstaller.zip")
			)
		)
		let release = GitHubPublishedRelease(
			tagName: "v1.5.0",
			draft: false,
			prerelease: false,
			assets: [trusted]
		)
		XCTAssertEqual(
			try release.requiredAsset(named: "GlyphsMCPInstaller.zip"),
			trusted
		)
		XCTAssertThrowsError(try release.requiredAsset(named: "SHA256SUMS"))

		let duplicate = GitHubPublishedRelease(
			tagName: "v1.5.0",
			draft: false,
			prerelease: false,
			assets: [trusted, trusted]
		)
		XCTAssertThrowsError(
			try duplicate.requiredAsset(named: "GlyphsMCPInstaller.zip")
		)

		let untrusted = GitHubPublishedRelease(
			tagName: "v1.5.0",
			draft: false,
			prerelease: false,
			assets: [
				GitHubReleaseAsset(
					name: "GlyphsMCPInstaller.zip",
					browserDownloadURL: try XCTUnwrap(
						URL(string: "https://example.com/GlyphsMCPInstaller.zip")
					)
				)
			]
		)
		XCTAssertThrowsError(
			try untrusted.requiredAsset(named: "GlyphsMCPInstaller.zip")
		)
	}

	func testGitHubPluginDownloaderVerifiesPublishedChecksum() throws {
		let payload = Data("trusted installer".utf8)
		let digest = SHA256.hash(data: payload).map { String(format: "%02x", $0) }.joined()
		let manifest = Data("\(digest)  installer-app/GlyphsMCPInstaller.zip\n".utf8)
		XCTAssertNoThrow(
			try GitHubPluginDownloader.verifyChecksum(
				payload,
				manifestData: manifest,
				assetName: "GlyphsMCPInstaller.zip"
			)
		)
		XCTAssertThrowsError(
			try GitHubPluginDownloader.verifyChecksum(
				Data("modified".utf8),
				manifestData: manifest,
				assetName: "GlyphsMCPInstaller.zip"
			)
		)
		XCTAssertThrowsError(
			try GitHubPluginDownloader.verifyChecksum(
				payload,
				manifestData: Data("\(digest)  first/GlyphsMCPInstaller.zip\n\(digest)  second/GlyphsMCPInstaller.zip\n".utf8),
				assetName: "GlyphsMCPInstaller.zip"
			)
		)
		XCTAssertThrowsError(
			try GitHubPluginDownloader.verifyChecksum(
				payload,
				manifestData: Data("not-a-digest  GlyphsMCPInstaller.zip\n".utf8),
				assetName: "GlyphsMCPInstaller.zip"
			)
		)
		XCTAssertThrowsError(
			try GitHubPluginDownloader.verifyChecksum(
				payload,
				manifestData: Data("\(digest)  ../GlyphsMCPInstaller.zip\n".utf8),
				assetName: "GlyphsMCPInstaller.zip"
			)
		)
	}

	func testGlyphsApplicationClassifierHandlesStableAndBetaBundles() {
		XCTAssertEqual(
			GlyphsApplicationDetector.classify(
				bundleIdentifier: "com.GeorgSeifert.Glyphs3",
				shortVersion: "3.5",
				displayName: "Glyphs 3",
				fileName: "Glyphs 3"
			),
			.v3
		)
		XCTAssertEqual(
			GlyphsApplicationDetector.classify(
				bundleIdentifier: "com.GeorgSeifert.Glyphs4Beta",
				shortVersion: "4.0a",
				displayName: "Glyphs 4",
				fileName: "Glyphs 4"
			),
			.v4
		)
		XCTAssertEqual(
			GlyphsApplicationDetector.classify(
				bundleIdentifier: "com.GeorgSeifert.GlyphsBeta",
				shortVersion: "4.1b",
				displayName: "Glyphs Beta",
				fileName: "Glyphs Beta"
			),
			.v4
		)
		XCTAssertNil(GlyphsApplicationDetector.classify(
			bundleIdentifier: "cx.ap.glyphsMcpServerInstaller",
			shortVersion: "1.2.3",
			displayName: "Glyphs MCP Installer",
			fileName: "GlyphsMCPInstaller"
		))
		XCTAssertNil(GlyphsApplicationDetector.classify(
			bundleIdentifier: "com.example.Unrelated",
			shortVersion: "4.0",
			displayName: "Unrelated App",
			fileName: "Unrelated App"
		))
	}

	func testGlyphsApplicationDetectorFindsBothAndPrefersStableBundle() throws {
		let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
		let glyphs3Beta = try makeFakeGlyphsApplication(
			under: root,
			name: "Glyphs 3 Beta",
			bundleIdentifier: "com.GeorgSeifert.Glyphs3Beta",
			shortVersion: "3.6b"
		)
		let glyphs3Stable = try makeFakeGlyphsApplication(
			under: root,
			name: "Glyphs 3",
			bundleIdentifier: "com.GeorgSeifert.Glyphs3",
			shortVersion: "3.5"
		)
		let glyphs4 = try makeFakeGlyphsApplication(
			under: root,
			name: "Glyphs Beta",
			bundleIdentifier: "com.GeorgSeifert.GlyphsBeta",
			shortVersion: "4.0a"
		)
		let unrelated = try makeFakeGlyphsApplication(
			under: root,
			name: "Glyphs MCP Installer",
			bundleIdentifier: "cx.ap.glyphsMcpServerInstaller",
			shortVersion: "1.2.3"
		)

		let detected = GlyphsApplicationDetector.detect(candidates: [glyphs3Beta, glyphs4, unrelated, glyphs3Stable])
		XCTAssertEqual(detected.map(\.majorVersion), [.v3, .v4])
		XCTAssertEqual(detected.first(where: { $0.majorVersion == .v3 })?.bundleIdentifier, "com.GeorgSeifert.Glyphs3")
		XCTAssertEqual(detected.first(where: { $0.majorVersion == .v4 })?.shortVersion, "4.0a")
		XCTAssertEqual(GlyphsApplicationDetector.detect(candidates: [glyphs3Stable]).map(\.majorVersion), [.v3])
		XCTAssertEqual(GlyphsApplicationDetector.detect(candidates: [glyphs4]).map(\.majorVersion), [.v4])
		XCTAssertTrue(GlyphsApplicationDetector.detect(candidates: [unrelated]).isEmpty)
		XCTAssertTrue(GlyphsApplicationDetector.detect(candidates: []).isEmpty)
	}

	func testTargetSelectionDefaultsToEveryDetectedVersionAndExcludesMissing() {
		let targets = [
			makeTargetStatus(version: .v3, detected: true),
			makeTargetStatus(version: .v4, detected: true),
		]
		XCTAssertEqual(InstallerTargetSelectionPolicy.initialSelection(from: targets), Set([.v3, .v4]))

		let oneMissing = [
			makeTargetStatus(version: .v3, detected: false),
			makeTargetStatus(version: .v4, detected: true),
		]
		XCTAssertEqual(InstallerTargetSelectionPolicy.initialSelection(from: oneMissing), Set([.v4]))
	}

	func testTargetSelectionPreservesChoicesDuringRefresh() {
		XCTAssertEqual(
			InstallerTargetSelectionPolicy.reconciledSelection(
				current: [],
				detected: [.v3, .v4],
				hasInitialized: false
			),
			[.v3, .v4]
		)
		XCTAssertEqual(
			InstallerTargetSelectionPolicy.reconciledSelection(
				current: [.v3],
				detected: [.v3, .v4],
				hasInitialized: true
			),
			[.v3]
		)
		XCTAssertEqual(
			InstallerTargetSelectionPolicy.reconciledSelection(
				current: [.v3],
				detected: [.v4],
				hasInitialized: true
			),
			[]
		)
	}

	func testTargetSelectionBlocksOnlySelectedRunningOrInvalidVersion() {
		let targets = [
			makeTargetStatus(version: .v3, detected: true, isRunning: true),
			makeTargetStatus(version: .v4, detected: true),
		]
		XCTAssertNil(InstallerTargetSelectionPolicy.installFailureReason(selectedVersions: [.v4], targets: targets))
		XCTAssertTrue(
			InstallerTargetSelectionPolicy.installFailureReason(selectedVersions: [.v3, .v4], targets: targets)?.contains("Glyphs 3") == true
		)
		XCTAssertNotNil(InstallerTargetSelectionPolicy.installFailureReason(selectedVersions: [], targets: targets))

		let missing = [makeTargetStatus(version: .v3, detected: false)]
		XCTAssertTrue(
			InstallerTargetSelectionPolicy.installFailureReason(selectedVersions: [.v3], targets: missing)?.contains("not detected") == true
		)

		let invalidPython = [
			makeTargetStatus(version: .v3, detected: true),
			makeTargetStatus(version: .v4, detected: true, pythonInstallFailureReason: "Python is unavailable."),
		]
		XCTAssertTrue(
			InstallerTargetSelectionPolicy.installFailureReason(selectedVersions: [.v3, .v4], targets: invalidPython)?.contains("Python is unavailable") == true
		)
	}

	func testAggregateInstallButtonTitleHandlesMixedState() {
		let targets = [
			makeTargetStatus(version: .v3, detected: true, installedPluginVersion: "1.0.0"),
			makeTargetStatus(version: .v4, detected: true),
		]
		XCTAssertEqual(
			InstallerTargetSelectionPolicy.installButtonTitle(selectedVersions: [.v3, .v4], targets: targets),
			"Install / Update Glyphs MCP Server"
		)
		XCTAssertEqual(
			InstallerTargetSelectionPolicy.installButtonTitle(selectedVersions: [.v3], targets: targets),
			"Update Glyphs MCP Server"
		)
	}

	func testInstallTargetPlanDeduplicatesSharedCustomPythonOnly() {
		let python = URL(fileURLWithPath: "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3")
		let shared3 = GlyphsInstallTargetPlan(
			version: .v3,
			pythonSelection: .custom(python3: python),
			pluginsDirectory: InstallerPaths.glyphsPluginsDir(glyphsVersion: .v3),
			pluginInstallStrategy: .bundledPayload
		)
		let shared4 = GlyphsInstallTargetPlan(
			version: .v4,
			pythonSelection: .custom(python3: python),
			pluginsDirectory: InstallerPaths.glyphsPluginsDir(glyphsVersion: .v4),
			pluginInstallStrategy: .bundledPayload
		)
		XCTAssertEqual(shared3.dependencyInstallKey, shared4.dependencyInstallKey)
		XCTAssertNotEqual(shared3.pluginsDirectory, shared4.pluginsDirectory)

		let bundled3 = GlyphsInstallTargetPlan(
			version: .v3,
			pythonSelection: .glyphs(pip3: URL(fileURLWithPath: "/tmp/pip3"), python3: python),
			pluginsDirectory: InstallerPaths.glyphsPluginsDir(glyphsVersion: .v3),
			pluginInstallStrategy: .bundledPayload
		)
		let bundled4 = GlyphsInstallTargetPlan(
			version: .v4,
			pythonSelection: .glyphs(pip3: URL(fileURLWithPath: "/tmp/pip3"), python3: python),
			pluginsDirectory: InstallerPaths.glyphsPluginsDir(glyphsVersion: .v4),
			pluginInstallStrategy: .bundledPayload
		)
		XCTAssertNotEqual(bundled3.dependencyInstallKey, bundled4.dependencyInstallKey)
	}

	func testDevelopmentSymlinkStrategyKeepsByDefaultAndReplacesOnRequest() {
		XCTAssertEqual(
			GlyphsPluginInstallStrategy.resolve(installedPluginIsSymlink: true, replaceDevSymlink: false),
			.keepDevSymlink
		)
		XCTAssertEqual(
			GlyphsPluginInstallStrategy.resolve(installedPluginIsSymlink: true, replaceDevSymlink: true),
			.latestFromGitHub
		)
		XCTAssertEqual(
			GlyphsPluginInstallStrategy.resolve(installedPluginIsSymlink: false, replaceDevSymlink: true),
			.bundledPayload
		)
	}

	func testCodexUninstallerRemovesOnlyMatchingServerBlock() throws {
		let toml = """
		model = "gpt-5"

		[mcp_servers.glyphs-mcp-server]
		url = "http://127.0.0.1:9680/mcp/"
		enabled = true

		[mcp_servers.keep-me]
		url = "https://example.test/mcp"
		"""

		XCTAssertEqual(CodexTomlUninstaller.inspect(toml: toml).safetyState, .removable)
		let updated = try XCTUnwrap(CodexTomlUninstaller.removingMatchingEntry(toml: toml))
		XCTAssertFalse(updated.contains("[mcp_servers.glyphs-mcp-server]"))
		XCTAssertTrue(updated.contains("model = \"gpt-5\""))
		XCTAssertTrue(updated.contains("[mcp_servers.keep-me]"))
	}

	func testCodexUninstallerPreservesSameNamedCustomEntry() {
		let toml = """
		[mcp_servers.glyphs-mcp-server]
		url = "https://custom.example/mcp"
		"""

		XCTAssertEqual(CodexTomlUninstaller.inspect(toml: toml).safetyState, .preserved)
		XCTAssertNil(CodexTomlUninstaller.removingMatchingEntry(toml: toml))
	}

	func testClaudeJSONUninstallerRequiresExactInstallerSignature() throws {
		let root: [String: Any] = [
			"theme": "dark",
			"mcpServers": [
				"glyphs-mcp": ["type": "http", "url": InstallerConstants.endpointURL.absoluteString],
				"keep-me": ["type": "http", "url": "https://example.test/mcp"],
			],
		]
		let data = try JSONSerialization.data(withJSONObject: root)

		XCTAssertEqual(
			ClaudeJSONUninstaller.inspect(json: data, client: .claudeCode, serverName: InstallerConstants.claudeCodeServerName).safetyState,
			.removable
		)
		let updated = try XCTUnwrap(ClaudeJSONUninstaller.removingMatchingEntry(
			json: data,
			client: .claudeCode,
			serverName: InstallerConstants.claudeCodeServerName
		))
		let updatedRoot = try XCTUnwrap(JSONSerialization.jsonObject(with: updated) as? [String: Any])
		let servers = try XCTUnwrap(updatedRoot["mcpServers"] as? [String: Any])
		XCTAssertNil(servers["glyphs-mcp"])
		XCTAssertNotNil(servers["keep-me"])
		XCTAssertEqual(updatedRoot["theme"] as? String, "dark")

		let custom = try JSONSerialization.data(withJSONObject: [
			"mcpServers": ["glyphs-mcp": ["type": "http", "url": "https://custom.example/mcp"]],
		])
		XCTAssertEqual(
			ClaudeJSONUninstaller.inspect(json: custom, client: .claudeCode, serverName: InstallerConstants.claudeCodeServerName).safetyState,
			.preserved
		)
	}

	func testClaudeDesktopUninstallerMatchesMcpRemoteCommand() throws {
		let data = try JSONSerialization.data(withJSONObject: [
			"mcpServers": [
				"glyphs-mcp-server": [
					"command": "npx",
					"args": ["mcp-remote", InstallerConstants.endpointURL.absoluteString],
				],
			],
		])
		XCTAssertEqual(
			ClaudeJSONUninstaller.inspect(json: data, client: .claudeDesktop, serverName: InstallerConstants.claudeDesktopServerName).safetyState,
			.removable
		)
	}

	func testUninstallScannerSelectsOnlyExactManagedArtifacts() throws {
		let root = FileManager.default.temporaryDirectory.appendingPathComponent("glyphs-mcp-uninstall-scan-\(UUID().uuidString)", isDirectory: true)
		defer { try? FileManager.default.removeItem(at: root) }
		let locations = makeUninstallLocations(root: root)
		let plugin3 = try XCTUnwrap(locations.pluginBundles[.v3])
		try FileManager.default.createDirectory(at: plugin3, withIntermediateDirectories: true)

		let managed = locations.codexSkillsRoot.appendingPathComponent("glyphs-mcp-connect", isDirectory: true)
		let similarlyNamed = locations.codexSkillsRoot.appendingPathComponent("glyphs-mcp-private-notes", isDirectory: true)
		try FileManager.default.createDirectory(at: managed, withIntermediateDirectories: true)
		try FileManager.default.createDirectory(at: similarlyNamed, withIntermediateDirectories: true)

		let plan = GlyphsUninstallScanner.scan(managedSkillNames: ["glyphs-mcp-connect"], locations: locations)
		XCTAssertEqual(plan.candidates.first(where: { $0.id == "plugin-3" })?.safetyState, .removable)
		XCTAssertEqual(plan.candidates.first(where: { $0.id == "plugin-4" })?.safetyState, .missing)
		XCTAssertTrue(plan.selectedCandidateIDs.contains("skill-codex-glyphs-mcp-connect"))
		XCTAssertFalse(plan.candidates.contains(where: { $0.location == similarlyNamed }))
	}

	func testUninstallSelectionBlocksOnlySelectedRunningGlyphsVersion() {
		let plugin3 = UninstallCandidate(
			id: "plugin-3",
			component: .plugin,
			title: "Glyphs 3 plug-in",
			location: URL(fileURLWithPath: "/tmp/Glyphs 3/Plugins/Glyphs MCP.glyphsPlugin"),
			safetyState: .removable,
			detail: "Installed",
			glyphsVersion: .v3
		)
		let plugin4 = UninstallCandidate(
			id: "plugin-4",
			component: .plugin,
			title: "Glyphs 4 plug-in",
			location: URL(fileURLWithPath: "/tmp/Glyphs 4/Plugins/Glyphs MCP.glyphsPlugin"),
			safetyState: .removable,
			detail: "Installed",
			glyphsVersion: .v4
		)
		let selected3 = GlyphsUninstallPlan(candidates: [plugin3, plugin4]).selecting(["plugin-3"])

		XCTAssertTrue(GlyphsUninstallSelectionPolicy.canExecute(
			plan: selected3,
			hasAcknowledged: true,
			runningVersions: [.v4],
			isBusy: false
		))
		XCTAssertFalse(GlyphsUninstallSelectionPolicy.canExecute(
			plan: selected3,
			hasAcknowledged: true,
			runningVersions: [.v3],
			isBusy: false
		))
		XCTAssertFalse(GlyphsUninstallSelectionPolicy.canExecute(
			plan: selected3,
			hasAcknowledged: false,
			runningVersions: [],
			isBusy: false
		))
	}

	func testUninstallerRemovesSymlinkWithoutFollowingItAndPreservesPython() throws {
		let root = FileManager.default.temporaryDirectory.appendingPathComponent("glyphs-mcp-uninstall-symlink-\(UUID().uuidString)", isDirectory: true)
		defer { try? FileManager.default.removeItem(at: root) }
		let locations = makeUninstallLocations(root: root)
		let source = root.appendingPathComponent("source/Glyphs MCP.glyphsPlugin", isDirectory: true)
		try FileManager.default.createDirectory(at: source, withIntermediateDirectories: true)
		let sourceMarker = source.appendingPathComponent("keep.txt")
		try Data("keep".utf8).write(to: sourceMarker)

		let plugin4 = try XCTUnwrap(locations.pluginBundles[.v4])
		try FileManager.default.createDirectory(at: plugin4.deletingLastPathComponent(), withIntermediateDirectories: true)
		try FileManager.default.createSymbolicLink(at: plugin4, withDestinationURL: source)
		let pythonMarker = root.appendingPathComponent("Glyphs 4/Scripts/site-packages/shared-package/__init__.py")
		try FileManager.default.createDirectory(at: pythonMarker.deletingLastPathComponent(), withIntermediateDirectories: true)
		try Data("shared".utf8).write(to: pythonMarker)

		let scanned = GlyphsUninstallScanner.scan(managedSkillNames: [], locations: locations)
		let plan = scanned.selecting(["plugin-4"])
		let report = GlyphsUninstaller(log: { _ in }).execute(plan: plan)

		XCTAssertEqual(report.removedCount, 1)
		XCTAssertFalse(GlyphsUninstallScanner.itemExists(at: plugin4))
		XCTAssertTrue(FileManager.default.fileExists(atPath: sourceMarker.path))
		XCTAssertTrue(FileManager.default.fileExists(atPath: pythonMarker.path))
		XCTAssertTrue(FileManager.default.fileExists(atPath: plugin4.deletingLastPathComponent().path))
	}

	func testUninstallerBacksUpConfigAndIsIdempotent() throws {
		let root = FileManager.default.temporaryDirectory.appendingPathComponent("glyphs-mcp-uninstall-config-\(UUID().uuidString)", isDirectory: true)
		defer { try? FileManager.default.removeItem(at: root) }
		let locations = makeUninstallLocations(root: root)
		try FileManager.default.createDirectory(at: locations.codexConfig.deletingLastPathComponent(), withIntermediateDirectories: true)
		let toml = """
		model = "gpt-5"
		[mcp_servers.glyphs-mcp-server]
		url = "http://127.0.0.1:9680/mcp/"
		[mcp_servers.keep-me]
		url = "https://example.test/mcp"
		"""
		try toml.write(to: locations.codexConfig, atomically: true, encoding: .utf8)

		let scanned = GlyphsUninstallScanner.scan(managedSkillNames: [], locations: locations)
		let first = GlyphsUninstaller(log: { _ in }).execute(plan: scanned.selecting(["client-codex"]))
		XCTAssertEqual(first.removedCount, 1)
		let updated = try String(contentsOf: locations.codexConfig, encoding: .utf8)
		XCTAssertFalse(updated.contains("[mcp_servers.glyphs-mcp-server]"))
		XCTAssertTrue(updated.contains("[mcp_servers.keep-me]"))
		let backups = try FileManager.default.contentsOfDirectory(at: locations.codexConfig.deletingLastPathComponent(), includingPropertiesForKeys: nil)
			.filter { $0.lastPathComponent.hasPrefix("config.toml.bak-") }
		XCTAssertEqual(backups.count, 1)

		let rescanned = GlyphsUninstallScanner.scan(managedSkillNames: [], locations: locations)
		XCTAssertEqual(rescanned.candidates.first(where: { $0.id == "client-codex" })?.safetyState, .missing)
		let second = GlyphsUninstaller(log: { _ in }).execute(plan: rescanned.selecting(["client-codex"]))
		XCTAssertEqual(second.removedCount, 0)
		XCTAssertEqual(second.failedCount, 0)
	}

	func testMalformedClientConfigurationIsDisabledAndPreserved() throws {
		let root = FileManager.default.temporaryDirectory.appendingPathComponent("glyphs-mcp-uninstall-malformed-\(UUID().uuidString)", isDirectory: true)
		defer { try? FileManager.default.removeItem(at: root) }
		let locations = makeUninstallLocations(root: root)
		try FileManager.default.createDirectory(at: locations.claudeCodeConfig.deletingLastPathComponent(), withIntermediateDirectories: true)
		try Data("{not-json".utf8).write(to: locations.claudeCodeConfig)

		let plan = GlyphsUninstallScanner.scan(managedSkillNames: [], locations: locations)
		let candidate = try XCTUnwrap(plan.candidates.first(where: { $0.id == "client-claudeCode" }))
		XCTAssertEqual(candidate.safetyState, .blocked)
		XCTAssertFalse(plan.selectedCandidateIDs.contains(candidate.id))
		XCTAssertEqual(try Data(contentsOf: locations.claudeCodeConfig), Data("{not-json".utf8))
	}

	func testUpdatePrepareRequestAcceptsOnlyVersionedExactArguments() throws {
		let identifier = UUID()
		let request = try UpdatePrepareRequest.parse(arguments: [
			"prepare",
			"--protocol", "1",
			"--version", "1.6.0",
			"--glyphs-major", "4",
			"--request-id", identifier.uuidString.lowercased(),
		])
		XCTAssertEqual(request.version, "1.6.0")
		XCTAssertEqual(request.glyphsMajor, 4)
		XCTAssertEqual(request.requestID, identifier)

		for arguments in [
			["prepare", "--protocol", "2", "--version", "1.6.0", "--glyphs-major", "4", "--request-id", identifier.uuidString],
			["prepare", "--protocol", "1", "--version", "v1.6.0", "--glyphs-major", "4", "--request-id", identifier.uuidString],
			["prepare", "--protocol", "1", "--version", "1.6.0", "--glyphs-major", "5", "--request-id", identifier.uuidString],
			["prepare", "--protocol", "1", "--version", "1.6.0", "--glyphs-major", "4", "--destination", "/tmp"],
			["prepare", "--protocol", "1", "--version", "1.6.0", "--glyphs-major", "4", "--request-id", "not-a-uuid"],
		] {
			XCTAssertThrowsError(try UpdatePrepareRequest.parse(arguments: arguments))
		}
	}

	func testUpdatePublishedReleaseRequiresExactStableTrustedAssets() throws {
		let valid = try updateReleaseJSON(
			version: "1.6.0",
			installerURL: "https://github.com/thierryc/Glyphs-mcp/releases/download/v1.6.0/GlyphsMCPInstaller.zip",
			checksumURL: "https://github.com/thierryc/Glyphs-mcp/releases/download/v1.6.0/SHA256SUMS"
		)
		let release = try UpdatePublishedRelease.parse(valid, expectedVersion: "1.6.0")
		XCTAssertEqual(release.tagName, "v1.6.0")

		let hostile = try updateReleaseJSON(
			version: "1.6.0",
			installerURL: "https://attacker.example/GlyphsMCPInstaller.zip",
			checksumURL: "https://github.com/thierryc/Glyphs-mcp/releases/download/v1.6.0/SHA256SUMS"
		)
		XCTAssertThrowsError(try UpdatePublishedRelease.parse(hostile, expectedVersion: "1.6.0"))

		let duplicate = try updateReleaseJSON(
			version: "1.6.0",
			installerURL: "https://github.com/thierryc/Glyphs-mcp/releases/download/v1.6.0/GlyphsMCPInstaller.zip",
			checksumURL: "https://github.com/thierryc/Glyphs-mcp/releases/download/v1.6.0/SHA256SUMS",
			duplicateInstaller: true
		)
		XCTAssertThrowsError(try UpdatePublishedRelease.parse(duplicate, expectedVersion: "1.6.0"))
	}

	func testUpdateChecksumManifestRejectsCorruptDuplicateAndTraversalEntries() throws {
		let data = Data("fixture".utf8)
		let digest = UpdateChecksumManifest.sha256(data)
		XCTAssertEqual(
			try UpdateChecksumManifest.expectedSHA256(
				Data("\(digest)  GlyphsMCPInstaller.zip\n".utf8),
				assetName: "GlyphsMCPInstaller.zip"
			),
			digest
		)
		for manifest in [
			"bad  GlyphsMCPInstaller.zip\n",
			"\(digest)  ../GlyphsMCPInstaller.zip\n",
			"\(digest)  one/GlyphsMCPInstaller.zip\n\(digest)  two/GlyphsMCPInstaller.zip\n",
		] {
			XCTAssertThrowsError(
				try UpdateChecksumManifest.expectedSHA256(
					Data(manifest.utf8),
					assetName: "GlyphsMCPInstaller.zip"
				)
			)
		}
	}

	func testUpdateStagingPreparesExactReleaseReusesStageAndNeverTouchesInstalledPlugin() async throws {
		let root = FileManager.default.temporaryDirectory
			.appendingPathComponent("glyphs-mcp-stage-\(UUID().uuidString)", isDirectory: true)
		defer { try? FileManager.default.removeItem(at: root) }
		let home = root.appendingPathComponent("home", isDirectory: true)
		let paths = UpdateStagingPaths(home: home)
		let installed = root.appendingPathComponent("installed/Glyphs MCP.glyphsPlugin", isDirectory: true)
		try FileManager.default.createDirectory(at: installed, withIntermediateDirectories: true)
		let installedMarker = installed.appendingPathComponent("untouched.txt")
		try Data("live plug-in".utf8).write(to: installedMarker)
		let before = try Data(contentsOf: installedMarker)

		let releaseEndpoint = "http://127.0.0.1:8765/release"
		let installerURL = "http://127.0.0.1:8765/GlyphsMCPInstaller.zip"
		let checksumsURL = "http://127.0.0.1:8765/SHA256SUMS"
		let archiveData = Data("fixture archive".utf8)
		let digest = UpdateChecksumManifest.sha256(archiveData)
		let releaseData = try updateReleaseJSON(
			version: "1.6.0",
			installerURL: installerURL,
			checksumURL: checksumsURL
		)
		let client = FakeUpdateHTTPClient(responses: [
			releaseEndpoint: releaseData,
			installerURL: archiveData,
			checksumsURL: Data("\(digest)  GlyphsMCPInstaller.zip\n".utf8),
		])
		let verifiedPlugin = root.appendingPathComponent("extracted/Glyphs MCP.glyphsPlugin", isDirectory: true)
		let verifier = UpdateTrustVerifier(
			verifyArchive: { _extractedRoot, version in
				try FileManager.default.createDirectory(at: verifiedPlugin, withIntermediateDirectories: true)
				try Data("signed fixture \(version)".utf8).write(
					to: verifiedPlugin.appendingPathComponent("fixture.txt"),
					options: .atomic
				)
				return UpdateVerifiedPlugin(
					bundleURL: verifiedPlugin,
					version: version,
					cdHash: "fixture-cdhash",
					teamIdentifier: UpdateHelperProtocol.expectedTeamIdentifier,
					authority: "Apple Development: Fixture"
				)
			},
			verifyPlugin: { plugin, version in
				guard FileManager.default.fileExists(atPath: plugin.path) else {
					throw UpdateStagingError("signature", "Missing fixture plug-in.")
				}
				return UpdateVerifiedPlugin(
					bundleURL: plugin,
					version: version,
					cdHash: "fixture-cdhash",
					teamIdentifier: UpdateHelperProtocol.expectedTeamIdentifier,
					authority: "Apple Development: Fixture"
				)
			}
		)
		let service = UpdateStagingService(
			paths: paths,
			client: client,
			runner: UpdateCommandRunner { _, _ in "" },
			verifier: verifier,
			environment: ["GLYPHS_MCP_UPDATE_API_URL": releaseEndpoint],
			now: { Date(timeIntervalSince1970: 1_785_379_200) },
			validateArchive: { _ in }
		)
		let first = try UpdatePrepareRequest(
			protocolVersion: 1,
			version: "1.6.0",
			glyphsMajor: 4,
			requestID: UUID()
		)
		let receipt = try await service.prepare(first)
		XCTAssertEqual(receipt.assetSHA256, digest)
		XCTAssertEqual(receipt.pluginCDHash, "fixture-cdhash")
		XCTAssertTrue(FileManager.default.fileExists(atPath: paths.stagedPlugin("1.6.0").path))
		XCTAssertTrue(FileManager.default.fileExists(atPath: paths.authorization(version: "1.6.0", glyphsMajor: 4).path))
		XCTAssertEqual(try Data(contentsOf: installedMarker), before)
		XCTAssertEqual(client.requestedURLs.count, 3)

		let second = try UpdatePrepareRequest(
			protocolVersion: 1,
			version: "1.6.0",
			glyphsMajor: 3,
			requestID: UUID()
		)
		let reused = try await service.prepare(second)
		XCTAssertEqual(reused, receipt)
		XCTAssertEqual(client.requestedURLs.count, 3)
		XCTAssertTrue(FileManager.default.fileExists(atPath: paths.authorization(version: "1.6.0", glyphsMajor: 3).path))
		XCTAssertEqual(try Data(contentsOf: installedMarker), before)
	}

	func testUpdateStagingRejectsChecksumWithoutCreatingReadyStage() async throws {
		let root = FileManager.default.temporaryDirectory
			.appendingPathComponent("glyphs-mcp-stage-bad-\(UUID().uuidString)", isDirectory: true)
		defer { try? FileManager.default.removeItem(at: root) }
		let endpoint = "http://127.0.0.1:8765/release"
		let installerURL = "http://127.0.0.1:8765/GlyphsMCPInstaller.zip"
		let checksumsURL = "http://127.0.0.1:8765/SHA256SUMS"
		let client = FakeUpdateHTTPClient(responses: [
			endpoint: try updateReleaseJSON(version: "1.6.0", installerURL: installerURL, checksumURL: checksumsURL),
			installerURL: Data("corrupt".utf8),
			checksumsURL: Data("\(String(repeating: "0", count: 64))  GlyphsMCPInstaller.zip\n".utf8),
		])
		let paths = UpdateStagingPaths(home: root)
		let service = UpdateStagingService(
			paths: paths,
			client: client,
			runner: UpdateCommandRunner { _, _ in "" },
			verifier: UpdateTrustVerifier(
				verifyArchive: { _, _ in throw UpdateStagingError("unexpected", "Verifier should not run.") },
				verifyPlugin: { _, _ in throw UpdateStagingError("unexpected", "Verifier should not run.") }
			),
			environment: ["GLYPHS_MCP_UPDATE_API_URL": endpoint]
		)
		let request = try UpdatePrepareRequest(
			protocolVersion: 1,
			version: "1.6.0",
			glyphsMajor: 4,
			requestID: UUID()
		)
		do {
			_ = try await service.prepare(request)
			XCTFail("Expected checksum rejection.")
		} catch let error as UpdateStagingError {
			XCTAssertEqual(error.code, "checksum")
		}
		XCTAssertFalse(FileManager.default.fileExists(atPath: paths.stagedVersion("1.6.0").path))
		XCTAssertFalse(FileManager.default.fileExists(atPath: paths.authorization(version: "1.6.0", glyphsMajor: 4).path))
	}

	func testUpdateZipValidatorRejectsMalformedAndEscapingPaths() throws {
		for path in [
			"../GlyphsMCPInstaller.app/Contents/Info.plist",
			"/GlyphsMCPInstaller.app/Contents/Info.plist",
			"Other.app/Contents/Info.plist",
			"GlyphsMCPInstaller.app/../escape",
			"GlyphsMCPInstaller.app\\Contents\\Info.plist",
		] {
			XCTAssertThrowsError(try UpdateZipValidator.validateEntryName(path))
		}
		XCTAssertNoThrow(
			try UpdateZipValidator.validateEntryName(
				"GlyphsMCPInstaller.app/Contents/Info.plist"
			)
		)
		XCTAssertThrowsError(try UpdateZipValidator.validate(Data("not a zip".utf8)))
	}

	func testExtractedTreeValidatorAllowsInternalLinksAndRejectsEscapingLinks() throws {
		let root = FileManager.default.temporaryDirectory
			.appendingPathComponent("glyphs-mcp-extracted-\(UUID().uuidString)", isDirectory: true)
		let outside = FileManager.default.temporaryDirectory
			.appendingPathComponent("glyphs-mcp-outside-\(UUID().uuidString)", isDirectory: true)
		defer {
			try? FileManager.default.removeItem(at: root)
			try? FileManager.default.removeItem(at: outside)
		}
		let versions = root.appendingPathComponent("GlyphsMCPInstaller.app/Contents/Frameworks/Test.framework/Versions", isDirectory: true)
		let versionA = versions.appendingPathComponent("A", isDirectory: true)
		try FileManager.default.createDirectory(at: versionA, withIntermediateDirectories: true)
		let current = versions.appendingPathComponent("Current")
		try FileManager.default.createSymbolicLink(at: current, withDestinationURL: versionA)
		XCTAssertNoThrow(try UpdateExtractedTreeValidator.validate(root))

		try FileManager.default.createDirectory(at: outside, withIntermediateDirectories: true)
		let escape = root.appendingPathComponent("GlyphsMCPInstaller.app/Contents/escape")
		try FileManager.default.createSymbolicLink(at: escape, withDestinationURL: outside)
		XCTAssertThrowsError(try UpdateExtractedTreeValidator.validate(root))
	}

	func testUpdateTrustVerifierRejectsWrongTeamRuntimeTimestampAndNotarization() throws {
		let root = FileManager.default.temporaryDirectory
			.appendingPathComponent("glyphs-mcp-trust-\(UUID().uuidString)", isDirectory: true)
		defer { try? FileManager.default.removeItem(at: root) }
		let app = root.appendingPathComponent("GlyphsMCPInstaller.app", isDirectory: true)
		let plugin = app.appendingPathComponent(
			"Contents/Resources/Payload/Glyphs MCP.glyphsPlugin",
			isDirectory: true
		)
		let pluginExecutable = plugin.appendingPathComponent("Contents/MacOS/plugin")
		try FileManager.default.createDirectory(
			at: pluginExecutable.deletingLastPathComponent(),
			withIntermediateDirectories: true
		)
		try Data("signed fixture".utf8).write(to: pluginExecutable)
		for (url, identifier) in [
			(app, "cx.ap.GlyphsMCPInstaller"),
			(plugin, "cx.ap.GlyphsMCP"),
		] {
			let info: [String: Any] = [
				"CFBundleIdentifier": identifier,
				"CFBundleShortVersionString": "1.6.0",
				"CFBundleVersion": "1.6.0",
			]
			let data = try PropertyListSerialization.data(
				fromPropertyList: info,
				format: .xml,
				options: 0
			)
			let destination = url.appendingPathComponent("Contents/Info.plist")
			try FileManager.default.createDirectory(
				at: destination.deletingLastPathComponent(),
				withIntermediateDirectories: true
			)
			try data.write(to: destination)
		}

		func verifier(
			team: String = UpdateHelperProtocol.expectedTeamIdentifier,
			runtime: Bool = true,
			timestamp: Bool = true,
			notarized: Bool = true
		) -> UpdateTrustVerifier {
			let runner = UpdateCommandRunner { executable, arguments in
				if executable.path == "/usr/bin/codesign", arguments.first == "-d" {
					return [
						"TeamIdentifier=\(team)",
						"Authority=\(UpdateHelperProtocol.expectedDeveloperIDAuthority)",
						"CDHash=fixture-cdhash",
						runtime ? "flags=0x10000(runtime)" : "flags=0x0",
						timestamp ? "Timestamp=Jul 30, 2026" : "",
					].joined(separator: "\n")
				}
				if executable.path == "/usr/bin/xcrun",
				   arguments.first == "stapler",
				   !notarized {
					throw UpdateStagingError("verification", "Missing notarization.")
				}
				return ""
			}
			return UpdateTrustVerifier.live(runner: runner)
		}

		let verified = try verifier().verifyArchive(root, "1.6.0")
		XCTAssertEqual(verified.bundleURL, plugin)
		XCTAssertEqual(verified.cdHash, "fixture-cdhash")
		XCTAssertThrowsError(try verifier().verifyArchive(root, "1.6.1"))
		for rejected in [
			verifier(team: "ATTACKER"),
			verifier(runtime: false),
			verifier(timestamp: false),
			verifier(notarized: false),
		] {
			XCTAssertThrowsError(try rejected.verifyArchive(root, "1.6.0"))
		}
	}

	func testUpdateStagingRecordsBoundedNetworkFailureWithoutReadyArtifacts() async throws {
		let root = FileManager.default.temporaryDirectory
			.appendingPathComponent("glyphs-mcp-stage-timeout-\(UUID().uuidString)", isDirectory: true)
		defer { try? FileManager.default.removeItem(at: root) }
		let paths = UpdateStagingPaths(home: root)
		let service = UpdateStagingService(
			paths: paths,
			client: ThrowingUpdateHTTPClient(
				error: UpdateStagingError("network", "The request timed out.")
			),
			environment: [:]
		)
		let request = try UpdatePrepareRequest(
			protocolVersion: 1,
			version: "1.6.0",
			glyphsMajor: 4,
			requestID: UUID()
		)
		do {
			_ = try await service.prepare(request)
			XCTFail("Expected network failure.")
		} catch let error as UpdateStagingError {
			XCTAssertEqual(error.code, "network")
		}
		let decoder = JSONDecoder()
		decoder.dateDecodingStrategy = .iso8601
		let status = try decoder.decode(
			UpdatePreparationStatus.self,
			from: Data(contentsOf: paths.requestStatus(request.requestID))
		)
		XCTAssertEqual(status.phase, .failed)
		XCTAssertEqual(status.errorCode, "network")
		XCTAssertFalse(FileManager.default.fileExists(atPath: paths.stagedVersion("1.6.0").path))
	}

	func testUpdateStagingCancellationWritesCancelledStatusAndCleansTemporaryData() async throws {
		let root = FileManager.default.temporaryDirectory
			.appendingPathComponent("glyphs-mcp-stage-cancel-\(UUID().uuidString)", isDirectory: true)
		defer { try? FileManager.default.removeItem(at: root) }
		let paths = UpdateStagingPaths(home: root)
		let service = UpdateStagingService(
			paths: paths,
			client: CancellableUpdateHTTPClient(),
			environment: [:]
		)
		let request = try UpdatePrepareRequest(
			protocolVersion: 1,
			version: "1.6.0",
			glyphsMajor: 3,
			requestID: UUID()
		)
		let task = Task { try await service.prepare(request) }
		try await Task.sleep(nanoseconds: 30_000_000)
		task.cancel()
		do {
			_ = try await task.value
			XCTFail("Expected cancellation.")
		} catch let error as UpdateStagingError {
			XCTAssertEqual(error.code, "cancelled")
		}
		let decoder = JSONDecoder()
		decoder.dateDecodingStrategy = .iso8601
		let status = try decoder.decode(
			UpdatePreparationStatus.self,
			from: Data(contentsOf: paths.requestStatus(request.requestID))
		)
		XCTAssertEqual(status.phase, .cancelled)
		XCTAssertFalse(FileManager.default.fileExists(
			atPath: paths.temporary.appendingPathComponent(request.requestID.uuidString.lowercased()).path
		))
	}

	func testUpdateHelperManagerPersistsPerTargetOptInAndRemovesOnlyAfterLastTarget() throws {
		let root = FileManager.default.temporaryDirectory
			.appendingPathComponent("glyphs-mcp-helper-\(UUID().uuidString)", isDirectory: true)
		defer { try? FileManager.default.removeItem(at: root) }
		let home = root.appendingPathComponent("home", isDirectory: true)
		let source = root.appendingPathComponent("GlyphsMCPUpdater")
		try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
		try Data("signed helper".utf8).write(to: source)
		let box = UpdateOptInBox()
		let store = UpdateOptInStore(
			isEnabled: { box.get($0) },
			setEnabled: { box.set($0, $1) }
		)
		let verifier = UpdateHelperVerifier { url in
			XCTAssertTrue(FileManager.default.fileExists(atPath: url.path))
			return VerifiedUpdateHelper(
				executableURL: url,
				probe: UpdateHelperProbe(build: "test"),
				cdHash: "helper-cdhash",
				teamIdentifier: UpdateHelperProtocol.expectedTeamIdentifier,
				authority: "Apple Development: Fixture"
			)
		}
		let manager = UpdateHelperManager(
			paths: UpdateStagingPaths(home: home),
			store: store,
			verifier: verifier
		)
		try manager.configure(embeddedExecutable: source, selections: [.v3: true, .v4: true])
		XCTAssertTrue(box.get(.v3))
		XCTAssertTrue(box.get(.v4))
		XCTAssertTrue(FileManager.default.fileExists(atPath: manager.paths.helperExecutable.path))
		XCTAssertTrue(FileManager.default.fileExists(atPath: manager.paths.installReceipt.path))
		let authorization3 = manager.paths.authorization(version: "1.6.0", glyphsMajor: 3)
		let stagedMarker = manager.paths.stagedVersion("1.6.0").appendingPathComponent("keep.txt")
		try FileManager.default.createDirectory(at: authorization3.deletingLastPathComponent(), withIntermediateDirectories: true)
		try Data("authorized".utf8).write(to: authorization3)
		try FileManager.default.createDirectory(at: stagedMarker.deletingLastPathComponent(), withIntermediateDirectories: true)
		try Data("verified stage".utf8).write(to: stagedMarker)

		try manager.configure(embeddedExecutable: source, selections: [.v3: false])
		XCTAssertFalse(box.get(.v3))
		XCTAssertTrue(box.get(.v4))
		XCTAssertTrue(FileManager.default.fileExists(atPath: manager.paths.helperExecutable.path))
		XCTAssertFalse(FileManager.default.fileExists(atPath: authorization3.path))
		XCTAssertTrue(FileManager.default.fileExists(atPath: stagedMarker.path))

		try manager.configure(embeddedExecutable: source, selections: [.v4: false])
		XCTAssertFalse(box.get(.v4))
		XCTAssertFalse(GlyphsUninstallScanner.itemExists(at: manager.paths.root))
	}

	func testUpdateHelperManagerDoesNotRecordOptInWhenVerificationFails() throws {
		let root = FileManager.default.temporaryDirectory
			.appendingPathComponent("glyphs-mcp-helper-fail-\(UUID().uuidString)", isDirectory: true)
		defer { try? FileManager.default.removeItem(at: root) }
		try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
		let source = root.appendingPathComponent("GlyphsMCPUpdater")
		try Data("untrusted".utf8).write(to: source)
		let box = UpdateOptInBox()
		let manager = UpdateHelperManager(
			paths: UpdateStagingPaths(home: root.appendingPathComponent("home")),
			store: UpdateOptInStore(
				isEnabled: { box.get($0) },
				setEnabled: { box.set($0, $1) }
			),
			verifier: UpdateHelperVerifier { _ in
				throw UpdateStagingError("helper_signature", "Untrusted helper.")
			}
		)
		XCTAssertThrowsError(
			try manager.configure(embeddedExecutable: source, selections: [.v4: true])
		)
		XCTAssertFalse(box.get(.v4))
		XCTAssertFalse(FileManager.default.fileExists(atPath: manager.paths.helperExecutable.path))
	}

	func testUpdateHelperManagerRollsBackHelperAndReceiptWhenFinalVerificationFails() throws {
		let root = FileManager.default.temporaryDirectory
			.appendingPathComponent("glyphs-mcp-helper-rollback-\(UUID().uuidString)", isDirectory: true)
		defer { try? FileManager.default.removeItem(at: root) }
		try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
		let oldSource = root.appendingPathComponent("OldUpdater")
		let newSource = root.appendingPathComponent("NewUpdater")
		try Data("old helper".utf8).write(to: oldSource)
		try Data("new helper".utf8).write(to: newSource)
		let paths = UpdateStagingPaths(home: root.appendingPathComponent("home"))
		let box = UpdateOptInBox()
		let verifier = UpdateHelperVerifier { url in
			let contents = try String(contentsOf: url, encoding: .utf8)
			if url == paths.helperExecutable, contents == "new helper" {
				throw UpdateStagingError("helper_signature", "Final helper verification failed.")
			}
			return VerifiedUpdateHelper(
				executableURL: url,
				probe: UpdateHelperProbe(build: "test"),
				cdHash: contents == "old helper" ? "old-cdhash" : "new-cdhash",
				teamIdentifier: UpdateHelperProtocol.expectedTeamIdentifier,
				authority: "Apple Development: Fixture"
			)
		}
		let manager = UpdateHelperManager(
			paths: paths,
			store: UpdateOptInStore(
				isEnabled: { box.get($0) },
				setEnabled: { box.set($0, $1) }
			),
			verifier: verifier
		)
		try manager.configure(embeddedExecutable: oldSource, selections: [.v4: true])
		let originalReceipt = try Data(contentsOf: paths.installReceipt)

		XCTAssertThrowsError(
			try manager.configure(embeddedExecutable: newSource, selections: [.v4: true])
		)
		XCTAssertEqual(
			try String(contentsOf: paths.helperExecutable, encoding: .utf8),
			"old helper"
		)
		XCTAssertEqual(try Data(contentsOf: paths.installReceipt), originalReceipt)
		XCTAssertTrue(box.get(.v4))
	}

	func testUpdaterUninstallCandidateRequiresMarkerAndRecognizedContents() throws {
		let root = FileManager.default.temporaryDirectory
			.appendingPathComponent("glyphs-mcp-updater-uninstall-\(UUID().uuidString)", isDirectory: true)
		defer { try? FileManager.default.removeItem(at: root) }
		let locations = makeUninstallLocations(root: root, updaterRoot: root.appendingPathComponent("Updater", isDirectory: true))
		let updater = try XCTUnwrap(locations.updaterRoot)
		try FileManager.default.createDirectory(at: updater, withIntermediateDirectories: true)
		try Data(UpdateHelperProtocol.managedMarker.utf8).write(
			to: updater.appendingPathComponent(".managed-by-glyphs-mcp")
		)
		try Data("helper".utf8).write(to: updater.appendingPathComponent(UpdateHelperProtocol.executableName))
		var plan = GlyphsUninstallScanner.scan(managedSkillNames: [], locations: locations)
		XCTAssertEqual(plan.candidates.first(where: { $0.id == "updater" })?.safetyState, .removable)

		try Data("private".utf8).write(to: updater.appendingPathComponent("unrecognized.txt"))
		plan = GlyphsUninstallScanner.scan(managedSkillNames: [], locations: locations)
		XCTAssertEqual(plan.candidates.first(where: { $0.id == "updater" })?.safetyState, .blocked)
	}

	private func updateReleaseJSON(
		version: String,
		installerURL: String,
		checksumURL: String,
		duplicateInstaller: Bool = false
	) throws -> Data {
		var assets: [[String: String]] = [
			["name": "GlyphsMCPInstaller.zip", "browser_download_url": installerURL],
			["name": "SHA256SUMS", "browser_download_url": checksumURL],
		]
		if duplicateInstaller {
			assets.append(["name": "GlyphsMCPInstaller.zip", "browser_download_url": installerURL])
		}
		return try JSONSerialization.data(withJSONObject: [
			"tag_name": "v\(version)",
			"draft": false,
			"prerelease": false,
			"published_at": "2026-07-30T00:00:00Z",
			"assets": assets,
		], options: [.sortedKeys])
	}

	private func makeUninstallLocations(root: URL, updaterRoot: URL? = nil) -> GlyphsUninstallLocations {
		GlyphsUninstallLocations(
			pluginBundles: [
				.v3: root.appendingPathComponent("Glyphs 3/Plugins/Glyphs MCP.glyphsPlugin", isDirectory: true),
				.v4: root.appendingPathComponent("Glyphs 4/Plugins/Glyphs MCP.glyphsPlugin", isDirectory: true),
			],
			codexSkillsRoot: root.appendingPathComponent(".codex/skills", isDirectory: true),
			claudeCodeSkillsRoot: root.appendingPathComponent(".claude/skills", isDirectory: true),
			codexConfig: root.appendingPathComponent(".codex/config.toml"),
			claudeDesktopConfig: root.appendingPathComponent("Claude/claude_desktop_config.json"),
			claudeCodeConfig: root.appendingPathComponent(".claude.json"),
			updaterRoot: updaterRoot
		)
	}

	private func makeFakeGlyphsApplication(
		under root: URL,
		name: String,
		bundleIdentifier: String,
		shortVersion: String
	) throws -> URL {
		let appURL = root.appendingPathComponent("\(name).app", isDirectory: true)
		let contents = appURL.appendingPathComponent("Contents", isDirectory: true)
		try FileManager.default.createDirectory(at: contents, withIntermediateDirectories: true, attributes: nil)
		let plist: [String: Any] = [
			"CFBundleIdentifier": bundleIdentifier,
			"CFBundleShortVersionString": shortVersion,
			"CFBundleDisplayName": name,
		]
		let data = try PropertyListSerialization.data(fromPropertyList: plist, format: .xml, options: 0)
		try data.write(to: contents.appendingPathComponent("Info.plist"))
		return appURL
	}

	private func makeTargetStatus(
		version: GlyphsMajorVersion,
		detected: Bool,
		isRunning: Bool = false,
		installedPluginVersion: String? = nil,
		pythonInstallFailureReason: String? = nil
	) -> GlyphsTargetStatusSnapshot {
		let app = detected ? GlyphsApplicationInfo(
			majorVersion: version,
			appURL: URL(fileURLWithPath: "/Applications/\(version.displayName).app"),
			bundleIdentifier: version.stableBundleIdentifier,
			shortVersion: version.rawValue + ".0",
			displayName: version.displayName,
			isBeta: false
		) : nil
		let pluginVersion = installedPluginVersion.map {
			PluginBundleVersion(shortVersion: $0, buildVersion: $0)
		}
		let pluginURL = InstallerPaths.glyphsPluginsDir(glyphsVersion: version)
			.appendingPathComponent("Glyphs MCP.glyphsPlugin", isDirectory: true)
		let inspection = PluginInstaller.InstalledPluginInspection(
			bundleURL: pluginURL,
			mode: pluginVersion == nil ? .notInstalled : .bundle,
			version: pluginVersion,
			symlinkTargetPath: nil
		)
		let pythonStatus = GlyphsPythonStatus(
			source: pythonInstallFailureReason == nil ? .glyphsSetting : nil,
			version: pythonInstallFailureReason == nil ? "3.14.0" : nil,
			pythonPath: pythonInstallFailureReason == nil ? "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3" : nil,
			pipPath: nil,
			summary: pythonInstallFailureReason == nil ? "Using Glyphs-selected Python 3.14.0" : "No usable Glyphs Python detected",
			installFailureReason: pythonInstallFailureReason
		)
		return GlyphsTargetStatusSnapshot(
			version: version,
			application: app,
			baseDirectory: InstallerPaths.glyphsBaseDir(glyphsVersion: version),
			pluginsDirectory: InstallerPaths.glyphsPluginsDir(glyphsVersion: version),
			pluginInspection: inspection,
			payloadPluginVersion: PluginBundleVersion(shortVersion: "1.2.3", buildVersion: "1.2.3"),
			pythonStatus: pythonStatus,
			isRunning: isRunning
		)
	}
}
