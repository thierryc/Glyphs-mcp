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
    @Published private(set) var catalogMessage = ""
    @Published var selected: CatalogSkill?
    @Published private(set) var files: [ProjectFile] = []
    @Published var previewPath = "SKILL.md"
    @Published var search = ""
    @Published var category = "All"
    @Published var client: SkillClient?
    @Published var projectScope = false
    @Published var projectURL: URL?
    @Published private(set) var observations: [String: [LocalSkillTarget: SkillInstallationStatus]] = [:]
    @Published private(set) var bundledObservations: [String: [String]] = [:]
    private let store = SkillStore()
    var pendingInspection: CatalogSkill?
    private var snapshot: Data?
    private var catalogEntries: [CatalogSkill] = []
    private var importEntries: [CatalogSkill] = []
    private var task: Task<Void, Never>?
    private var bundledPayload: InstallerPayload?
    private var payloadTask: Task<Void, Never>?
    private var scanGeneration = 0
    private var installer: SupplementalSkillInstaller { .init(bundledNames: Set(catalogEntries.filter(\.bundled).map(\.name))) }
    var filtered: [CatalogSkill] {
        skills.filter { skill in
            (search.isEmpty || (skill.name + " " + skill.description + " " + skill.author).localizedCaseInsensitiveContains(search)) &&
            (client == nil || skill.compatibleClients.contains(client!)) &&
            (category == "All" || category == "Included" && skill.bundled || category == "Additional" && !skill.bundled || category == "Installed" && isInstalled(skill))
        }.sorted { ($0.bundled ? 0 : 1, $0.name) < ($1.bundled ? 0 : 1, $1.name) }
    }
    func isInstalled(_ skill: CatalogSkill) -> Bool {
        skill.bundled ? !(bundledObservations[skill.id] ?? []).isEmpty : observations[skill.id]?.values.contains(where: { $0.state != .notInstalled }) == true
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
        // Clear previous-scope status before the background scan can publish it.
        observations = [:]
        let catalog = catalogEntries
        let imports = importEntries
        let names = Set(catalog.filter(\.bundled).map(\.name))
        let scopeReady = !projectScope || projectURL != nil
        let rootProject = projectScope ? projectURL : nil
        let roots = scopeReady ? LocalSkillTarget.allCases.flatMap { $0.roots(project: rootProject) } : []
        let payload = bundledPayload
        if payload == nil && payloadTask == nil {
            payloadTask = Task { [weak self] in
                guard let self else { return }
                defer { self.payloadTask = nil }
                do {
                    self.bundledPayload = try await InstallerPayloadDiscovery.shared.resolve {
                        try InstallerPayload.resolve()
                    }
                    self.rescan()
                } catch { self.message = error.localizedDescription }
            }
        }
        Task {
            let result = await Task.detached(priority: .userInitiated) {
                let service = SupplementalSkillInstaller(bundledNames: names)
                var entries = catalog
                var scanMessage = ""
                for entry in imports where !entries.contains(where: { $0.id == entry.id || $0.name == entry.name }) { entries.append(entry) }
                for root in roots where FileManager.default.fileExists(atPath: root.path) {
                    do {
                        try service.recover(root: root)
                        for receipt in try service.installed(in: root) where !entries.contains(where: { $0.id == receipt.skill.id || $0.name == receipt.skill.name }) {
                            entries.append(receipt.skill)
                        }
                    } catch { scanMessage = error.localizedDescription }
                }
                let observations = scopeReady ? Dictionary(uniqueKeysWithValues: entries.filter { !$0.bundled }.map { skill in
                    (skill.id, Dictionary(uniqueKeysWithValues: LocalSkillTarget.allCases.map { ($0, service.status(skill, target: $0, project: rootProject)) }))
                }) : [:]
                var bundledObservations: [String: [String]] = [:]
                for skill in entries.filter(\.bundled) {
                    var states: [String] = []
                    for (title, root) in [("Codex", InstallerPaths.codexSkillsDir), ("Claude Code", InstallerPaths.claudeCodeSkillsDir),
                                          ("Cursor", InstallerPaths.cursorPluginDir.appendingPathComponent("skills")),
                                          ("Codex / Cursor", InstallerPaths.home.appendingPathComponent(".agents/skills"))] {
                        let folder = root.appendingPathComponent(skill.name)
                        guard FileManager.default.fileExists(atPath: folder.appendingPathComponent("SKILL.md").path) else { continue }
                        let expected = payload?.skillsDir.map { $0.appendingPathComponent(skill.name) }
                        let equal = expected.flatMap { try? InstallerPayloadManifestResolver.treeIdentity($0) }
                            == (try? InstallerPayloadManifestResolver.treeIdentity(folder))
                        states.append(title + ": " + NSLocalizedString(equal && expected != nil ? "Installed" : "Existing copy — review version", comment: "") + "\n" + folder.path)
                    }
                    bundledObservations[skill.id] = states
                }
                return (entries, observations, bundledObservations, scanMessage)
            }.value
            // Switching again invalidates older work without blocking the next click.
            guard generation == scanGeneration else { return }
            skills = result.0
            observations = result.1
            bundledObservations = result.2
            if !result.3.isEmpty { message = result.3 }
            scanning = false
        }
    }
    func inspect(_ skill: CatalogSkill) {
        guard !busy else { return }
        selected = skill; files = []; previewPath = "SKILL.md"; busy = true; message = "Loading skill instructions…"
        messageIsError = false; operationDetails = ""
        task = Task {
            defer { busy = false }
            do {
                let bundledRoot: URL?
                if skill.bundled {
                    let payload = try await InstallerPayloadDiscovery.shared.resolve { try InstallerPayload.resolve() }
                    bundledRoot = payload.skillsDir
                } else { bundledRoot = nil }
                files = try await store.files(skill, bundledRoot: bundledRoot)
                message = ""
            }
            catch { message = error.localizedDescription; messageIsError = true }
        }
    }
    func discover(repository: String, directory: String, revision: String) async throws -> [CatalogSkill] {
        try await store.discover(repository: repository, directory: directory.isEmpty ? "." : directory, revision: revision)
    }
    func addImport(_ skill: CatalogSkill) async throws {
        guard !catalogEntries.contains(where: { $0.name == skill.name && $0.id != skill.id }) else { throw ProjectError("This name belongs to a catalog skill. Use its reviewed entry instead.") }
        try await store.remember(skill); importEntries = try await store.imports(); rescan(); pendingInspection = skill
    }
    func chooseProject() {
        let panel = NSOpenPanel(); panel.canChooseDirectories = true; panel.canChooseFiles = false; panel.allowsMultipleSelection = false
        if panel.runModal() == .OK { projectURL = panel.url; projectScope = true; rescan() }
    }
    func installSelected(target: LocalSkillTarget, using owner: InstallerViewModel, replace: Bool = false, replaceLink: Bool = false) {
        guard !scanning, let skill = selected, !skill.bundled, target.supports(skill), !files.isEmpty else { return }
        guard !projectScope || projectURL != nil else { message = "Choose a project folder before installing."; return }
        let package = files; let project = projectScope ? projectURL : nil
        let service = installer
        let root = service.installationRoot(skill, target: target, project: project)
        let updating = service.status(skill, root: root).isInstalled
        run(owner, title: updating ? "Updating skill…" : "Installing skill…", success: (updating ? "Updated for " : "Installed for ") + target.title + ".") {
            try await ProjectFiles.perform { try service.install(skill, files: package, root: root, project: project, replace: replace, replaceLink: replaceLink) }
        }
    }
    func remove(_ skill: CatalogSkill, target: LocalSkillTarget, owner: InstallerViewModel) {
        guard !scanning else { return }
        guard !projectScope || projectURL != nil else { message = "Choose a project folder."; return }
        let service = installer
        let root = service.installationRoot(skill, target: target, project: projectScope ? projectURL : nil)
        run(owner, title: "Removing skill…", success: "Removed from " + target.title + ". A backup was kept.") {
            try await ProjectFiles.perform { try service.remove(skill, root: root, preserveExisting: true) }
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
            return "Exported: " + destination.path + "\nUpload and enable this ZIP in your host's Skills settings. Required MCP connections are configured separately; hosted uploads do not grant access to Glyphs on this Mac."
        }
    }
    private func run(_ owner: InstallerViewModel, title: String, success: String? = nil, operation: @escaping () async throws -> String) {
        guard !busy, !owner.operationsBusy else { return }
        busy = true; owner.supplementalSkillsBusy = true; message = title; messageIsError = false; operationDetails = ""; owner.notice = .information(title)
        task = Task {
            defer { busy = false; owner.supplementalSkillsBusy = false; rescan() }
            do { let result = try await operation(); message = success ?? result; operationDetails = success == nil ? "" : result; owner.notice = .information(message) }
            catch { message = error.localizedDescription; messageIsError = true; owner.notice = .information(message) }
        }
    }
}

