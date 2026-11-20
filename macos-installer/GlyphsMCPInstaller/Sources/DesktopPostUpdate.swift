import AppKit
import SwiftUI
import GlyphsMCPInstallerCore

struct PostUpdateItem: Identifiable, Sendable {
    enum Change: Sendable {
        case component(id: String, expected: String)
        case managedSkill(AgentSkillBundleInstaller.ReviewedChange, InstallerClientKind, URL)
        case cursor(expected: String)
        case catalogSkill(CatalogSkill, [SkillCopy])
    }

    let id: String
    let title: String
    let detail: String?
    let optional: Bool
    let change: Change

    var requiresClosedGlyphs: Bool {
        if case .component = change { return true }
        return false
    }
}

struct PostUpdateResult {
    var remaining: [PostUpdateItem] = []
    var errors: [String] = []
    var reopenGlyphs = false
    var serverNeedsRestore = false

    mutating func fail(_ items: [PostUpdateItem], message: String) {
        remaining.append(contentsOf: items)
        errors.append("\(items.map(\.title).formatted(.list(type: .and)))\n\(message)")
    }
}

struct DesktopPostUpdateWizard: View {
    static let size = CGSize(width: 500, height: 380)

    private enum Page { case offer, quit, quitting, additions, ready, checking, installing, result }

    @ObservedObject var installer: InstallerViewModel
    let items: [PostUpdateItem]
    let finish: (_ showSetup: Bool) -> Void

    @State private var page = Page.offer
    @State private var additions: Set<String> = []
    @State private var reviewedAdditions = false
    @State private var approved: [PostUpdateItem] = []
    @State private var installRequested = false
    @State private var quitTargets: Set<pid_t> = []
    @State private var result = PostUpdateResult()
    @State private var guidance = ""
    @State private var closedGlyphs = false
    @AccessibilityFocusState private var headingFocused: Bool

    private var updates: [PostUpdateItem] { items.filter { !$0.optional } }
    private var options: [PostUpdateItem] { items.filter(\.optional) }
    private var working: Bool { [.checking, .quitting, .installing].contains(page) }

    var body: some View {
        VStack(spacing: 20) {
            Spacer(minLength: 0)
            if page == .offer {
                Image(nsImage: NSApp.applicationIconImage)
                    .resizable().scaledToFit().frame(width: 72, height: 72)
                    .accessibilityHidden(true)
            }
            Text(title)
                .font(.system(size: 27, weight: .bold, design: .rounded))
                .multilineTextAlignment(.center)
                .accessibilityAddTraits(.isHeader)
                .accessibilityFocused($headingFocused)
            pageContent
            if !guidance.isEmpty {
                Text(verbatim: guidance)
                    .font(.callout).foregroundStyle(.secondary).multilineTextAlignment(.center)
            }
            actions
            Spacer(minLength: 0)
        }
        .padding(28)
        .frame(width: Self.size.width, height: Self.size.height)
        .background(Color(nsColor: .windowBackgroundColor))
        .onChange(of: page) { _, _ in headingFocused = true }
        .onExitCommand { if !working { finish(true) } }
    }

    private var title: LocalizedStringKey {
        switch page {
        case .offer: "Finish updating Glyphs MCP"
        case .quit: installer.running ? "Quit Glyphs to continue" : "Glyphs 4 is closed"
        case .quitting: "Waiting for Glyphs to close"
        case .additions: "New tools and skills"
        case .ready: "Ready to install"
        case .checking: "Checking Glyphs Python…"
        case .installing: "Installing updates…"
        case .result: result.errors.isEmpty ? "Update complete" : "Some changes need attention"
        }
    }

    @ViewBuilder private var pageContent: some View {
        switch page {
        case .offer:
            Text("Review updates and choose whether to install new tools and skills.")
                .foregroundStyle(.secondary).multilineTextAlignment(.center)
        case .quit:
            if installer.running {
                Text("Save your open fonts before installing.")
                    .foregroundStyle(.secondary).multilineTextAlignment(.center)
            }
        case .quitting:
            progress
            Text("If Glyphs shows a save dialog, finish it there.")
                .foregroundStyle(.secondary).multilineTextAlignment(.center)
        case .additions:
            Text("Choose what else to install.")
                .foregroundStyle(.secondary)
            scrollableRows {
                ForEach(options) { item in
                    if isInstallable(item) {
                        Toggle(isOn: Binding(get: { additions.contains(item.id) }, set: { checked in
                            if checked { additions.insert(item.id) } else { additions.remove(item.id) }
                        })) { itemLabel(item) }
                            .toggleStyle(.checkbox)
                    } else {
                        HStack {
                            itemLabel(item)
                            Spacer()
                            Button("View in Skills") { openSkills(item) }
                                .buttonStyle(.plain).foregroundStyle(Color.accentColor)
                        }
                    }
                }
            }
        case .ready:
            EmptyView()
        case .checking:
            progress
        case .installing:
            progress
            Text(verbatim: installer.message).foregroundStyle(.secondary).multilineTextAlignment(.center)
        case .result:
            if !result.errors.isEmpty {
                scrollableRows {
                    ForEach(Array(result.errors.enumerated()), id: \.offset) { _, message in
                        Text(verbatim: message).textSelection(.enabled)
                    }
                }
            }
        }
    }

