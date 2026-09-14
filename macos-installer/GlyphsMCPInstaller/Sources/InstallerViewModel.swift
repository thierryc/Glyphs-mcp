import AppKit
import Foundation
import SwiftUI
import GlyphsMCPInstallerCore

@MainActor
final class InstallerViewModel: ObservableObject {
    enum Stage: String, CaseIterable { case choose = "Choose", install = "Install", ready = "Ready" }
    @Published var stage: Stage = .choose
    @Published var applications: [GlyphsApplicationInfo] = []
    @Published var selectedVersion: GlyphsMajorVersion = .v4
    @Published var components: Set<String> = ["mcp", "curve-inspector", "reference-inspector"]
    @Published var installed: Set<String> = []
    @Published var clients: Set<InstallerClientKind> = []
    @Published var detectedClients: [InstallerClientKind] = []
    @Published var notice: ComponentNotice = .none
    var message: String { notice.text }
    @Published var log = ""
    @Published var busy = false
    @Published var skillConflicts: [SkillInstallationResult.Entry] = []
    private var skillClients: Set<InstallerClientKind> = []
    private var skillPayload: InstallerPayload?
    @Published var troubleshooting = false
    @Published var running = false
    @Published var receiptURL: URL?
    @Published var updateStatus: PluginUpdateStatus = .idle
    var projectVersion: String { Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "unknown" }
    var versionLabel: String { DesktopIdentity.versionLabel }
    private var task: Task<Void, Never>?
    private var observers: [NSObjectProtocol] = []
    private let runner = ProcessRunner()
    private let fm = FileManager.default
    var stopServiceBeforeQuit: (() async throws -> Void)?
    private let root = InstallerPaths.home.appendingPathComponent("Library/Application Support/Glyphs MCP/lean-v2")

    var application: GlyphsApplicationInfo? { applications.first { $0.majorVersion == selectedVersion } }
    var componentPlan: DesktopComponentPlan { DesktopComponentPlan(installed: installed, selected: components) }
    var canInstall: Bool { !busy && application != nil && !running && (selectedVersion == .v3 || componentPlan.hasWork) }
    var canConnectClients: Bool { selectedVersion == .v3 || components.contains("mcp") }
    var completionTitle: String {
        if notice.isFailure { return "Components installed; AI connection needs attention" }
        return selectedVersion == .v4 && installed.isEmpty ? "Components removed" : "Components installed"
    }
    var inspectorInstructions: String {
        let commands = [("curve-inspector", "Curve Inspector"), ("reference-inspector", "Changes Against Reference")]
            .filter { installed.contains($0.0) }.map { $0.1 }.joined(separator: " and ")
        return commands.isEmpty ? "" : "In Glyphs’ View menu, enable " + commands + "."
    }
    var installButtonTitle: String { selectedVersion == .v4 && !installed.isEmpty ? "Apply Changes" : "Install" }

    init() {
        refresh()
        let center = NSWorkspace.shared.notificationCenter
        for event in [NSWorkspace.didLaunchApplicationNotification, NSWorkspace.didTerminateApplicationNotification] {
            observers.append(center.addObserver(forName: event, object: nil, queue: .main) { [weak self] _ in
                Task { @MainActor in self?.refreshRunning() }
            })
        }
    }

    deinit {
        for observer in observers { NSWorkspace.shared.notificationCenter.removeObserver(observer) }
    }

    func checkForUpdates() {
        guard updateStatus != .checking else { return }
        updateStatus = .checking
        Task {
            do { updateStatus = try await GitHubReleaseResolver.checkForUpdate(currentVersion: projectVersion) }
            catch { updateStatus = .error(message: "Couldn’t check for updates. Please try again.") }
        }
    }

    func refresh() {
        applications = GlyphsApplicationDetector.detect()
        if application == nil, let first = applications.first { selectedVersion = first.majorVersion }
        let path = root.appendingPathComponent("installation.json")
        if let data = try? Data(contentsOf: path), let receipt = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let names = receipt["components"] as? [String] {
            installed = Set(names).intersection(DesktopComponent.ids)
            components = DesktopComponentPlan.initialSelection(installed: installed, hasReceipt: true); receiptURL = path
        } else {
            let plugins = InstallerPaths.glyphsPluginsDir(glyphsVersion: .v4)
            installed = Set(Self.componentNames.filter { fm.fileExists(atPath: plugins.appendingPathComponent($0.bundle).path) }.map(\.id))
            components = DesktopComponentPlan.initialSelection(installed: installed, hasReceipt: false)
        }
        detectedClients = []
        if NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.openai.codex") != nil || fm.fileExists(atPath: InstallerPaths.home.appendingPathComponent(".codex").path) { detectedClients.append(.codex) }
        if NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.anthropic.claudefordesktop") != nil || fm.fileExists(atPath: InstallerPaths.claudeDesktopConfig.path) { detectedClients.append(.claudeDesktop) }
        if fm.fileExists(atPath: InstallerPaths.home.appendingPathComponent(".claude").path) { detectedClients.append(.claudeCode) }
        refreshRunning()
    }

