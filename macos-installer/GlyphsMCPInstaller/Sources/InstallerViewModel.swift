import AppKit
import Foundation
import GlyphsMCPInstallerCore

@MainActor
final class InstallerViewModel: ObservableObject {
    @Published private(set) var applications: [GlyphsApplicationInfo] = []
    @Published private(set) var installed: Set<String> = []
    @Published private(set) var componentStates: [String: SetupItemState] = [:]
    @Published private(set) var componentUpdates: [String: ComponentUpdateStatus] = [:]
    private var componentUpdateTask: Task<Void, Never>?
    var componentUpdateReminderKey: String {
        ComponentUpdateReminder.key(version: projectVersion,
            build: Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "unknown", root: root)
    }
    @Published private(set) var connectorStates: [InstallerClientKind: SetupItemState] = [:]
    @Published private(set) var detectedClients: Set<InstallerClientKind> = []
    @Published private(set) var connectorInformation: [InstallerClientKind: String] = [:]
    @Published private(set) var connectorVersions: [InstallerClientKind: String] = [:]
    @Published var notice: ComponentNotice = .none
    @Published private(set) var log = ""
    @Published private(set) var busy = false
    @Published var includeDevelopmentSkills = UserDefaults.standard.bool(forKey: "includeGlyphsMCPDevelopmentSkills") {
        didSet { UserDefaults.standard.set(includeDevelopmentSkills, forKey: "includeGlyphsMCPDevelopmentSkills") }
    }
    @Published var supplementalSkillsBusy = false
    @Published private(set) var optionalStates: [String: OptionalToolState] = [:]
    @Published private(set) var optionalErrors: [String: String] = [:]
    @Published private(set) var optionalOperation: String?
    @Published private(set) var optionalDiscoveryError: String?
    private var optionalTask: Task<Void, Never>?
    var operationsBusy: Bool { busy || supplementalSkillsBusy || optionalOperation != nil }
    @Published private(set) var running = false
    @Published private(set) var receiptURL: URL?
    @Published var updateStatus: PluginUpdateStatus = .idle
    @Published private var pythonSession = GlyphsPythonCheckSession()
    @Published private(set) var selectedGlyphsPath: String?
    var pythonCheck: GlyphsPythonCheckState { pythonSession.state }
    var pythonDetection: GlyphsPythonDetection? { pythonSession.detection }
    var hasMultipleGlyphsCopies: Bool { GlyphsCopySelectionPolicy.showsSelector(for: applications) }
    var canSelectGlyphsCopy: Bool { !operationsBusy && refreshTask == nil }
    private static let selectedGlyphsPreference = "selectedGlyphs4ApplicationPath"
    var pythonReady: Bool { pythonCheck.verified }
    var checkingPython: Bool { pythonCheck.isChecking }
    var pythonVersion: String? { pythonCheck.version }
    var pythonSetupError: String? { pythonCheck.error }
    var canInstallComponents: Bool { pythonCheck.allowsInstallation }

    var stopServiceBeforeQuit: (() async throws -> Void)?
    var showTroubleshootingLogs: (() -> Void)?

    private let runner = ProcessRunner()
    private let fm = FileManager.default
    private let diagnosticSessionID = UUID().uuidString
    private let eventLogger = InstallerEventLogger()
    private let logCollector = InstallerLogCollector()
    private let root = InstallerPaths.home.appendingPathComponent("Library/Application Support/Glyphs MCP/lean-v2")
    @Published private(set) var initializationStage: String?
    @Published private(set) var initializationError: String?
    @Published private(set) var initializationStartedAt = Date()
    @Published private(set) var initializationDetails: [String] = []
    private var payload: InstallerPayload?
    private let payloadResolver = InstallerPayloadDiscovery.shared
    private var refreshTask: Task<Void, Never>?
    private var setupVisible = false
    private var phaseStartedAt: Date?

    func recordPresentation(_ name: String, since start: Date) {
        timed(name, since: start)
    }

    func setSetupVisible(_ visible: Bool) {
        setupVisible = visible
        if visible {
            if !pythonReady && !pythonCheck.isSkipped { checkGlyphsPython() }
            refreshOptionalTools()
        }
    }

    private func stage(_ text: String) {
        if let previous = initializationStage, let start = phaseStartedAt {
            timed(previous, since: start)
        }
        phaseStartedAt = Date()
        initializationStage = text
        initializationDetails.append(text)
    }

    private func timed(_ name: String, since start: Date) {
        let detail = String(format: "%@ completed in %.2f seconds", name, Date().timeIntervalSince(start))
        initializationDetails.append(detail)
        record(detail)
    }
    private var task: Task<Void, Never>?
    private var pythonCheckTask: Task<Void, Never>?
    private var observers: [NSObjectProtocol] = []

