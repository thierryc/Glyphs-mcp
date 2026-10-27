import Foundation

public enum DesktopTaskPromptIntent: String, CaseIterable, Identifiable {
    case review, closeTask
    public var id: String { rawValue }
    public var label: String { self == .review ? "Review" : "Close task" }
}

public struct DesktopTaskRecovery: Decodable, Equatable {
    public struct Action: Decodable, Equatable, Identifiable {
        public let action: String
        public let label: String
        public let consequence: String
        public let token: String
        public var id: String { action }
        public var isCancellation: Bool { action == "cancel" || action == "discard" }
    }
    public let workflowId: String?
    public let jobId: String?
    public let revision: Int
    public let state: String
    public let documentName: String
    public let path: String?
    public let message: String
    public let warning: String?
    public let closed: Bool
    public let pending: Bool
    public let receipt: String?
    public let actions: [Action]
    public var statusLabel: String {
        if state == "expired" { return "Expired" }
        if state == "archived" { return "Unverified" }
        if closed { return "Closed" }
        if pending { return "Cancellation pending" }
        switch state {
        case "interrupted": return "Interrupted"
        case "uncertain": return "Outcome unknown"
        case "applying", "preparing", "saving", "resolving": return "Running"
        default: return "Needs decision"
        }
    }
    public var closingActions: [Action] {
        guard !closed else { return [] }
        return actions.filter { ["finish_script", "finish_edit", "cancel", "discard"].contains($0.action)
            || ($0.action == "archive_interrupted" && workflowId == nil && jobId != nil && state == "interrupted") }
    }
}

public struct DesktopTask: Decodable, Equatable, Identifiable {
    public struct Blocker: Decodable, Equatable, Identifiable {
        public let jobId: String?
        public let taskId: String?
        public let workflowId: String?
        public let documentId: String?
        public let documentName: String
        public let scope: String
        public let reason: String
        public let wait: String
        public let message: String
        public var id: String { taskId ?? jobId ?? documentName }
    }
    public struct Origin: Decodable, Equatable {
        public let agent: String
        public let conversationId: String
        public let conflict: Bool?
    }
    public let id: String
    public let workflowId: String?
    public let jobId: String?
    public let title: String
    public let documentName: String
    public let path: String?
    public let state: String
    public let closed: Bool
    public let createdAt: TimeInterval
    public let updatedAt: TimeInterval
    public let historyRevision: String?
    public let message: String?
    public let saveStatus: String?
    public let supportText: String?
    public let outcome: String?
    public let checkpointWarning: String?
    public let progress: Int?
    public let total: Int?
    public let origin: Origin?
    public let blockedBy: [String]
    public let blocking: [String]
    public let taskStatus: String?
    public let recoveryStatus: String?
    public let outcomeLabel: String?
    public let blockers: [Blocker]?
    public let expiredAt: TimeInterval?

    public var startedDate: Date? { Self.validDate(createdAt) }
    public var lastActivityDate: Date? {
        guard let updated = Self.validDate(updatedAt) else { return startedDate }
        return startedDate.map { max($0, updated) } ?? updated
    }
    public var expirationDate: Date? { expiredAt.flatMap(Self.validDate) }
    private static func validDate(_ timestamp: TimeInterval) -> Date? {
        guard timestamp.isFinite, timestamp > 0,
              timestamp <= Date.distantFuture.timeIntervalSince1970 else { return nil }
        return Date(timeIntervalSince1970: timestamp)
    }

    // Presentation is independent of closure: a finished task may retain recovery.
    public var displayStatus: String {
        if let taskStatus { return taskStatus }
        if closed { return "finished" }
        if state == "running" { return "working" }
        return "needs_attention"
    }
    public var taskGroup: String {
        switch displayStatus {
        case "working", "waiting": return "active"
        case "finished": return "finished"
        default: return "attention"
        }
    }
    public var rowStatusLabel: String? { state == "expired" ? "Expired" : taskGroup == "finished" ? outcomeLabel ?? statusLabel : statusLabel }
    public var recoveryAvailable: Bool { recoveryStatus == "available" }
    public var taskActionLabel: String {
        state == "unknown" || state == "interrupted" ? "Check result…" : "Task actions…"
    }

