import AppKit
import SwiftUI
import GlyphsMCPInstallerCore

@MainActor
final class DesktopSkillsModel: ObservableObject {
    @Published private(set) var skills: [CatalogSkill] = []
    @Published private(set) var busy = false
    @Published private(set) var scanning = false
    @Published private(set) var galleryResult = ""
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
    @Published private(set) var updateIDs: Set<String> = []
    @Published private(set) var updateCheckMessage = ""
    private var projectFolders: [URL] = []
    private weak var projects: DesktopProjectsModel?
    private var packageVersion: SkillPackageVersion?
    private var verifiedPackages: [String: SkillPackageVersion] = [:]
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
            (client.map(skill.supports) ?? true) &&
            (category == "All" || category == "Included" && skill.bundled || category == "Additional" && !skill.bundled || category == "Installed" && isInstalled(skill) || category == "Updates" && hasUpdate(skill))
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
        updateIDs.contains(skill.id)
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
                    guard let url = Bundle.main.url(forResource: "registry", withExtension: "json", subdirectory: "SkillsCatalog") else { throw ProjectError(localized: "The bundled skills catalog is missing.") }
                    snapshot = try Data(contentsOf: url)
                }
                catalogEntries = try await store.catalog(snapshot: snapshot!, refresh: refresh).skills
                importEntries = try await store.imports()
                await loadBundledPackages()
                rescan()
                catalogMessage = refresh ? "Skills catalog refreshed." : ""
            } catch { catalogMessage = error.presentationDescription() }
        }
    }

    private func loadBundledPackages() async {
        verifiedPackages = [:]
        updateCheckMessage = ""
        do {
            let payload = try await InstallerPayloadDiscovery.shared.resolve { try InstallerPayload.resolve() }
            let directories = payload.managedSkillDirectories()
            let entries = catalogEntries
            let result = await Task.detached(priority: .utility) {
                BundledSkillPackages(skills: entries, directories: directories)
            }.value
            verifiedPackages = result.versions
            if !result.failures.isEmpty {
                updateCheckMessage = "Some skill updates could not be checked. Refresh to try again."
                operationDetails = result.presentationFailures.joined(separator: "\n")
            }
        } catch {
            updateCheckMessage = "Some skill updates could not be checked. Refresh to try again."
            operationDetails = error.presentationDescription()
        }
    }

    func rescan() {
        // Setup/project notifications can arrive before the initial catalog load.
        // An empty scan must not erase remembered project skill installations.
        guard !catalogEntries.isEmpty else { return }
        scanGeneration += 1
        let generation = scanGeneration
        scanning = true
        let catalog = catalogEntries
        let imports = importEntries
        let folders = projectFolders
        let availablePackages = verifiedPackages
        let service = installer
        Task {
            let (entries, overview, warning) = await Task.detached(priority: .userInitiated) {
                var entries = catalog
                var warning = ""
                let placements = SkillPlacement.allCases.filter { $0 != .cursorPlugin }
                let projectRoots = Dictionary(uniqueKeysWithValues: folders.compactMap { folder -> (URL, [URL])? in
                    var isDirectory: ObjCBool = false
                    guard FileManager.default.fileExists(atPath: folder.path, isDirectory: &isDirectory),
                          isDirectory.boolValue else {
                        return nil
                    }
                    return (folder, placements.filter(\.supportsProjects).map { folder.appendingPathComponent($0.rawValue) })
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
                        warning = error.presentationDescription()
                    }
                }
                let overview = SkillOverview(skills: entries, installer: service,
                    packages: availablePackages, projectRoots: projectRoots)
                return (entries, overview, warning)
            }.value
            guard generation == scanGeneration else { return }
            skills = entries
            global = overview.global
            projectScopes = overview.projects
            updateIDs = overview.updateIDs
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
                let package = try await loadFiles(skill)
                packageVersion = try await ProjectFiles.perform {
                    SkillPackageVersion(label: skill.version, files: package)
                }
                verifiedPackages[skill.id] = packageVersion
                files = package
                message = ""
            } catch {
                message = error.presentationDescription()
                messageIsError = true
            }
        }
    }

    private func loadFiles(_ skill: CatalogSkill) async throws -> [ProjectFile] {
        let bundledRoot: URL?
        if skill.bundled {
            let payload = try await InstallerPayloadDiscovery.shared.resolve { try InstallerPayload.resolve() }
            guard let folder = payload.managedSkillDirectories().first(where: { $0.lastPathComponent == skill.name }) else {
                throw ProjectError(localized: "This skill is missing from the app’s verified payload.")
            }
            bundledRoot = folder.deletingLastPathComponent()
        } else {
            bundledRoot = nil
        }
        return try await store.files(skill, bundledRoot: bundledRoot)
    }

    func updateLocations(for skill: CatalogSkill) -> [SkillUpdateLocation] {
        var locations = SkillUpdateLocation.eligible(in: global[skill.id])
        for folder in projectFolders {
            locations += SkillUpdateLocation.eligible(in: projectScopes[folder]?[skill.id], project: folder)
        }
        var seen = Set<String>()
        return locations.filter { seen.insert($0.id).inserted }
    }

    func update(_ skill: CatalogSkill, locations: [SkillUpdateLocation], using owner: InstallerViewModel) {
        guard !scanning, !locations.isEmpty else { return }
        let service = installer
        let title = AppLocalization.text(skill.title)
        run(owner, title: "Updating skill…", skillID: skill.id, setupOperation: .update, gallery: true) {
            do {
                let files = try await self.loadFiles(skill)
                let (result, package) = try await ProjectFiles.perform {
                    let package = SkillPackageVersion(label: skill.version, files: files)
                    return (service.update(skill, locations: locations, files: files, package: package), package)
                }
                self.verifiedPackages[skill.id] = package
                if self.selected?.id == skill.id {
                    self.packageVersion = package
                    self.files = files
                }
                if locations.contains(where: { $0.copy.placement == .antigravity }) {
                    owner.refreshConnectorDetection()
                }
                let details = (result.completed + result.presentationFailures).joined(separator: "\n")
                let count = Int64(result.completed.count)
                if !result.presentationFailures.isEmpty {
                    let failures = result.presentationFailures.joined(separator: "\n")
                    let summary = count == 0 ? AppLocalization.format("Could not update %@. %@", title, failures)
                        : AppLocalization.format("Updated %@ in %lld of %lld locations.", title, count,
                                                 Int64(Set(locations.map(\.id)).count)) + "\n" + failures
                    return (summary, details, true)
                }
                let summary = count == 1 ? AppLocalization.format("Updated %@ in one location.", title)
                    : AppLocalization.format("Updated %@ in %lld locations.", title, count)
                return (summary, details, false)
            } catch {
                let destinations = locations.map { $0.title + " — " + $0.id }
                let detail = ([error.presentationDescription()] + destinations).joined(separator: "\n")
                return (AppLocalization.format("Could not update %@. %@", title, detail), detail, true)
            }
        }
    }

    func discover(repository: String, directory: String, revision: String) async throws -> [CatalogSkill] {
        try await store.discover(repository: repository, directory: directory.isEmpty ? "." : directory, revision: revision)
    }
    func addImport(_ skill: CatalogSkill) async throws {
        guard !catalogEntries.contains(where: { $0.name == skill.name && $0.id != skill.id }) else { throw ProjectError(localized: "This name belongs to a catalog skill. Use its reviewed entry instead.") }
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
            defer {
                if targets?.contains(where: { $0.placement == .antigravity }) == true {
                    owner.refreshConnectorDetection()
                }
            }
            let (result, count) = try await ProjectFiles.perform {
                let destinations: [SkillCopy]
                if let targets {
                    destinations = targets
                } else {
                    let scope = service.scopeStatus(skill, project: project, package: packageVersion)
                    guard !scope.agents.isEmpty else {
                        throw ProjectError(localized: "Choose a project folder outside your default skill location.")
                    }
                    destinations = scope.missing(for: scope.agents)
                }
                let result = service.apply(operation, to: destinations, skill: skill, files: package, project: project,
                                           replace: confirmed, package: packageVersion, forAgent: agent)
                return (result, destinations.count)
            }
            let details = (result.completed + result.presentationFailures).joined(separator: "\n")
            if result.failures.isEmpty {
                return (AppLocalization.text(result.completed.isEmpty ? "The skill is already installed." : success), details, false)
            }
            if result.completed.isEmpty {
                return (AppLocalization.text("No locations changed. See Technical details."), details, true)
            }
            return (AppLocalization.format("Changed %lld of %lld locations. See Technical details.", Int64(result.completed.count), Int64(count)), details, true)
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
            guard result.exitCode == 0 else { throw ProjectError(localized: "Skill export failed.") }
            let data = try Data(contentsOf: zip); _ = try TemplateArchive.validate(data)
            try data.write(to: destination, options: .atomic)
            return (AppLocalization.text("Skill ZIP exported."), destination.path, false)
        }
    }
    private func run(_ owner: InstallerViewModel, title: String, skillID: String? = nil,
                     setupOperation: SetupOperation? = nil, gallery: Bool = false,
                     operation: @escaping () async throws -> (String, String, Bool)) {
        guard !busy, !owner.operationsBusy else { return }
        if gallery { galleryResult = "" }
        activeSkillID = skillID
        activeOperation = setupOperation
        busy = true
        owner.supplementalSkillsBusy = true
        message = AppLocalization.text(title)
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
                message = error.presentationDescription()
                messageIsError = true
            }
            if gallery {
                galleryResult = message
                NSAccessibility.post(element: NSApplication.shared, notification: .announcementRequested, userInfo: [
                    .announcement: message, .priority: NSAccessibilityPriorityLevel.high.rawValue
                ])
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
                VStack(alignment: .leading, spacing: DesktopDashboardLayout.sectionSpacing) {
                    if #unavailable(macOS 26.0) {
                        Text(LocalizedStringKey(section == .companions ? "Companion Plugins" : "AI Agents"))
                            .font(.largeTitle.bold())
                    }
                    Text(LocalizedStringKey(section == .companions ? "Manage optional Glyphs plugins. The bundled inspectors require the Glyphs MCP bridge." : "Configure each AI agent independently. Download the client application separately when needed."))
                        .foregroundStyle(.secondary)
                    Button("Open Setup", action: showSetup)
                    if section == .companions && installer.running {
                        DesktopComponentPreparation()
                    }
                    InstallationView(section: section)
                }
                .modifier(DesktopDashboardPageLayout())
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
            "glyphs": "Choose a workflow for editing or checking a Glyphs font.",
            "glyphs-mcp-development": "Build and test scripts and plugins for Glyphs.",
            "glyphs-mcp-italic-first-pass": "Prepare a first slant for your italic design.",
            "glyphs-mcp-kerning": "Review the spacing between letter pairs.",
            "glyphs-mcp-maintainer-feedback": "Collect useful details for a clear bug report.",
            "glyphs-mcp-master-compatibility": "Compare contour starts across your masters.",
            "glyphs-mcp-opentype-features": "Write and check your font’s OpenType features.",
            "glyphs-mcp-outlines-docs": "Inspect curves and plan focused outline edits.",
            "glyphs-mcp-path-doctor": "Find outline problems and review suggested repairs.",
            "glyphs-mcp-release": "Check a local Glyphs MCP release before publishing.",
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
    let locations: [SkillUpdateLocation]
    let checking: Bool
    let progress: String?
    let update: () -> Void
    let reviewRemoval: () -> Void
    let open: () -> Void
    private var presentation: SkillCardPresentation { .init(skill) }

    var body: some View {
        DesktopCatalogCard(previewHeight: nil, detailMinimumHeight: 48) {
            EmptyView()
        } title: {
            Text(LocalizedStringKey(presentation.title))
        } detail: {
            Text(LocalizedStringKey(presentation.goal))
        } status: {
            if let progress {
                DesktopStatus(title: progress, tone: .progress, spinning: true)
            } else if checking {
                DesktopStatus(title: "Checking installation…", spinning: true)
            } else if let first = locations.first {
                Label {
                    if locations.count == 1 {
                        Text("Update available for \(first.title)")
                    } else {
                        Text("Updates available in \(locations.count) locations")
                    }
                } icon: {
                    Image(systemName: "arrow.down.circle").accessibilityHidden(true)
                }
                .font(.callout.weight(.medium))
                .fixedSize(horizontal: false, vertical: true)
            } else {
                DesktopStatus(title: installed ? "Installed" : "Not installed",
                              tone: installed ? .installed : .neutral,
                              symbol: installed ? "checkmark.circle.fill" : "circle")
            }
        } actions: {
            DesktopActionRow {
                if let first = locations.first {
                    DesktopActionButton(title: locations.count == 1 ? "Update" : "Choose updates…",
                                        emphasis: .primary, action: update)
                        .accessibilityLabel(Text(verbatim: locations.count == 1
                            ? AppLocalization.format("Update %@ for %@", AppLocalization.text(presentation.title), first.title)
                            : AppLocalization.format("Choose update locations for %@", AppLocalization.text(presentation.title))))
                        .disabled(checking || progress != nil)
                } else if !skill.bundled && !installed {
                    DesktopActionButton(title: "Install", emphasis: .primary, action: open)
                        .disabled(checking)
                } else if !skill.bundled && installed {
                    DesktopActionButton(title: "Uninstall…", action: reviewRemoval).disabled(checking)
                }
                DesktopActionButton(title: "Details", action: open)
                    .accessibilityLabel(Text("Details for \(AppLocalization.text(presentation.title))"))
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

    private struct UpdateChoice: Identifiable {
        let skill: CatalogSkill
        let locations: [SkillUpdateLocation]
        var id: String { skill.id }
    }
    @State private var choosingUpdates: UpdateChoice?

    private var searchField: some View {
        TextField("Search skills", text: $model.search).textFieldStyle(.roundedBorder)
    }

    @ViewBuilder private var filters: some View {
        Picker("Show", selection: $model.category) {
            ForEach(["All", "Included", "Additional", "Installed", "Updates"], id: \.self) { category in
                Text(LocalizedStringKey(category)).tag(category)
            }
        }.fixedSize()
        Picker("Agent", selection: $model.client) {
            Text("All agents").tag(Optional<SkillClient>.none)
            ForEach(SkillClient.allCases) { Text($0.title).tag(Optional($0)) }
        }.fixedSize()
    }

    private func open(_ skill: CatalogSkill, showAgentActions: Bool = false) {
        initialSection = showAgentActions ? (model.hasGlobalInstallation(skill) ? "agents" : "project") : nil
        model.inspect(skill)
    }

    private func revealPostUpdateSkill() {
        guard !model.busy, let skill = installer.postUpdateSkillToReveal else { return }
        installer.postUpdateSkillToReveal = nil
        open(skill)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DesktopDashboardLayout.sectionSpacing) {
                HStack(alignment: .firstTextBaseline) {
                    if #unavailable(macOS 26.0) {
                        Text("Skills").font(.largeTitle.bold())
                        Spacer()
                    }
                    Button("Refresh") { model.load(refresh: true) }.disabled(model.busy)
                    Button("Add from GitHub…") { showingImport = true }.disabled(model.busy || installer.operationsBusy)
                    DesktopTextLink("Contribute", destination: SkillCatalog.contributionURL)
                }
                if !model.updateIDs.isEmpty {
                    HStack {
                        Label {
                            Text(verbatim: AppLocalization.count("%lld skills have updates", model.updateIDs.count))
                        } icon: {
                            Image(systemName: "arrow.down.circle")
                        }
                        .font(.headline)
                        Spacer()
                        if model.category != "Updates" {
                            Button("Show updates") {
                                model.category = "Updates"
                                model.search = ""
                                model.client = nil
                            }
                        }
                    }
                    .padding()
                    .background(Color.accentColor.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
                }
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 14) {
                        searchField.frame(minWidth: 160)
                        filters
                    }
                    VStack(alignment: .leading, spacing: 8) {
                        searchField
                        DesktopActionRow { filters }
                    }
                }
                if (model.busy || model.scanning) && model.selected == nil { ProgressView().controlSize(.small) }
                if !model.catalogMessage.isEmpty { Text(LocalizedStringKey(model.catalogMessage)).font(.callout) }
                if !model.updateCheckMessage.isEmpty {
                    Text(LocalizedStringKey(model.updateCheckMessage)).font(.callout).foregroundStyle(.secondary)
                }
                if !model.galleryResult.isEmpty {
                    Text(verbatim: model.galleryResult).font(.callout).textSelection(.enabled)
                }
                SetupCardGrid {
                    ForEach(model.filtered) { skill in
                        let locations = model.hasUpdate(skill) ? model.updateLocations(for: skill) : []
                        DesktopSkillCard(skill: skill, installed: model.isInstalled(skill),
                            locations: locations,
                            checking: model.scanning,
                            progress: model.activeSkillID == skill.id ? (model.activeOperation == .remove ? "Uninstalling…" : model.activeOperation?.progressLabel) : nil,
                            update: {
                                if locations.count == 1 {
                                    model.update(skill, locations: locations, using: installer)
                                } else {
                                    choosingUpdates = UpdateChoice(skill: skill, locations: locations)
                                }
                            },
                            reviewRemoval: { open(skill, showAgentActions: true) },
                            open: { open(skill) })
                            .disabled(model.busy || installer.operationsBusy)
                            .accessibilityElement(children: .contain)
                    }
                }
                if model.filtered.isEmpty && !model.busy && !model.scanning { Text("No matching skills.").foregroundStyle(.secondary) }
            }
            .modifier(DesktopDashboardPageLayout())
        }
        .task {
            model.prepareProjects(projects)
            if model.skills.isEmpty { model.load() } else { model.rescan() }
            revealPostUpdateSkill()
        }
        .onChange(of: installer.postUpdateSkillToReveal) { _, _ in revealPostUpdateSkill() }
        .onChange(of: model.busy) { _, busy in if !busy { revealPostUpdateSkill() } }
        .sheet(isPresented: $showingImport, onDismiss: {
            if let skill = model.pendingInspection {
                model.pendingInspection = nil
                open(skill)
            }
        }) { SkillImportSheet(model: model) }
        .sheet(item: $choosingUpdates) { choice in
            SkillUpdateChooser(skill: choice.skill, locations: choice.locations,
                              working: model.busy || installer.operationsBusy || model.scanning) { chosen in
                choosingUpdates = nil
                model.update(choice.skill, locations: chosen, using: installer)
            }
        }
        .sheet(item: $model.selected) { skill in
            SkillDetailsSheet(skill: skill, model: model, installer: installer, initialSection: initialSection,
                              projects: projects) {
                model.selected = nil
                manageAgents()
            }
        }
    }
}

