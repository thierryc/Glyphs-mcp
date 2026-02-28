import AppKit
import Combine
import Foundation
import SwiftUI
import GlyphsMCPInstallerCore

enum InstallerRoute: Hashable {
	case preflight
	case check
	case pythonTarget
	case install
	case clients
	case finish
}

enum PythonMode: String, CaseIterable, Hashable {
	case glyphs
	case custom
}

@MainActor
final class InstallerViewModel: ObservableObject {
	@Published var navPath: [InstallerRoute] = []

	@Published var isGuidedSetupFlow: Bool = false

	@Published var preflight = PreflightResult.empty
	@Published var check = CheckResult.empty
	@Published var pythonMode: PythonMode = .glyphs
	@Published var selectedCustomPythonPath: String? = nil
	@Published var doInstallDependencies: Bool = true
	@Published var doInstallPluginBundle: Bool = true

	@Published var logText: String = ""
	@Published var isBusy: Bool = false
	@Published var installSteps: [InstallStep] = InstallStep.defaultSteps
	@Published var installSucceeded: Bool = false
	@Published var didRunInstall: Bool = false
	@Published var restartRecommended: Bool = false

	@Published var githubStatus: PluginUpdateStatus = .idle
	@Published var installedPluginVersion: PluginBundleVersion? = nil
	@Published var payloadPluginVersion: PluginBundleVersion? = nil
	@Published var githubPluginVersion: PluginBundleVersion? = nil
	@Published var useGitHubPluginForInstall: Bool = false

	@Published var configureCodex: Bool = true
	@Published var configureClaudeDesktop: Bool = true
	@Published var configureClaudeCode: Bool = true
	@Published var configureAntigravity: Bool = true

	@Published var createStarterFolder: Bool = false
	@Published var starterParentFolder: URL? = nil
	@Published var starterProjectName: String = "Glyphs MCP Project"
	@Published var createdStarterProjectFolder: URL? = nil

	let glyphsPluginsDir: URL = InstallerPaths.glyphsPluginsDir

	private let runner = ProcessRunner()
	private var lastLogAt: Date = .distantPast
	private var installTask: Task<Void, Never>? = nil
	private var clientsTask: Task<Void, Never>? = nil
	private var heartbeatTask: Task<Void, Never>? = nil

	func go(_ route: InstallerRoute) {
		navPath.append(route)
	}

	func back() {
		_ = navPath.popLast()
	}

	func goHome() {
		navPath.removeAll()
		isGuidedSetupFlow = false
	}

	func scanPreflight() {
		preflight = Preflight.scan()
		refreshLocalPluginVersions()

		// Default the mode to match what Glyphs is configured to use.
		// If Glyphs points at a python.org framework, treat it as "Custom Python".
		// Otherwise, prefer Glyphs' bundled Python (GlyphsPythonPlugin) when available.
		if preflight.glyphsSelectedPythonFrameworkPath != nil {
			pythonMode = .custom
		} else if preflight.glyphsPipPath != nil {
			pythonMode = .glyphs
		} else {
			pythonMode = .custom
		}

		// Preselect the custom interpreter to match Glyphs' selected framework when possible.
		if pythonMode == .custom, selectedCustomPythonPath == nil {
			if let glyphsFramework = preflight.glyphsSelectedPythonFrameworkPath {
				selectedCustomPythonPath = preflight.customPythons.first(where: { $0.path.hasPrefix(glyphsFramework) })?.path
			}
			if selectedCustomPythonPath == nil {
				selectedCustomPythonPath = preflight.customPythons.first?.path
			}
		}

		Task { await refreshGitHubPluginVersionIfNeeded(force: false) }
	}

	func scanCheck() {
		check = Check.scan()
		refreshLocalPluginVersions()
		Task { await refreshGitHubPluginVersionIfNeeded(force: false) }
	}

	func appendLog(_ line: String) {
		lastLogAt = Date()
		if logText.isEmpty {
			logText = line
		} else {
			logText += "\n" + line
		}
	}

	func chooseCustomPythonViaPicker() {
		let panel = NSOpenPanel()
		panel.allowsMultipleSelection = false
		panel.canChooseDirectories = false
		panel.canChooseFiles = true
		panel.title = "Choose Python interpreter"
		panel.prompt = "Choose"
		panel.begin { [weak self] resp in
			guard let self, resp == .OK, let url = panel.url else { return }
			Task { @MainActor in
				self.selectedCustomPythonPath = url.path
			}
		}
	}