    func refreshRunning() {
        running = application.map { app in NSWorkspace.shared.runningApplications.contains { $0.bundleURL?.standardizedFileURL == app.appURL.standardizedFileURL } } ?? false
        notice.glyphsRunningChanged(running)
    }

    func quitGlyphs() {
        guard !busy, let application else { return }
        busy = true
        Task {
            defer { busy = false }
            do {
                if selectedVersion == .v4 { try await stopServiceBeforeQuit?() }
                for app in NSWorkspace.shared.runningApplications where app.bundleURL?.standardizedFileURL == application.appURL.standardizedFileURL { app.terminate() }
                notice = .waitingForGlyphs
                refreshRunning()
            } catch { notice = .failure(error.localizedDescription) }
        }
    }

    func openGlyphs() {
        if let application { NSWorkspace.shared.openApplication(at: application.appURL, configuration: NSWorkspace.OpenConfiguration()) }
    }

    func componentBinding(_ id: String) -> Binding<Bool> {
        Binding(get: { self.components.contains(id) }, set: { selected in
            if selected { self.components.insert(id) }
            else { self.components.remove(id) }
        })
    }

    func prepareComponentChange(_ id: String, enabled: Bool) {
        guard !busy, DesktopComponent.ids.contains(id) else { return }
        refresh()
        selectedVersion = .v4; refreshRunning()
        components = installed
        if enabled { components.insert(id) } else { components.remove(id) }
        clients = []; notice = .none; stage = .choose
    }

    func clientBinding(_ client: InstallerClientKind) -> Binding<Bool> {
        Binding(get: { self.clients.contains(client) }, set: { selected in
            if selected { self.clients.insert(client) } else { self.clients.remove(client) }
        })
    }

    func install() {
        refreshRunning()
        guard canInstall, let application else { return }
        skillConflicts = []; skillClients = []; skillPayload = nil
        busy = true; stage = .install; notice = .information("Checking the installation…"); log = ""
        let plan = DesktopComponentPlan(installed: DesktopInstallation().components, selected: components)
        let chosen = plan.selected, connections = canConnectClients ? clients : []
        task = Task {
            var coreInstalled = false
            do {
                let payload = try await Task.detached { try InstallerPayload.resolve() }.value
                refreshRunning()
                guard !running else { throw InstallerError.userFacing("Close Glyphs, then try again.") }
                if selectedVersion == .v4 {
                    let lean = payload.payloadDir.appendingPathComponent("Lean")
                    #if arch(arm64)
                    let architecture = "arm64"
                    #else
                    let architecture = "x86_64"
                    #endif
                    let python = lean.appendingPathComponent("runtimes/\(architecture)/bin/python3")
                    let helper = payload.payloadDir.appendingPathComponent("Installer/install_simple_v2.py")
                    let base = ["-B", helper.path, "--build", lean.path, "--glyphs-app", application.appURL.path]
                    if !chosen.isEmpty { try await execute(python, base + ["--preflight-only"]) }
                    notice = .information("Applying component changes…")
                    let args = base + ["--start"] + plan.arguments
                    try await execute(python, args)
                    receiptURL = root.appendingPathComponent("installation.json")
                } else {
                    notice = .information("Installing Glyphs MCP 1.11.0 for Glyphs 3…")
                    try await installLegacy(payload)
                }
                coreInstalled = true
                if !connections.isEmpty && (selectedVersion == .v3 || chosen.contains("mcp")) {
                    notice = .information("Configuring AI connections…")
                    try await configureClients(connections, payload: payload.forGlyphsVersion(selectedVersion))
                }
                refresh()
                stage = .ready
                notice = .information(selectedVersion == .v4 && installed.isEmpty
                    ? "Your preferences have been kept."
                    : "Open Glyphs to load your components.")
            } catch {
                notice = .failure(error.localizedDescription)
                log += "\n" + error.localizedDescription
                stage = coreInstalled ? .ready : .choose
                if coreInstalled { refresh() }
            }
            busy = false
        }
    }

