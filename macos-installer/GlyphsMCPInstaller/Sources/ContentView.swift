import AppKit
import SwiftUI
import GlyphsMCPInstallerCore

struct ContentView: View {
    @EnvironmentObject private var installer: InstallerViewModel
    @EnvironmentObject private var desktop: DesktopModel
    @StateObject private var projects = DesktopProjectsModel()
    @AppStorage("projectsExpanded") private var projectsExpanded = true
    @State private var columnVisibility: NavigationSplitViewVisibility = .all

    var body: some View {
        NavigationSplitView(columnVisibility: $columnVisibility) {
            ScrollView {
                VStack(alignment: .leading, spacing: 4) {
                    sidebarItem("Overview", icon: "square.grid.2x2", destination: .overview)
                    sidebarItem("Components", icon: "puzzlepiece.extension", destination: .components)
                    sidebarItem("Project", icon: "folder.badge.plus", destination: .templates)
                    HStack(spacing: 6) {
                        Button { projectsExpanded.toggle() } label: {
                            Image(systemName: projectsExpanded ? "chevron.down" : "chevron.right")
                                .font(.system(size: 10, weight: .semibold)).frame(width: 14, height: 22)
                        }.buttonStyle(.plain)
                            .accessibilityLabel(projectsExpanded ? "Collapse My Project" : "Expand My Project")
                        Text("My Project").fontWeight(.semibold).frame(maxWidth: .infinity, alignment: .leading)
                        DesktopProjectActions(model: projects)
                    }.font(.callout).foregroundStyle(.secondary).padding(.horizontal, 8).padding(.top, 16).padding(.bottom, 4)
                    if projectsExpanded {
                        ForEach(projects.navigation.recent, id: \.self) { path in
                            projectRow(path)
                        }
                        if projects.navigation.recent.isEmpty {
                            Text("No projects yet").font(.caption).foregroundStyle(.secondary).padding(.horizontal, 12)
                        }
                    }
                }.padding(12)
            }
            .safeAreaInset(edge: .bottom) {
                Button { desktop.showWelcome() } label: {
                    Label("Welcome & Support", systemImage: "heart.circle").frame(maxWidth: .infinity, alignment: .leading)
                }.buttonStyle(.plain).padding()
            }
            .modifier(DesktopSidebarToolbarDefaults())
            .frame(minWidth: 190)
            .navigationSplitViewColumnWidth(min: 190, ideal: 225, max: 300)
        } detail: {
            switch projects.navigation.destination {
            case .overview: DesktopOverview { id, enabled in
                installer.prepareComponentChange(id, enabled: enabled)
                projects.select(.components)
            }
            case .components: InstallationView()
            case .templates: DesktopProjectCatalog(model: projects)
            case .project(let path): DesktopProjectWorkspace(model: projects, path: path)
            }
        }
        .navigationTitle(DesktopIdentity.applicationTitle)
        .modifier(DesktopSidebarToggle(columnVisibility: $columnVisibility))
        .frame(minWidth: 800, minHeight: 600)
        .task { projects.inspect(); await projects.loadTemplates() }
        .sheet(item: $projects.creation) { creation in
            DesktopProjectWizard(model: projects, template: creation.template)
        }
        .sheet(item: $projects.editing) { editing in
            DesktopProjectSettings(model: projects, path: editing.id)
        }
    }

    private func projectRow(_ path: String) -> some View {
        let selected = projects.selectedProject == path
        let name = projects.navigation.name(for: path)
        return HStack(spacing: 4) {
            Button { projects.select(.project(path)) } label: {
                Label(name, systemImage: "folder").lineLimit(1).truncationMode(.middle)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 8)
                    .contentShape(Rectangle())
            }.buttonStyle(.plain).help(path)
                .accessibilityAddTraits(selected ? .isSelected : [])
            Menu { DesktopProjectMenuActions(model: projects, path: path) } label: {
                Image(systemName: "ellipsis").frame(width: 22, height: 24).contentShape(Rectangle())
            }.menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
                .accessibilityLabel("More for \(name)").help("Project actions")
        }.padding(.horizontal, 10)
            .foregroundStyle(selected ? Color.white : Color.primary)
            .background(selected ? Color.accentColor : Color.clear, in: RoundedRectangle(cornerRadius: 8))
            .contextMenu { DesktopProjectMenuActions(model: projects, path: path) }
    }

    private func sidebarItem(_ title: String, icon: String, destination: DesktopDestination) -> some View {
        let selected = projects.navigation.destination == destination
        return Button { projects.select(destination) } label: {
            Label(title, systemImage: icon).lineLimit(1).truncationMode(.middle)
                .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 10).padding(.vertical, 8)
                .contentShape(Rectangle())
        }.buttonStyle(.plain)
            .foregroundStyle(selected ? Color.white : Color.primary)
            .background(selected ? Color.accentColor : Color.clear, in: RoundedRectangle(cornerRadius: 8))
            .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

