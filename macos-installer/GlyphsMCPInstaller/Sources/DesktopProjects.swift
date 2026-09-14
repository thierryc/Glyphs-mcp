import AppKit
import SwiftUI
import GlyphsMCPInstallerCore

struct DesktopProjectCreation: Identifiable {
    let id = UUID()
    let template: DesktopTemplateChoice
}

struct DesktopProjectEditing: Identifiable {
    let id: String
}

@MainActor
final class DesktopProjectsModel: ObservableObject {
    @Published private(set) var navigation: DesktopProjectNavigation
    @Published private(set) var localTemplates: [String]
    @Published private(set) var templates: [ProjectTemplate] = []
    @Published var creation: DesktopProjectCreation?
    @Published var editing: DesktopProjectEditing?
    @Published private(set) var git: GitObservation?
    @Published private(set) var gitMessage = ""
    @Published private(set) var diff = ""
    @Published private(set) var inspecting = false
    @Published private(set) var loadingTemplates = false
    @Published private(set) var message = ""
    let store = TemplateStore()
    private let defaults: UserDefaults
    private let gitReader = ReadOnlyGit()
    private var inspection: Task<Void, Never>?
    var selectedProject: String? { navigation.selectedProject }

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        navigation = DesktopProjectNavigation(defaults: defaults, hasInstallation: DesktopInstallation().hasInstallation)
        localTemplates = defaults.stringArray(forKey: "localTemplates") ?? []
    }
    func select(_ destination: DesktopDestination?) {
        let previous = selectedProject
        navigation.select(destination); navigation.save(to: defaults)
        if selectedProject != previous { inspect() }
    }
    func loadTemplates(refresh: Bool = false) async {
        guard !loadingTemplates else { return }
        loadingTemplates = true
        defer { loadingTemplates = false }
        do {
            let registry = try await (refresh ? store.refreshRegistry() : store.registry())
            try Task.checkCancellation()
            templates = registry.templates; message = ""
        } catch { if !Task.isCancelled { message = error.localizedDescription } }
    }
    func refreshTemplates() { Task { await loadTemplates(refresh: true) } }
    func create(_ template: DesktopTemplateChoice = .starter) { creation = DesktopProjectCreation(template: template) }
    func templateName(_ choice: DesktopTemplateChoice) -> String {
        switch choice {
        case .starter: return "Font Project Starter"
        case .registry(let id): return templates.first(where: { $0.id == id })?.name ?? "Project template"
        case .local(let path): return URL(fileURLWithPath: path).lastPathComponent
        }
    }
    func files(for choice: DesktopTemplateChoice) async throws -> [ProjectFile] {
        switch choice {
        case .starter: return ProjectFiles.starter(agents: StarterProjectCreator.builtinTemplate)
        case .registry(let id):
            guard let template = templates.first(where: { $0.id == id }) else { throw ProjectError("Choose a template from the current catalog.") }
            return try await store.files(template)
        case .local(let path):
            return try await ProjectFiles.perform { try ProjectFiles.read(URL(fileURLWithPath: path)) }
        }
    }
    func addProject(_ url: URL) {
        select(.project(url.standardizedFileURL.path))
        defaults.set(true, forKey: "projectsExpanded")
    }
    func edit(_ path: String) { editing = DesktopProjectEditing(id: path) }
    func remove(_ path: String) {
        let previous = selectedProject
        navigation.remove(path); navigation.save(to: defaults)
        if editing?.id == path { editing = nil }
        if selectedProject != previous { inspect() }
    }
    func update(_ path: String, name: String, folder: URL) throws {
        let previous = selectedProject
        try navigation.update(path, name: name, folder: folder)
        navigation.save(to: defaults)
        if selectedProject != previous { inspect() }
    }
    func folderExists(_ path: String) -> Bool {
        var directory: ObjCBool = false
        return FileManager.default.fileExists(atPath: path, isDirectory: &directory) && directory.boolValue
    }
    func showInFinder(_ path: String) {
        guard folderExists(path) else { return }
        NSWorkspace.shared.open(URL(fileURLWithPath: path))
    }
    func chooseProject() {
        let panel = Self.folderPanel("Open Project Folder")
        panel.begin { [weak self] response in if response == .OK, let url = panel.url { self?.addProject(url) } }
    }
    func chooseTemplate() {
        let panel = Self.folderPanel("Choose Local Template")
        panel.begin { [weak self] response in
            guard response == .OK, let url = panel.url, let self else { return }
            self.rememberTemplate(url); self.select(.templates)
        }
    }
    func rememberTemplate(_ url: URL) {
        let path = url.standardizedFileURL.path
        if !localTemplates.contains(path) { localTemplates.append(path) }
        defaults.set(localTemplates, forKey: "localTemplates")
    }
    func inspect() {
        inspection?.cancel(); git = nil; diff = ""; gitMessage = ""; inspecting = false
        guard let project = selectedProject else { return }
        guard folderExists(project) else {
            gitMessage = "Project folder not found. Choose Edit to locate it."
            return
        }
        inspecting = true
        inspection = Task {
            do {
                let observation = try await gitReader.inspect(URL(fileURLWithPath: project))
                guard !Task.isCancelled, selectedProject == project else { return }
                git = observation
            } catch { if !Task.isCancelled, selectedProject == project { gitMessage = error.localizedDescription } }
            if !Task.isCancelled, selectedProject == project { inspecting = false }
        }
    }
    func showDiff(_ path: String) {
        guard let project = selectedProject else { return }
        inspection?.cancel(); inspecting = true; diff = ""
        inspection = Task {
            do {
                let value = try await gitReader.diff(URL(fileURLWithPath: project), path: path)
                if !Task.isCancelled, selectedProject == project { diff = value }
            } catch { if !Task.isCancelled, selectedProject == project { gitMessage = error.localizedDescription } }
            if !Task.isCancelled, selectedProject == project { inspecting = false }
        }
    }
    func openExternal(_ key: String) {
        guard let selectedProject else { return }
        let folder = URL(fileURLWithPath: selectedProject)
        if let path = defaults.string(forKey: key), FileManager.default.fileExists(atPath: path) {
            NSWorkspace.shared.open([folder], withApplicationAt: URL(fileURLWithPath: path), configuration: NSWorkspace.OpenConfiguration(), completionHandler: nil)
        } else {
            let panel = NSOpenPanel(); panel.title = "Choose an application"; panel.allowedContentTypes = [.applicationBundle]
            panel.directoryURL = URL(fileURLWithPath: "/Applications")
            panel.begin { [weak self] response in
                if response == .OK, let app = panel.url {
                    self?.defaults.set(app.path, forKey: key)
                    NSWorkspace.shared.open([folder], withApplicationAt: app, configuration: NSWorkspace.OpenConfiguration(), completionHandler: nil)
                }
            }
        }
    }
    static func folderPanel(_ title: String) -> NSOpenPanel {
        let panel = NSOpenPanel(); panel.title = title; panel.canChooseDirectories = true; panel.canChooseFiles = false
        panel.canCreateDirectories = true; return panel
    }
}