    @ViewBuilder private var actions: some View {
        switch page {
        case .offer:
            VStack(spacing: 12) {
                Button("Let the wizard do everything for me", action: begin)
                    .buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
                Button("Do it manually in Setup") { finish(true) }
                    .buttonStyle(.plain).foregroundStyle(.secondary)
            }
        case .quit:
            if installer.running {
                ViewThatFits(in: .horizontal) {
                    HStack { quitButtons }.fixedSize(horizontal: true, vertical: false)
                    VStack { quitButtons }
                }
            } else {
                Button("Continue", action: finishQuit)
                    .buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
            }
        case .additions:
            Button("Continue", action: approveAdditions)
                .buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
        case .ready:
            Button("Install", action: startInstallation)
                .buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
                .disabled(installer.operationsBusy)
        case .result:
            HStack {
                if !result.errors.isEmpty { Button("Open Setup") { finish(true) } }
                if result.reopenGlyphs && !result.serverNeedsRestore {
                    Button("Reopen Glyphs") {
                        installer.openGlyphs()
                        finish(false)
                    }
                }
                if !result.remaining.isEmpty || result.serverNeedsRestore {
                    Button("Retry remaining") {
                        approved = result.remaining
                        startInstallation()
                    }.buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
                } else {
                    Button("Done") { finish(false) }
                        .buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction)
                }
            }
        case .quitting:
            Button("Continue", action: finishQuit)
                .buttonStyle(.borderedProminent).disabled(true)
        case .checking, .installing:
            Button("Install", action: startInstallation)
                .buttonStyle(.borderedProminent).disabled(true)
        }
    }

    private var progress: some View { ProgressView().accessibilityLabel(Text(title)) }

    @ViewBuilder private var quitButtons: some View {
        Button("Quit Glyphs") { quit(save: false) }
        Button("Save and quit Glyphs") { quit(save: true) }
            .buttonStyle(.borderedProminent)
            .accessibilityHint("Save and quit Glyphs saves changes in all open fonts.")
    }

    private func scrollableRows<Content: View>(@ViewBuilder _ content: () -> Content) -> some View {
        ViewThatFits(in: .vertical) {
            rows(content).fixedSize(horizontal: false, vertical: true)
            ScrollView { rows(content) }
        }
        .frame(maxWidth: 340)
    }

    private func rows<Content: View>(@ViewBuilder _ content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 12, content: content)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 4)
    }

    private func itemLabel(_ item: PostUpdateItem) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(verbatim: item.title)
            if let detail = item.detail {
                Text(verbatim: detail).font(.caption).foregroundStyle(.secondary)
            }
        }.accessibilityElement(children: .combine)
    }

    private func isInstallable(_ item: PostUpdateItem) -> Bool {
        if case .catalogSkill(_, let targets) = item.change { return !targets.isEmpty }
        return true
    }

    private func openSkills(_ item: PostUpdateItem) {
        guard case .catalogSkill(let skill, _) = item.change else { return }
        finish(false)
        Task { @MainActor in installer.postUpdateSkillToReveal = skill }
    }

    private func begin() {
        approved = updates
        reviewedAdditions = options.isEmpty
        advance()
    }

    private func approveAdditions() {
        approved = updates + options.filter { additions.contains($0.id) && isInstallable($0) }
        reviewedAdditions = true
        if approved.isEmpty { finish(false) } else { advance() }
    }

    private func advance() {
        guard !showQuitIfNeeded() else { return }
        page = reviewedAdditions ? .ready : .additions
    }

    private func showQuitIfNeeded() -> Bool {
        guard approved.contains(where: \.requiresClosedGlyphs) else { return false }
        installer.refreshRunning()
        let running = GlyphsRuntime.runningGlyphs4PIDs()
        guard !running.isEmpty else { return false }
        quitTargets = running
        page = .quit
        return true
    }

    private func startInstallation() {
        guard !installer.operationsBusy else { return }
        guidance = ""
        installRequested = true
        guard !showQuitIfNeeded() else { return }
        page = .checking
        Task {
            if approved.contains(where: \.requiresClosedGlyphs), await installer.preparePostUpdatePython() == false {
                result.errors = [AppLocalization.text("Complete the Glyphs Python check in Setup, then try the update again.")]
                result.remaining = approved
                installRequested = false
                page = .result
            } else {
                await install()
            }
        }
    }

    private func finishQuit() {
        guidance = ""
        if installRequested { startInstallation() } else { advance() }
    }

    private func quit(save: Bool) {
        guard !installer.operationsBusy else { return }
        guidance = ""
        page = .quitting
        Task {
            do {
                if try await installer.quitGlyphsForPostUpdate(confirmedPIDs: quitTargets, save: save) {
                    closedGlyphs = true
                }
                finishQuit()
            } catch {
                quitTargets = GlyphsRuntime.runningGlyphs4PIDs()
                if quitTargets.isEmpty { closedGlyphs = true }
                guidance = error.presentationDescription()
                page = .quit
            }
        }
    }

    private func install() async {
        guard !showQuitIfNeeded() else { return }
        page = .installing
        let previousReopen = result.reopenGlyphs
        result = await installer.installPostUpdate(approved, restoreServer: result.serverNeedsRestore)
        result.reopenGlyphs = previousReopen || closedGlyphs && approved.contains {
            $0.requiresClosedGlyphs && !result.remaining.map(\.id).contains($0.id)
        }
        page = .result
    }
}
