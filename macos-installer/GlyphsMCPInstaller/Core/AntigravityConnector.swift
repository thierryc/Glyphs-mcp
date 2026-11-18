import Foundation

public struct AntigravityConnector {
    public static let appBundleIdentifiers = ["com.google.antigravity", "com.google.antigravity-ide"]
    static let serverName = "glyphs-mcp"
    private static let legacyServerName = "glyphs-mcp-server"

    public enum ConnectionStatus: Equatable {
        case missing, configured, updateAvailable, conflict

        public var label: String {
            switch self {
            case .missing: return "Missing"
            case .configured: return "Configured"
            case .updateAvailable: return "Port update available"
            case .conflict: return "Needs review"
            }
        }
    }

    public enum SkillsStatus: Equatable {
        case notChecked, missing, partial, available, updateAvailable, conflict

        public var label: String {
            switch self {
            case .notChecked: return "Not checked"
            case .missing: return "Missing"
            case .partial: return "Partially installed"
            case .available: return "Available"
            case .updateAvailable: return "Update available"
            case .conflict: return "Needs review"
            }
        }
    }

    private let home: URL
    private let endpoint: URL

    public init(home: URL = InstallerPaths.home, endpoint: URL = InstallerConstants.endpointURL) {
        self.home = home
        self.endpoint = endpoint
    }

    public static func isDetected(applicationURL: (String) -> URL?) -> Bool {
        appBundleIdentifiers.contains { applicationURL($0) != nil }
    }

    public var configURL: URL { home.appendingPathComponent(".gemini/config/mcp_config.json") }
    public var skillsURL: URL { home.appendingPathComponent(SkillPlacement.antigravity.rawValue, isDirectory: true) }
    private var legacyConfigURL: URL { home.appendingPathComponent(".gemini/antigravity/mcp_config.json") }

    public func connectionStatus() -> ConnectionStatus {
        do {
            let config = try loadConfiguration()
            guard let (name, entry) = try connection(in: config.servers) else { return .missing }
            if matchesEndpoint(entry) { return .configured }
            if owns(entry, named: name) { return .updateAvailable }
        } catch {
            return .conflict
        }
        return .conflict
    }

    /// Returns true when a matching user-managed connection was reused.
    @discardableResult
    public func configureConnection() throws -> Bool {
        var config = try loadConfiguration()
        if let (name, entry) = try connection(in: config.servers) {
            let owned = owns(entry, named: name)
            if matchesEndpoint(entry) { return !owned }
            guard owned else { throw conflictError }
        }
        let entry = ["serverUrl": endpoint.absoluteString]
        config.servers[Self.serverName] = entry
        config.root["mcpServers"] = config.servers
        try prepareWrite(expected: config.original)
        try JSONConnectorOwnership.write(root: config.root, managedEntry: entry,
                                         client: .antigravity, serverName: Self.serverName, to: configURL)
        return false
    }

    /// Returns true when an existing connection was preserved.
    @discardableResult
    public func removeConnection() throws -> Bool {
        var config = try loadConfiguration()
        guard let (name, entry) = try connection(in: config.servers) else { return false }
        guard owns(entry, named: name) else { return true }
        config.servers.removeValue(forKey: name)
        config.root["mcpServers"] = config.servers
        try prepareWrite(expected: config.original)
        let receiptURL = JSONConnectorOwnership.receiptURL(for: configURL)
        let receipt = try Data(contentsOf: receiptURL)
        try FileManager.default.removeItem(at: receiptURL)
        do {
            try JsonConfig.writeJSON(config.root, to: configURL)
        } catch {
            try FileIO.writeAtomically(receipt, to: receiptURL)
            throw error
        }
        return false
    }

    public var hasOwnershipReceipt: Bool {
        if (try? attributesIfPresent(JSONConnectorOwnership.receiptURL(for: configURL))?[.type] as? FileAttributeType) == .typeRegular {
            return true
        }
        guard (try? attributesIfPresent(skillReceiptURL)?[.type] as? FileAttributeType) == .typeRegular,
              let data = try? Data(contentsOf: skillReceiptURL),
              let receipt = try? JSONDecoder().decode([String: String].self, from: data) else { return false }
        return !receipt.isEmpty
    }

