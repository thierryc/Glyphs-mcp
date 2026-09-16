import Foundation

public struct GitObservation: Equatable, Sendable {
    public let branch: String
    public let headRevision: String?
    public let changes: [Change]

    public init(branch: String, headRevision: String?, changes: [Change]) {
        self.branch = branch
        self.headRevision = headRevision
        self.changes = changes
    }

    public struct Change: Equatable, Identifiable, Sendable {
        public enum Kind: String, Equatable, Sendable {
            case added, modified, deleted, renamed, copied, untracked, conflicted
        }

        public let status: String
        public let stagedStatus: String
        public let workingStatus: String
        public let kind: Kind
        public let path: String
        public let originalPath: String?

        public init(
            status: String,
            stagedStatus: String,
            workingStatus: String,
            kind: Kind,
            path: String,
            originalPath: String? = nil
        ) {
            self.status = status
            self.stagedStatus = stagedStatus
            self.workingStatus = workingStatus
            self.kind = kind
            self.path = path
            self.originalPath = originalPath
        }
        public var id: String { path }
        public var statusLabel: String {
            switch kind {
            case .added: return "A"
            case .modified: return "M"
            case .deleted: return "D"
            case .renamed: return "R"
            case .copied: return "C"
            case .untracked: return "U"
            case .conflicted: return "!"
            }
        }
        public var isGlyphPackageGlyph: Bool {
            let parts = path.split(separator: "/").map(String.init)
            guard path.hasSuffix(".glyph"), parts.count >= 3 else { return false }
            return parts.dropLast(2).last?.hasSuffix(".glyphspackage") == true && parts[parts.count - 2] == "glyphs"
        }
    }
}

public enum GitFileContent: Equatable, Sendable {
    case text(String)
    case missing
    case binary
    case oversized(Int)
    case symbolicLink(String)

    public var text: String? {
        if case .text(let value) = self { return value }
        if case .missing = self { return "" }
        return nil
    }
}

public struct GitFileComparison: Equatable, Sendable {
    public static let maximumBytes = 2 * 1024 * 1024
    public let path: String
    public let originalPath: String?
    public let kind: GitObservation.Change.Kind
    public let oldContent: GitFileContent
    public let newContent: GitFileContent

    public init(
        path: String,
        originalPath: String?,
        kind: GitObservation.Change.Kind,
        oldContent: GitFileContent,
        newContent: GitFileContent
    ) {
        self.path = path
        self.originalPath = originalPath
        self.kind = kind
        self.oldContent = oldContent
        self.newContent = newContent
    }

    public var isTextDiffAvailable: Bool { oldContent.text != nil && newContent.text != nil }
}

public struct GitChangeTreeNode: Equatable, Identifiable, Sendable {
    public let id: String
    public let name: String
    public let change: GitObservation.Change?
    public let children: [GitChangeTreeNode]?

    public init(id: String, name: String, change: GitObservation.Change?, children: [GitChangeTreeNode]?) {
        self.id = id
        self.name = name
        self.change = change
        self.children = children
    }
}

public enum GitChangeTree {
    public static func hierarchy(_ changes: [GitObservation.Change]) -> [GitChangeTreeNode] {
        let root = Builder(name: "", path: "")
        changes.forEach(root.insert)
        return root.frozen()
    }

    public static func filtered(_ changes: [GitObservation.Change], query: String) -> [GitObservation.Change] {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return changes }
        return changes.filter { change in
            change.path.localizedCaseInsensitiveContains(trimmed)
                || change.originalPath?.localizedCaseInsensitiveContains(trimmed) == true
        }
    }

    private final class Builder {
        let name: String
        let path: String
        var change: GitObservation.Change?
        var children: [String: Builder] = [:]

        init(name: String, path: String) { self.name = name; self.path = path }

        func insert(_ change: GitObservation.Change) {
            let parts = change.path.split(separator: "/").map(String.init)
            var node = self
            var accumulated: [String] = []
            for (index, part) in parts.enumerated() {
                accumulated.append(part)
                let key = accumulated.joined(separator: "/")
                if node.children[part] == nil { node.children[part] = .init(name: part, path: key) }
                node = node.children[part]!
                if index == parts.count - 1 { node.change = change }
            }
        }

        func frozen() -> [GitChangeTreeNode] {
            children.values.sorted {
                if ($0.change == nil) != ($1.change == nil) { return $0.change == nil }
                return $0.name.localizedStandardCompare($1.name) == .orderedAscending
            }.map { child in
                let nested = child.frozen()
                return .init(id: child.path, name: child.name, change: child.change,
                             children: nested.isEmpty ? nil : nested)
            }
        }
    }
}

private struct GitComparisonCacheKey: Hashable, Sendable {
    let project: String
    let headRevision: String?
    let path: String
    let originalPath: String?
    let status: String
    let workingMetadata: String
}