    var message: String { notice.text }
    var projectVersion: String { Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "unknown" }
    var versionLabel: String { DesktopIdentity.versionLabel }
    var application: GlyphsApplicationInfo? { GlyphsCopySelectionPolicy.selected(from: applications, preferredPath: selectedGlyphsPath) }
    var allInstalled: Bool {
        DesktopComponent.ids.isSubset(of: installed)
            && Set(InstallerClientKind.allCases).isSubset(of: installedConnectors)
    }
    var bulkActionTitle: String { allInstalled ? "Update All" : "Install All" }
    var canChangeComponents: Bool { !operationsBusy && refreshTask == nil && !checkingPython && application != nil && !running }
    var canRunBulkAction: Bool { canChangeComponents && canInstallComponents }
    var installedConnectors: Set<InstallerClientKind> {
        Set(InstallerClientKind.allCases.filter { connectorStates[$0] == .installed })
    }
    var inspectorInstructions: String {
        let names = [("curve-inspector", "Curve Inspector"), ("reference-inspector", "Changes Against Reference")]
            .filter { installed.contains($0.0) }.map(\.1).joined(separator: " and ")
        return names.isEmpty ? "" : "In Glyphs’ View menu, enable " + names + "."
    }

    init() {
        selectedGlyphsPath = UserDefaults.standard.string(forKey: Self.selectedGlyphsPreference)
        let center = NSWorkspace.shared.notificationCenter
        for event in [NSWorkspace.didLaunchApplicationNotification, NSWorkspace.didTerminateApplicationNotification] {
            observers.append(center.addObserver(forName: event, object: nil, queue: .main) { [weak self] _ in
                Task { @MainActor in self?.refreshRunning() }
            })
        }
        diagnostic("session.started", details: [
            "appVersion": projectVersion,
            "appBuild": Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "unknown",
            "appPath": Bundle.main.bundleURL.path,
            "macOS": ProcessInfo.processInfo.operatingSystemVersionString,
            "architecture": Self.processArchitecture,
        ])
    }

    private static var processArchitecture: String {
        #if arch(arm64)
        return "arm64"
        #else
        return "x86_64"
        #endif
    }

    private func diagnostic(_ event: String, operationID: String? = nil, details: [String: Any] = [:]) {
        record(logCollector.diagnosticEvent(event, sessionID: diagnosticSessionID,
                                          operationID: operationID, details: details))
    }

    deinit {
        for observer in observers { NSWorkspace.shared.notificationCenter.removeObserver(observer) }
        task?.cancel()
        pythonCheckTask?.cancel()
        refreshTask?.cancel()
        optionalTask?.cancel()
        componentUpdateTask?.cancel()
    }

    func checkForUpdates() {
        guard updateStatus != .checking else { return }
        updateStatus = .checking
        Task {
            do { updateStatus = try await GitHubReleaseResolver.checkForUpdate(currentVersion: projectVersion) }
            catch { updateStatus = .error(message: "Couldn’t check for updates. Please try again.") }
        }
    }

    func refresh(resetFailures: Bool = false) {
        guard refreshTask == nil, !operationsBusy else { return }
        initializationStartedAt = Date()
        initializationError = nil
        initializationDetails = []
        stage("Checking installed components…")
        refreshTask = Task { [weak self] in
            guard let self else { return }
            defer {
                self.refreshTask = nil
                if !self.checkingPython { self.initializationStage = nil }
                if self.setupVisible && !self.pythonCheck.isSkipped && !Task.isCancelled { self.checkGlyphsPython() }
        }
        let start = Date()
        // Local qualification can simulate a blocked filesystem check without
        // delaying first presentation. This preference is absent from Release.
        #if DEBUG
        let qualificationDelay = min(30, max(0, UserDefaults(suiteName: "cx.ap.glyphsMcp.qualification")?
            .double(forKey: "startupDiscoveryDelaySeconds") ?? 0))
        #else
        let qualificationDelay: TimeInterval = 0
        #endif
        let discovered = await Task.detached(priority: .utility) {
            if qualificationDelay > 0 { Thread.sleep(forTimeInterval: qualificationDelay) }
            let all = GlyphsApplicationDetector.detectAll()
            return (GlyphsCopySelectionPolicy.copies(from: all), DesktopInstallation(), all)
        }.value
        guard !Task.isCancelled else { return }
        self.applications = discovered.0
        self.selectedGlyphsPath = self.application?.appURL.path
        if let path = self.selectedGlyphsPath { UserDefaults.standard.set(path, forKey: Self.selectedGlyphsPreference) }
        self.bindPythonToSelectedCopy()
        self.diagnostic("glyphs.discovery", details: [
            "copies": discovered.2.map { ["path": $0.appURL.path, "bundleIdentifier": $0.bundleIdentifier,
                                           "version": $0.shortVersion ?? "unknown", "beta": $0.isBeta] as [String: Any] },
            "selectedPath": self.application?.appURL.path ?? "none",
            "selectionPolicy": "Retain user selection; otherwise prefer stable bundle, then /Applications, then path order",
            "scanScope": "/Applications, ~/Applications and Launch Services bundle lookup",
        ])
        let installation = discovered.1
        self.timed("Installed component discovery", since: start)
        installed = installation.components
        let receipt = root.appendingPathComponent("installation.json")
        let receiptIsLink = (try? receipt.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink) == true
        receiptURL = fm.fileExists(atPath: receipt.path) || receiptIsLink ? receipt : nil
        for component in DesktopComponent.all {
            let current = componentStates[component.id]
            if resetFailures || !Self.preservesDuringRefresh(current) {
                componentStates[component.id] = installation.developmentLinkedComponents.contains(component.id)
                    ? .developmentLinked
                    : installed.contains(component.id) ? .installed : .notInstalled
            }
        }
        if !installation.brokenDevelopmentLinkedComponents.isEmpty,
           resetFailures || !notice.isFailure {
            let names = DesktopComponent.all
                .filter { installation.brokenDevelopmentLinkedComponents.contains($0.id) }
                .map(\.title).joined(separator: ", ")
            notice = .failure("Development links were found, but their build targets are missing: \(names). Rebuild the linked development payload, then refresh Setup.")
        }
        refreshConnectorDetection(resetFailures: resetFailures)
        refreshRunning()
        refreshComponentUpdates()

        }
    }