    public func skillsStatus(payload: InstallerPayload?, includeDevelopmentSkills: Bool) -> SkillsStatus {
        do {
            try validateSkillsLocation()
            guard try attributesIfPresent(skillsURL) != nil else { return .missing }
            guard let sources = payload?.managedSkillDirectories(), !sources.isEmpty else { return .notChecked }
            let receipts: [String: String]
            if try attributesIfPresent(skillReceiptURL) != nil {
                receipts = try JSONDecoder().decode([String: String].self, from: Data(contentsOf: skillReceiptURL))
            } else {
                receipts = [:]
            }
            let direct = SupplementalSkillInstaller(home: home)
            var available = 0
            var missing = false
            var updateAvailable = false
            for source in sources {
                let name = source.lastPathComponent
                if !includeDevelopmentSkills && AgentSkillBundleInstaller.developmentSkillNames.contains(name) { continue }
                if try direct.hasDirectChoice(name, root: skillsURL) { continue }
                let destination = skillsURL.appendingPathComponent(name)
                let descriptor = destination.appendingPathComponent("SKILL.md")
                guard FileManager.default.isReadableFile(atPath: descriptor.path) else {
                    missing = true
                    continue
                }
                available += 1
                if let owned = receipts[name],
                   (try? attributesIfPresent(destination)?[.type] as? FileAttributeType) == .typeDirectory,
                   (try? InstallerPayloadManifestResolver.treeIdentity(destination)) == owned,
                   let bundled = try? InstallerPayloadManifestResolver.treeIdentity(source),
                   bundled != owned {
                    updateAvailable = true
                }
            }
            if missing { return available == 0 ? .missing : .partial }
            return updateAvailable ? .updateAvailable : .available
        } catch {
            return .conflict
        }
    }

    public func installSkills(from payload: InstallerPayload, includeDevelopmentSkills: Bool,
                              log: @escaping (String) -> Void) throws -> SkillInstallationResult {
        try validateSkillsLocation()
        return try AgentSkillBundleInstaller(log: log).installManagedSkills(
            from: payload, to: skillsURL, clientName: "Antigravity", overwriteExisting: false,
            includeDevelopmentSkills: includeDevelopmentSkills)
    }

    public func removeSkills(from payload: InstallerPayload,
                             log: @escaping (String) -> Void) throws -> SkillInstallationResult {
        try validateSkillsLocation()
        return try AgentSkillBundleInstaller(log: log).removeOwnedSkills(from: payload, under: skillsURL)
    }

    private var skillReceiptURL: URL { skillsURL.appendingPathComponent(".glyphs-mcp-skills.json") }

    private func validateSkillsLocation() throws {
        try requireDirectoryIfPresent(home.appendingPathComponent(".gemini"))
        try requireDirectoryIfPresent(skillsURL.deletingLastPathComponent())
        try requireDirectoryIfPresent(skillsURL)
        try requireRegularFileIfPresent(skillReceiptURL)
        try requireRegularFileIfPresent(skillsURL.appendingPathComponent(".glyphs-mcp-catalog-skills.json"))
        try requireDirectoryIfPresent(AgentSkillBundleInstaller.skillBackupRoot(for: skillsURL))
    }

    private struct Configuration {
        var root: [String: Any]
        var servers: [String: Any]
        let original: Data?
    }

    private func loadConfiguration() throws -> Configuration {
        try requireDirectoryIfPresent(home.appendingPathComponent(".gemini"))
        try requireDirectoryIfPresent(configURL.deletingLastPathComponent())
        try requireRegularFileIfPresent(configURL)
        try requireRegularFileIfPresent(JSONConnectorOwnership.receiptURL(for: configURL))
        try requireDirectoryIfPresent(legacyConfigURL.deletingLastPathComponent())
        if let attributes = try attributesIfPresent(legacyConfigURL) {
            guard attributes[.type] as? FileAttributeType == .typeSymbolicLink,
                  legacyConfigURL.resolvingSymlinksInPath() == configURL.resolvingSymlinksInPath()
                    || resolvesDirectlyToConfig(legacyConfigURL) else {
                throw InstallerError.localized("Antigravity has a separate legacy MCP config. Review both files in Antigravity before running Setup.")
            }
        }
        guard try attributesIfPresent(configURL) != nil else {
            return .init(root: [:], servers: [:], original: nil)
        }
        let data = try Data(contentsOf: configURL)
        guard let root = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              root["mcpServers"] == nil || root["mcpServers"] is [String: Any] else {
            throw InstallerError.localized("Antigravity’s MCP config is invalid. Fix it in Antigravity and retry Setup.")
        }
        return .init(root: root, servers: root["mcpServers"] as? [String: Any] ?? [:], original: data)
    }

