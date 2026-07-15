import AppKit
import Foundation
import SwiftUI
import GlyphsMCPInstallerCore

enum InstallerTab: String, CaseIterable, Hashable {
	case wizard
	case install
	case link
	case skill
	case status
	case help

	var isAdvancedOnly: Bool {
		InstallerAdvancedModePolicy.advancedTabIDs.contains(rawValue)
	}

	static func visibleTabs(isAdvancedModeEnabled: Bool) -> [InstallerTab] {
		InstallerAdvancedModePolicy.visibleTabIDs(isAdvancedModeEnabled: isAdvancedModeEnabled).compactMap(Self.init(rawValue:))
	}

	var systemImage: String {
		switch self {
		case .wizard: return "wand.and.stars"
		case .install: return "square.and.arrow.down"
		case .link: return "link"
		case .skill: return "sparkles"
		case .status: return "checklist"
		case .help: return "questionmark.circle"
		}
	}
}

enum InstallerActionKind: Equatable {
	case wizard
	case install
	case link
	case skill
	case project
	case uninstall
}

struct InstallerActionState: Equatable {
	var activeKind: InstallerActionKind? = nil
	var logText: String = ""
	var installSteps: [InstallStep] = InstallStep.defaultSteps
	var restartRecommended: Bool = false
	var clientReloadRecommended: Bool = false

	var isBusy: Bool { activeKind != nil }

	mutating func resetFor(_ kind: InstallerActionKind) {
		activeKind = kind
		logText = ""
		restartRecommended = false
		clientReloadRecommended = false
		if kind == .install {
			installSteps = InstallStep.defaultSteps
		}
		if kind == .wizard {
			installSteps = InstallStep.defaultSteps
		}
	}
}

@MainActor
final class InstallerViewModel: ObservableObject {
	@Published var selectedTab: InstallerTab = .wizard
	@Published var isAdvancedModeEnabled: Bool {
		didSet {
			InstallerAdvancedModePreferences.save(isAdvancedModeEnabled)
			if !isAdvancedModeEnabled, selectedTab.isAdvancedOnly {
				selectedTab = .wizard
			}
		}
	}
	@Published private(set) var snapshot = InstallerStatusSnapshotBuilder.build(
		preflight: .empty,
		check: .empty,
		installedPluginVersion: nil,
		payloadPluginVersion: nil,
		glyphsRunning: false
	)
	@Published var actionState = InstallerActionState()

	@Published var configureCodex: Bool = true
	@Published var configureClaudeDesktop: Bool = true
	@Published var configureClaudeCode: Bool = true

	@Published var installCodexSkills: Bool = true
	@Published var installClaudeCodeSkills: Bool = true
	@Published var selectedGlyphsVersions: Set<GlyphsMajorVersion> = []
	@Published var replaceDevSymlinkVersions: Set<GlyphsMajorVersion> = []
	@Published var isShowingUninstallSheet = false
	@Published private(set) var uninstallPlan = GlyphsUninstallPlan(candidates: [])
	@Published var uninstallSelectedCandidateIDs: Set<String> = []
	@Published var hasAcknowledgedUninstall = false
	@Published private(set) var uninstallReport: GlyphsUninstallReport?

	@Published var starterParentFolder: URL? = nil
	@Published var starterProjectName: String = "Glyphs MCP Project"
	@Published var createdStarterProjectFolder: URL? = nil

	let manualClaudeCommand = "claude mcp add --scope user --transport http \(InstallerConstants.claudeCodeServerName) \(InstallerConstants.endpointURL.absoluteString)"

	private let runner = ProcessRunner()
	private var lastPreflight = PreflightResult.empty
	private var lastCheck = CheckResult.empty
	private var lastLogAt: Date = .distantPast
	private var installTask: Task<Void, Never>? = nil
	private var clientsTask: Task<Void, Never>? = nil
	private var skillsTask: Task<Void, Never>? = nil
	private var heartbeatTask: Task<Void, Never>? = nil
	private var glyphsWatcherTask: Task<Void, Never>? = nil
	private var uninstallTask: Task<Void, Never>? = nil
	private var lastGlyphsRunningVersions: Set<GlyphsMajorVersion>?
	private var hasInitializedGlyphsSelection = false

