import Darwin
import Foundation

public enum LocalSkillTarget: String, CaseIterable, Identifiable, Sendable {
    case agents, claudeCode
    public var id: String { rawValue }
    public var title: String { self == .agents ? "Codex & Cursor" : "Claude Code" }
    public func root(home: URL = InstallerPaths.home, project: URL? = nil) -> URL {
        (project ?? home).appendingPathComponent(self == .agents ? ".agents/skills" : ".claude/skills")
    }
    public func roots(home: URL = InstallerPaths.home, project: URL? = nil) -> [URL] {
        [root(home: home, project: project)] + (self == .agents
            ? [".codex/skills", ".cursor/skills"].map { (project ?? home).appendingPathComponent($0) } : [])
    }
    public func supports(_ skill: CatalogSkill) -> Bool {
        self == .agents ? skill.compatibleClients.contains(.codex) || skill.compatibleClients.contains(.cursor) : skill.compatibleClients.contains(.claudeCode)
    }
}

public enum SkillPlacement: String, CaseIterable, Sendable {
    case shared = ".agents/skills"
    case codex = ".codex/skills"
    case claudeCode = ".claude/skills"
    case cursor = ".cursor/skills"
    case cursorPlugin = ".cursor/plugins/local/glyphs-mcp/skills"

    public static let localAgents: [SkillClient] = [.codex, .claudeCode, .cursor]

    public var agents: [SkillClient] {
        switch self {
        case .shared, .codex: return [.codex, .cursor]
        case .claudeCode: return [.claudeCode, .cursor]
        case .cursor, .cursorPlugin: return [.cursor]
        }
    }

    fileprivate func owner(in compatibleAgents: [SkillClient]) -> SkillClient? {
        let primary: SkillClient
        switch self {
        case .shared, .codex: primary = .codex
        case .claudeCode: primary = .claudeCode
        case .cursor, .cursorPlugin: primary = .cursor
        }
        return compatibleAgents.contains(primary) ? primary : agents.first(where: compatibleAgents.contains)
    }

    fileprivate static func preferred(for agent: SkillClient) -> Self {
        switch agent {
        case .codex: return .shared
        case .claudeCode: return .claudeCode
        default: return .cursor
        }
    }
}

public struct SkillCopy: Identifiable, Sendable {
    public let placement: SkillPlacement
    public let root: URL
    public let status: SkillInstallationStatus
    fileprivate let identity: String?
    public var id: String { status.path }
}

public struct SkillScopeStatus: Sendable {
    public let agents: [SkillClient]
    public let copies: [SkillCopy]

    public func installed(for agent: SkillClient) -> [SkillCopy] {
        copies.filter { $0.placement.agents.contains(agent) && $0.status.isInstalled }
    }

    // Agent discovery may overlap, but manage each installation under its owner once.
    public func managedCopies(for agent: SkillClient) -> [SkillCopy] {
        installed(for: agent).filter { $0.placement.owner(in: agents) == agent }
    }

    public func missing(for requested: [SkillClient]) -> [SkillCopy] {
        var covered = Set(agents.filter { !installed(for: $0).isEmpty })
        var targets: [SkillCopy] = []
        for agent in agents where requested.contains(agent) && !covered.contains(agent) {
            let placement = SkillPlacement.preferred(for: agent)
            guard let target = copies.first(where: { $0.placement == placement }) else { continue }
            targets.append(target)
            covered.formUnion(placement.agents)
        }
        return targets
    }
}

public enum SkillCopyOperation: Equatable, Sendable {
    case install, reinstall, update, remove
}

public struct SkillBatchResult: Sendable {
    public var completed: [String] = []
    public var failures: [String] = []
}

public struct SkillPackageVersion: Sendable {
    public let label: String
    fileprivate let hash: String
    fileprivate let linkedHash: String

    public init(label: String, files: [ProjectFile]) {
        self.label = label
        self.hash = SupplementalSkillInstaller.hash(files)
        let authored = files.filter { !ProjectFiles.isPythonCache($0.path, isDirectory: $0.data == nil) }
        self.linkedHash = authored.count == files.count ? hash : SupplementalSkillInstaller.hash(authored)
    }
}