private struct SkillUpdateChooser: View {
    let skill: CatalogSkill
    let locations: [SkillUpdateLocation]
    let working: Bool
    let update: ([SkillUpdateLocation]) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var selection: Set<String> = []

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Choose update locations").font(.title2.bold()).accessibilityAddTraits(.isHeader)
            Text("Choose where to update \(AppLocalization.text(skill.title)).")
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    ForEach(locations, id: \.id) { location in
                        Toggle(isOn: Binding(get: { selection.contains(location.id) }, set: { checked in
                            if checked { selection.insert(location.id) } else { selection.remove(location.id) }
                        })) {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(verbatim: location.title)
                                if locations.contains(where: { $0.id != location.id && $0.title == location.title }) {
                                    Text(verbatim: (location.id as NSString).abbreviatingWithTildeInPath)
                                        .font(.caption).foregroundStyle(.secondary)
                                        .fixedSize(horizontal: false, vertical: true)
                                }
                            }
                        }
                        .toggleStyle(.checkbox)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            HStack {
                Spacer()
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                Button("Update selected") { update(chosenLocations) }
                    .keyboardShortcut(.defaultAction)
                    .disabled(working || chosenLocations.isEmpty)
            }
        }
        .padding(24)
        .frame(minWidth: 380, minHeight: 220, idealHeight: 300)
    }

    private var chosenLocations: [SkillUpdateLocation] {
        locations.filter { selection.contains($0.id) }
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
    @State private var commandAgent: SkillClient?

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
            switch operation {
            case .remove: return "Uninstall this skill?"
            case .reinstall: return "Reinstall this skill?"
            case .update: return actionTitle == "Replace" ? "Replace this skill?" : "Update this skill?"
            case .install: return "Install this skill?"
            }
        }

        var message: String {
            let agents = SkillPlacement.localAgents.filter { agent in
                targets.contains { $0.placement.agents.contains(agent) }
            }.map(\.title).joined(separator: ", ")
            let heading = project.map { AppLocalization.format("%@ in %@", agents, $0.lastPathComponent) }
                ?? AppLocalization.format("%@ in the default locations", agents)
            let paths = targets.map { ($0.status.path as NSString).abbreviatingWithTildeInPath }.joined(separator: "\n")
            let link = targets.contains { $0.status.state == .linked }
                ? "\n" + AppLocalization.text("The link will change. Its original folder stays in place.") : ""
            return AppLocalization.format("%@\n\n%@\n\nA backup will be kept.%@", heading, paths, link)
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
                        Text("Installation locations").font(.title2.bold()).accessibilityAddTraits(.isHeader)
                        if projectUpdatesFirst {
                            projectsSection.id("project")
                            Divider()
                        }
                        macSection.id("agents")
                        if !projectUpdatesFirst {
                            Divider()
                            projectsSection.id("project")
                        }
                        Divider()
                        if let url = skill.feedbackURL {
                            VStack(alignment: .leading, spacing: 4) {
                                DesktopTextLink("Share feedback on GitHub", destination: url)
                                Text("Tell the contributor what worked or report a problem.")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                            Divider()
                        }
                        invocationLabel
                        Divider()
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
                    let names = tested.map(\.title).formatted(.list(type: .and))
                    if Set(tested) == Set(skill.compatibleClients) {
                        Text("Tested with \(names)").font(.caption).foregroundStyle(.secondary)
                    } else {
                        Text("Tested with \(names) only").font(.caption).foregroundStyle(.secondary)
                    }
                }
                Text(LocalizedStringKey(skill.categoryTitle)).font(.caption.weight(.medium))
            }.frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    @ViewBuilder private var invocationLabel: some View {
        let agents = [SkillClient.codex, .claudeCode, .cursor].filter(skill.compatibleClients.contains)
        if let first = agents.first {
            let selected = commandAgent.flatMap { agents.contains($0) ? $0 : nil } ?? first
            let command = (selected == .codex ? "$" : "/") + skill.name
            VStack(alignment: .leading, spacing: 8) {
                Text("Use this skill").font(.headline).accessibilityAddTraits(.isHeader)
                HStack {
                    Picker("Agent", selection: Binding(get: { selected }, set: { commandAgent = $0 })) {
                        ForEach(agents) { Text($0.title).tag($0) }
                    }.fixedSize()
                    Spacer()
                    Button("Copy command") {
                        NSPasteboard.general.clearContents()
                        NSPasteboard.general.setString(command, forType: .string)
                    }
                }
                Text(verbatim: command).font(.callout.monospaced()).textSelection(.enabled)
            }
        }
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

    private var projectUpdatesFirst: Bool {
        !hasUpdate(model.global[skill.id]?.editableCopies ?? []) &&
            model.projectScopes.values.contains { hasUpdate($0[skill.id]?.editableCopies ?? []) }
    }

    private var macSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            sectionHeading("On this Mac", subtitle: "Make this skill available across projects on this Mac.")
            if let scope = model.global[skill.id] {
                if scope.agents.isEmpty {
                    Text("No compatible local agents").foregroundStyle(.secondary)
                }
                ForEach(scope.agents.sorted { lhs, rhs in
                    hasUpdate(scope.managedCopies(for: lhs)) && !hasUpdate(scope.managedCopies(for: rhs))
                }) { agent in
                    agentSection(agent, scope: scope)
                }
            }
        }
    }

    private func agentSection(_ agent: SkillClient, scope: SkillScopeStatus) -> some View {
        let copies = updatesFirst(scope.managedCopies(for: agent))
        let pluginCopy = copies.first { $0.placement == .cursorPlugin }
        return VStack(alignment: .leading, spacing: 3) {
            Text(agent.title).font(.body.weight(.medium)).accessibilityAddTraits(.isHeader)
            if !copies.isEmpty {
                ForEach(copies) { copy in
                    if copy.placement == .cursorPlugin {
                        cursorPluginCopy(copy)
                    } else {
                        VStack(alignment: .leading, spacing: 3) {
                            if pluginCopy != nil {
                                Text("Separate skill copy").font(.caption.weight(.medium))
                            }
                            agentCopy(agent, copy: copy)
                        }
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
            Text("Included with the Cursor plugin").font(.callout)
            versionStatus(copy.status)
            path(copy.status.path)
            DesktopActionButton(title: "Manage in AI Agents", action: managePlugin)
                .disabled(unavailable)
                .accessibilityHint("Opens the Cursor plugin controls")
        }
        .padding(.bottom, 5)
    }

    private func agentCopy(_ agent: SkillClient, copy: SkillCopy) -> some View {
        HStack(alignment: .center, spacing: 16) {
            VStack(alignment: .leading, spacing: 3) {
                versionStatus(copy.status)
                path(copy.status.path)
                let others = copy.placement.agents.filter { $0 != agent }.map(\.title)
                if copy.status.isInstalled && !others.isEmpty {
                    Text("Also visible in \(others.formatted(.list(type: .and)))").font(.caption).foregroundStyle(.secondary)
                }
            }
            Spacer(minLength: 0)
            SkillDialogActions {
                if copy.status.state == .notInstalled {
                    DesktopActionButton(title: "Install") {
                        model.change(.install, targets: [copy], using: installer, forAgent: agent)
                    }.disabled(!canInstall).accessibilityLabel("Install for \(agent.title)")
                } else if copy.status.isInstalled {
                    copyActions(copy, location: agent.title)
                }
            }
        }
    }

    @ViewBuilder private func copyActions(_ copy: SkillCopy, location: String, project: URL? = nil) -> some View {
        let action = versionAction(for: [copy])
        if copy.status.state == .updateAvailable {
            DesktopActionButton(title: action.title, emphasis: .primary) {
                changeVersion(action.operation, copies: [copy], project: project)
            }.disabled(!canInstall).accessibilityLabel("Update for \(location)")
        }
        Menu("More") {
            if copy.status.state != .updateAvailable {
                Button(LocalizedStringKey(action.title)) {
                    changeVersion(action.operation, copies: [copy], project: project)
                }.disabled(!canInstall)
            }
            Button(LocalizedStringKey(project == nil ? "Uninstall…" : "Remove from project…"), role: .destructive) {
                confirmation = .init(operation: .remove, targets: [copy], project: project)
            }
        }.fixedSize().disabled(unavailable).accessibilityLabel("More actions for \(location)")
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
                sectionHeading("In projects", subtitle: "Manage copies installed in individual project folders.")
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
                Text(LocalizedStringKey(model.scanning ? "Checking for project copies…" : "No project copies installed."))
                    .font(.callout).foregroundStyle(.secondary)
            } else {
                if folders.count > 1 || !projectFilter.isEmpty {
                    TextField("Search installed projects", text: $projectFilter).textFieldStyle(.roundedBorder)
                }
                if matches.isEmpty {
                    Text("No matching project copies.").font(.callout).foregroundStyle(.secondary)
                }
                ForEach(matches.sorted { lhs, rhs in
                    hasUpdate(copies[lhs]?.editableCopies ?? []) && !hasUpdate(copies[rhs]?.editableCopies ?? [])
                }, id: \.self) { folder in
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
                ForEach(updatesFirst(scope.editableCopies)) { copy in
                    let agents = copy.placement.agents.filter(scope.agents.contains).map(\.title).formatted(.list(type: .and))
                    HStack {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(agents).font(.callout)
                            versionStatus(copy.status)
                            path(copy.status.path, relativeTo: folder)
                        }
                        Spacer()
                        SkillDialogActions {
                            copyActions(copy, location: AppLocalization.format("%@ in %@", agents, navigation.name(for: folder.path)), project: folder)
                        }
                    }
                }
                if projectAgents.allSatisfy(globalAgents.contains) {
                    Text("Remove the project copy if you use the Mac-wide copy. This avoids keeping two versions.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                let missing = scope.missing(for: scope.agents)
                if !missing.isEmpty {
                    DesktopActionButton(title: "Install in project") {
                        model.change(.install, targets: missing, project: folder, using: installer)
                    }.disabled(!canInstall)
                }
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
        panel.prompt = AppLocalization.text("Install")
        panel.message = AppLocalization.text("Choose a folder to install this skill for all compatible agents in that project.")
        if panel.runModal() == .OK, let chosen = panel.url {
            projectFilter = ""
            projects.rememberSkillProject(chosen)
            model.change(.install, project: chosen.standardizedFileURL, using: installer)
        }
    }

    private func hasUpdate(_ copies: [SkillCopy]) -> Bool {
        copies.contains { $0.status.state == .updateAvailable }
    }

    private func updatesFirst(_ copies: [SkillCopy]) -> [SkillCopy] {
        copies.sorted { $0.status.state == .updateAvailable && $1.status.state != .updateAvailable }
    }

    private var advanced: some View {
        DisclosureGroup("Technical details") {
            VStack(alignment: .leading, spacing: 10) {
                Text(skill.author + " · " + skill.license)
                if let version = skill.version { Text("Version \(version)") }
                Text("Revision: \(skill.source.revision)").textSelection(.enabled)
                ForEach(skill.requirements, id: \.self) { Text($0) }
                if let url = skill.source.browseURL { DesktopTextLink("View source", destination: url) }
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
        return DisclosureGroup("Show path") {
            Text(verbatim: display).font(.caption.monospaced()).textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
        }.font(.caption).foregroundStyle(.secondary)
    }

    @ViewBuilder private func versionStatus(_ status: SkillInstallationStatus) -> some View {
        if status.matchesPackage == true && status.state != .updateAvailable {
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
            if let version = status.availableVersion, version != status.installedVersion {
                Text(status.installedVersion.map { AppLocalization.format("%@ · Update to %@", $0, version) } ?? AppLocalization.format("Update to %@", version))
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
                                do { try await model.addImport(skill); dismiss() } catch { message = error.presentationDescription() }
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
                        catch { message = error.presentationDescription() }
                    }
                }.buttonStyle(.borderedProminent).disabled(repository.isEmpty)
            }
        }.padding(24).frame(width: 620).disabled(busy).interactiveDismissDisabled(busy)
    }
}
