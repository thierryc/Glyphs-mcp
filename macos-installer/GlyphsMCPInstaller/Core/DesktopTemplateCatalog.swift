import Foundation

public extension DesktopTemplateChoice {
    var catalogID: String {
        switch self {
        case .starter: return "builtin:starter"
        case .registry(let id): return "registry:" + id
        case .local(let path): return "local:" + URL(fileURLWithPath: path).standardizedFileURL.path
        }
    }
}

public struct DesktopTemplateEntry: Identifiable {
    public let choice: DesktopTemplateChoice
    public let name: String
    public let description: String
    public let template: ProjectTemplate?
    public var id: String { choice.catalogID }
    public var source: String {
        switch choice {
        case .starter: return "Built-in"
        case .registry: return template?.isBundled == true ? "Built-in" : "GitHub"
        case .local: return "Local"
        }
    }
    public var localURL: URL? {
        guard case .local(let path) = choice else { return nil }
        return URL(fileURLWithPath: path).standardizedFileURL
    }

    public static func catalog(templates: [ProjectTemplate], localPaths: [String],
                               favorites: DesktopTemplateFavorites) -> [Self] {
        var entries = [Self(choice: .starter, name: "Font Project Starter",
                            description: "Folders for font sources, proofs, exports, and documentation.", template: nil)]
        entries += templates.map { Self(choice: .registry($0.id), name: $0.name, description: $0.description, template: $0) }
        entries += localPaths.filter { $0.hasPrefix("/") }.map {
            let url = URL(fileURLWithPath: $0).standardizedFileURL
            return Self(choice: .local(url.path), name: url.lastPathComponent,
                        description: "Create a project from your editable template folder.", template: nil)
        }
        var seen = Set<String>()
        return entries.filter { seen.insert($0.id).inserted }.sorted { left, right in
            let leftFavorite = favorites.contains(left.choice), rightFavorite = favorites.contains(right.choice)
            if leftFavorite != rightFavorite { return leftFavorite }
            let comparison = left.name.localizedStandardCompare(right.name)
            return comparison == .orderedSame ? left.id < right.id : comparison == .orderedAscending
        }
    }
}

public struct DesktopTemplateFavorites {
    private var ids: Set<String>
    private static let key = "favoriteTemplateIDs"

    public init(defaults: UserDefaults) {
        ids = Set(defaults.stringArray(forKey: Self.key) ?? [])
    }
    public func contains(_ choice: DesktopTemplateChoice) -> Bool { ids.contains(choice.catalogID) }
    public mutating func toggle(_ choice: DesktopTemplateChoice) {
        if ids.remove(choice.catalogID) == nil { ids.insert(choice.catalogID) }
    }
    public func save(to defaults: UserDefaults) {
        // Keep absent registry entries so a refresh or temporary offline state never loses favorites.
        defaults.set(ids.sorted(), forKey: Self.key)
    }
}
