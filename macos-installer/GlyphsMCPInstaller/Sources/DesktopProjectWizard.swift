import AppKit
import ImageIO
import SwiftUI
import GlyphsMCPInstallerCore

struct DesktopProjectWizard: View {
    private enum Step { case template, details, project }
    @ObservedObject var model: DesktopProjectsModel
    let template: DesktopTemplateChoice
    let previewFirst: Bool
    @Environment(\.dismiss) private var dismiss
    @State private var step: Step
    @State private var name = "My Font Project"
    @State private var parent = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
    @State private var files: [ProjectFile] = []
    @State private var filesLoaded = false
    @State private var busy = false
    @State private var error = ""
    @State private var operation: Task<Void, Never>?
    init(model: DesktopProjectsModel, template: DesktopTemplateChoice, previewFirst: Bool = false) {
        self.model = model; self.template = template; self.previewFirst = previewFirst
        _step = State(initialValue: previewFirst ? .template : .details)
    }
    private var title: String {
        switch step {
        case .template: return "Preview template"
        case .details: return "Name your font project"
        case .project: return "Preview your project"
        }
    }
    private var initializesGit: Bool { if case .registry(let id) = template { return model.templates.first { $0.id == id }?.isBundled == true }; return false }
    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            VStack(alignment: .leading, spacing: 6) {
                Text(LocalizedStringKey(title)).font(.title.bold())
                Text("Template: \(model.templateName(template))").foregroundStyle(.secondary)
            }
            if step == .details {
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
                if step == .project {
                    Text(parent.appendingPathComponent(name.trimmingCharacters(in: .whitespacesAndNewlines)).path)
                        .font(.callout).foregroundStyle(.secondary).textSelection(.enabled)
                }
                if filesLoaded {
                    DesktopTemplateFileBrowser(files: files,
                        projectName: step == .project ? name.trimmingCharacters(in: .whitespacesAndNewlines) : nil,
                        endpoint: DesktopInstallation().endpoint)
                } else {
                    VStack(spacing: 12) {
                        if busy { ProgressView("Preparing template…") }
                        else { Button("Retry Preview") { loadFiles(next: step) } }
                    }.frame(maxWidth: .infinity, minHeight: 360)
                }
                if step == .project {
                    if initializesGit {
                        Text("Create Project initializes a new local Git repository and enables MCP checkpoints. It does not make a commit, save a font or push. Add your own font to sources.")
                            .font(.callout).foregroundStyle(.secondary)
                    }
                    Button("Save as Local Template…", action: duplicateTemplate).disabled(busy)
                }
            }
            if !error.isEmpty { Label(error, systemImage: "exclamationmark.circle").foregroundStyle(.orange) }
            if busy, step != .template { Text(LocalizedStringKey(step == .details ? "Preparing template…" : "Creating project…")).font(.callout).foregroundStyle(.secondary) }
            HStack {
                Button(LocalizedStringKey(step == .template ? "Close" : "Cancel")) { operation?.cancel(); dismiss() }.keyboardShortcut(.cancelAction)
                Spacer()
                if step == .project { Button("Back") { step = .details }.disabled(busy) }
                else if step == .details, previewFirst { Button("Back to Preview") { step = .template }.disabled(busy) }
                if step == .template {
                    Button("Use Template…") { step = .details }.disabled(busy || !filesLoaded)
                } else {
                    Button(LocalizedStringKey(step == .project ? "Create Project" : "Preview Project"), action: advance)
                        .keyboardShortcut(.defaultAction).disabled(busy || name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
        }.padding(28).frame(width: step == .details ? 570 : 900)
            .task { if previewFirst { loadFiles(next: .template) } }
            .onDisappear { operation?.cancel() }
    }
    private func chooseParent() {
        let panel = DesktopProjectsModel.folderPanel("Choose Project Location"); panel.directoryURL = parent
        panel.begin { response in if response == .OK, let url = panel.url { parent = url } }
    }
    private func advance() {
        if step == .details { loadFiles(next: .project); return }
        error = ""; busy = true
        let snapshot = files, location = parent, projectName = name, endpoint = DesktopInstallation().endpoint, initializeGit = initializesGit
        operation = Task {
            do {
                let url = try await ProjectFiles.perform { try ProjectFiles.create(snapshot, in: location, name: projectName, endpoint: endpoint, initializeGit: initializeGit) }
                model.addProject(url); dismiss()
            } catch { if !Task.isCancelled { self.error = error.localizedDescription } }
            busy = false
        }
    }
    private func loadFiles(next: Step) {
        error = ""
        if filesLoaded { step = next; return }
        busy = true
        operation = Task {
            do {
                let snapshot = try await model.files(for: template)
                try Task.checkCancellation()
                files = snapshot; filesLoaded = true; step = next
            } catch { if !Task.isCancelled { self.error = error.localizedDescription } }
            busy = false
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

private struct DesktopTemplateFileBrowser: View {
    let files: [ProjectFile]
    let projectName: String?
    let endpoint: URL
    @State private var selection: String?
    private var nodes: [ProjectPreviewNode] { ProjectPreviewNode.hierarchy(files) }
    private var selectedFile: ProjectFile? { files.first { $0.path == selection } }

    var body: some View {
        HSplitView {
            VStack(alignment: .leading, spacing: 8) {
                Text("Folder structure").font(.headline)
                List(selection: $selection) {
                    OutlineGroup(nodes, children: \.children) { node in
                        Label(node.name, systemImage: node.isDirectory ? "folder" : "doc.text")
                            .tag(node.path).help(node.path)
                    }
                }.listStyle(.sidebar).accessibilityIdentifier("template-file-tree")
            }.frame(minWidth: 220, idealWidth: 280)
            VStack(alignment: .leading, spacing: 8) {
                Text(selection ?? "File contents").font(.headline).textSelection(.enabled)
                fileContent.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            }.padding(.leading, 12).frame(minWidth: 320, idealWidth: 540)
        }.frame(height: 400)
            .onAppear { selectInitialFile() }
            .onChange(of: files) { _, _ in selectInitialFile() }
    }
    @ViewBuilder private var fileContent: some View {
        if let file = selectedFile, let original = file.data {
            let data = projectName.map { ProjectFiles.renderedData(original, projectName: $0, endpoint: endpoint) } ?? original
            if let image = rasterImage(data) {
                ScrollView {
                    Image(image, scale: 1, label: Text("Image preview for \(file.path)")).resizable().scaledToFit()
                }
            } else if let preview = ProjectTextPreview.read(data) {
                VStack(alignment: .leading, spacing: 8) {
                    if data.isEmpty { Text("Empty file").foregroundStyle(.secondary) }
                    else {
                        GeometryReader { geometry in
                            ScrollView([.horizontal, .vertical]) {
                                Text(verbatim: preview.text).font(.system(.body, design: .monospaced))
                                    .textSelection(.enabled)
                                    .frame(minWidth: geometry.size.width, minHeight: geometry.size.height, alignment: .topLeading)
                                    .accessibilityIdentifier("template-file-content")
                            }
                        }
                    }
                    if preview.truncated { Text("Showing the first 256 KB.").font(.caption).foregroundStyle(.secondary) }
                }
            } else {
                Text("Binary file · \(ByteCountFormatter.string(fromByteCount: Int64(data.count), countStyle: .file))\nNo inline preview is available.")
                    .foregroundStyle(.secondary)
            }
        } else if let path = selection {
            let empty = !files.contains { $0.path.hasPrefix(path + "/") }
            Text(empty ? "Empty folder" : "Select a file in this folder to preview its contents.").foregroundStyle(.secondary)
        } else {
            Text(files.isEmpty ? "This template is empty." : "Select a file to preview its contents.").foregroundStyle(.secondary)
        }
    }
    private func selectInitialFile() {
        selection = files.first { $0.path == "README.md" && $0.data != nil }?.path
            ?? files.first { $0.data != nil }?.path
    }
    private func rasterImage(_ data: Data) -> CGImage? {
        guard data.count <= 16 * 1024 * 1024,
              let source = CGImageSourceCreateWithData(data as CFData, nil),
              let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
              let width = properties[kCGImagePropertyPixelWidth] as? NSNumber,
              let height = properties[kCGImagePropertyPixelHeight] as? NSNumber,
              width.doubleValue * height.doubleValue <= 20_000_000 else { return nil }
        return CGImageSourceCreateImageAtIndex(source, 0, nil)
    }
}
