import AppKit
import SwiftUI
import GlyphsMCPInstallerCore

enum DesktopDashboardLayout {
    static let initialWidth: CGFloat = 1_180
    static let initialHeight: CGFloat = 780
    static let minimumWidth: CGFloat = 1_040
    static let minimumHeight: CGFloat = 600
    static let sidebarMinimumWidth: CGFloat = 220
    static let sidebarIdealWidth: CGFloat = 250
    static let sidebarMaximumWidth: CGFloat = 320
}

enum DesktopSetupLayout {
    static let contentMaximumWidth: CGFloat = 850
    static let contentPadding: CGFloat = 32
}

struct ContentView: View {
    @EnvironmentObject private var installer: InstallerViewModel
    @EnvironmentObject private var desktop: DesktopModel
    @StateObject private var projects = DesktopProjectsModel()
    @StateObject private var skills = DesktopSkillsModel()
    @AppStorage("projectsExpanded") private var projectsExpanded = true
    @State private var columnVisibility: NavigationSplitViewVisibility = .all

    var body: some View {
        NavigationSplitView(columnVisibility: $columnVisibility) {
            VStack(spacing: 0) {
                ScrollView {
                    VStack(alignment: .leading, spacing: 4) {
                        sidebarItem("Setup", icon: "shippingbox.and.arrow.backward", destination: .setup)
                        Button { projects.select(.tasks) } label: {
                            HStack {
                                Label("Tasks", systemImage: "list.bullet")
                                Spacer()
                                DesktopTaskBadge(count: desktop.unreadTaskCount)
                            }.padding(.horizontal, 10).padding(.vertical, 8)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .contentShape(Rectangle())
                        }.buttonStyle(.plain)
                            .foregroundStyle(projects.navigation.destination == .tasks ? Color.white : Color.primary)
                            .background(projects.navigation.destination == .tasks ? Color.accentColor : Color.clear, in: RoundedRectangle(cornerRadius: 8))
                            .accessibilityAddTraits(projects.navigation.destination == .tasks ? .isSelected : [])
                        sidebarItem("Companion Plugins", icon: "puzzlepiece.extension", destination: .companions)
                        sidebarItem("AI Agents", icon: "sparkles", destination: .agents)
                        sidebarItem("Skills", icon: "books.vertical", destination: .skills)
                        sidebarItem("Project", icon: "folder.badge.plus", destination: .templates)
                        HStack(spacing: 6) {
                            Button { projectsExpanded.toggle() } label: {
                                Image(systemName: projectsExpanded ? "chevron.down" : "chevron.right")
                                    .font(.system(size: 10, weight: .semibold)).frame(width: 14, height: 22)
                            }.buttonStyle(.plain)
                                .accessibilityLabel(LocalizedStringKey(projectsExpanded ? "Collapse My Project" : "Expand My Project"))
                            Text("My Project").fontWeight(.semibold).lineLimit(1)
                                .frame(minWidth: 0, maxWidth: .infinity, alignment: .leading)
                            DesktopProjectActions(model: projects)
                        }.font(.callout).foregroundStyle(.secondary).padding(.horizontal, 8).padding(.top, 16).padding(.bottom, 4)
                        if projectsExpanded {
                            ForEach(projects.navigation.alphabetizedProjects, id: \.self) { path in
                                projectRow(path)
                            }
                            if projects.navigation.recent.isEmpty {
                                Text("No projects yet").font(.caption).foregroundStyle(.secondary).padding(.horizontal, 12)
                            }
                        }
                    }
                    .padding(12)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .clipped()
                VStack(spacing: 4) {
                    DesktopHealthStatus().padding(.horizontal).padding(.top, 12)
                    Button { desktop.showWelcome() } label: {
                        Label("Welcome & Support", systemImage: "heart.circle").lineLimit(1)
                            .frame(minWidth: 0, maxWidth: .infinity, alignment: .leading)
                    }.buttonStyle(.plain).padding()
                }
            }
            .modifier(DesktopSidebarToolbarDefaults())
            .frame(minWidth: DesktopDashboardLayout.sidebarMinimumWidth)
            .navigationSplitViewColumnWidth(
                min: DesktopDashboardLayout.sidebarMinimumWidth,
                ideal: DesktopDashboardLayout.sidebarIdealWidth,
                max: DesktopDashboardLayout.sidebarMaximumWidth
            )
        } detail: {
            switch projects.navigation.destination {
            case .setup: DesktopSetup { projects.select($0) }
            case .tasks: DesktopTasksView()
            case .companions: DesktopFocusedSetup(section: .companions) { projects.select(.setup) }
            case .agents: DesktopFocusedSetup(section: .agents) { projects.select(.setup) }
            case .skills: DesktopSkillsView(model: skills, installer: installer, project: projects.navigation.lastProject) { projects.select(.agents) }
            case .templates: DesktopProjectCatalog(model: projects)
            case .project(let path): DesktopProjectWorkspace(model: projects, path: path)
            }
        }
        .onAppear { handleSetupRequest(); handleTasksRequest() }
        .onChange(of: desktop.tasksRequested) { _, _ in handleTasksRequest() }
        .onChange(of: desktop.setupRequested) { _, _ in handleSetupRequest() }
        .navigationTitle(DesktopIdentity.applicationTitle)
        .modifier(DesktopSidebarToggle(columnVisibility: $columnVisibility))
        .toolbar {
            if #available(macOS 26.0, *) {
                ToolbarItem(placement: .primaryAction) {
                    DesktopServerStatusIndicator()
                }
                // The status pill supplies its own background. A plain button
                // style alone does not remove the toolbar's shared background.
                .sharedBackgroundVisibility(.hidden)
            } else {
                ToolbarItem(placement: .primaryAction) {
                    DesktopServerStatusIndicator()
                }
            }
        }
        .frame(minWidth: DesktopDashboardLayout.minimumWidth,
               minHeight: DesktopDashboardLayout.minimumHeight)
        .task { projects.inspect(); await projects.loadTemplates() }
        .sheet(item: $projects.creation) { creation in
            DesktopProjectWizard(model: projects, template: creation.template, previewFirst: creation.previewFirst)
        }
        .sheet(item: $projects.editing) { editing in
            DesktopProjectSettings(model: projects, path: editing.id)
        }
    }

