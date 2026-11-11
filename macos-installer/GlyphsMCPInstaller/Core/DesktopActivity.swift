import Foundation

public struct DesktopActivity: Decodable, Equatable, Identifiable {
    public let jobId: String
    public let document: String
    public let kind: String
    public let phase: String
    public let startedAt: TimeInterval
    public let finishedAt: TimeInterval?
    public let completed: Int?
    public let total: Int?
    public let message: String?
    public var id: String { jobId }
    public var isBusy: Bool { ["copying_source", "preparing", "applying", "cancelling", "discarding"].contains(phase) }
    public var title: String {
        let name = taskName.prefix(1).uppercased() + taskName.dropFirst()
        let key: String
        let argument: String
        switch phase {
        case "copying_source": key = "Copying source for %@"; argument = taskName
        case "preparing": key = "Preparing %@"; argument = taskName
        case "ready": key = "%@ ready to review"; argument = name
        case "applying": key = "Applying %@"; argument = taskName
        case "applied": key = "%@ applied"; argument = name
        case "cancelling": key = "Cancelling %@"; argument = taskName
        case "discarding": key = "Reverting %@"; argument = taskName
        case "discarded": key = (completed ?? 0) > 0 ? "%@ reverted" : "%@ proposal discarded"; argument = name
        case "cancelled": key = "%@ cancelled"; argument = name
        case "interrupted": key = "%@ interrupted"; argument = name
        default: key = "%@ needs attention"; argument = name
        }
        return String(format: NSLocalizedString(key, comment: "Font task activity"), argument)
    }
    public var taskName: String {
        let key = ["spacing": "spacing", "width_delta": "width changes", "slant": "slant",
                   "kerning_collision": "kerning", "start_nodes": "start nodes"][kind] ?? "font changes"
        return NSLocalizedString(key, comment: "Font task name")
    }
    public var progressText: String? {
        guard let completed, let total, total > 0 else { return nil }
        if isBusy { return String(format: NSLocalizedString("%@ of %@ changes", comment: "Task progress"), completed.formatted(), total.formatted()) }
        guard completed > 0 else { return nil }
        return String(format: NSLocalizedString("%@ changes", comment: "Task change count"), completed.formatted())
    }
    public var detailMessage: String? {
        guard let message, !message.isEmpty else { return nil }
        let normalized = message.trimmingCharacters(in: .whitespacesAndNewlines).lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "."))
        let routine = ["job cancelled", "job canceled", "application was cancelled", "application was canceled", "preparation was cancelled", "preparation was canceled"]
        return phase == "cancelled" && routine.contains(normalized) ? nil : message
    }
}

/// The server supplies newest observations first. Keep separate jobs distinct,
/// but keep their history out of the main status surface.
public struct DesktopActivitySummary {
    public let jobs: [DesktopActivity]
    public let heading: String
    public let history: [DesktopActivity]
    public let additionalCount: Int
    public init(jobs observed: [DesktopActivity], activeCount: Int = 0) {
        let active = observed.filter(\.isBusy)
        let ready = observed.filter { $0.phase == "ready" }
        let candidates = !active.isEmpty ? active : !ready.isEmpty ? ready : Array(observed.prefix(1))
        jobs = Array(candidates.prefix(3))
        heading = !active.isEmpty ? "In progress" : !ready.isEmpty ? "Awaiting review" : "Last result"
        let selected = Set(jobs.map(\.id))
        history = observed.filter { !selected.contains($0.id) }
        additionalCount = max(0, (!active.isEmpty ? max(activeCount, active.count) : candidates.count) - jobs.count)
    }
}

