import AppKit
import SwiftUI
import GlyphsMCPInstallerCore

struct ContentView: View {
	@EnvironmentObject private var model: InstallerViewModel

	var body: some View {
		let snapshot = model.snapshot
		let action = model.actionState

		VStack(spacing: 18) {
			InstallerTopTabBar(selection: $model.selectedTab, isAdvancedModeEnabled: model.isAdvancedModeEnabled)
				.padding(.top, 18)
				.padding(.horizontal, 24)

			Group {
				switch model.selectedTab {
				case .wizard:
					WizardTabView(
						snapshot: snapshot,
						action: action,
						configureCodex: $model.configureCodex,
						configureClaudeDesktop: $model.configureClaudeDesktop,
						configureClaudeCode: $model.configureClaudeCode,
						installCodexSkills: $model.installCodexSkills,
						installClaudeCodeSkills: $model.installClaudeCodeSkills,
						replaceDevPluginWithLatestOnlineVersion: $model.replaceDevPluginWithLatestOnlineVersion,
						onRunWizard: model.startWizard,
						onCancel: model.cancelWizard,
						onQuitGlyphs: GlyphsRuntime.quitGlyphsWithConfirmation
					)
				case .install:
					InstallTabView(
						snapshot: snapshot,
						action: action,
						replaceDevPluginWithLatestOnlineVersion: $model.replaceDevPluginWithLatestOnlineVersion,
						onInstall: model.startInstall,
						onCancel: model.cancelInstall,
						onQuitGlyphs: GlyphsRuntime.quitGlyphsWithConfirmation
					)
				case .link:
					LinkTabView(
						clients: snapshot.clients,
						detectedClientsSummary: snapshot.detectedClientsSummary,
						manualClaudeCommand: model.manualClaudeCommand,
						action: action,
						bindingForClient: model.binding(for:),
						onLink: model.startClientConfig,
						onCancel: model.cancelClientConfig
					)
				case .skill:
					SkillTabView(
						skills: snapshot.skills,
						codexSkillsEnabled: $model.installCodexSkills,
						claudeSkillsEnabled: $model.installClaudeCodeSkills,
						action: action,
						onInstallSkills: model.startSkillInstall,
						onCancel: model.cancelSkillInstall
					)
				case .status:
					StatusTabView(
						snapshot: snapshot,
						isAdvancedModeEnabled: model.isAdvancedModeEnabled,
						pluginsFolder: model.glyphsPluginsDir,
						onRefresh: model.refreshSnapshot,
						onReveal: model.revealInFinder(url:)
					)
				case .help:
					HelpTabView(
						projectName: $model.starterProjectName,
						selectedFolder: model.starterParentFolder,
						createdFolder: model.createdStarterProjectFolder,
						isBusy: action.isBusy,
						logText: action.logText,
						onChooseFolder: model.chooseStarterParentFolder,
						onCreateProject: { Task { await model.createStarterProject() } },
						onReveal: model.revealInFinder(url:)
					)
				}
			}
			.frame(maxWidth: .infinity, maxHeight: .infinity)
		}
		.frame(minWidth: 920, minHeight: 700)
		.background(VisualEffectBackground().ignoresSafeArea())
		.groupBoxStyle(GlassGroupBoxStyle())
	}
}

private struct WizardTabView: View {
	let snapshot: InstallerStatusSnapshot
	let action: InstallerActionState
	@Binding var configureCodex: Bool
	@Binding var configureClaudeDesktop: Bool
	@Binding var configureClaudeCode: Bool
	@Binding var installCodexSkills: Bool
	@Binding var installClaudeCodeSkills: Bool
	@Binding var replaceDevPluginWithLatestOnlineVersion: Bool
	let onRunWizard: () -> Void
	let onCancel: () -> Void
	let onQuitGlyphs: () -> Void

