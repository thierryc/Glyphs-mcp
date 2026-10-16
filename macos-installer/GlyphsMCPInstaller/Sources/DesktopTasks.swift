import AppKit
import SwiftUI
import GlyphsMCPInstallerCore

struct DesktopTaskBadge: View {
    let count: Int
    var body: some View {
        if count > 0 {
            Text(count > 99 ? "99+" : String(count))
                .font(.caption.monospacedDigit()).padding(.horizontal, 7).padding(.vertical, 2)
                .background(.quaternary, in: Capsule())
                .accessibilityLabel(Text("\(count) unread tasks"))
        }
    }
}

struct DesktopHealthStatus: View {
    @EnvironmentObject private var desktop: DesktopModel
    var body: some View {
        VStack(spacing: 8) {
            row("MCP", value: desktop.serviceRunning == true && !desktop.stale ? "Connected" : desktop.serviceRunning == false ? "Stopped" : "Unavailable",
                available: desktop.serviceRunning == true && !desktop.stale)
            row("Glyphs 4", value: desktop.glyphsRunning ? "Running" : "Not running", available: desktop.glyphsRunning)
        }.font(.caption).accessibilityElement(children: .contain)
    }
    private func row(_ name: String, value: String, available: Bool) -> some View {
        HStack(spacing: 7) {
            Image(systemName: "circle.fill").font(.system(size: 7))
                .foregroundStyle(available ? Color.green : Color.secondary).accessibilityHidden(true)
            Text(LocalizedStringKey(name))
            Spacer()
            Text(LocalizedStringKey(value)).foregroundStyle(.secondary)
        }.accessibilityElement(children: .combine)
    }
}

