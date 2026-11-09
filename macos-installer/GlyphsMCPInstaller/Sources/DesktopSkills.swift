import AppKit
import SwiftUI
import GlyphsMCPInstallerCore

@MainActor
final class DesktopSkillsModel: ObservableObject {
    @Published private(set) var skills: [CatalogSkill] = []
    @Published private(set) var busy = false
    @Published private(set) var scanning = false
    @Published var message = ""
    @Published private(set) var messageIsError = false
    @Published private(set) var operationDetails = ""
    @Published private(set) var activeSkillID: String?
    @Published private(set) var activeOperation: SetupOperation?
    @Published private(set) var catalogMessage = ""
    @Published var selected: CatalogSkill?
    @Published private(set) var files: [ProjectFile] = []
    @Published var search = ""
    @Published var category = "All"
    @Published var client: SkillClient?
    @Published private(set) var global: [String: SkillScopeStatus] = [:]
    @Published private(set) var projectScopes: [URL: [String: SkillScopeStatus]] = [:]
    private var projectFolders: [URL] = []
    private weak var projects: DesktopProjectsModel?
    private var packageVersion: SkillPackageVersion?
    private let store = SkillStore()
    var pendingInspection: CatalogSkill?
    private var snapshot: Data?
    private var catalogEntries: [CatalogSkill] = []
    private var importEntries: [CatalogSkill] = []
    private var task: Task<Void, Never>?
    private var scanGeneration = 0
    private var installer: SupplementalSkillInstaller { .init(bundledNames: Set(catalogEntries.filter(\.bundled).map(\.name))) }
    var filtered: [CatalogSkill] {
        skills.filter { skill in
            (search.isEmpty || (skill.title + " " + skill.name + " " + skill.description + " " + skill.author).localizedCaseInsensitiveContains(search)) &&
            (client == nil || skill.compatibleClients.contains(client!)) &&
            (category == "All" || category == "Included" && skill.bundled || category == "Additional" && !skill.bundled || category == "Installed" && isInstalled(skill))
        }.sorted { ($0.bundled ? 0 : 1, $0.title) < ($1.bundled ? 0 : 1, $1.title) }
    }
    func isInstalled(_ skill: CatalogSkill) -> Bool {
        hasGlobalInstallation(skill) || projectScopes.values.contains { scopes in
            scopes[skill.id]?.editableCopies.isEmpty == false
        }
    }

    private var projectSkillInstallations: [String: Set<String>] {
        Dictionary(uniqueKeysWithValues: projectScopes.map { folder, scopes in
            (folder.path, Set(scopes.keys.filter { scopes[$0]?.editableCopies.isEmpty == false }))
        })
    }

    func hasUpdate(_ skill: CatalogSkill) -> Bool {
        let scopes = [global[skill.id]].compactMap { $0 } + projectScopes.values.compactMap { $0[skill.id] }
        return scopes.contains { $0.editableCopies.contains { $0.status.state == .updateAvailable } }
    }

    func hasGlobalInstallation(_ skill: CatalogSkill) -> Bool {
        guard let scope = global[skill.id] else { return false }
        return scope.agents.contains { !scope.installed(for: $0).isEmpty }
    }
    func load(refresh: Bool = false) {
        guard !busy else { return }; busy = true
        task = Task {
            defer { busy = false }
            do {
                if snapshot == nil {
                    guard let url = Bundle.main.url(forResource: "registry", withExtension: "json", subdirectory: "SkillsCatalog") else { throw ProjectError("The bundled skills catalog is missing.") }
                    snapshot = try Data(contentsOf: url)
                }
                catalogEntries = try await store.catalog(snapshot: snapshot!, refresh: refresh).skills
                importEntries = try await store.imports()
                rescan()
                catalogMessage = refresh ? "Skills catalog refreshed." : ""
            } catch { catalogMessage = error.localizedDescription }
        }
    }
    func rescan() {
        scanGeneration += 1
        let generation = scanGeneration
        scanning = true
        let catalog = catalogEntries
        let imports = importEntries
        let folders = projectFolders
        let selected = selected
        let packageVersion = packageVersion
        let service = installer
        Task {
            let (entries, scopes, projectScopes, warning) = await Task.detached(priority: .userInitiated) {
                var entries = catalog
                var warning = ""
                let placements = SkillPlacement.allCases.filter { $0 != .cursorPlugin }
                let projectRoots = Dictionary(uniqueKeysWithValues: folders.compactMap { folder -> (URL, [URL])? in
                    var isDirectory: ObjCBool = false
                    guard FileManager.default.fileExists(atPath: folder.path, isDirectory: &isDirectory),
                          isDirectory.boolValue else {
                        return nil
                    }
                    return (folder, placements.map { folder.appendingPathComponent($0.rawValue) })
                })
                let roots = placements.map { service.home.appendingPathComponent($0.rawValue) }
                    + projectRoots.values.flatMap { $0 }
                for entry in imports where !entries.contains(where: { $0.id == entry.id || $0.name == entry.name }) {
                    entries.append(entry)
                }
                for root in roots where FileManager.default.fileExists(atPath: root.path) {
                    do {
                        try SupplementalSkillInstaller.regularAncestors(root)
                        try service.recover(root: root)
                        for receipt in try service.installed(in: root) where !entries.contains(where: {
                            $0.id == receipt.skill.id || $0.name == receipt.skill.name
                        }) {
                            entries.append(receipt.skill)
                        }
                    } catch {
                        warning = error.localizedDescription
                    }
                }
                let scopes = Dictionary(uniqueKeysWithValues: entries.map { skill in
                    (skill.id, service.scopeStatus(skill, package: skill.id == selected?.id ? packageVersion : nil))
                })
                let projectScopes = projectRoots.map { folder, roots in
                    let present = Set(roots.flatMap { (try? FileManager.default.contentsOfDirectory(atPath: $0.path)) ?? [] })
                    let candidates = entries.filter { present.contains($0.name) }
                    let statuses = Dictionary(uniqueKeysWithValues: candidates.map { skill in
                        (skill.id, service.scopeStatus(skill, project: folder,
                                                       package: skill.id == selected?.id ? packageVersion : nil))
                    })
                    return (folder, statuses)
                }
                return (entries, scopes, Dictionary(uniqueKeysWithValues: projectScopes), warning)
            }.value
            guard generation == scanGeneration else { return }
            skills = entries
            global = scopes
            self.projectScopes = projectScopes
            projects?.recordProjectSkillInstallations(projectSkillInstallations)
            if !warning.isEmpty { operationDetails = warning }
            scanning = false
        }
    }