    public var agentName: String? {
        switch origin?.agent { case "codex": return "Codex"; case "claude_code": return "Claude Code"; default: return nil }
    }
    public var conversationURL: URL? {
        guard origin?.agent == "codex", origin?.conflict != true,
              let identity = origin?.conversationId, UUID(uuidString: identity) != nil else { return nil }
        return URL(string: "codex://threads/" + identity)
    }
    public var conversationUnavailableMessage: String? {
        guard conversationURL == nil else { return nil }
        if origin?.conflict == true {
            return "The conversation could not be identified reliably. Copy the prompt into your agent."
        }
        if origin?.agent == "claude_code" {
            return "A direct Claude Code conversation link is unavailable. Copy the prompt into your agent."
        }
        return "No usable conversation link was captured for this task. Copy the prompt into your agent."
    }
    public var statusLabel: String? {
        if state == "expired" { return "Expired" }
        if taskStatus != nil {
            switch displayStatus {
            case "working": return "Working"
            case "waiting": return "Waiting"
            case "finished": return "Finished"
            default: return "Needs attention"
            }
        }
        switch state {
        case "running": return "Running"
        case "needs_decision": return "Needs decision"
        case "blocked": return "Blocked"
        case "unknown": return "Outcome unknown"
        case "interrupted": return "Interrupted"
        case "archived": return "Unverified"
        case "failed": return "Failed"
        default: return nil
        }
    }
    public func prompt(for intent: DesktopTaskPromptIntent) -> String {
        guard intent == .closeTask else { return copyRequest }
        return """
        Help me close Glyphs MCP task \(workflowId ?? jobId ?? id) for \(documentName): \(title).

        Retrieve its current state and blockers. Explain its existing cancellation and recovery choices, including any Keep, Save, Undo, or Restore decision required. If running, explain cancellation limits. Show only currently available actions and wait for my choice.

        Do not rerun the script or automatically cancel, save, restore, or close the task. Keep all workflow decisions in this conversation.
        """
    }
    public var copyRequest: String {
        "Review Glyphs MCP task \(workflowId ?? jobId ?? id) for \(documentName): \(title). Retrieve its current state and blockers, then show the existing available choices in this conversation. Do not repeat the script or automatically save, restore, or close the task."
    }
}

public struct DesktopTaskExpiryPolicy: Codable, Equatable {
    public var version = 1
    public var inactivityDays = 1
    public init(inactivityDays: Int = 1) { self.inactivityDays = inactivityDays }
    public static func file(under root: URL) -> URL { root.appendingPathComponent("jobs/task-policy.json") }
    public static func read(under root: URL) throws -> Self {
        let file = file(under: root)
        guard FileManager.default.fileExists(atPath: file.path) else { return Self() }
        let policy = try JSONDecoder().decode(Self.self, from: Data(contentsOf: file))
        guard policy.version == 1, (1...365).contains(policy.inactivityDays) else {
            throw CocoaError(.coderReadCorrupt)
        }
        return policy
    }
    public func write(under root: URL) throws {
        guard version == 1, (1...365).contains(inactivityDays) else { throw CocoaError(.coderInvalidValue) }
        let file = Self.file(under: root)
        try FileManager.default.createDirectory(at: file.deletingLastPathComponent(), withIntermediateDirectories: true)
        try JSONEncoder().encode(self).write(to: file, options: .atomic)
    }
}

public struct DesktopTaskReference: Decodable, Equatable {
    public let id: String
    public let createdAt: TimeInterval
    public let closed: Bool
    public let historyRevision: String?
    public init(task: DesktopTask) {
        id = task.id; createdAt = task.createdAt; closed = task.closed; historyRevision = task.historyRevision
    }
}