struct DesktopTasksView: View {
    @EnvironmentObject private var desktop: DesktopModel
    @Environment(\.controlActiveState) private var controlActiveState
    @Environment(\.colorSchemeContrast) private var contrast
    @FocusState private var taskListFocused: Bool
    @State private var selected: String?
    @State private var historyExpanded = false
    @State private var copied = false
    @State private var promptIntent: DesktopTaskPromptIntent = .review
    @State private var linkFailed = false
    @State private var confirmingClearHistory = false
    @State private var recoveryTask: DesktopTask?
    private let copyPrompt: (String) -> Bool
    init(selection: String? = nil, promptIntent: DesktopTaskPromptIntent = .review,
         copyPrompt: @escaping (String) -> Bool = { request in
             NSPasteboard.general.clearContents()
             return NSPasteboard.general.setString(request, forType: .string)
         }) {
        _selected = State(initialValue: selection)
        _promptIntent = State(initialValue: promptIntent)
        self.copyPrompt = copyPrompt
    }
    private var task: DesktopTask? { desktop.visibleTasks.first { $0.id == selected } }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let notice = desktop.tasksNotice {
                Text(notice).font(.callout).foregroundStyle(.secondary)
            }
            if desktop.tasksStale, desktop.tasksObservedAt != nil {
                Text("Showing the last observation.").font(.caption).foregroundStyle(.secondary)
            }
            if desktop.tasks.isEmpty && !desktop.hasClearedTaskHistory {
                if desktop.tasksNotice != nil {
                    ContentUnavailableView("Tasks Unavailable", systemImage: "exclamationmark.triangle")
                } else if desktop.tasksObservedAt == nil {
                    ProgressView("Loading Tasks…").frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    ContentUnavailableView("No Tasks", systemImage: "list.bullet", description: Text("Tasks appear here when an agent works with Glyphs MCP."))
                }
            } else {
                HSplitView {
                    VStack(spacing: 0) {
                        List(selection: $selected) {
                            let running = desktop.visibleTasks.filter { !$0.closed && $0.state == "running" }
                            if !running.isEmpty {
                                taskGroup("In progress", tasks: running)
                            }
                            let open = desktop.visibleTasks.filter { !$0.closed && $0.state != "running" }
                            if !open.isEmpty {
                                taskGroup("Tasks needing attention", tasks: open)
                            }
                            let closed = desktop.visibleTasks.filter(\.closed)
                            if !closed.isEmpty {
                                taskGroup("Recently closed tasks", tasks: closed)
                            }
                            if desktop.tasksNextCursor != nil {
                                Button("Load Earlier Tasks") { Task { await desktop.refreshTasks(loadMore: true) } }
                                    .disabled(desktop.tasksLoading)
                            }
                            if desktop.visibleTasks.isEmpty {
                                Text("Closed history cleared.").font(.callout).foregroundStyle(.secondary)
                                    .selectionDisabled().listRowSeparator(.hidden)
                            }
                        }
                        .listStyle(.inset)
                        .focused($taskListFocused)
                        .scrollContentBackground(.hidden)
                        .background(Color(nsColor: .controlBackgroundColor))
                        .frame(maxHeight: .infinity)
                        historyControls
                    }
                    .frame(minWidth: 220, idealWidth: 270, maxWidth: 320, maxHeight: .infinity)
                    ScrollView {
                        if let task {
                            details(task)
                                .frame(maxWidth: 720, alignment: .leading)
                                .padding(.horizontal, 28).padding(.vertical, 20)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        } else {
                            ContentUnavailableView("Select a Task", systemImage: "list.bullet")
                                .frame(maxWidth: .infinity, minHeight: 240)
                        }
                    }
                    .background(Color(nsColor: .controlBackgroundColor))
                    .frame(minWidth: 300, maxHeight: .infinity)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .padding(.horizontal, DesktopSetupLayout.contentPadding)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .onAppear { desktop.setVisible("tasks", true) }
        .onDisappear { desktop.setVisible("tasks", false) }
        .onChange(of: selected) { _, _ in
            copied = false; linkFailed = false; historyExpanded = false; promptIntent = .review
            if let task { desktop.readTask(task) }
        }
        .onChange(of: desktop.visibleTasks) { _, _ in
            if let selected, !desktop.visibleTasks.contains(where: { $0.id == selected }) { self.selected = nil }
            if let task { desktop.readTask(task) }
        }
        .confirmationDialog("Clear closed task history?", isPresented: $confirmingClearHistory, titleVisibility: .visible) {
            Button("Clear Closed History") { desktop.clearClosedTaskHistory() }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Hide all currently closed tasks, including earlier pages. Cleared history is removed after 30 days. You can show it again before cleanup from History Options. Open tasks, recovery data, diagnostics, and Unverified outcomes are kept.")
        }
        .sheet(item: $recoveryTask) { task in
            DesktopTaskRecoveryView(task: task).environmentObject(desktop).desktopDesign()
        }
    }

    private var historyControls: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Button("Clear Closed History…") { confirmingClearHistory = true }
                    .buttonStyle(DesktopSecondaryButtonStyle()).controlSize(.small)
                    .disabled(!desktop.canClearTaskHistory)
                Spacer(minLength: 0)
                Menu {
                    Button("Show Cleared History") { desktop.restoreTaskHistory() }
                        .disabled(!desktop.hasClearedTaskHistory)
                } label: {
                    Label("History Options", systemImage: "ellipsis").labelStyle(.iconOnly)
                }
                .menuStyle(.borderlessButton).fixedSize()
                .help("History Options")
            }
            if let notice = desktop.taskHistoryNotice {
                Text(notice).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 10)
        .background(Color(nsColor: .controlBackgroundColor))
    }

    private func taskGroup(_ title: LocalizedStringKey, tasks: [DesktopTask]) -> some View {
        Group {
            // Heading rows scroll with their group, so the first heading has
            // the same appearance as every other heading (no floating shadow).
            Text(title).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                .padding(.top, 10).padding(.bottom, 4)
                .frame(maxWidth: .infinity, alignment: .leading)
                .listRowInsets(EdgeInsets(top: 0, leading: 12, bottom: 0, trailing: 12))
                .listRowSeparator(.hidden)
                .selectionDisabled()
                .accessibilityAddTraits(.isHeader)
            ForEach(tasks) { row($0).tag($0.id) }
        }
    }

    private func row(_ task: DesktopTask) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(task.documentName).fontWeight(desktop.isUnread(task) ? .semibold : .medium)
                .lineLimit(1).truncationMode(.middle)
            Text(LocalizedStringKey(task.title)).font(.callout)
                .foregroundStyle(selected == task.id ? .primary : .secondary).lineLimit(2)
            if let status = task.statusLabel {
                if selected == task.id {
                    Text(LocalizedStringKey(status)).font(.caption)
                } else {
                    Text(LocalizedStringKey(status)).font(.caption)
                        .foregroundStyle(task.state == "running" ? Color.secondary : Color.orange)
                }
            }
            if let agent = task.agentName {
                Text(agent).font(.caption).foregroundStyle(selected == task.id ? .primary : .secondary)
            }
        }
            .padding(.vertical, 6)
            .listRowBackground(selected == task.id && usesSoftInactiveSelection ? DesktopInactiveTaskSelection() : nil)
            .listRowSeparator(.hidden)
            .listRowInsets(EdgeInsets(top: 4, leading: 12, bottom: 4, trailing: 12))
            .contextMenu {
                Button("Copy Request") {
                    let request = selected == task.id ? task.prompt(for: promptIntent) : task.copyRequest
                    let success = copyPrompt(request)
                    if selected == task.id { copied = success }
                }
            }
            .accessibilityElement(children: .combine)
            .accessibilityValue(Text(desktop.isUnread(task) ? "Unread" : "Read"))
    }

    private var usesSoftInactiveSelection: Bool {
        // A nil row background leaves AppKit's accent selection and stronger
        // accessibility appearance intact. Selection itself stays with List.
        contrast != .increased && (controlActiveState != .key || !taskListFocused)
    }

    private func details(_ task: DesktopTask) -> some View {
        VStack(alignment: .leading, spacing: 20) {
            VStack(alignment: .leading, spacing: 6) {
                Text(LocalizedStringKey(task.title)).font(.title2.weight(.semibold)).textSelection(.enabled)
                Text([task.path.map { URL(fileURLWithPath: $0).lastPathComponent } ?? task.documentName, task.agentName].compactMap { $0 }.joined(separator: " · "))
                    .font(.callout).foregroundStyle(.secondary).textSelection(.enabled)
            }
            if task.closed, let support = task.supportText { Text(support).textSelection(.enabled) }
            if let message = task.message {
                Text(message).foregroundStyle(.secondary).lineSpacing(3).textSelection(.enabled)
            }
            if let warning = task.checkpointWarning { Label(warning, systemImage: "exclamationmark.triangle").foregroundStyle(.orange) }
            if let progress = task.progress, let total = task.total, total > 0, task.state == "running" {
                ProgressView(value: Double(progress), total: Double(total))
                Text("\(progress) of \(total) changes").font(.caption).foregroundStyle(.secondary)
            }
            if !task.blockedBy.isEmpty {
                Text("Waiting for: \(names(task.blockedBy))").foregroundStyle(.orange)
            }
            if !task.blocking.isEmpty {
                Text("Blocking: \(names(task.blocking))").foregroundStyle(.orange)
            }
            if !task.closed {
                if task.state == "running" {
                    Text("Work is in progress in Glyphs.").font(.callout).foregroundStyle(.secondary)
                }
                if let url = task.conversationURL {
                    DesktopActionButton(title: "Open Conversation…", symbol: "arrow.up.right") {
                        NSWorkspace.shared.open(url, configuration: .init()) { _, error in
                            Task { @MainActor in
                                if selected == task.id { linkFailed = error != nil }
                            }
                        }
                    }
                }
                if linkFailed {
                    Text("The conversation could not be opened. Copy the prompt to continue in your agent.")
                        .font(.caption).foregroundStyle(.secondary)
                } else if let explanation = task.conversationUnavailableMessage {
                    Text(LocalizedStringKey(explanation)).font(.caption).foregroundStyle(.secondary)
                }
                DesktopTaskPrompt(request: task.prompt(for: promptIntent), intent: $promptIntent, copied: $copied, copyPrompt: copyPrompt)
                Button("Recovery Options…") { recoveryTask = task }
                    .buttonStyle(DesktopSecondaryButtonStyle()).controlSize(.small)
            }
            Divider()
            DisclosureGroup("History", isExpanded: $historyExpanded) {
                VStack(alignment: .leading, spacing: 8) {
                    LabeledContent("Created") { Text(Date(timeIntervalSince1970: task.createdAt).formatted()) }
                    LabeledContent("Last updated") { Text(Date(timeIntervalSince1970: task.updatedAt).formatted()) }
                    LabeledContent("Font at last check") {
                        Text(LocalizedStringKey(task.saveStatus == "unsaved" ? "Unsaved changes" : task.saveStatus == "saved" ? "Saved" : "Unknown"))
                    }
                    if let outcome = task.outcome { Text(outcome.replacingOccurrences(of: "_", with: " ").capitalized) }
                    Text(task.workflowId ?? task.jobId ?? task.id).textSelection(.enabled)
                }.font(.caption).foregroundStyle(.secondary).padding(.top, 8)
            }
        }
    }
    private func names(_ identities: [String]) -> String {
        identities.map { id in desktop.tasks.first { $0.id == id }?.documentName ?? id }.joined(separator: ", ")
    }
}