private actor GitComparisonCache {
    static let shared = GitComparisonCache()
    private var values: [GitComparisonCacheKey: GitFileComparison] = [:]

    func value(for key: GitComparisonCacheKey) -> GitFileComparison? { values[key] }
    func insert(_ value: GitFileComparison, for key: GitComparisonCacheKey) {
        values = values.filter { $0.key.project != key.project || $0.key.path != key.path }
        values[key] = value
    }
}

public struct ReadOnlyGit {
    public let executable: URL?
    private let runner = ProcessRunner()

    public init(executable: URL? = nil) {
        self.executable = executable ?? [
            "/Applications/Xcode.app/Contents/Developer/usr/bin/git",
            "/Library/Developer/CommandLineTools/usr/bin/git",
            "/opt/homebrew/bin/git",
            "/usr/local/bin/git",
        ].first(where: { FileManager.default.isExecutableFile(atPath: $0) })
            .map { URL(fileURLWithPath: $0) }
    }

    public func inspect(_ project: URL) async throws -> GitObservation {
        let branch = try await run(project, ["symbolic-ref", "--quiet", "--short", "HEAD"], allowFailure: true).stdout
        let status = try await run(project, ["status", "--porcelain=v1", "-z", "--untracked-files=normal"]).stdout
        let fields = status.split(separator: "\0", omittingEmptySubsequences: true).map(String.init)
        var changes: [GitObservation.Change] = []
        var index = 0
        while index < fields.count {
            let field = fields[index]
            index += 1
            guard field.count >= 4 else { throw ProjectError("Git returned an invalid status record.") }
            let state = String(field.prefix(2))
            let path = String(field.dropFirst(3))
            var original: String?
            if state.contains("R") || state.contains("C") {
                guard index < fields.count else { throw ProjectError("Git returned an incomplete renamed-file record.") }
                original = fields[index]
                index += 1
            }
            changes.append(.init(
                status: state,
                stagedStatus: String(state.prefix(1)),
                workingStatus: String(state.suffix(1)),
                kind: kind(for: state),
                path: path,
                originalPath: original
            ))
        }
        let name = branch.trimmingCharacters(in: .whitespacesAndNewlines)
        let revision = try await run(project, ["rev-parse", "--verify", "HEAD"], allowFailure: true).stdout
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let shortRevision = String(revision.prefix(7))
        let label = revision.isEmpty ? (name.isEmpty ? "No commits yet" : name + " · No commits yet")
            : (name.isEmpty ? "Detached at " + shortRevision : name)
        return GitObservation(branch: label, headRevision: revision.isEmpty ? nil : revision, changes: changes)
    }

    public func comparison(
        _ project: URL,
        change: GitObservation.Change,
        headRevision: String?
    ) async throws -> GitFileComparison {
        try Task.checkCancellation()
        try ProjectFiles.validateRelativePath(change.path)
        if let originalPath = change.originalPath { try ProjectFiles.validateRelativePath(originalPath) }
        let metadata = try workingMetadata(project, path: change.path)
        let key = GitComparisonCacheKey(
            project: project.standardizedFileURL.path,
            headRevision: headRevision,
            path: change.path,
            originalPath: change.originalPath,
            status: change.status,
            workingMetadata: metadata
        )
        if let cached = await GitComparisonCache.shared.value(for: key) { return cached }
        let oldPath = change.originalPath ?? change.path
        let oldContent: GitFileContent
        if let headRevision, let object = try await blobObject(project, revision: headRevision, path: oldPath) {
            oldContent = try await blobContent(project, object: object)
        } else {
            oldContent = .missing
        }
        let newContent = try workingContent(project, path: change.path)
        try Task.checkCancellation()
        let value = GitFileComparison(path: change.path, originalPath: change.originalPath, kind: change.kind,
                                      oldContent: oldContent, newContent: newContent)
        await GitComparisonCache.shared.insert(value, for: key)
        return value
    }

    /// Retained for callers that need the literal Git patch rather than the content comparison.
    public func diff(_ project: URL, path: String) async throws -> String {
        try ProjectFiles.validateRelativePath(path)
        let arguments = ["diff", "--no-ext-diff", "--no-textconv", "--no-color", "--submodule=short"]
        let unstaged = try await run(project, arguments + ["--", path]).stdout
        let staged = try await run(project, arguments + ["--cached", "--", path]).stdout
        let text = (staged.isEmpty ? "" : "Staged changes\n" + staged + "\n")
            + (unstaged.isEmpty ? "" : "Working-tree changes\n" + unstaged)
        return text.isEmpty ? "No tracked text diff. New, binary or untracked files can be opened in your editor."
            : String(text.prefix(100_000)) + (text.count > 100_000 ? "\n… Diff truncated for display." : "")
    }

    private func kind(for state: String) -> GitObservation.Change.Kind {
        if state == "??" { return .untracked }
        if state.contains("U") || state == "AA" || state == "DD" { return .conflicted }
        if state.contains("R") { return .renamed }
        if state.contains("C") { return .copied }
        if state.contains("D") { return .deleted }
        if state.contains("A") { return .added }
        return .modified
    }

