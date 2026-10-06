import AppKit
import SwiftUI
import GlyphsMCPInstallerCore

enum GlyphComparisonPalette {
    static let currentLightHex = "#137a55"
    static let currentDarkHex = "#4cc38a"
    static let referenceLightHex = "#db2e8c"
    static let referenceDarkHex = "#f15ba6"
    static let deltaLightHex = "#137a554d"
    static let deltaDarkHex = "#4cc38a5c"

    static func current(_ scheme: ColorScheme) -> Color {
        scheme == .dark
            ? Color(red: 76.0 / 255, green: 195.0 / 255, blue: 138.0 / 255)
            : Color(red: 19.0 / 255, green: 122.0 / 255, blue: 85.0 / 255)
    }

    static func reference(_ scheme: ColorScheme) -> Color {
        scheme == .dark
            ? Color(red: 241.0 / 255, green: 91.0 / 255, blue: 166.0 / 255)
            : Color(red: 219.0 / 255, green: 46.0 / 255, blue: 140.0 / 255)
    }

    static func currentHex(_ scheme: ColorScheme) -> String { scheme == .dark ? currentDarkHex : currentLightHex }
    static func referenceHex(_ scheme: ColorScheme) -> String { scheme == .dark ? referenceDarkHex : referenceLightHex }
    static func deltaHex(_ scheme: ColorScheme) -> String { scheme == .dark ? deltaDarkHex : deltaLightHex }
}

struct DesktopCheckpointHistory: View {
    @ObservedObject var model: DesktopProjectsModel
    @ObservedObject var history: CheckpointHistoryStore
    @Environment(\.dismiss) private var dismiss
    @Environment(\.colorScheme) private var colorScheme
    @State private var openingPaths: Set<String> = []
    @State private var openError = ""

