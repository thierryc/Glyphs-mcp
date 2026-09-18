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

enum DesktopGlyphDiffMode: String, CaseIterable, Identifiable {
    case visual = "Visual"
    case text = "Text"
    var id: String { rawValue }
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
    @Published private(set) var selectedChange: GitObservation.Change?
    @Published private(set) var comparison: GitFileComparison?
    @Published private(set) var comparisonMessage = ""
    @Published private(set) var glyphDiff: GlyphDiffDocument?
    @Published private(set) var glyphMessage = ""
    @Published private(set) var loadingComparison = false
    @Published private(set) var loadingGlyphDiff = false
    @Published var glyphMode: DesktopGlyphDiffMode = .visual
    @Published private(set) var inspecting = false
    @Published private(set) var loadingTemplates = false
    @Published private(set) var message = ""
    let store = TemplateStore()
    private let defaults: UserDefaults
    private let gitReader = ReadOnlyGit()
    private let glyphReader = GlyphDiffService()
    private var inspection: Task<Void, Never>?
    private var comparisonTask: Task<Void, Never>?
    private var glyphRetryTask: Task<Void, Never>?
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
        let selectedPath = selectedChange?.path
        inspection?.cancel(); comparisonTask?.cancel(); glyphRetryTask?.cancel()
        git = nil; gitMessage = ""; inspecting = false
        comparison = nil; glyphDiff = nil; comparisonMessage = ""; glyphMessage = ""
        loadingComparison = false; loadingGlyphDiff = false
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
                if let change = observation.changes.first(where: { $0.path == selectedPath }) ?? observation.changes.first {
                    selectChange(change)
                } else {
                    selectedChange = nil
                }
            } catch { if !Task.isCancelled, selectedProject == project { gitMessage = error.localizedDescription } }
            if !Task.isCancelled, selectedProject == project { inspecting = false }
        }
    }
    func showDiff(_ path: String) {
        guard let change = git?.changes.first(where: { $0.path == path }) else { return }
        selectChange(change)
    }
    func selectChange(_ change: GitObservation.Change) {
        guard let project = selectedProject, let git else { return }
        comparisonTask?.cancel(); glyphRetryTask?.cancel()
        selectedChange = change
        comparison = nil; glyphDiff = nil; comparisonMessage = ""; glyphMessage = ""
        loadingComparison = true; loadingGlyphDiff = change.isGlyphPackageGlyph
        comparisonTask = Task {
            do {
                async let glyphValueTask: GlyphDiffDocument? = change.isGlyphPackageGlyph
                    ? glyphReader.compare(project: URL(fileURLWithPath: project), change: change, headRevision: git.headRevision)
                    : nil
                let value = try await gitReader.comparison(URL(fileURLWithPath: project), change: change, headRevision: git.headRevision)
                guard !Task.isCancelled, selectedProject == project, selectedChange?.path == change.path else { return }
                comparison = value
                loadingComparison = false
                let glyphValue: GlyphDiffDocument?
                if change.isGlyphPackageGlyph {
                    do { glyphValue = try await glyphValueTask }
                    catch {
                        glyphValue = nil
                        if !Task.isCancelled, selectedProject == project, selectedChange?.path == change.path {
                            glyphMessage = error.localizedDescription
                            glyphMode = .text
                        }
                    }
                } else { glyphValue = nil }
                guard !Task.isCancelled, selectedProject == project, selectedChange?.path == change.path else { return }
                glyphDiff = glyphValue
            } catch {
                if !Task.isCancelled, selectedProject == project, selectedChange?.path == change.path {
                    comparisonMessage = error.localizedDescription
                }
            }
            if !Task.isCancelled, selectedProject == project, selectedChange?.path == change.path {
                loadingComparison = false
                loadingGlyphDiff = false
            }
        }
    }
    func retryGlyphPreview() {
        guard let project = selectedProject, let git, let change = selectedChange,
              change.isGlyphPackageGlyph else { return }
        glyphRetryTask?.cancel()
        glyphDiff = nil; glyphMessage = ""; loadingGlyphDiff = true; glyphMode = .visual
        let headRevision = git.headRevision
        glyphRetryTask = Task {
            do {
                let value = try await glyphReader.compare(
                    project: URL(fileURLWithPath: project), change: change, headRevision: headRevision
                )
                guard !Task.isCancelled, selectedProject == project,
                      selectedChange?.path == change.path else { return }
                glyphDiff = value
            } catch {
                guard !Task.isCancelled, selectedProject == project,
                      selectedChange?.path == change.path else { return }
                glyphMessage = error.localizedDescription
                glyphMode = .text
            }
            if !Task.isCancelled, selectedProject == project, selectedChange?.path == change.path {
                loadingGlyphDiff = false
            }
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
        VStack(alignment: .leading, spacing: 18) {
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
            DesktopGitWorkspace(model: model)
        }
        .padding(.horizontal, 28).padding(.top, 28).padding(.bottom, 18)
    }
}