    func prepareProjects(_ projects: DesktopProjectsModel) {
        self.projects = projects
        var seen = Set<URL>()
        projectFolders = projects.navigation.skillProjects
            .map { URL(fileURLWithPath: $0, isDirectory: true).standardizedFileURL }
            .filter { seen.insert($0).inserted }
    }

    func inspect(_ skill: CatalogSkill) {
        guard !busy else { return }
        selected = skill
        files = []
        packageVersion = nil
        busy = true
        message = "Loading skill…"
        messageIsError = false
        operationDetails = ""
        rescan()
        task = Task {
            defer { busy = false; rescan() }
            do {
                let bundledRoot: URL?
                if skill.bundled {
                    let payload = try await InstallerPayloadDiscovery.shared.resolve { try InstallerPayload.resolve() }
                    guard let folder = payload.managedSkillDirectories().first(where: { $0.lastPathComponent == skill.name }) else {
                        throw ProjectError("This skill is missing from the app’s verified payload.")
                    }
                    bundledRoot = folder.deletingLastPathComponent()
                } else {
                    bundledRoot = nil
                }
                let package = try await store.files(skill, bundledRoot: bundledRoot)
                packageVersion = try await ProjectFiles.perform {
                    SkillPackageVersion(label: skill.version, files: package)
                }
                files = package
                message = ""
            } catch {
                message = error.localizedDescription
                messageIsError = true
            }
        }
    }

    func discover(repository: String, directory: String, revision: String) async throws -> [CatalogSkill] {
        try await store.discover(repository: repository, directory: directory.isEmpty ? "." : directory, revision: revision)
    }
    func addImport(_ skill: CatalogSkill) async throws {
        guard !catalogEntries.contains(where: { $0.name == skill.name && $0.id != skill.id }) else { throw ProjectError("This name belongs to a catalog skill. Use its reviewed entry instead.") }
        try await store.remember(skill); importEntries = try await store.imports(); rescan(); pendingInspection = skill
    }
    func change(_ operation: SkillCopyOperation, targets: [SkillCopy]? = nil, project: URL? = nil,
                using owner: InstallerViewModel, confirmed: Bool = false, forAgent agent: SkillClient? = nil) {
        guard !scanning, let skill = selected,
              targets.map({ !$0.isEmpty }) ?? (operation == .install && project != nil),
              operation == .remove || !files.isEmpty else { return }
        let package = files
        let packageVersion = packageVersion
        let service = installer
        let setupOperation: SetupOperation
        let title: String
        let success: String
        switch operation {
        case .install: (setupOperation, title, success) = (.install, "Installing skill…", "Skill installed.")
        case .reinstall: (setupOperation, title, success) = (.install, "Reinstalling skill…", "Skill reinstalled.")
        case .update: (setupOperation, title, success) = (.update, "Updating skill…", "Skill updated.")
        case .remove: (setupOperation, title, success) = (.remove, "Uninstalling skill…", "Skill uninstalled.")
        }
        run(owner, title: title, skillID: skill.id, setupOperation: setupOperation) {
            let (result, count) = try await ProjectFiles.perform {
                let destinations: [SkillCopy]
                if let targets {
                    destinations = targets
                } else {
                    let scope = service.scopeStatus(skill, project: project, package: packageVersion)
                    guard !scope.agents.isEmpty else {
                        throw ProjectError("Choose a project folder outside your default skill location.")
                    }
                    destinations = scope.missing(for: scope.agents)
                }
                let result = service.apply(operation, to: destinations, skill: skill, files: package, project: project,
                                           replace: confirmed, package: packageVersion, forAgent: agent)
                return (result, destinations.count)
            }
            let details = (result.completed + result.failures).joined(separator: "\n")
            if result.failures.isEmpty {
                return (result.completed.isEmpty ? "The skill is already installed." : success, details, false)
            }
            if result.completed.isEmpty {
                return ("No locations changed. See Advanced for details.", details, true)
            }
            return ("Changed \(result.completed.count) of \(count) locations. See Advanced for details.", details, true)
        }
    }