	private var selectedSummary: String {
		var items: [String] = ["plug-in", "dependencies"]
		if configureCodex { items.append("Codex") }
		if configureClaudeDesktop { items.append("Claude Desktop") }
		if configureClaudeCode { items.append("Claude Code") }
		if installCodexSkills { items.append("Codex skills") }
		if installClaudeCodeSkills { items.append("Claude Code skills") }
		return items.joined(separator: ", ")
	}

	var body: some View {
		CenteredTabScroll {
				Text("Run the local setup in one click. Details stay in Status.")
					.foregroundStyle(.secondary)
					.font(.title3)

				if snapshot.glyphsRunning {
					WarningBanner(
						title: "Glyphs is running",
						message: "Quit Glyphs before running the wizard so the plug-in can update cleanly.",
						buttonTitle: "Quit Glyphs…",
						action: onQuitGlyphs
					)
					.frame(maxWidth: 760)
				} else if let message = snapshot.installMessage {
					WarningBanner(title: "Setup blocked", message: message)
						.frame(maxWidth: 760)
				}

				if snapshot.showsDevPluginReplacementOption, let devPluginWarning = snapshot.devPluginWarning {
					GroupBox {
						VStack(alignment: .leading, spacing: 12) {
							WarningBanner(
								title: "Development plug-in detected",
								message: devPluginWarning
							)
							Toggle("Replace dev plug-in with latest online version", isOn: $replaceDevPluginWithLatestOnlineVersion)
						}
					}
					.frame(maxWidth: 760)
				}

				GroupBox("Setup") {
					VStack(alignment: .leading, spacing: 14) {
						Text("Update the plug-in and dependencies.")
						Text("Link the selected agents.")
						Text("Update skills for the selected clients.")
							.padding(.bottom, 4)

						Divider()

						Toggle("Link Codex", isOn: $configureCodex)
						Toggle("Link Claude Desktop", isOn: $configureClaudeDesktop)
						Toggle("Link Claude Code", isOn: $configureClaudeCode)
						Divider()
						Toggle("Install Codex skills", isOn: $installCodexSkills)
						Toggle("Install Claude Code skills", isOn: $installClaudeCodeSkills)

						Text("Selected: \(selectedSummary)")
							.font(.callout)
							.foregroundStyle(.secondary)
					}
					.frame(maxWidth: .infinity, alignment: .leading)
				}

				HeroActionSection(
					title: snapshot.wizardButtonTitle,
					isDisabled: !snapshot.canInstall || action.isBusy,
					action: onRunWizard,
					showsProgress: action.activeKind == .wizard
				) {
					if action.activeKind == .wizard {
						Button("Cancel", action: onCancel)
							.buttonStyle(SecondaryPillButtonStyle())
							.keyboardShortcut(.cancelAction)
					}
				}

				if action.activeKind == .wizard {
					GroupBox("Wizard progress") {
						VStack(alignment: .leading, spacing: 10) {
							ForEach(action.installSteps) { step in
								HStack(spacing: 10) {
									Image(systemName: step.state.symbolName)
										.foregroundStyle(step.state.color)
										.frame(width: 18)
									Text(step.title)
									Spacer()
								}
							}
							if action.clientReloadRecommended {
								Text("Reload Codex / Claude Code after the wizard finishes.")
									.foregroundStyle(.secondary)
									.font(.callout)
							}
						}
						.frame(maxWidth: .infinity, alignment: .leading)
					}
					.frame(maxWidth: 760)
				}
		}
	}
}

private struct InstallTabView: View {
	let snapshot: InstallerStatusSnapshot
	let action: InstallerActionState
	@Binding var replaceDevPluginWithLatestOnlineVersion: Bool
	let onInstall: () -> Void
	let onCancel: () -> Void
	let onQuitGlyphs: () -> Void