public struct DesktopTaskPage: Decodable, Equatable {
    public let version: Int
    public let observedAt: TimeInterval
    public let tasks: [DesktopTask]
    public let nextCursor: Int?
    public let index: [DesktopTaskReference]?

    public func mergingHistory(_ previous: [DesktopTask]) -> [DesktopTask] {
        let identities = index.map { Set($0.map(\.id)) }
        var merged = Dictionary(uniqueKeysWithValues: previous.filter {
            $0.closed && (identities?.contains($0.id) ?? true)
        }.map { ($0.id, $0) })
        for task in tasks { merged[task.id] = task }
        return merged.values.sorted {
            $0.updatedAt == $1.updatedAt ? $0.id > $1.id : $0.updatedAt > $1.updatedAt
        }
    }
    public func nextHistoryCursor(in loaded: [DesktopTask], ignoring clearedIDs: Set<String> = []) -> Int? {
        guard let index else { return nextCursor }
        let closed = index.filter(\.closed), identities = Set(loaded.map(\.id))
        let prefix = closed.prefix { identities.contains($0.id) || clearedIDs.contains($0.id) }.count
        return prefix < closed.count ? prefix : nil
    }
}

/// Local hiding plus a durable outbox for server-owned 30-day retention.
public struct DesktopTaskHistoryState {
    public struct Record: Codable, Equatable {
        public let id: String
        public let revision: String?
    }
    public struct Operation: Codable, Equatable, Identifiable {
        public let id: UUID
        public let action: String
        public let records: [Record]
    }
    private struct Retention: Codable {
        var clearedAt: [String: TimeInterval]
        var operations: [Operation]
    }
    public private(set) var clearedIDs: Set<String>
    public private(set) var clearedAt: [String: TimeInterval]
    public private(set) var pendingOperations: [Operation]
    private let defaults: UserDefaults
    private let key: String
    public init(defaults: UserDefaults, namespace: String, now: Date = Date()) {
        self.defaults = defaults
        key = "taskHistory.v1." + namespace
        clearedIDs = Set(defaults.stringArray(forKey: key) ?? [])
        if let data = defaults.data(forKey: key + ".retention.v2"),
           let retention = try? JSONDecoder().decode(Retention.self, from: data) {
            clearedAt = retention.clearedAt; pendingOperations = retention.operations
        } else {
            // Legacy clears have no timestamp: start a fresh grace period.
            clearedAt = Dictionary(uniqueKeysWithValues: clearedIDs.map { ($0, now.timeIntervalSince1970) })
            pendingOperations = []
            enqueue("clear", records: clearedIDs.sorted().map { Record(id: $0, revision: nil) })
            persist()
        }
    }
    public func isVisible(_ task: DesktopTask) -> Bool { !task.closed || !clearedIDs.contains(task.id) }
    public func isVisible(_ task: DesktopTaskReference) -> Bool { !task.closed || !clearedIDs.contains(task.id) }
    public mutating func clearClosed(_ index: [DesktopTaskReference], now: Date = Date()) {
        let fresh = index.filter { $0.closed && !clearedIDs.contains($0.id) }
        for task in fresh {
            clearedIDs.insert(task.id); clearedAt[task.id] = now.timeIntervalSince1970
        }
        enqueue("clear", records: fresh.map { Record(id: $0.id, revision: $0.historyRevision) })
        persist()
    }
    public mutating func observeIndex(_ index: [DesktopTaskReference], pruneMissing: Bool = false) {
        let reopened = Set(index.filter { !$0.closed }.map(\.id)).intersection(clearedIDs)
        if !reopened.isEmpty {
            enqueue("restore", records: reopened.sorted().map { Record(id: $0, revision: nil) })
        }
        var removed = reopened
        if pruneMissing { removed.formUnion(clearedIDs.subtracting(index.map(\.id))) }
        guard !removed.isEmpty else { return }
        clearedIDs.subtract(removed)
        for id in removed { clearedAt.removeValue(forKey: id) }
        persist()
    }
    public mutating func restore(now: Date = Date()) {
        let records = clearedIDs.sorted().map { Record(id: $0, revision: nil) }
        enqueue("restore", records: records)
        // Within the grace period, restoration remains immediate even offline.
        // Older cached entries wait for the server to establish availability.
        let recent = clearedIDs.filter { now.timeIntervalSince1970 - (clearedAt[$0] ?? 0) < 30 * 86400 }
        clearedIDs.subtract(recent)
        for id in recent { clearedAt.removeValue(forKey: id) }
        persist()
    }
    public mutating func acknowledge(_ operation: Operation) {
        guard pendingOperations.first?.id == operation.id else { return }
        pendingOperations.removeFirst()
        if operation.action == "restore" {
            let recleared = Set(pendingOperations.filter { $0.action == "clear" }.flatMap { $0.records.map(\.id) })
            for record in operation.records where !recleared.contains(record.id) {
                clearedIDs.remove(record.id); clearedAt.removeValue(forKey: record.id)
            }
        }
        persist()
    }
    private mutating func enqueue(_ action: String, records: [Record]) {
        var offset = 0
        while offset < records.count {
            pendingOperations.append(Operation(id: UUID(), action: action, records: Array(records[offset..<min(offset + 100, records.count)])))
            offset += 100
        }
    }
    private func persist() {
        defaults.set(Array(clearedIDs).sorted(), forKey: key)
        if let data = try? JSONEncoder().encode(Retention(clearedAt: clearedAt, operations: pendingOperations)) {
            defaults.set(data, forKey: key + ".retention.v2")
        }
    }
}

