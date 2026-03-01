import AppKit
import SwiftUI
import GlyphsMCPInstallerCore

struct ContentView: View {
	@EnvironmentObject private var model: InstallerViewModel
	@State private var showHelp: Bool = false

	var body: some View {
		NavigationStack(path: $model.navPath) {
				WelcomeView()
				.navigationDestination(for: InstallerRoute.self) { route in
					switch route {
					case .preflight: PreflightView()
					case .check: CheckView()
					case .pythonTarget: PythonTargetView()
					case .install: InstallView()
					case .clients: ClientsView()
					case .finish: FinishView()
					}
				}
		}
		.toolbar {
			ToolbarItem(placement: .primaryAction) {
				Button {
					showHelp = true
				} label: {
					Image(systemName: "questionmark.circle")
				}
				.help("Help")
			}
		}
		.sheet(isPresented: $showHelp) {
			HelpSheetView()
		}
		.frame(minWidth: 860, minHeight: 640)
		.background(VisualEffectBackground().ignoresSafeArea())
		.groupBoxStyle(GlassGroupBoxStyle())
		.background(
			WindowConfigurator { window in
				window.titleVisibility = .hidden
				window.titlebarAppearsTransparent = true
				window.isMovableByWindowBackground = true
				window.title = ""
			}
		)
	}
}

private struct HelpSheetView: View {
	@Environment(\.dismiss) private var dismiss

	var body: some View {
		VStack(spacing: 0) {
			ScrollView {
				VStack(alignment: .leading, spacing: 14) {
					Text("Help")
						.font(.title2.bold())
					Text("A quick guide to get you set up. If anything feels unclear, you can always run “Check status…” first — it makes no changes.")
						.foregroundStyle(.secondary)

					GroupBox("Python (custom setup)") {
						VStack(alignment: .leading, spacing: 8) {
							Text(.init("For the smoothest custom setup, install Python **3.12** from python.org."))
							Text(.init("Then, in **Glyphs → Settings → Addons → Python version**, select the same **3.12** version and restart Glyphs."))
								.foregroundStyle(.secondary)
							Link("Download Python for macOS (python.org)", destination: URL(string: "https://www.python.org/downloads/macos/")!)
						}
						.frame(maxWidth: .infinity, alignment: .leading)
					}

					GroupBox("Guides & links") {
						VStack(alignment: .leading, spacing: 8) {
							Link("Manual: ap.cx/gmcp", destination: URL(string: "https://www.ap.cx/gmcp")!)
							Link("GitHub repository", destination: URL(string: "https://github.com/thierryc/Glyphs-mcp")!)
							Link("Report an issue", destination: URL(string: "https://github.com/thierryc/Glyphs-mcp/issues")!)
						}
						.frame(maxWidth: .infinity, alignment: .leading)
					}

					GroupBox("After install") {
						VStack(alignment: .leading, spacing: 8) {
							Text("1) Restart Glyphs if you updated the plug‑in.")
							Text(.init("2) In Glyphs: **Edit → Start MCP Server**"))
							(
								Text("3) In your agent (Codex / Claude), select the MCP server named ")
								+ Text("glyphs-mcp-server").font(.system(.body, design: .monospaced))
								+ Text(".")
							)
							.foregroundStyle(.secondary)
						}
						.frame(maxWidth: .infinity, alignment: .leading)
					}
				}
				.padding(20)
			}

			Divider()

			HStack {
				Spacer()
				Button("Close") { dismiss() }
					.keyboardShortcut(.cancelAction)
			}
			.padding(20)
		}
		.frame(width: 520, height: 520)
	}
}

private struct WelcomeView: View {
	@EnvironmentObject private var model: InstallerViewModel
	@State private var didCopy: Bool = false