/// Exceptional recovery, using only fresh server-issued closing choices.
private struct DesktopTaskRecoveryView: View {
    let task: DesktopTask
    @EnvironmentObject private var desktop: DesktopModel
    @Environment(\.dismiss) private var dismiss
    @State private var recovery: DesktopTaskRecovery?
    @State private var busy = false
    @State private var failure: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            HStack(spacing: 12) {
                Button { dismiss() } label: {
                    Label("Close Recovery Options", systemImage: "xmark")
                        .labelStyle(.iconOnly).font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(.secondary).frame(width: 24, height: 24)
                        .background(.quaternary, in: Circle())
                }
                .buttonStyle(.plain).keyboardShortcut(.cancelAction).disabled(busy)
                .help("Close without changing this task")
                Text("Recovery Options").font(.title2.weight(.semibold))
                Spacer(minLength: 0)
            }
            VStack(alignment: .leading, spacing: 4) {
                Text(recovery?.documentName ?? task.documentName).font(.headline)
                Text(LocalizedStringKey(task.title)).foregroundStyle(.secondary)
                if let path = recovery?.path ?? task.path {
                    Text(URL(fileURLWithPath: path).lastPathComponent)
                        .font(.caption).foregroundStyle(.secondary).lineLimit(1).truncationMode(.middle)
                        .help(path).textSelection(.enabled)
                }
                if let recovery {
                    Text(LocalizedStringKey(recovery.statusLabel)).font(.caption.weight(.medium)).foregroundStyle(.secondary)
                }
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    if let recovery {
                        if let receipt = recovery.receipt {
                            Text(LocalizedStringKey(receipt)).textSelection(.enabled)
                        } else if recovery.message != "Review the consequences before resolving this abandoned task." {
                            Text(LocalizedStringKey(recovery.message)).textSelection(.enabled)
                        }
                        if let warning = recovery.warning {
                            Label(warning, systemImage: "exclamationmark.triangle")
                                .font(.callout).foregroundStyle(.orange).textSelection(.enabled)
                        }
                        ForEach(recovery.closingActions) { choice in
                            Text(LocalizedStringKey(choice.consequence)).font(.callout).foregroundStyle(.secondary)
                                .textSelection(.enabled).padding(.top, 8)
                        }
                    }
                    if let failure { Text(LocalizedStringKey(failure)).foregroundStyle(.orange).textSelection(.enabled) }
                    if busy { ProgressView("Checking task…").controlSize(.small) }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }.frame(maxHeight: 360)
            HStack(spacing: 12) {
                if recovery?.closed != true {
                    Button("Check Again") { Task { await load() } }
                        .buttonStyle(DesktopSecondaryButtonStyle()).disabled(busy)
                }
                Spacer()
                if let recovery {
                    ForEach(recovery.closingActions) { choice in
                        if choice.isCancellation {
                            Button(LocalizedStringKey(choice.label), role: .destructive) { Task { await load(choice: choice) } }
                                .buttonStyle(.borderedProminent).buttonBorderShape(.capsule).tint(.red).disabled(busy)
                        } else {
                            Button(LocalizedStringKey(choice.label)) { Task { await load(choice: choice) } }
                                .buttonStyle(DesktopSecondaryButtonStyle()).disabled(busy)
                        }
                    }
                }
            }
        }
        .padding(24).frame(width: 500)
        .interactiveDismissDisabled(busy)
        .task { await load() }
    }

    @MainActor private func load(choice: DesktopTaskRecovery.Action? = nil) async {
        guard !busy else { return }
        busy = true; failure = nil
        let revision = recovery?.revision
        // A failed or lost response leaves no actionable stale buttons or receipt.
        recovery = nil
        defer { busy = false }
        do { recovery = try await desktop.taskRecovery(task, choice: choice, revision: revision) }
        catch { failure = error.localizedDescription }
    }
}