/// Local presentation preference, independent of server state and action tokens.
public struct DesktopTaskReadState {
    private var seen: Set<String>
    private var initialized: Bool
    private var known: Set<String>
    private var baseline: TimeInterval
    private let defaults: UserDefaults
    private let key: String
    public init(defaults: UserDefaults, namespace: String) {
        self.defaults = defaults
        key = "taskRead.v1." + namespace
        seen = Set(defaults.stringArray(forKey: key) ?? [])
        initialized = defaults.bool(forKey: key + ".initialized")
        known = Set(defaults.stringArray(forKey: key + ".known") ?? [])
        baseline = defaults.double(forKey: key + ".baseline")
    }
    public mutating func observe(_ tasks: [DesktopTask]) { observeIndex(tasks.map(DesktopTaskReference.init)) }
    public mutating func observeIndex(_ tasks: [DesktopTaskReference]) {
        let previousSeen = seen, previousKnown = known, wasInitialized = initialized
        if !initialized {
            baseline = Date().timeIntervalSince1970
            seen.formUnion(tasks.filter(\.closed).map(\.id))
            initialized = true
        }
        seen.formUnion(tasks.filter { $0.closed && $0.createdAt <= baseline && !known.contains($0.id) }.map(\.id))
        known.formUnion(tasks.map(\.id))
        if seen != previousSeen || known != previousKnown || initialized != wasInitialized { persist() }
    }
    public func isUnread(_ task: DesktopTask) -> Bool { !seen.contains(task.id) }
    public func isUnread(_ task: DesktopTaskReference) -> Bool { !seen.contains(task.id) }
    public mutating func read(_ task: DesktopTask) {
        guard seen.insert(task.id).inserted else { return }
        persist()
    }
    private func persist() {
        defaults.set(Array(seen).sorted(), forKey: key)
        defaults.set(initialized, forKey: key + ".initialized")
        defaults.set(Array(known).sorted(), forKey: key + ".known")
        defaults.set(baseline, forKey: key + ".baseline")
    }
}