public struct SupplementalSkillReceipt: Codable, Equatable, Sendable {
    public var skill: CatalogSkill
    public var contentSHA256: String
    var removed: Bool? = nil
    var packageVersion: String? = nil
}

public struct SkillInstallationStatus: Sendable {
    public enum State: String, Sendable { case notInstalled, installed, updateAvailable, modified, unowned, linked, blocked }
    public let state: State
    public let path: String
    public var verifiedVersion: String? = nil
    public var installedVersion: String? = nil
    public var availableVersion: String? = nil
    public var title: String {
        switch state {
        case .notInstalled: return "Not installed"
        case .installed: return "Installed"
        case .updateAvailable: return "Update available"
        case .modified: return "Installed · locally modified"
        case .unowned: return "Installed · existing copy"
        case .linked: return "Installed · linked folder"
        case .blocked: return "Folder needs review"
        }
    }
    public var isInstalled: Bool { state != .notInstalled && state != .blocked }
    public var requiresBackupConfirmation: Bool { state == .modified || state == .unowned }
}

/// Mutations are serialized by the desktop model and by an advisory lock for each
/// destination root. Journals make interrupted folder/receipt transitions recoverable.
public struct SupplementalSkillInstaller {
    public let home: URL
    public let bundledNames: Set<String>
    public init(home: URL = InstallerPaths.home, bundledNames: Set<String> = []) { self.home = home; self.bundledNames = bundledNames }
    private static let ledgerName = ".glyphs-mcp-catalog-skills.json"
    private static let journalName = ".glyphs-mcp-catalog-transaction.json"
    private struct Journal: Codable {
        let name: String
        let newHash: String?
        let oldHash: String?
        let backup: String?
        let stage: String?
        let previous: [String: SupplementalSkillReceipt]
        let next: [String: SupplementalSkillReceipt]
    }
    public static func regularAncestors(_ url: URL) throws {
        var cursor = url.standardizedFileURL
        while cursor.path != "/" {
            // Foundation canonicalizes temporary URLs to macOS's /tmp and /var
            // aliases. These two system aliases are not user-controlled roots.
            if cursor.path == "/tmp" || cursor.path == "/var" {
                let link = try? FileManager.default.destinationOfSymbolicLink(atPath: cursor.path)
                if link == "private" + cursor.path || link == "/private" + cursor.path {
                    cursor.deleteLastPathComponent(); continue
                }
            }
            if let values = try? cursor.resourceValues(forKeys: [.isSymbolicLinkKey, .isDirectoryKey]),
               values.isSymbolicLink == true || values.isDirectory == false {
                throw ProjectError("Choose a regular folder without symbolic-link ancestors: " + cursor.path)
            }
            cursor.deleteLastPathComponent()
        }
    }
    private static func exists(_ url: URL) -> Bool {
        FileManager.default.fileExists(atPath: url.path) || (try? url.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink) == true
    }
    private static func identity(_ url: URL) throws -> String {
        if (try? url.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink) == true {
            return TemplateStore.checksum(Data(("symbolic-link\0" + (try FileManager.default.destinationOfSymbolicLink(atPath: url.path))).utf8))
        }
        let files = try ProjectFiles.read(url)
        return hash(files)
    }
    public static func hash(_ files: [ProjectFile]) -> String {
        var data = Data()
        for file in files.sorted(by: { $0.path < $1.path }) {
            data.append(Data(file.path.utf8)); data.append(0)
            data.append(Data((file.data == nil ? "directory" : TemplateStore.checksum(file.data!)).utf8)); data.append(0)
        }
        return TemplateStore.checksum(data)
    }
    private static func receipts(_ root: URL) throws -> [String: SupplementalSkillReceipt] {
        let url = root.appendingPathComponent(ledgerName)
        guard exists(url) else { return [:] }
        guard (try url.resourceValues(forKeys: [.isSymbolicLinkKey])).isSymbolicLink != true else { throw ProjectError("The skills receipt is a symbolic link.") }
        let data = try Data(contentsOf: url)
        guard data.count < 2_000_000 else { throw ProjectError("The skills receipt is too large.") }
        let receipts = try JSONDecoder().decode([String: SupplementalSkillReceipt].self, from: data)
        guard receipts.allSatisfy({ SkillMetadata.validName($0.key) && $0.value.skill.name == $0.key && SkillSource.isHash($0.value.contentSHA256) }) else {
            throw ProjectError("Invalid skills ownership receipt.")
        }
        return receipts
    }
    public func installed(in root: URL) throws -> [SupplementalSkillReceipt] {
        try Self.receipts(root).values.filter { $0.removed != true }.sorted { $0.skill.name < $1.skill.name }
    }

