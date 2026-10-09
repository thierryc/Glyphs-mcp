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