    private var groups: [(String, [FontCheckpoint])] {
        var result: [(String, [FontCheckpoint])] = []
        for row in history.rows {
            let label = row.dayLabel()
            if result.last?.0 == label { result[result.count - 1].1.append(row) }
            else { result.append((label, [row])) }
        }
        return result
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Compare font checkpoints").font(.title2.bold())
            if !history.documents.isEmpty {
                Picker("Font", selection: Binding(get: { history.documentID }, set: { history.choose($0) })) {
                    Text("Choose a font").tag("")
                    ForEach(history.documents) { document in
                        Text(document.filename + (history.documents.filter { $0.filename == document.filename }.count > 1 ? " — " + URL(fileURLWithPath: document.path).deletingLastPathComponent().path : ""))
                            .help(document.path).tag(document.id)
                    }
                }
                .pickerStyle(.menu)
                .disabled(history.documents.count == 1)
            }
            if history.documentsLoaded && history.documents.isEmpty && history.unopenedFonts.isEmpty {
                Text("No saved Glyphs font sources were found in this project.").foregroundStyle(.secondary)
            } else if !history.rows.isEmpty {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Choose a version to compare with the latest checkpoint")
                        .font(.subheadline.weight(.medium))
                    Text("Unsaved edits in Glyphs are not included.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                .padding(.top, 4)
                ScrollView {
                    VStack(alignment: .leading, spacing: 0) {
                        ForEach(Array(groups.enumerated()), id: \.offset) { _, group in
                            Text(group.0)
                                .font(.caption).foregroundStyle(.secondary)
                                .padding(.top, 12).padding(.bottom, 4).padding(.horizontal, 8)
                            ForEach(group.1) { checkpoint in
                                checkpointRow(checkpoint)
                            }
                        }
                    }
                }.frame(height: min(330, CGFloat(history.rows.count) * 44 + CGFloat(groups.count) * 28))
                if history.rows.count == 1 {
                    Text("No earlier checkpoints for this font yet.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            } else if !history.busy && history.error.isEmpty && !history.documentID.isEmpty {
                Text("No checkpoints for this font yet.").foregroundStyle(.secondary)
            }
            if history.documentsLoaded && !history.unopenedFonts.isEmpty {
                unopenedFonts
            }
            if history.busy { ProgressView("Loading checkpoints…").controlSize(.small) }
            if !history.error.isEmpty {
                Text(history.error).font(.caption).foregroundStyle(.red).textSelection(.enabled)
                HStack {
                    Button("Retry") {
                        if history.documentsLoaded { history.load(more: history.cursor != nil) }
                        else { open() }
                    }
                    if history.documentsLoaded { Button("Reload recent checkpoints") { history.load(more: false) } }
                }.disabled(history.busy)
            }
            if history.cursor != nil {
                Divider()
                Button("Load older checkpoints…") { history.load(more: true) }.disabled(history.busy)
            }
            if !openError.isEmpty {
                Text(openError).font(.caption).foregroundStyle(.red).textSelection(.enabled)
            }
        }
        .padding(16).frame(width: 520)
        .onAppear { open() }
        .onDisappear { history.cancel() }
    }

    @ViewBuilder private func checkpointRow(_ checkpoint: FontCheckpoint) -> some View {
        let latest = checkpoint.revision == history.latestRevision
        let selected = !latest && model.historicalComparison?.before == checkpoint.revision
            && model.historicalComparison?.documentID == history.documentID
        Group {
            if latest {
                checkpointRowContents(checkpoint, latest: true, selected: false)
            } else {
                Button {
                    guard let document = history.document, let project = model.selectedProject else { return }
                    model.showCheckpointComparison(.init(document: document, checkpoint: checkpoint, after: history.head, projectRoot: project))
                    dismiss()
                } label: {
                    checkpointRowContents(checkpoint, latest: false, selected: selected)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .disabled(history.head.isEmpty)
            }
        }
        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
        .background(selected ? GlyphComparisonPalette.reference(colorScheme).opacity(colorScheme == .dark ? 0.18 : 0.10) : Color.clear,
                    in: RoundedRectangle(cornerRadius: 8))
        .help(checkpoint.helpText)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(rowAccessibilityLabel(checkpoint, latest: latest, selected: selected))
    }

    private func checkpointRowContents(_ checkpoint: FontCheckpoint, latest: Bool, selected: Bool) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            Group {
                if latest {
                    Circle().fill(GlyphComparisonPalette.current(colorScheme))
                } else if selected {
                    Circle().fill(GlyphComparisonPalette.reference(colorScheme))
                } else {
                    Color.clear
                }
            }
            .frame(width: 12, height: 12)
            .accessibilityHidden(true)
            Text(checkpoint.title)
                .lineLimit(2).multilineTextAlignment(.leading)
                .frame(maxWidth: .infinity, alignment: .leading)
                .layoutPriority(1)
            Text(checkpoint.timeLabel)
                .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                .frame(width: 72, alignment: .trailing)
        }
        .padding(.horizontal, 8).padding(.vertical, 6)
    }

    private func rowAccessibilityLabel(_ checkpoint: FontCheckpoint, latest: Bool, selected: Bool) -> String {
        let status = latest ? "Latest checkpoint, " : selected ? "Selected reference, " : ""
        return status + checkpoint.title + ", " + checkpoint.dateLabel
    }
    private func open() {
        guard let project = model.selectedProject else { return }
        history.open(project: project, preferredDocument: model.historicalComparison?.documentID)
    }

    private var unopenedFonts: some View {
        VStack(alignment: .leading, spacing: 8) {
            Divider()
            Text(LocalizedStringKey(history.documents.isEmpty ? "Open a font in Glyphs to view its checkpoints" : "Fonts not open in Glyphs"))
                .font(.caption).foregroundStyle(.secondary)
            ScrollView {
                VStack(spacing: 4) {
                    ForEach(history.unopenedFonts) { font in
                        Button { openFonts([font]) } label: {
                            HStack(spacing: 8) {
                                Image(systemName: "character.cursor.ibeam")
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(font.filename).lineLimit(1)
                                    if let project = model.selectedProject {
                                        Text(relativePath(font.path, project: project)).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                                    }
                                }
                                Spacer()
                                if openingPaths.contains(font.path) { ProgressView().controlSize(.small) }
                                else { Text("Open").foregroundStyle(Color.accentColor) }
                            }.padding(7).contentShape(Rectangle())
                        }
                        .buttonStyle(.plain).help(font.path).disabled(!openingPaths.isEmpty)
                    }
                }
            }.frame(maxHeight: 180)
            if history.unopenedFonts.count > 1 {
                Button("Open all in Glyphs") { openFonts(history.unopenedFonts) }
                    .disabled(!openingPaths.isEmpty)
            }
        }
    }

    private func relativePath(_ path: String, project: String) -> String {
        let root = URL(fileURLWithPath: project).standardizedFileURL.path + "/"
        let value = URL(fileURLWithPath: path).standardizedFileURL.path
        return value.hasPrefix(root) ? String(value.dropFirst(root.count)) : value
    }

    private func openFonts(_ fonts: [CheckpointFontSource]) {
        guard !fonts.isEmpty else { return }
        var applications = GlyphsApplicationDetector.detect().filter { $0.majorVersion == .v4 }
        let installation = DesktopInstallation()
        if let installed = installation.application {
            applications.append(contentsOf: GlyphsApplicationDetector.detect(candidates: [installed]).filter { $0.majorVersion == .v4 })
        }
        guard let application = applications.first(where: { $0.appURL.standardizedFileURL == installation.application?.standardizedFileURL }) ?? applications.first else {
            openError = "Glyphs 4 was not found. Install or locate Glyphs, then try again."
            return
        }
        openError = ""; openingPaths = Set(fonts.map(\.path))
        let urls = fonts.map { URL(fileURLWithPath: $0.path) }
        NSWorkspace.shared.open(urls, withApplicationAt: application.appURL, configuration: NSWorkspace.OpenConfiguration()) { _, error in
            Task { @MainActor in
                if let error { openError = "Could not open the selected font\(fonts.count == 1 ? "" : "s"): \(error.localizedDescription)" }
                openingPaths = []
                guard error == nil else { return }
                try? await Task.sleep(for: .seconds(1))
                open()
            }
        }
    }
}

