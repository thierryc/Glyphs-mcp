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
						action: action,
						configureCodex: $model.configureCodex,
						configureClaudeDesktop: $model.configureClaudeDesktop,
						configureClaudeCode: $model.configureClaudeCode,
						installCodexSkills: $model.installCodexSkills,
						installClaudeCodeSkills: $model.installClaudeCodeSkills,
						targets: snapshot.glyphsTargets,
						selectedGlyphsRunning: model.selectedGlyphsAreRunning,
						installMessage: model.installFailureReason,
						canInstall: model.canInstall,
						wizardButtonTitle: model.wizardButtonTitle,
						bindingForTarget: model.binding(for:),
						replacementBindingForTarget: model.replacementBinding(for:),
						onRunWizard: model.startWizard,
						onCancel: model.cancelWizard,
						onQuitGlyphs: model.quitSelectedGlyphsWithConfirmation
					)
				case .install:
					InstallTabView(
						targets: snapshot.glyphsTargets,
						action: action,
						selectedGlyphsRunning: model.selectedGlyphsAreRunning,
						installMessage: model.installFailureReason,
						canInstall: model.canInstall,
						installButtonTitle: model.installButtonTitle,
						bindingForTarget: model.binding(for:),
						replacementBindingForTarget: model.replacementBinding(for:),
						onInstall: model.startInstall,
						onCancel: model.cancelInstall,
						onQuitGlyphs: model.quitSelectedGlyphsWithConfirmation
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
						onRefresh: model.refreshSnapshot,
						onUninstall: model.presentUninstall,
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
		.sheet(isPresented: $model.isShowingUninstallSheet) {
			UninstallReviewSheet(
				plan: model.uninstallPlan,
				action: model.actionState,
				report: model.uninstallReport,
				hasAcknowledged: $model.hasAcknowledgedUninstall,
				selectedCount: model.selectedUninstallCandidates.count,
				selectedGlyphsRunning: model.selectedUninstallGlyphsAreRunning,
				canUninstall: model.canRunUninstall,
				bindingForCandidate: model.uninstallBinding(for:),
				onQuitGlyphs: model.quitSelectedUninstallGlyphsWithConfirmation,
				onUninstall: model.startUninstall,
				onDismiss: model.dismissUninstall
			)
		}
	}
}

private struct WizardTabView: View {
	let action: InstallerActionState
	@Binding var configureCodex: Bool
	@Binding var configureClaudeDesktop: Bool
	@Binding var configureClaudeCode: Bool
	@Binding var installCodexSkills: Bool
	@Binding var installClaudeCodeSkills: Bool
	let targets: [GlyphsTargetStatusSnapshot]
	let selectedGlyphsRunning: Bool
	let installMessage: String?
	let canInstall: Bool
	let wizardButtonTitle: String
	let bindingForTarget: (GlyphsMajorVersion) -> Binding<Bool>
	let replacementBindingForTarget: (GlyphsMajorVersion) -> Binding<Bool>
	let onRunWizard: () -> Void
	let onCancel: () -> Void
	let onQuitGlyphs: () -> Void