    func hasDirectChoice(_ name: String, root: URL) throws -> Bool {
        try Self.receipts(root)[name]?.skill.id == "builtin:" + name
    }

    public func scopeStatus(_ skill: CatalogSkill, project: URL? = nil, package: SkillPackageVersion? = nil) -> SkillScopeStatus {
        let base = project ?? home
        let agents = SkillPlacement.localAgents.filter { skill.compatibleClients.contains($0) }
        let copies = SkillPlacement.allCases.compactMap { placement -> SkillCopy? in
            if placement == .cursorPlugin && project != nil { return nil }
            let root = base.appendingPathComponent(placement.rawValue, isDirectory: true)
            let destination = root.appendingPathComponent(skill.name)
            let fingerprint = try? Self.identity(destination)
            var current = status(skill, root: root, package: package, fingerprint: fingerprint)
            if Self.exists(destination) {
                let instructions = destination.appendingPathComponent("SKILL.md")
                let size = try? instructions.resourceValues(forKeys: [.fileSizeKey]).fileSize
                let name = size.flatMap { $0 <= 1_000_000 ? try? Data(contentsOf: instructions) : nil }
                    .flatMap { try? SkillMetadata.parse($0).name }
                if name != skill.name || fingerprint == nil {
                    current = .init(state: .blocked, path: destination.path)
                }
            }
            return .init(placement: placement, root: root, status: current, identity: fingerprint)
        }
        return .init(agents: agents, copies: copies)
    }

    public func apply(_ operation: SkillCopyOperation, to targets: [SkillCopy], skill: CatalogSkill,
                      files: [ProjectFile], project: URL? = nil, replace: Bool = false,
                      package: SkillPackageVersion? = nil) -> SkillBatchResult {
        var result = SkillBatchResult()
        if let project {
            do {
                try Self.regularAncestors(project)
                guard try project.resourceValues(forKeys: [.isDirectoryKey]).isDirectory == true else {
                    throw ProjectError("Choose an existing project folder.")
                }
            } catch {
                result.failures.append(error.localizedDescription)
                return result
            }
        }
        var visited = Set<String>()
        for target in targets where visited.insert(target.id).inserted {
            do {
                guard target.placement != .cursorPlugin,
                      target.placement.agents.contains(where: { skill.compatibleClients.contains($0) }),
                      target.root == (project ?? home).appendingPathComponent(target.placement.rawValue, isDirectory: true),
                      target.status.state != .blocked else {
                    throw ProjectError("Review the existing folder before continuing.")
                }
                switch operation {
                case .install, .reinstall, .update:
                    if operation == .install {
                        let current = scopeStatus(skill, project: project)
                        let requested = current.agents.filter { target.placement.agents.contains($0) }
                        if current.missing(for: requested).isEmpty { continue }
                    }
                    result.completed.append(try install(skill, files: files, root: target.root, project: project,
                        replace: replace, replaceLink: replace, reviewed: target, packageVersion: package?.label))
                case .remove:
                    result.completed.append(try remove(skill, root: target.root, preserveExisting: replace,
                        reviewed: target, rememberRemoval: project == nil))
                }
            } catch {
                result.failures.append(target.status.path + ": " + error.localizedDescription)
            }
        }
        return result
    }
    /// Use the same location for discovery and actions. Older agent-specific
    /// installations must not look absent merely because the shared root is empty.
    public func installationRoot(_ skill: CatalogSkill, target: LocalSkillTarget, project: URL? = nil) -> URL {
        target.roots(home: home, project: project).first { Self.exists($0.appendingPathComponent(skill.name)) }
            ?? target.root(home: home, project: project)
    }
    public func status(_ skill: CatalogSkill, target: LocalSkillTarget, project: URL? = nil) -> SkillInstallationStatus {
        status(skill, root: installationRoot(skill, target: target, project: project))
    }
    public func status(_ skill: CatalogSkill, root: URL) -> SkillInstallationStatus {
        status(skill, root: root, package: nil, fingerprint: nil)
    }