struct DesktopCheckpointDetails: View {
    let context: CheckpointComparisonContext
    @Environment(\.dismiss) private var dismiss
    @State private var details = ""
    @State private var error = ""
    @State private var busy = false
    @State private var attempt = 0
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack { Text("Action details").font(.title2.bold()); Spacer(); Button("Done") { dismiss() } }
            Text(context.checkpoint.title).font(.headline)
            Text(context.checkpoint.helpText).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
            Text("Recorded actions may not explain all font changes; manual changes are possible.").font(.caption)
            if busy { ProgressView("Loading actions…") }
            if !error.isEmpty { Text(error).foregroundStyle(.red); Button("Retry") { attempt += 1 } }
            ScrollView { Text(details).font(.caption.monospaced()).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading) }
        }.padding(24).frame(width: 640, height: 480)
            .task(id: attempt) {
                busy = true; error = ""
                do {
                    let value = try await CheckpointClient.read(documentID: context.documentID, selector: ["kind":"checkpoint_details", "selected":context.before])
                    guard !Task.isCancelled else { return }
                    details = String(decoding: try JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted, .sortedKeys]), as: UTF8.self)
                } catch { if !Task.isCancelled { self.error = error.localizedDescription } }
                busy = false
            }
    }
}

struct DesktopCheckpointRestore: View {
    let context: CheckpointComparisonContext
    let completed: () -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var key = UUID().uuidString
    @State private var workflow: [String: Any]?
    @State private var pending: [String: Any]?
    @State private var busy = false
    @State private var error = ""
    @State private var started = false
    @State private var refreshed = false

    private var actions: [[String: Any]] { workflow?["actions"] as? [[String: Any]] ?? [] }
    private var terminal: Bool {
        guard let state = workflow?["state"] as? String else { return false }
        return ["executed", "saved", "discarded", "cancelled", "failed", "no_changes"].contains(state) && actions.isEmpty
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Restore this checkpoint?").font(.title2.bold())
            Text(context.document.filename).font(.headline)
            Text(context.checkpoint.title)
            Text(context.checkpoint.helpText).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
            Text("Restoring replaces the open font’s content, including unsaved edits, and clears Undo history. It does not save. Git history and other files remain intact.")
            if let workflow {
                Divider()
                Text(workflow["message"] as? String ?? "Checking result…").textSelection(.enabled)
                ForEach(actions.indices, id: \.self) { index in
                    let action = actions[index]
                    Button(action["label"] as? String ?? "Continue") { respond(action) }
                        .disabled(busy || pending != nil || action["requiresDestination"] as? Bool == true)
                    if action["requiresDestination"] as? Bool == true {
                        Text("Use the offered manual save option to save in Glyphs.").font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
            if busy { ProgressView("Checking restore…").controlSize(.small) }
            if !error.isEmpty {
                Text(error).foregroundStyle(.red).textSelection(.enabled)
                Button("Check result / Retry") {
                    if let pending { perform(pending) }
                    else { poll() }
                }.disabled(busy)
            }
            HStack {
                Spacer()
                if !started {
                    Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                    Button("Restore…") {
                        started = true
                        perform(["action":"restore", "document_id":context.documentID, "revision":context.before, "idempotency_key":key])
                    }.keyboardShortcut(.defaultAction)
                } else if terminal {
                    Button("Done") { dismiss() }.keyboardShortcut(.defaultAction)
                } else if workflow != nil {
                    Button("Check result") { poll() }.disabled(busy || pending != nil)
                }
            }
        }.padding(24).frame(width: 560)
            .interactiveDismissDisabled(started && !terminal)
            .task {
                while !Task.isCancelled {
                    do { try await Task.sleep(for: .seconds(2)) } catch { return }
                    if workflow?["poll"] as? Bool == true && !busy && pending == nil && error.isEmpty { poll() }
                }
            }
    }
    private func poll() {
        guard let id = workflow?["id"] else { return }
        perform(["action":"workflow", "workflow_id":id])
    }
    private func respond(_ action: [String: Any]) {
        guard let workflow else { return }
        perform(["action":"respond", "workflow_id":workflow["id"] ?? "", "expected_revision":workflow["revision"] ?? 0, "action_token":action["token"] ?? ""])
    }
    private func perform(_ body: [String: Any]) {
        guard !busy else { return }
        busy = true; error = ""; pending = body
        Task { @MainActor in
            do {
                guard let value = try await CheckpointClient.call(body) as? [String: Any] else { throw ProjectError("Invalid restore response. Check the existing result.") }
                workflow = value; pending = nil
                let state = value["state"] as? String
                let job = value["job"] as? [String: Any]
                if !refreshed && ["executed", "saved"].contains(state ?? "") && job?["outcome"] as? String != "unverified" {
                    refreshed = true; completed()
                }
            } catch { self.error = error.localizedDescription }
            busy = false
        }
    }
}