/// An opaque system surface with a faint blend of the inactive-selection color.
/// Semantic colors continue to adapt to the current light/dark appearance.
private struct DesktopInactiveTaskSelection: View {
    var body: some View {
        RoundedRectangle(cornerRadius: 8, style: .continuous)
            .fill(Color(nsColor: .controlBackgroundColor))
            .overlay {
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(Color(nsColor: .unemphasizedSelectedContentBackgroundColor).opacity(0.22))
            }
            .overlay {
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .strokeBorder(Color(nsColor: .separatorColor).opacity(0.5))
            }
            .padding(.horizontal, 10)
            .allowsHitTesting(false).accessibilityHidden(true)
    }
}

/// The exact handoff text is visible before copying and remains selectable.
private struct DesktopTaskPrompt: View {
    let request: String
    @Binding var intent: DesktopTaskPromptIntent
    @Binding var copied: Bool
    let copyPrompt: (String) -> Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 12) {
                Text("Prompt for the Agent").font(.callout.weight(.medium))
                Spacer(minLength: 8)
                Button {
                    copied = copyPrompt(request)
                } label: {
                    Label(LocalizedStringKey(copied ? "Copied" : "Copy"), systemImage: copied ? "checkmark" : "doc.on.doc")
                        .labelStyle(.iconOnly).frame(width: 16, height: 16)
                }
                .buttonStyle(DesktopSecondaryButtonStyle()).controlSize(.small)
                .help(LocalizedStringKey(copied ? "Prompt copied" : "Copy prompt"))
                .accessibilityLabel(Text(LocalizedStringKey(copied ? "Prompt copied" : "Copy prompt")))
            }
            Picker("Prompt purpose", selection: $intent) {
                ForEach(DesktopTaskPromptIntent.allCases) { intent in
                    Text(LocalizedStringKey(intent.label)).tag(intent)
                }
            }
            .pickerStyle(.segmented).labelsHidden().controlSize(.small)
            .fixedSize(horizontal: true, vertical: false)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityLabel(Text("Prompt purpose"))
            Text(request)
                .font(.system(.callout, design: .monospaced))
                .lineSpacing(3).textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(16)
        .background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 10, style: .continuous).strokeBorder(Color.primary.opacity(0.07))
        }
        .accessibilityElement(children: .contain)
        .onChange(of: request) { _, _ in copied = false }
    }
}