private struct DesktopSidebarToggle: ViewModifier {
    @Binding var columnVisibility: NavigationSplitViewVisibility

    @ViewBuilder func body(content: Content) -> some View {
        if #available(macOS 14, *) {
            content.toolbar {
                ToolbarItem(placement: .navigation) {
                    Button {
                        columnVisibility = columnVisibility == .detailOnly ? .all : .detailOnly
                    } label: {
                        Label(columnVisibility == .detailOnly ? "Show Sidebar" : "Hide Sidebar", systemImage: "sidebar.left")
                    }
                    .help(columnVisibility == .detailOnly ? "Show Sidebar" : "Hide Sidebar")
                }
            }
        } else {
            content
        }
    }
}

private struct DesktopSidebarToolbarDefaults: ViewModifier {
    @ViewBuilder func body(content: Content) -> some View {
        if #available(macOS 14, *) {
            content.toolbar(removing: .sidebarToggle)
        } else {
            content
        }
    }
}

struct DesktopOverview: View {
    @EnvironmentObject private var installer: InstallerViewModel
    @EnvironmentObject private var desktop: DesktopModel
    let changeComponent: (String, Bool) -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 26) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Your Glyphs workspace").font(.largeTitle.bold())
                }
                GroupBox {
                    VStack(alignment: .leading, spacing: 16) {
                        HStack {
                            Image(systemName: desktop.statusSymbol)
                                .foregroundStyle(desktop.stale ? Color.secondary : Color.accentColor).font(.title2)
                            VStack(alignment: .leading, spacing: 4) {
                                Text(desktop.title).font(.title2.weight(.semibold))
                                Text("MCP port \(String(desktop.installation.port))").foregroundStyle(.secondary)
                            }
                            Spacer()
                            DesktopServerButton()
                        }
                        if !desktop.notice.isEmpty { Text(desktop.notice).font(.callout).foregroundStyle(.secondary) }
                        Divider()
                        DesktopActivityView()
                    }.padding(12).frame(maxWidth: .infinity, alignment: .leading)
                }
                HStack(spacing: 12) {
                    Button("Open Glyphs", action: installer.openGlyphs).disabled(installer.application == nil)
                    Button("Refresh") { Task { await desktop.refresh() } }
                    Spacer()
                    Text(installer.versionLabel).font(.caption).foregroundStyle(.secondary)
                }
                VStack(alignment: .leading, spacing: 16) {
                    Text("Components").font(.title3.bold())
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 210), spacing: 16)], spacing: 16) {
                        ForEach(DesktopComponent.all) { component in
                            ComponentCard(component: component) {
                                Text(component.title).font(.headline)
                            } action: {
                                let installed = installer.installed.contains(component.id)
                                HStack {
                                    Text(installed ? "Installed" : "Not installed").font(.caption).foregroundStyle(.secondary)
                                    Spacer()
                                    Button(installed ? "Remove" : "Install") { changeComponent(component.id, !installed) }
                                        .disabled(installer.busy || !installer.applications.contains { $0.majorVersion == .v4 })
                                        .accessibilityLabel("\(installed ? "Remove" : "Install") \(component.title)")
                                        .help(installed ? "Review removal in Components. Its preferences will be kept." : "Review installation in Components for Glyphs 4.")
                                }
                            }
                        }
                    }
                }
                DisclosureGroup("Troubleshooting") {
                    VStack(alignment: .leading, spacing: 10) {
                        Text("MCP endpoint: \(desktop.installation.endpoint.absoluteString)").textSelection(.enabled)
                        if let executable = desktop.status?.worker.executable { Text("glyphs-cli: \(executable)").textSelection(.enabled) }
                        Text("Installed components: \(desktop.installation.version ?? "Unknown")")
                        if !desktop.recentMessages.isEmpty {
                            Text("Recent events").font(.headline)
                            Text(desktop.recentMessages.joined(separator: "\n")).font(.caption).textSelection(.enabled)
                        }
                        HStack {
                            Button("Copy Diagnostic Report", action: desktop.copyDiagnostics)
                            Button("Open Logs") { NSWorkspace.shared.open(FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Logs/Glyphs MCP")) }
                        }
                    }.font(.callout).padding(.top, 8)
                }
            }.padding(32).frame(maxWidth: 850, alignment: .leading)
        }
        .onAppear { desktop.setVisible("overview", true) }
        .onDisappear { desktop.setVisible("overview", false) }
    }
}