	var selectedTargetStatuses: [GlyphsTargetStatusSnapshot] {
		snapshot.glyphsTargets
			.filter { selectedGlyphsVersions.contains($0.version) }
			.sorted { $0.version < $1.version }
	}

	var installFailureReason: String? {
		InstallerTargetSelectionPolicy.installFailureReason(
			selectedVersions: selectedGlyphsVersions,
			targets: snapshot.glyphsTargets
		)
	}

	var canInstall: Bool { installFailureReason == nil }

	var selectedGlyphsAreRunning: Bool {
		selectedTargetStatuses.contains(where: \.isRunning)
	}

	var installButtonTitle: String {
		InstallerTargetSelectionPolicy.installButtonTitle(
			selectedVersions: selectedGlyphsVersions,
			targets: snapshot.glyphsTargets
		)
	}

	var wizardButtonTitle: String {
		let hasInstalledPlugin = selectedTargetStatuses.contains { $0.installedPluginVersion != nil }
		let hasExistingSkills = snapshot.skills.contains(where: \.hasInstalledSkills)
		return (hasInstalledPlugin || hasExistingSkills) ? "Update Setup" : "Complete Setup"
	}

	var selectedUninstallCandidates: [UninstallCandidate] {
		uninstallPlan.candidates.filter {
			uninstallSelectedCandidateIDs.contains($0.id) && $0.safetyState.isSelectable
		}
	}

	var selectedUninstallGlyphsVersions: Set<GlyphsMajorVersion> {
		GlyphsUninstallSelectionPolicy.selectedPluginVersions(
			plan: uninstallPlan.selecting(uninstallSelectedCandidateIDs)
		)
	}

	var selectedUninstallGlyphsAreRunning: Bool {
		GlyphsUninstallSelectionPolicy.selectedGlyphsAreRunning(
			plan: uninstallPlan.selecting(uninstallSelectedCandidateIDs),
			runningVersions: Set(snapshot.glyphsTargets.filter(\.isRunning).map(\.version))
		)
	}

	var canRunUninstall: Bool {
		GlyphsUninstallSelectionPolicy.canExecute(
			plan: uninstallPlan.selecting(uninstallSelectedCandidateIDs),
			hasAcknowledged: hasAcknowledgedUninstall,
			runningVersions: Set(snapshot.glyphsTargets.filter(\.isRunning).map(\.version)),
			isBusy: actionState.isBusy
		)
	}

	init() {
		isAdvancedModeEnabled = InstallerAdvancedModePreferences.load()
		refreshSnapshot()
		startGlyphsWatcher()
	}

	func setAdvancedModeEnabled(_ enabled: Bool) {
		isAdvancedModeEnabled = enabled
	}

	deinit {
		installTask?.cancel()
		clientsTask?.cancel()
		skillsTask?.cancel()
		heartbeatTask?.cancel()
		glyphsWatcherTask?.cancel()
		uninstallTask?.cancel()
	}

	func refreshSnapshot() {
		let preflight = Preflight.scanGlobal()
		let check = Check.scanClients()
		let applications = GlyphsApplicationDetector.detect()
		let applicationsByVersion = Dictionary(uniqueKeysWithValues: applications.map { ($0.majorVersion, $0) })
		let payloadPluginVersion = (try? InstallerPayload.resolve()).flatMap { PluginVersionReader.readPluginVersion(pluginBundle: $0.pluginBundle) }
		let runningVersions = GlyphsRuntime.runningVersions()
		let targets = GlyphsMajorVersion.allCases.map { version in
			GlyphsTargetStatusBuilder.build(
				version: version,
				application: applicationsByVersion[version],
				preflight: Preflight.scanGlyphs(glyphsVersion: version),
				payloadPluginVersion: payloadPluginVersion,
				isRunning: runningVersions.contains(version)
			)
		}
		let detectedVersions = Set(targets.filter(\.isDetected).map(\.version))

		lastPreflight = preflight
		lastCheck = check
		lastGlyphsRunningVersions = runningVersions
		snapshot = InstallerStatusSnapshotBuilder.build(
			glyphsTargets: targets,
			globalPreflight: preflight,
			check: check,
			payloadPluginVersion: payloadPluginVersion
		)
		selectedGlyphsVersions = InstallerTargetSelectionPolicy.reconciledSelection(
			current: selectedGlyphsVersions,
			detected: detectedVersions,
			hasInitialized: hasInitializedGlyphsSelection
		)
		hasInitializedGlyphsSelection = true
		let symlinkVersions = Set(targets.filter(\.installedPluginIsSymlink).map(\.version))
		replaceDevSymlinkVersions.formIntersection(symlinkVersions)
	}