    private func status(_ skill: CatalogSkill, root: URL, package: SkillPackageVersion?, fingerprint: String?) -> SkillInstallationStatus {
        let destination = root.appendingPathComponent(skill.name)
        let path = destination.path
        guard Self.exists(destination) else { return .init(state: .notInstalled, path: path) }
        let linked = (try? destination.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink) == true
        if linked {
            // Version comparison ignores generated bytecode. Link and ownership checks remain exact.
            let verified = package.flatMap { package -> String? in
                guard let files = try? ProjectFiles.read(destination.resolvingSymlinksInPath(), excludingPythonCaches: true),
                      Self.hash(files) == package.linkedHash else { return nil }
                return package.label
            }
            return .init(state: .linked, path: path, verifiedVersion: verified, availableVersion: package?.label)
        }
        let hash = fingerprint ?? (try? Self.identity(destination))
        let verified = package.flatMap { $0.hash == hash ? $0.label : nil }
        if let receipt = try? Self.receipts(root)[skill.name], receipt.skill.id == skill.id {
            guard receipt.removed != true, let hash, hash == receipt.contentSHA256 else {
                return .init(state: .modified, path: path, verifiedVersion: verified, availableVersion: package?.label)
            }
            let current = package.map { $0.hash == hash }
                ?? (skill.bundled || receipt.skill.source == skill.source)
            let installedVersion = receipt.packageVersion
                ?? (receipt.skill.bundled ? nil : "Revision " + receipt.skill.source.revision.prefix(8))
            return .init(state: current ? .installed : .updateAvailable, path: path,
                         verifiedVersion: verified, installedVersion: installedVersion, availableVersion: package?.label)
        }
        if skill.bundled, legacyOwns(skill.name, destination: destination, root: root) {
            return .init(state: package.map { $0.hash == hash } ?? true ? .installed : .updateAvailable,
                         path: path, verifiedVersion: verified, availableVersion: package?.label)
        }
        return .init(state: .unowned, path: path, verifiedVersion: verified, availableVersion: package?.label)
    }

    private func legacyOwns(_ name: String, destination: URL, root: URL) -> Bool {
        guard [SkillPlacement.codex, .claudeCode].contains(where: {
            root.path == home.appendingPathComponent($0.rawValue).path
        }) else { return false }
        let ledger = root.appendingPathComponent(".glyphs-mcp-skills.json")
        guard (try? ledger.resourceValues(forKeys: [.isSymbolicLinkKey]))?.isSymbolicLink == false,
              let data = try? Data(contentsOf: ledger), data.count < 2_000_000,
              let receipt = try? JSONDecoder().decode([String: String].self, from: data)[name],
              let identity = try? InstallerPayloadManifestResolver.treeIdentity(destination) else { return false }
        return identity == receipt
    }

    private func canManage(_ skill: CatalogSkill, reviewed: SkillCopy?) -> Bool {
        if skill.bundled {
            return reviewed != nil && bundledNames.contains(skill.name) && skill.id == "builtin:" + skill.name
        }
        return !bundledNames.contains(skill.name)
    }

