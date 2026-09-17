import AppKit
import Foundation
import GlyphsMCPInstallerCore

@MainActor
final class InstallerViewModel: ObservableObject {
    @Published private(set) var applications: [GlyphsApplicationInfo] = []
    @Published private(set) var installed: Set<String> = []
    @Published private(set) var componentStates: [String: SetupItemState] = [:]
    @Published private(set) var connectorStates: [InstallerClientKind: SetupItemState] = [:]
    @Published private(set) var detectedClients: Set<InstallerClientKind> = []
    @Published private(set) var connectorVersions: [InstallerClientKind: String] = [:]
    @Published var notice: ComponentNotice = .none
    @Published private(set) var log = ""
    @Published private(set) var busy = false
    @Published private(set) var running = false
    @Published private(set) var receiptURL: URL?
    @Published var updateStatus: PluginUpdateStatus = .idle

    var stopServiceBeforeQuit: (() async throws -> Void)?
    var showTroubleshootingLogs: (() -> Void)?

    private let runner = ProcessRunner()
    private let fm = FileManager.default
    private let eventLogger = InstallerEventLogger()
    private let logCollector = InstallerLogCollector()
    private let root = InstallerPaths.home.appendingPathComponent("Library/Application Support/Glyphs MCP/lean-v2")
    private var payload: InstallerPayload?
    private var task: Task<Void, Never>?
    private var observers: [NSObjectProtocol] = []

    var message: String { notice.text }
    var projectVersion: String { Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "unknown" }
    var versionLabel: String { DesktopIdentity.versionLabel }
    var application: GlyphsApplicationInfo? { applications.first { $0.majorVersion == .v4 } }
    var allInstalled: Bool {
        DesktopComponent.ids.isSubset(of: installed)
            && Set(InstallerClientKind.allCases).isSubset(of: installedConnectors)
    }
    var bulkActionTitle: String { allInstalled ? "Update All" : "Install All" }
    var canChangeComponents: Bool { !busy && application != nil && !running }
    var canRunBulkAction: Bool { canChangeComponents }
    var installedConnectors: Set<InstallerClientKind> {
        Set(InstallerClientKind.allCases.filter { connectorStates[$0] == .installed })
    }
    var inspectorInstructions: String {
        let names = [("curve-inspector", "Curve Inspector"), ("reference-inspector", "Changes Against Reference")]
            .filter { installed.contains($0.0) }.map(\.1).joined(separator: " and ")
        return names.isEmpty ? "" : "In Glyphs’ View menu, enable " + names + "."
    }

    init() {
        refresh(resetFailures: true)
        let center = NSWorkspace.shared.notificationCenter
        for event in [NSWorkspace.didLaunchApplicationNotification, NSWorkspace.didTerminateApplicationNotification] {
            observers.append(center.addObserver(forName: event, object: nil, queue: .main) { [weak self] _ in
                Task { @MainActor in self?.refreshRunning() }
            })
        }
        Task { [weak self] in
            guard let self else { return }
            self.payload = try? InstallerPayload.resolve()
            self.refreshConnectorDetection()
        }
    }

    deinit {
        for observer in observers { NSWorkspace.shared.notificationCenter.removeObserver(observer) }
        task?.cancel()
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
        applications = GlyphsApplicationDetector.detect().filter { $0.majorVersion == .v4 }
        let installation = DesktopInstallation()
        installed = installation.components
        let receipt = root.appendingPathComponent("installation.json")
        receiptURL = fm.fileExists(atPath: receipt.path) ? receipt : nil
        for component in DesktopComponent.all {
            let current = componentStates[component.id]
            if resetFailures || !Self.preservesDuringRefresh(current) {
                componentStates[component.id] = installed.contains(component.id) ? .installed : .notInstalled
            }
        }
        refreshConnectorDetection(resetFailures: resetFailures)
        refreshRunning()
    }

    func refreshRunning() {
        running = application.map { target in
            NSWorkspace.shared.runningApplications.contains {
                $0.bundleURL?.standardizedFileURL == target.appURL.standardizedFileURL
            }
        } ?? false
        notice.glyphsRunningChanged(running)
    }

