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

struct DesktopConnectionStatus: View {
    @EnvironmentObject private var desktop: DesktopModel
    var body: some View {
        HStack(spacing: 16) {
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
            Text(LocalizedStringKey(value)).foregroundStyle(.secondary)
        }.accessibilityElement(children: .combine)
    }
}

struct DesktopGlyphsHealthView: View {
    let report: DesktopGlyphsHealthReport
    @State private var expanded = false
    @State private var copiedAt: Date?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Glyphs Health").font(.headline)
                    .accessibilityAddTraits(.isHeader)
                Spacer()
                Button {
                    var transaction = Transaction(animation: nil)
                    transaction.disablesAnimations = true
                    withTransaction(transaction) { expanded.toggle() }
                } label: {
                    Label(LocalizedStringKey(expanded ? "Hide details" : "Show details"),
                          systemImage: expanded ? "chevron.up" : "chevron.down")
                }
                .controlSize(.small)
                .accessibilityIdentifier("desktop.glyphsHealth.details")
                Button {
                    copiedAt = report.copyToPasteboard() ? .now : nil
                } label: {
                    Label("Copy report as Markdown", systemImage: copiedAt == nil ? "doc.on.doc" : "checkmark")
                        .labelStyle(.iconOnly).frame(width: 16, height: 16)
                }
                .buttonStyle(DesktopSecondaryButtonStyle()).controlSize(.small)
                .help(LocalizedStringKey(copiedAt == nil ? "Copy report as Markdown" : "Copied"))
                .accessibilityValue(Text(LocalizedStringKey(copiedAt == nil ? "" : "Copied")))
                .accessibilityIdentifier("desktop.glyphsHealth.copyReport")
                .task(id: copiedAt) {
                    guard copiedAt != nil else { return }
                    try? await Task.sleep(for: .seconds(2))
                    guard !Task.isCancelled else { return }
                    copiedAt = nil
                }
            }

            if let health = report.availableHealth {
                Text(LocalizedStringKey(report.stale ? "Showing the last observation." : health.readinessTitle))
                    .font(.callout.weight(.semibold))
                if let footprint = report.footprintIndicator {
                    healthIndicator(footprint.title, symbol: footprint.symbol, color: Color(nsColor: footprint.color))
                }
                if report.pressureValue == "critical" {
                    healthIndicator(health.pressureTitle, symbol: "exclamationmark.triangle.fill", color: .red)
                } else {
                    Text(LocalizedStringKey(health.pressureTitle)).foregroundStyle(.secondary)
                }
                if report.hasSevereDelay {
                    healthIndicator("New heavy work paused", symbol: "pause.circle.fill", color: .red)
                } else if health.state == "paused" {
                    Text("New heavy work paused").fontWeight(.semibold)
                }
                ForEach(report.additionalReasons, id: \.self) { reason in
                    Text(LocalizedStringKey(DesktopGlyphsHealth.reasonLabel(reason)))
                        .font(.callout.weight(.semibold))
                }
                if !expanded, !report.stale {
                    Text(LocalizedStringKey(health.agentGuidance))
                        .foregroundStyle(.secondary)
                }
            } else {
                Text(LocalizedStringKey(report.statusTitle)).foregroundStyle(.secondary)
            }

            if expanded {
                Divider()
                if let health = report.availableHealth {
                    DesktopGlyphsHealthDetails(health: health)
                } else {
                    Text(LocalizedStringKey(report.unavailableDetail)).foregroundStyle(.secondary)
                }
            }
        }
        .font(.caption)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("desktop.glyphsHealth")
    }

    private func healthIndicator(_ title: String, symbol: String, color: Color) -> some View {
        Label {
            Text(LocalizedStringKey(title))
        } icon: {
            Image(systemName: symbol).foregroundStyle(color).accessibilityHidden(true)
        }
    }
}

struct DesktopGlyphsHealthReport {
    let health: DesktopGlyphsHealth?
    let stale: Bool
    let checking: Bool

    var availableHealth: DesktopGlyphsHealth? {
        guard !checking, let health, health.available == true, health.version == 1 else { return nil }
        return health
    }

    var pressureValue: String? {
        guard !stale, let pressure = availableHealth?.signals?["pressure"], pressure.available == true else { return nil }
        return pressure.value
    }

    var hasSevereDelay: Bool {
        !stale && availableHealth?.reasons?.contains("native_dispatch_delayed") == true
    }

    var footprintLevel: DesktopGlyphsFootprint.Level? {
        guard !stale, let signal = availableHealth?.signals?["footprint"],
              signal.available == true, signal.stale != true, let bytes = signal.bytes else { return nil }
        return DesktopGlyphsFootprint(bytes: bytes, installedMemory: ProcessInfo.processInfo.physicalMemory)?.level
    }

