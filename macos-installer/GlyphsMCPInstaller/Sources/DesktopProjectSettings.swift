import AppKit
import SwiftUI

struct DesktopProjectMenuActions: View {
    @ObservedObject var model: DesktopProjectsModel
    let path: String

    var body: some View {
        Button("Open in Finder") { model.showInFinder(path) }.disabled(!model.folderExists(path))
        Button("Edit Settings…") { model.edit(path) }
        Divider()
        Button("Remove from List") { model.remove(path) }
    }
}

struct DesktopProjectSettings: View {
    @ObservedObject var model: DesktopProjectsModel
    let path: String
    @Environment(\.dismiss) private var dismiss
    @State private var name: String
    @State private var folder: URL
    @State private var error = ""

    init(model: DesktopProjectsModel, path: String) {
        self.model = model; self.path = path
        _name = State(initialValue: model.navigation.name(for: path))
        _folder = State(initialValue: URL(fileURLWithPath: path))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            Text("Project Settings").font(.title2.bold())
            VStack(alignment: .leading, spacing: 8) {
                Text("Display name").font(.headline)
                TextField("Display name", text: $name).textFieldStyle(.roundedBorder)
                Text("Used in Glyphs MCP. The folder name stays the same.").font(.caption).foregroundStyle(.secondary)
            }
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text("Project folder").font(.headline)
                    Spacer()
                    Button("Choose Folder…", action: chooseFolder)
                }
                Text(folder.path).font(.callout).foregroundStyle(.secondary)
                    .textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
                Text("Choose its new location if you moved the folder.").font(.caption).foregroundStyle(.secondary)
            }
            if !error.isEmpty { Text(error).font(.callout).foregroundStyle(.red) }
            HStack {
                Button("Cancel") { dismiss() }.keyboardShortcut(.cancelAction)
                Spacer()
                Button("Save", action: save).keyboardShortcut(.defaultAction)
                    .disabled(name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }.padding(28).frame(width: 460)
    }

    private func chooseFolder() {
        let panel = DesktopProjectsModel.folderPanel("Choose Project Folder")
        panel.canCreateDirectories = false; panel.directoryURL = folder
        panel.begin { response in if response == .OK, let url = panel.url { folder = url; error = "" } }
    }

    private func save() {
        do { try model.update(path, name: name, folder: folder); dismiss() }
        catch { self.error = error.localizedDescription }
    }
}