    public func recover(root: URL) throws {
        guard Self.exists(root.appendingPathComponent(Self.journalName)) else { return }
        try locked(root) { try recoverLocked(root) }
    }
    private func recoverLocked(_ root: URL) throws {
        let journalURL = root.appendingPathComponent(Self.journalName)
        guard Self.exists(journalURL) else { return }
        guard (try journalURL.resourceValues(forKeys: [.isSymbolicLinkKey])).isSymbolicLink != true else { throw ProjectError("The skills transaction is a symbolic link.") }
        let journal = try JSONDecoder().decode(Journal.self, from: Data(contentsOf: journalURL))
        guard SkillMetadata.validName(journal.name), journal.newHash.map(SkillSource.isHash) ?? true, journal.oldHash.map(SkillSource.isHash) ?? true else {
            throw ProjectError("Invalid skills recovery record.")
        }
        let destination = root.appendingPathComponent(journal.name)
        let current = Self.exists(destination) ? try Self.identity(destination) : nil
        let ledger = try Self.receipts(root)
        if ledger == journal.next && current == journal.newHash {
            try cleanupStage(journal, root: root)
            try FileManager.default.removeItem(at: journalURL); return
        }
        // Never replace content changed after an interrupted transaction.
        guard current == journal.newHash || current == journal.oldHash else {
            throw ProjectError("Interrupted skills operation has edited content. Preserve it and review " + journalURL.path)
        }
        if current != journal.oldHash {
            if let backup = journal.backup, let oldHash = journal.oldHash {
                let source = URL(fileURLWithPath: backup)
                let backupRoot = root.deletingLastPathComponent().appendingPathComponent("glyphs-mcp-skill-backups/catalog")
                try Self.regularAncestors(source.deletingLastPathComponent())
                // Foundation standardization can resolve the final symlink.
                // Validate its location lexically after checking every parent;
                // recovery restores the link itself, never its external target.
                guard source.path.hasPrefix(backupRoot.path + "/"),
                      !source.pathComponents.contains(".."), !source.pathComponents.contains("."),
                      try Self.identity(source) == oldHash else {
                    throw ProjectError("The skill recovery backup is invalid.")
                }
                let stage = root.appendingPathComponent(".skill-restore-" + UUID().uuidString)
                try FileManager.default.copyItem(at: source, to: stage)
                defer { try? FileManager.default.removeItem(at: stage) }
                try Self.exchange(stage: stage, destination: destination)
            } else if Self.exists(destination) { try FileManager.default.removeItem(at: destination) }
        }
        try Self.writeLedger(journal.previous, root: root)
        try cleanupStage(journal, root: root)
        try FileManager.default.removeItem(at: journalURL)
    }
    private func cleanupStage(_ journal: Journal, root: URL) throws {
        guard let name = journal.stage else { return }
        guard name.hasPrefix(".skill-"), !name.contains("/"), !name.contains("\\") else { throw ProjectError("Invalid skill recovery staging path.") }
        let stage = root.appendingPathComponent(name)
        guard Self.exists(stage) else { return }
        let hash = try Self.identity(stage)
        guard hash == journal.oldHash || hash == journal.newHash else { throw ProjectError("A recovery staging folder was edited and preserved: " + stage.path) }
        try FileManager.default.removeItem(at: stage)
    }
    public func install(_ skill: CatalogSkill, files: [ProjectFile], root: URL, project: URL? = nil, replace: Bool = false, replaceLink: Bool = false) throws -> String {
        try install(skill, files: files, root: root, project: project, replace: replace, replaceLink: replaceLink, reviewed: nil, packageVersion: nil)
    }