struct DesktopServerButton: View {
    @EnvironmentObject private var desktop: DesktopModel
    var body: some View {
        Button(desktop.controlProgress ?? (desktop.serviceRunning == false ? "Start Server" : "Stop Server")) {
            desktop.control(desktop.serviceRunning == false ? "start" : "stop")
        }.disabled(!desktop.canChangeSettings)
        .help(desktop.status?.isBusy == true ? "Wait for the current operation to finish." : "Start or stop the MCP server.")
    }
}

struct DesktopActivityView: View {
    @EnvironmentObject private var desktop: DesktopModel
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let status = desktop.status {
                if let notice = desktop.activityNotice {
                    Label(notice, systemImage: "clock").font(.caption).foregroundStyle(.secondary)
                }
                let summary = status.summary
                if !summary.jobs.isEmpty {
                    Text(desktop.stale ? "Last observed activity" : summary.heading).font(.caption).foregroundStyle(.secondary)
                    ForEach(summary.jobs) { DesktopActivityRow(job: $0, live: !desktop.stale) }
                    if summary.additionalCount > 0 {
                        Text("\(summary.additionalCount) additional tasks").font(.caption).foregroundStyle(.secondary)
                    }
                }
                if !status.worker.available {
                    Text("Glyphs worker unavailable").font(.caption).foregroundStyle(.secondary)
                } else if status.worker.executions?.isEmpty == false && !summary.jobs.contains(where: \.isBusy) {
                    Text(status.workerTitle).font(.callout)
                }
                if !summary.history.isEmpty {
                    DisclosureGroup("Recent Tasks") {
                        ScrollView {
                            VStack(alignment: .leading, spacing: 12) {
                                ForEach(summary.history) { job in
                                    DesktopActivityRow(job: job, live: !desktop.stale)
                                    Text(job.jobId).font(.caption2).foregroundStyle(.secondary).textSelection(.enabled)
                                }
                            }.padding(.top, 8).frame(maxWidth: .infinity, alignment: .leading)
                        }.frame(maxHeight: 240)
                    }.font(.callout)
                }
            }
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct DesktopActivityRow: View {
    let job: DesktopActivity
    let live: Bool
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(job.title).fontWeight(.medium)
            Text(job.document).foregroundStyle(.secondary)
            if let progress = job.progressText { Text(progress).font(.callout).monospacedDigit() }
            if job.isBusy && live {
                Text(Date(timeIntervalSince1970: job.startedAt), style: .timer).font(.caption).monospacedDigit()
            }
            if let message = job.detailMessage { Text(message).font(.caption).foregroundStyle(.secondary) }
        }
    }
}

struct DesktopWelcomeView: View {
    let close: () -> Void
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Image(nsImage: NSApp.applicationIconImage)
                .resizable().interpolation(.high).scaledToFit()
                .frame(width: 96, height: 96)
                .frame(maxWidth: .infinity).padding(.vertical, 24)
                .accessibilityLabel("Glyphs MCP")
            VStack(alignment: .leading, spacing: 5) {
                Text("Welcome to Glyphs MCP").font(.title.bold())
                Text(DesktopIdentity.versionLabel)
                    .font(.caption).foregroundStyle(.secondary)
            }
            Text("Glyphs MCP connects Glyphs to AI assistants, helping you explore fonts, refine spacing and kerning, and automate repetitive tasks through natural language—so you can focus on designing type.").foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            Text("Thank you for supporting the project by testing, sharing feedback, and donating. Your contributions help make Glyphs MCP better for everyone.").foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            VStack(alignment: .leading, spacing: 14) {
                resourceLink("Documentation", destination: DesktopIdentity.documentation,
                    icon: Image(systemName: "book"))
                resourceLink("Report an Issue", destination: DesktopIdentity.issues,
                    icon: Image("GitHubMark").renderingMode(.template), monochrome: true)
                resourceLink("Support the project", destination: DesktopIdentity.support,
                    icon: Image(systemName: "heart.circle"))
            }
            HStack(spacing: 3) {
                Text("Made by").foregroundStyle(.secondary)
                Link("Thierry Charbonnel", destination: DesktopIdentity.linkedIn)
                    .help("Thierry Charbonnel on LinkedIn")
                    .accessibilityLabel("Thierry Charbonnel on LinkedIn")
            }.font(.caption)
            HStack { Spacer(); Button("Close", action: close).keyboardShortcut(.defaultAction) }
        }.padding(28).frame(width: 440)
    }

    private func resourceLink(_ title: String, destination: URL, icon: Image,
                              monochrome: Bool = false) -> some View {
        Link(destination: destination) {
            HStack(spacing: 10) {
                icon.resizable().scaledToFit().frame(width: 16, height: 16)
                    .foregroundStyle(monochrome ? Color.primary : Color.accentColor)
                    .accessibilityHidden(true)
                Text(title)
            }
        }.help(destination.absoluteString)
    }
}
