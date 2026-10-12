import Foundation

/// Coalesces expensive immutable discovery. Failures may be retried; cancelling
/// one caller does not cancel work still needed by another caller.
public actor SharedInitialization<Value: Sendable> {
    private var pending: Task<Value, Error>?
    private var value: Value?

    public init() {}

    public func resolve(_ load: @escaping @Sendable () throws -> Value) async throws -> Value {
        if let value { return value }
        if let pending { return try await pending.value }
        let task = Task.detached(priority: .utility, operation: load)
        pending = task
        do {
            let result = try await task.value
            value = result
            pending = nil
            return result
        } catch {
            pending = nil
            throw error
        }
    }
}

/// Setup and the skills catalog share the same immutable, verified payload.
public enum InstallerPayloadDiscovery {
    public static let shared = SharedInitialization<InstallerPayload>()
}

/// A skipped check enables installation without claiming Python was verified.
/// Payload preparation failures cannot be bypassed by this choice.
public enum GlyphsPythonCheckState: Equatable, Sendable {
    case notChecked
    case checking
    case ready(String?)
    case failed(String, canSkip: Bool)
    case skipped(String)

    public var verified: Bool { if case .ready = self { return true }; return false }
    public var isChecking: Bool { self == .checking }
    public var isSkipped: Bool { if case .skipped = self { return true }; return false }
    public var allowsInstallation: Bool { verified || isSkipped }
    public var canSkip: Bool { if case .failed(_, let allowed) = self { return allowed }; return false }
    public var version: String? { if case .ready(let version) = self { return version }; return nil }
    public var error: String? {
        switch self {
        case .failed(let message, _), .skipped(let message): return message
        default: return nil
        }
    }

    public func allowingUnverifiedInstallation() -> Self {
        guard case .failed(let message, true) = self else { return self }
        return .skipped(message)
    }
}

/// Interpreter evidence belongs to the exact check, never the private MCP Python.
public struct GlyphsPythonDetection: Equatable, Sendable {
    public let path: String?
    public let nativeVersion: String?
    public var isGlyphsModule: Bool { path?.contains("/Application Support/Glyphs 4/Repositories/Python/") == true }

    public static func parse(_ diagnostics: String, checkID: String) -> Self? {
        var path: String?
        var version: String?
        for line in diagnostics.split(separator: "\n") {
            guard let marker = line.range(of: "GLYPHS_MCP_SETUP:"),
                  let data = String(line[marker.upperBound...]).data(using: .utf8),
                  let row = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
                  row["checkId"] as? String == checkID else { continue }
            switch row["event"] as? String {
            case "python.preference":
                if let selected = row["selectedPath"] as? String, !selected.isEmpty { path = selected }
            case "python.selection":
                if let selected = row["framework"] as? String { path = selected }
            case "python.native-result":
                for native in (row["stdout"] as? String ?? "").split(separator: "\n") {
                    let prefix = "GLYPHS_MCP_NATIVE_CONTEXT:"
                    guard native.hasPrefix(prefix),
                          let data = String(native.dropFirst(prefix.count)).data(using: .utf8),
                          let context = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else { continue }
                    path = context["prefix"] as? String ?? path
                    version = context["version"] as? String
                }
            default: break
            }
        }
        return path == nil && version == nil ? nil : Self(path: path, nativeVersion: version)
    }
}

/// A new application or check invalidates late results, including A → B → A.
public struct GlyphsPythonCheckSession: Sendable {
    public private(set) var application: GlyphsApplicationInfo?
    public private(set) var state: GlyphsPythonCheckState = .notChecked
    public private(set) var detection: GlyphsPythonDetection?
    public private(set) var activeCheckID: UUID?
    public init() {}

    @discardableResult public mutating func bind(_ application: GlyphsApplicationInfo?) -> Bool {
        guard self.application != application else { return false }
        self.application = application
        state = .notChecked
        detection = nil
        activeCheckID = nil
        return true
    }
    public mutating func begin() -> UUID {
        let id = UUID()
        activeCheckID = id
        state = .checking
        detection = nil
        return id
    }
    public func accepts(_ id: UUID) -> Bool { activeCheckID == id }
    @discardableResult public mutating func finish(_ id: UUID, state: GlyphsPythonCheckState,
                                                  detection: GlyphsPythonDetection? = nil) -> Bool {
        guard accepts(id) else { return false }
        self.state = state
        self.detection = detection
        return true
    }
    public mutating func allowUnverifiedInstallation() { state = state.allowingUnverifiedInstallation() }
}
