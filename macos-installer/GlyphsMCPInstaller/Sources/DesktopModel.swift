import AppKit
import Foundation
import SwiftUI
import GlyphsMCPInstallerCore

@MainActor
final class DesktopModel: ObservableObject {
    @Published private(set) var installation = DesktopInstallation()
    @Published private(set) var status: DesktopServerStatus?
    @Published private(set) var lastObserved: Date?
    @Published private(set) var notice = ""
    @Published private(set) var stale = false
    @Published private(set) var controlAction: String?
    var controlling: Bool { controlAction != nil }
    var controlProgress: String? { DesktopDiagnostics.controlProgress(controlAction) }
    var statusSymbol: String { DesktopDiagnostics.statusSymbol(running: serviceRunning, stale: stale, status: status) }
    var activityNotice: String? {
        guard stale else { return nil }
        return serviceRunning == false ? "Last result from before the server stopped." : "Activity unavailable · showing the last observation"
    }
    @Published private(set) var serviceRunning: Bool?
    @Published private(set) var recentMessages: [String] = []
    var onWelcome: (() -> Void)?
    func showWelcome() { onWelcome?() }
    private var visibility = DesktopMonitorPolicy()
    private var sampler: Task<Void, Never>?
    private var refreshing = false
    private var jobEvents: DesktopJobEvents?
    private var eventPending = false
    private var lastAttempt = ContinuousClock.now
    private let runner = ProcessRunner()
    private var observers: [NSObjectProtocol] = []

    var title: String {
        DesktopDiagnostics.serverTitle(
            hasServer: installation.hasServer,
            running: serviceRunning,
            status: status,
            hasNotice: !notice.isEmpty
        )
    }
    var canControl: Bool { !controlling && !stale && status?.controlProtocol == 1 && status?.isBusy == false }
    var canChangeSettings: Bool { installation.hasServer && !controlling && (serviceRunning == false || canControl) }
    var tokenURL: URL { installation.tokenURL }

    init() {
        let center = NSWorkspace.shared.notificationCenter
        for event in [NSWorkspace.didLaunchApplicationNotification, NSWorkspace.didTerminateApplicationNotification, NSWorkspace.didActivateApplicationNotification] {
            observers.append(center.addObserver(forName: event, object: nil, queue: .main) { [weak self] _ in
                Task { @MainActor in
                    guard let self, self.visibility.visible || self.visibility.menuBarVisible else { return }
                    await self.refresh()
                }
            })
        }
    }
    deinit {
        sampler?.cancel()
        for observer in observers { NSWorkspace.shared.notificationCenter.removeObserver(observer) }
    }

    func setVisible(_ surface: String, _ visible: Bool) {
        if visible { visibility.surfaces.insert(surface) } else { visibility.surfaces.remove(surface) }
        updateSampler()
        if visible { Task { await refresh() } }
    }
    func setDashboardVisible(_ visible: Bool) {
        visibility.dashboardVisible = visible
        updateSampler()
        if visible { Task { await refresh() } }
    }
    var showsActivityDot: Bool { status?.showsActivityDot(stale: stale, running: serviceRunning) == true }

    func setMenuBarVisible(_ visible: Bool) {
        guard visible != visibility.menuBarVisible else { return }
        visibility.menuBarVisible = visible
        if visible {
            jobEvents = DesktopJobEvents(root: installation.root) { [weak self] in
                self?.jobStateChanged()
            }
            Task { await refresh() }
        } else { jobEvents?.stop(); jobEvents = nil; eventPending = false }
        updateSampler()
    }

    private func jobStateChanged() {
        // Status reconciliation can itself persist native progress. While busy,
        // the existing two-second sampler covers those events without feedback.
        if showsActivityDot && sampler != nil && !refreshing { return }
        eventPending = true
        updateSampler()
    }

    private func updateSampler() {
        guard !refreshing else { return }
        sampler?.cancel(); sampler = nil
        let regular = visibility.interval(busy: showsActivityDot)
        guard regular != nil || eventPending else { return }
        // Coalesce notifications and keep requests at least two seconds apart.
        // Idle, hidden surfaces use no recurring timer at all.
        let since = lastAttempt.duration(to: .now)
        let delay: Duration = eventPending ? max(.milliseconds(200), .seconds(2) - since) : .seconds(regular!)
        sampler = Task { [weak self] in
            do { try await Task.sleep(for: delay) } catch { return }
            guard let self, !Task.isCancelled else { return }
            self.sampler = nil
            await self.refresh()
        }
    }