    private func install(_ skill: CatalogSkill, files: [ProjectFile], root: URL, project: URL?,
                         replace: Bool, replaceLink: Bool, reviewed: SkillCopy?, packageVersion: String?) throws -> String {
        guard canManage(skill, reviewed: reviewed) else { throw ProjectError("This bundled skill needs its verified app payload.") }
        _ = try SkillMetadata.validate(files, expectedName: skill.name, bundled: skill.bundled)
        return try locked(root) {
            try recoverLocked(root)
            let destination = root.appendingPathComponent(skill.name)
            let previous = try Self.receipts(root)
            let hash = Self.hash(files)
            let oldHash = Self.exists(destination) ? try Self.identity(destination) : nil
            let linked = (try? destination.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink) == true
            guard !linked || replace && replaceLink else { throw ProjectError("This is a linked skill. Confirm replacing the link with a managed copy; its original folder will be kept.") }
            if let reviewed, reviewed.identity != oldHash { throw ProjectError("The skill changed. Review the current copy and try again.") }
            let owned = !linked && owns(skill, receipts: previous, hash: oldHash, destination: destination, root: root)
            guard oldHash == nil || owned || replace else { throw ProjectError("Existing skill is edited or unmanaged. Review it, then choose Replace with backup.") }
            if reviewed == nil { try checkCollisions(skill, root: root, project: project) }
            let stage = root.appendingPathComponent(".skill-stage-" + UUID().uuidString)
            try FileManager.default.createDirectory(at: stage, withIntermediateDirectories: false)
            defer { try? FileManager.default.removeItem(at: stage) }
            for file in files {
                let target = stage.appendingPathComponent(file.path)
                if let data = file.data {
                    try FileManager.default.createDirectory(at: target.deletingLastPathComponent(), withIntermediateDirectories: true)
                    try data.write(to: target, options: .withoutOverwriting)
                } else { try FileManager.default.createDirectory(at: target, withIntermediateDirectories: true) }
            }
            guard try Self.identity(stage) == hash else { throw ProjectError("Staged skill verification failed.") }
            let backup = try oldHash.map { _ in try self.backup(destination, root: root) }
            var next = previous
            next[skill.name] = .init(skill: skill, contentSHA256: hash, packageVersion: packageVersion)
            let journal = Journal(name: skill.name, newHash: hash, oldHash: oldHash, backup: backup?.path, stage: stage.lastPathComponent, previous: previous, next: next)
            try JSONEncoder().encode(journal).write(to: root.appendingPathComponent(Self.journalName), options: .atomic)
            do {
                guard (Self.exists(destination) ? try Self.identity(destination) : nil) == oldHash else { throw ProjectError("The skill changed during installation.") }
                try Self.exchange(stage: stage, destination: destination)
                try Self.writeLedger(next, root: root)
                try FileManager.default.removeItem(at: root.appendingPathComponent(Self.journalName))
            } catch {
                try recoverLocked(root); throw error
            }
            return "Installed: " + destination.path + (backup.map { "\nBackup: " + $0.path } ?? "")
        }
    }
    public func remove(_ skill: CatalogSkill, root: URL, preserveExisting: Bool = false) throws -> String {
        try remove(skill, root: root, preserveExisting: preserveExisting, reviewed: nil, rememberRemoval: false)
    }

    private func remove(_ skill: CatalogSkill, root: URL, preserveExisting: Bool, reviewed: SkillCopy?,
                        rememberRemoval: Bool) throws -> String {
        guard SkillMetadata.validName(skill.name), canManage(skill, reviewed: reviewed) else {
            throw ProjectError("This skill cannot be removed from this location.")
        }
        return try locked(root) {
            try recoverLocked(root)
            let destination = root.appendingPathComponent(skill.name)
            var next = try Self.receipts(root); let previous = next
            let linked = (try? destination.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink) == true
            let oldHash = try Self.identity(destination)
            if let reviewed, reviewed.identity != oldHash { throw ProjectError("The skill changed. Review the current copy and try again.") }
            let owned = !linked && owns(skill, receipts: previous, hash: oldHash, destination: destination, root: root)
            guard owned || preserveExisting else {
                throw ProjectError("The skill is modified or unmanaged and was preserved.")
            }
            let backup = try backup(destination, root: root)
            if rememberRemoval && skill.bundled {
                next[skill.name] = .init(skill: skill, contentSHA256: oldHash, removed: true)
            } else {
                next.removeValue(forKey: skill.name)
            }
            let stage = root.appendingPathComponent(".skill-remove-" + UUID().uuidString)
            defer { try? FileManager.default.removeItem(at: stage) }
            let journal = Journal(name: skill.name, newHash: nil, oldHash: oldHash, backup: backup.path, stage: stage.lastPathComponent, previous: previous, next: next)
            try JSONEncoder().encode(journal).write(to: root.appendingPathComponent(Self.journalName), options: .atomic)
            do {
                guard try Self.identity(destination) == oldHash else { throw ProjectError("The skill changed during removal.") }
                guard renameatx_np(AT_FDCWD, destination.path, AT_FDCWD, stage.path, UInt32(RENAME_EXCL)) == 0 else { throw ProjectError("The skill could not be removed atomically.") }
                try Self.writeLedger(next, root: root)
                try FileManager.default.removeItem(at: root.appendingPathComponent(Self.journalName))
            } catch { try recoverLocked(root); throw error }
            return (linked ? "Removed link: " : "Removed: ") + destination.path + (linked ? "\nOriginal folder preserved." : "") + "\nBackup: " + backup.path
        }
    }
    private func owns(_ skill: CatalogSkill, receipts: [String: SupplementalSkillReceipt], hash: String?,
                      destination: URL, root: URL) -> Bool {
        if let receipt = receipts[skill.name] {
            return receipt.skill.id == skill.id && receipt.removed != true && receipt.contentSHA256 == hash
        }
        return skill.bundled && legacyOwns(skill.name, destination: destination, root: root)
    }