	var body: some View {
		CenteredTabScroll {
				PageIntroText("Update the Glyphs MCP plug-in and its Python dependencies.")

				if snapshot.glyphsRunning {
					WarningBanner(
						title: "Glyphs is running",
						message: "Quit Glyphs before updating the plug-in.",
						buttonTitle: "Quit Glyphs…",
						action: onQuitGlyphs
					)
				} else if let message = snapshot.installMessage {
					WarningBanner(title: "Install blocked", message: message)
				}

				if snapshot.showsDevPluginReplacementOption, let devPluginWarning = snapshot.devPluginWarning {
					GroupBox {
						VStack(alignment: .leading, spacing: 12) {
							WarningBanner(
								title: "Development plug-in",
								message: devPluginWarning
							)
							Toggle("Replace with latest online plug-in", isOn: $replaceDevPluginWithLatestOnlineVersion)
						}
					}
				}

				GroupBox("Plugin") {
					VStack(alignment: .leading, spacing: 14) {
						SimpleInfoRow(title: "Versions", value: snapshot.versionLine)
						SimpleInfoRow(title: "Glyphs Python", value: snapshot.pythonStatus.summary)
					}
					.frame(maxWidth: .infinity, alignment: .leading)
				}

				HeroActionSection(
					title: snapshot.installButtonTitle,
					isDisabled: !snapshot.canInstall || action.isBusy,
					action: onInstall,
					showsProgress: action.activeKind == .install
				) {
					if action.activeKind == .install {
						Button("Cancel", action: onCancel)
							.buttonStyle(SecondaryPillButtonStyle())
							.keyboardShortcut(.cancelAction)
					}
				}

				GroupBox("Install progress") {
					VStack(alignment: .leading, spacing: 10) {
						ForEach(action.installSteps) { step in
							HStack(spacing: 10) {
								Image(systemName: step.state.symbolName)
									.foregroundStyle(step.state.color)
									.frame(width: 18)
								Text(step.title)
								Spacer()
							}
						}
						if action.restartRecommended {
							Text("Restart Glyphs if you had it open before updating.")
								.foregroundStyle(.secondary)
								.font(.callout)
						}
					}
					.frame(maxWidth: .infinity, alignment: .leading)
				}

				InstallerLogGroupBox(logText: action.logText, isBusy: action.activeKind == .install)
		}
	}
}

private struct LinkTabView: View {
	let clients: [InstallerClientStatusSnapshot]
	let detectedClientsSummary: String
	let manualClaudeCommand: String
	let action: InstallerActionState
	let bindingForClient: (InstallerClientKind) -> Binding<Bool>
	let onLink: () -> Void
	let onCancel: () -> Void
	@State private var copiedClaudeCommand: Bool = false

	var body: some View {
		CenteredTabScroll {
				PageIntroText("Link Glyphs MCP to the coding agents on this Mac.")

				GroupBox("Agents") {
					VStack(alignment: .leading, spacing: 14) {
						Text(detectedClientsSummary)
							.foregroundStyle(.secondary)

						ForEach(clients) { row in
							ClientToggleRow(
								row: row,
								isOn: bindingForClient(row.kind),
								disabled: !row.detected
							)
						}

						if !clients.contains(where: { $0.kind == .claudeCode && $0.detected }) {
							Divider()
							Text("Manual Claude Code command")
								.font(.headline)
							Text(manualClaudeCommand)
								.font(.system(.callout, design: .monospaced))
								.textSelection(.enabled)
							HStack {
								Button("Copy command") {
									Pasteboard.copy(manualClaudeCommand)
									copiedClaudeCommand = true
									DispatchQueue.main.asyncAfter(deadline: .now() + 2) { copiedClaudeCommand = false }
								}
								.buttonStyle(SecondaryPillButtonStyle())
								if copiedClaudeCommand {
									Text("Copied")
										.foregroundStyle(.secondary)
								}
							}
						}
					}
					.frame(maxWidth: .infinity, alignment: .leading)
				}

				HeroActionSection(
					title: "Link to agents",
					isDisabled: action.isBusy,
					action: onLink,
					showsProgress: action.activeKind == .link
				) {
					if action.activeKind == .link {
						Button("Cancel", action: onCancel)
							.buttonStyle(SecondaryPillButtonStyle())
							.keyboardShortcut(.cancelAction)
					}
				}

				if action.clientReloadRecommended {
					Text("Restart the client if the new connection does not appear.")
						.foregroundStyle(.secondary)
				}

				InstallerLogGroupBox(logText: action.logText, isBusy: action.activeKind == .link)
		}
	}
}