struct DesktopFocusedSetup: View {
    @EnvironmentObject private var installer: InstallerViewModel
    let section: InstallationView.Section
    let showSetup: () -> Void
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Text(LocalizedStringKey(section == .companions ? "Companion Plugins" : "AI Agents")).font(.largeTitle.bold())
                Text(LocalizedStringKey(section == .companions ? "Manage optional Glyphs plugins. The bundled inspectors require the Glyphs MCP bridge." : "Configure each AI agent independently. Download the client application separately when needed."))
                    .foregroundStyle(.secondary)
                Button("Open Setup", action: showSetup)
                if section == .companions && installer.running {
                    Text("Quit Glyphs before changing components. You can save unsaved fonts when prompted.").foregroundStyle(.orange)
                    Button("Quit Glyphs", action: installer.quitGlyphs).disabled(installer.operationsBusy)
                }
                InstallationView(section: section)
            }.padding(DesktopSetupLayout.contentPadding).frame(maxWidth: DesktopSetupLayout.contentMaximumWidth, alignment: .leading)
                .frame(maxWidth: .infinity)
        }
    }
}

private struct SkillCardPresentation {
    let title: String
    let goal: String
    init(_ skill: CatalogSkill) {
        let included: [String: (String, String)] = [
            "glyphs": ("Font workflows", "Find the right workflow for your next font task."),
            "glyphs-mcp-development": ("Scripts & plugins", "Build tools that make your font work easier."),
            "glyphs-mcp-italic-first-pass": ("Italic first pass", "Prepare a first slant for your italic design."),
            "glyphs-mcp-kerning": ("Kerning", "Review the spacing between letter pairs."),
            "glyphs-mcp-maintainer-feedback": ("Report an issue", "Collect useful details for a clear bug report."),
            "glyphs-mcp-master-compatibility": ("Master consistency", "Compare contour starts across your masters."),
            "glyphs-mcp-opentype-features": ("OpenType features", "Write and check your font’s OpenType features."),
            "glyphs-mcp-outlines-docs": ("Outline review", "Inspect curves and plan focused outline edits."),
            "glyphs-mcp-release": ("Prepare a release", "Check a Glyphs MCP release before publication."),
            "glyphs-mcp-scripting": ("Font scripts", "Create a focused script for a font task."),
            "glyphs-mcp-spacing": ("Spacing", "Prepare spacing suggestions from reference letters.")
        ]
        if skill.bundled, let content = included[skill.name] {
            title = content.0; goal = content.1
        } else {
            title = skill.name.replacingOccurrences(of: "-", with: " ").capitalized
            goal = skill.name == "dekink-native" ? "Find and repair interpolation kinks while preserving your master outlines."
                : skill.description.components(separatedBy: ". ").first ?? skill.description
        }
    }
}