    var footprintIndicator: (title: String, symbol: String, color: NSColor)? {
        guard let level = footprintLevel else { return nil }
        if level == .heavy { return (level.title, "exclamationmark.triangle.fill", .systemOrange) }
        return (level.title, "checkmark.circle.fill", .systemGreen)
    }

    var additionalReasons: [String] {
        (availableHealth?.reasons ?? []).filter {
            $0 != "memory_pressure_warning" && $0 != "memory_pressure_critical"
                && $0 != "native_dispatch_slow" && $0 != "native_dispatch_delayed"
        }
    }

    var statusTitle: String {
        if checking { return "Checking Glyphs" }
        if stale { return "Health observation stale" }
        guard let health = availableHealth else { return "Health unavailable" }
        if health.state == "paused" { return health.title }
        if health.readinessTitle == "Native response delayed" { return health.readinessTitle }
        if footprintLevel == .heavy { return DesktopGlyphsFootprint.Level.heavy.title }
        if pressureValue == "warning" || pressureValue == "critical" { return health.pressureTitle }
        if let reason = additionalReasons.first { return DesktopGlyphsHealth.reasonLabel(reason) }
        return health.readinessTitle
    }

    var unavailableDetail: String {
        checking ? "Collecting health evidence…"
            : "Health protection is unavailable. Update bridge and sidecar together to enable it."
    }

    @MainActor @discardableResult
    func copyToPasteboard() -> Bool {
        let markdown = markdownReport()
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        return pasteboard.setString(markdown, forType: .string)
    }

    private func markdownReport() -> String {
        func label(_ key: String) -> String {
            NSLocalizedString(key, comment: "Glyphs Health Markdown report")
        }

        var lines = ["# \(label("Glyphs Health"))", ""]
        guard let health = availableHealth else {
            lines += ["**\(label("Status")):** \(label(statusTitle))", "", label(unavailableDetail), ""]
            return lines.joined(separator: "\n")
        }

        lines += ["- \(label(stale ? "Showing the last observation." : health.readinessTitle))",
                  "- \(label(health.pressureTitle))"]
        if health.state == "paused" { lines.append("- \(label("New heavy work paused"))") }
        if let pressure = health.signals?["pressure"], pressure.available == true, let time = pressure.observedAt {
            lines.append("- \(label("Last pressure report")): \(Date(timeIntervalSince1970: time).ISO8601Format())")
        }
        lines += additionalReasons.map { "- \(label(DesktopGlyphsHealth.reasonLabel($0)))" }

        if let documents = health.signals?["documents"], documents.available == true {
            lines += ["", "## \(label("Open documents"))", ""]
            if let time = documents.observedAt {
                lines.append("- \(label("Checked at")): \(Date(timeIntervalSince1970: time).ISO8601Format())")
            }
            if let count = documents.fontCount { lines.append("- \(label("Open fonts")): \(count)") }
            if let count = documents.unsavedCount { lines.append("- \(label("Fonts with unsaved changes")): \(count)") }
            if let count = documents.editTabCount { lines.append("- \(label("Edit tabs")): \(count)") }
            if documents.complete == false { lines.append("- \(label("Some details could not be checked."))") }
        }
        if let footprint = health.signals?["footprint"], footprint.available == true, let bytes = footprint.bytes {
            lines += ["", "## \(label("Glyphs memory"))", ""]
            if let time = footprint.observedAt {
                lines.append("- \(label("Sampled at")): \(Date(timeIntervalSince1970: time).ISO8601Format())")
            }
            lines.append("- \(label("Glyphs footprint")): \(formatHealthMemory(bytes))")
            if let share = formatHealthMemoryShare(bytes) {
                lines.append("- \(label("Share of installed RAM")): \(share)")
            }
            if let level = footprintLevel { lines.append("- \(label(level.title))") }
            if let growth = footprint.growthBytes {
                lines.append("- \(healthGrowthLabel(footprint)): \(formatHealthMemory(growth, signed: true))")
            }
            if footprint.stale == true { lines.append("- \(label("Memory observation is stale."))") }
        }
        if !stale {
            lines += ["", "## \(label("Agent guidance"))", "", label(health.agentGuidance), ""]
        }
        return lines.joined(separator: "\n")
    }
}

private func formatHealthMemory(_ bytes: Int64, signed: Bool = false) -> String {
    let value = ByteCountFormatter.string(fromByteCount: bytes, countStyle: .memory)
    return signed && bytes > 0 ? "+\(value)" : value
}