	func binding(for version: GlyphsMajorVersion) -> Binding<Bool> {
		Binding(
			get: { self.selectedGlyphsVersions.contains(version) },
			set: { isSelected in
				if isSelected {
					self.selectedGlyphsVersions.insert(version)
				} else {
					self.selectedGlyphsVersions.remove(version)
				}
			}
		)
	}

	func replacementBinding(for version: GlyphsMajorVersion) -> Binding<Bool> {
		Binding(
			get: { self.replaceDevSymlinkVersions.contains(version) },
			set: { shouldReplace in
				if shouldReplace {
					self.replaceDevSymlinkVersions.insert(version)
				} else {
					self.replaceDevSymlinkVersions.remove(version)
				}
			}
		)
	}

	func uninstallBinding(for candidateID: String) -> Binding<Bool> {
		Binding(
			get: { self.uninstallSelectedCandidateIDs.contains(candidateID) },
			set: { isSelected in
				guard self.uninstallPlan.candidates.first(where: { $0.id == candidateID })?.safetyState.isSelectable == true else { return }
				if isSelected {
					self.uninstallSelectedCandidateIDs.insert(candidateID)
				} else {
					self.uninstallSelectedCandidateIDs.remove(candidateID)
				}
			}
		)
	}

	func quitSelectedGlyphsWithConfirmation() {
		GlyphsRuntime.quitGlyphsWithConfirmation(versions: selectedGlyphsVersions)
	}

	func quitSelectedUninstallGlyphsWithConfirmation() {
		GlyphsRuntime.quitGlyphsWithConfirmation(
			versions: selectedUninstallGlyphsVersions,
			reason: NSLocalizedString("must be closed so its plug-in can be removed safely.", comment: "Uninstall quit Glyphs reason")
		)
	}

	func presentUninstall() {
		guard !actionState.isBusy else { return }
		uninstallPlan = makeUninstallPlan()
		uninstallSelectedCandidateIDs = uninstallPlan.selectedCandidateIDs
		hasAcknowledgedUninstall = false
		uninstallReport = nil
		isShowingUninstallSheet = true
	}

	func dismissUninstall() {
		guard actionState.activeKind != .uninstall else { return }
		isShowingUninstallSheet = false
	}

	func startUninstall() {
		guard canRunUninstall else { return }
		let executionPlan = uninstallPlan.selecting(uninstallSelectedCandidateIDs)
		guard !executionPlan.selectedCandidates.isEmpty else { return }

		actionState.resetFor(.uninstall)
		appendLog(NSLocalizedString("== Uninstall ==", comment: "Uninstall log heading"))
		uninstallReport = nil
		uninstallTask?.cancel()

		let log: @Sendable (String) -> Void = { [weak self] line in
			Task { @MainActor in self?.appendLog(line) }
		}
		let finish: @Sendable (GlyphsUninstallReport) -> Void = { [weak self] report in
			Task { @MainActor in
				guard let self else { return }
				self.actionState.activeKind = nil
				self.uninstallReport = report
				self.refreshSnapshot()
				self.uninstallPlan = self.makeUninstallPlan()
				self.uninstallSelectedCandidateIDs = []
				if report.failedCount == 0 {
					self.appendLog(String(format: NSLocalizedString("Uninstall complete. Removed %d item(s).", comment: "Uninstall success log"), report.removedCount))
				} else {
					self.appendLog(String(format: NSLocalizedString("Uninstall finished with %d failure(s). Completed changes were kept.", comment: "Uninstall partial failure log"), report.failedCount))
				}
			}
		}

		uninstallTask = Task.detached(priority: .userInitiated) {
			let report = GlyphsUninstaller(log: log).execute(plan: executionPlan)
			finish(report)
		}
	}

	private func makeUninstallPlan() -> GlyphsUninstallPlan {
		let skillNames = (try? InstallerPayload.resolve())?.managedSkillDirectories().map(\.lastPathComponent) ?? []
		return GlyphsUninstallScanner.scan(managedSkillNames: skillNames)
	}