    private func connection(in servers: [String: Any]) throws -> (String, [String: Any])? {
        let candidates = servers.filter { name, value in
            if name == Self.serverName || name == Self.legacyServerName { return true }
            guard let entry = value as? [String: Any] else { return false }
            return ["serverUrl", "url"].contains { matchesEndpointURL(entry[$0]) }
        }
        guard let candidate = candidates.first else { return nil }
        guard candidates.count == 1, let entry = candidate.value as? [String: Any] else {
            throw conflictError
        }
        return (candidate.key, entry)
    }

    private func matchesEndpoint(_ entry: [String: Any]) -> Bool {
        guard entry["disabled"] == nil || entry["disabled"] as? Bool == false,
              entry["command"] == nil else { return false }
        let configured = ["serverUrl", "url"].compactMap { entry[$0] }
        return !configured.isEmpty && configured.allSatisfy(matchesEndpointURL)
    }

    private func matchesEndpointURL(_ value: Any?) -> Bool {
        guard let address = value as? String,
              let components = URLComponents(string: address),
              let active = URLComponents(url: endpoint, resolvingAgainstBaseURL: false),
              components.scheme == active.scheme,
              components.port == active.port,
              components.host == active.host || components.host == "localhost",
              components.user == nil, components.password == nil,
              components.query == nil, components.fragment == nil else { return false }
        let path = components.percentEncodedPath
        return path == active.percentEncodedPath || path + "/" == active.percentEncodedPath
            || path == active.percentEncodedPath + "/"
    }

    private func owns(_ entry: [String: Any], named name: String) -> Bool {
        name == Self.serverName && JSONConnectorOwnership.matches(
            entry, client: .antigravity, serverName: name, at: configURL)
    }

    private func prepareWrite(expected: Data?) throws {
        guard try loadConfiguration().original == expected else { throw conflictError }
        _ = try FileIO.backupIfExists(configURL)
        guard try loadConfiguration().original == expected else { throw conflictError }
    }

    private func resolvesDirectlyToConfig(_ link: URL) -> Bool {
        guard let target = try? FileManager.default.destinationOfSymbolicLink(atPath: link.path) else { return false }
        let absolute = target.hasPrefix("/") ? URL(fileURLWithPath: target)
            : link.deletingLastPathComponent().appendingPathComponent(target)
        return absolute.standardizedFileURL.path == configURL.standardizedFileURL.path
    }

    private func attributesIfPresent(_ url: URL) throws -> [FileAttributeKey: Any]? {
        do {
            return try FileManager.default.attributesOfItem(atPath: url.path)
        } catch let error as NSError where error.domain == NSCocoaErrorDomain
            && [NSFileNoSuchFileError, NSFileReadNoSuchFileError].contains(error.code) {
            return nil
        }
    }

    private func requireDirectoryIfPresent(_ url: URL) throws {
        if let attributes = try attributesIfPresent(url), attributes[.type] as? FileAttributeType != .typeDirectory {
            throw locationError
        }
    }

    private func requireRegularFileIfPresent(_ url: URL) throws {
        if let attributes = try attributesIfPresent(url), attributes[.type] as? FileAttributeType != .typeRegular {
            throw locationError
        }
    }

    private var locationError: InstallerError {
        .localized("Antigravity’s configuration or skills path is redirected or has an unexpected file type. Existing files were preserved.")
    }

    private var conflictError: InstallerError {
        .localized("Review the existing Glyphs MCP connection in Antigravity. Setup preserves disabled, modified, or conflicting connections.")
    }
}