private func formatHealthMemoryShare(_ bytes: Int64) -> String? {
    guard let footprint = DesktopGlyphsFootprint(bytes: bytes, installedMemory: ProcessInfo.processInfo.physicalMemory)
    else { return nil }
    let fraction = footprint.fraction
    let percent = fraction > 0 && fraction < 0.01
        ? NSLocalizedString("Less than 1%", comment: "Small share of installed RAM")
        : fraction.formatted(.percent.precision(.fractionLength(0...1)))
    return String.localizedStringWithFormat(
        NSLocalizedString("%@ of %@", comment: "Memory share and total installed RAM"),
        percent, formatHealthMemory(footprint.installedBytes)
    )
}

private func healthGrowthLabel(_ footprint: DesktopGlyphsHealth.Signal) -> String {
    if let seconds = footprint.growthWindowSeconds {
        return String.localizedStringWithFormat(
            NSLocalizedString("Change over %lld sec", comment: "Glyphs footprint trend interval"), Int64(seconds)
        )
    }
    return NSLocalizedString("Change across recent samples", comment: "Glyphs footprint trend from an older bridge")
}

private struct DesktopGlyphsHealthDetails: View {
    let health: DesktopGlyphsHealth

    var body: some View {
        let documents = health.signals?["documents"]
        let footprint = health.signals?["footprint"]
        let hasDocuments = documents?.available == true
        let hasMemory = footprint?.available == true && footprint?.bytes != nil

        VStack(alignment: .leading, spacing: 12) {
            if hasDocuments || hasMemory {
                LazyVGrid(columns: [
                    GridItem(hasDocuments && hasMemory ? .adaptive(minimum: 280) : .flexible(),
                             spacing: 12, alignment: .topLeading)
                ], spacing: 12) {
                    if hasDocuments, let documents { documentGroup(documents) }
                    if hasMemory, let footprint, let bytes = footprint.bytes { memoryGroup(footprint, bytes: bytes) }
                }
            }
            if let pressure = health.signals?["pressure"], pressure.available == true, let time = pressure.observedAt {
                Text("Last pressure report \(Text(Date(timeIntervalSince1970: time), style: .relative)) ago")
                    .foregroundStyle(.secondary)
            }
            VStack(alignment: .leading, spacing: 8) {
                Text("Agent guidance").fontWeight(.semibold)
                    .accessibilityAddTraits(.isHeader)
                Text(LocalizedStringKey(health.agentGuidance)).foregroundStyle(.secondary)
            }
        }
    }

    private func documentGroup(_ documents: DesktopGlyphsHealth.Signal) -> some View {
        let checked = documents.observedAt.map {
            Text("Checked \(Text(Date(timeIntervalSince1970: $0), style: .relative)) ago")
        }
        return group("Open documents", observation: checked) {
            if let count = documents.fontCount {
                metric("Open fonts", value: Text(count, format: .number))
            }
            if let count = documents.unsavedCount {
                metric("Fonts with unsaved changes", value: documents.complete == false
                    ? Text("\(count) found") : Text(count, format: .number))
            }
            if let count = documents.editTabCount {
                metric("Edit tabs", value: documents.complete == false
                    ? Text("\(count) counted") : Text(count, format: .number))
            }
            if documents.complete == false {
                Text("Some details could not be checked.").foregroundStyle(.secondary)
            }
        }
    }

    private func memoryGroup(_ footprint: DesktopGlyphsHealth.Signal, bytes: Int64) -> some View {
        let sampled = footprint.observedAt.map {
            Text("Sampled \(Text(Date(timeIntervalSince1970: $0), style: .relative)) ago")
        }
        return group("Glyphs memory", observation: sampled) {
            metric("Glyphs footprint", value: Text(formatHealthMemory(bytes)))
            if let share = formatHealthMemoryShare(bytes) {
                metric("Share of installed RAM", value: Text(share))
            }
            if let growth = footprint.growthBytes {
                metric(LocalizedStringKey(healthGrowthLabel(footprint)), value: Text(formatHealthMemory(growth, signed: true)))
            }
            if footprint.stale == true {
                Text("Memory observation is stale.").foregroundStyle(.secondary)
            }
        }
    }