	func binding(for kind: InstallerClientKind) -> Binding<Bool> {
		switch kind {
		case .codex:
			return Binding(get: { self.configureCodex }, set: { self.configureCodex = $0 })
		case .claudeDesktop:
			return Binding(get: { self.configureClaudeDesktop }, set: { self.configureClaudeDesktop = $0 })
		case .claudeCode:
			return Binding(get: { self.configureClaudeCode }, set: { self.configureClaudeCode = $0 })
		}
	}

	func chooseStarterParentFolder() {
		let panel = NSOpenPanel()
		panel.allowsMultipleSelection = false
		panel.canChooseFiles = false
		panel.canChooseDirectories = true
		panel.canCreateDirectories = true
		panel.title = NSLocalizedString("Choose where to create the starter project folder", comment: "Open panel title")
		panel.prompt = NSLocalizedString("Choose", comment: "Open panel prompt")
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
		guard !actionState.isBusy else { return }
		guard canInstall else {
			setActionMessage("== Install ==", message: "ERROR: \(installFailureReason ?? "Install is blocked.")")
			return
		}
		guard let targetPlans = makeInstallTargetPlans() else {
			setActionMessage("== Install ==", message: "ERROR: Could not prepare the selected Glyphs installations.")
			return
		}

		actionState.resetFor(.install)
		appendLog("== Install ==")
		actionState.installSteps = InstallStep.steps(for: targetPlans.map(\.version))
		createdStarterProjectFolder = nil

		let options = InstallOptions(
			targets: targetPlans
		)

		beginHeartbeat()
		installTask?.cancel()
		let log: @Sendable (String) -> Void = { [weak self] line in
			Task { @MainActor in self?.appendLog(line) }
		}
		let mark: @Sendable (InstallStep.ID, InstallStep.State) -> Void = { [weak self] id, state in
			Task { @MainActor in self?.markInstallStep(id: id, state: state) }
		}
		let finish: @Sendable (Bool, Bool) -> Void = { [weak self] succeeded, restartRecommended in
			Task { @MainActor in
				guard let self else { return }
				self.stopHeartbeat()
				self.actionState.activeKind = nil
				self.actionState.restartRecommended = restartRecommended && succeeded
				self.refreshSnapshot()
			}
		}

		installTask = Task.detached(priority: .userInitiated) { [runner, options] in
			await InstallerViewModel.runInstallDetached(options: options, runner: runner, log: log, mark: mark, finish: finish)
		}
	}

	func startWizard() {
		guard !actionState.isBusy else { return }
		guard canInstall else {
			setActionMessage("== Wizard ==", message: "ERROR: \(installFailureReason ?? "Setup is blocked.")")
			return
		}
		guard let targetPlans = makeInstallTargetPlans() else {
			setActionMessage("== Wizard ==", message: "ERROR: Could not prepare the selected Glyphs installations.")
			return
		}

		let payload = try? InstallerPayload.resolve()
		let codexOverwriteSkills = installCodexSkills ? confirmOverwriteManagedSkillsIfNeeded(payload: payload, destRoot: InstallerPaths.codexSkillsDir, clientName: "Codex") : false
		let claudeOverwriteSkills = installClaudeCodeSkills ? confirmOverwriteManagedSkillsIfNeeded(payload: payload, destRoot: InstallerPaths.claudeCodeSkillsDir, clientName: "Claude Code") : false

		actionState.resetFor(.wizard)
		appendLog("== Wizard ==")
		actionState.installSteps = InstallStep.steps(for: targetPlans.map(\.version))
		createdStarterProjectFolder = nil

		let installOptions = InstallOptions(
			targets: targetPlans
		)

		let clientOptions = ClientsOptions(
			configureCodex: configureCodex,
			configureClaudeDesktop: configureClaudeDesktop,
			configureClaudeCode: configureClaudeCode,
			installCodexSkills: installCodexSkills,
			overwriteCodexSkills: codexOverwriteSkills,
			installClaudeCodeSkills: installClaudeCodeSkills,
			overwriteClaudeCodeSkills: claudeOverwriteSkills
		)

		beginHeartbeat()
		installTask?.cancel()
		let log: @Sendable (String) -> Void = { [weak self] line in
			Task { @MainActor in self?.appendLog(line) }
		}
		let mark: @Sendable (InstallStep.ID, InstallStep.State) -> Void = { [weak self] id, state in
			Task { @MainActor in self?.markInstallStep(id: id, state: state) }
		}
		let finish: @Sendable (Bool, Bool, Bool) -> Void = { [weak self] succeeded, restartRecommended, reloadRecommended in
			Task { @MainActor in
				guard let self else { return }
				self.stopHeartbeat()
				self.actionState.activeKind = nil
				self.actionState.restartRecommended = restartRecommended && succeeded
				self.actionState.clientReloadRecommended = reloadRecommended && succeeded
				self.refreshSnapshot()
				if succeeded {
					self.selectedTab = .status
				}
			}
		}

		installTask = Task.detached(priority: .userInitiated) { [runner, installOptions, clientOptions] in
			await InstallerViewModel.runWizardDetached(
				installOptions: installOptions,
				clientOptions: clientOptions,
				runner: runner,
				log: log,
				mark: mark,
				finish: finish
			)
		}
	}