	var body: some View {
		VStack(alignment: .leading, spacing: 12) {
			Text("Glyphs MCP Installer")
				.font(.largeTitle.bold())
			Text("A guided setup to install the Glyphs MCP plug‑in, Python dependencies, and optional MCP client configuration. You can review choices before anything changes.")
				.foregroundStyle(.secondary)

			GroupBox("Status") {
				VStack(alignment: .leading, spacing: 10) {
					HStack {
						Label("Plug‑in installed", systemImage: "puzzlepiece.extension")
						Spacer()
						Text(model.installedPluginVersion?.displayString ?? "Not installed")
							.foregroundStyle(.secondary)
							.textSelection(.enabled)
					}
					HStack {
						Label("This installer", systemImage: "shippingbox")
						Spacer()
						Text(model.payloadPluginVersion?.displayString ?? "Unknown")
							.foregroundStyle(.secondary)
							.textSelection(.enabled)
					}
					HStack {
						Label("GitHub", systemImage: "arrow.down.circle")
						Spacer()
						Text(githubLine)
							.foregroundStyle(.secondary)
							.textSelection(.enabled)
					}

					if isUpdateAvailable {
						HStack(spacing: 10) {
							Label("Update available", systemImage: "sparkles")
								.foregroundStyle(.blue)
							Spacer()
							Button("Download & update…") {
								model.doInstallDependencies = false
								model.doInstallPluginBundle = true
								model.useGitHubPluginForInstall = true
								model.go(.preflight)
							}
							.buttonStyle(.borderedProminent)
						}
					} else if isInstallerOutdated {
						Label("A newer plug‑in exists on GitHub than in this installer.", systemImage: "info.circle")
							.foregroundStyle(.secondary)
					}

					HStack(spacing: 10) {
						Button("Refresh") {
							Task { @MainActor in
								await model.refreshGitHubPluginVersionIfNeeded(force: true)
							}
						}
						if didCopy {
							Text("Copied")
								.foregroundStyle(.secondary)
						}
						Spacer()
						Button("Copy endpoint") {
							Pasteboard.copy(InstallerConstants.endpointURL.absoluteString)
							didCopy = true
							DispatchQueue.main.asyncAfter(deadline: .now() + 2) { didCopy = false }
						}
					}
				}
				.frame(maxWidth: .infinity, alignment: .leading)
			}

			GroupBox("Before you start") {
				VStack(alignment: .leading, spacing: 8) {
					Label("If Glyphs is open, you may need to restart it after installing.", systemImage: "arrow.clockwise")
					Label("Installing Python dependencies requires internet access.", systemImage: "network")
					Label("Client configuration edits create backups.", systemImage: "doc.on.doc")
				}
				.frame(maxWidth: .infinity, alignment: .leading)
			}

			GroupBox("What will be done") {
				VStack(alignment: .leading, spacing: 6) {
					Label("Install plug‑in into Glyphs Plugins folder", systemImage: "puzzlepiece.extension")
					Label("Install Python dependencies via pip (network required)", systemImage: "shippingbox")
					Label("Configure MCP clients (optional)", systemImage: "gear")
					Label("Create a starter project folder with AGENTS.md (optional)", systemImage: "folder")
				}
				.frame(maxWidth: .infinity, alignment: .leading)
			}

			Spacer()

			HStack {
				Button("Create project folder…") {
					model.isGuidedSetupFlow = false
					model.go(.finish)
				}
				Button("Check status…") {
					model.isGuidedSetupFlow = false
					model.go(.check)
				}
				Spacer()
				Button("Guided setup…") {
					model.isGuidedSetupFlow = true
					model.doInstallDependencies = true
					model.doInstallPluginBundle = true
					model.useGitHubPluginForInstall = false
					model.go(.preflight)
				}
				.keyboardShortcut(.defaultAction)
			}
		}
			.padding(20)
			.onAppear {
				model.refreshLocalPluginVersions()
				Task { @MainActor in
					await model.refreshGitHubPluginVersionIfNeeded(force: false)
				}
			}
		}

	private var githubLine: String {
		switch model.githubStatus {
		case .idle: return "Not checked"
		case .checking: return "Checking…"
		case .upToDate(let latest): return latest.displayString
		case .updateAvailable(_, let latest): return "\(latest.displayString) (update available)"
		case .error(let message): return "Error: \(message)"
		}
	}

	private var isUpdateAvailable: Bool {
		guard let latest = model.githubPluginVersion else { return false }
		if let installed = model.installedPluginVersion {
			return latest > installed
		}
		return true
	}

	private var isInstallerOutdated: Bool {
		guard let latest = model.githubPluginVersion, let payload = model.payloadPluginVersion else { return false }
		return latest > payload
	}
}

private enum SetupStep: Int, CaseIterable, Identifiable {
	case preflight
	case python
	case install
	case clients
	case finish

	var id: Int { rawValue }

	var title: String {
		switch self {
		case .preflight: return "Preflight"
		case .python: return "Python"
		case .install: return "Install"
		case .clients: return "Clients"
		case .finish: return "Finish"
		}
	}
}

private struct SetupProgressHeader: View {
	let current: SetupStep