public struct DesktopServerStatus: Decodable, Equatable {
    public struct Observation: Decodable, Equatable {
        public let stale: Bool
        public let ageSeconds: Double?
    }
    public struct Bridge: Decodable, Equatable {
        public let reachable: Bool
        public let activeOperations: Int?
        public var bridgeVersion: String? = nil
        public var codeHash: String? = nil
        public var runtimeId: String? = nil
        public var checking: Bool? = nil
    }
    public struct Worker: Decodable, Equatable {
        public struct Execution: Decodable, Equatable, Identifiable {
            public let jobId: String; public let pid: Int?; public let startedAt: TimeInterval; public let phase: String?
            public var id: String { jobId }
        }
        public let available: Bool
        public let executable: String?
        public let executions: [Execution]?
    }
    public struct Activity: Decodable, Equatable { public let jobs: [DesktopActivity]; public let activeCount: Int }
    public let sidecarVersion: String
    public let bridge: Bridge
    public let worker: Worker
    public let activity: Activity?
    public let controlProtocol: Int?
    public var codeHash: String? = nil
    public var runtimeId: String? = nil
    public var health: DesktopGlyphsHealth? = nil
    public var statusObservation: Observation? = nil
    public func identityIssues(expectedSidecar: String?, expectedBridge: String?) -> [String] {
        func check(_ component: String, _ expected: String?, _ reported: String?, _ recovery: String) -> String? {
            guard let expected, let reported,
                  expected.range(of: "^sha256:[0-9a-f]{64}$", options: .regularExpression) != nil,
                  reported.range(of: "^sha256:[0-9a-f]{64}$", options: .regularExpression) != nil else {
                return "\(component) identity unavailable: legacy or unreadable receipt/runtime evidence."
            }
            return expected == reported ? nil : "\(component) fingerprint differs from the installed receipt; the loaded process may be stale. \(recovery)"
        }
        var issues = [check("Sidecar", expectedSidecar, codeHash, "After jobs finish, stop and start the MCP service explicitly.")].compactMap { $0 }
        if bridge.reachable {
            if let issue = check("Bridge", expectedBridge, bridge.codeHash, "Resolve unsaved fonts, then reopen Glyphs to reload the bridge.") { issues.append(issue) }
        } else { issues.append("Bridge unreachable. Open Glyphs 4 → Edit → Glyphs MCP Server….") }
        return issues
    }
    public var isBusy: Bool {
        (activity?.activeCount ?? 0) > 0 || activity?.jobs.contains(where: \.isBusy) == true
            || (bridge.activeOperations ?? 0) > 0 || worker.executions?.isEmpty == false
    }
    public var summary: DesktopActivitySummary { DesktopActivitySummary(jobs: activity?.jobs ?? [], activeCount: activity?.activeCount ?? 0) }
    public func showsActivityDot(stale: Bool, running: Bool?) -> Bool { !stale && running == true && isBusy }
    public var title: String { bridge.checking == true ? "Checking Glyphs" : isBusy ? "Working" : bridge.reachable ? "Ready" : "Waiting for Glyphs" }
    public var workerTitle: String {
        if !worker.available { return "Worker unavailable" }
        if worker.executions?.contains(where: { $0.phase == "running" }) == true { return "Glyphs worker running" }
        return worker.executions?.isEmpty == false ? "Glyphs worker starting" : "Glyphs worker idle"
    }
}