	func cancelInstall() {
		installTask?.cancel()
		installTask = nil
		stopHeartbeat()
		actionState.activeKind = nil
		appendLog("Cancelled.")
	}

	func cancelWizard() {
		installTask?.cancel()
		installTask = nil
		stopHeartbeat()
		actionState.activeKind = nil
		appendLog("Cancelled.")
	}

	func startClientConfig() {
		guard !actionState.isBusy else { return }
		guard configureCodex || configureClaudeDesktop || configureClaudeCode else {
			setActionMessage("== Link to agents ==", message: "Nothing selected.")
			return
		}

		actionState.resetFor(.link)
		appendLog("== Link to agents ==")

		let options = ClientsOptions(
			configureCodex: configureCodex,
			configureClaudeDesktop: configureClaudeDesktop,
			configureClaudeCode: configureClaudeCode,
			installCodexSkills: false,
			overwriteCodexSkills: false,
			installClaudeCodeSkills: false,
			overwriteClaudeCodeSkills: false
		)

		clientsTask?.cancel()
		let log: @Sendable (String) -> Void = { [weak self] line in
			Task { @MainActor in self?.appendLog(line) }
		}
		let finish: @Sendable (Bool) -> Void = { [weak self] reloadRecommended in
			Task { @MainActor in
				guard let self else { return }
				self.actionState.activeKind = nil
				self.actionState.clientReloadRecommended = reloadRecommended
				self.refreshSnapshot()
			}
		}

		clientsTask = Task.detached(priority: .userInitiated) { [runner, options] in
			await InstallerViewModel.runClientsDetached(options: options, runner: runner, log: log, finish: finish)
		}
	}

	func cancelClientConfig() {
		clientsTask?.cancel()
		clientsTask = nil
		actionState.activeKind = nil
		appendLog("Cancelled.")
	}

	func startSkillInstall() {
		guard !actionState.isBusy else { return }
		guard installCodexSkills || installClaudeCodeSkills else {
			setActionMessage("== Install skills ==", message: "Nothing selected.")
			return
		}

		let payload = try? InstallerPayload.resolve()
		let codexOverwriteSkills = installCodexSkills ? confirmOverwriteManagedSkillsIfNeeded(payload: payload, destRoot: InstallerPaths.codexSkillsDir, clientName: "Codex") : false
		let claudeOverwriteSkills = installClaudeCodeSkills ? confirmOverwriteManagedSkillsIfNeeded(payload: payload, destRoot: InstallerPaths.claudeCodeSkillsDir, clientName: "Claude Code") : false

		actionState.resetFor(.skill)
		appendLog("== Install skills ==")

		let options = ClientsOptions(
			configureCodex: false,
			configureClaudeDesktop: false,
			configureClaudeCode: false,
			installCodexSkills: installCodexSkills,
			overwriteCodexSkills: codexOverwriteSkills,
			installClaudeCodeSkills: installClaudeCodeSkills,
			overwriteClaudeCodeSkills: claudeOverwriteSkills
		)

		skillsTask?.cancel()
		let log: @Sendable (String) -> Void = { [weak self] line in
			Task { @MainActor in self?.appendLog(line) }
		}
		let finish: @Sendable (Bool) -> Void = { [weak self] reloadRecommended in
			Task { @MainActor in
				guard let self else { return }
				self.actionState.activeKind = nil
				self.actionState.clientReloadRecommended = reloadRecommended
				self.refreshSnapshot()
			}
		}

		skillsTask = Task.detached(priority: .userInitiated) { [runner, options] in
			await InstallerViewModel.runClientsDetached(options: options, runner: runner, log: log, finish: finish)
		}
	}