struct DesktopProjectWorkspace: View {
    @ObservedObject var model: DesktopProjectsModel
    let path: String
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                HStack(alignment: .top, spacing: 16) {
                    Image(systemName: "folder.fill").font(.system(size: 34)).foregroundStyle(Color.accentColor)
                    VStack(alignment: .leading, spacing: 6) {
                        Text(model.navigation.name(for: path)).font(.largeTitle.bold())
                        Text(path).font(.callout).foregroundStyle(.secondary).textSelection(.enabled)
                    }
                    Spacer()
                }
                HStack(spacing: 10) {
                    Group {
                        Button("Open in Finder") { model.showInFinder(path) }
                        Button("Open in Editor…") { model.openExternal("projectEditor") }
                        Button("Open in Git Client…") { model.openExternal("projectGitClient") }
                    }.disabled(!model.folderExists(path))
                    Spacer(minLength: 0)
                    Button { model.edit(path) } label: { Label("Edit", systemImage: "pencil") }
                        .help("Edit project settings")
                }
                GroupBox {
                    VStack(alignment: .leading, spacing: 14) {
                        HStack {
                            Label("Git information", systemImage: "arrow.triangle.branch").font(.headline)
                            Spacer()
                            Button(action: model.inspect) { Image(systemName: "arrow.clockwise") }
                                .help("Refresh Git information").accessibilityLabel("Refresh Git information").disabled(model.inspecting)
                        }
                        if let git = model.git {
                            HStack {
                                Text(git.branch).fontWeight(.medium)
                                Spacer()
                                Text(git.changes.isEmpty ? "Working tree is clean" : "\(git.changes.count) changed files").foregroundStyle(.secondary)
                            }
                            if !git.changes.isEmpty {
                                Divider()
                                LazyVStack(alignment: .leading, spacing: 8) {
                                    ForEach(git.changes) { change in
                                        Button { model.showDiff(change.path) } label: {
                                            HStack { Text(change.status).monospaced().foregroundStyle(.secondary); Text(change.path); Spacer() }
                                        }.buttonStyle(.plain)
                                    }
                                }
                            }
                        } else {
                            Text(model.gitMessage.isEmpty ? "Reading local Git information…" : model.gitMessage).foregroundStyle(.secondary)
                        }
                        if !model.diff.isEmpty {
                            Divider()
                            ScrollView([.horizontal, .vertical]) {
                                Text(model.diff).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }.frame(maxHeight: 300)
                        }
                    }.padding(12).frame(maxWidth: .infinity, alignment: .leading)
                }
            }.padding(32).frame(maxWidth: 900, alignment: .leading).frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}