	func chooseStarterParentFolder() {
		let panel = NSOpenPanel()
		panel.allowsMultipleSelection = false
		panel.canChooseFiles = false
		panel.canChooseDirectories = true
		panel.canCreateDirectories = true
		panel.title = "Choose where to create the starter project folder"
		panel.prompt = "Choose"
		panel.begin { [weak self] resp in
			guard let self, resp == .OK, let url = panel.url else { return }
			Task { @MainActor in
				self.starterParentFolder = url
			}
		}
	}

	func revealInFinder(url: URL) {
		NSWorkspace.shared.activateFileViewerSelecting([url])
	}

	func startInstall() {
		guard !isBusy else { return }
		didRunInstall = true
		isBusy = true
		installSucceeded = false
		restartRecommended = false
		createdStarterProjectFolder = nil
		installSteps = InstallStep.makeSteps(includeDownload: useGitHubPluginForInstall, includeDeps: doInstallDependencies, includePlugin: doInstallPluginBundle)

		logText = ""
		appendLog("== Install ==")

		do {
			if !doInstallDependencies && !doInstallPluginBundle {
				throw InstallerError.userFacing("Nothing to do: enable dependencies and/or plug‑in install.")
			}

			let pythonForDeps: PythonSelection? = doInstallDependencies ? try resolvePythonForDeps() : nil
			let glyphsRunning = doInstallPluginBundle && GlyphsRuntime.isGlyphsRunning()
			if glyphsRunning {
				appendLog("Note: Glyphs appears to be running. A restart may be required to load the plug‑in.")
			}

			let allowReplacePlugin = confirmReplacePluginIfNeeded()
			let options = InstallOptions(
				useGitHubPluginForInstall: useGitHubPluginForInstall,
				doInstallDependencies: doInstallDependencies,
				doInstallPluginBundle: doInstallPluginBundle,
				pythonForDeps: pythonForDeps,
				glyphsRunning: glyphsRunning,
				allowReplacePlugin: allowReplacePlugin
			)

			beginHeartbeat()
			installTask?.cancel()
			let log: @Sendable (String) -> Void = { [weak self] line in
				Task { @MainActor in
					self?.appendLog(line)
				}
			}
			let mark: @Sendable (InstallStep.ID, InstallStep.State) -> Void = { [weak self] id, state in
				Task { @MainActor in
					guard let self else { return }
					InstallStep.mark(&self.installSteps, state, for: id)
				}
			}
			let finish: @Sendable (_ succeeded: Bool, _ restartRecommended: Bool) -> Void = { [weak self] succeeded, restartRecommended in
				Task { @MainActor in
					guard let self else { return }
					self.stopHeartbeat()
					self.installSucceeded = succeeded
					self.restartRecommended = restartRecommended
					self.isBusy = false
					self.refreshLocalPluginVersions()
					Task { await self.refreshGitHubPluginVersionIfNeeded(force: false) }
				}
			}

			installTask = Task.detached(priority: .userInitiated) { [runner, options] in
				await InstallerViewModel.runInstallDetached(options: options, runner: runner, log: log, mark: mark, finish: finish)
			}
		} catch {
			appendLog("ERROR: \(error.localizedDescription)")
			isBusy = false
		}
	}

	func cancelInstall() {
		installTask?.cancel()
		installTask = nil
		stopHeartbeat()
		isBusy = false
		appendLog("Cancelled.")
	}

	func startClientConfig() {
		guard !isBusy else { return }
		isBusy = true
		appendLog("== Configure clients ==")

		let options = ClientsOptions(
			configureCodex: configureCodex,
			configureClaudeDesktop: configureClaudeDesktop,
			configureClaudeCode: configureClaudeCode,
			configureAntigravity: configureAntigravity
		)
		clientsTask?.cancel()
		let log: @Sendable (String) -> Void = { [weak self] line in
			Task { @MainActor in
				self?.appendLog(line)
			}
		}
		let finish: @Sendable () -> Void = { [weak self] in
			Task { @MainActor in
				self?.isBusy = false
			}
		}
		clientsTask = Task.detached(priority: .userInitiated) { [runner, options] in
			await InstallerViewModel.runClientsDetached(options: options, runner: runner, log: log, finish: finish)
		}
	}

	func cancelClientConfig() {
		clientsTask?.cancel()
		clientsTask = nil
		isBusy = false
		appendLog("Cancelled.")
	}

	func createStarterProject() async {
		guard let parent = starterParentFolder else { return }
		isBusy = true
		appendLog("== Starter project ==")
		do {
			let name = starterProjectName.trimmingCharacters(in: .whitespacesAndNewlines)
			let created = try StarterProjectCreator(log: appendLog).createStarterProject(in: parent, projectName: name.isEmpty ? nil : name)
			createdStarterProjectFolder = created
			appendLog("Created starter folder: \(created.path)")
		} catch {
			appendLog("ERROR: \(error.localizedDescription)")
		}
		isBusy = false
	}