	func cancelSkillInstall() {
		skillsTask?.cancel()
		skillsTask = nil
		actionState.activeKind = nil
		appendLog("Cancelled.")
	}

	func createStarterProject() async {
		guard !actionState.isBusy else { return }
		guard let parent = starterParentFolder else { return }
		actionState.resetFor(.project)
		appendLog("== Starter project ==")
		do {
			let name = starterProjectName.trimmingCharacters(in: .whitespacesAndNewlines)
			let created = try StarterProjectCreator(log: appendLog).createStarterProject(in: parent, projectName: name.isEmpty ? nil : name)
			createdStarterProjectFolder = created
			appendLog("Created starter folder: \(created.path)")
		} catch {
			appendLog("ERROR: \(error.localizedDescription)")
		}
		actionState.activeKind = nil
	}

	private func startGlyphsWatcher() {
		glyphsWatcherTask?.cancel()
		glyphsWatcherTask = Task { [weak self] in
			guard let self else { return }
			while !Task.isCancelled {
				try? await Task.sleep(nanoseconds: 1_000_000_000)
				guard !Task.isCancelled else { break }
				let runningVersions = GlyphsRuntime.runningVersions()
				if runningVersions != self.lastGlyphsRunningVersions {
					self.refreshSnapshot()
				}
			}
		}
	}

	private func setActionMessage(_ header: String, message: String) {
		actionState.logText = ""
		appendLog(header)
		appendLog(message)
	}

	private func appendLog(_ line: String) {
		lastLogAt = Date()
		if actionState.logText.isEmpty {
			actionState.logText = line
		} else {
			actionState.logText += "\n" + line
		}
	}

	private func markInstallStep(id: InstallStep.ID, state: InstallStep.State) {
		guard let idx = actionState.installSteps.firstIndex(where: { $0.id == id }) else { return }
		actionState.installSteps[idx].state = state
	}

	private func confirmOverwriteManagedSkillsIfNeeded(payload: InstallerPayload?, destRoot: URL, clientName: String) -> Bool {
		guard let payload else { return false }
		let installer = AgentSkillBundleInstaller(log: { _ in })
		let existing = installer.existingManagedSkillDestinations(from: payload, under: destRoot)
		guard !existing.isEmpty else { return false }

		let alert = NSAlert()
		alert.messageText = "Replace existing Glyphs MCP skills for \(clientName)?"
		alert.informativeText = "Existing managed Glyphs MCP skills were found in \(destRoot.path).\n\nChoose Replace to update those skills in place. Choose Keep current to leave existing skills untouched; any missing Glyphs MCP skills will still be installed."
		alert.addButton(withTitle: "Replace")
		alert.addButton(withTitle: "Keep current")
		return alert.runModal() == .alertFirstButtonReturn
	}

	private func makeInstallTargetPlans() -> [GlyphsInstallTargetPlan]? {
		var plans: [GlyphsInstallTargetPlan] = []
		for target in selectedTargetStatuses {
			guard let pythonSelection = target.pythonStatus.makeSelection() else { return nil }
			let strategy = GlyphsPluginInstallStrategy.resolve(
				installedPluginIsSymlink: target.installedPluginIsSymlink,
				replaceDevSymlink: replaceDevSymlinkVersions.contains(target.version)
			)
			plans.append(GlyphsInstallTargetPlan(
				version: target.version,
				pythonSelection: pythonSelection,
				pluginsDirectory: target.pluginsDirectory,
				pluginInstallStrategy: strategy
			))
		}
		return plans.isEmpty ? nil : plans
	}