    func selectGlyphsApplication(_ path: String) {
        guard canSelectGlyphsCopy, let chosen = applications.first(where: { $0.appURL.path == path }),
              chosen.appURL != application?.appURL else { return }
        selectedGlyphsPath = chosen.appURL.path
        UserDefaults.standard.set(chosen.appURL.path, forKey: Self.selectedGlyphsPreference)
        bindPythonToSelectedCopy()
        diagnostic("glyphs.selection-changed", details: ["selectedPath": path, "bundleIdentifier": chosen.bundleIdentifier])
        refreshRunning()
        if setupVisible { checkGlyphsPython() }
    }

    private func bindPythonToSelectedCopy() {
        guard pythonSession.bind(application) else { return }
        pythonCheckTask?.cancel()
        pythonCheckTask = nil
        initializationError = nil
        initializationDetails = []
        phaseStartedAt = nil
        if refreshTask == nil { initializationStage = nil }
    }

    private var runningGlyphs4Applications: [NSRunningApplication] {
        NSWorkspace.shared.runningApplications.filter { app in
            guard let url = app.bundleURL else { return false }
            return !GlyphsCopySelectionPolicy.copies(from: GlyphsApplicationDetector.allApplications(candidates: [url])).isEmpty
        }
    }

    private var runningGlyphsDiagnostics: [[String: Any]] {
        NSWorkspace.shared.runningApplications
            .filter { GlyphsRunningProcessDetector.supportedBundleIdentifiers.contains($0.bundleIdentifier ?? "") }
            .map { ["path": $0.bundleURL?.path ?? "unknown", "bundleIdentifier": $0.bundleIdentifier ?? "unknown",
                    "processId": $0.processIdentifier] }
    }

    func refreshRunning() {
        running = !runningGlyphs4Applications.isEmpty
        notice.glyphsRunningChanged(running)
    }

    func quitGlyphs() {
        guard !operationsBusy, application != nil else { return }
        busy = true
        Task {
            defer { busy = false }
            do {
                try await stopServiceBeforeQuit?()
                for app in self.runningGlyphs4Applications {
                    app.terminate()
                }
                notice = .waitingForGlyphs
                record("Requested Glyphs 4 to quit before setup changes.")
                refreshRunning()
            } catch {
                notice = .failure(error.localizedDescription)
                record("Could not quit Glyphs safely: \(error.localizedDescription)")
            }
        }
    }

    func openGlyphs() {
        guard let application else { return }
        let configuration = NSWorkspace.OpenConfiguration()
        configuration.activates = true
        NSWorkspace.shared.openApplication(at: application.appURL, configuration: configuration)
    }

    func openPythonInPluginManager() {
        guard !operationsBusy, !checkingPython, let application,
              let url = URL(string: "glyphsapp4://showplugin/Python") else { return }
        NSWorkspace.shared.open([url], withApplicationAt: application.appURL,
                                configuration: NSWorkspace.OpenConfiguration()) { [weak self] _, error in
            if let error {
                Task { @MainActor in
                    self?.notice = .failure("Open Window → Plugin Manager → Modules in Glyphs and choose Python. " + error.localizedDescription)
                }
            }
        }
    }

