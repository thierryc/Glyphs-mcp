import AppKit
import SwiftUI
import GlyphsMCPInstallerCore

struct DesktopCheckpointHistory: View {
    @ObservedObject var model: DesktopProjectsModel
    @ObservedObject var history: CheckpointHistoryStore
    @Environment(\.dismiss) private var dismiss

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
            Text("Font checkpoints").font(.headline)
            Text("Compare with latest checkpoint").font(.caption).foregroundStyle(.secondary)
            if history.documents.count > 1 {
                Picker("Font", selection: Binding(get: { history.documentID }, set: { history.choose($0) })) {
                    Text("Choose a font").tag("")
                    ForEach(history.documents) { document in
                        Text(document.filename + (history.documents.filter { $0.filename == document.filename }.count > 1 ? " — " + URL(fileURLWithPath: document.path).deletingLastPathComponent().path : ""))
                            .help(document.path).tag(document.id)
                    }
                }
            } else if let document = history.document {
                Text(document.filename).font(.caption).foregroundStyle(.secondary).help(document.path)
            }
            if history.documentsLoaded && history.documents.isEmpty {
                Text("Open the intended saved font in Glyphs to view its checkpoints.").foregroundStyle(.secondary)
            } else if !history.rows.isEmpty {
                ScrollView {
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(Array(groups.enumerated()), id: \.offset) { _, group in
                            Text(group.0).font(.caption).foregroundStyle(.secondary).padding(.top, 8).padding(.horizontal, 8)
                            ForEach(group.1) { checkpoint in
                                Button {
                                    guard let document = history.document, let project = model.selectedProject else { return }
                                    model.showCheckpointComparison(.init(document: document, checkpoint: checkpoint, after: history.head, projectRoot: project))
                                    dismiss()
                                } label: {
                                    HStack(alignment: .firstTextBaseline, spacing: 16) {
                                        Text(checkpoint.title).lineLimit(2).multilineTextAlignment(.leading).frame(maxWidth: .infinity, alignment: .leading)
                                        Text(checkpoint.timeLabel).font(.caption).monospacedDigit().foregroundStyle(.secondary)
                                    }.padding(8).contentShape(Rectangle())
                                }
                                .buttonStyle(.plain)
                                .background(model.historicalComparison?.before == checkpoint.revision && model.historicalComparison?.documentID == history.documentID ? Color.accentColor.opacity(0.15) : Color.clear, in: RoundedRectangle(cornerRadius: 6))
                                .help(checkpoint.helpText)
                                .accessibilityLabel(checkpoint.title + ", " + checkpoint.dateLabel)
                                .disabled(history.head.isEmpty)
                            }
                        }
                    }
                }.frame(height: min(330, CGFloat(history.rows.count) * 44 + CGFloat(groups.count) * 28))
            } else if !history.busy && history.error.isEmpty && !history.documentID.isEmpty {
                Text("No checkpoints for this font yet.").foregroundStyle(.secondary)
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
        }
        .padding(16).frame(width: 420)
        .onAppear { open() }
        .onDisappear { history.cancel() }
    }
    private func open() {
        guard let project = model.selectedProject else { return }
        history.open(project: project, preferredDocument: model.historicalComparison?.documentID)
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
