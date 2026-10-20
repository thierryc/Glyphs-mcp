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
    @Published private(set) var setupRequested = false
    func requestSetup() { setupRequested = true }
    func consumeSetupRequest() { setupRequested = false }
    var onWelcome: (() -> Void)?
    func showWelcome() { onWelcome?() }
    @Published private(set) var tasks: [DesktopTask] = []
    private var taskIndex: [DesktopTaskReference] = []
    @Published private(set) var tasksNotice: String?
    @Published private(set) var taskHistoryNotice: String?
    @Published private(set) var tasksStale = false
    @Published private(set) var tasksLoading = false
    @Published private(set) var tasksObservedAt: Date?
    @Published private(set) var tasksNextCursor: Int?
    @Published private(set) var tasksRequested = false
    @Published private(set) var glyphsRunning = false
    private lazy var taskReadState = DesktopTaskReadState(defaults: .standard, namespace: installation.root.path)
    private lazy var taskHistoryState = DesktopTaskHistoryState(defaults: .standard, namespace: installation.root.path)
    var visibleTasks: [DesktopTask] { tasks.filter { taskHistoryState.isVisible($0) } }
    var canClearTaskHistory: Bool { taskIndex.contains { $0.closed && taskHistoryState.isVisible($0) } }
    var hasClearedTaskHistory: Bool { !taskHistoryState.clearedIDs.isEmpty }
    var unreadTaskCount: Int { taskIndex.filter { taskHistoryState.isVisible($0) && taskReadState.isUnread($0) }.count }
    func clearClosedTaskHistory() {
        objectWillChange.send()
        taskHistoryState.clearClosed(taskIndex)
        tasksNextCursor = nil
        Task { await refreshTasks() }
    }
    func restoreTaskHistory() {
        objectWillChange.send()
        taskHistoryState.restore()
        Task { await refreshTasks() }
    }
    func isUnread(_ task: DesktopTask) -> Bool { taskReadState.isUnread(task) }
    func readTask(_ task: DesktopTask) {
        guard taskReadState.isUnread(task) else { return }
        objectWillChange.send(); taskReadState.read(task)
    }
    func requestTasks() { tasksRequested = true }
    func consumeTasksRequest() { tasksRequested = false }

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
            hasNotice: !notice.isEmpty,
            stale: stale
        )
    }
    var needsGlyphsRecovery: Bool {
        DesktopDiagnostics.needsGlyphsRecovery(hasServer: installation.hasServer,
            running: serviceRunning, stale: stale, status: status, hasNotice: !notice.isEmpty)
    }
    var canControl: Bool { !controlling && !stale && status?.controlProtocol == 1 && status?.isBusy == false }
    var canChangeSettings: Bool { installation.hasServer && !controlling && (serviceRunning == false || canControl) }
    var tokenURL: URL { installation.tokenURL }

    init() {
        let center = NSWorkspace.shared.notificationCenter
        for event in [NSWorkspace.didLaunchApplicationNotification, NSWorkspace.didTerminateApplicationNotification, NSWorkspace.didActivateApplicationNotification] {
            observers.append(center.addObserver(forName: event, object: nil, queue: .main) { [weak self] _ in
                Task { @MainActor in
                    guard let self, self.visibility.visible || self.visibility.menuBarVisible || self.visibility.dashboardVisible else { return }
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
        updateEventMonitor()
        updateSampler()
        if visible { Task { await refresh() } }
    }
    var showsActivityDot: Bool { status?.showsActivityDot(stale: stale, running: serviceRunning) == true }

    func setMenuBarVisible(_ visible: Bool) {
        guard visible != visibility.menuBarVisible else { return }
        visibility.menuBarVisible = visible
        updateEventMonitor()
        updateSampler()
        if visible { Task { await refresh() } }
    }

    private func updateEventMonitor() {
        if visibility.menuBarVisible || visibility.dashboardVisible {
            if jobEvents == nil {
                jobEvents = DesktopJobEvents(root: installation.root) { [weak self] in self?.jobStateChanged() }
            }
        } else { jobEvents?.stop(); jobEvents = nil; eventPending = false }
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
        glyphsRunning = NSWorkspace.shared.runningApplications.contains { app in
            guard GlyphsRunningProcessDetector.supportedBundleIdentifiers.contains(app.bundleIdentifier ?? ""),
                  let url = app.bundleURL else { return false }
            return !GlyphsCopySelectionPolicy.copies(from: GlyphsApplicationDetector.allApplications(candidates: [url])).isEmpty
        }
        let current = DesktopInstallation()
        if current != installation {
            let changedRoot = current.root != installation.root
            installation = current
            if changedRoot {
                taskReadState = DesktopTaskReadState(defaults: .standard, namespace: current.root.path)
                taskHistoryState = DesktopTaskHistoryState(defaults: .standard, namespace: current.root.path)
                tasks = []; taskIndex = []; tasksObservedAt = nil; tasksNextCursor = nil
                tasksNotice = nil; tasksStale = false
                jobEvents?.stop(); jobEvents = nil; updateEventMonitor()
            }
        }
        guard current.hasServer else {
            status = nil; notice = ""; stale = false; serviceRunning = nil
            tasksStale = tasksObservedAt != nil
            tasksNotice = NSLocalizedString("Install Glyphs MCP in Setup to show Tasks.", comment: "Tasks prerequisite")
            return
        }
        do {
            let token = try String(contentsOf: tokenURL, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines)
            let request = DesktopStatusRequest.make(port: current.port, token: token)
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
            await refreshTasks()
            // Development links are mutable by design and use a lightweight
            // receipt without immutable payload fingerprints. Their explicit
            // Setup status is the trust signal; managed installs still require
            // the normal sidecar and bridge identity checks.
            notice = installation.isDevelopmentLinked ? "" : observed.identityIssues(
                expectedSidecar: installation.expectedSidecarHash,
                expectedBridge: installation.expectedBridgeHash
            ).joined(separator: "\n")
        } catch is CancellationError {
        } catch {
            guard !Task.isCancelled, !controlling else { return }
            tasksStale = tasksObservedAt != nil
            tasksNotice = NSLocalizedString("Tasks are unavailable. Try again when the server is connected.", comment: "Task inventory error")
            stale = status != nil
            if let observed = try? await serviceAction("status"), let data = observed["data"] as? [String: Any] {
                serviceRunning = data["processRunning"] as? Bool ?? data["running"] as? Bool
            } else { serviceRunning = nil }
            let message = DesktopDiagnostics.statusFailure(error, running: serviceRunning)
            if serviceRunning == false { notice = "" }
            else if notice != message { notice = message; remember(message) }
        }
    }

    func refreshTasks(loadMore: Bool = false) async {
        guard !tasksLoading, installation.hasServer, !controlling else { return }
        if loadMore && tasksNextCursor == nil { return }
        tasksLoading = true
        defer { tasksLoading = false }
        let root = installation.root
        do {
            await syncTaskHistory(root: root)
            guard root == installation.root, !controlling, !Task.isCancelled else { return }
            let token = try String(contentsOf: tokenURL, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines)
            let cursor = loadMore ? tasksNextCursor ?? 0 : 0
            var request = URLRequest(url: URL(string: "http://127.0.0.1:\(installation.port)/internal/tasks?cursor=\(cursor)")!)
            request.timeoutInterval = 3
            request.cachePolicy = .reloadIgnoringLocalCacheData
            request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
            let (data, response) = try await URLSession.shared.data(for: request)
            guard root == installation.root, !controlling, !Task.isCancelled else { return }
            let code = (response as? HTTPURLResponse)?.statusCode
            if code == 404 {
                tasksNotice = NSLocalizedString("Update Glyphs MCP to show Tasks.", comment: "Older task inventory")
                tasksStale = tasksObservedAt != nil
                return
            }
            guard code == 200 else { throw URLError(.badServerResponse) }
            struct Envelope: Decodable { let ok: Bool; let data: DesktopTaskPage? }
            let envelope = try JSONDecoder().decode(Envelope.self, from: data)
            guard envelope.ok, let page = envelope.data, page.version == 1 else { throw URLError(.cannotParseResponse) }
            tasks = page.mergingHistory(tasks)
            taskIndex = page.index ?? tasks.map(DesktopTaskReference.init)
            taskReadState.observeIndex(taskIndex)
            taskHistoryState.observeIndex(taskIndex, pruneMissing: page.index != nil)
            tasksNextCursor = page.nextHistoryCursor(in: tasks, ignoring: taskHistoryState.clearedIDs)
            tasksObservedAt = Date(timeIntervalSince1970: page.observedAt)
            tasksStale = false; tasksNotice = nil
        } catch {
            tasksStale = tasksObservedAt != nil
            tasksNotice = NSLocalizedString("Tasks are unavailable. Try again when the server is connected.", comment: "Task inventory error")
        }
    }

    private func syncTaskHistory(root: URL) async {
        guard !taskHistoryState.pendingOperations.isEmpty else { taskHistoryNotice = nil; return }
        do {
            let token = try String(contentsOf: tokenURL, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines)
            // Bound work per refresh; the persisted queue survives app shutdown.
            for _ in 0..<10 {
                guard let operation = taskHistoryState.pendingOperations.first else { break }
                var request = URLRequest(url: URL(string: "http://127.0.0.1:\(installation.port)/internal/task-history")!)
                request.httpMethod = "POST"; request.timeoutInterval = 5
                request.cachePolicy = .reloadIgnoringLocalCacheData
                request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                struct Payload: Encodable { let action: String; let records: [DesktopTaskHistoryState.Record] }
                request.httpBody = try JSONEncoder().encode(Payload(action: operation.action, records: operation.records))
                let (data, response) = try await URLSession.shared.data(for: request)
                guard root == installation.root, !controlling, !Task.isCancelled else { return }
                if (response as? HTTPURLResponse)?.statusCode == 404 {
                    taskHistoryNotice = NSLocalizedString("Update the sidecar to enable 30-day cleanup. History remains hidden.", comment: "History compatibility")
                    return
                }
                struct Envelope: Decodable { struct Result: Decodable { let version: Int }; let ok: Bool; let data: Result? }
                let envelope = try JSONDecoder().decode(Envelope.self, from: data)
                guard (response as? HTTPURLResponse)?.statusCode == 200, envelope.ok, envelope.data?.version == 1 else {
                    throw URLError(.badServerResponse)
                }
                taskHistoryState.acknowledge(operation)
            }
            taskHistoryNotice = taskHistoryState.pendingOperations.isEmpty ? nil : NSLocalizedString("History changes are waiting to sync.", comment: "History outbox")
        } catch {
            guard root == installation.root else { return }
            taskHistoryNotice = NSLocalizedString("History changes are waiting to sync. The 30-day period starts when the server receives Clear.", comment: "History offline")
        }
    }

    func taskRecovery(_ task: DesktopTask, choice: DesktopTaskRecovery.Action? = nil,
                      revision: Int? = nil) async throws -> DesktopTaskRecovery {
        guard let identity = task.workflowId ?? task.jobId else {
            throw InstallerError.userFacing("This task could not be identified. Refresh Tasks before choosing.")
        }
        guard installation.hasServer, !controlling else {
            throw InstallerError.userFacing("Connect to the server before using Recovery Options.")
        }
        let root = installation.root
        let identityKey = task.workflowId == nil ? "job_id" : "workflow_id"
        var payload: [String: Any] = ["action": "options", identityKey: identity]
        if let choice, let revision {
            payload = ["action": "respond", identityKey: identity,
                       "expected_revision": revision, "action_token": choice.token]
        }
        let token = try String(contentsOf: tokenURL, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines)
        var request = URLRequest(url: URL(string: "http://127.0.0.1:\(installation.port)/internal/task-recovery")!)
        request.httpMethod = "POST"; request.timeoutInterval = 30
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: payload)
        let (data, response) = try await URLSession.shared.data(for: request)
        guard root == installation.root, !Task.isCancelled else { throw CancellationError() }
        if (response as? HTTPURLResponse)?.statusCode == 404 {
            throw InstallerError.userFacing("Update the sidecar to use Recovery Options. You can still review this task in your agent.")
        }
        struct Failure: Decodable { let message: String }
        struct Envelope: Decodable { let ok: Bool; let data: DesktopTaskRecovery?; let error: Failure? }
        let result = try JSONDecoder().decode(Envelope.self, from: data)
        guard (response as? HTTPURLResponse)?.statusCode == 200, result.ok,
              let recovery = result.data,
              (task.workflowId != nil ? recovery.workflowId == identity : recovery.workflowId == nil && recovery.jobId == identity) else {
            throw InstallerError.userFacing(result.error?.message ?? "The task outcome could not be confirmed. Check again before choosing.")
        }
        if choice != nil { await refreshTasks() }
        return recovery
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
        guard canControl else { throw InstallerError.userFacing(!stale && status?.isBusy == true ? "Wait for the current font task to finish before closing Glyphs." : "The MCP server could not be stopped safely. Open Glyphs and finish any pending dialogs, then Refresh Setup. If it still fails, check the troubleshooting logs before changing components.") }
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