    func checkGlyphsPython() {
        guard !operationsBusy, refreshTask == nil, !checkingPython else { return }
        guard let application else { return }
        let checkToken = pythonSession.begin()
        let checkID = checkToken.uuidString
        diagnostic("python-check.requested", operationID: checkID, details: [
            "glyphsPath": application.appURL.path, "bundleIdentifier": application.bundleIdentifier,
            "version": application.shortVersion ?? "unknown", "runningCopies": runningGlyphsDiagnostics,
        ])
        pythonCheckTask = Task { [weak self] in
            guard let self else { return }
            let start = Date()
            self.initializationStartedAt = start
            self.initializationError = nil
            defer { if self.pythonSession.accepts(checkToken) { self.initializationStage = nil } }
            self.stage("Preparing setup files…")
            var payloadReady = false
            do {
                let payload = try await self.resolvePayload(operationID: checkID)
                guard !Task.isCancelled, self.pythonSession.accepts(checkToken) else { return }
                payloadReady = true
                let lean = payload.payloadDir.appendingPathComponent("Lean")
                #if arch(arm64)
                let architecture = "arm64"
                #else
                let architecture = "x86_64"
                #endif
                let python = lean.appendingPathComponent("runtimes/\(architecture)/bin/python3")
                let helper = payload.payloadDir.appendingPathComponent("Installer/install_simple_v2.py")
                let preflightStart = Date()
                self.stage("Checking Glyphs Python…")
                #if DEBUG
                if ProcessInfo.processInfo.arguments.contains("--qualify-python-check-failure") {
                    throw InstallerError.userFacing("Qualification: simulated Glyphs Python check failure.")
                }
                #endif
                self.diagnostic("python-check.helper-started", operationID: checkID,
                                details: ["privatePython": python.path, "helper": helper.path, "timeoutSeconds": 60])
                let result = try await self.runner.runCapturing(executable: python,
                    args: ["-I", "-B", helper.path, "--build", lean.path,
                           "--glyphs-app", application.appURL.path, "--preflight-only",
                           "--diagnostic-id", checkID], timeout: 60,
                    onFailureOutput: { [weak self] output in
                        Task { @MainActor in
                            for line in output.stderr.prefix(32768).split(separator: "\n") { self?.record(String(line)) }
                            self?.diagnostic("python-check.helper-interrupted", operationID: checkID,
                                             details: ["stdout": String(output.stdout.prefix(8192)), "partialOutputRetained": true])
                        }
                    })
                guard !Task.isCancelled, self.pythonSession.accepts(checkToken) else { return }
                let detection = GlyphsPythonDetection.parse(result.stderr, checkID: checkID)
                for line in result.stderr.split(separator: "\n") { self.record(String(line)) }
                self.diagnostic("python-check.helper-finished", operationID: checkID,
                                details: ["exitCode": result.exitCode, "elapsedSeconds": Date().timeIntervalSince(preflightStart),
                                          "stdout": String(result.stdout.prefix(8192))])
                let response = (try? JSONSerialization.jsonObject(with: result.stdoutData)) as? [String: Any]
                guard result.exitCode == 0, response?["ok"] as? Bool == true else {
                    let detail = (response?["error"] as? [String: Any])?["message"] as? String
                    let message = detail ?? result.stderr
                    self.pythonSession.finish(checkToken, state: .failed(message, canSkip: payloadReady), detection: detection)
                    throw InstallerError.userFacing(message)
                }
                self.pythonSession.finish(checkToken, state: .ready(response?["pythonVersion"] as? String), detection: detection)
                Task { [weak self] in self?.refreshOptionalTools() }
                self.timed("Glyphs Python preflight", since: preflightStart)
            } catch {
                guard !Task.isCancelled, self.pythonSession.accepts(checkToken) else { return }
                self.pythonSession.finish(checkToken, state: .failed(error.localizedDescription, canSkip: payloadReady),
                                        detection: self.pythonDetection)
                self.initializationError = error.localizedDescription
                self.diagnostic("python-check.failed", operationID: checkID,
                                details: ["payloadReady": payloadReady, "error": error.localizedDescription,
                                          "elapsedSeconds": Date().timeIntervalSince(start)])
                self.record("Glyphs Python readiness check failed: \(error.localizedDescription)")
            }
        }
    }

    func allowInstallationWithoutPythonCheck() {
        guard !operationsBusy, !checkingPython, let application, pythonCheck.canSkip else { return }
        pythonSession.allowUnverifiedInstallation()
        record("User allowed installation without a verified Glyphs Python check for \(application.appURL.path).")
    }

    func installAll() {
        refreshRunning()
        guard canRunBulkAction else { return }
        let plan = SetupQueuePolicy.bulkPlan(installedComponents: installed, installedConnectors: installedConnectors)
        for item in plan {
            switch item {
            case .component(let id, let operation): componentStates[id] = .queued(operation)
            case .connector(let client, let operation): connectorStates[client] = .queued(operation)
            }
        }
        busy = true
        notice = .information("Preparing the setup queue…")
        record("Queued \(plan.count) v2 setup items.")
        task = Task { [weak self] in await self?.runBulkQueue(plan) }
    }

    func installComponent(_ id: String) { performComponent(id, operation: .install) }
    func updateComponent(_ id: String) { performComponent(id, operation: .update) }
    func removeComponent(_ id: String) { performComponent(id, operation: .remove) }
    func retryComponent(_ id: String) {
        guard case .failed(let operation, _) = componentStates[id] else { return }
        performComponent(id, operation: operation)
    }

    func installConnector(_ client: InstallerClientKind) { performConnector(client, operation: .install) }
    func updateConnector(_ client: InstallerClientKind) { performConnector(client, operation: .update) }
    func removeConnector(_ client: InstallerClientKind) { performConnector(client, operation: .remove) }
    func retryConnector(_ client: InstallerClientKind) {
        guard case .failed(let operation, _) = connectorStates[client] else { return }
        performConnector(client, operation: operation)
    }

    func state(for component: DesktopComponent) -> SetupItemState {
        componentStates[component.id] ?? .notInstalled
    }

    func state(for client: InstallerClientKind) -> SetupItemState {
        connectorStates[client] ?? .notInstalled
    }

    func connectorGuidance(_ client: InstallerClientKind) -> String {
        switch client {
        case .codex: return "Reload Codex after setup changes. MCP settings and managed skills are included. The Glyphs MCP development skill is also available in Skills for creating scripts and plugins."
        case .claudeCode: return "Restart Claude Code after setup changes. MCP settings and managed skills are included. The Glyphs MCP development skill is also available in Skills for creating scripts and plugins."
        case .claudeDesktop: return "Restart Claude Desktop after setup changes."
        case .cursor: return "Reload or restart Cursor to activate the local Glyphs MCP plug-in."
        }
    }

