import CryptoKit
import Darwin
import Foundation

public struct ProjectTemplate: Codable, Equatable, Identifiable {
    public let id: String
    public let name: String
    public let description: String
    public let author: String
    public let license: String
    public let repository: String
    public let templateDirectory: String
    public let revision: String
    public let archiveSHA256: String
    public var archiveURL: URL? {
        guard let url = URL(string: repository), url.scheme == "https", url.host == "github.com",
              url.user == nil, url.password == nil, url.query == nil, url.fragment == nil else { return nil }
        let parts = url.path.split(separator: "/")
        guard parts.count == 2, parts.allSatisfy({ $0.range(of: #"^[A-Za-z0-9_.-]+$"#, options: .regularExpression) != nil }),
              revision.range(of: #"^[a-f0-9]{40}$"#, options: .regularExpression) != nil,
              archiveSHA256.range(of: #"^[a-f0-9]{64}$"#, options: .regularExpression) != nil else { return nil }
        return URL(string: "https://codeload.github.com/\(parts[0])/\(parts[1])/zip/\(revision)")
    }
}

public struct TemplateRegistry: Codable {
    public let schemaVersion: Int
    public let templates: [ProjectTemplate]
    public static var remoteURL: URL {
        URL(string: Bundle.main.object(forInfoDictionaryKey: "GMCPTemplateRegistryURL") as? String
            ?? "https://raw.githubusercontent.com/thierryc/Glyphs-mcp/main/templates/registry.json")!
    }
    public static func decode(_ data: Data) throws -> Self {
        guard data.count < 256_000 else { throw ProjectError("The template registry is too large.") }
        let value = try JSONDecoder().decode(Self.self, from: data)
        guard value.schemaVersion == 1, value.templates.count <= 100,
              Set(value.templates.map(\.id)).count == value.templates.count else { throw ProjectError("Invalid template registry.") }
        for template in value.templates {
            guard template.archiveURL != nil else { throw ProjectError("A template needs a public repository, pinned revision and checksum.") }
            if template.templateDirectory != "." { try ProjectFiles.validateRelativePath(template.templateDirectory) }
        }
        return value
    }
}

public struct ProjectError: LocalizedError {
    public let message: String
    public init(_ message: String) { self.message = message }
    public var errorDescription: String? { message }
}

public struct ProjectFile: Equatable, Sendable {
    public let path: String
    public let data: Data?
    public init(path: String, data: Data?) { self.path = path; self.data = data }
}

public enum ProjectFiles {
    public static func perform<T: Sendable>(_ action: @Sendable @escaping () throws -> T) async throws -> T {
        let task = Task.detached(priority: .userInitiated, operation: action)
        return try await withTaskCancellationHandler(operation: { try await task.value }, onCancel: { task.cancel() })
    }
    public static func validateRelativePath(_ path: String) throws {
        guard !path.isEmpty, !path.hasPrefix("/"), !path.contains("\\"),
              !path.unicodeScalars.contains(where: { CharacterSet.controlCharacters.contains($0) }),
              !path.split(separator: "/", omittingEmptySubsequences: false).contains(where: { $0.isEmpty || $0 == "." || $0 == ".." }) else {
            throw ProjectError("The template contains an unsafe path.")
        }
    }
    public static func read(_ source: URL, maximumBytes: Int = 64 * 1024 * 1024) throws -> [ProjectFile] {
        let fm = FileManager.default
        let keys: Set<URLResourceKey> = [.isSymbolicLinkKey, .isDirectoryKey, .isRegularFileKey, .fileSizeKey]
        let root = try source.resourceValues(forKeys: keys)
        guard root.isDirectory == true, root.isSymbolicLink != true else { throw ProjectError("Choose a regular template folder.") }
        let canonical = source.resolvingSymlinksInPath().standardizedFileURL
        var enumerationError: Error?
        guard let enumerator = fm.enumerator(at: canonical, includingPropertiesForKeys: Array(keys), errorHandler: { _, error in enumerationError = error; return false }) else {
            throw ProjectError("The template folder could not be read.")
        }
        var files: [ProjectFile] = []; var bytes = 0
        while let url = enumerator.nextObject() as? URL {
            if [".git", ".DS_Store"].contains(url.lastPathComponent) { enumerator.skipDescendants(); continue }
            let normalized = url.resolvingSymlinksInPath().standardizedFileURL.path
            guard normalized.hasPrefix(canonical.path + "/") else { throw ProjectError("The template contains an unsafe path.") }
            let path = String(normalized.dropFirst(canonical.path.count + 1))
            try validateRelativePath(path)
            let values = try url.resourceValues(forKeys: keys)
            guard values.isSymbolicLink != true, values.isDirectory == true || values.isRegularFile == true else { throw ProjectError("Templates cannot contain links or special files.") }
            guard files.count < 10_000, bytes + (values.fileSize ?? 0) <= maximumBytes else { throw ProjectError("The template is too large.") }
            let data = values.isDirectory == true ? nil : try Data(contentsOf: url)
            bytes += data?.count ?? 0
            guard bytes <= maximumBytes else { throw ProjectError("The template is too large.") }
            files.append(ProjectFile(path: path, data: data))
        }
        if let enumerationError { throw enumerationError }
        return files.sorted { $0.path < $1.path }
    }
    public static func starter(agents: String) -> [ProjectFile] {
        [ProjectFile(path: "AGENTS.md", data: Data(agents.utf8)),
         ProjectFile(path: "README.md", data: Data("# {{PROJECT_NAME}}\n\nFont sources in `sources`, exports in `exports`, proofs in `proofs`.\n".utf8)),
         ProjectFile(path: ".gitignore", data: Data(".DS_Store\n*.bak\n".utf8))] +
        ["sources", "exports", "proofs", "documentation"].map { ProjectFile(path: $0, data: nil) }
    }
    public static func create(_ files: [ProjectFile], in parent: URL, name: String, endpoint: URL) throws -> URL {
        let name = name.trimmingCharacters(in: .whitespacesAndNewlines)
        try validateRelativePath(name)
        guard !name.contains("/"), !name.hasPrefix("."), name.utf8.count <= 200 else { throw ProjectError("Use a project name without path separators or a leading dot.") }
        let target = parent.appendingPathComponent(name, isDirectory: true)
        let fm = FileManager.default
        guard !fm.fileExists(atPath: target.path) else { throw ProjectError("A folder with this name already exists. Choose another name.") }
        let stage = parent.appendingPathComponent(".glyphs-mcp-project-" + UUID().uuidString)
        try fm.createDirectory(at: stage, withIntermediateDirectories: false)
        defer { try? fm.removeItem(at: stage) }
        var paths = Set<String>()
        for file in files {
            try Task.checkCancellation()
            try validateRelativePath(file.path)
            guard paths.insert(file.path.precomposedStringWithCanonicalMapping.lowercased()).inserted else { throw ProjectError("The template contains duplicate file names.") }
            let destination = stage.appendingPathComponent(file.path)
            if let data = file.data {
                try fm.createDirectory(at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
                if let text = String(data: data, encoding: .utf8), data.count < 1_000_000 {
                    let rendered = text.replacingOccurrences(of: "{{PROJECT_NAME}}", with: name)
                        .replacingOccurrences(of: "{{SERVER_NAME}}", with: InstallerConstants.codexServerName)
                        .replacingOccurrences(of: "{{ENDPOINT_URL}}", with: endpoint.absoluteString)
                    try Data(rendered.utf8).write(to: destination, options: .withoutOverwriting)
                } else { try data.write(to: destination, options: .withoutOverwriting) }
                try fm.setAttributes([.posixPermissions: 0o644], ofItemAtPath: destination.path)
            } else { try fm.createDirectory(at: destination, withIntermediateDirectories: true) }
        }
        try Task.checkCancellation()
        // Atomic exclusive rename closes the name-collision race. Never replace
        // or remove an existing project, including after failed creation.
        guard renameatx_np(AT_FDCWD, stage.path, AT_FDCWD, target.path, UInt32(RENAME_EXCL)) == 0 else {
            throw ProjectError("The project could not be created at this location: " + String(cString: strerror(errno)))
        }
        return target
    }
}