private struct SkillTabView: View {
	let skills: [InstallerSkillTargetSnapshot]
	@Binding var codexSkillsEnabled: Bool
	@Binding var claudeSkillsEnabled: Bool
	let action: InstallerActionState
	let onInstallSkills: () -> Void
	let onCancel: () -> Void

	private var canInstall: Bool {
		(codexSkillsEnabled || claudeSkillsEnabled) && !action.isBusy
	}

	private var selectedTargetsHaveExistingSkills: Bool {
		selectedSkillTargets.contains(where: \.hasInstalledSkills)
	}

	private var selectedSkillTargets: [InstallerSkillTargetSnapshot] {
		skills.filter { target in
			switch target.kind {
			case .codex: return codexSkillsEnabled
			case .claudeCode: return claudeSkillsEnabled
			}
		}
	}

	var body: some View {
		CenteredTabScroll {
				PageIntroText("Install Glyphs MCP skills for the selected clients.")

				GroupBox("Skills") {
					VStack(alignment: .leading, spacing: 12) {
						Toggle("Codex", isOn: $codexSkillsEnabled)
						Text(skillStatus(for: .codex))
							.font(.callout)
							.foregroundStyle(.secondary)
						Text(InstallerPaths.codexSkillsDir.path)
							.font(.callout)
							.foregroundStyle(.secondary)

						Divider()

						Toggle("Claude Code", isOn: $claudeSkillsEnabled)
						Text(skillStatus(for: .claudeCode))
							.font(.callout)
							.foregroundStyle(.secondary)
						Text(InstallerPaths.claudeCodeSkillsDir.path)
							.font(.callout)
							.foregroundStyle(.secondary)
					}
					.frame(maxWidth: .infinity, alignment: .leading)
				}

				HeroActionSection(
					title: InstallerSimpleUI.skillButtonTitle(hasExistingManagedSkills: selectedTargetsHaveExistingSkills),
					isDisabled: !canInstall,
					action: onInstallSkills,
					showsProgress: action.activeKind == .skill
				) {
					if action.activeKind == .skill {
						Button("Cancel", action: onCancel)
							.buttonStyle(SecondaryPillButtonStyle())
							.keyboardShortcut(.cancelAction)
					}
				}

				Text("Restart Codex or Claude Code if the skills do not appear.")
					.foregroundStyle(.secondary)

				if action.clientReloadRecommended {
					Text("Skills were updated.")
						.foregroundStyle(.secondary)
				}

				InstallerLogGroupBox(logText: action.logText, isBusy: action.activeKind == .skill)
		}
	}

	private func skillStatus(for kind: InstallerSkillTargetSnapshot.Kind) -> String {
		skills.first(where: { $0.kind == kind })?.statusText ?? "Not installed"
	}
}

private struct StatusTabView: View {
	let snapshot: InstallerStatusSnapshot
	let isAdvancedModeEnabled: Bool
	let pluginsFolder: URL
	let onRefresh: () -> Void
	let onReveal: (URL) -> Void