private struct DesktopSkillCard: View {
    let skill: CatalogSkill
    let installed: Bool
    let hasUpdate: Bool
    let open: () -> Void
    @State private var hovering = false
    private var presentation: SkillCardPresentation { .init(skill) }
    private var badge: String { hasUpdate ? "Update available" : installed ? "Installed" : skill.bundled ? "Included" : "Available" }
    var body: some View {
        Button(action: open) {
            VStack(alignment: .leading, spacing: 12) {
                Text(LocalizedStringKey(presentation.title)).font(.headline).foregroundStyle(.primary)
                Text(LocalizedStringKey(presentation.goal)).font(.callout).foregroundStyle(.secondary)
                    .lineLimit(2).fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 8)
                HStack {
                    Text(LocalizedStringKey(badge)).font(.caption.weight(.medium))
                        .foregroundStyle(hasUpdate ? Color.orange : Color.accentColor)
                        .padding(.horizontal, 9).padding(.vertical, 4)
                        .background(Color.accentColor.opacity(0.08), in: Capsule())
                    Spacer()
                    Text("Details").font(.caption.weight(.medium)).foregroundStyle(Color.accentColor)
                }
            }.padding(18).frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                .frame(minHeight: 155)
                .background(Color(nsColor: .windowBackgroundColor), in: RoundedRectangle(cornerRadius: 14))
                .overlay(RoundedRectangle(cornerRadius: 14).fill(Color.accentColor.opacity(hovering ? 0.065 : 0.025)))
                .overlay(RoundedRectangle(cornerRadius: 14).strokeBorder(Color.accentColor.opacity(hovering ? 0.35 : 0.16)))
                .shadow(color: Color.primary.opacity(0.035), radius: 6, y: 2)
                .contentShape(RoundedRectangle(cornerRadius: 14))
        }.buttonStyle(.plain).onHover { hovering = $0 }
            .accessibilityElement(children: .combine)
            .accessibilityHint("View details and installation options")
    }
}

