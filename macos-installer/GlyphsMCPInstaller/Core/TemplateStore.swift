import CryptoKit
import Foundation

public actor TemplateStore {
    public let root: URL
    private let runner = ProcessRunner()
    private let session: URLSession
    public init(root: URL? = nil, session: URLSession? = nil) {
        let cache = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Caches/Glyphs MCP/Templates")
        self.root = root ?? (DesktopIdentity.isBeta ? cache.appendingPathComponent("beta") : cache)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.httpShouldSetCookies = false
        self.session = session ?? URLSession(configuration: configuration)
    }
    public func registry(bundle: Bundle = .main) throws -> TemplateRegistry {
        let cached = root.appendingPathComponent("registry.json")
        if let data = try? Data(contentsOf: cached), let registry = try? TemplateRegistry.decode(data) { return registry }
        guard let bundled = bundle.url(forResource: "registry", withExtension: "json", subdirectory: "Templates") else { throw ProjectError("The bundled template registry is missing.") }
        return try TemplateRegistry.decode(Data(contentsOf: bundled))
    }
    public func refreshRegistry() async throws -> TemplateRegistry {
        let data = try await download(TemplateRegistry.remoteURL, maximumBytes: 256_000)
        let registry = try TemplateRegistry.decode(data)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        try data.write(to: root.appendingPathComponent("registry.json"), options: .atomic)
        return registry
    }
    public func files(_ template: ProjectTemplate) async throws -> [ProjectFile] {
        guard let remote = template.archiveURL else { throw ProjectError("The template registry entry is invalid.") }
        if template.templateDirectory != "." { try ProjectFiles.validateRelativePath(template.templateDirectory) }
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let cached = root.appendingPathComponent(template.archiveSHA256 + ".zip")
        let archive: Data
        if let data = try? Data(contentsOf: cached), Self.checksum(data) == template.archiveSHA256 { archive = data }
        else {
            archive = try await download(remote, maximumBytes: 20 * 1024 * 1024)
            guard Self.checksum(archive) == template.archiveSHA256 else { throw ProjectError("The template download does not match its pinned checksum.") }
            _ = try TemplateArchive.validate(archive)
            try Task.checkCancellation()
            try archive.write(to: cached, options: .atomic)
        }
        let folder = try TemplateArchive.validate(archive)
        let temporary = root.appendingPathComponent("extract-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: temporary, withIntermediateDirectories: false)
        defer { try? FileManager.default.removeItem(at: temporary) }
        let result = try await runner.runCapturing(executable: URL(fileURLWithPath: "/usr/bin/ditto"), args: ["-x", "-k", cached.path, temporary.path], timeout: 30)
        guard result.exitCode == 0 else { throw ProjectError("The template archive could not be expanded.") }
        let base = temporary.appendingPathComponent(folder)
        let source = template.templateDirectory == "." ? base : base.appendingPathComponent(template.templateDirectory)
        // Never execute template programs or copy a repository's Git database.
        return try ProjectFiles.read(source)
    }
    public static func checksum(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
    private func download(_ url: URL, maximumBytes: Int) async throws -> Data {
        var request = URLRequest(url: url); request.timeoutInterval = 30
        let (bytes, response) = try await session.bytes(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200,
              response.url?.scheme == "https", response.url?.host == url.host,
              response.expectedContentLength <= maximumBytes else { throw ProjectError("The template download is unavailable or too large.") }
        var data = Data()
        for try await byte in bytes {
            guard data.count < maximumBytes else { throw ProjectError("The template download is too large.") }
            data.append(byte)
        }
        try Task.checkCancellation()
        return data
    }
}