	var body: some View {
		CenteredTabScroll {
				PageIntroText("Check the plug-in, agents, and local server details.")

				GroupBox("Plugin") {
					VStack(alignment: .leading, spacing: 10) {
						SimpleInfoRow(title: "Plug-in", value: snapshot.pluginStatusSummary)
						if let symlinkTarget = snapshot.installedPluginSymlinkTarget {
							PathInfoRow(title: "Dev target", value: symlinkTarget) {
								onReveal(URL(fileURLWithPath: symlinkTarget))
							}
						}
						SimpleInfoRow(title: "Python", value: snapshot.pythonStatus.summary)
						SimpleInfoRow(title: "Glyphs", value: snapshot.glyphsRunning ? "Running" : "Not running")
						PathInfoRow(title: "Plug-ins folder", value: pluginsFolder.path) {
							onReveal(pluginsFolder)
						}
					}
					.frame(maxWidth: .infinity, alignment: .leading)
				}

				GroupBox("Agents") {
					VStack(alignment: .leading, spacing: 12) {
						ForEach(snapshot.clients) { row in
							ClientStatusCard(
								title: row.name,
								row: row,
								isAdvancedModeEnabled: isAdvancedModeEnabled
							)
						}
					}
					.frame(maxWidth: .infinity, alignment: .leading)
				}

				GroupBox("Server") {
					VStack(alignment: .leading, spacing: 10) {
						Text(InstallerConstants.endpointURL.absoluteString)
							.font(.system(.body, design: .monospaced))
							.textSelection(.enabled)
						Text("If the server is not running, start it in Glyphs with Edit → Start MCP Server.")
							.foregroundStyle(.secondary)
					}
					.frame(maxWidth: .infinity, alignment: .leading)
				}

				HeroActionSection(title: "Re-scan", action: onRefresh)
		}
	}
}

private struct HelpTabView: View {
	@Binding var projectName: String
	let selectedFolder: URL?
	let createdFolder: URL?
	let isBusy: Bool
	let logText: String
	let onChooseFolder: () -> Void
	let onCreateProject: () -> Void
	let onReveal: (URL) -> Void
	@State private var copiedPrompt: Bool = false

	private let examplePrompt = "Use the Glyphs MCP server and call `list_open_fonts`. Return a table with `familyName`, `filePath`, `masterCount`, and `glyphCount` for each open font."

	var body: some View {
		CenteredTabScroll {
				PageIntroText("Create a starter folder, copy a prompt, and open the docs.")

				GroupBox("Project") {
					VStack(alignment: .leading, spacing: 12) {
						TextField("Project name", text: $projectName)
						HStack {
							Button("Choose location…", action: onChooseFolder)
								.buttonStyle(SecondaryPillButtonStyle())
							if let selectedFolder {
								Text(selectedFolder.path)
									.foregroundStyle(.secondary)
									.textSelection(.enabled)
							} else {
								Text("No folder selected")
									.foregroundStyle(.secondary)
							}
						}

						HeroActionSection(
							title: "Create project folder",
							isDisabled: selectedFolder == nil || isBusy,
							action: onCreateProject
						)

						if let createdFolder {
							HStack {
								Text(createdFolder.path)
									.foregroundStyle(.secondary)
									.textSelection(.enabled)
								Button("Open in Finder") { onReveal(createdFolder) }
									.buttonStyle(SecondaryPillButtonStyle())
							}
						}
					}
					.frame(maxWidth: .infinity, alignment: .leading)
				}

				GroupBox("Prompt") {
					VStack(alignment: .leading, spacing: 10) {
						Text(examplePrompt)
							.font(.system(.callout, design: .monospaced))
							.textSelection(.enabled)
						HStack {
							Button("Copy prompt") {
								Pasteboard.copy(examplePrompt)
								copiedPrompt = true
								DispatchQueue.main.asyncAfter(deadline: .now() + 2) { copiedPrompt = false }
							}
							.buttonStyle(SecondaryPillButtonStyle())
							if copiedPrompt {
								Text("Copied")
									.foregroundStyle(.secondary)
							}
						}
					}
					.frame(maxWidth: .infinity, alignment: .leading)
				}

				GroupBox("Links") {
					VStack(alignment: .leading, spacing: 8) {
						Link("GitHub", destination: URL(string: "https://github.com/thierryc/Glyphs-mcp")!)
						Link("Website", destination: URL(string: "https://www.ap.cx/gmcp")!)
					}
					.frame(maxWidth: .infinity, alignment: .leading)
				}

				InstallerLogGroupBox(logText: logText, isBusy: isBusy)
		}
	}
}

private struct InstallerTopTabBar: View {
	@Binding var selection: InstallerTab
	let isAdvancedModeEnabled: Bool