struct DesktopSkillsView: View {
    @ObservedObject var model: DesktopSkillsModel
    @ObservedObject var installer: InstallerViewModel
    let project: String?
    let manageAgents: () -> Void
    @State private var showingImport = false
    @State private var replacementTarget: LocalSkillTarget?
    @State private var replacingLink = false
    @State private var removalTarget: LocalSkillTarget?
    @State private var showingInformation = false
    @State private var informationTab = "Instructions"
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                HStack(alignment: .firstTextBaseline) {
                    Text("Skills").font(.largeTitle.bold()); Spacer()
                    Button("Refresh") { model.load(refresh: true) }.disabled(model.busy)
                    Button("Add from GitHub…") { showingImport = true }.disabled(model.busy || installer.operationsBusy)
                    Link("Contribute", destination: SkillCatalog.contributionURL)
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
                            hasUpdate: model.observations[skill.id]?.values.contains(where: { $0.state == .updateAvailable }) == true) { model.inspect(skill) }
                            .disabled(model.busy)
                    }
                }
                if model.filtered.isEmpty && !model.busy && !model.scanning { Text("No matching skills.").foregroundStyle(.secondary) }
            }.padding(DesktopSetupLayout.contentPadding)
                .frame(maxWidth: DesktopSetupLayout.contentMaximumWidth, alignment: .leading).frame(maxWidth: .infinity)
        }
        .task { if model.skills.isEmpty { model.load() } else { model.rescan() } }
        .onChange(of: model.projectScope) { _, _ in model.rescan() }
        .onChange(of: installer.busy) { _, busy in if !busy { model.rescan() } }
        .sheet(isPresented: $showingImport, onDismiss: {
            if let skill = model.pendingInspection { model.pendingInspection = nil; model.inspect(skill) }
        }) { SkillImportSheet(model: model) }
        .sheet(item: $model.selected) { skill in
            VStack(spacing: 0) {
                HStack(spacing: 16) {
                    Button {
                        guard !model.busy, !installer.operationsBusy else { return }
                        model.selected = nil
                    } label: {
                        Image(systemName: "xmark").font(.system(size: 13, weight: .semibold))
                            .frame(width: 28, height: 28)
                            .background(Color.primary.opacity(0.06), in: Circle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Close")
                    .help("Close")
                    .keyboardShortcut(.cancelAction)
                    .disabled(model.busy || installer.operationsBusy)
                    Text(LocalizedStringKey(SkillCardPresentation(skill).title)).font(.title2.bold())
                    Spacer()
                }.padding(.horizontal, 28).padding(.top, 24).padding(.bottom, 12)
                ScrollView { detail(skill).padding(.horizontal, 28).padding(.bottom, 24) }
            }.frame(width: 660, height: 580)
                .background(Color(nsColor: .textBackgroundColor))
                .interactiveDismissDisabled(model.busy || installer.operationsBusy)
                .sheet(isPresented: $showingInformation) { informationSheet(skill) }
                .confirmationDialog("Update this skill?", isPresented: Binding(get: { replacementTarget != nil }, set: { if !$0 { replacementTarget = nil } }), titleVisibility: .visible) {
                    if let target = replacementTarget {
                        Button("Update") { replacementTarget = nil; model.installSelected(target: target, using: installer, replace: true, replaceLink: replacingLink) }
                    }
                } message: {
                    Text(LocalizedStringKey(replacingLink ? "This replaces the link with a managed copy of the catalog version. Your original folder stays untouched, and a backup of the link will be kept." : "Your existing copy will be backed up before it is replaced with the catalog version."))
                }
                .confirmationDialog("Remove this skill?", isPresented: Binding(get: { removalTarget != nil }, set: { if !$0 { removalTarget = nil } }), titleVisibility: .visible) {
                    if let target = removalTarget {
                        Button("Remove", role: .destructive) { removalTarget = nil; model.remove(skill, target: target, owner: installer) }
                    }
                } message: {
                    Text("A backup will be kept. If this is a linked folder, only the link is removed; the original folder stays untouched.")
                }
        }
    }
    @ViewBuilder private func detail(_ skill: CatalogSkill) -> some View {
        let presentation = SkillCardPresentation(skill)
        VStack(alignment: .leading, spacing: 20) {
            Text(LocalizedStringKey(presentation.goal)).foregroundStyle(.secondary)
            if !model.message.isEmpty {
                HStack(alignment: .top, spacing: 10) {
                    if model.busy { ProgressView().controlSize(.small) }
                    else { Image(systemName: model.messageIsError ? "exclamationmark.triangle.fill" : "checkmark.circle.fill").foregroundStyle(model.messageIsError ? Color.orange : Color.green) }
                    Text(LocalizedStringKey(model.message)).font(.callout).textSelection(.enabled)
                }.padding(12).frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 10))
            }
            if skill.bundled {
                VStack(alignment: .leading, spacing: 14) {
                    Text("Included with Glyphs MCP").font(.headline)
                    Text("Manage this skill with your AI agent setup.").foregroundStyle(.secondary)
                    Button("Manage AI Agent Setup") { model.selected = nil; manageAgents() }
                        .disabled(model.busy || installer.operationsBusy)
                    ForEach(model.bundledObservations[skill.id] ?? [], id: \.self) {
                        Text($0).foregroundStyle(.secondary).textSelection(.enabled)
                    }
                    if !model.isInstalled(skill) { Text("Included; not installed in a detected local location.").foregroundStyle(.secondary) }
                }.padding(18).frame(maxWidth: .infinity, alignment: .leading)
                    .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.primary.opacity(0.15)))
            } else {
                installationPane(skill)
            }
            VStack(alignment: .leading, spacing: 8) {
                Text(LocalizedStringKey(skill.bundled ? "Included skill" : "Community skill"))
                ForEach(skill.requirements, id: \.self) { Text($0) }
                HStack(spacing: 24) {
                    Button("View source") { informationTab = "Source"; showingInformation = true }
                    Button("Read instructions") { informationTab = "Instructions"; showingInformation = true }
                }.buttonStyle(.link).padding(.top, 4)
            }
            HStack {
                if skill.compatibleClients.contains(.chatgpt) { Link("ChatGPT upload guide", destination: URL(string: "https://developers.openai.com/cookbook/examples/chatgpt/chatgpt_prompt_guide/chatgpt_prompt_guide")!) }
                if skill.compatibleClients.contains(.claude) { Link("Claude upload guide", destination: URL(string: "https://support.claude.com/en/articles/12512198-how-to-create-custom-skills")!) }
                Spacer()
                Button("Export ZIP…") { model.export(skill, owner: installer) }
                    .disabled(model.busy || installer.operationsBusy || model.files.isEmpty)
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
    private func installationPane(_ skill: CatalogSkill) -> some View {
        VStack(alignment: .leading, spacing: 24) {
            Text("Installation").font(.headline)
            VStack(alignment: .leading, spacing: 16) {
                Text(LocalizedStringKey(model.projectScope ? "Available only in the selected project." : "Available across your projects on this Mac."))
                    .foregroundStyle(.secondary)
                HStack(spacing: 12) {
                    Text(LocalizedStringKey(model.projectScope ? "Project folder:" : "Location:"))
                    Image(systemName: model.projectScope ? "folder.fill" : "house.fill").foregroundStyle(Color.accentColor)
                    Text(model.projectScope ? model.projectURL?.lastPathComponent ?? NSLocalizedString("Choose a project folder", comment: "") : NSHomeDirectory())
                        .lineLimit(1).truncationMode(.middle)
                        .help(model.projectScope ? model.projectURL?.path ?? "" : NSHomeDirectory())
                    Spacer(minLength: 0)
                    if model.projectScope {
                        Menu("Choose…") {
                            Button("Choose Project…", action: model.chooseProject)
                            if let project {
                                Button("Use Last Project") { model.projectURL = URL(fileURLWithPath: project); model.rescan() }
                            }
                        }.fixedSize().disabled(model.busy || installer.operationsBusy)
                    }
                }.frame(height: 32)
                Divider()
                ForEach(LocalSkillTarget.allCases.filter { $0.supports(skill) }) { target in
                    installationRow(skill, target: target)
                }
            }.padding(18).padding(.top, 12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.primary.opacity(0.15)))
                .overlay(alignment: .top) {
                    SkillLocationPicker(projectScope: $model.projectScope)
                        .disabled(model.busy || installer.operationsBusy)
                        .padding(.horizontal, 6)
                        .background(Color(nsColor: .textBackgroundColor))
                        .offset(y: -16)
                }
        }
    }
    private func installationRow(_ skill: CatalogSkill, target: LocalSkillTarget) -> some View {
        let status = model.observations[skill.id]?[target]
        let installed = status?.isInstalled == true
        let linked = status?.state == .linked
        let unavailable = model.busy || model.scanning || installer.operationsBusy || model.projectScope && model.projectURL == nil
        return VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 16) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(LocalizedStringKey(target == .agents ? "Codex & Cursor" : target.title)).font(.headline)
                    HStack(spacing: 6) {
                        if model.scanning { ProgressView().controlSize(.mini) }
                        Text(LocalizedStringKey(model.scanning ? "Checking installation…" : status?.title ?? "Choose a project folder"))
                    }.foregroundStyle(.secondary)
                }
                Spacer()
                Button(LocalizedStringKey(installed ? "Update" : "Install")) {
                    if status?.requiresBackupConfirmation == true || linked { replacingLink = linked; replacementTarget = target }
                    else { model.installSelected(target: target, using: installer) }
                }.buttonStyle(.borderedProminent)
                    .disabled(unavailable || model.files.isEmpty)
                    .accessibilityLabel((installed ? "Update for " : "Install for ") + target.title)
                    .help(installed ? "Install the current catalog version. A backup will be kept." : "Install this skill for this agent.")
                Menu {
                    if let status, status.isInstalled {
                        Button("Show in Finder") { NSWorkspace.shared.selectFile(status.path, inFileViewerRootedAtPath: "") }
                    }
                    Button("Locations and activity") { informationTab = "Activity"; showingInformation = true }
                    Button("Remove", role: .destructive) { removalTarget = target }.disabled(!installed)
                } label: { Image(systemName: "ellipsis") }
                    .menuIndicator(.hidden).fixedSize()
                    .disabled(unavailable)
                    .accessibilityLabel("More options for " + target.title)
            }
            Text(status?.path ?? " ").foregroundStyle(.secondary).lineLimit(1).truncationMode(.middle)
                .textSelection(.enabled).help(status?.path ?? "")
            if linked {
                Text("This skill uses a linked local folder. Update installs a managed copy here; Remove detaches the link. Both keep your original folder.")
                    .foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
    private func informationSheet(_ skill: CatalogSkill) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text(LocalizedStringKey(SkillCardPresentation(skill).title)).font(.title2.bold())
                Spacer()
                Button("Done") { showingInformation = false }.keyboardShortcut(.cancelAction)
            }
            Picker("Information", selection: $informationTab) {
                Text("Instructions").tag("Instructions")
                Text("Source").tag("Source")
                Text("Activity").tag("Activity")
            }.pickerStyle(.segmented)
            if informationTab == "Instructions", !model.files.isEmpty {
                Picker("File", selection: $model.previewPath) {
                    ForEach(model.files.filter { $0.data != nil }, id: \.path) { Text($0.path).tag($0.path) }
                }
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    if informationTab == "Instructions" {
                        if let data = model.files.first(where: { $0.path == model.previewPath })?.data {
                            if let text = String(data: data, encoding: .utf8) {
                                if text.count > 100_000 { Text("Preview limited to 100,000 characters. The complete file is included in installation and export.") }
                                Text(String(text.prefix(100_000))).font(.system(.body, design: .monospaced)).textSelection(.enabled)
                            } else { Text("Binary resource; included in installation and export.") }
                        } else { Text("Instructions are not available yet.") }
                    } else if informationTab == "Source" {
                        Text(skill.name).font(.headline)
                        Text(skill.description)
                        Text(skill.author + " · " + skill.license)
                        Text("Revision: " + skill.source.revision).textSelection(.enabled)
                        if let url = skill.source.browseURL { Link("Open on GitHub", destination: url) }
                        Text("Clients: " + skill.compatibleClients.map(\.title).joined(separator: ", "))
                        ForEach(skill.requirements, id: \.self) { Text($0) }
                        Text("Exports require upload and activation in the host. Local Glyphs access and other dependencies must be configured separately.").foregroundStyle(.secondary)
                    } else {
                        ForEach(LocalSkillTarget.allCases.filter { $0.supports(skill) }) { target in
                            if let status = model.observations[skill.id]?[target] {
                                Text(LocalizedStringKey(target.title)).font(.headline)
                                Text(status.path).textSelection(.enabled)
                                Text(LocalizedStringKey(status.title)).foregroundStyle(.secondary)
                            }
                        }
                        if !model.operationDetails.isEmpty { Text(model.operationDetails).textSelection(.enabled) }
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }
        }.padding(24).frame(width: 620, height: 520)
            .background(Color(nsColor: .textBackgroundColor))
    }

}

// A compact scope selector with equal segments and native button focus behavior.
private struct SkillLocationPicker: View {
    @Binding var projectScope: Bool
    @Environment(\.isEnabled) private var isEnabled
    var body: some View {
        HStack(spacing: 2) {
            segment("All My Projects", project: false)
            segment("One Project", project: true)
        }.padding(3)
            .background(Color.primary.opacity(0.06), in: Capsule())
            .overlay(Capsule().stroke(Color.primary.opacity(0.12)))
            .opacity(isEnabled ? 1 : 0.5)
            .accessibilityElement(children: .contain)
            .accessibilityLabel("Install location")
    }
    private func segment(_ title: LocalizedStringKey, project: Bool) -> some View {
        Button { projectScope = project } label: {
            Text(title).frame(width: 138, height: 26)
                .background {
                    if projectScope == project {
                        Capsule().fill(Color(nsColor: .textBackgroundColor))
                            .shadow(color: .black.opacity(0.12), radius: 2, y: 1)
                    }
                }
                .contentShape(Capsule())
        }.buttonStyle(.plain)
            .accessibilityAddTraits(projectScope == project ? .isSelected : [])
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
                        VStack(alignment: .leading) { Text(skill.name).font(.headline); Text(skill.description).font(.caption) }
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