    func connectorLogoAsset(_ client: InstallerClientKind) -> String {
        switch client {
        case .codex: return "CodexLogo"
        case .claudeCode: return "ClaudeCodeLogo"
        case .claudeDesktop: return "ClaudeLogo"
        case .cursor: return "CursorLogo"
        }
    }

    func logText(source: InstallerLogSource, serverEvents: [String]) -> String {
        logCollector.collect(source: source, serverEvents: serverEvents)
    }

    func redactedDiagnostics(serverEvents: [String]) -> String {
        logCollector.redactedDiagnosticReport(logCollector.collect(source: .all, serverEvents: serverEvents))
    }

    func revealLogs() {
        try? fm.createDirectory(at: InstallerPaths.installerLogDirectory, withIntermediateDirectories: true)
        NSWorkspace.shared.activateFileViewerSelecting([InstallerPaths.installerLogDirectory])
    }

    private func runBulkQueue(_ queue: [SetupQueueItem]) async {
        defer { busy = false; refreshComponentUpdates() }
        do {
            refreshRunning()
            guard !running else { throw InstallerError.userFacing("Quit Glyphs, then try again.") }
            let componentItems = queue.compactMap { item -> (String, SetupOperation)? in
                if case .component(let id, let operation) = item { return (id, operation) }
                return nil
            }
            for (id, operation) in componentItems { componentStates[id] = .active(operation) }
            notice = .information("Installing Glyphs components…")
            try await executeComponentTransaction(selected: DesktopComponent.ids)
            for (id, _) in componentItems { componentStates[id] = .installed }
            installed = DesktopComponent.ids
            record("Installed all bundled Glyphs 4 components atomically.")
        } catch {
            let message = error.localizedDescription
            for component in DesktopComponent.all {
                let operation = componentStates[component.id]?.operation ?? .install
                componentStates[component.id] = .failed(operation, message)
            }
            for client in InstallerClientKind.allCases {
                let operation = connectorStates[client]?.operation ?? .install
                connectorStates[client] = .failed(operation, "Blocked because Glyphs MCP did not install successfully.")
            }
            notice = .failure(message)
            record("Component transaction failed: \(message)")
            return
        }

        var connectorFailures = 0
        var preservedSkills = false
        let connectorItems = queue.compactMap { item -> (InstallerClientKind, SetupOperation)? in
            if case .connector(let client, let operation) = item { return (client, operation) }
            return nil
        }
        for (client, operation) in connectorItems {
            connectorStates[client] = .active(operation)
            notice = .information("Configuring \(client.displayName)…")
            do {
                let information = try await executeConnector(client, operation: operation)
                connectorInformation[client] = information
                preservedSkills = preservedSkills || information != nil
                connectorStates[client] = .installed
                connectorVersions[client] = payload?.plugin(for: .v4).version.shortVersion ?? projectVersion
                record("Configured \(client.displayName).")
            } catch {
                connectorFailures += 1
                connectorInformation[client] = nil
                connectorStates[client] = .failed(operation, error.localizedDescription)
                record("\(client.displayName) failed: \(error.localizedDescription)")
            }
        }
        refreshPreservingOperationResults()
        notice = .setupCompletion(failedConnections: connectorFailures, preservedSkills: preservedSkills)
    }

    private func performComponent(_ id: String, operation: SetupOperation) {
        refreshRunning()
        guard DesktopComponent.ids.contains(id), canChangeComponents else { return }
        guard operation == .remove || canInstallComponents else {
            notice = .failure("Complete Glyphs Python setup and choose Check again before installing components.")
            return
        }
        busy = true
        componentStates[id] = .active(operation)
        notice = .information(operation.progressLabel.replacingOccurrences(of: "…", with: "") + " " + componentTitle(id) + "…")
        task = Task { [weak self] in
            guard let self else { return }
            defer { self.busy = false; self.refreshComponentUpdates() }
            do {
                if operation == .remove {
                    try await self.executeComponentRemoval(id)
                    self.componentStates[id] = .notInstalled
                    self.installed.remove(id)
                } else {
                    try await self.executeComponentTransaction(selected: self.installed.union([id]), only: id)
                    self.componentStates[id] = .installed
                    self.installed.insert(id)
                }
                self.notice = .information("\(self.componentTitle(id)) \(operation == .remove ? "removed" : "installed").")
                self.record("\(operation.rawValue.capitalized) completed for \(self.componentTitle(id)).")
                self.refreshPreservingOperationResults()
            } catch {
                self.componentStates[id] = .failed(operation, error.localizedDescription)
                self.notice = .failure(error.localizedDescription)
                self.record("\(self.componentTitle(id)) failed: \(error.localizedDescription)")
            }
        }
    }

