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
        switch phase {
        case "copying_source": return "Copying source for \(taskName)"
        case "preparing": return "Preparing \(taskName)"
        case "ready": return "\(name) ready to review"
        case "applying": return "Applying \(taskName)"
        case "applied": return "\(name) applied"
        case "cancelling": return "Cancelling \(taskName)"
        case "discarding": return "Reverting \(taskName)"
        case "discarded": return (completed ?? 0) > 0 ? "\(name) reverted" : "\(name) proposal discarded"
        case "cancelled": return "\(name) cancelled"
        case "interrupted": return "\(name) interrupted"
        default: return "\(name) needs attention"
        }
    }
    public var taskName: String {
        ["spacing": "spacing", "width_delta": "width changes", "slant": "slant",
         "kerning_collision": "kerning", "start_nodes": "start nodes"][kind] ?? "font changes"
    }
    public var progressText: String? {
        guard let completed, let total, total > 0 else { return nil }
        if isBusy { return "\(completed.formatted()) of \(total.formatted()) changes" }
        guard completed > 0 else { return nil }
        return "\(completed.formatted()) changes"
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
    public struct Bridge: Decodable, Equatable {
        public let reachable: Bool
        public let activeOperations: Int?
        public var bridgeVersion: String? = nil
        public var codeHash: String? = nil
        public var runtimeId: String? = nil
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
    public var title: String { isBusy ? "Working" : bridge.reachable ? "Ready" : "Waiting for Glyphs" }
    public var workerTitle: String {
        if !worker.available { return "Worker unavailable" }
        if worker.executions?.contains(where: { $0.phase == "running" }) == true { return "Glyphs worker running" }
        return worker.executions?.isEmpty == false ? "Glyphs worker starting" : "Glyphs worker idle"
    }
}

public enum DesktopDiagnostics {
    public static func serverTitle(
        hasServer: Bool,
        running: Bool?,
        status: DesktopServerStatus?,
        hasNotice: Bool
    ) -> String {
        if !hasServer { return "MCP server not installed" }
        if running == false { return "Server stopped" }
        if let status { return status.title }
        if running == true { return "Server running" }
        return hasNotice ? "Server unavailable" : "Checking server"
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