	var body: some View {
		HStack(spacing: 14) {
			ForEach(SetupStep.allCases) { step in
				HStack(spacing: 8) {
					ZStack {
						Circle()
							.fill(color(for: step))
							.frame(width: 22, height: 22)
						Text("\(step.rawValue + 1)")
							.font(.caption.bold())
							.foregroundStyle(.white)
					}
					Text(step.title)
						.font(.callout)
						.foregroundStyle(foreground(for: step))
				}
				if step != SetupStep.allCases.last {
					Rectangle()
						.fill(.quaternary)
						.frame(width: 28, height: 1)
				}
			}
			Spacer()
		}
		.padding(.horizontal, 20)
		.padding(.vertical, 8)
	}

	private func color(for step: SetupStep) -> Color {
		if step.rawValue < current.rawValue { return .green }
		if step == current { return .blue }
		return .gray.opacity(0.5)
	}

	private func foreground(for step: SetupStep) -> Color {
		if step.rawValue <= current.rawValue { return .primary }
		return .secondary
	}
}

private struct CheckView: View {
	@EnvironmentObject private var model: InstallerViewModel

	var body: some View {
		VStack(alignment: .leading, spacing: 12) {
			ScrollView {
				VStack(alignment: .leading, spacing: 12) {
					Text("Check (no changes)")
						.font(.title.bold())
					Text("A quick health check. Nothing will be installed or modified.")
						.foregroundStyle(.secondary)

					GroupBox {
						VStack(alignment: .leading, spacing: 10) {
							Label(summaryTitle, systemImage: summarySymbol)
								.foregroundStyle(summaryColor)
							Text(summaryDetails)
								.foregroundStyle(.secondary)

							if let github = model.githubPluginVersion {
								HStack {
									Label("Plug‑in update", systemImage: "arrow.down.circle")
									Spacer()
									Text(github.displayString)
										.foregroundStyle(.secondary)
								}
									HStack {
										Text("Installed: \(model.installedPluginVersion?.displayString ?? "Not installed")")
											.foregroundStyle(.secondary)
										Spacer()
										Button("Refresh") {
											Task { @MainActor in
												await model.refreshGitHubPluginVersionIfNeeded(force: true)
											}
										}
									}
								} else {
									HStack {
										Label("Plug‑in update", systemImage: "arrow.down.circle")
									Spacer()
									Text("Checking…")
										.foregroundStyle(.secondary)
								}
							}

							HStack {
								Button("Open plug‑ins folder") { model.revealInFinder(url: model.glyphsPluginsDir) }
								Button("Open Codex config") { model.revealInFinder(url: InstallerPaths.codexConfig) }
								Button("Open Claude Desktop config") { model.revealInFinder(url: InstallerPaths.claudeDesktopConfig) }
								Spacer()
							}
						}
						.frame(maxWidth: .infinity, alignment: .leading)
					}

					GroupedCheckItemsView(items: model.check.items)
				}
				.padding(20)
			}
			.frame(maxWidth: .infinity, maxHeight: .infinity)

			Divider()

			HStack {
				Button("Re-scan") { model.scanCheck() }
				Spacer()
				Button("Back") { model.back() }
				Button("Continue to setup…") {
					model.isGuidedSetupFlow = true
					model.go(.preflight)
				}
					.keyboardShortcut(.defaultAction)
			}
			.padding(20)
		}
		.onAppear { model.scanCheck() }
	}

	private var hasBad: Bool { model.check.items.contains(where: { $0.level == .bad }) }
	private var hasWarn: Bool { model.check.items.contains(where: { $0.level == .warn }) }

	private var summaryTitle: String {
		if hasBad { return "Needs attention" }
		if hasWarn { return "Mostly OK" }
		return "Everything looks good"
	}

	private var summaryDetails: String {
		if hasBad { return "Some required components are missing or misconfigured. Review the sections below." }
		if hasWarn { return "A few items may need attention. You can still continue to guided setup." }
		return "Your environment looks ready."
	}

	private var summarySymbol: String { hasBad ? "xmark.octagon.fill" : (hasWarn ? "exclamationmark.triangle.fill" : "checkmark.circle.fill") }
	private var summaryColor: Color { hasBad ? .red : (hasWarn ? .orange : .green) }
}

private struct PreflightView: View {
	@EnvironmentObject private var model: InstallerViewModel

