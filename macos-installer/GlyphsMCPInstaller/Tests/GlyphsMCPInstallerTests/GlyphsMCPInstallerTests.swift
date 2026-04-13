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

	func testClaudeCliListInspectorDetectsNoServersConfigured() {
		let output = "No MCP servers configured. Use `claude mcp add` to add a server."
		XCTAssertEqual(ClaudeCliListInspector.detectNoServersConfigured(output: output), "No MCP servers configured.")
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
				skills: [.init(kind: .codex, installedSkillNames: ["glyphs-mcp-connect"])]
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

	func testGlyphsPythonResolverBlocksUnsupportedVersion() throws {
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
		XCTAssertTrue(detectedKinds.contains(.claudeCode))
		XCTAssertTrue(snapshot.detectedClientsSummary.contains("Codex"))
		XCTAssertTrue(snapshot.detectedClientsSummary.contains("Claude Code"))
		let codex = snapshot.clients.first(where: { $0.kind == .codex })
		let claude = snapshot.clients.first(where: { $0.kind == .claudeCode })
		XCTAssertEqual(codex?.statusText, "Configured")
		XCTAssertEqual(codex?.appStatus.summary, "Installed")
		XCTAssertEqual(codex?.cliStatus.summary, "Installed")
		XCTAssertEqual(codex?.configStatus.summary, "Configured")
		XCTAssertEqual(codex?.detailText, "Codex app and CLI share ~/.codex/config.toml.")
		XCTAssertEqual(claude?.statusText, "Configured")
		XCTAssertEqual(claude?.appStatus.summary, "Installed")
		XCTAssertEqual(claude?.cliStatus.summary, "Installed")
		XCTAssertEqual(claude?.configStatus.summary, "Configured")
		XCTAssertEqual(claude?.detailText, "Claude app and Claude Code CLI share ~/.claude.json.")

		let firstUndetectedIndex = snapshot.clients.firstIndex(where: { !$0.detected }) ?? snapshot.clients.endIndex
		let detectedPrefix = snapshot.clients[..<firstUndetectedIndex]
		XCTAssertTrue(detectedPrefix.allSatisfy(\.detected))
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
		XCTAssertEqual(claude?.appStatus.summary, "Not found")
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
		let codexSkill = codexRoot.appendingPathComponent("glyphs-mcp-connect", isDirectory: true)

		try FileManager.default.createDirectory(at: plugin, withIntermediateDirectories: true, attributes: nil)
		try FileManager.default.createDirectory(at: skillsDir.appendingPathComponent("glyphs-mcp-connect", isDirectory: true), withIntermediateDirectories: true, attributes: nil)
		try FileManager.default.createDirectory(at: skillsDir.appendingPathComponent("glyphs-mcp-spacing", isDirectory: true), withIntermediateDirectories: true, attributes: nil)
		try "mcp\n".write(to: req, atomically: true, encoding: .utf8)
		try FileManager.default.createDirectory(at: codexSkill, withIntermediateDirectories: true, attributes: nil)

		let payload = InstallerPayload(payloadDir: payloadDir, pluginBundle: plugin, requirementsTxt: req, skillsDir: skillsDir)
		let detected = InstallerSkillTargetDetector.detect(payload: payload, codexRoot: codexRoot, claudeCodeRoot: claudeRoot)

		let codexTarget = try XCTUnwrap(detected.first(where: { $0.kind == .codex }))
		let claudeTarget = try XCTUnwrap(detected.first(where: { $0.kind == .claudeCode }))
		XCTAssertEqual(codexTarget.installedSkillNames, ["glyphs-mcp-connect"])
		XCTAssertTrue(codexTarget.hasInstalledSkills)
		XCTAssertEqual(claudeTarget.installedSkillNames, [])
		XCTAssertFalse(claudeTarget.hasInstalledSkills)
	}

	func testInstallerClientOrderingPutsDetectedClientsFirst() {
		let ordered = InstallerClientOrdering.ordered([
			.init(kind: .claudeCode, isDetected: true),
			.init(kind: .codex, isDetected: true),
		])

		XCTAssertEqual(
			ordered.map(\.kind),
			[InstallerClientKind.codex, .claudeCode]
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

	func testPayloadManagedSkillDirectoriesFiltersGlyphsSkills() throws {
		let tmp = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
		let payloadDir = tmp.appendingPathComponent("Payload", isDirectory: true)
		let plugin = payloadDir.appendingPathComponent("Glyphs MCP.glyphsPlugin", isDirectory: true)
		let req = payloadDir.appendingPathComponent("requirements.txt")
		let skillsDir = payloadDir.appendingPathComponent("skills", isDirectory: true)

		try FileManager.default.createDirectory(at: plugin, withIntermediateDirectories: true, attributes: nil)
		try FileManager.default.createDirectory(at: skillsDir.appendingPathComponent("glyphs-mcp-connect", isDirectory: true), withIntermediateDirectories: true, attributes: nil)
		try FileManager.default.createDirectory(at: skillsDir.appendingPathComponent("glyphs-mcp-spacing", isDirectory: true), withIntermediateDirectories: true, attributes: nil)
		try FileManager.default.createDirectory(at: skillsDir.appendingPathComponent("other-skill", isDirectory: true), withIntermediateDirectories: true, attributes: nil)
		try "mcp\n".write(to: req, atomically: true, encoding: .utf8)

		let payload = InstallerPayload(payloadDir: payloadDir, pluginBundle: plugin, requirementsTxt: req, skillsDir: skillsDir)
		let managed = payload.managedSkillDirectories().map(\.lastPathComponent)
		XCTAssertEqual(managed, ["glyphs-mcp-connect", "glyphs-mcp-spacing"])
	}

	func testAgentSkillBundleInstallerOverwritesManagedSkillsOnlyWhenRequested() throws {
		let tmp = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
		let payloadDir = tmp.appendingPathComponent("Payload", isDirectory: true)
		let plugin = payloadDir.appendingPathComponent("Glyphs MCP.glyphsPlugin", isDirectory: true)
		let req = payloadDir.appendingPathComponent("requirements.txt")
		let skillsDir = payloadDir.appendingPathComponent("skills", isDirectory: true)
		let connect = skillsDir.appendingPathComponent("glyphs-mcp-connect", isDirectory: true)
		let spacing = skillsDir.appendingPathComponent("glyphs-mcp-spacing", isDirectory: true)
		let destRoot = tmp.appendingPathComponent("dest", isDirectory: true)
		let existingManaged = destRoot.appendingPathComponent("glyphs-mcp-connect", isDirectory: true)
		let unrelated = destRoot.appendingPathComponent("third-party-skill", isDirectory: true)

		try FileManager.default.createDirectory(at: plugin, withIntermediateDirectories: true, attributes: nil)
		try FileManager.default.createDirectory(at: connect, withIntermediateDirectories: true, attributes: nil)
		try FileManager.default.createDirectory(at: spacing, withIntermediateDirectories: true, attributes: nil)
		try FileManager.default.createDirectory(at: existingManaged, withIntermediateDirectories: true, attributes: nil)
		try FileManager.default.createDirectory(at: unrelated, withIntermediateDirectories: true, attributes: nil)
		try "mcp\n".write(to: req, atomically: true, encoding: .utf8)
		try "new managed\n".write(to: connect.appendingPathComponent("SKILL.md"), atomically: true, encoding: .utf8)
		try "new spacing\n".write(to: spacing.appendingPathComponent("SKILL.md"), atomically: true, encoding: .utf8)
		try "old managed\n".write(to: existingManaged.appendingPathComponent("SKILL.md"), atomically: true, encoding: .utf8)
		try "keep me\n".write(to: unrelated.appendingPathComponent("SKILL.md"), atomically: true, encoding: .utf8)

		let payload = InstallerPayload(payloadDir: payloadDir, pluginBundle: plugin, requirementsTxt: req, skillsDir: skillsDir)
		let installer = AgentSkillBundleInstaller(log: { _ in })
		_ = try installer.installManagedSkills(from: payload, to: destRoot, clientName: "Codex", overwriteExisting: true)

		XCTAssertEqual(try String(contentsOf: existingManaged.appendingPathComponent("SKILL.md"), encoding: .utf8), "new managed\n")
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