    func refresh() async {
        guard !refreshing else { return }
        // A control request can outlast the pending timer. Keep the monitor
        // scheduled while the shared control helper owns the service.
        guard !controlling else { updateSampler(); return }
        sampler?.cancel(); sampler = nil
        eventPending = false; lastAttempt = .now
        refreshing = true
        defer { refreshing = false; updateSampler() }
        let current = DesktopInstallation()
        if current != installation { installation = current }
        guard current.hasServer else { status = nil; notice = ""; stale = false; serviceRunning = nil; return }
        do {
            let token = try String(contentsOf: tokenURL, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines)
            var request = URLRequest(url: URL(string: "http://127.0.0.1:\(current.port)/internal/status")!)
            request.timeoutInterval = 3
            request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
            request.cachePolicy = .reloadIgnoringLocalCacheData
            let (data, response) = try await URLSession.shared.data(for: request)
            guard !controlling, !Task.isCancelled else { return }
            guard (response as? HTTPURLResponse)?.statusCode == 200 else {
                let code = (response as? HTTPURLResponse)?.statusCode
                remember("Activity request: HTTP \(code.map(String.init) ?? "unknown").")
                throw InstallerError.userFacing(DesktopDiagnostics.statusFailure(code))
            }
            let object = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            guard object?["ok"] as? Bool == true, let payload = object?["data"] else {
                throw InstallerError.userFacing("The server could not report its current activity.")
            }
            let observed = try JSONDecoder().decode(DesktopServerStatus.self, from: JSONSerialization.data(withJSONObject: payload))
            if observed != status {
                let old = Dictionary(uniqueKeysWithValues: (status?.activity?.jobs ?? []).map { ($0.jobId, $0.phase) })
                for job in observed.activity?.jobs ?? [] where old[job.jobId] != job.phase {
                    remember("\(job.jobId): \(job.title)\(job.message.map { " — " + $0 } ?? "")")
                }
                status = observed
            }
            lastObserved = Date(); stale = false; serviceRunning = true
            notice = observed.identityIssues(expectedSidecar: installation.expectedSidecarHash,
                expectedBridge: installation.expectedBridgeHash).joined(separator: "\n")
        } catch is CancellationError {
        } catch {
            guard !Task.isCancelled, !controlling else { return }
            stale = status != nil
            let message = (error as? URLError) != nil ? "The server is not responding. Refresh Setup or open the troubleshooting logs." : error.localizedDescription
            if let observed = try? await serviceAction("status"), let data = observed["data"] as? [String: Any] {
                serviceRunning = data["processRunning"] as? Bool ?? data["running"] as? Bool
            } else { serviceRunning = nil }
            if serviceRunning == false { notice = "" }
            else if notice != message { notice = message; remember(message) }
        }
    }

    private func serviceAction(_ action: String, value: String? = nil) async throws -> [String: Any] {
        guard let python = installation.python else { throw InstallerError.userFacing("The MCP server is not installed.") }
        var args = ["-I", "-B", installation.root.appendingPathComponent("sidecar/control.py").path, action]
        if let value { args.append(value) }
        let result = try await runner.runCapturing(executable: python, args: args, timeout: 35)
        let object = try JSONSerialization.jsonObject(with: Data(result.stdout.utf8)) as? [String: Any]
        guard result.exitCode == 0, object?["ok"] as? Bool == true, let object else {
            throw InstallerError.userFacing(object?["error"] as? String ?? "The MCP server action could not complete.")
        }
        return object
    }

    func stopForInstallation() async throws {
        guard !controlling else { throw InstallerError.userFacing("A service control is already in progress.") }
        await refresh()
        guard installation.hasServer, serviceRunning != false else { return }
        guard canControl else { throw InstallerError.userFacing(status?.isBusy == true ? "Wait for the current font task to finish before closing Glyphs." : "The MCP server could not be stopped safely. Open Setup and check the troubleshooting logs before changing components.") }
        controlAction = "stop"
        defer { controlAction = nil }
        _ = try await serviceAction("stop")
        serviceRunning = false; stale = status != nil
    }

    func control(_ action: String, value: String? = nil) {
        guard !controlling, installation.python != nil else { return }
        controlAction = action; notice = ""
        Task {
            do {
                let result = try await serviceAction(action, value: value)
                let data = result["data"] as? [String: Any]
                serviceRunning = data?["processRunning"] as? Bool ?? data?["running"] as? Bool
                if action == "stop" { stale = status != nil }
                installation = DesktopInstallation()
            } catch { notice = error.localizedDescription; remember(notice); controlAction = nil; return }
            controlAction = nil
            if action != "stop" { await refresh() }
        }
    }

    private func remember(_ message: String) {
        let bounded = String(message.prefix(500))
        if recentMessages.last?.hasSuffix(bounded) == true { return }
        recentMessages.append(Date().formatted(date: .omitted, time: .standard) + " " + bounded)
        recentMessages = Array(recentMessages.suffix(20))
    }

    func copyDiagnostics() {
        let token = (try? String(contentsOf: tokenURL, encoding: .utf8))?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let details = "Glyphs MCP \(Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") ?? "unknown")\nInstalled components: \(installation.version ?? "unknown") (bridge \(status?.bridge.bridgeVersion ?? "unavailable"))\n\(title)\n\(notice)\nComponents: \(installation.components.sorted().joined(separator: ", "))\nSidecar identity: \(status?.runtimeId ?? "unavailable") \(status?.codeHash ?? "unavailable")\nBridge identity: \(status?.bridge.runtimeId ?? "unavailable") \(status?.bridge.codeHash ?? "unavailable")\nMCP endpoint: \(installation.endpoint)\nPython: \(installation.python?.path ?? "unavailable")\nWorker: \(status?.worker.executable ?? "unavailable")\nLast observation: \(lastObserved?.description ?? "none")\n\(recentMessages.joined(separator: "\n"))"
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(DesktopDiagnostics.redact(details, secrets: [token]), forType: .string)
    }
}