	var body: some View {
		HStack(spacing: 8) {
			ForEach(InstallerTab.visibleTabs(isAdvancedModeEnabled: isAdvancedModeEnabled), id: \.self) { tab in
				Button(tabLabel(for: tab)) {
					selection = tab
				}
				.buttonStyle(TopTabButtonStyle(isSelected: selection == tab))
			}
		}
		.padding(8)
		.background(
			Capsule(style: .continuous)
				.fill(.thinMaterial)
		)
		.overlay(
			Capsule(style: .continuous)
				.strokeBorder(.white.opacity(0.14))
		)
		.frame(maxWidth: .infinity, alignment: .center)
	}

	private func tabLabel(for tab: InstallerTab) -> String {
		switch tab {
		case .wizard: return "Wizard"
		case .install: return "Plugin"
		case .link: return "Agents"
		case .skill: return "Skill"
		case .status: return "Status"
		case .help: return "Help"
		}
	}
}

private struct TopTabButtonStyle: ButtonStyle {
	let isSelected: Bool

	func makeBody(configuration: Configuration) -> some View {
		configuration.label
			.font(.title3.weight(isSelected ? .semibold : .regular))
			.foregroundStyle(isSelected ? Color.primary : Color.primary.opacity(0.78))
			.padding(.horizontal, 18)
			.padding(.vertical, 12)
			.frame(minHeight: 44, alignment: .center)
			.background(
				Capsule(style: .continuous)
					.fill(isSelected ? Color.white.opacity(0.78) : Color.clear)
			)
			.overlay(
				Capsule(style: .continuous)
					.strokeBorder(isSelected ? .white.opacity(0.18) : .clear)
			)
			.scaleEffect(configuration.isPressed ? 0.985 : 1)
			.animation(.easeOut(duration: 0.12), value: configuration.isPressed)
	}
}

private struct HeroActionSection<SecondaryContent: View>: View {
	let title: String
	let isDisabled: Bool
	let action: () -> Void
	let showsProgress: Bool
	@ViewBuilder let secondaryContent: () -> SecondaryContent

	init(
		title: String,
		isDisabled: Bool = false,
		action: @escaping () -> Void,
		showsProgress: Bool = false,
		@ViewBuilder secondaryContent: @escaping () -> SecondaryContent = { EmptyView() }
	) {
		self.title = title
		self.isDisabled = isDisabled
		self.action = action
		self.showsProgress = showsProgress
		self.secondaryContent = secondaryContent
	}

	var body: some View {
		VStack(spacing: 14) {
			Button(title, action: action)
				.buttonStyle(PrimaryHeroButtonStyle())
				.disabled(isDisabled)

			if showsProgress {
				ProgressView()
			}

			secondaryContent()
		}
		.frame(maxWidth: .infinity, alignment: .center)
	}
}

private struct AdaptivePillActions<Content: View>: View {
	@ViewBuilder let content: () -> Content

	var body: some View {
		ViewThatFits(in: .horizontal) {
			HStack(spacing: 12) {
				content()
			}
			VStack(spacing: 10) {
				content()
			}
		}
		.frame(maxWidth: .infinity, alignment: .center)
	}
}

private struct CenteredTabScroll<Content: View>: View {
	@ViewBuilder let content: () -> Content

	var body: some View {
		ScrollView {
			VStack(spacing: 24) {
				content()
			}
			.frame(maxWidth: 760)
			.padding(.horizontal, 24)
			.padding(.bottom, 24)
			.frame(maxWidth: .infinity)
		}
	}
}

private struct PageIntroText: View {
	let text: String

	init(_ text: String) {
		self.text = text
	}

	var body: some View {
		Text(text)
			.foregroundStyle(.secondary)
			.font(.title3)
			.multilineTextAlignment(.center)
			.frame(maxWidth: 760)
	}
}

private struct ClientToggleRow: View {
	let row: InstallerClientStatusSnapshot
	@Binding var isOn: Bool
	let disabled: Bool