    func export(_ skill: CatalogSkill, owner: InstallerViewModel) {
        guard !files.isEmpty else { return }
        let panel = NSSavePanel(); panel.nameFieldStringValue = skill.name + ".zip"
        guard panel.runModal() == .OK, let destination = panel.url else { return }
        // Save panel authorizes replacing this exact export file, not skill folders.
        let package = files
        run(owner, title: "Exporting skill…") {
            let temporary = FileManager.default.temporaryDirectory.appendingPathComponent("glyphs-skill-export-" + UUID().uuidString)
            try FileManager.default.createDirectory(at: temporary, withIntermediateDirectories: false)
            defer { try? FileManager.default.removeItem(at: temporary) }
            let folder = temporary.appendingPathComponent(skill.name)
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: false)
            for file in package {
                let path = folder.appendingPathComponent(file.path)
                if let data = file.data {
                    try FileManager.default.createDirectory(at: path.deletingLastPathComponent(), withIntermediateDirectories: true)
                    try data.write(to: path)
                } else { try FileManager.default.createDirectory(at: path, withIntermediateDirectories: true) }
            }
            let zip = temporary.appendingPathComponent("export.zip")
            let result = try await ProcessRunner().runCapturing(executable: URL(fileURLWithPath: "/usr/bin/ditto"), args: ["-c", "-k", "--norsrc", "--noextattr", "--noacl", "--keepParent", folder.path, zip.path], timeout: 30)
            guard result.exitCode == 0 else { throw ProjectError("Skill export failed.") }
            let data = try Data(contentsOf: zip); _ = try TemplateArchive.validate(data)
            try data.write(to: destination, options: .atomic)
            return ("Skill ZIP exported.", destination.path, false)
        }
    }
    private func run(_ owner: InstallerViewModel, title: String, skillID: String? = nil,
                     setupOperation: SetupOperation? = nil,
                     operation: @escaping () async throws -> (String, String, Bool)) {
        guard !busy, !owner.operationsBusy else { return }
        activeSkillID = skillID
        activeOperation = setupOperation
        busy = true
        owner.supplementalSkillsBusy = true
        message = title
        messageIsError = false
        operationDetails = ""
        task = Task {
            defer {
                busy = false
                activeSkillID = nil
                activeOperation = nil
                owner.supplementalSkillsBusy = false
                rescan()
            }
            do {
                (message, operationDetails, messageIsError) = try await operation()
            } catch {
                message = error.localizedDescription
                messageIsError = true
            }
            owner.notice = .information(message)
        }
    }
}

struct DesktopFocusedSetup: View {
    @EnvironmentObject private var installer: InstallerViewModel
    let section: InstallationView.Section
    var agentToReveal: InstallerClientKind? = nil
    let showSetup: () -> Void
    var body: some View {
        ScrollViewReader { scroll in
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    Text(LocalizedStringKey(section == .companions ? "Companion Plugins" : "AI Agents")).font(.largeTitle.bold())
                    Text(LocalizedStringKey(section == .companions ? "Manage optional Glyphs plugins. The bundled inspectors require the Glyphs MCP bridge." : "Configure each AI agent independently. Download the client application separately when needed."))
                        .foregroundStyle(.secondary)
                    Button("Open Setup", action: showSetup)
                    if section == .companions && installer.running {
                        DesktopComponentPreparation()
                    }
                    InstallationView(section: section)
                }
                .padding(DesktopSetupLayout.contentPadding)
                .frame(maxWidth: DesktopSetupLayout.contentMaximumWidth, alignment: .leading)
                .frame(maxWidth: .infinity)
            }
            .onAppear {
                if let agentToReveal { scroll.scrollTo(agentToReveal, anchor: .top) }
            }
        }
    }
}

private struct SkillCardPresentation {
    let title: String
    let goal: String
    init(_ skill: CatalogSkill) {
        let goals: [String: String] = [
            "glyphs": "Find the right workflow for your next font task.",
            "glyphs-mcp-development": "Build tools that make your font work easier.",
            "glyphs-mcp-italic-first-pass": "Prepare a first slant for your italic design.",
            "glyphs-mcp-kerning": "Review the spacing between letter pairs.",
            "glyphs-mcp-maintainer-feedback": "Collect useful details for a clear bug report.",
            "glyphs-mcp-master-compatibility": "Compare contour starts across your masters.",
            "glyphs-mcp-opentype-features": "Write and check your font’s OpenType features.",
            "glyphs-mcp-outlines-docs": "Inspect curves and plan focused outline edits.",
            "glyphs-mcp-path-doctor": "Find outline problems and review suggested repairs.",
            "glyphs-mcp-release": "Check a Glyphs MCP release before publication.",
            "glyphs-mcp-scripting": "Create a focused script for a font task.",
            "glyphs-mcp-spacing": "Prepare spacing suggestions from reference letters."
        ]
        title = skill.title
        goal = skill.bundled ? goals[skill.name] ?? skill.description
            : skill.description.components(separatedBy: ". ").first ?? skill.description
    }
}

private struct DesktopSkillCard: View {
    let skill: CatalogSkill
    let installed: Bool
    let hasUpdate: Bool
    let checking: Bool
    let progress: String?
    let reviewRemoval: () -> Void
    let open: () -> Void
    private var presentation: SkillCardPresentation { .init(skill) }