	var body: some View {
		VStack(alignment: .leading, spacing: 12) {
			SetupProgressHeader(current: .preflight)

			ScrollView {
				VStack(alignment: .leading, spacing: 12) {
					Text("Preflight")
						.font(.title.bold())

					GroupBox {
						VStack(alignment: .leading, spacing: 10) {
							Label("Recommended", systemImage: "wand.and.stars")
								.foregroundStyle(.blue)
							Text("Install the plug‑in and dependencies, then (optionally) configure MCP clients. You can change these choices in the next step.")
								.foregroundStyle(.secondary)

							if model.githubPluginVersion != nil {
								Toggle("Download latest plug‑in from GitHub (optional)", isOn: $model.useGitHubPluginForInstall)
								Text("If enabled, the installer will download the latest plug‑in from GitHub over HTTPS before installing.")
									.foregroundStyle(.secondary)
									.font(.callout)
							} else {
								Text("GitHub version not checked yet. Continue without downloading, or refresh on the Home screen.")
									.foregroundStyle(.secondary)
									.font(.callout)
							}
						}
						.frame(maxWidth: .infinity, alignment: .leading)
					}

					GroupedPreflightItemsView(items: model.preflight.items, updateLine: updateLine)
				}
				.padding(20)
			}
			.frame(maxWidth: .infinity, maxHeight: .infinity)

			Divider()

			HStack {
				Button("Re-scan") { model.scanPreflight() }
				Spacer()
				Button("Back") { model.back() }
				Button("Continue") { model.go(.pythonTarget) }
					.keyboardShortcut(.defaultAction)
			}
			.padding(20)
		}
		.onAppear { model.scanPreflight() }
	}

	private var updateLine: String? {
		guard let github = model.githubPluginVersion else { return nil }
		if let payload = model.payloadPluginVersion, github > payload {
			return "A newer plug‑in exists on GitHub than inside this installer. You can enable “Download latest plug‑in from GitHub” above, or download the latest installer."
		}
		return nil
	}
}

private struct GroupedPreflightItemsView: View {
	let items: [PreflightItem]
	let updateLine: String?

	var body: some View {
		VStack(spacing: 12) {
			if let updateLine {
				GroupBox("Update") {
					Label(updateLine, systemImage: "info.circle")
						.foregroundStyle(.secondary)
				}
			}

			GroupBox("Glyphs + plug‑in") {
				ItemList(items: items.filter { isGlyphsSection($0) })
			}
			GroupBox("Python") {
				ItemList(items: items.filter { isPythonSection($0) })
			}
			GroupBox("Tools") {
				ItemList(items: items.filter { isToolsSection($0) })
			}
		}
	}

	private func isGlyphsSection(_ item: PreflightItem) -> Bool {
		item.title.lowercased().contains("glyphs") || item.title.lowercased().contains("plugin")
	}
	private func isPythonSection(_ item: PreflightItem) -> Bool {
		item.title.lowercased().contains("python")
	}
	private func isToolsSection(_ item: PreflightItem) -> Bool {
		!(isGlyphsSection(item) || isPythonSection(item))
	}
}

private struct GroupedCheckItemsView: View {
	let items: [PreflightItem]

	var body: some View {
		VStack(spacing: 12) {
			GroupBox("Glyphs + plug‑in") { ItemList(items: items.filter { isGlyphsSection($0) }) }
			GroupBox("Tools") { ItemList(items: items.filter { isToolsSection($0) }) }
			GroupBox("MCP Clients") { ItemList(items: items.filter { isMcpSection($0) }) }
		}
	}

	private func isGlyphsSection(_ item: PreflightItem) -> Bool {
		let t = item.title.lowercased()
		return t.contains("glyphs") || t.contains("plug‑in") || t.contains("plugin")
	}
	private func isMcpSection(_ item: PreflightItem) -> Bool {
		item.title.lowercased().contains("mcp")
	}
	private func isToolsSection(_ item: PreflightItem) -> Bool {
		!(isGlyphsSection(item) || isMcpSection(item))
	}
}

private struct ItemList: View {
	let items: [PreflightItem]

	var body: some View {
		VStack(alignment: .leading, spacing: 10) {
			if items.isEmpty {
				Text("No items.")
					.foregroundStyle(.secondary)
			} else {
				ForEach(items) { item in
					HStack(alignment: .top, spacing: 8) {
						Image(systemName: item.level.symbolName)
							.foregroundStyle(item.level.color)
							.frame(width: 18)
						VStack(alignment: .leading, spacing: 2) {
							Text(item.title).bold()
							Text(item.details)
								.foregroundStyle(.secondary)
								.fixedSize(horizontal: false, vertical: true)
								.contextMenu {
									Button("Copy") { Pasteboard.copy(item.details) }
								}
						}
					}
				}
			}
		}
		.frame(maxWidth: .infinity, alignment: .leading)
	}
}

private enum Pasteboard {
	static func copy(_ text: String) {
		let pb = NSPasteboard.general
		pb.clearContents()
		pb.setString(text, forType: .string)
	}
}

private struct InstallerLogGroupBox: View {
	let logText: String
	let isBusy: Bool