    private func handleTasksRequest() {
        guard desktop.tasksRequested else { return }
        projects.select(.tasks)
        desktop.consumeTasksRequest()
    }

    private func handleSetupRequest() {
        guard desktop.setupRequested else { return }
        projects.select(.setup)
        desktop.consumeSetupRequest()
    }

    private func projectRow(_ path: String) -> some View {
        let selected = projects.selectedProject == path
        let name = projects.navigation.name(for: path)
        return HStack(spacing: 4) {
            Button { projects.select(.project(path)) } label: {
                Label(name, systemImage: "folder").lineLimit(1).truncationMode(.middle)
                    .frame(minWidth: 0, maxWidth: .infinity, alignment: .leading).padding(.vertical, 8)
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
            Label(LocalizedStringKey(title), systemImage: icon).lineLimit(1).truncationMode(.middle)
                .frame(minWidth: 0, maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 10).padding(.vertical, 8)
                .contentShape(Rectangle())
        }.buttonStyle(.plain)
            .foregroundStyle(selected ? Color.white : Color.primary)
            .background(selected ? Color.accentColor : Color.clear, in: RoundedRectangle(cornerRadius: 8))
            .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

private struct DesktopServerStatusIndicator: View {
    @EnvironmentObject private var desktop: DesktopModel

    private var title: String { desktop.controlProgress ?? desktop.title }
    private var color: Color {
        guard desktop.serviceRunning == true, !desktop.stale else { return .secondary }
        return desktop.status?.bridge.reachable == true && !desktop.showsActivityDot ? .green : .accentColor
    }

    var body: some View {
        Button { desktop.requestSetup() } label: {
            HStack(spacing: 6) {
                if desktop.controlling {
                    ProgressView().controlSize(.small)
                } else {
                    Image(systemName: desktop.statusSymbol)
                        .foregroundStyle(color)
                        .accessibilityHidden(true)
                }
                Text("MCP").fontWeight(.medium)
                Text(LocalizedStringKey(title)).foregroundStyle(.secondary)
            }
            .font(.callout)
            .lineLimit(1)
            .fixedSize()
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(.quaternary, in: Capsule())
        }
        .buttonStyle(.plain)
        .help("Open Setup")
        .accessibilityLabel(Text("Glyphs MCP") + Text(": ") + Text(LocalizedStringKey(title)))
        .accessibilityIdentifier("desktop.serverStatus")
    }
}

private struct DesktopSidebarToggle: ViewModifier {
    @Binding var columnVisibility: NavigationSplitViewVisibility

    @ViewBuilder func body(content: Content) -> some View {
        content.toolbar {
            ToolbarItem(placement: .navigation) {
                Button {
                    columnVisibility = columnVisibility == .detailOnly ? .all : .detailOnly
                } label: {
                    Label(LocalizedStringKey(columnVisibility == .detailOnly ? "Show Sidebar" : "Hide Sidebar"), systemImage: "sidebar.left")
                }
                .help(LocalizedStringKey(columnVisibility == .detailOnly ? "Show Sidebar" : "Hide Sidebar"))
            }
        }
    }
}

private struct DesktopSidebarToolbarDefaults: ViewModifier {
    @ViewBuilder func body(content: Content) -> some View {
        content.toolbar(removing: .sidebarToggle)
    }
}

struct DesktopSetup: View {
    let navigate: (DesktopDestination) -> Void
    @EnvironmentObject private var installer: InstallerViewModel
    @EnvironmentObject private var desktop: DesktopModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 26) {
                HStack(alignment: .firstTextBaseline) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Setup").font(.largeTitle.bold())
                        Text("Install and manage Glyphs MCP from one place.").foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button { installer.showTroubleshootingLogs?() } label: {
                        Image(systemName: "doc.text.magnifyingglass")
                    }
                    .buttonStyle(.borderless)
                    .accessibilityLabel("Open Troubleshooting Logs")
                    .help("Open Troubleshooting Logs")
                }
                DesktopInitializationStatus()
                GroupBox {
                    VStack(alignment: .leading, spacing: 16) {
                        HStack {
                            Image(systemName: desktop.statusSymbol)
                                .foregroundStyle(desktop.stale ? Color.secondary : Color.accentColor).font(.title2)
                            VStack(alignment: .leading, spacing: 4) {
                                Text(LocalizedStringKey(desktop.title)).font(.title2.weight(.semibold))
                                Text("MCP port \(String(desktop.installation.port))").foregroundStyle(.secondary)
                            }
                            Spacer()
                            DesktopServerButton()
                        }
                        if !desktop.notice.isEmpty { Text(desktop.notice).font(.callout).foregroundStyle(.secondary) }
                        if desktop.needsGlyphsRecovery {
                            Text("Bring Glyphs to the front and finish any startup, trial or plug-in dialogs. Then return here and choose Refresh. If there is no pending dialog, open Troubleshooting Logs.")
                                .font(.callout)
                            HStack {
                                Button("Open Glyphs", action: installer.openGlyphs)
                                    .disabled(installer.application == nil)
                                Button("Open Troubleshooting Logs") { installer.showTroubleshootingLogs?() }
                            }
                        }
                        if desktop.status?.worker.available == false {
                            Text("Glyphs worker unavailable").font(.caption).foregroundStyle(.secondary)
                        }
                    }.padding(12).frame(maxWidth: .infinity, alignment: .leading)
                }
                if installer.application != nil {
                    DesktopPythonSetup()
                }
                if installer.running {
                    DesktopComponentPreparation()
                }
                HStack(spacing: 12) {
                    Button("Open Glyphs", action: installer.openGlyphs).disabled(installer.application == nil)
                    Button("Refresh") {
                        installer.refresh(resetFailures: true)
                        Task { await desktop.refresh() }
                    }.disabled(installer.operationsBusy)
                    Spacer()
                    Text(installer.versionLabel).font(.caption).foregroundStyle(.secondary)
                }
                HStack {
                    Button("Companion Plugins") { navigate(.companions) }
                    Button("AI Agents") { navigate(.agents) }
                    Button("Skills") { navigate(.skills) }
                }
                Text("Eleven included skills are managed with your agent connections. Browse Skills for their status and additional workflows.")
                    .font(.callout).foregroundStyle(.secondary)
                InstallationView()
            }
            .padding(DesktopSetupLayout.contentPadding)
            .frame(maxWidth: DesktopSetupLayout.contentMaximumWidth, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .onAppear { desktop.setVisible("setup", true); installer.setSetupVisible(true) }
        .onDisappear { desktop.setVisible("setup", false); installer.setSetupVisible(false) }
    }
}

/// Both installation views keep the preparation action in the same trailing position.
struct DesktopComponentPreparation: View {
    @EnvironmentObject private var installer: InstallerViewModel