	private func resolvePythonForDeps() throws -> PythonSelection {
		switch pythonMode {
		case .glyphs:
			guard let pipPath = preflight.glyphsPipPath else {
				throw InstallerError.userFacing("Glyphs Python (pip3) was not found. In Glyphs: Settings → Addons → install Python (GlyphsPythonPlugin), then re-run.")
			}
			let pip = URL(fileURLWithPath: pipPath)
			let python = pip.deletingLastPathComponent().appendingPathComponent("python3")
			return .glyphs(pip3: pip, python3: python)
		case .custom:
			guard let path = selectedCustomPythonPath, !path.isEmpty else {
				throw InstallerError.userFacing("Select a custom Python interpreter first.")
			}
			return .custom(python3: URL(fileURLWithPath: path))
		}
	}

	private func confirmReplacePluginIfNeeded() -> Bool {
		guard doInstallPluginBundle else { return true }
		let dest = InstallerPaths.glyphsPluginsDir.appendingPathComponent("Glyphs MCP.glyphsPlugin", isDirectory: true)
		guard FileManager.default.fileExists(atPath: dest.path) else { return true }

		let prev = PluginVersionReader.readPluginVersion(pluginBundle: dest)?.displayString ?? "Unknown"
		let next = payloadPluginVersion?.displayString ?? (githubPluginVersion?.displayString ?? "Unknown")

		let alert = NSAlert()
		alert.messageText = "Replace existing plug‑in?"
		alert.informativeText = "An existing Glyphs MCP plug‑in is installed (\(prev)).\n\nThe installer will install \(next).\n\nYou can keep the current version if you prefer."
		alert.addButton(withTitle: "Replace")
		alert.addButton(withTitle: "Keep current")
		let resp = alert.runModal()
		return resp == .alertFirstButtonReturn
	}

	private func beginHeartbeat() {
		stopHeartbeat()
		heartbeatTask = Task { [weak self] in
			guard let self else { return }
			while !Task.isCancelled {
				try? await Task.sleep(nanoseconds: 20_000_000_000)
				guard self.isBusy else { break }
				if Date().timeIntervalSince(self.lastLogAt) >= 20 {
					self.appendLog("Still working…")
				}
			}
		}
	}

	private func stopHeartbeat() {
		heartbeatTask?.cancel()
		heartbeatTask = nil
	}

	func refreshLocalPluginVersions() {
		let installedBundle = InstallerPaths.glyphsPluginsDir.appendingPathComponent("Glyphs MCP.glyphsPlugin", isDirectory: true)
		installedPluginVersion = PluginVersionReader.readPluginVersion(pluginBundle: installedBundle)

		if let payload = try? InstallerPayload.resolve() {
			payloadPluginVersion = PluginVersionReader.readPluginVersion(pluginBundle: payload.pluginBundle)
		} else {
			payloadPluginVersion = nil
		}
	}

	func refreshGitHubPluginVersionIfNeeded(force: Bool = false) async {
		if case .checking = githubStatus { return }
		if !force, githubPluginVersion != nil { return }
		githubStatus = .checking

		do {
			let res = try await GitHubPluginVersionFetcher.fetchLatestVersion()
			githubPluginVersion = res.version
			if let installedPluginVersion, res.version > installedPluginVersion {
				githubStatus = .updateAvailable(installed: installedPluginVersion, latest: res.version)
			} else {
				githubStatus = .upToDate(latest: res.version)
			}
		} catch {
			githubStatus = .error(message: error.localizedDescription)
		}
	}