	@State private var copiedLogs: Bool = false
	@State private var showLogDetails: Bool = false
	private let bottomID = "log-bottom"

	var body: some View {
		GroupBox("Log") {
			VStack(alignment: .leading, spacing: 10) {
				HStack(spacing: 10) {
					Button("Copy logs") {
						Pasteboard.copy(logText)
						copiedLogs = true
						DispatchQueue.main.asyncAfter(deadline: .now() + 2) { copiedLogs = false }
					}
					.disabled(logText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
					if copiedLogs {
						Text("Copied")
							.foregroundStyle(.secondary)
					}
					Spacer()
				}

				DisclosureGroup(isExpanded: $showLogDetails) {
					ScrollViewReader { proxy in
						ScrollView {
							VStack(alignment: .leading, spacing: 10) {
								if isBusy {
									HStack(spacing: 8) {
										ProgressView()
											.controlSize(.small)
										Text("Running…")
											.foregroundStyle(.secondary)
									}
								}

								if logText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
									Text("Logs will appear here.")
										.foregroundStyle(.secondary)
										.font(.callout)
								} else {
									Text(logText)
										.font(.system(.body, design: .monospaced))
										.frame(maxWidth: .infinity, alignment: .leading)
										.textSelection(.enabled)
								}

								Color.clear
									.frame(height: 1)
									.id(bottomID)
							}
							.frame(maxWidth: .infinity, alignment: .leading)
						}
						.frame(minHeight: 220, maxHeight: 320)
						.onChange(of: logText) { _ in
							guard showLogDetails else { return }
							DispatchQueue.main.async {
								withAnimation(.easeOut(duration: 0.2)) {
									proxy.scrollTo(bottomID, anchor: .bottom)
								}
							}
						}
					}
				} label: {
					Text(showLogDetails ? "Hide details" : "Show details")
						.foregroundStyle(.secondary)
				}
			}
		}
	}
}

	private struct PythonTargetView: View {
		@EnvironmentObject private var model: InstallerViewModel

		var body: some View {
			VStack(alignment: .leading, spacing: 12) {
				SetupProgressHeader(current: .python)
				ScrollView {
					VStack(alignment: .leading, spacing: 12) {
						Text("Python Target")
							.font(.title.bold())
						Text("Use the same Python version shown in Glyphs → Settings → Addons → Python version. Changing it in Glyphs requires restarting Glyphs.")
							.foregroundStyle(.secondary)

						GroupBox {
							VStack(alignment: .leading, spacing: 10) {
								Toggle("Install Python dependencies (pip)", isOn: $model.doInstallDependencies)
								Toggle("Install / update plug‑in bundle", isOn: $model.doInstallPluginBundle)

								if model.doInstallDependencies {
									if let selected = model.preflight.glyphsSelectedPythonVersion ?? model.preflight.glyphsSelectedPythonFrameworkPath {
										Label("Glyphs is currently set to: \(selected)", systemImage: "info.circle")
											.foregroundStyle(.secondary)
											.textSelection(.enabled)
									} else {
										Label("Glyphs Python setting could not be detected (pick the version shown in Glyphs).", systemImage: "exclamationmark.triangle")
											.foregroundStyle(.secondary)
									}

									if model.pythonMode == .custom,
									   let glyphsFramework = model.preflight.glyphsSelectedPythonFrameworkPath,
									   let picked = model.selectedCustomPythonPath,
									   !picked.hasPrefix(glyphsFramework) {
										Label("This interpreter does not match Glyphs’ current Python setting. Your install may not work until you switch Glyphs’ Python version and restart Glyphs.", systemImage: "exclamationmark.triangle.fill")
											.foregroundStyle(.orange)
											.textSelection(.enabled)
									}

									Picker("Mode", selection: $model.pythonMode) {
										Text("Glyphs’ Python (Plugin Manager)").tag(PythonMode.glyphs)
										Text("Custom Python").tag(PythonMode.custom)
									}
									.pickerStyle(.radioGroup)

									if model.pythonMode == .custom {
										HStack {
											Picker("Interpreter", selection: $model.selectedCustomPythonPath) {
												ForEach(model.preflight.customPythons, id: \.path) { cand in
													Text("\(cand.path) (\(cand.version) – \(cand.source))").tag(Optional(cand.path))
												}
											}
											.frame(maxWidth: 520)

											Button("Choose…") { model.chooseCustomPythonViaPicker() }
										}

										if let p = model.selectedCustomPythonPath {
											Text("Selected: \(p)")
												.foregroundStyle(.secondary)
												.textSelection(.enabled)
										}
									} else {
										Text("Glyphs pip: \(model.preflight.glyphsPipPath ?? "not found")")
											.foregroundStyle(.secondary)
											.textSelection(.enabled)
									}
								} else {
									Text("Dependencies will be skipped. You can still update the plug‑in bundle.")
										.foregroundStyle(.secondary)
								}
							}
							.frame(maxWidth: .infinity, alignment: .leading)
						}
					}
					.padding(20)
				}
				.frame(maxWidth: .infinity, maxHeight: .infinity)

				Divider()

				HStack {
					Spacer()
					Button("Back") { model.back() }
					Button("Install") {
						model.go(.install)
						DispatchQueue.main.async {
							model.startInstall()
						}
					}
						.keyboardShortcut(.defaultAction)
				}
				.padding(20)
			}
		}
	}

	private struct InstallView: View {
		@EnvironmentObject private var model: InstallerViewModel

		var body: some View {
			let actionableSteps = model.installSteps.filter { $0.id != .done }
			let completed = actionableSteps.filter { $0.state == .success }.count
			let total = max(actionableSteps.count, 1)
			let progress = Double(completed) / Double(total)
			let currentStep = model.installSteps.first(where: { $0.state == .running })?.title

			VStack(alignment: .leading, spacing: 12) {
				SetupProgressHeader(current: .install)
				ScrollView {
					VStack(alignment: .leading, spacing: 12) {
						Text("Install")
							.font(.title.bold())
					Text("You can leave this window open while it runs. If something fails, you can copy the logs and try again.")
						.foregroundStyle(.secondary)

					if model.doInstallPluginBundle && GlyphsRuntime.isGlyphsRunning() {
						GroupBox {
							HStack(alignment: .top, spacing: 10) {
								Image(systemName: "exclamationmark.triangle.fill")
									.foregroundStyle(.orange)
								VStack(alignment: .leading, spacing: 6) {
									Text("Glyphs appears to be running.")
										.bold()
									Text("Installing or updating the plug‑in may require restarting Glyphs to take effect.")
										.foregroundStyle(.secondary)
									HStack {
										Button("Quit Glyphs…") { GlyphsRuntime.quitGlyphsWithConfirmation() }
										Spacer()
									}
								}
							}
						}
					}

					GroupBox("Progress") {
						VStack(alignment: .leading, spacing: 6) {
							if let currentStep {
								Text("Current: \(currentStep)")
									.foregroundStyle(.secondary)
									.font(.callout)
							} else if model.installSucceeded {
								Text("Completed")
									.foregroundStyle(.secondary)
									.font(.callout)
							} else if model.isBusy {
								Text("Starting…")
									.foregroundStyle(.secondary)
									.font(.callout)
							}

							HStack {
								ProgressView(value: progress)
									.progressViewStyle(.linear)
									.frame(maxWidth: .infinity)
									.padding(.leading, 2)
								Text("\(completed)/\(total)")
									.foregroundStyle(.secondary)
									.font(.callout)
							}
							.padding(.bottom, 6)

							ForEach(model.installSteps) { step in
								HStack {
									Image(systemName: step.state.symbolName)
										.foregroundStyle(step.state.color)
										.frame(width: 18)
									Text(step.title)
									Spacer()
								}
							}
						}
						.frame(maxWidth: .infinity, alignment: .leading)
					}

						InstallerLogGroupBox(logText: model.logText, isBusy: model.isBusy)
					}
					.padding(20)
				}
				.frame(maxWidth: .infinity, maxHeight: .infinity)

			Divider()

				HStack {
					Button("Start setup") {
						model.startInstall()
					}
						.disabled(model.isBusy)
						.buttonStyle(.bordered)
					if model.isBusy {
						Button("Cancel") { model.cancelInstall() }
							.keyboardShortcut(.cancelAction)
					}
					Spacer()
				Button("Back") { model.back() }
					.disabled(model.isBusy)
				Button("Continue") { model.go(.clients) }
					.disabled(!model.installSucceeded)
					.keyboardShortcut(.defaultAction)
			}
			.padding(20)
		}
		.onAppear {
			guard !model.didRunInstall else { return }
			DispatchQueue.main.async {
				model.startInstall()
			}
		}
	}
}

	private struct ClientsView: View {
		@EnvironmentObject private var model: InstallerViewModel
		@State private var copiedClaudeCommand: Bool = false

		var body: some View {
			VStack(alignment: .leading, spacing: 12) {
				SetupProgressHeader(current: .clients)
				ScrollView {
					VStack(alignment: .leading, spacing: 12) {
						Text("Configure clients")
							.font(.title.bold())
					Text("Optional. This edits local config files (with backups) or uses CLIs when available.")
						.foregroundStyle(.secondary)

					GroupBox {
						VStack(alignment: .leading, spacing: 10) {
							ClientRow(
								name: "Codex",
								status: clientStatus(title: "Codex MCP settings"),
								details: "Will update: \(InstallerPaths.codexConfig.path)",
								isOn: $model.configureCodex,
								disabled: false
							)
							ClientRow(
								name: "Claude Desktop",
								status: clientStatus(title: "Claude Desktop MCP settings"),
								details: "Will update: \(InstallerPaths.claudeDesktopConfig.path)",
								isOn: $model.configureClaudeDesktop,
								disabled: false
							)
							ClientRow(
								name: "Claude Code",
								status: clientStatus(title: "Claude Code MCP settings"),
								details: "Uses the `claude` CLI when available.",
								isOn: $model.configureClaudeCode,
								disabled: model.preflight.claudePath == nil
							)
							ClientRow(
								name: "Antigravity",
								status: clientStatus(title: "Antigravity MCP settings"),
								details: "Will update: \(InstallerPaths.antigravityConfig.path)",
								isOn: $model.configureAntigravity,
								disabled: false
							)

							if let cmd = suggestedClaudeAddCommand {
								HStack {
									Text("Claude Code is not configured. You can also run:")
										.foregroundStyle(.secondary)
									Spacer()
								}
								Text(cmd)
									.font(.system(.callout, design: .monospaced))
									.textSelection(.enabled)
								HStack {
									Button("Copy command") {
										Pasteboard.copy(cmd)
										copiedClaudeCommand = true
										DispatchQueue.main.asyncAfter(deadline: .now() + 2) { copiedClaudeCommand = false }
									}
									if copiedClaudeCommand {
										Text("Copied")
											.foregroundStyle(.secondary)
									}
									Spacer()
								}
							}
						}
						.frame(maxWidth: .infinity, alignment: .leading)
					}

						InstallerLogGroupBox(logText: model.logText, isBusy: model.isBusy)
					}
					.padding(20)
				}
				.frame(maxWidth: .infinity, maxHeight: .infinity)

			Divider()

				HStack {
					Button("Configure") {
						model.startClientConfig()
					}
						.disabled(model.isBusy)
					if model.isBusy {
						Button("Cancel") { model.cancelClientConfig() }
							.keyboardShortcut(.cancelAction)
					}
					Spacer()
					Button("Back") { model.back() }
					.disabled(model.isBusy)
				Button("Continue") { model.go(.finish) }
					.keyboardShortcut(.defaultAction)
			}
			.padding(20)
		}
		.onAppear { model.scanCheck() }
	}

	private func clientStatus(title: String) -> String {
		model.check.items.first(where: { $0.title == title })?.details ?? "Not checked"
	}

	private var suggestedClaudeAddCommand: String? {
		guard let item = model.check.items.first(where: { $0.title == "Claude Code MCP settings" }) else { return nil }
		guard let r = item.details.range(of: "Run: ") else { return nil }
		return String(item.details[r.upperBound...]).trimmingCharacters(in: .whitespacesAndNewlines)
	}
}

	private struct FinishView: View {
		@EnvironmentObject private var model: InstallerViewModel
		@State private var copiedPrompt: Bool = false
		@State private var copiedEndpoint: Bool = false

		var body: some View {
			VStack(alignment: .leading, spacing: 12) {
				if model.isGuidedSetupFlow {
					SetupProgressHeader(current: .finish)
				}

				ScrollView {
					VStack(alignment: .leading, spacing: 12) {
						Text("You’re ready")
							.font(.title.bold())

						GroupBox("Next steps") {
							VStack(alignment: .leading, spacing: 6) {
								if model.restartRecommended {
									Text("1) Restart Glyphs to load the updated plug‑in.")
										.bold()
								} else {
									Text("1) Open (or restart) Glyphs if needed.")
										.bold()
								}
								Text("2) In Glyphs: Edit → Start MCP Server")
									.bold()
								Text("3) Try an example prompt (below)")
									.bold()

								HStack {
									Text("Endpoint: \(InstallerConstants.endpointURL.absoluteString)")
										.foregroundStyle(.secondary)
										.textSelection(.enabled)
									Spacer()
									Button("Copy endpoint") {
										Pasteboard.copy(InstallerConstants.endpointURL.absoluteString)
										copiedEndpoint = true
										DispatchQueue.main.asyncAfter(deadline: .now() + 2) { copiedEndpoint = false }
									}
									if copiedEndpoint { Text("Copied").foregroundStyle(.secondary) }
								}

								Text("If your agent can’t connect, restart Glyphs and start the MCP server first, then try again.")
									.foregroundStyle(.secondary)
							}
							.frame(maxWidth: .infinity, alignment: .leading)
						}

						GroupBox("Try it now") {
							VStack(alignment: .leading, spacing: 10) {
								Text("Example prompt: List open fonts")
									.font(.headline)
								Text("Use the Glyphs MCP server and call `list_open_fonts`. Return a table with `familyName`, `filePath`, `masterCount`, and `glyphCount` for each open font.")
									.foregroundStyle(.secondary)

								Text(examplePrompt)
									.font(.system(.callout, design: .monospaced))
									.textSelection(.enabled)

								HStack {
									Button("Copy prompt") {
										Pasteboard.copy(examplePrompt)
										copiedPrompt = true
										DispatchQueue.main.asyncAfter(deadline: .now() + 2) { copiedPrompt = false }
									}
									if copiedPrompt { Text("Copied").foregroundStyle(.secondary) }
									Spacer()
								}

								Text("Tip: In Codex / Claude, select the MCP server named `glyphs-mcp-server`.")
									.foregroundStyle(.secondary)
							}
							.frame(maxWidth: .infinity, alignment: .leading)
						}

						GroupBox("Starter project folder") {
							VStack(alignment: .leading, spacing: 10) {
								Toggle("Create a starter project folder with AGENTS.md", isOn: $model.createStarterFolder)
								TextField("Project name", text: $model.starterProjectName)
									.disabled(!model.createStarterFolder)
								Text("This becomes the folder name and is written into `AGENTS.md` so your agent knows to use the Glyphs MCP server.")
									.foregroundStyle(.secondary)
									.font(.callout)
								HStack {
									Button("Choose location…") { model.chooseStarterParentFolder() }
										.disabled(!model.createStarterFolder)
									if let folder = model.starterParentFolder {
										Text(folder.path)
											.foregroundStyle(.secondary)
											.textSelection(.enabled)
									} else {
										Text("No folder selected").foregroundStyle(.secondary)
									}
								}

								Button("Create starter project") {
									Task { await model.createStarterProject() }
								}
								.disabled(!model.createStarterFolder || model.starterParentFolder == nil || model.isBusy)

								if let created = model.createdStarterProjectFolder {
									HStack {
										Text("Created: \(created.path)")
											.foregroundStyle(.secondary)
											.textSelection(.enabled)
										Spacer()
										Button("Open in Finder") { model.revealInFinder(url: created) }
									}
								}
							}
							.frame(maxWidth: .infinity, alignment: .leading)
						}

						GroupBox("Open config files") {
							HStack {
								Button("Codex") { model.revealInFinder(url: InstallerPaths.codexConfig) }
								Button("Claude Desktop") { model.revealInFinder(url: InstallerPaths.claudeDesktopConfig) }
								Button("Antigravity") { model.revealInFinder(url: InstallerPaths.antigravityConfig) }
								Spacer()
							}
							.frame(maxWidth: .infinity, alignment: .leading)
						}

						InstallerLogGroupBox(logText: model.logText, isBusy: model.isBusy)
					}
					.padding(20)
					.frame(maxWidth: .infinity, alignment: .leading)
				}
				.frame(maxWidth: .infinity, maxHeight: .infinity)

				Divider()

				HStack {
					Button("Open Glyphs Plugins folder") { model.revealInFinder(url: model.glyphsPluginsDir) }
					Spacer()
					Button("Back") { model.back() }
					Button(model.isGuidedSetupFlow ? "Done" : "Home") { model.goHome() }
						.buttonStyle(.borderedProminent)
						.keyboardShortcut(.defaultAction)
				}
				.padding(20)
			}
		}

		private var examplePrompt: String {
			"Use the Glyphs MCP server and call `list_open_fonts`. Return a table with `familyName`, `filePath`, `masterCount`, and `glyphCount` for each open font."
		}
	}

private struct ClientRow: View {
	let name: String
	let status: String
	let details: String
	@Binding var isOn: Bool
	let disabled: Bool

	var body: some View {
		VStack(alignment: .leading, spacing: 6) {
			HStack {
				Toggle(name, isOn: $isOn)
					.disabled(disabled)
				Spacer()
			}
			Text(status)
				.foregroundStyle(.secondary)
				.font(.callout)
			Text(details)
				.foregroundStyle(.secondary)
				.font(.callout)
		}
		.padding(.vertical, 4)
	}
}