    var body: some View {
        HStack(alignment: .center, spacing: 24) {
            VStack(alignment: .leading, spacing: 8) {
                Text("Close Glyphs to install or update components.")
                    .font(.title3.bold())
                Text("You can save your fonts when prompted.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)

            DesktopActionButton(title: "Quit Glyphs to Install or Update", emphasis: .primary,
                                action: installer.quitGlyphs)
                .disabled(installer.operationsBusy)
        }
        .padding(.vertical, 16)
    }
}

struct DesktopServerButton: View {
    @EnvironmentObject private var desktop: DesktopModel
    var body: some View {
        Button(LocalizedStringKey(desktop.controlProgress ?? (desktop.serviceRunning == false ? "Start Server" : "Stop Server"))) {
            desktop.control(desktop.serviceRunning == false ? "start" : "stop")
        }.disabled(!desktop.canChangeSettings)
        .help(LocalizedStringKey(desktop.status?.isBusy == true ? "Wait for the current operation to finish." : "Start or stop the MCP server."))
    }
}

private struct WelcomeSlide {
    let title: String
    let body: String
    let symbol: String
    static let all = [
        WelcomeSlide(title: "Welcome to Glyphs MCP",
            body: "Bring an AI companion into your font-making workflow. Explore ideas, get help with repetitive tasks, and spend more time designing type.", symbol: "sparkles"),
        WelcomeSlide(title: "Your font. Your decisions.",
            body: "Tell your assistant what you want to achieve. Review its proposed changes, guide the next step, and decide what to keep.", symbol: "slider.horizontal.3"),
        WelcomeSlide(title: "How it connects",
            body: "Your AI assistant connects through Glyphs MCP to work with Glyphs. MCP is the connection that lets the assistant use tools inside your font workflow. The companion app helps you set up and check that connection.", symbol: "arrow.left.arrow.right"),
        WelcomeSlide(title: "Get ready to connect",
            body: "You'll need Glyphs 4 and a supported AI client, such as Codex or Claude Code. Install the official Python module through Glyphs’ Plugin Manager, then use this companion app to install the Glyphs MCP bridge and connect your client.", symbol: "shippingbox"),
        WelcomeSlide(title: "What’s new in v2.0.0",
            body: "A companion app for setup and AI connections.\n\nGuided font edits with previews and separate Keep and Save actions.\n\nFont projects, templates and optional local Git checkpoints.\n\nCurve Inspector and Changes Against Reference inside Glyphs.", symbol: "star.circle"),
        WelcomeSlide(title: "Made together",
            body: "Glyphs MCP is an open-source community project by Thierry Charbonnel. Share an idea, report an issue, or contribute on GitHub. Thank you for testing, participating, and supporting the project.", symbol: "heart")
    ]
}

struct DesktopWelcomeView: View {
    let startSetup: () -> Void
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var page = 0
    private var slide: WelcomeSlide { WelcomeSlide.all[page] }
    private var isLast: Bool { page == WelcomeSlide.all.count - 1 }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Glyphs MCP").font(.headline)
                Spacer()
                Text(DesktopIdentity.versionLabel).font(.caption).foregroundStyle(.secondary)
            }.padding(.bottom, 20)
            ScrollView {
                VStack(spacing: 22) {
                    illustration.frame(height: 150).accessibilityHidden(true)
                    Text(LocalizedStringKey(slide.title))
                        .font(.system(size: 30, weight: .bold, design: .rounded))
                        .multilineTextAlignment(.center).accessibilityAddTraits(.isHeader)
                    Text(LocalizedStringKey(slide.body))
                        .font(.body).foregroundStyle(.secondary)
                        .multilineTextAlignment(.center).lineSpacing(5)
                        .fixedSize(horizontal: false, vertical: true)
                    if isLast { communityLinks }
                }
                .frame(maxWidth: .infinity).padding(.horizontal, 12).padding(.vertical, 12)
                .id(page)
                .transition(reduceMotion ? .identity : .opacity)
            }
            Spacer(minLength: 16)
            HStack(spacing: 8) {
                ForEach(WelcomeSlide.all.indices, id: \.self) { index in
                    Circle().fill(index == page ? Color.accentColor : Color.secondary.opacity(0.25))
                        .frame(width: 7, height: 7)
                }
            }.accessibilityElement(children: .ignore)
                .accessibilityLabel(Text("Slide \(page + 1) of \(WelcomeSlide.all.count)"))
                .padding(.bottom, 22)
            HStack {
                Button("Skip to setup", action: startSetup).buttonStyle(.plain).foregroundStyle(.secondary)
                Spacer()
                Button("Back") { navigate(-1) }.disabled(page == 0)
                Button {
                    if isLast { startSetup() } else { navigate(1) }
                } label: {
                    Text(isLast ? LocalizedStringKey("Start setup") : LocalizedStringKey("Next"))
                }.buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
            }
        }
        .padding(32).frame(width: 600, height: 640)
        .background(Color(nsColor: .windowBackgroundColor))
    }