    private func performConnector(_ client: InstallerClientKind, operation: SetupOperation) {
        guard !operationsBusy else { return }
        if operation != .remove && !installed.contains("mcp") {
            connectorStates[client] = .failed(operation, "Install Glyphs MCP before configuring this connection.")
            return
        }
        busy = true
        connectorStates[client] = .active(operation)
        notice = .information("\(operation.progressLabel.replacingOccurrences(of: "…", with: "")) \(client.displayName)…")
        task = Task { [weak self] in
            guard let self else { return }
            defer { self.busy = false }
            do {
                let information = try await self.executeConnector(client, operation: operation)
                self.connectorInformation[client] = information
                self.connectorStates[client] = operation == .remove ? .notInstalled : .installed
                if operation == .remove { self.connectorVersions.removeValue(forKey: client) }
                else { self.connectorVersions[client] = self.payload?.plugin(for: .v4).version.shortVersion ?? self.projectVersion }
                self.notice = .information(information ?? "\(client.displayName) \(operation == .remove ? "removed" : "configured").")
                self.record("\(operation.rawValue.capitalized) completed for \(client.displayName).")
            } catch {
                self.connectorInformation[client] = nil
                self.connectorStates[client] = .failed(operation, error.localizedDescription)
                self.notice = .failure(error.localizedDescription)
                self.record("\(client.displayName) failed: \(error.localizedDescription)")
            }
        }
    }

    private struct OptionalResponse: Decodable {
        let ok: Bool
        let data: [OptionalToolState]?
    }

    func refreshOptionalTools() {
        guard optionalTask == nil, !operationsBusy else { return }
        optionalTask = Task { [weak self] in
            guard let self else { return }
            defer { self.optionalTask = nil }
            do {
                let result = try await self.optionalCommand(action: "status")
                let response = try JSONDecoder().decode(OptionalResponse.self, from: result.stdoutData)
                guard response.ok, let states = response.data else { throw InstallerError.userFacing("Could not inspect optional tools.") }
                self.optionalStates = Dictionary(uniqueKeysWithValues: states.map { ($0.id, $0) })
                self.optionalDiscoveryError = nil
            } catch {
                self.optionalDiscoveryError = error.localizedDescription
                self.record("Optional tool discovery: \(error.localizedDescription)")
            }
        }
    }

    func canChangeOptionalTool(_ id: String) -> Bool {
        !operationsBusy && !checkingPython && optionalTask == nil &&
        optionalStates[id]?.protectedInstallation != true &&
        (id != "beztrace-glyphs" || (application != nil && !running && canInstallComponents))
    }

    func changeOptionalTool(_ id: String, action: String) {
        guard canChangeOptionalTool(id) else { return }
        if action != "remove" && optionalStates[id]?.available != true { return }
        optionalOperation = id
        optionalErrors[id] = nil
        optionalTask = Task { [weak self] in
            guard let self else { return }
            do {
                // The existing control handshake refuses active/unresolved jobs.
                try await self.stopServiceBeforeQuit?()
                _ = try await self.optionalCommand(action: action, tool: id)
                self.record("Optional tool \(id): \(action) completed; native loading remains unverified.")
            } catch { self.optionalErrors[id] = error.localizedDescription; self.record("Optional tool \(id): \(error.localizedDescription)") }
            self.optionalOperation = nil
            self.optionalTask = nil
            self.refreshOptionalTools()
        }
    }

    private func optionalCommand(action: String, tool: String? = nil) async throws -> ProcessRunner.Result {
        let payload = try await resolvePayload()
        #if arch(arm64)
        let architecture = "arm64"
        #else
        let architecture = "x86_64"
        #endif
        let python = payload.payloadDir.appendingPathComponent("Lean/runtimes/\(architecture)/bin/python3")
        let helper = payload.payloadDir.appendingPathComponent("Installer/install_optional_tools.py")
        let catalog = payload.payloadDir.appendingPathComponent("Installer/optional-tools.json")
        var arguments = ["-I", "-B", helper.path, "--catalog", catalog.path, "--action", action]
        if let tool { arguments += ["--tool", tool] }
        if tool == "beztrace-glyphs", let resources = Bundle.main.resourceURL {
            arguments += ["--engine", resources.appendingPathComponent("Beztrace/beztrace-0.2.1").path]
        }
        let result = try await runner.runCapturing(executable: python, args: arguments, timeout: 600, maximumStandardOutputBytes: 1024 * 1024)
        guard result.exitCode == 0 else {
            let response = (try? JSONSerialization.jsonObject(with: result.stdoutData)) as? [String: Any]
            let message = (response?["error"] as? [String: Any])?["message"] as? String
            throw InstallerError.userFacing(message ?? result.stderr)
        }
        return result
    }

    private func executeComponentTransaction(selected: Set<String>, only: String? = nil) async throws {
        guard let application else { throw InstallerError.userFacing("Glyphs 4 is required.") }
        let payload = try await resolvePayload()
        let lean = payload.payloadDir.appendingPathComponent("Lean")
        #if arch(arm64)
        let architecture = "arm64"
        #else
        let architecture = "x86_64"
        #endif
        let python = lean.appendingPathComponent("runtimes/\(architecture)/bin/python3")
        let helper = payload.payloadDir.appendingPathComponent("Installer/install_simple_v2.py")
        var args = ["-B", helper.path, "--build", lean.path, "--glyphs-app", application.appURL.path, "--start"]
        if pythonCheck.isSkipped { args.append("--skip-python-check") }
        if !selected.contains("mcp") { args.append("--no-mcp") }
        for id in selected.sorted() where id != "mcp" { args += ["--companion", id] }
        if let only { args += ["--only", only] }
        let operationID = UUID().uuidString
        args += ["--diagnostic-id", operationID]
        diagnostic("installation.requested", operationID: operationID,
                   details: ["components": selected.sorted(), "only": only ?? "all-selected",
                             "pythonCheckSkipped": pythonCheck.isSkipped, "glyphsPath": application.appURL.path])
        do {
            try await execute(python, args)
            diagnostic("installation.completed", operationID: operationID)
        } catch {
            diagnostic("installation.failed", operationID: operationID, details: ["error": error.localizedDescription])
            throw error
        }
        receiptURL = root.appendingPathComponent("installation.json")
    }

