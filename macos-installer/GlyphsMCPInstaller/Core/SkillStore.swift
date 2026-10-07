import Foundation

public actor SkillStore {
    public let root: URL
    private let session: URLSession
    private let runner = ProcessRunner()
    public init(root: URL? = nil, session: URLSession? = nil) {
        let cache = InstallerPaths.home.appendingPathComponent("Library/Caches/Glyphs MCP/Skills")
        self.root = root ?? (DesktopIdentity.isBeta ? cache.appendingPathComponent("beta") : cache)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.httpShouldSetCookies = false
        self.session = session ?? URLSession(configuration: configuration)
    }
    public func catalog(snapshot: Data, refresh: Bool = false) async throws -> SkillCatalog {
        let bundled = try SkillCatalog.decode(snapshot)
        if refresh {
            let data = try await download(SkillCatalog.remoteURL, maximumBytes: 512_000)
            let value = try SkillCatalog.decode(data).includingBundled(bundled)
            try ensureRoot()
            try data.write(to: root.appendingPathComponent("registry.json"), options: .atomic)
            return value
        }
        if let data = try? Data(contentsOf: root.appendingPathComponent("registry.json")),
           let value = try? SkillCatalog.decode(data).includingBundled(bundled) { return value }
        return bundled
    }
    public func imports() throws -> [CatalogSkill] {
        let path = root.appendingPathComponent("imports.json")
        guard FileManager.default.fileExists(atPath: path.path) else { return [] }
        return try SkillCatalog.decode(Data(contentsOf: path), allowImports: true).skills
    }
    public func remember(_ skill: CatalogSkill) throws {
        guard skill.classification == .imported, !skill.bundled else { throw ProjectError("Only personal imports can be saved here.") }
        var entries = try imports()
        guard !entries.contains(where: { $0.name == skill.name && $0.id != skill.id }) else { throw ProjectError("Another import has this skill name.") }
        entries.removeAll { $0.id == skill.id }; entries.append(skill)
        let data = try JSONEncoder().encode(SkillCatalog(skills: entries))
        _ = try SkillCatalog.decode(data, allowImports: true)
        try ensureRoot(); try data.write(to: root.appendingPathComponent("imports.json"), options: .atomic)
    }
    public func files(_ skill: CatalogSkill, bundledRoot: URL? = nil) async throws -> [ProjectFile] {
        if skill.bundled {
            guard let bundledRoot else { throw ProjectError("The matching bundled skills payload is unavailable.") }
            let files = try ProjectFiles.read(bundledRoot.appendingPathComponent(skill.name))
            _ = try SkillMetadata.validate(files, expectedName: skill.name, bundled: true)
            return files
        }
        guard let hash = skill.source.archiveSHA256, SkillSource.isHash(hash), let url = skill.source.archiveURL else {
            throw ProjectError("The skill has no pinned archive and checksum.")
        }
        let archive = try await archiveData(url: url, checksum: hash)
        return try await extract(archive) { folder in
            let directory = skill.source.directory
            if directory != "." { try ProjectFiles.validateRelativePath(directory) }
            let source = directory == "." ? folder : folder.appendingPathComponent(directory)
            let files = try ProjectFiles.read(source)
            _ = try SkillMetadata.validate(files, expectedName: skill.name)
            return files
        }
    }
    /// Public API only; no credential discovery, Git hooks, clone, or source execution.
    public func discover(repository: String, directory: String = ".", revision: String = "") async throws -> [CatalogSkill] {
        if directory != "." { try ProjectFiles.validateRelativePath(directory) }
        let proposed = SkillSource(repository: repository.trimmingCharacters(in: .whitespacesAndNewlines), directory: directory, revision: "")
        guard let repositoryURL = proposed.repositoryURL else { throw ProjectError("Enter a public GitHub repository URL, with the directory and revision in their separate fields.") }
        let path = repositoryURL.path
        let info = try await json(URL(string: "https://api.github.com/repos" + path)!)
        guard info["private"] as? Bool == false else { throw ProjectError("Only public GitHub repositories are supported.") }
        let ref = revision.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let defaultBranch = info["default_branch"] as? String, !defaultBranch.isEmpty else { throw ProjectError("The repository has no default branch.") }
        let resolved = ref.isEmpty ? defaultBranch : ref
        guard resolved.count <= 200, !resolved.contains(where: { $0.isNewline || $0.isASCII && $0.asciiValue! < 32 }) else { throw ProjectError("Invalid Git revision.") }
        var allowed = CharacterSet.urlPathAllowed; allowed.remove(charactersIn: "/?#%")
        guard let encoded = resolved.addingPercentEncoding(withAllowedCharacters: allowed) else { throw ProjectError("Invalid Git revision.") }
        let commit = try await json(URL(string: "https://api.github.com/repos" + path + "/commits/" + encoded)!)
        guard let sha = commit["sha"] as? String, SkillSource.isCommit(sha) else { throw ProjectError("The Git revision could not be resolved.") }
        var pinned = SkillSource(repository: repositoryURL.absoluteString, directory: directory, revision: sha)
        let data = try await download(pinned.archiveURL!, maximumBytes: 20 * 1024 * 1024)
        _ = try TemplateArchive.validate(data)
        pinned.archiveSHA256 = TemplateStore.checksum(data)
        try ensureRoot(); try data.write(to: root.appendingPathComponent(pinned.archiveSHA256! + ".zip"), options: .atomic)
        let source = pinned
        return try await extract(data) { folder in
            let scoped = directory == "." ? folder : folder.appendingPathComponent(directory)
            let files = try ProjectFiles.read(scoped)
            let skillPaths = files.filter { $0.path == "SKILL.md" || $0.path.hasSuffix("/SKILL.md") }.map(\.path)
            guard !skillPaths.isEmpty, skillPaths.count <= 100 else { throw ProjectError("Choose a directory containing between one and 100 skills.") }
            return try skillPaths.map { path in
                let local = (path as NSString).deletingLastPathComponent
                let prefix = local.isEmpty ? "" : local + "/"
                let package = files.filter { $0.path.hasPrefix(prefix) }.map { ProjectFile(path: String($0.path.dropFirst(prefix.count)), data: $0.data) }
                    .filter { !$0.path.isEmpty }
                let metadata = try SkillMetadata.validate(package)
                var skillSource = source
                skillSource.directory = [directory == "." ? "" : directory, local].filter { !$0.isEmpty }.joined(separator: "/")
                if skillSource.directory.isEmpty { skillSource.directory = "." }
                let owner = String(repositoryURL.path.split(separator: "/")[0])
                return CatalogSkill(id: "import:" + pathID(repositoryURL.path + "/" + skillSource.directory), name: metadata.name,
                    description: metadata.description, author: owner, license: "Not verified; review the source license",
                    classification: .imported, source: skillSource, compatibleClients: SkillClient.allCases,
                    requirements: ["Client compatibility and dependencies are unverified. Review the complete skill before installing."])
            }
        }
    }
    private func archiveData(url: URL, checksum: String) async throws -> Data {
        try ensureRoot()
        let cached = root.appendingPathComponent(checksum + ".zip")
        if let data = try? Data(contentsOf: cached), TemplateStore.checksum(data) == checksum {
            _ = try TemplateArchive.validate(data); return data
        }
        let data = try await download(url, maximumBytes: 20 * 1024 * 1024)
        guard TemplateStore.checksum(data) == checksum else { throw ProjectError("The skill archive does not match its pinned checksum.") }
        _ = try TemplateArchive.validate(data)
        try data.write(to: cached, options: .atomic); return data
    }
    private func extract<T>(_ data: Data, read: (URL) throws -> T) async throws -> T {
        let top = try TemplateArchive.validate(data)
        try ensureRoot()
        let temporary = root.appendingPathComponent("extract-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: temporary, withIntermediateDirectories: false)
        defer { try? FileManager.default.removeItem(at: temporary) }
        let zip = temporary.appendingPathComponent("archive.zip")
        try data.write(to: zip)
        let output = temporary.appendingPathComponent("contents")
        let result = try await runner.runCapturing(executable: URL(fileURLWithPath: "/usr/bin/ditto"), args: ["-x", "-k", zip.path, output.path], timeout: 30)
        guard result.exitCode == 0 else { throw ProjectError("The skill archive could not be expanded.") }
        try Task.checkCancellation()
        return try read(output.appendingPathComponent(top))
    }
    private func ensureRoot() throws {
        try SupplementalSkillInstaller.regularAncestors(root)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }
    private func json(_ url: URL) async throws -> [String: Any] {
        let data = try await download(url, maximumBytes: 2_000_000)
        guard let value = try JSONSerialization.jsonObject(with: data) as? [String: Any] else { throw ProjectError("GitHub returned an invalid response.") }
        return value
    }
    private func download(_ url: URL, maximumBytes: Int) async throws -> Data {
        var request = URLRequest(url: url); request.timeoutInterval = 30
        request.setValue("Glyphs-MCP-Skills", forHTTPHeaderField: "User-Agent")
        let (bytes, response) = try await session.bytes(for: request)
        guard let http = response as? HTTPURLResponse else { throw ProjectError("The skill source is unavailable.") }
        if http.statusCode == 403 || http.statusCode == 429 { throw ProjectError("GitHub access or rate limit reached. Try again later; cached skills remain available.") }
        guard http.statusCode == 200, response.url?.scheme == "https", response.url?.host == url.host,
              response.expectedContentLength <= maximumBytes else { throw ProjectError("The skill source is unavailable or too large.") }
        var data = Data()
        for try await byte in bytes {
            guard data.count < maximumBytes else { throw ProjectError("The skill download is too large.") }
            data.append(byte)
        }
        try Task.checkCancellation(); return data
    }
}

private func pathID(_ value: String) -> String { String(TemplateStore.checksum(Data(value.utf8)).prefix(24)) }
