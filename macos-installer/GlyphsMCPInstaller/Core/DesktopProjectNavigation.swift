import Foundation

public enum DesktopDestination: Hashable {
    case setup, tasks, companions, agents, skills, templates
    case project(String)
}

/// Browsing templates does not forget the last project. The remembered project
/// is a launch fallback, separate from the explicit Templates destination.
public struct DesktopProjectNavigation: Equatable {
    public private(set) var recent: [String]
    public private(set) var lastProject: String?
    public private(set) var destination: DesktopDestination
    private var names: [String: String]
    private var legacySkillFolders: Set<String>
    private var projectSkillInstallations: [String: Set<String>]
    public var selectedProject: String? {
        if case .project(let path) = destination { return path }
        return nil
    }

    /// Present projects by their displayed names while retaining `recent` as
    /// the persistence and eviction order.
    public var alphabetizedProjects: [String] {
        alphabetized(recent)
    }

    public var skillProjects: [String] {
        alphabetized(Set(recent).union(legacySkillFolders).union(projectSkillInstallations.keys))
    }

    private func alphabetized(_ paths: some Sequence<String>) -> [String] {
        paths.sorted { left, right in
            switch name(for: left).localizedStandardCompare(name(for: right)) {
            case .orderedAscending:
                return true
            case .orderedDescending:
                return false
            case .orderedSame:
                return left.localizedStandardCompare(right) == .orderedAscending
            }
        }
    }

    public init(defaults: UserDefaults, hasInstallation: Bool) {
        var seen = Set<String>()
        let normalized = (defaults.stringArray(forKey: "recentProjects") ?? []).filter { $0.hasPrefix("/") }
            .map { URL(fileURLWithPath: $0).standardizedFileURL.path }
            .filter { seen.insert($0).inserted }
        let restored = Array(normalized.prefix(12))
        recent = restored
        names = (defaults.dictionary(forKey: "projectDisplayNames") as? [String: String] ?? [:])
            .filter { restored.contains($0.key) && !$0.value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        legacySkillFolders = Set((defaults.stringArray(forKey: "skillProjectFolders") ?? [])
            .filter { $0.hasPrefix("/") }.map { URL(fileURLWithPath: $0).standardizedFileURL.path })
        let remembered = defaults.dictionary(forKey: "projectSkillInstallations") as? [String: [String]] ?? [:]
        projectSkillInstallations = remembered.filter { $0.key.hasPrefix("/") && !$0.value.isEmpty }.mapValues(Set.init)
        let stored = defaults.string(forKey: "lastSelectedProject")
        lastProject = stored.flatMap { restored.contains($0) ? $0 : nil } ?? restored.first
        destination = hasInstallation ? lastProject.map(DesktopDestination.project) ?? .setup : .setup
    }

    public mutating func select(_ value: DesktopDestination?) {
        destination = value ?? lastProject.map(DesktopDestination.project) ?? .templates
        if case .project(let path) = destination {
            let path = URL(fileURLWithPath: path).standardizedFileURL.path
            rememberProject(URL(fileURLWithPath: path, isDirectory: true))
            destination = .project(path)
        }
    }

    /// Remember a folder selected in the skill manager without leaving Skills.
    public mutating func rememberProject(_ folder: URL) {
        let path = folder.standardizedFileURL.path
        recent.removeAll { $0 == path }
        recent.insert(path, at: 0)
        recent = Array(recent.prefix(12))
        names = names.filter { recent.contains($0.key) }
        lastProject = path
    }

    public func name(for path: String) -> String {
        names[path] ?? URL(fileURLWithPath: path).lastPathComponent
    }

    public func lastKnownSkillInstallation(_ skillID: String, in projectPath: String) -> Bool {
        projectSkillInstallations[projectPath]?.contains(skillID) == true
    }

    /// Each scan reports accessible folders only. Preserve the last known copies of offline projects.
    public mutating func recordProjectSkillInstallations(_ installations: [String: Set<String>]) {
        for (path, skillIDs) in installations {
            projectSkillInstallations[path] = skillIDs.isEmpty ? nil : skillIDs
        }
    }

    /// Forget only the app's registration; project files are never removed.
    public mutating func remove(_ path: String) {
        recent.removeAll { $0 == path }
        names.removeValue(forKey: path)
        if lastProject == path { lastProject = recent.first }
        if selectedProject == path { destination = lastProject.map(DesktopDestination.project) ?? .templates }
    }

    /// Update the displayed name and reconnect a moved folder without moving files.
    public mutating func update(_ path: String, name: String, folder: URL) throws {
        guard let index = recent.firstIndex(of: path) else { throw ProjectError("This project is no longer in the list.") }
        let name = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { throw ProjectError("Enter a project name.") }
        guard folder.isFileURL else { throw ProjectError("Choose a local project folder.") }
        let updated = folder.standardizedFileURL.path
        if updated != path {
            guard !recent.contains(updated) else { throw ProjectError("That folder is already in My Project.") }
            var directory: ObjCBool = false
            guard FileManager.default.fileExists(atPath: updated, isDirectory: &directory), directory.boolValue else {
                throw ProjectError("Choose an existing project folder.")
            }
        }
        recent[index] = updated
        names.removeValue(forKey: path)
        names[updated] = name == folder.lastPathComponent ? nil : name
        if lastProject == path { lastProject = updated }
        if selectedProject == path { destination = .project(updated) }
    }

    public func save(to defaults: UserDefaults) {
        defaults.set(recent, forKey: "recentProjects")
        defaults.set(lastProject, forKey: "lastSelectedProject")
        defaults.set(names, forKey: "projectDisplayNames")
        defaults.set(projectSkillInstallations.mapValues { $0.sorted() }, forKey: "projectSkillInstallations")
    }
}

public enum DesktopTemplateChoice: Hashable {
    case starter
    case registry(String)
    case local(String)
}
