import Foundation

public enum SkillClient: String, Codable, CaseIterable, Identifiable, Sendable {
    case codex, cursor, claudeCode, chatgpt, claude
    public var id: String { rawValue }
    public var title: String {
        switch self {
        case .codex: return "Codex"
        case .cursor: return "Cursor"
        case .claudeCode: return "Claude Code"
        case .chatgpt: return "ChatGPT"
        case .claude: return "Claude"
        }
    }
}

public struct SkillSource: Codable, Equatable, Sendable {
    public var repository: String
    public var directory: String
    public var revision: String
    public var archiveSHA256: String?
    public init(repository: String, directory: String, revision: String, archiveSHA256: String? = nil) {
        self.repository = repository; self.directory = directory; self.revision = revision; self.archiveSHA256 = archiveSHA256
    }
    public var repositoryURL: URL? {
        guard let url = URL(string: repository), url.scheme == "https", url.host == "github.com",
              url.user == nil, url.password == nil, url.port == nil, url.query == nil, url.fragment == nil else { return nil }
        let parts = url.path.split(separator: "/")
        guard parts.count == 2, parts.allSatisfy({ $0.range(of: #"^[A-Za-z0-9_.-]+$"#, options: .regularExpression) != nil && $0 != "." && $0 != ".." }) else { return nil }
        return URL(string: "https://github.com/\(parts[0])/\(parts[1])")
    }
    public var archiveURL: URL? {
        guard let repositoryURL, Self.isCommit(revision) else { return nil }
        return URL(string: "https://codeload.github.com\(repositoryURL.path)/zip/\(revision)")
    }
    public var browseURL: URL? {
        guard let repositoryURL, Self.isCommit(revision) else { return nil }
        var url = repositoryURL.appendingPathComponent("tree").appendingPathComponent(revision)
        if directory != "." {
            guard (try? ProjectFiles.validateRelativePath(directory)) != nil else { return nil }
            for component in directory.split(separator: "/") { url.appendPathComponent(String(component)) }
        }
        return url
    }
    public static func isCommit(_ value: String) -> Bool { value.range(of: #"^[a-f0-9]{40}$"#, options: .regularExpression) != nil }
    public static func isHash(_ value: String) -> Bool { value.range(of: #"^[a-f0-9]{64}$"#, options: .regularExpression) != nil }
}

public struct CatalogSkill: Codable, Equatable, Identifiable, Sendable {
    public enum Classification: String, Codable, Sendable { case curated, community, imported }
    public var id: String
    public var name: String
    public var description: String
    public var author: String
    public var license: String
    public var classification: Classification
    public var source: SkillSource
    public var compatibleClients: [SkillClient]
    public var requirements: [String]
    public var bundled: Bool
    public init(id: String, name: String, description: String, author: String, license: String,
                classification: Classification, source: SkillSource, compatibleClients: [SkillClient], requirements: [String], bundled: Bool = false) {
        self.id = id; self.name = name; self.description = description; self.author = author; self.license = license
        self.classification = classification; self.source = source; self.compatibleClients = compatibleClients
        self.requirements = requirements; self.bundled = bundled
    }
    public var categoryTitle: String {
        if bundled { return "Included with Glyphs MCP" }
        switch classification { case .curated: return "Curated"; case .community: return "Community"; case .imported: return "Unreviewed import" }
    }
}

public struct SkillCatalog: Codable, Sendable {
    public var schemaVersion: Int
    public var skills: [CatalogSkill]
    public init(skills: [CatalogSkill]) { schemaVersion = 1; self.skills = skills }
    public static let remoteURL = URL(string: "https://raw.githubusercontent.com/thierryc/glyphs-mcp-skills/main/registry.json")!
    public static let contributionURL = URL(string: "https://github.com/thierryc/glyphs-mcp-skills/blob/main/CONTRIBUTING.md")!
    public static func decode(_ data: Data, allowImports: Bool = false) throws -> Self {
        guard data.count <= 512_000 else { throw ProjectError("The skills catalog is too large.") }
        let value = try JSONDecoder().decode(Self.self, from: data)
        guard value.schemaVersion == 1, value.skills.count <= 500,
              Set(value.skills.map(\.id)).count == value.skills.count,
              Set(value.skills.map { $0.name.lowercased() }).count == value.skills.count else { throw ProjectError("Invalid skills catalog.") }
        for entry in value.skills {
            guard SkillMetadata.validName(entry.name), !entry.id.isEmpty, entry.id.count <= 160,
                  !entry.description.isEmpty, entry.description.count <= 1024,
                  !entry.author.isEmpty, !entry.license.isEmpty,
                  entry.source.archiveURL != nil, !entry.compatibleClients.isEmpty,
                  Set(entry.compatibleClients).count == entry.compatibleClients.count,
                  allowImports || entry.classification != .imported,
                  entry.bundled || entry.source.archiveSHA256.map(SkillSource.isHash) == true else {
                throw ProjectError("A skill needs valid metadata, compatibility, a pinned public source and checksum.")
            }
            if entry.source.directory != "." { try ProjectFiles.validateRelativePath(entry.source.directory) }
            if entry.bundled {
                guard entry.id == "builtin:" + entry.name, entry.source.repository == "https://github.com/thierryc/Glyphs-mcp",
                      entry.source.directory == "skills/" + entry.name else { throw ProjectError("Invalid included skill.") }
            }
        }
        return value
    }
    /// Bundled entries always come from this app's snapshot, never remote metadata.
    public func includingBundled(_ bundled: Self) throws -> Self {
        let included = bundled.skills.filter(\.bundled)
        let names = Set(included.map(\.name))
        guard !skills.contains(where: { !$0.bundled && names.contains($0.name) }) else { throw ProjectError("A catalog skill conflicts with an included skill.") }
        return Self(skills: included + skills.filter { !$0.bundled })
    }
}

public struct SkillMetadata: Equatable, Sendable {
    public let name: String
    public let description: String
    public static func validName(_ value: String) -> Bool {
        value.count <= 64 && value.range(of: #"^[a-z0-9]+(?:-[a-z0-9]+)*$"#, options: .regularExpression) != nil
    }
    /// Reads the standard required fields without evaluating YAML tags or programs.
    public static func parse(_ data: Data) throws -> Self {
        guard data.count <= 1_000_000, let text = String(data: data, encoding: .utf8) else { throw ProjectError("SKILL.md must be bounded UTF-8 text.") }
        let lines = text.replacingOccurrences(of: "\r\n", with: "\n").components(separatedBy: "\n")
        guard lines.first == "---", let end = lines.dropFirst().firstIndex(of: "---") else { throw ProjectError("SKILL.md needs YAML frontmatter.") }
        var fields: [String: String] = [:]
        var index = 1
        while index < end {
            let line = lines[index]; index += 1
            if line.first?.isWhitespace == true || line.hasPrefix("#") || line.isEmpty { continue }
            guard let colon = line.firstIndex(of: ":") else { continue }
            let key = String(line[..<colon]); guard key == "name" || key == "description" else { continue }
            guard fields[key] == nil else { throw ProjectError("Duplicate skill metadata field.") }
            var value = String(line[line.index(after: colon)...]).trimmingCharacters(in: .whitespaces)
            if [">", ">-", "|", "|-", ">+", "|+"].contains(value) {
                let separator = value.hasPrefix(">") ? " " : "\n"
                var chunks: [String] = []
                while index < end && (lines[index].first?.isWhitespace == true || lines[index].isEmpty) {
                    chunks.append(lines[index].trimmingCharacters(in: .whitespaces)); index += 1
                }
                value = chunks.joined(separator: separator).trimmingCharacters(in: .whitespacesAndNewlines)
            } else if value.hasPrefix("\"") {
                guard let decoded = try? JSONDecoder().decode(String.self, from: Data(value.utf8)) else { throw ProjectError("Invalid quoted skill metadata.") }
                value = decoded
            } else if value.hasPrefix("'") {
                guard value.hasSuffix("'"), value.count >= 2 else { throw ProjectError("Invalid quoted skill metadata.") }
                value = String(value.dropFirst().dropLast()).replacingOccurrences(of: "''", with: "'")
            } else {
                guard !value.hasPrefix("!"), !value.hasPrefix("&"), !value.hasPrefix("*"), !value.hasPrefix("["), !value.hasPrefix("{") else {
                    throw ProjectError("Use plain or quoted name and description metadata.")
                }
                if let comment = value.range(of: " #") { value = String(value[..<comment.lowerBound]) }
            }
            fields[key] = value
        }
        guard let name = fields["name"], validName(name), let description = fields["description"], !description.isEmpty, description.count <= 1024 else {
            throw ProjectError("SKILL.md needs a valid name and description.")
        }
        return .init(name: name, description: description)
    }
    public static func validate(_ files: [ProjectFile], expectedName: String? = nil, bundled: Bool = false) throws -> Self {
        guard let data = files.first(where: { $0.path == "SKILL.md" })?.data else { throw ProjectError("The folder is missing SKILL.md.") }
        let metadata = try parse(data)
        guard expectedName == nil || expectedName == metadata.name else { throw ProjectError("The skill name differs from its catalog entry.") }
        var paths = Set<String>()
        for file in files {
            try ProjectFiles.validateRelativePath(file.path)
            guard paths.insert(file.path.precomposedStringWithCanonicalMapping.lowercased()).inserted else { throw ProjectError("Duplicate skill paths.") }
        }
        if !bundled {
            let links = try NSRegularExpression(pattern: #"\]\(([^\s)]+)(?:\s+[^)]*)?\)"#)
            for file in files where file.path.hasSuffix(".md") {
                guard let data = file.data, let text = String(data: data, encoding: .utf8) else { continue }
                for match in links.matches(in: text, range: NSRange(text.startIndex..., in: text)) {
                    guard let range = Range(match.range(at: 1), in: text) else { continue }
                    let link = String(text[range])
                    if link.hasPrefix("#") || URL(string: link)?.scheme != nil { continue }
                    var path = String(link.split(separator: "#", maxSplits: 1)[0]).removingPercentEncoding ?? link
                    if path.hasPrefix("./") { path = String(path.dropFirst(2)) }
                    guard !path.hasPrefix("/"), !path.contains("\\") else { throw ProjectError("Unsafe skill reference.") }
                    var parts = (file.path as NSString).deletingLastPathComponent.split(separator: "/").map(String.init)
                    for component in path.split(separator: "/", omittingEmptySubsequences: false) {
                        if component == "." { continue }
                        if component == ".." {
                            guard !parts.isEmpty else { throw ProjectError("A reference leaves the skill folder.") }
                            parts.removeLast()
                        } else { parts.append(String(component)) }
                    }
                    let relative = parts.joined(separator: "/")
                    try ProjectFiles.validateRelativePath(relative)
                    guard files.contains(where: { $0.path == relative }) else { throw ProjectError("Missing referenced skill file: " + relative) }
                }
            }
        }
        return metadata
    }
}