    private func group<Content: View>(
        _ title: LocalizedStringKey, observation: Text?, @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            let heading = Text(title).fontWeight(.semibold).accessibilityAddTraits(.isHeader)
            if let observation {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .firstTextBaseline) {
                        heading
                        Spacer(minLength: 8)
                        observation.foregroundStyle(.secondary)
                    }
                    VStack(alignment: .leading, spacing: 3) {
                        heading
                        observation.foregroundStyle(.secondary)
                    }
                }
            } else {
                heading
            }
            Divider()
            content()
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.quaternary.opacity(0.35), in: RoundedRectangle(cornerRadius: 8))
    }

    private func metric(_ title: LocalizedStringKey, value: Text) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(title)
            Spacer(minLength: 0)
            value.monospacedDigit().fixedSize(horizontal: true, vertical: false)
        }
        .accessibilityElement(children: .combine)
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
                            let attention = desktop.visibleTasks.filter { $0.taskGroup == "attention" }
                            if !attention.isEmpty {
                                taskGroup("Needs attention", tasks: attention)
                            }
                            let active = desktop.visibleTasks.filter { $0.taskGroup == "active" }
                            if !active.isEmpty {
                                taskGroup("Active", tasks: active)
                            }
                            let finished = desktop.visibleTasks.filter { $0.taskGroup == "finished" }
                            if !finished.isEmpty {
                                taskGroup("Finished", tasks: finished)
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
                        .contentMargins(.top, DesktopDashboardLayout.pageTopPadding - 8, for: .scrollContent)
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
                                .padding([.horizontal, .bottom], DesktopDashboardLayout.pagePadding)
                                .padding(.top, DesktopDashboardLayout.pageTopPadding)
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
        .padding(.leading, 16)
        .padding(.trailing, DesktopDashboardLayout.pagePadding)
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
            HStack(spacing: 8) {
                if let status = task.rowStatusLabel {
                    if selected == task.id {
                        Text(LocalizedStringKey(status))
                    } else {
                        Text(LocalizedStringKey(status))
                            .foregroundStyle(task.taskGroup == "attention" ? Color.orange : Color.secondary)
                    }
                }
                Spacer(minLength: 4)
                if let date = task.startedDate {
                    Text(date, format: .dateTime.year().month(.abbreviated).day())
                        .foregroundStyle(selected == task.id ? .primary : .secondary)
                        .help(date.formatted(date: .complete, time: .shortened))
                }
            }.font(.caption).lineLimit(1)
            if task.recoveryAvailable {
                Label("Recovery available", systemImage: "arrow.uturn.backward")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
            .padding(.vertical, 3)
            .listRowBackground(selected == task.id && usesSoftInactiveSelection ? DesktopInactiveTaskSelection() : nil)
            .listRowSeparator(.hidden)
            .listRowInsets(EdgeInsets(top: 3, leading: 12, bottom: 3, trailing: 12))
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
            HStack(spacing: 12) {
                if let status = task.statusLabel { Text(LocalizedStringKey(status)) }
                if let outcome = task.outcomeLabel { Text(LocalizedStringKey(outcome)) }
            }.font(.callout).foregroundStyle(.secondary)
            VStack(alignment: .leading, spacing: 4) {
                if let date = task.startedDate {
                    HStack { Text("Started"); Text(date, format: .dateTime.year().month(.abbreviated).day().hour().minute()) }
                }
                if let date = task.lastActivityDate, date != task.startedDate {
                    HStack { Text("Last activity"); Text(date, format: .dateTime.year().month(.abbreviated).day().hour().minute()) }
                }
                if let date = task.expirationDate {
                    HStack { Text("Expired"); Text(date, format: .dateTime.year().month(.abbreviated).day().hour().minute()) }
                }
            }.font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
            if task.recoveryAvailable {
                Label("Recovery available in this Glyphs session", systemImage: "arrow.uturn.backward")
                    .font(.callout).foregroundStyle(.secondary)
            }
            if let remaining = task.remainingWork {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Remaining work").font(.callout.weight(.semibold))
                        .accessibilityAddTraits(.isHeader)
                    Text(remaining).textSelection(.enabled)
                }
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
            if let blockers = task.blockers, !blockers.isEmpty {
                ForEach(blockers) { blocker in
                    VStack(alignment: .leading, spacing: 6) {
                        Text(blocker.message).textSelection(.enabled)
                        if let identity = blocker.taskId {
                            Button("View blocking task") { selected = identity }
                                .buttonStyle(DesktopSecondaryButtonStyle()).controlSize(.small)
                        }
                    }
                }
            } else if !task.blockedBy.isEmpty {
                Text("Waiting for: \(names(task.blockedBy))").foregroundStyle(.secondary)
            }
            if !task.blocking.isEmpty {
                Text("Blocking: \(names(task.blocking))").foregroundStyle(.orange)
            }
            if !task.closed || task.taskGroup == "attention" {
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
                if !task.closed {
                    Button(LocalizedStringKey(task.taskActionLabel)) { recoveryTask = task }
                        .buttonStyle(DesktopSecondaryButtonStyle()).controlSize(.small)
                }
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