	var body: some View {
		VStack(alignment: .leading, spacing: 6) {
			HStack {
				Toggle(row.name, isOn: $isOn)
					.disabled(disabled)
				Spacer()
				Text(row.statusText)
					.font(.caption)
					.foregroundStyle(row.cardState == .configured ? .green : .secondary)
			}
			if let detailText = row.detailText, !detailText.isEmpty {
				Text(detailText)
					.foregroundStyle(.secondary)
					.font(.callout)
			}
			Text(row.visibleProbes.map { "\($0.label): \($0.summary)" }.joined(separator: " • "))
				.foregroundStyle(.secondary)
				.font(.callout)
		}
		.padding(.vertical, 4)
	}
}

private struct ClientStatusCard: View {
	let title: String
	let row: InstallerClientStatusSnapshot
	let isAdvancedModeEnabled: Bool

	var body: some View {
		VStack(alignment: .leading, spacing: 10) {
			HStack(alignment: .firstTextBaseline) {
				Text(title)
					.font(.headline)
				Spacer()
				Text(row.statusText)
					.font(.callout.weight(.medium))
					.foregroundStyle(statusColor)
			}

			ForEach(Array(row.visibleProbes.enumerated()), id: \.offset) { entry in
				ClientProbeRow(probe: entry.element, isAdvancedModeEnabled: isAdvancedModeEnabled)
			}

			if let detailText = row.detailText, !detailText.isEmpty {
				Text(detailText)
					.foregroundStyle(.secondary)
					.font(.callout)
			}
		}
		.padding(.vertical, 4)
	}

	private var statusColor: Color {
		switch row.cardState {
		case .configured: return .green
		case .partial: return .orange
		case .notDetected: return .secondary
		}
	}
}

private struct ClientProbeRow: View {
	let probe: InstallerClientStatusSnapshot.Probe
	let isAdvancedModeEnabled: Bool

	var body: some View {
		VStack(alignment: .leading, spacing: 2) {
			HStack(alignment: .firstTextBaseline, spacing: 12) {
				Text(probe.label)
					.font(.callout.weight(.semibold))
					.frame(width: 54, alignment: .leading)
				Text(probe.summary)
					.foregroundStyle(.secondary)
					.font(.callout)
			}
			if isAdvancedModeEnabled, let detail = probe.detail, !detail.isEmpty {
				Text(detail)
					.foregroundStyle(.secondary)
					.font(.caption)
					.padding(.leading, 66)
					.textSelection(.enabled)
			}
		}
	}
}

private struct SimpleInfoRow: View {
	let title: String
	let value: String

	var body: some View {
		HStack(alignment: .top, spacing: 10) {
			Text(title)
				.fontWeight(.semibold)
			Spacer()
			Text(value)
				.foregroundStyle(.secondary)
				.multilineTextAlignment(.trailing)
				.textSelection(.enabled)
		}
	}
}

private struct PathInfoRow: View {
	let title: String
	let value: String
	let action: () -> Void

	var body: some View {
		HStack(alignment: .top, spacing: 10) {
			Text(title)
				.fontWeight(.semibold)
			Spacer()
			Button(action: action) {
				Text(value)
					.foregroundStyle(.blue)
					.multilineTextAlignment(.trailing)
					.textSelection(.enabled)
			}
			.buttonStyle(.plain)
		}
	}
}

private struct WarningBanner: View {
	let title: String
	let message: String
	var buttonTitle: String? = nil
	var action: (() -> Void)? = nil

	var body: some View {
		HStack(alignment: .top, spacing: 10) {
			Image(systemName: "exclamationmark.triangle.fill")
				.foregroundStyle(.orange)
			VStack(alignment: .leading, spacing: 6) {
				Text(title)
					.bold()
				Text(message)
					.foregroundStyle(.secondary)
				if let buttonTitle, let action {
					Button(buttonTitle, action: action)
				}
			}
			Spacer()
		}
		.padding(14)
		.background(.orange.opacity(0.08), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
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
		GroupBox("Details") {
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
						.frame(minHeight: 160, maxHeight: 280)
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
