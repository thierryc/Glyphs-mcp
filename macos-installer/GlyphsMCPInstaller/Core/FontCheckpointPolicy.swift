import Foundation

/// Shared with the sidecar. AGENTS.md is guidance, never executable policy.
public enum FontCheckpointPolicy {
    public struct Value { public let enabled: Bool; public let data: Data? }
    public static func read(_ folder: URL) throws -> Value {
        let url = folder.appendingPathComponent(".glyphs-mcp.json")
        if !FileManager.default.fileExists(atPath: url.path),
           (try? FileManager.default.destinationOfSymbolicLink(atPath: url.path)) == nil {
            return .init(enabled: false, data: nil)
        }
        let resource = try url.resourceValues(forKeys: [.isSymbolicLinkKey, .isRegularFileKey, .fileSizeKey])
        guard resource.isSymbolicLink != true, resource.isRegularFile == true, (resource.fileSize ?? 0) <= 16_384 else {
            throw ProjectError("The checkpoint configuration is unsafe or too large.")
        }
        let data = try Data(contentsOf: url)
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let version = object["schemaVersion"] as? NSNumber,
              CFGetTypeID(version) != CFBooleanGetTypeID(), version == 1,
              let settings = object["gitCheckpoints"] as? [String: Any],
              let enabled = settings["enabled"] as? NSNumber,
              CFGetTypeID(enabled) == CFBooleanGetTypeID() else { throw ProjectError("The checkpoint configuration is invalid.") }
        return .init(enabled: enabled.boolValue, data: data)
    }
    public static func write(_ folder: URL, enabled: Bool, expected: Data?) throws {
        let current = try read(folder)
        guard current.data == expected else { throw ProjectError("Project settings changed. Reopen settings before saving.") }
        if current.enabled == enabled { return }
        var object = try current.data.map { try JSONSerialization.jsonObject(with: $0) as! [String: Any] } ?? [:]
        object["schemaVersion"] = 1
        var settings = object["gitCheckpoints"] as? [String: Any] ?? [:]
        settings["enabled"] = enabled; object["gitCheckpoints"] = settings
        let data = try JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted, .sortedKeys])
        guard data.count <= 16_384 else { throw ProjectError("Project settings are too large.") }
        try data.write(to: folder.appendingPathComponent(".glyphs-mcp.json"), options: .atomic)
    }
}