/// Additive health evidence. Missing fields from older bridges remain unavailable.
public struct DesktopGlyphsHealth: Decodable, Equatable {
    public struct Signal: Decodable, Equatable {
        public let available: Bool?
        public let observedAt: TimeInterval?
        public let ageSeconds: Double?
        public let stale: Bool?
        public let complete: Bool?
        public let fontCount: Int?
        public let unsavedCount: Int?
        public let editTabCount: Int?
        public let bytes: Int64?
        public let growthBytes: Int64?
        public let growthWindowSeconds: Int?
        public let value: String?
        public let pendingSeconds: Double?
        public let schedulingSeconds: Double?
    }
    public let version: Int?
    public let available: Bool?
    public let bridgeSessionId: String?
    public let revision: Int?
    public let state: String
    public let signals: [String: Signal]?
    public let reasons: [String]?
    public var pressureTitle: String {
        guard let pressure = signals?["pressure"], pressure.available == true else {
            return "System memory pressure is unknown."
        }
        switch pressure.value {
        case "normal": return "Mac memory pressure is normal"
        case "warning": return "Mac memory pressure is elevated"
        case "critical": return "Mac memory pressure is critical"
        default: return "System memory pressure is unknown."
        }
    }
    public var readinessTitle: String {
        if reasons?.contains(where: { $0 == "native_dispatch_slow" || $0 == "native_dispatch_delayed" }) == true {
            return "Native response delayed"
        }
        guard let dispatch = signals?["dispatch"], dispatch.available == true, dispatch.stale != true,
              let duration = dispatch.schedulingSeconds, (0...2).contains(duration) else {
            return "Glyphs responsiveness unconfirmed"
        }
        let elapsed = dispatch.observedAt.map { Date().timeIntervalSince1970 - $0 }
        let age = max(dispatch.ageSeconds ?? 0, elapsed ?? 0)
        return (dispatch.ageSeconds != nil || elapsed != nil) && age <= 60
            ? "Glyphs is responsive" : "Last Glyphs response was timely"
    }
    public var title: String {
        guard available == true, version == 1 else { return "Health unavailable" }
        switch state {
        case "normal": return "No slowdown detected"
        case "caution": return "Reduce load"
        case "paused": return "New heavy work paused"
        default: return "Health unknown"
        }
    }
    public var agentGuidance: String {
        if state == "paused" {
            return "Agents defer new expensive work and retry later. Existing work and recovery are preserved."
        }
        if reasons?.contains("native_dispatch_slow") == true {
            return "Wait for the current operation before starting another."
        }
        if reasons?.contains("memory_pressure_warning") == true {
            return "Continue routine edits. Run large imports, exports, comparisons and whole-font snapshots one at a time."
        }
        if reasons?.contains("font_budget_reached") == true {
            return "Reuse open fonts when possible."
        }
        return "Agents follow health advisories returned by tools."
    }
    public static func reasonLabel(_ reason: String) -> String {
        switch reason {
        case "font_budget_reached": return "Open-font warning threshold reached"
        case "memory_pressure_warning": return "System memory pressure elevated"
        case "memory_pressure_critical": return "System memory pressure critical"
        case "native_dispatch_slow", "native_dispatch_delayed": return "Native response delayed"
        case "recovering": return "Waiting for sustained recovery"
        default: return "Health evidence incomplete"
        }
    }
}

public struct DesktopGlyphsFootprint {
    public enum Level: Equatable {
        case light, moderate, heavy

        public var title: String {
            switch self {
            case .light: return "Light Glyphs footprint"
            case .moderate: return "Moderate Glyphs footprint"
            case .heavy: return "Heavy Glyphs footprint"
            }
        }
    }

    public let installedBytes: Int64
    public let fraction: Double

    public init?(bytes: Int64, installedMemory: UInt64) {
        guard bytes >= 0, installedMemory > 0, let installedBytes = Int64(exactly: installedMemory) else { return nil }
        self.installedBytes = installedBytes
        fraction = Double(bytes) / Double(installedBytes)
    }

    public var level: Level {
        // These bands describe Glyphs' share of RAM. macOS supplies the pressure signal separately.
        if fraction < 0.05 { return .light }
        if fraction < 0.15 { return .moderate }
        return .heavy
    }
}

public struct DesktopGlyphsHealthPolicy: Codable, Equatable {
    public var version = 1
    public var fontWarningThreshold: Int?
    public init(fontWarningThreshold: Int? = nil) { self.fontWarningThreshold = fontWarningThreshold }
    public static func file(under root: URL) -> URL { root.appendingPathComponent("jobs/health-policy.json") }
    public static func read(under root: URL) throws -> Self {
        let file = file(under: root)
        guard FileManager.default.fileExists(atPath: file.path) else { return Self() }
        let policy = try JSONDecoder().decode(Self.self, from: Data(contentsOf: file))
        guard policy.version == 1, let threshold = policy.fontWarningThreshold, (1...128).contains(threshold)
        else { throw CocoaError(.coderReadCorrupt) }
        return policy
    }
    public func write(under root: URL) throws {
        guard version == 1 else { throw CocoaError(.coderInvalidValue) }
        let file = Self.file(under: root)
        guard let fontWarningThreshold else {
            do { try FileManager.default.removeItem(at: file) }
            catch let error as CocoaError where error.code == .fileNoSuchFile { }
            return
        }
        guard (1...128).contains(fontWarningThreshold) else { throw CocoaError(.coderInvalidValue) }
        try FileManager.default.createDirectory(at: file.deletingLastPathComponent(), withIntermediateDirectories: true)
        try JSONEncoder().encode(self).write(to: file, options: .atomic)
    }
}