    var body: some View {
        DesktopCatalogCard(previewHeight: nil, detailMinimumHeight: 48) {
            EmptyView()
        } title: {
            Text(LocalizedStringKey(presentation.title))
        } detail: {
            VStack(alignment: .leading, spacing: 4) {
                Text(LocalizedStringKey(presentation.goal))
                if skill.bundled { Text("Included with Glyphs MCP").font(.caption) }
            }
        } status: {
            DesktopStatus(title: progress ?? (checking ? "Checking installation…" : installed ? "Installed" : "Not installed"),
                tone: progress != nil ? (progress == "Uninstalling…" ? .neutral : .progress) : checking ? .neutral : installed ? .installed : .neutral,
                symbol: installed ? "checkmark.circle.fill" : "circle", spinning: checking || progress != nil)
            if hasUpdate { Text("Update available").font(.caption).foregroundStyle(.secondary) }
        } actions: {
            if skill.bundled {
                DesktopActionButton(title: "Details", action: open)
                    .accessibilityLabel("Details for " + presentation.title)
            } else {
                HStack(alignment: .bottom, spacing: 8) {
                    DesktopActionRow {
                        if let progress {
                            DesktopActionButton(title: progress, action: {}).disabled(true)
                        } else {
                            if !installed || hasUpdate {
                                DesktopActionButton(title: installed ? "Update" : "Install",
                                    symbol: installed ? "arrow.clockwise" : "arrow.down.to.line",
                                    emphasis: installed ? .secondary : .primary, action: open)
                                    .disabled(checking)
                                    .help("Choose the agent and location for this skill.")
                            }
                            if installed {
                                DesktopActionButton(title: "Uninstall…", action: reviewRemoval).disabled(checking)
                            }
                        }
                    }
                    Button("Details", action: open).buttonStyle(.link).font(.caption).fixedSize()
                        .accessibilityLabel("Details for " + presentation.title)
                }
            }
        } footer: {
            EmptyView()
        }
    }
}

struct DesktopSkillsView: View {
    @ObservedObject var model: DesktopSkillsModel
    @ObservedObject var installer: InstallerViewModel
    @ObservedObject var projects: DesktopProjectsModel
    private var navigation: DesktopProjectNavigation { projects.navigation }
    let manageAgents: () -> Void
    @State private var showingImport = false
    @State private var initialSection: String?

    private func open(_ skill: CatalogSkill, showAgentActions: Bool = false) {
        initialSection = showAgentActions ? (model.hasGlobalInstallation(skill) ? "agents" : "project") : nil
        model.inspect(skill)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                HStack(alignment: .firstTextBaseline) {
                    Text("Skills").font(.largeTitle.bold()); Spacer()
                    Button("Refresh") { model.load(refresh: true) }.disabled(model.busy)
                    Button("Add from GitHub…") { showingImport = true }.disabled(model.busy || installer.operationsBusy)
                    DesktopTextLink("Contribute", destination: SkillCatalog.contributionURL)
                }
                Text("Find a workflow for your next font task.").foregroundStyle(.secondary)
                HStack(spacing: 14) {
                    TextField("Search skills", text: $model.search).textFieldStyle(.roundedBorder)
                    Picker("Show", selection: $model.category) {
                        ForEach(["All", "Included", "Additional", "Installed"], id: \.self) { Text(LocalizedStringKey($0)).tag($0) }
                    }.frame(maxWidth: 180)
                    Picker("Agent", selection: $model.client) {
                        Text("All agents").tag(Optional<SkillClient>.none)
                        ForEach(SkillClient.allCases) { Text($0.title).tag(Optional($0)) }
                    }.frame(maxWidth: 170)
                }
                if (model.busy || model.scanning) && model.selected == nil { ProgressView().controlSize(.small) }
                if !model.catalogMessage.isEmpty { Text(LocalizedStringKey(model.catalogMessage)).font(.callout) }
                SetupCardGrid {
                    ForEach(model.filtered) { skill in
                        DesktopSkillCard(skill: skill, installed: model.isInstalled(skill),
                            hasUpdate: model.hasUpdate(skill),
                            checking: model.scanning,
                            progress: model.activeSkillID == skill.id ? (model.activeOperation == .remove ? "Uninstalling…" : model.activeOperation?.progressLabel) : nil,
                            reviewRemoval: { open(skill, showAgentActions: true) },
                            open: { open(skill) })
                            .disabled(model.busy)
                    }
                }
                if model.filtered.isEmpty && !model.busy && !model.scanning { Text("No matching skills.").foregroundStyle(.secondary) }
            }.padding(DesktopSetupLayout.contentPadding)
                .frame(maxWidth: DesktopSetupLayout.contentMaximumWidth, alignment: .leading).frame(maxWidth: .infinity)
        }
        .task {
            model.prepareProjects(projects)
            if model.skills.isEmpty { model.load() } else { model.rescan() }
        }
        .onChange(of: navigation.skillProjects) { _, _ in
            model.prepareProjects(projects)
            model.rescan()
        }
        .onChange(of: installer.busy) { _, busy in if !busy { model.rescan() } }
        .sheet(isPresented: $showingImport, onDismiss: {
            if let skill = model.pendingInspection {
                model.pendingInspection = nil
                open(skill)
            }
        }) { SkillImportSheet(model: model) }
        .sheet(item: $model.selected) { skill in
            SkillDetailsSheet(skill: skill, model: model, installer: installer, initialSection: initialSection,
                              projects: projects) {
                model.selected = nil
                manageAgents()
            }
        }
    }
}

private struct SkillDetailsSheet: View {
    let skill: CatalogSkill
    @ObservedObject var model: DesktopSkillsModel
    @ObservedObject var installer: InstallerViewModel
    let initialSection: String?
    @ObservedObject var projects: DesktopProjectsModel
    private var navigation: DesktopProjectNavigation { projects.navigation }
    let managePlugin: () -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var confirmation: Confirmation?
    @State private var previewPath = "SKILL.md"
    @State private var projectFilter = ""

    private struct Confirmation {
        let operation: SkillCopyOperation
        let targets: [SkillCopy]
        let project: URL?

        var actionTitle: String {
            switch operation {
            case .remove: return project == nil ? "Uninstall" : "Remove from project"
            case .reinstall: return "Reinstall"
            case .update: return targets.contains { $0.status.state == .updateAvailable } ? "Update" : "Replace"
            case .install: return "Install"
            }
        }