    private func execute(_ executable: URL, _ args: [String]) async throws {
        let result = try await runner.runCapturing(executable: executable, args: args,
            environment: ProcessInfo.processInfo.environment.merging(["PYTHONDONTWRITEBYTECODE":"1", "PYTHONNOUSERSITE":"1"]) { _, new in new }, timeout: 300)
        log += result.stdout + result.stderr
        guard result.exitCode == 0 else {
            let data = result.stdout.data(using: .utf8) ?? Data()
            let response = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            let detail = (response?["error"] as? [String: Any])?["message"] as? String
            throw InstallerError.userFacing(detail ?? (result.stderr.isEmpty ? result.stdout : result.stderr))
        }
    }

    private func installLegacy(_ payload: InstallerPayload) async throws {
        let preflight = await Task.detached { Preflight.scanGlyphs(glyphsVersion: .v3) }.value
        let status = GlyphsPythonResolver.resolve(preflight: preflight)
        guard let python = status.makeSelection() else { throw InstallerError.userFacing(status.installFailureReason ?? "Enable Python in Glyphs 3 first.") }
        let plugin = payload.plugin(for: .v3)
        let report = try await RuntimeProbeExecutor(runner: runner, log: { _ in }).check(
            python: python.pythonExecutable, probe: plugin.runtimeProbe,
            sitePackages: InstallerPaths.glyphsScriptsSitePackages(glyphsVersion: .v3), mode: .preinstall)
        guard let pathPlan = report.pathPlan else { throw InstallerError.userFacing("Glyphs 3 runtime check is incomplete.") }
        try await DepsInstaller(runner: runner, log: { _ in }).installAndVerify(python: python,
            requirementsTxt: payload.requirementsTxt, runtimeProbe: plugin.runtimeProbe, glyphsVersion: .v3, pathPlan: pathPlan)
        _ = try PluginInstaller(log: { _ in }).installPluginBundle(from: plugin.bundleURL,
            toPluginsDir: InstallerPaths.glyphsPluginsDir(glyphsVersion: .v3), allowReplace: true)
        try Glyphs3UpdatePinManager().pin()
    }

    private func configureClients(_ clients: Set<InstallerClientKind>, payload: InstallerPayload) async throws {
        let logger: (String) -> Void = { [weak self] text in self?.log += text + "\n" }
        skillPayload = payload
        let endpoint = selectedVersion == .v4 ? DesktopInstallation().endpoint : URL(string: "http://127.0.0.1:9680/mcp")!
        let proxy: [String]? = selectedVersion == .v4 ? [root.appendingPathComponent("runtime/bin/python3").path, "-B", root.appendingPathComponent("sidecar/proxy.py").path] : nil
        let skills = AgentSkillBundleInstaller(log: logger)
        for client in clients.sorted(by: { $0.rawValue < $1.rawValue }) {
            do {
                switch client {
                case .codex:
                    try await CodexConfigurator(runner: runner, endpointURL: endpoint, log: logger).configure()
                    recordSkills(try skills.installCodexSkills(payload: payload, overwriteExisting: false), client: client)
                case .claudeDesktop:
                    try ClaudeDesktopConfigurator(endpointURL: endpoint, proxyCommand: proxy, log: logger).configure()
                case .claudeCode:
                    try await ClaudeCodeConfigurator(runner: runner, endpointURL: endpoint, log: logger).configureIfAvailable()
                    recordSkills(try skills.installClaudeCodeSkills(payload: payload, overwriteExisting: false), client: client)
                }
            } catch {
                let name = client.displayName
                throw InstallerError.userFacing("Couldn’t configure \(name). \(error.localizedDescription)")
            }
        }
        if !skillConflicts.isEmpty { throw InstallerError.userFacing("AI connection configured; preserved skills need attention.\n" + skillConflicts.compactMap(\.repairAction).joined(separator: "\n")) }
    }

    private func recordSkills(_ result: SkillInstallationResult, client: InstallerClientKind) {
        skillConflicts += result.conflicts
        if !result.conflicts.isEmpty { skillClients.insert(client) }
    }

    func replacePreservedSkills() {
        guard !busy, let payload = skillPayload else { return }
        busy = true
        defer { busy = false }
        do {
            let installer = AgentSkillBundleInstaller(log: { [weak self] text in self?.log += text + "\n" })
            for client in skillClients.sorted(by: { $0.rawValue < $1.rawValue }) {
                if client == .codex { try installer.installCodexSkills(payload: payload, overwriteExisting: true) }
                if client == .claudeCode { try installer.installClaudeCodeSkills(payload: payload, overwriteExisting: true) }
            }
            skillConflicts = []; skillClients = []
            notice = .information("Skills updated. Replaced or retired skills were backed up outside the skill-discovery folder. See the log for exact paths.")
        } catch { notice = .failure(error.localizedDescription) }
    }

    static let componentNames = DesktopComponent.all
}