	private func beginHeartbeat() {
		stopHeartbeat()
		heartbeatTask = Task { [weak self] in
			guard let self else { return }
			while !Task.isCancelled {
				try? await Task.sleep(nanoseconds: 20_000_000_000)
				guard self.actionState.isBusy else { break }
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

	nonisolated private static func runGlyphsInstallPhase(
		options: InstallOptions,
		runner: ProcessRunner,
		log: @escaping @Sendable (String) -> Void,
		mark: @escaping @Sendable (InstallStep.ID, InstallStep.State) -> Void
	) async throws {
		func step(_ title: String, id: InstallStep.ID, operation: () async throws -> Void) async throws {
			mark(id, .running)
			log("-- \(title) --")
			do {
				try await operation()
				mark(id, .success)
			} catch {
				mark(id, .failure)
				throw error
			}
		}

		var payload: InstallerPayload!
		try await step("Resolve payload", id: .payload) {
			payload = try InstallerPayload.resolve()
			log("Payload OK: \(payload.payloadDir.path)")
		}

		var completedDependencyKeys: Set<String> = []
		var downloadedPluginBundle: URL?
		for target in options.targets.sorted(by: { $0.version < $1.version }) {
			if Task.isCancelled { throw CancellationError() }
			let dependencyStepID = InstallStep.ID.dependencies(target.version)
			if completedDependencyKeys.contains(target.dependencyInstallKey) {
				log("Reusing dependencies already installed for \(target.version.displayName).")
				mark(dependencyStepID, .success)
			} else {
				try await step("Install \(target.version.displayName) dependencies", id: dependencyStepID) {
					try await DepsInstaller(runner: runner, log: log).installAndVerify(
						python: target.pythonSelection,
						requirementsTxt: payload.requirementsTxt,
						glyphsVersion: target.version
					)
				}
				completedDependencyKeys.insert(target.dependencyInstallKey)
			}

			try await step("Install \(target.version.displayName) plug-in", id: .plugin(target.version)) {
				let installer = PluginInstaller(log: log)
				switch target.pluginInstallStrategy {
				case .bundledPayload:
					log("Installing the bundled plug-in for \(target.version.displayName).")
					_ = try installer.installPluginBundle(from: payload.pluginBundle, toPluginsDir: target.pluginsDirectory, allowReplace: true)
				case .keepDevSymlink:
					log("Keeping the existing \(target.version.displayName) development symlink in place.")
				case .latestFromGitHub:
					if downloadedPluginBundle == nil {
						log("Downloading the latest GitHub plug-in once for the selected targets.")
						downloadedPluginBundle = try await GitHubPluginDownloader(runner: runner, log: log).downloadAndExtractPluginBundle()
					}
					guard let downloadedPluginBundle else {
						throw InstallerError.userFacing("The latest GitHub plug-in could not be resolved.")
					}
					_ = try installer.installPluginBundle(from: downloadedPluginBundle, toPluginsDir: target.pluginsDirectory, allowReplace: true)
				}
			}
		}
	}

	nonisolated private static func runInstallDetached(
		options: InstallOptions,
		runner: ProcessRunner,
		log: @escaping @Sendable (String) -> Void,
		mark: @escaping @Sendable (InstallStep.ID, InstallStep.State) -> Void,
		finish: @escaping @Sendable (Bool, Bool) -> Void
	) async {
		do {
			if Task.isCancelled { throw CancellationError() }
			try await runGlyphsInstallPhase(options: options, runner: runner, log: log, mark: mark)

			mark(.done, .done)
			let names = options.targets.sorted(by: { $0.version < $1.version }).map { $0.version.displayName }.joined(separator: " and ")
			log("Install complete for \(names). Next: open Glyphs and run Edit → Glyphs MCP Server.")
			finish(true, false)
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
		finish: @escaping @Sendable (Bool) -> Void
	) async {
		do {
			var shouldRecommendReload = false
			if options.configureCodex {
				try await CodexConfigurator(runner: runner, log: log).configure()
			}
			if options.configureClaudeDesktop {
				try ClaudeDesktopConfigurator(log: log).configure()
			}
			if options.configureClaudeCode {
				try await ClaudeCodeConfigurator(runner: runner, log: log).configureIfAvailable()
			}
			if options.installCodexSkills || options.installClaudeCodeSkills {
				let payload = try InstallerPayload.resolve()
				let skillInstaller = AgentSkillBundleInstaller(log: log)
				if options.installCodexSkills {
					shouldRecommendReload = (try skillInstaller.installCodexSkills(payload: payload, overwriteExisting: options.overwriteCodexSkills)) || shouldRecommendReload
				}
				if options.installClaudeCodeSkills {
					shouldRecommendReload = (try skillInstaller.installClaudeCodeSkills(payload: payload, overwriteExisting: options.overwriteClaudeCodeSkills)) || shouldRecommendReload
				}
				if shouldRecommendReload {
					log("Reload or restart Codex / Claude Code to pick up the newly installed Glyphs MCP skills.")
				}
			}
			log("Done.")
			finish(shouldRecommendReload)
		} catch {
			log("ERROR: \(error.localizedDescription)")
			finish(false)
		}
	}

	nonisolated private static func runWizardDetached(
		installOptions: InstallOptions,
		clientOptions: ClientsOptions,
		runner: ProcessRunner,
		log: @escaping @Sendable (String) -> Void,
		mark: @escaping @Sendable (InstallStep.ID, InstallStep.State) -> Void,
		finish: @escaping @Sendable (Bool, Bool, Bool) -> Void
	) async {
		do {
			if Task.isCancelled { throw CancellationError() }
			try await runGlyphsInstallPhase(options: installOptions, runner: runner, log: log, mark: mark)

			mark(.done, .done)
			log("-- Link clients and install skills --")

			var reloadRecommended = false
			if clientOptions.configureCodex {
				try await CodexConfigurator(runner: runner, log: log).configure()
				reloadRecommended = true
			}
			if clientOptions.configureClaudeDesktop {
				try ClaudeDesktopConfigurator(log: log).configure()
				reloadRecommended = true
			}
			if clientOptions.configureClaudeCode {
				try await ClaudeCodeConfigurator(runner: runner, log: log).configureIfAvailable()
				reloadRecommended = true
			}
			if clientOptions.installCodexSkills || clientOptions.installClaudeCodeSkills {
				let payload = try InstallerPayload.resolve()
				let skillInstaller = AgentSkillBundleInstaller(log: log)
				if clientOptions.installCodexSkills {
					reloadRecommended = (try skillInstaller.installCodexSkills(payload: payload, overwriteExisting: clientOptions.overwriteCodexSkills)) || reloadRecommended
				}
				if clientOptions.installClaudeCodeSkills {
					reloadRecommended = (try skillInstaller.installClaudeCodeSkills(payload: payload, overwriteExisting: clientOptions.overwriteClaudeCodeSkills)) || reloadRecommended
				}
			}

			let names = installOptions.targets.sorted(by: { $0.version < $1.version }).map { $0.version.displayName }.joined(separator: " and ")
			log("Setup complete for \(names). Next: open Glyphs and run Edit → Glyphs MCP Server.")
			if reloadRecommended {
				log("Reload or restart Codex / Claude Code to pick up the new configuration and skills.")
			}
			finish(true, false, reloadRecommended)
		} catch is CancellationError {
			mark(.done, .failure)
			log("Cancelled.")
			finish(false, false, false)
		} catch {
			mark(.done, .failure)
			log("ERROR: \(error.localizedDescription)")
			finish(false, false, false)
		}
	}
}

extension InstallerViewModel: @unchecked Sendable {}

private struct InstallOptions: Sendable {
	let targets: [GlyphsInstallTargetPlan]
}

private struct ClientsOptions: Sendable {
	let configureCodex: Bool
	let configureClaudeDesktop: Bool
	let configureClaudeCode: Bool
	let installCodexSkills: Bool
	let overwriteCodexSkills: Bool
	let installClaudeCodeSkills: Bool
	let overwriteClaudeCodeSkills: Bool
}

struct InstallStep: Identifiable, Equatable {
	enum ID: Hashable, Sendable {
		case payload
		case dependencies(GlyphsMajorVersion)
		case plugin(GlyphsMajorVersion)
		case done
	}

	enum State: Equatable {
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
		steps(for: [.installerDefault])
	}

	static func steps(for versions: [GlyphsMajorVersion]) -> [InstallStep] {
		var result: [InstallStep] = [
			.init(id: .payload, title: NSLocalizedString("Resolve payload", comment: "Install step title"), state: .pending),
		]
		for version in Array(Set(versions)).sorted() {
			result.append(.init(
				id: .dependencies(version),
				title: String(format: NSLocalizedString("Install %@ dependencies", comment: "Install step title"), version.displayName),
				state: .pending
			))
			result.append(.init(
				id: .plugin(version),
				title: String(format: NSLocalizedString("Install %@ plug-in", comment: "Install step title"), version.displayName),
				state: .pending
			))
		}
		result.append(.init(id: .done, title: NSLocalizedString("Done", comment: "Install step title"), state: .pending))
		return result
	}
}
