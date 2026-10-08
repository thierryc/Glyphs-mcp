import AppKit
import SwiftUI
import GlyphsMCPInstallerCore

@MainActor
final class DesktopSkillsModel: ObservableObject {
    @Published private(set) var skills: [CatalogSkill] = []
    @Published private(set) var busy = false
    @Published var message = ""
    @Published private(set) var catalogMessage = ""
    @Published var selected: CatalogSkill?
    @Published private(set) var files: [ProjectFile] = []
    @Published var previewPath = "SKILL.md"
    @Published var search = ""
    @Published var category = "All"
    @Published var client: SkillClient?
    @Published var projectScope = false
    @Published var projectURL: URL?
    @Published var targets: Set<LocalSkillTarget> = [.agents]
    @Published private(set) var observations: [String: [LocalSkillTarget: SkillInstallationStatus]] = [:]
    @Published private(set) var bundledObservations: [String: [String]] = [:]
    private let store = SkillStore()
    var pendingInspection: CatalogSkill?
    private var snapshot: Data?
    private var catalogEntries: [CatalogSkill] = []
    private var importEntries: [CatalogSkill] = []
    private var task: Task<Void, Never>?
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
        var entries = catalogEntries
        for entry in importEntries where !entries.contains(where: { $0.id == entry.id || $0.name == entry.name }) { entries.append(entry) }
        let scopeReady = !projectScope || projectURL != nil
        let rootProject = projectScope ? projectURL : nil
        let roots = scopeReady ? LocalSkillTarget.allCases.map { $0.root(project: rootProject) } : []
        for root in roots where FileManager.default.fileExists(atPath: root.path) {
            do {
                try installer.recover(root: root)
                for receipt in try installer.installed(in: root) where !entries.contains(where: { $0.id == receipt.skill.id || $0.name == receipt.skill.name }) {
                    entries.append(receipt.skill)
                }
            } catch { message = error.localizedDescription }
        }
        skills = entries
        observations = scopeReady ? Dictionary(uniqueKeysWithValues: entries.filter { !$0.bundled }.map { skill in
            (skill.id, Dictionary(uniqueKeysWithValues: LocalSkillTarget.allCases.map { ($0, installer.status(skill, root: $0.root(project: rootProject))) }))
        }) : [:]
        let payload = try? InstallerPayload.resolve()
        bundledObservations = [:]
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
    }
    func inspect(_ skill: CatalogSkill) {
        guard !busy else { return }
        let compatibleTargets = Set(LocalSkillTarget.allCases.filter { $0.supports(skill) })
        targets = targets.intersection(compatibleTargets)
        if targets.isEmpty, let first = LocalSkillTarget.allCases.first(where: { compatibleTargets.contains($0) }) { targets = [first] }
        selected = skill; files = []; previewPath = "SKILL.md"; busy = true; message = "Loading skill instructions…"
        task = Task {
            defer { busy = false }
            do { files = try await store.files(skill, bundledRoot: (try? InstallerPayload.resolve())?.skillsDir); message = "" }
            catch { message = error.localizedDescription }
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
    func installSelected(using owner: InstallerViewModel, replace: Bool = false) {
        guard let skill = selected, !skill.bundled, !targets.isEmpty, !files.isEmpty else { return }
        guard !projectScope || projectURL != nil else { message = "Choose a project folder before installing."; return }
        let package = files; let project = projectScope ? projectURL : nil
        let selectedTargets = targets.filter { $0.supports(skill) }
        guard !selectedTargets.isEmpty else { message = "Choose a compatible local client."; return }
        let service = installer
        run(owner, title: "Installing skill…") {
            var outcomes: [String] = []
            for target in selectedTargets.sorted(by: { $0.rawValue < $1.rawValue }) {
                do {
                    let result = try await ProjectFiles.perform { try service.install(skill, files: package, root: target.root(project: project), project: project, replace: replace) }
                    outcomes.append(target.title + "\n" + result)
                } catch { outcomes.append(target.title + ": " + error.localizedDescription) }
            }
            return outcomes.joined(separator: "\n\n")
        }
    }
    func remove(_ skill: CatalogSkill, target: LocalSkillTarget, owner: InstallerViewModel) {
        guard !projectScope || projectURL != nil else { message = "Choose a project folder."; return }
        let root = target.root(project: projectScope ? projectURL : nil); let service = installer
        run(owner, title: "Removing skill…") { try await ProjectFiles.perform { try service.remove(skill, root: root) } }
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
    private func run(_ owner: InstallerViewModel, title: String, operation: @escaping () async throws -> String) {
        guard !busy, !owner.operationsBusy else { return }
        busy = true; owner.supplementalSkillsBusy = true; message = title; owner.notice = .information(title)
        task = Task {
            defer { busy = false; owner.supplementalSkillsBusy = false; rescan() }
            do { message = try await operation(); owner.notice = .information(message) }
            catch { message = error.localizedDescription; owner.notice = .information(message) }
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
            goal = skill.description.components(separatedBy: ". ").first ?? skill.description
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
    @State private var replaceConfirmation = false
    @State private var removalTarget: LocalSkillTarget?
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
                if model.busy && model.selected == nil { ProgressView().controlSize(.small) }
                if !model.catalogMessage.isEmpty { Text(LocalizedStringKey(model.catalogMessage)).font(.callout) }
                SetupCardGrid {
                    ForEach(model.filtered) { skill in
                        DesktopSkillCard(skill: skill, installed: model.isInstalled(skill),
                            hasUpdate: model.observations[skill.id]?.values.contains(where: { $0.state == .updateAvailable }) == true) { model.inspect(skill) }
                            .disabled(model.busy)
                    }
                }
                if model.filtered.isEmpty && !model.busy { Text("No matching skills.").foregroundStyle(.secondary) }
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
            ScrollView { detail(skill).padding(28) }.frame(width: 790, height: 720)
                .interactiveDismissDisabled(model.busy)
                .confirmationDialog("Replace existing skill copies with verified backups?", isPresented: $replaceConfirmation, titleVisibility: .visible) {
                    Button("Replace with backup", role: .destructive) { model.installSelected(using: installer, replace: true) }
                }
                .confirmationDialog("Remove this installed skill? A backup will be kept.", isPresented: Binding(get: { removalTarget != nil }, set: { if !$0 { removalTarget = nil } }), titleVisibility: .visible) {
                    if let target = removalTarget {
                        Button("Remove", role: .destructive) { removalTarget = nil; model.remove(skill, target: target, owner: installer) }
                    }
                }
        }
    }
    @ViewBuilder private func detail(_ skill: CatalogSkill) -> some View {
        let presentation = SkillCardPresentation(skill)
        VStack(alignment: .leading, spacing: 20) {
            HStack { Text(LocalizedStringKey(presentation.title)).font(.title2.bold()); Spacer(); Button("Done") { model.selected = nil }.disabled(model.busy) }
            Text(LocalizedStringKey(presentation.goal)).foregroundStyle(.secondary)
            if model.busy { ProgressView().controlSize(.small) }
            if !model.message.isEmpty { Text(LocalizedStringKey(model.message)).font(.callout).textSelection(.enabled) }
            if skill.bundled {
                Text("Included with Glyphs MCP").font(.callout).foregroundStyle(Color.accentColor)
                Button("Manage AI Agent Setup") { model.selected = nil; manageAgents() }
                DisclosureGroup("Installed copies") {
                    ForEach(model.bundledObservations[skill.id] ?? [], id: \.self) { Text($0).font(.caption).textSelection(.enabled).padding(.vertical, 4) }
                    if !model.isInstalled(skill) { Text("Included; not installed in a detected local location.").font(.caption) }
                }
            } else {
                Text(LocalizedStringKey(skill.categoryTitle)).font(.caption).foregroundStyle(.secondary)
                Text("Add to your agents").font(.headline)
                HStack {
                    Picker("Scope", selection: $model.projectScope) { Text("Personal").tag(false); Text("Project").tag(true) }.pickerStyle(.segmented).frame(width: 220)
                    if model.projectScope {
                        Button("Choose Project…", action: model.chooseProject)
                        if let project, model.projectURL == nil {
                            Button("Use Last Project") { model.projectURL = URL(fileURLWithPath: project); model.rescan() }
                        }
                    }
                }.disabled(model.busy || installer.operationsBusy)
                if model.projectScope, let url = model.projectURL { Text(url.lastPathComponent).font(.caption).foregroundStyle(.secondary) }
                HStack {
                    ForEach(LocalSkillTarget.allCases.filter { $0.supports(skill) }) { target in
                        Toggle(LocalizedStringKey(target.title), isOn: Binding(get: { model.targets.contains(target) }, set: { if $0 { model.targets.insert(target) } else { model.targets.remove(target) } })).toggleStyle(.checkbox)
                    }
                }.disabled(model.busy || installer.operationsBusy)
                HStack {
                    Button("Add / Update Skill") { model.installSelected(using: installer) }.buttonStyle(.borderedProminent)
                    Menu("More") {
                        Button("Replace with backup…") { replaceConfirmation = true }
                        ForEach(LocalSkillTarget.allCases) { target in
                            if let state = model.observations[skill.id]?[target], state.state == .installed || state.state == .updateAvailable {
                                Button("Remove from \(target.title)…") { removalTarget = target }
                            }
                        }
                    }
                }.disabled(model.busy || installer.operationsBusy || model.files.isEmpty || model.projectScope && model.projectURL == nil || model.targets.isEmpty)
                DisclosureGroup("Installed copies") {
                    ForEach(LocalSkillTarget.allCases) { target in
                        if let status = model.observations[skill.id]?[target] {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(NSLocalizedString(target.title, comment: "") + ": " + NSLocalizedString(status.title, comment: ""))
                                Text(status.path).foregroundStyle(.secondary).textSelection(.enabled)
                            }.font(.caption).padding(.vertical, 4)
                        }
                    }
                }
            }
            HStack {
                Button("Export ZIP…") { model.export(skill, owner: installer) }.disabled(model.busy || installer.operationsBusy || model.files.isEmpty)
                if skill.compatibleClients.contains(.chatgpt) { Link("ChatGPT upload guide", destination: URL(string: "https://developers.openai.com/cookbook/examples/chatgpt/chatgpt_prompt_guide/chatgpt_prompt_guide")!) }
                if skill.compatibleClients.contains(.claude) { Link("Claude upload guide", destination: URL(string: "https://support.claude.com/en/articles/12512198-how-to-create-custom-skills")!) }
            }.font(.callout)
            Divider()
            DisclosureGroup("Source and requirements") {
                VStack(alignment: .leading, spacing: 10) {
                    Text(skill.name).font(.caption).textSelection(.enabled)
                    Text(skill.description).font(.callout)
                    Text(skill.author + " · " + skill.license).font(.caption)
                    Text("Revision: " + skill.source.revision).font(.caption).textSelection(.enabled)
                    if let url = skill.source.browseURL { Link("Open on GitHub", destination: url) }
                    Text("Clients: " + skill.compatibleClients.map(\.title).joined(separator: ", ")).font(.caption)
                    ForEach(skill.requirements, id: \.self) { Text($0).font(.callout) }
                    Text("Exports require upload and activation in the host. Local Glyphs access and other dependencies must be configured separately.").font(.caption).foregroundStyle(.secondary)
                }.padding(.top, 10)
            }
            DisclosureGroup("Instructions and files") {
                if !model.files.isEmpty {
                    Picker("File", selection: $model.previewPath) {
                        ForEach(model.files.filter { $0.data != nil }, id: \.path) { Text($0.path).tag($0.path) }
                    }.padding(.top, 10)
                    if let data = model.files.first(where: { $0.path == model.previewPath })?.data {
                        if let text = String(data: data, encoding: .utf8) {
                            if text.count > 100_000 { Text("Preview limited to 100,000 characters. The complete file is included in installation and export.").font(.caption) }
                            ScrollView { Text(String(text.prefix(100_000))).font(.system(.caption, design: .monospaced)).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading) }.frame(height: 210)
                        } else { Text("Binary resource; included in installation and export.").font(.caption) }
                    }
                }
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
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