public enum DesktopStatusRequest {
    public static func make(port: Int, token: String) -> URLRequest {
        var request = URLRequest(url: URL(string: "http://127.0.0.1:\(port)/internal/status")!)
        // Current sidecars return a passive cache immediately. Retain the
        // compatibility timeout for older installed sidecars.
        request.timeoutInterval = 20
        request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        request.cachePolicy = .reloadIgnoringLocalCacheData
        return request
    }
}

public enum DesktopDiagnostics {
    public enum StatusTone { case ready, active, unavailable }

    public static func statusTone(running: Bool?, stale: Bool, status: DesktopServerStatus?) -> StatusTone {
        guard running == true, !stale else { return .unavailable }
        guard let status, status.bridge.reachable, status.bridge.checking != true, !status.isBusy else { return .active }
        return .ready
    }

    public static func serverTitle(
        hasServer: Bool,
        running: Bool?,
        status: DesktopServerStatus?,
        hasNotice: Bool,
        stale: Bool = false
    ) -> String {
        if !hasServer { return "MCP server not installed" }
        if running == false { return "Server stopped" }
        if stale { return "Status unavailable" }
        if let status { return status.title }
        if running == true { return "Server running" }
        return hasNotice ? "Server unavailable" : "Checking server"
    }

    public static func needsGlyphsRecovery(hasServer: Bool, running: Bool?, stale: Bool,
                                          status: DesktopServerStatus?, hasNotice: Bool) -> Bool {
        // A failed HTTP refresh says nothing about Glyphs startup dialogs.
        // Only a fresh bridge check can support that recovery advice.
        guard hasServer, running != false, !stale else { return false }
        return status?.bridge.reachable == false
    }

    public static func statusFailure(_ error: Error, running: Bool?) -> String {
        guard let error = error as? URLError else { return error.localizedDescription }
        if error.code == .timedOut {
            return NSLocalizedString(running == true
                ? "The server is running, but its status check took too long. Refresh Setup or open Troubleshooting Logs."
                : "The status check took too long. Refresh Setup or open Troubleshooting Logs.", comment: "Status timeout")
        }
        return NSLocalizedString("Could not read the server status. Refresh Setup or open Troubleshooting Logs.", comment: "Status connection failure")
    }

    public static func statusFailure(_ code: Int?) -> String {
        if code == 401 || code == 403 { return "The MCP server rejected this app’s connection. Check authentication in Troubleshooting." }
        return "The MCP server could not report its activity. Try Refresh or open Troubleshooting."
    }

    public static func controlProgress(_ action: String?) -> String? {
        guard let action else { return nil }
        switch action {
        case "start": return "Starting…"
        case "stop": return "Stopping…"
        default: return "Applying…"
        }
    }

    public static func statusSymbol(running: Bool?, stale: Bool, status: DesktopServerStatus?) -> String {
        if running == false { return "stop.circle" }
        if stale { return "exclamationmark.circle" }
        guard let status else { return "circle" }
        if status.isBusy { return "ellipsis.circle" }
        return status.bridge.reachable ? "checkmark.circle.fill" : "circle"
    }

    public static func redact(_ text: String, secrets: [String] = []) -> String {
        var result = String(text.suffix(16_000))
        for secret in secrets where !secret.isEmpty { result = result.replacingOccurrences(of: secret, with: "[redacted]") }
        for pattern in [#"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"#,
                        #"(?i)((?:token|password|secret|authorization)[\"']?\s*[:=]\s*[\"']?)[^\s\"',}]+"#] {
            result = result.replacingOccurrences(of: pattern, with: "$1[redacted]", options: .regularExpression)
        }
        return result
    }
}