    private func executeComponentRemoval(_ id: String) async throws {
        guard let application else { throw InstallerError.userFacing("Glyphs 4 is required.") }
        let payload = try await resolvePayload()
        let lean = payload.payloadDir.appendingPathComponent("Lean")
        #if arch(arm64)
        let architecture = "arm64"
        #else
        let architecture = "x86_64"
        #endif
        let python = lean.appendingPathComponent("runtimes/\(architecture)/bin/python3")
        let helper = payload.payloadDir.appendingPathComponent("Installer/install_simple_v2.py")
        let args = ["-B", helper.path, "--build", lean.path, "--glyphs-app", application.appURL.path,
                    "--no-mcp", "--remove", id, "--only", id]
        try await execute(python, args)
    }

    private func executeConnector(_ client: InstallerClientKind, operation: SetupOperation) async throws -> String? {
        let payload = try await resolvePayload()
        let endpoint = DesktopInstallation().endpoint
        let logger: (String) -> Void = { [weak self] text in self?.appendLog(text) }
        let skills = AgentSkillBundleInstaller(log: logger)
        if operation == .remove {
            switch client {
            case .codex:
                try ConnectorConfigurationRemover.removeCodex(endpoint: endpoint)
                let result = try skills.removeOwnedSkills(from: payload, under: InstallerPaths.codexSkillsDir)
                return result.preservationInformation
            case .claudeCode:
                try ConnectorConfigurationRemover.removeClaude(client: .claudeCode, at: InstallerPaths.claudeCodeConfig,
                    serverName: InstallerConstants.claudeCodeServerName, endpoint: endpoint)
                let result = try skills.removeOwnedSkills(from: payload, under: InstallerPaths.claudeCodeSkillsDir)
                return result.preservationInformation
            case .claudeDesktop:
                try ConnectorConfigurationRemover.removeClaude(client: .claudeDesktop, at: InstallerPaths.claudeDesktopConfig,
                    serverName: InstallerConstants.claudeDesktopServerName, endpoint: endpoint)
            case .cursor:
                try makeCursorInstaller(payload, logger: logger).remove()
            }
            return nil
        }

        switch client {
        case .codex:
            try await CodexConfigurator(runner: runner, endpointURL: endpoint, log: logger).configure()
            return try skills.installCodexSkills(payload: payload, overwriteExisting: false, includeDevelopmentSkills: includeDevelopmentSkills).preservationInformation
        case .claudeCode:
            try await ClaudeCodeConfigurator(runner: runner, endpointURL: endpoint, log: logger).configureIfAvailable()
            return try skills.installClaudeCodeSkills(payload: payload, overwriteExisting: false, includeDevelopmentSkills: includeDevelopmentSkills).preservationInformation
        case .claudeDesktop:
            let proxy = [root.appendingPathComponent("runtime/bin/python3").path,
                         "-B", root.appendingPathComponent("sidecar/proxy.py").path]
            try ClaudeDesktopConfigurator(endpointURL: endpoint, proxyCommand: proxy, log: logger).configure()
        case .cursor:
            try makeCursorInstaller(payload, logger: logger).installOrUpdate()
        }
        return nil
    }

    private func resolvePayload(operationID: String? = nil) async throws -> InstallerPayload {
        let start = Date()
        let model = self
        let resolved = try await payloadResolver.resolve {
            try InstallerPayload.resolve(progress: { message in
                Task { @MainActor in
                    if model.checkingPython && (operationID == nil || model.pythonSession.activeCheckID?.uuidString == operationID) { model.stage(message) }
                }
            })
        }
        payload = resolved
        diagnostic("payload.resolved", operationID: operationID ?? UUID().uuidString,
                   details: ["elapsedSeconds": Date().timeIntervalSince(start), "path": resolved.payloadDir.path,
                             "scope": "caller wait; discovery is shared and cached"])
        return resolved
    }

    private func makeCursorInstaller(_ payload: InstallerPayload, logger: @escaping (String) -> Void) throws -> CursorPluginInstaller {
        guard let source = payload.cursorPluginURL,
              let identity = payload.cursorPluginIdentity,
              let version = payload.cursorPluginVersion else {
            throw InstallerError.userFacing("The installer payload does not contain the Cursor plug-in.")
        }
        return CursorPluginInstaller(source: source, expectedIdentity: identity, version: version, log: logger)
    }

    private func execute(_ executable: URL, _ args: [String]) async throws {
        let environment = ProcessInfo.processInfo.environment.merging([
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"
        ]) { _, new in new }
        let result = try await runner.runCapturing(executable: executable, args: args, environment: environment, timeout: 300)
        record(String(result.stdout.prefix(16384)))
        record(String(result.stderr.prefix(32768)))
        guard result.exitCode == 0 else {
            let data = result.stdout.data(using: .utf8) ?? Data()
            let response = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            let detail = (response?["error"] as? [String: Any])?["message"] as? String
            throw InstallerError.userFacing(detail ?? (result.stderr.isEmpty ? result.stdout : result.stderr))
        }
    }