        var title: LocalizedStringKey {
            if operation == .remove, let project {
                return "Remove the skill from \(project.lastPathComponent)?"
            }
            return "\(actionTitle) this skill?"
        }

        var message: String {
            let agents = SkillPlacement.localAgents.filter { agent in
                targets.contains { $0.placement.agents.contains(agent) }
            }.map(\.title).joined(separator: ", ")
            let scope = project.map { "in \($0.lastPathComponent)" } ?? "in the default locations"
            let paths = targets.map { ($0.status.path as NSString).abbreviatingWithTildeInPath }.joined(separator: "\n")
            let link = targets.contains { $0.status.state == .linked }
                ? "\nThe link will change. Its original folder stays in place." : ""
            return "\(agents) \(scope)\n\n\(paths)\n\nA backup will be kept.\(link)"
        }
    }

    private var presentation: SkillCardPresentation { .init(skill) }
    private var unavailable: Bool { model.busy || installer.operationsBusy || model.scanning }
    private var canInstall: Bool { !unavailable && !model.files.isEmpty }

    var body: some View {
        VStack(spacing: 0) {
            header.padding(.horizontal, 24).padding(.vertical, 18)
            Divider()
            ScrollViewReader { scroll in
                ScrollView {
                    VStack(alignment: .leading, spacing: 13) {
                        Text("Install").font(.title2.bold()).accessibilityAddTraits(.isHeader)
                        allAgents
                        Divider()
                        byAgent.id("agents")
                        Divider()
                        projectsSection.id("project")
                        Divider()
                        if let url = skill.feedbackURL {
                            VStack(alignment: .leading, spacing: 4) {
                                DesktopTextLink("Share feedback on GitHub", destination: url)
                                Text("Tell the contributor what worked or report a problem.")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                            Divider()
                        }
                        advanced
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 24).padding(.vertical, 16)
                }
                .onAppear {
                    if let initialSection { scroll.scrollTo(initialSection, anchor: .top) }
                }
            }
            Divider()
            footer.padding(.horizontal, 24).padding(.vertical, 14)
        }
        .frame(minWidth: 560, idealWidth: 700, minHeight: 460, idealHeight: 680)
        .background(Color(nsColor: .textBackgroundColor))
        .interactiveDismissDisabled(model.busy || installer.operationsBusy)
        .confirmationDialog(confirmation?.title ?? "Confirm skill change",
                            isPresented: Binding(get: { confirmation != nil }, set: { if !$0 { confirmation = nil } }),
                            titleVisibility: .visible, presenting: confirmation) { request in
            Button(LocalizedStringKey(request.actionTitle),
                   role: request.operation == .remove ? .destructive : nil) {
                confirmation = nil
                model.change(request.operation, targets: request.targets, project: request.project,
                             using: installer, confirmed: true)
            }
            Button("Cancel", role: .cancel) { confirmation = nil }
        } message: { request in
            Text(request.message)
        }
    }

    private var header: some View {
        HStack(alignment: .top, spacing: 14) {
            Button { dismiss() } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 13, weight: .semibold))
                    .frame(width: 28, height: 28)
                    .background(Color.primary.opacity(0.06), in: Circle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Close skill details")
            .disabled(model.busy || installer.operationsBusy)

            VStack(alignment: .leading, spacing: 7) {
                Text(LocalizedStringKey(presentation.title)).font(.title2.bold()).accessibilityAddTraits(.isHeader)
                Text(LocalizedStringKey(presentation.goal)).foregroundStyle(.secondary)
                if let tested = skill.testedClients {
                    let names = tested.map(\.title).joined(separator: ", ")
                    if Set(tested) == Set(skill.compatibleClients) {
                        Text("Tested with \(names)").font(.caption).foregroundStyle(.secondary)
                    } else {
                        Text("Tested with \(names) only").font(.caption).foregroundStyle(.secondary)
                    }
                }
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 8) {
                        Text("Find it in your agent").foregroundStyle(.secondary)
                        invocationLabel
                    }
                    VStack(alignment: .leading, spacing: 5) {
                        Text("Find it in your agent").foregroundStyle(.secondary)
                        invocationLabel
                    }
                }.font(.callout)
            }.frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var invocationLabel: some View {
        Text("/" + presentation.title)
            .font(.callout.monospaced()).textSelection(.enabled)
            .padding(.horizontal, 8).padding(.vertical, 4)
            .background(.quaternary, in: RoundedRectangle(cornerRadius: 5))
    }

    private var footer: some View {
        HStack(spacing: 10) {
            if model.busy || model.scanning { ProgressView().controlSize(.small).accessibilityLabel("Working") }
            if !model.message.isEmpty {
                Text(LocalizedStringKey(model.message))
                    .font(.callout).foregroundStyle(model.messageIsError ? Color.primary : Color.secondary)
            }
            Spacer()
            Button("Done") { dismiss() }
                .keyboardShortcut(.cancelAction)
                .disabled(model.busy || installer.operationsBusy)
        }
    }