    func quitGlyphs() {
        guard !busy, let application else { return }
        busy = true
        Task {
            defer { busy = false }
            do {
                try await stopServiceBeforeQuit?()
                for app in NSWorkspace.shared.runningApplications
                    where app.bundleURL?.standardizedFileURL == application.appURL.standardizedFileURL {
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
        NSWorkspace.shared.openApplication(at: application.appURL, configuration: NSWorkspace.OpenConfiguration())
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
        record("Queued \(plan.count) Beta-3 setup items.")
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
        case .codex: return "Reload Codex after setup changes. MCP settings and managed skills are included."
        case .claudeCode: return "Restart Claude Code after setup changes. MCP settings and managed skills are included."
        case .claudeDesktop: return "Restart Claude Desktop after setup changes."
        case .cursor: return "Reload or restart Cursor to activate the local Glyphs MCP plug-in."
        }
    }

    func connectorSymbol(_ client: InstallerClientKind) -> String {
        switch client {
        case .codex: return "chevron.left.forwardslash.chevron.right"
        case .claudeCode: return "terminal"
        case .claudeDesktop: return "desktopcomputer"
        case .cursor: return "cursorarrow.rays"
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
        defer { busy = false }
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
        let connectorItems = queue.compactMap { item -> (InstallerClientKind, SetupOperation)? in
            if case .connector(let client, let operation) = item { return (client, operation) }
            return nil
        }
        for (client, operation) in connectorItems {
            connectorStates[client] = .active(operation)
            notice = .information("Configuring \(client.displayName)…")
            do {
                try await executeConnector(client, operation: operation)
                connectorStates[client] = .installed
                connectorVersions[client] = payload?.plugin(for: .v4).version.shortVersion ?? projectVersion
                record("Configured \(client.displayName).")
            } catch {
                connectorFailures += 1
                connectorStates[client] = .failed(operation, error.localizedDescription)
                record("\(client.displayName) failed: \(error.localizedDescription)")
            }
        }
        refreshPreservingOperationResults()
        notice = connectorFailures == 0
            ? .information("Setup is complete. Reload your connected apps and open Glyphs.")
            : .failure("Components installed; \(connectorFailures) connection\(connectorFailures == 1 ? "" : "s") need attention.")
    }

    private func performComponent(_ id: String, operation: SetupOperation) {
        refreshRunning()
        guard DesktopComponent.ids.contains(id), canChangeComponents else { return }
        busy = true
        componentStates[id] = .active(operation)
        notice = .information(operation.progressLabel.replacingOccurrences(of: "…", with: "") + " " + componentTitle(id) + "…")
        task = Task { [weak self] in
            guard let self else { return }
            defer { self.busy = false }
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
        guard !busy else { return }
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
                try await self.executeConnector(client, operation: operation)
                self.connectorStates[client] = operation == .remove ? .notInstalled : .installed
                if operation == .remove { self.connectorVersions.removeValue(forKey: client) }
                else { self.connectorVersions[client] = self.payload?.plugin(for: .v4).version.shortVersion ?? self.projectVersion }
                self.notice = .information("\(client.displayName) \(operation == .remove ? "removed" : "configured").")
                self.record("\(operation.rawValue.capitalized) completed for \(client.displayName).")
            } catch {
                self.connectorStates[client] = .failed(operation, error.localizedDescription)
                self.notice = .failure(error.localizedDescription)
                self.record("\(client.displayName) failed: \(error.localizedDescription)")
            }
        }
    }

    private func executeComponentTransaction(selected: Set<String>, only: String? = nil) async throws {
        guard let application else { throw InstallerError.userFacing("Glyphs 4 is required.") }
        let payload = try resolvePayload()
        let lean = payload.payloadDir.appendingPathComponent("Lean")
        #if arch(arm64)
        let architecture = "arm64"
        #else
        let architecture = "x86_64"
        #endif
        let python = lean.appendingPathComponent("runtimes/\(architecture)/bin/python3")
        let helper = payload.payloadDir.appendingPathComponent("Installer/install_simple_v2.py")
        var args = ["-B", helper.path, "--build", lean.path, "--glyphs-app", application.appURL.path, "--start"]
        if !selected.contains("mcp") { args.append("--no-mcp") }
        for id in selected.sorted() where id != "mcp" { args += ["--companion", id] }
        if let only { args += ["--only", only] }
        try await execute(python, args)
        receiptURL = root.appendingPathComponent("installation.json")
    }

    private func executeComponentRemoval(_ id: String) async throws {
        guard let application else { throw InstallerError.userFacing("Glyphs 4 is required.") }
        let payload = try resolvePayload()
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

    private func executeConnector(_ client: InstallerClientKind, operation: SetupOperation) async throws {
        let payload = try resolvePayload()
        let endpoint = DesktopInstallation().endpoint
        let logger: (String) -> Void = { [weak self] text in self?.appendLog(text) }
        let skills = AgentSkillBundleInstaller(log: logger)
        if operation == .remove {
            switch client {
            case .codex:
                try ConnectorConfigurationRemover.removeCodex(endpoint: endpoint)
                let result = try skills.removeOwnedSkills(from: payload, under: InstallerPaths.codexSkillsDir)
                try throwOnSkillConflicts(result)
            case .claudeCode:
                try ConnectorConfigurationRemover.removeClaude(client: .claudeCode, at: InstallerPaths.claudeCodeConfig,
                    serverName: InstallerConstants.claudeCodeServerName, endpoint: endpoint)
                let result = try skills.removeOwnedSkills(from: payload, under: InstallerPaths.claudeCodeSkillsDir)
                try throwOnSkillConflicts(result)
            case .claudeDesktop:
                try ConnectorConfigurationRemover.removeClaude(client: .claudeDesktop, at: InstallerPaths.claudeDesktopConfig,
                    serverName: InstallerConstants.claudeDesktopServerName, endpoint: endpoint)
            case .cursor:
                try makeCursorInstaller(payload, logger: logger).remove()
            }
            return
        }

        switch client {
        case .codex:
            try await CodexConfigurator(runner: runner, endpointURL: endpoint, log: logger).configure()
            try throwOnSkillConflicts(try skills.installCodexSkills(payload: payload, overwriteExisting: false))
        case .claudeCode:
            try await ClaudeCodeConfigurator(runner: runner, endpointURL: endpoint, log: logger).configureIfAvailable()
            try throwOnSkillConflicts(try skills.installClaudeCodeSkills(payload: payload, overwriteExisting: false))
        case .claudeDesktop:
            let proxy = [root.appendingPathComponent("runtime/bin/python3").path,
                         "-B", root.appendingPathComponent("sidecar/proxy.py").path]
            try ClaudeDesktopConfigurator(endpointURL: endpoint, proxyCommand: proxy, log: logger).configure()
        case .cursor:
            try makeCursorInstaller(payload, logger: logger).installOrUpdate()
        }
    }

    private func resolvePayload() throws -> InstallerPayload {
        if let payload { return payload }
        let resolved = try InstallerPayload.resolve()
        payload = resolved
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

    private func throwOnSkillConflicts(_ result: SkillInstallationResult) throws {
        guard !result.conflicts.isEmpty else { return }
        let paths = result.conflicts.map(\.path).joined(separator: "\n")
        throw InstallerError.userFacing("Modified or unowned skills were preserved:\n" + paths)
    }

    private func execute(_ executable: URL, _ args: [String]) async throws {
        let environment = ProcessInfo.processInfo.environment.merging([
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"
        ]) { _, new in new }
        let result = try await runner.runCapturing(executable: executable, args: args, environment: environment, timeout: 300)
        appendLog(result.stdout)
        appendLog(result.stderr)
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
        for (id, state) in componentResults where state.failureMessage != nil || state == .installed || state == .notInstalled {
            componentStates[id] = state
        }
        for (client, state) in connectorResults where state.failureMessage != nil || state == .installed || state == .notInstalled {
            connectorStates[client] = state
        }
    }

    private func componentTitle(_ id: String) -> String {
        DesktopComponent.all.first { $0.id == id }?.title ?? id
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
        case .notInstalled, .installed: return false
        }
    }
}