    private func blobObject(_ project: URL, revision: String, path: String) async throws -> String? {
        let result = try await run(project, ["ls-tree", "-z", revision, "--", path])
        guard !result.stdoutData.isEmpty else { return nil }
        guard let tab = result.stdoutData.firstIndex(of: 0x09) else {
            throw ProjectError("Git returned an invalid tree record.")
        }
        let header = String(decoding: result.stdoutData[..<tab], as: UTF8.self).split(separator: " ")
        guard header.count >= 3, header[1] == "blob" else { return nil }
        return String(header[2])
    }

    private func blobContent(_ project: URL, object: String) async throws -> GitFileContent {
        let sizeText = try await run(project, ["cat-file", "-s", object]).stdout
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard let size = Int(sizeText) else { throw ProjectError("Git returned an invalid blob size.") }
        guard size <= GitFileComparison.maximumBytes else { return .oversized(size) }
        return classify(try await run(project, ["cat-file", "blob", object]).stdoutData)
    }

    private func workingContent(_ project: URL, path: String) throws -> GitFileContent {
        let url = try safeWorkingURL(project, path: path)
        let attributes: [FileAttributeKey: Any]
        do { attributes = try FileManager.default.attributesOfItem(atPath: url.path) }
        catch let error as NSError where Self.isMissingFileError(error) {
            return .missing
        }
        if attributes[.type] as? FileAttributeType == .typeSymbolicLink {
            return .symbolicLink(try FileManager.default.destinationOfSymbolicLink(atPath: url.path))
        }
        guard attributes[.type] as? FileAttributeType == .typeRegular else { return .binary }
        let size = (attributes[.size] as? NSNumber)?.intValue ?? 0
        guard size <= GitFileComparison.maximumBytes else { return .oversized(size) }
        return classify(try Data(contentsOf: url, options: .mappedIfSafe))
    }

    private func workingMetadata(_ project: URL, path: String) throws -> String {
        let url = try safeWorkingURL(project, path: path)
        do {
            let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
            let type = (attributes[.type] as? FileAttributeType)?.rawValue ?? "unknown"
            let size = (attributes[.size] as? NSNumber)?.int64Value ?? -1
            let modified = (attributes[.modificationDate] as? Date)?.timeIntervalSince1970 ?? -1
            let inode = (attributes[.systemFileNumber] as? NSNumber)?.uint64Value ?? 0
            let link = type == FileAttributeType.typeSymbolicLink.rawValue
                ? try FileManager.default.destinationOfSymbolicLink(atPath: url.path) : ""
            return "\(type):\(size):\(modified):\(inode):\(link)"
        } catch let error as NSError where Self.isMissingFileError(error) {
            return "missing"
        }
    }

    private func safeWorkingURL(_ project: URL, path: String) throws -> URL {
        try ProjectFiles.validateRelativePath(path)
        let root = project.standardizedFileURL
        let parts = path.split(separator: "/").map(String.init)
        var current = root
        for (index, part) in parts.enumerated() {
            current.appendPathComponent(part)
            do {
                let attributes = try FileManager.default.attributesOfItem(atPath: current.path)
                if attributes[.type] as? FileAttributeType == .typeSymbolicLink, index < parts.count - 1 {
                    throw ProjectError("A symbolic link in the selected path escapes the repository boundary.")
                }
            } catch let error as NSError where Self.isMissingFileError(error) {
                if index < parts.count - 1 { return root.appendingPathComponent(path) }
            }
        }
        return current
    }

    private static func isMissingFileError(_ error: NSError) -> Bool {
        error.domain == NSCocoaErrorDomain
            && (error.code == NSFileNoSuchFileError || error.code == NSFileReadNoSuchFileError)
    }

    private func classify(_ data: Data) -> GitFileContent {
        guard !data.contains(0), let text = String(data: data, encoding: .utf8) else { return .binary }
        return .text(text)
    }

    private func run(
        _ project: URL,
        _ arguments: [String],
        allowFailure: Bool = false
    ) async throws -> ProcessRunner.Result {
        guard let executable else { throw ProjectError("Git is unavailable. Project creation and templates remain available.") }
        let args = ["--no-optional-locks", "--no-pager", "--literal-pathspecs", "-c", "core.fsmonitor=false",
                    "-c", "core.untrackedCache=false", "-c", "core.hooksPath=/dev/null", "-c", "credential.helper=",
                    "-c", "diff.external=", "-C", project.path] + arguments
        let result = try await runner.runCapturing(executable: executable, args: args,
            environment: ["PATH": "/usr/bin:/bin", "HOME": FileManager.default.homeDirectoryForCurrentUser.path,
                          "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_OPTIONAL_LOCKS": "0",
                          "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"], timeout: 10)
        guard result.exitCode == 0 || allowFailure else {
            if result.stderr.contains("not a git repository") { throw ProjectError("This folder isn’t a Git repository.") }
            throw ProjectError(String(result.stderr.prefix(1000)).trimmingCharacters(in: .whitespacesAndNewlines))
        }
        return result
    }
}