    private var allAgents: some View {
        let scope = model.global[skill.id]
        return VStack(alignment: .leading, spacing: 8) {
            sectionHeading("Default for all projects", subtitle: "Make this skill available across projects on this Mac.")
            if let scope {
                if scope.agents.isEmpty {
                    Text("No compatible local agents").foregroundStyle(.secondary)
                } else {
                    DesktopActionRow { scopeActions(scope, project: nil) }
                    if scope.copies.contains(where: { $0.placement == .cursorPlugin && $0.status.isInstalled })
                        && scope.agents.contains(.cursor) {
                        Text("The copy included in the Cursor plugin is managed in AI Agents.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    private var byAgent: some View {
        VStack(alignment: .leading, spacing: 6) {
            sectionHeading("By agent", subtitle: "Use in every project for the agent you choose.")
            if let scope = model.global[skill.id] {
                ForEach(scope.agents) { agent in
                    agentSection(agent, scope: scope)
                }
            }
        }
    }

    private func agentSection(_ agent: SkillClient, scope: SkillScopeStatus) -> some View {
        let copies = scope.managedCopies(for: agent)
        let pluginCopy = copies.first { $0.placement == .cursorPlugin }
        return VStack(alignment: .leading, spacing: 3) {
            Text(agent.title).font(.body.weight(.medium)).accessibilityAddTraits(.isHeader)
            if !copies.isEmpty {
                if let pluginCopy { cursorPluginCopy(pluginCopy) }
                ForEach(copies.filter { $0.placement != .cursorPlugin }) { copy in
                    VStack(alignment: .leading, spacing: 3) {
                        if pluginCopy != nil {
                            Text("Separate skill copy").font(.caption.weight(.medium))
                        }
                        agentCopy(agent, copy: copy)
                    }
                }
            } else if let proposed = scope.installTarget(for: agent) {
                if !scope.installed(for: agent).isEmpty {
                    Text("Also available through a shared installation")
                        .font(.caption).foregroundStyle(.secondary)
                }
                agentCopy(agent, copy: proposed)
            }
        }
        .padding(.vertical, 3)
        .accessibilityElement(children: .contain)
    }

    private func cursorPluginCopy(_ copy: SkillCopy) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text("Included in the Glyphs MCP plugin for Cursor").font(.callout.weight(.medium))
            Text("To update or remove this copy, manage the whole plugin in AI Agents.")
                .font(.callout).foregroundStyle(.secondary)
            versionStatus(copy.status)
            path(copy.status.path)
            DesktopActionButton(title: "Open AI Agents", action: managePlugin)
                .disabled(unavailable)
                .accessibilityHint("Opens the Cursor plugin controls")
        }
        .padding(.bottom, 5)
    }

    private func agentCopy(_ agent: SkillClient, copy: SkillCopy) -> some View {
        HStack(alignment: .center, spacing: 16) {
            VStack(alignment: .leading, spacing: 3) {
                path(copy.status.path)
                versionStatus(copy.status)
                let others = copy.placement.agents.filter { $0 != agent }.map(\.title)
                if !others.isEmpty {
                    Text("Also visible in \(others.joined(separator: ", "))").font(.caption).foregroundStyle(.secondary)
                }
            }
            Spacer(minLength: 0)
            SkillDialogActions {
                if copy.status.state == .notInstalled {
                    DesktopActionButton(title: "Install") {
                        model.change(.install, targets: [copy], using: installer, forAgent: agent)
                    }.disabled(!canInstall).accessibilityLabel("Install for \(agent.title)")
                } else if copy.status.isInstalled {
                    let action = versionAction(for: [copy])
                    DesktopActionButton(title: action.title, emphasis: action.emphasis) {
                        changeVersion(action.operation, copies: [copy])
                    }.disabled(!canInstall).accessibilityLabel("\(action.title) for \(agent.title)")
                    DesktopActionButton(title: "Uninstall…") {
                        confirmation = .init(operation: .remove, targets: [copy], project: nil)
                    }.disabled(unavailable).accessibilityLabel("Uninstall for \(agent.title)")
                }
            }
        }
    }

    private var projectsSection: some View {
        let global = model.global[skill.id]
        let agents = global?.agents ?? []
        let globalAgents = Set(agents.filter { global?.installed(for: $0).isEmpty == false })
        let copies = model.projectScopes.compactMapValues { scopes -> SkillScopeStatus? in
            guard let scope = scopes[skill.id], !scope.editableCopies.isEmpty else { return nil }
            return scope
        }
        let folders = navigation.skillProjects
            .map { URL(fileURLWithPath: $0, isDirectory: true).standardizedFileURL }
            .filter { folder in
                copies[folder] != nil ||
                    (!model.scanning && model.projectScopes[folder] == nil
                     && navigation.lastKnownSkillInstallation(skill.id, in: folder.path))
            }
        let filter = projectFilter.trimmingCharacters(in: .whitespacesAndNewlines)
        let matches = folders.filter { folder in
            filter.isEmpty || navigation.name(for: folder.path).localizedCaseInsensitiveContains(filter)
                || folder.path.localizedCaseInsensitiveContains(filter)
        }
        return VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top) {
                sectionHeading("Project copies", subtitle: "Manage copies installed in individual project folders.")
                Spacer()
                DesktopActionButton(title: folders.isEmpty ? "Install in a project…" : "Install in another project…",
                                    emphasis: .primary, action: installInProject)
                    .disabled(!canInstall || agents.isEmpty)
            }
            if !globalAgents.isEmpty {
                Text("Agents with a Mac-wide copy can use it in any project without a project copy.")
                    .font(.callout).foregroundStyle(.secondary)
            }
            if folders.isEmpty {
                Text(model.scanning ? "Checking for project copies…" : "No project copies installed.")
                    .font(.callout).foregroundStyle(.secondary)
            } else {
                if folders.count > 1 || !projectFilter.isEmpty {
                    TextField("Search installed projects", text: $projectFilter).textFieldStyle(.roundedBorder)
                }
                if matches.isEmpty {
                    Text("No matching project copies.").font(.callout).foregroundStyle(.secondary)
                }
                ForEach(matches, id: \.self) { folder in
                    Divider()
                    projectRow(folder, scope: copies[folder], globalAgents: globalAgents)
                }
            }
        }
    }

    private func projectRow(_ folder: URL, scope: SkillScopeStatus?, globalAgents: Set<SkillClient>) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            VStack(alignment: .leading, spacing: 3) {
                Text(navigation.name(for: folder.path))
                    .font(.body.weight(.medium)).accessibilityAddTraits(.isHeader)
                path(folder.path)
            }
            if let scope {
                let projectAgents = scope.agents.filter { !scope.installed(for: $0).isEmpty }
                ForEach(scope.editableCopies) { copy in
                    VStack(alignment: .leading, spacing: 3) {
                        path(copy.status.path, relativeTo: folder)
                        versionStatus(copy.status)
                    }
                }
                if projectAgents.allSatisfy(globalAgents.contains) {
                    Text("Remove the project copy if you use the Mac-wide copy. This avoids keeping two versions.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                DesktopActionRow { scopeActions(scope, project: folder) }
            } else {
                Label("Project folder unavailable", systemImage: "exclamationmark.triangle.fill")
                    .font(.callout).foregroundStyle(.orange)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 3)
    }

    private func installInProject() {
        let panel = DesktopProjectsModel.folderPanel("Choose Project Folder")
        panel.canCreateDirectories = false
        panel.directoryURL = navigation.lastProject.map { URL(fileURLWithPath: $0, isDirectory: true) }
        panel.prompt = "Install"
        panel.message = "Choose a folder to install this skill for all compatible agents in that project."
        if panel.runModal() == .OK, let chosen = panel.url {
            projectFilter = ""
            projects.rememberSkillProject(chosen)
            model.change(.install, project: chosen.standardizedFileURL, using: installer)
        }
    }

    @ViewBuilder private func scopeActions(_ scope: SkillScopeStatus, project: URL?) -> some View {
        let installed = scope.editableCopies
        let missing = scope.missing(for: scope.agents)
        let updates = installed.filter { $0.status.state == .updateAvailable }
        let versionTargets = updates.isEmpty ? installed : updates
        if !missing.isEmpty {
            DesktopActionButton(title: project == nil ? "Install default" : "Install in project", emphasis: .primary) {
                model.change(.install, targets: missing, project: project, using: installer)
            }.disabled(!canInstall)
        }
        if !versionTargets.isEmpty {
            let action = versionAction(for: versionTargets)
            let suffix = project == nil ? " default" : " in project"
            let title = action.title == "Replace…" ? "Replace" + suffix + "…" : action.title + suffix
            DesktopActionButton(title: title, emphasis: action.emphasis) {
                changeVersion(action.operation, copies: versionTargets, project: project)
            }.disabled(!canInstall)
        }
        if !installed.isEmpty {
            DesktopActionButton(title: project == nil ? "Remove default…" : "Remove from project…") {
                confirmation = .init(operation: .remove, targets: installed, project: project)
            }.disabled(unavailable)
        }
    }

    private var advanced: some View {
        DisclosureGroup("Advanced") {
            VStack(alignment: .leading, spacing: 10) {
                Text(skill.author + " · " + skill.license)
                if let version = skill.version { Text("Version \(version)") }
                Text("Revision: \(skill.source.revision)").textSelection(.enabled)
                ForEach(skill.requirements, id: \.self) { Text($0) }
                if let url = skill.source.browseURL { DesktopTextLink("View source", destination: url) }
                if skill.compatibleClients.contains(.codex) {
                    Text("Codex: $\(skill.name)").textSelection(.enabled)
                }
                if skill.compatibleClients.contains(.claudeCode) {
                    Text("Claude Code: /\(skill.name)").textSelection(.enabled)
                }
                if skill.compatibleClients.contains(.cursor) {
                    Text("Cursor: /\(skill.name)").textSelection(.enabled)
                }
                if !model.files.isEmpty {
                    let example = SkillMetadata.examplePrompt(in: model.files)
                        ?? "Use the \(presentation.title) skill. Tell me what you need to get started."
                    Text("Example prompt").font(.headline)
                    Text(example).textSelection(.enabled)
                    Button("Copy example") {
                        NSPasteboard.general.clearContents()
                        NSPasteboard.general.setString(example, forType: .string)
                    }
                    instructions
                }
                if !model.operationDetails.isEmpty {
                    Text("Installation activity").font(.headline)
                    Text(model.operationDetails).textSelection(.enabled)
                }
                if skill.compatibleClients.contains(.chatgpt) || skill.compatibleClients.contains(.claude) {
                    Text("For hosted agents, export the skill and upload it in the agent’s settings.")
                    if skill.compatibleClients.contains(.chatgpt) {
                        DesktopTextLink("ChatGPT upload guide", destination: URL(string: "https://developers.openai.com/cookbook/examples/chatgpt/chatgpt_prompt_guide/chatgpt_prompt_guide")!)
                    }
                    if skill.compatibleClients.contains(.claude) {
                        DesktopTextLink("Claude upload guide", destination: URL(string: "https://support.claude.com/en/articles/12512198-how-to-create-custom-skills")!)
                    }
                    Button("Export ZIP…") { model.export(skill, owner: installer) }.disabled(!canInstall)
                }
            }.font(.callout).padding(.top, 10)
        }
    }

    private var instructions: some View {
        DisclosureGroup("Read instructions") {
            VStack(alignment: .leading, spacing: 8) {
                DisclosureGroup("Skill files") {
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(model.files.filter { $0.data != nil }, id: \.path) { file in
                            Button { previewPath = file.path } label: {
                                Text(file.path).multilineTextAlignment(.leading)
                            }
                            .buttonStyle(.link)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                Text(previewPath).font(.caption).foregroundStyle(.secondary)
                if let data = model.files.first(where: { $0.path == previewPath })?.data,
                   let text = String(data: data, encoding: .utf8) {
                    if text.count > 100_000 { Text("Preview limited to 100,000 characters.") }
                    Text(String(text.prefix(100_000))).font(.callout.monospaced()).textSelection(.enabled)
                } else {
                    Text("Binary resource included with the skill.")
                }
            }.padding(.top, 8)
        }
    }

    private func sectionHeading(_ title: LocalizedStringKey, subtitle: LocalizedStringKey) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title).font(.headline).accessibilityAddTraits(.isHeader)
            Text(subtitle).font(.callout).foregroundStyle(.secondary)
        }
    }

    private func path(_ value: String, relativeTo project: URL? = nil) -> some View {
        let prefix = project.map { $0.path + "/" }
        let display = if let prefix, value.hasPrefix(prefix) {
            String(value.dropFirst(prefix.count))
        } else {
            (value as NSString).abbreviatingWithTildeInPath
        }
        return Text(display)
            .font(.caption.monospaced()).foregroundStyle(.secondary)
            .textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
    }

    @ViewBuilder private func versionStatus(_ status: SkillInstallationStatus) -> some View {
        if status.matchesPackage == true {
            Label {
                if let version = status.availableVersion { Text("Version \(version)") }
                else { Text("Up to date") }
            } icon: {
                Image(systemName: "checkmark.circle")
            }
            .font(.caption).foregroundStyle(.secondary)
            .accessibilityLabel(status.availableVersion.map { Text("Version \($0), up to date") } ?? Text("Up to date"))
            if status.state == .linked {
                Text("Linked folder").font(.caption).foregroundStyle(.secondary)
            }
        } else if status.state == .updateAvailable {
            if let version = status.availableVersion {
                Text(status.installedVersion.map { "\($0) · Update to \(version)" } ?? "Update to \(version)")
                    .font(.caption).foregroundStyle(.secondary)
            } else {
                Text("Update available").font(.caption).foregroundStyle(.secondary)
            }
        } else if status.state != .notInstalled {
            Text(LocalizedStringKey(status.title)).font(.caption).foregroundStyle(.secondary)
            if status.isInstalled && status.matchesPackage == false {
                Text("Version unverified").font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private func versionAction(for copies: [SkillCopy]) -> (operation: SkillCopyOperation, title: String, emphasis: DesktopActionButton.Emphasis) {
        if copies.contains(where: { $0.status.state == .updateAvailable }) {
            return (.update, "Update", .primary)
        }
        if copies.allSatisfy({ $0.status.matchesPackage == true || $0.status.state == .installed }) {
            return (.reinstall, "Reinstall", .secondary)
        }
        return (.update, "Replace…", .secondary)
    }

    private func changeVersion(_ operation: SkillCopyOperation, copies: [SkillCopy], project: URL? = nil) {
        if copies.contains(where: { $0.status.requiresBackupConfirmation || $0.status.state == .linked }) {
            confirmation = .init(operation: operation, targets: copies, project: project)
        } else {
            model.change(operation, targets: copies, project: project, using: installer)
        }
    }
}

private struct SkillDialogActions<Content: View>: View {
    @ViewBuilder let content: () -> Content

    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 8) { content() }
            VStack(alignment: .trailing, spacing: 8) { content() }
        }
        .fixedSize(horizontal: false, vertical: true)
    }
}

private struct SkillImportSheet: View {
    @ObservedObject var model: DesktopSkillsModel
    @Environment(\.dismiss) private var dismiss
    @State private var repository = ""
    @State private var directory = ""
    @State private var revision = ""
    @State private var discovered: [CatalogSkill] = []
    @State private var message = ""
    @State private var busy = false
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Import from GitHub").font(.title2.bold())
            Text("Import a public repository privately. This does not submit it to the reviewed catalog.").foregroundStyle(.secondary)
            TextField("Repository URL", text: $repository)
            TextField("Directory (optional)", text: $directory)
            TextField("Revision (optional; default branch)", text: $revision)
            Text("Imports are unreviewed. Check instructions, scripts, dependencies and licensing before installing.").font(.callout)
            if !message.isEmpty { Text(message).font(.callout) }
            if busy { ProgressView() }
            ScrollView {
                ForEach(discovered) { skill in
                    HStack {
                        VStack(alignment: .leading) { Text(skill.title).font(.headline); Text(skill.description).font(.caption) }
                        Spacer()
                        Button("Add and Review") {
                            busy = true
                            Task {
                                defer { busy = false }
                                do { try await model.addImport(skill); dismiss() } catch { message = error.localizedDescription }
                            }
                        }
                    }.padding(.vertical, 8)
                }
            }.frame(maxHeight: 220)
            HStack {
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                Spacer()
                Button("Find Skills") {
                    busy = true; discovered = []; message = ""
                    Task {
                        defer { busy = false }
                        do { discovered = try await model.discover(repository: repository, directory: directory, revision: revision) }
                        catch { message = error.localizedDescription }
                    }
                }.buttonStyle(.borderedProminent).disabled(repository.isEmpty)
            }
        }.padding(24).frame(width: 620).disabled(busy).interactiveDismissDisabled(busy)
    }
}