    private func backup(_ source: URL, root: URL) throws -> URL {
        let parent = root.deletingLastPathComponent().appendingPathComponent("glyphs-mcp-skill-backups/catalog/" + UUID().uuidString)
        try Self.regularAncestors(parent)
        try FileManager.default.createDirectory(at: parent, withIntermediateDirectories: true)
        let target = parent.appendingPathComponent(source.lastPathComponent)
        let coordinates = ["source": source.path, "backup": target.path, "identity": try Self.identity(source)]
        try JSONEncoder().encode(coordinates).write(to: parent.appendingPathComponent("backup.json"), options: .atomic)
        try FileManager.default.copyItem(at: source, to: target)
        guard try Self.identity(source) == Self.identity(target) else { throw ProjectError("Skill backup verification failed.") }
        return target
    }
    private func checkCollisions(_ skill: CatalogSkill, root: URL, project: URL?) throws {
        // Independent agents and personal/project scopes can intentionally have
        // separate copies. Only competing locations in this agent scope collide.
        let agentRoots = LocalSkillTarget.agents.roots(home: home, project: project)
        guard agentRoots.contains(where: { $0.standardizedFileURL.path == root.standardizedFileURL.path }) else { return }
        let roots = agentRoots + (project == nil ? [home.appendingPathComponent(".cursor/plugins/local/glyphs-mcp/skills")] : [])
        for other in roots where other.resolvingSymlinksInPath().standardizedFileURL.path != root.resolvingSymlinksInPath().standardizedFileURL.path {
            let destination = other.appendingPathComponent(skill.name)
            guard Self.exists(destination) else { continue }
            // Separate managed copies for different hosts/scopes are intentional.
            if let receipt = try Self.receipts(other)[skill.name], receipt.skill.id == skill.id,
               (try? Self.identity(destination)) == receipt.contentSHA256 { continue }
            throw ProjectError("A skill with this name already exists at " + destination.path + ". Manage that copy before adding another.")
        }
    }
    private func locked<T>(_ root: URL, action: () throws -> T) throws -> T {
        try Self.regularAncestors(root)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let path = root.appendingPathComponent(".glyphs-mcp-catalog.lock").path
        let descriptor = open(path, O_CREAT | O_RDWR | O_NOFOLLOW, mode_t(0o600))
        guard descriptor >= 0 else { throw ProjectError("Could not lock the skills folder.") }
        defer { close(descriptor) }
        guard flock(descriptor, LOCK_EX | LOCK_NB) == 0 else { throw ProjectError("Another skills operation is using this folder.") }
        defer { flock(descriptor, LOCK_UN) }
        return try action()
    }
    private static func writeLedger(_ value: [String: SupplementalSkillReceipt], root: URL) throws {
        let path = root.appendingPathComponent(ledgerName)
        if exists(path) {
            guard try path.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink != true else { throw ProjectError("The skills receipt is a symbolic link.") }
        }
        try JSONEncoder().encode(value).write(to: path, options: .atomic)
    }
    private static func exchange(stage: URL, destination: URL) throws {
        let flag = exists(destination) ? RENAME_SWAP : RENAME_EXCL
        guard renameatx_np(AT_FDCWD, stage.path, AT_FDCWD, destination.path, UInt32(flag)) == 0 else { throw ProjectError("The skill could not be installed atomically: " + String(cString: strerror(errno))) }
    }
}