    private func navigate(_ offset: Int) {
        withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.25)) {
            page = min(max(page + offset, 0), WelcomeSlide.all.count - 1)
        }
    }

    @ViewBuilder private var illustration: some View {
        if page == 2 {
            HStack(spacing: 18) {
                diagramItem("AI assistant", symbol: "sparkles")
                Image(systemName: "arrow.left.arrow.right").foregroundStyle(.secondary)
                diagramItem("Glyphs MCP", symbol: "network")
                Image(systemName: "arrow.left.arrow.right").foregroundStyle(.secondary)
                diagramItem("Glyphs", symbol: "textformat")
            }
        } else if page == 3 {
            HStack(spacing: 40) {
                clientMark("CodexLogo", title: "Codex")
                clientMark("ClaudeCodeLogo", title: "Claude Code")
            }
        } else if page == 0 {
            Image(nsImage: NSApp.applicationIconImage)
                .resizable().scaledToFit().frame(width: 120, height: 120)
        } else {
            Image(systemName: slide.symbol).font(.system(size: 64, weight: .light))
                .foregroundStyle(Color.accentColor)
                .frame(width: 140, height: 140)
                .background(Color.accentColor.opacity(0.08), in: RoundedRectangle(cornerRadius: 32))
        }
    }

    private func diagramItem(_ title: String, symbol: String) -> some View {
        VStack(spacing: 14) {
            Image(systemName: symbol).font(.system(size: 32))
                .foregroundStyle(Color.accentColor)
                .frame(width: 72, height: 72)
                .background(Color.accentColor.opacity(0.08), in: RoundedRectangle(cornerRadius: 20))
            Text(LocalizedStringKey(title)).font(.caption.weight(.medium))
        }
    }

    private func clientMark(_ asset: String, title: String) -> some View {
        VStack(spacing: 14) {
            Image(asset).resizable().scaledToFit().frame(width: 64, height: 64)
            Text(title).font(.callout.weight(.medium))
        }
    }

    private var communityLinks: some View {
        VStack(spacing: 14) {
            HStack(spacing: 22) {
                DesktopTextLink("Documentation", destination: DesktopIdentity.documentation)
                DesktopTextLink("Contribute on GitHub", destination: DesktopIdentity.issues.deletingLastPathComponent())
                DesktopTextLink("Support the project", destination: DesktopIdentity.support)
            }.font(.caption)
            DesktopTextLink("Contact Thierry Charbonnel", destination: DesktopIdentity.linkedIn).font(.caption)
        }.padding(.top, 4)
    }
}