	private var selectedSummary: String {
		var items = targets
			.filter { bindingForTarget($0.version).wrappedValue }
			.map { $0.version.displayName }
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

				if selectedGlyphsRunning {
					WarningBanner(
						title: "Selected Glyphs version is running",
						message: installMessage ?? "Quit the selected Glyphs versions before running the wizard.",
						buttonTitle: "Quit Glyphs…",
						action: onQuitGlyphs
					)
					.frame(maxWidth: 760)
				} else if let message = installMessage {
					WarningBanner(title: "Setup blocked", message: message)
						.frame(maxWidth: 760)
				}

				GlyphsTargetSelectionGroup(
					targets: targets,
					isBusy: action.isBusy,
					bindingForTarget: bindingForTarget,
					replacementBindingForTarget: replacementBindingForTarget
				)

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
					title: wizardButtonTitle,
					isDisabled: !canInstall || action.isBusy,
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
	let targets: [GlyphsTargetStatusSnapshot]
	let action: InstallerActionState
	let selectedGlyphsRunning: Bool
	let installMessage: String?
	let canInstall: Bool
	let installButtonTitle: String
	let bindingForTarget: (GlyphsMajorVersion) -> Binding<Bool>
	let replacementBindingForTarget: (GlyphsMajorVersion) -> Binding<Bool>
	let onInstall: () -> Void
	let onCancel: () -> Void
	let onQuitGlyphs: () -> Void

	var body: some View {
		CenteredTabScroll {
				PageIntroText("Update the Glyphs MCP plug-in and its Python dependencies.")

				if selectedGlyphsRunning {
					WarningBanner(
						title: "Selected Glyphs version is running",
						message: installMessage ?? "Quit the selected Glyphs versions before updating the plug-in.",
						buttonTitle: "Quit Glyphs…",
						action: onQuitGlyphs
					)
				} else if let message = installMessage {
					WarningBanner(title: "Install blocked", message: message)
				}

				GlyphsTargetSelectionGroup(
					targets: targets,
					isBusy: action.isBusy,
					bindingForTarget: bindingForTarget,
					replacementBindingForTarget: replacementBindingForTarget
				)

				HeroActionSection(
					title: installButtonTitle,
					isDisabled: !canInstall || action.isBusy,
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

private struct GlyphsTargetSelectionGroup: View {
	let targets: [GlyphsTargetStatusSnapshot]
	let isBusy: Bool
	let bindingForTarget: (GlyphsMajorVersion) -> Binding<Bool>
	let replacementBindingForTarget: (GlyphsMajorVersion) -> Binding<Bool>

	var body: some View {
		GroupBox("Install for") {
			VStack(alignment: .leading, spacing: 14) {
				ForEach(Array(targets.sorted { $0.version < $1.version }.enumerated()), id: \.element.id) { entry in
					if entry.offset > 0 { Divider() }
					GlyphsTargetSelectionRow(
						target: entry.element,
						isSelected: bindingForTarget(entry.element.version),
						replaceDevSymlink: replacementBindingForTarget(entry.element.version),
						isBusy: isBusy
					)
				}
			}
			.frame(maxWidth: .infinity, alignment: .leading)
		}
	}
}

private struct GlyphsTargetSelectionRow: View {
	let target: GlyphsTargetStatusSnapshot
	@Binding var isSelected: Bool
	@Binding var replaceDevSymlink: Bool
	let isBusy: Bool

	var body: some View {
		VStack(alignment: .leading, spacing: 8) {
			HStack(alignment: .firstTextBaseline) {
				Toggle(target.version.displayName, isOn: $isSelected)
					.disabled(!target.isDetected || isBusy)
				Spacer()
				Text(target.isDetected ? "Detected" : "Not detected")
					.font(.callout.weight(.medium))
					.foregroundStyle(target.isDetected ? Color.green : Color.secondary)
			}

			if let application = target.application {
				Text([application.shortVersion, application.appURL.path].compactMap { $0 }.joined(separator: " • "))
					.font(.callout)
					.foregroundStyle(.secondary)
					.textSelection(.enabled)
			} else {
				Text("Install \(target.version.displayName) before selecting this target.")
					.font(.callout)
					.foregroundStyle(.secondary)
			}

			Text("Plug-in: \(target.pluginStatusSummary) • Python: \(target.pythonStatus.summary)")
				.font(.callout)
				.foregroundStyle(.secondary)

			if target.isRunning {
				Label("Running — quit before installation", systemImage: "exclamationmark.triangle.fill")
					.font(.callout)
					.foregroundStyle(.orange)
			}

			if isSelected, let warning = target.devPluginWarning {
				WarningBanner(title: "Development plug-in", message: warning)
				Toggle("Replace \(target.version.displayName) symlink with latest GitHub plug-in", isOn: $replaceDevSymlink)
					.disabled(isBusy)
			}
		}
		.padding(.vertical, 2)
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
	let onRefresh: () -> Void
	let onUninstall: () -> Void
	let onReveal: (URL) -> Void

	var body: some View {
		CenteredTabScroll {
				PageIntroText("Check the plug-in, agents, and local server details.")

				GroupBox("Glyphs installations") {
					VStack(alignment: .leading, spacing: 14) {
						ForEach(Array(snapshot.glyphsTargets.enumerated()), id: \.element.id) { entry in
							if entry.offset > 0 { Divider() }
							GlyphsTargetStatusCard(target: entry.element, onReveal: onReveal)
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
						Text("If the server is not running, start it in Glyphs with Edit → Glyphs MCP Server.")
							.foregroundStyle(.secondary)
					}
					.frame(maxWidth: .infinity, alignment: .leading)
				}

				HeroActionSection(title: "Re-scan", action: onRefresh)

				Button("Uninstall…", role: .destructive, action: onUninstall)
					.buttonStyle(SecondaryPillButtonStyle())
					.accessibilityHint("Review exactly what will be removed before uninstalling.")
		}
	}
}

private struct UninstallReviewSheet: View {
	let plan: GlyphsUninstallPlan
	let action: InstallerActionState
	let report: GlyphsUninstallReport?
	@Binding var hasAcknowledged: Bool
	let selectedCount: Int
	let selectedGlyphsRunning: Bool
	let canUninstall: Bool
	let bindingForCandidate: (String) -> Binding<Bool>
	let onQuitGlyphs: () -> Void
	let onUninstall: () -> Void
	let onDismiss: () -> Void

	private var isUninstalling: Bool { action.activeKind == .uninstall }

	var body: some View {
		VStack(spacing: 0) {
			HStack {
				VStack(alignment: .leading, spacing: 4) {
					Text("Review Glyphs MCP Uninstall")
						.font(.title2.weight(.semibold))
					Text("Nothing is removed until you confirm below.")
						.foregroundStyle(.secondary)
				}
				Spacer()
			}
			.padding(24)

			Divider()

			ScrollView {
				VStack(alignment: .leading, spacing: 18) {
					UninstallDisclaimer()
					if !plan.hasRemovableItems {
						Label("Nothing safely attributable is currently installed.", systemImage: "checkmark.shield")
							.foregroundStyle(.secondary)
					}

					if selectedGlyphsRunning {
						WarningBanner(
							title: "Selected Glyphs version is running",
							message: "Quit only the selected running Glyphs versions before removing their plug-ins.",
							buttonTitle: "Quit Selected Glyphs Apps…",
							action: onQuitGlyphs
						)
					}

					ForEach(UninstallComponentKind.allCases, id: \.rawValue) { component in
						let candidates = plan.candidates.filter { $0.component == component }
						if !candidates.isEmpty {
							GroupBox(componentTitle(component)) {
								VStack(alignment: .leading, spacing: 12) {
									ForEach(Array(candidates.enumerated()), id: \.element.id) { entry in
										if entry.offset > 0 { Divider() }
										UninstallCandidateRow(
											candidate: entry.element,
											isSelected: bindingForCandidate(entry.element.id),
											isDisabled: isUninstalling
										)
									}
								}
								.frame(maxWidth: .infinity, alignment: .leading)
							}
						}
					}

					GroupBox("Always preserved") {
						VStack(alignment: .leading, spacing: 7) {
							Label("Python packages and every site-packages folder", systemImage: "lock.shield")
							Label("Glyphs preferences and Glyphs MCP settings", systemImage: "lock.shield")
							Label("Font annotations, documents, repositories, and shared parent folders", systemImage: "lock.shield")
						}
						.frame(maxWidth: .infinity, alignment: .leading)
					}

					if let report {
						UninstallReportView(report: report)
					}

					if report == nil {
						Toggle("I understand that the selected items will be permanently removed.", isOn: $hasAcknowledged)
							.toggleStyle(.checkbox)
							.disabled(isUninstalling)
					}

					if isUninstalling || !action.logText.isEmpty {
						InstallerLogGroupBox(logText: action.logText, isBusy: isUninstalling)
					}
				}
				.padding(24)
			}

			Divider()

			HStack {
				Text(selectionSummary)
					.foregroundStyle(.secondary)
				Spacer()
				Button(report == nil ? "Cancel" : "Close", action: onDismiss)
					.keyboardShortcut(.cancelAction)
					.disabled(isUninstalling)
				if report == nil {
					Button("Uninstall", role: .destructive, action: onUninstall)
						.keyboardShortcut(.defaultAction)
						.disabled(!canUninstall)
				}
			}
			.padding(18)
		}
		.frame(width: 780, height: 720)
	}

	private var selectionSummary: String {
		if selectedCount == 1 {
			return NSLocalizedString("1 item selected", comment: "Uninstall selection count")
		}
		return String(format: NSLocalizedString("%d items selected", comment: "Uninstall selection count"), selectedCount)
	}

	private func componentTitle(_ component: UninstallComponentKind) -> String {
		switch component {
		case .plugin: return NSLocalizedString("Glyphs plug-ins", comment: "Uninstall component group")
		case .skill: return NSLocalizedString("Managed skills", comment: "Uninstall component group")
		case .client: return NSLocalizedString("Client configuration", comment: "Uninstall component group")
		}
	}
}

private struct UninstallDisclaimer: View {
	var body: some View {
		HStack(alignment: .top, spacing: 12) {
			Image(systemName: "exclamationmark.triangle.fill")
				.foregroundStyle(.red)
				.font(.title2)
			VStack(alignment: .leading, spacing: 7) {
				Text("Important — review before continuing")
					.font(.headline)
				Text("The uninstaller removes only checked items at the exact paths shown below. Matching client configuration files are backed up first. Same-named custom entries are preserved.")
				Text("Shared Python dependencies cannot be attributed safely and will not be removed.")
					.fontWeight(.semibold)
			}
		}
		.padding(14)
		.frame(maxWidth: .infinity, alignment: .leading)
		.background(Color.red.opacity(0.08), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
		.overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(Color.red.opacity(0.25)))
	}
}

private struct UninstallCandidateRow: View {
	let candidate: UninstallCandidate
	@Binding var isSelected: Bool
	let isDisabled: Bool

	var body: some View {
		HStack(alignment: .top, spacing: 12) {
			Toggle("", isOn: $isSelected)
				.labelsHidden()
				.toggleStyle(.checkbox)
				.disabled(isDisabled || !candidate.safetyState.isSelectable)
			VStack(alignment: .leading, spacing: 4) {
				HStack {
					Text(candidate.title)
						.fontWeight(.medium)
					Spacer()
					Text(stateLabel)
						.font(.caption.weight(.semibold))
						.foregroundStyle(stateColor)
				}
				Text(candidate.location.path)
					.font(.system(.caption, design: .monospaced))
					.foregroundStyle(.secondary)
					.textSelection(.enabled)
				Text(candidate.detail)
					.font(.caption)
					.foregroundStyle(.secondary)
			}
		}
	}

	private var stateLabel: String {
		switch candidate.safetyState {
		case .removable:
			return isSelected
				? NSLocalizedString("Selected for removal", comment: "Uninstall candidate state")
				: NSLocalizedString("Not selected", comment: "Uninstall candidate state")
		case .missing: return NSLocalizedString("Not detected", comment: "Uninstall candidate state")
		case .preserved: return NSLocalizedString("Preserved", comment: "Uninstall candidate state")
		case .blocked: return NSLocalizedString("Cannot inspect — preserved", comment: "Uninstall candidate state")
		}
	}

	private var stateColor: Color {
		switch candidate.safetyState {
		case .removable: return isSelected ? .red : .secondary
		case .missing: return .secondary
		case .preserved, .blocked: return .orange
		}
	}
}

private struct UninstallReportView: View {
	let report: GlyphsUninstallReport

	var body: some View {
		GroupBox(report.succeeded
			? NSLocalizedString("Uninstall complete", comment: "Uninstall result heading")
			: NSLocalizedString("Uninstall partially completed", comment: "Uninstall result heading")) {
			VStack(alignment: .leading, spacing: 8) {
				Text(String(
					format: NSLocalizedString("Removed: %d • Skipped: %d • Failed: %d", comment: "Uninstall result counts"),
					report.removedCount,
					report.skippedCount,
					report.failedCount
				))
				ForEach(report.outcomes) { outcome in
					Label {
						Text("\(outcome.candidate.title): \(outcome.message)")
					} icon: {
						Image(systemName: outcomeIcon(outcome.status))
							.foregroundStyle(outcomeColor(outcome.status))
					}
				}
			}
			.frame(maxWidth: .infinity, alignment: .leading)
		}
	}

	private func outcomeIcon(_ status: UninstallOutcomeStatus) -> String {
		switch status {
		case .removed: return "checkmark.circle.fill"
		case .skipped: return "minus.circle.fill"
		case .failed: return "xmark.octagon.fill"
		}
	}

	private func outcomeColor(_ status: UninstallOutcomeStatus) -> Color {
		switch status {
		case .removed: return .green
		case .skipped: return .orange
		case .failed: return .red
		}
	}
}

private struct GlyphsTargetStatusCard: View {
	let target: GlyphsTargetStatusSnapshot
	let onReveal: (URL) -> Void

	var body: some View {
		VStack(alignment: .leading, spacing: 10) {
			HStack {
				Text(target.version.displayName)
					.font(.headline)
				Spacer()
				Text(target.isDetected ? "Detected" : "Not detected")
					.foregroundStyle(target.isDetected ? Color.green : Color.secondary)
			}
			if let application = target.application {
				SimpleInfoRow(title: "App version", value: application.shortVersion ?? "Unknown")
				PathInfoRow(title: "Application", value: application.appURL.path) {
					onReveal(application.appURL)
				}
			} else {
				SimpleInfoRow(title: "Application", value: "Not detected")
			}
			SimpleInfoRow(title: "Plug-in", value: target.pluginStatusSummary)
			if let symlinkTarget = target.installedPluginSymlinkTarget {
				PathInfoRow(title: "Dev target", value: symlinkTarget) {
					onReveal(URL(fileURLWithPath: symlinkTarget))
				}
			}
			SimpleInfoRow(title: "Python", value: target.pythonStatus.summary)
			SimpleInfoRow(title: "Running", value: target.isRunning ? "Yes" : "No")
			PathInfoRow(title: "Plug-ins folder", value: target.pluginsDirectory.path) {
				onReveal(target.pluginsDirectory)
			}
		}
		.padding(.vertical, 3)
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