    private func refreshConnectorDetection(resetFailures: Bool = false) {
        detectedClients = Set(InstallerClientKind.allCases.filter(detectsClient))
        for client in InstallerClientKind.allCases {
            let current = connectorStates[client]
            guard resetFailures || !Self.preservesDuringRefresh(current) else { continue }
            if connectorIsInstalled(client) {
                connectorStates[client] = .installed
                connectorVersions[client] = installedConnectorVersion(client)
            } else {
                connectorStates[client] = .notInstalled
                connectorVersions.removeValue(forKey: client)
            }
        }
    }

    private func detectsClient(_ client: InstallerClientKind) -> Bool {
        switch client {
        case .codex:
            return NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.openai.codex") != nil
                || fm.fileExists(atPath: InstallerPaths.home.appendingPathComponent(".codex").path)
        case .claudeCode:
            return fm.fileExists(atPath: InstallerPaths.home.appendingPathComponent(".claude").path)
                || fm.fileExists(atPath: InstallerPaths.claudeCodeConfig.path)
        case .claudeDesktop:
            return NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.anthropic.claudefordesktop") != nil
                || fm.fileExists(atPath: InstallerPaths.claudeDesktopConfig.path)
        case .cursor:
            return NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.todesktop.230313mzl4w4u92") != nil
                || fm.fileExists(atPath: InstallerPaths.home.appendingPathComponent(".cursor").path)
        }
    }

    private func connectorIsInstalled(_ client: InstallerClientKind) -> Bool {
        let endpoint = DesktopInstallation().endpoint.absoluteString
        switch client {
        case .codex:
            guard let text = try? String(contentsOf: InstallerPaths.codexConfig, encoding: .utf8) else { return false }
            return CodexTomlInspector.readServerConfig(toml: text, serverName: InstallerConstants.codexServerName)?.url == endpoint
        case .claudeCode:
            guard let text = try? String(contentsOf: InstallerPaths.claudeCodeConfig, encoding: .utf8) else { return false }
            return ClaudeConfigInspector.readServerConfig(json: text, serverName: InstallerConstants.claudeCodeServerName)?.url == endpoint
        case .claudeDesktop:
            guard let data = try? Data(contentsOf: InstallerPaths.claudeDesktopConfig),
                  let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let servers = root["mcpServers"] as? [String: Any],
                  let server = servers[InstallerConstants.claudeDesktopServerName] as? [String: Any],
                  let args = server["args"] as? [String] else { return false }
            return args.contains(endpoint)
        case .cursor:
            if let payload, let installer = try? makeCursorInstaller(payload, logger: { _ in }) {
                if case .installed = installer.inspect() { return true }
                return false
            }
            return fm.fileExists(atPath: InstallerPaths.cursorPluginDir.path)
                && fm.fileExists(atPath: InstallerPaths.cursorPluginReceipt.path)
        }
    }

    private func installedConnectorVersion(_ client: InstallerClientKind) -> String {
        if client == .cursor,
           let data = try? Data(contentsOf: InstallerPaths.cursorPluginReceipt),
           let receipt = try? JSONDecoder().decode(CursorPluginOwnershipReceipt.self, from: data) {
            return receipt.version
        }
        return DesktopInstallation().version ?? projectVersion
    }

    private func refreshPreservingOperationResults() {
        let componentResults = componentStates
        let connectorResults = connectorStates
        refresh()
        for (id, state) in componentResults where state.failureMessage != nil || state == .installed || state == .developmentLinked || state == .notInstalled {
            componentStates[id] = state
        }
        for (client, state) in connectorResults where state.failureMessage != nil || state == .installed || state == .notInstalled {
            connectorStates[client] = state
        }
    }

    private func componentTitle(_ id: String) -> String {
        DesktopComponent.all.first { $0.id == id }?.title ?? id
    }

    private func refreshComponentUpdates() {
        componentUpdateTask?.cancel()
        componentUpdateTask = Task { [weak self] in
            guard let self else { return }
            do {
                let payload = try await self.resolvePayload()
                guard !Task.isCancelled else { return }
                let lean = payload.payloadDir.appendingPathComponent("Lean")
                let architecture = Self.processArchitecture
                let statuses = await Task.detached(priority: .utility) {
                    ComponentUpdatePolicy.discover(installation: DesktopInstallation(), lean: lean,
                        architecture: architecture)
                }.value
                guard !Task.isCancelled else { return }
                self.componentUpdates = statuses
            } catch {
                guard !Task.isCancelled else { return }
                self.componentUpdates = [:]
                self.record("Component update availability could not be verified: \(error.localizedDescription)")
            }
        }
    }

    private func appendLog(_ text: String) {
        guard !text.isEmpty else { return }
        log += (log.isEmpty ? "" : "\n") + text
        if log.utf8.count > 200_000 { log = String(log.suffix(160_000)) }
    }

    private func record(_ message: String) {
        appendLog(message)
        eventLogger.append(message)
    }

    private static func preservesDuringRefresh(_ state: SetupItemState?) -> Bool {
        guard let state else { return false }
        switch state {
        case .queued, .active, .failed: return true
        case .notInstalled, .installed, .developmentLinked: return false
        }
    }
}