	nonisolated private static func runInstallDetached(
		options: InstallOptions,
		runner: ProcessRunner,
		log: @escaping @Sendable (String) -> Void,
		mark: @escaping @Sendable (InstallStep.ID, InstallStep.State) -> Void,
		finish: @escaping @Sendable (Bool, Bool) -> Void
	) async {
		func step(_ title: String, id: InstallStep.ID, op: () async throws -> Void) async throws {
			mark(id, .running)
			log("-- \(title) --")
			try await op()
			mark(id, .success)
		}

		do {
			if Task.isCancelled { throw CancellationError() }
			var didRecommendRestart = false

			try await step("Resolve payload", id: .payload) {
				let payload = try InstallerPayload.resolve()
				log("Payload OK: \(payload.payloadDir.path)")
			}

			var pluginBundleOverride: URL? = nil
			if options.useGitHubPluginForInstall {
				try await step("Download plug‑in update", id: .download) {
					pluginBundleOverride = try await GitHubPluginDownloader(runner: runner, log: log).downloadAndExtractPluginBundle()
				}
			}

			if options.doInstallDependencies, let python = options.pythonForDeps {
				try await step("Install dependencies", id: .deps) {
					let payload = try InstallerPayload.resolve()
					try await DepsInstaller(runner: runner, log: log).installAndVerify(python: python, requirementsTxt: payload.requirementsTxt)
				}
			}

			if options.doInstallPluginBundle {
				try await step("Install plugin bundle", id: .plugin) {
					let payload = try InstallerPayload.resolve()
					let src = pluginBundleOverride ?? payload.pluginBundle
					let outcome = try PluginInstaller(log: log).installPluginBundle(from: src, toPluginsDir: InstallerPaths.glyphsPluginsDir, allowReplace: options.allowReplacePlugin)
					if outcome.didWrite, options.glyphsRunning {
						didRecommendRestart = true
						log("Restart recommended: Glyphs is running and the plug‑in was updated.")
					}
				}
			}

			mark(.done, .done)
			log("Install complete. Next: open Glyphs and run Edit → Start MCP Server.")
			finish(true, didRecommendRestart)
		} catch is CancellationError {
			mark(.done, .failure)
			log("Cancelled.")
			finish(false, false)
		} catch {
			mark(.done, .failure)
			log("ERROR: \(error.localizedDescription)")
			finish(false, false)
		}
	}

	nonisolated private static func runClientsDetached(
		options: ClientsOptions,
		runner: ProcessRunner,
		log: @escaping @Sendable (String) -> Void,
		finish: @escaping @Sendable () -> Void
	) async {
		do {
			if options.configureCodex {
				try await CodexConfigurator(runner: runner, log: log).configure()
			}
			if options.configureClaudeDesktop {
				try ClaudeDesktopConfigurator(log: log).configure()
			}
			if options.configureClaudeCode {
				try await ClaudeCodeConfigurator(runner: runner, log: log).configureIfAvailable()
			}
			if options.configureAntigravity {
				try AntigravityConfigurator(log: log).configure()
			}
			log("Client configuration complete.")
		} catch {
			log("ERROR: \(error.localizedDescription)")
		}

		finish()
	}
}

extension InstallerViewModel: @unchecked Sendable {}

private struct InstallOptions: Sendable {
	let useGitHubPluginForInstall: Bool
	let doInstallDependencies: Bool
	let doInstallPluginBundle: Bool
	let pythonForDeps: PythonSelection?
	let glyphsRunning: Bool
	let allowReplacePlugin: Bool
}

private struct ClientsOptions: Sendable {
	let configureCodex: Bool
	let configureClaudeDesktop: Bool
	let configureClaudeCode: Bool
	let configureAntigravity: Bool
}

struct InstallStep: Identifiable {
	enum ID: String {
		case payload
		case download
		case deps
		case plugin
		case done
	}
	enum State {
		case pending
		case running
		case success
		case failure
		case done

		var symbolName: String {
			switch self {
			case .pending: return "circle"
			case .running: return "arrow.triangle.2.circlepath"
			case .success: return "checkmark.circle.fill"
			case .failure: return "xmark.octagon.fill"
			case .done: return "flag.checkered"
			}
		}

		var color: Color {
			switch self {
			case .pending: return .secondary
			case .running: return .blue
			case .success: return .green
			case .failure: return .red
			case .done: return .green
			}
		}
	}

	let id: ID
	let title: String
	var state: State

	static var defaultSteps: [InstallStep] {
		makeSteps(includeDownload: false, includeDeps: true, includePlugin: true)
	}

	static func makeSteps(includeDownload: Bool, includeDeps: Bool, includePlugin: Bool) -> [InstallStep] {
		var steps: [InstallStep] = []
		steps.append(.init(id: .payload, title: "Resolve payload", state: .pending))
		if includeDownload {
			steps.append(.init(id: .download, title: "Download update", state: .pending))
		}
		if includeDeps {
			steps.append(.init(id: .deps, title: "Install dependencies", state: .pending))
		}
		if includePlugin {
			steps.append(.init(id: .plugin, title: "Install plugin bundle", state: .pending))
		}
		steps.append(.init(id: .done, title: "Done", state: .pending))
		return steps
	}

	static func mark(_ steps: inout [InstallStep], _ state: State, for id: ID) {
		guard let idx = steps.firstIndex(where: { $0.id == id }) else { return }
		steps[idx].state = state
	}

	static func reset(_ steps: inout [InstallStep]) {
		steps = defaultSteps
	}
}
