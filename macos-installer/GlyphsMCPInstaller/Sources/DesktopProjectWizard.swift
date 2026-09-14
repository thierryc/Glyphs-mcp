import AppKit
import SwiftUI
import GlyphsMCPInstallerCore

struct DesktopProjectWizard: View {
    @ObservedObject var model: DesktopProjectsModel
    let template: DesktopTemplateChoice
    @Environment(\.dismiss) private var dismiss
    @State private var step = 0
    @State private var name = "My Font Project"
    @State private var parent = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
    @State private var files: [ProjectFile] = []
    @State private var busy = false
    @State private var error = ""
    @State private var operation: Task<Void, Never>?
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            VStack(alignment: .leading, spacing: 6) {
                Text(step == 0 ? "Name your font project" : "Preview your project").font(.title.bold())
                Text("Template: \(model.templateName(template))").foregroundStyle(.secondary)
            }
            if step == 0 {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Project name").font(.subheadline.weight(.medium))
                    TextField("Project name", text: $name)
                }
                Text("Location").font(.subheadline.weight(.medium))
                HStack {
                    Text(parent.path).lineLimit(2).foregroundStyle(.secondary)
                    Spacer()
                    Button("Choose Location…", action: chooseParent)
                }
                if case .registry(let id) = template, let entry = model.templates.first(where: { $0.id == id }) {
                    Text("\(entry.author) · \(entry.license)").font(.caption).foregroundStyle(.secondary)
                    Text("Template files are copied. Scripts are not run.").font(.caption).foregroundStyle(.secondary)
                }
                Button("Change Template…") { model.select(.templates); dismiss() }
            } else {
                Text(parent.appendingPathComponent(name.trimmingCharacters(in: .whitespacesAndNewlines)).path).font(.callout).foregroundStyle(.secondary)
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 5) {
                        ForEach(files, id: \.path) { file in Label(file.path, systemImage: file.data == nil ? "folder" : "doc") }
                    }
                }.frame(minHeight: 180, maxHeight: 320)
                Button("Save as Local Template…", action: duplicateTemplate)
            }
            if !error.isEmpty { Label(error, systemImage: "exclamationmark.circle").foregroundStyle(.red) }
            if busy { Text(step == 0 ? "Preparing template…" : "Creating project…").font(.callout).foregroundStyle(.secondary) }
            HStack {
                Button("Cancel") { operation?.cancel(); dismiss() }.keyboardShortcut(.cancelAction)
                Spacer()
                if step > 0 { Button("Back") { step -= 1 }.disabled(busy) }
                Button(step == 1 ? "Create Project" : "Preview Project", action: advance)
                    .keyboardShortcut(.defaultAction).disabled(busy || name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }.padding(28).frame(width: 570).onDisappear { operation?.cancel() }
    }
    private func chooseParent() {
        let panel = DesktopProjectsModel.folderPanel("Choose Project Location"); panel.directoryURL = parent
        panel.begin { response in if response == .OK, let url = panel.url { parent = url } }
    }
    private func advance() {
        error = ""; busy = true
        if step == 0 {
            operation = Task {
                do {
                    files = try await model.files(for: template)
                    try Task.checkCancellation(); step = 1
                } catch { if !Task.isCancelled { self.error = error.localizedDescription } }
                busy = false
            }
        } else {
            let snapshot = files, location = parent, projectName = name, endpoint = DesktopInstallation().endpoint
            operation = Task {
                do {
                    let url = try await ProjectFiles.perform { try ProjectFiles.create(snapshot, in: location, name: projectName, endpoint: endpoint) }
                    model.addProject(url); dismiss()
                } catch { if !Task.isCancelled { self.error = error.localizedDescription } }
                busy = false
            }
        }
    }
    private func duplicateTemplate() {
        let panel = DesktopProjectsModel.folderPanel("Choose a Folder for Your Editable Template")
        panel.begin { response in
            guard response == .OK, let parent = panel.url else { return }
            do {
                let url = try ProjectFiles.create(files, in: parent, name: name + " Template", endpoint: DesktopInstallation().endpoint)
                model.rememberTemplate(url); NSWorkspace.shared.open(url)
            } catch { self.error = error.localizedDescription }
        }
    }
}
