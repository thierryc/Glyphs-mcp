import AppKit
import SwiftUI
import GlyphsMCPInstallerCore

extension DesktopProjectsModel {
    func refreshFontSources() {
        fontSourcesTask?.cancel()
        fontSourcesGeneration = UUID()
        let generation = fontSourcesGeneration
        fontSources = []; fontSourcesError = ""; loadingFontSources = false
        guard let project = selectedProject else { return }
        loadingFontSources = true
        fontSourcesTask = Task {
            do {
                let sources = try await ProjectFiles.perform {
                    try FontSourceDiscovery.scan(URL(fileURLWithPath: project))
                }
                guard !Task.isCancelled, generation == fontSourcesGeneration else { return }
                fontSources = sources
            } catch {
                guard !Task.isCancelled, generation == fontSourcesGeneration else { return }
                fontSourcesError = error.localizedDescription
            }
            if generation == fontSourcesGeneration { loadingFontSources = false }
        }
    }

    func preparePackageCopy(_ source: ProjectFontSource) {
        guard source.canCreatePackageCopy, copyingSource == nil else { return }
        packageCopyError = ""; packageCopySource = source
    }

    func createPackageCopy(_ source: ProjectFontSource, name: String) {
        guard copyingSource == nil, let project = selectedProject else { return }
        packageCopyError = ""; packageCopyResult = nil
        copyingSource = source.id; packageCopyProject = project
        packageCopyTask = Task {
            do {
                let result = try await FontPackageCopyService.shared.create(source: source.url, name: name)
                packageCopyResult = result
                selectedFontSource = result.url.resolvingSymlinksInPath().standardizedFileURL.path
                packageCopySource = nil
                if selectedProject == project { refreshFontSources(); inspect() }
            } catch is CancellationError {
                packageCopySource = nil
            } catch { packageCopyError = error.localizedDescription }
            copyingSource = nil; packageCopyTask = nil
        }
    }

    func cancelPackageCopy() {
        if copyingSource != nil { packageCopyTask?.cancel() }
        else { packageCopySource = nil }
    }

    func revealFontSource(_ url: URL) {
        NSWorkspace.shared.activateFileViewerSelecting([url])
    }
}

struct DesktopFontSources: View {
    @ObservedObject var model: DesktopProjectsModel

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Font sources").font(.headline)
                    Text("Saved sources in this project").font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Button(action: model.refreshFontSources) { Image(systemName: "arrow.clockwise") }
                    .buttonStyle(.borderless).help("Refresh font sources")
                    .accessibilityLabel("Refresh font sources").disabled(model.loadingFontSources)
            }
            if model.loadingFontSources {
                ProgressView("Reading font sources…").controlSize(.small)
            } else if !model.fontSourcesError.isEmpty {
                Text(model.fontSourcesError).font(.callout).foregroundStyle(.orange)
            } else if model.fontSources.isEmpty {
                Text("No Glyphs sources in this project.").font(.callout).foregroundStyle(.secondary)
            } else {
                LazyVStack(spacing: 0) {
                    ForEach(model.fontSources) { source in
                        if source.id != model.fontSources.first?.id { Divider().padding(.horizontal, 12) }
                        HStack(spacing: 8) {
                            Image(systemName: source.canCreatePackageCopy ? "doc" : "shippingbox")
                                .font(.title3).foregroundStyle(.secondary).frame(width: 24)
                            VStack(alignment: .leading, spacing: 4) {
                                Text(source.url.lastPathComponent).font(.callout)
                                    .lineLimit(1).truncationMode(.middle)
                                let directory = (source.relativePath as NSString).deletingLastPathComponent
                                if directory.isEmpty {
                                    Text("Project root").font(.caption).foregroundStyle(.secondary)
                                } else {
                                    Text(directory).font(.caption).foregroundStyle(.secondary)
                                        .lineLimit(1).truncationMode(.middle)
                                }
                            }
                            Spacer()
                            if model.copyingSource == source.id { ProgressView().controlSize(.small) }
                            Menu { actions(source) } label: {
                                Image(systemName: "ellipsis").frame(width: 22, height: 22)
                            }
                            .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
                            .accessibilityLabel(Text("Font source actions: \(source.relativePath)"))
                        }
                        .padding(.horizontal, 12).padding(.vertical, 10).contentShape(Rectangle())
                        .background(model.selectedFontSource == source.id ? Color.accentColor.opacity(0.15) : .clear,
                                    in: RoundedRectangle(cornerRadius: 5))
                        .contextMenu { actions(source) }
                        .help(source.url.path)
                        .accessibilityIdentifier("font-source-\(source.relativePath)")
                    }
                }.modifier(DesktopCardSurface())
            }
            if model.packageCopyProject == model.selectedProject, let result = model.packageCopyResult {
                HStack {
                    Label("Package copy created", systemImage: "checkmark.circle.fill").foregroundStyle(.green)
                    Text(result.url.lastPathComponent).lineLimit(1).truncationMode(.middle)
                    Spacer()
                    Button("Reveal in Finder") { model.revealFontSource(result.url) }
                }.font(.callout).accessibilityIdentifier("package-copy-success")
            }
        }
    }

    @ViewBuilder private func actions(_ source: ProjectFontSource) -> some View {
        if source.canCreatePackageCopy {
            Button("Create Package Copy…") { model.preparePackageCopy(source) }
                .disabled(model.copyingSource != nil)
            Divider()
        }
        Button("Reveal in Finder") { model.revealFontSource(source.url) }
    }
}

struct DesktopPackageCopySheet: View {
    @ObservedObject var model: DesktopProjectsModel
    let source: ProjectFontSource
    @State private var name: String
    private var running: Bool { model.copyingSource != nil }
    private var nameError: String? {
        do { _ = try FontPackageCopyService.destination(source: source.url, name: name); return nil }
        catch { return error.localizedDescription }
    }

    init(model: DesktopProjectsModel, source: ProjectFontSource) {
        self.model = model; self.source = source
        _name = State(initialValue: source.url.deletingPathExtension().lastPathComponent + ".glyphspackage")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Create Package Copy").font(.title2.bold())
            Text(source.relativePath).font(.callout).textSelection(.enabled)
            TextField("Package filename", text: $name).textFieldStyle(.roundedBorder)
                .disabled(running).accessibilityIdentifier("package-copy-filename")
            Text(source.url.deletingLastPathComponent().path).font(.caption).foregroundStyle(.secondary)
                .textSelection(.enabled)
            Text("Creates a package beside this source and keeps the original. Only saved contents are copied; unsaved Glyphs edits are excluded. Per-glyph modification timestamps may be omitted.")
                .font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            if running {
                ProgressView("Creating and verifying package copy…").controlSize(.small)
            } else if let error = nameError {
                Text(error).font(.callout).foregroundStyle(.orange)
            }
            if !model.packageCopyError.isEmpty {
                Text(model.packageCopyError).font(.callout).foregroundStyle(.orange)
                    .textSelection(.enabled).lineLimit(8)
            }
            HStack {
                Spacer()
                Button("Cancel", action: model.cancelPackageCopy).keyboardShortcut(.cancelAction)
                Button("Create Package Copy") { model.createPackageCopy(source, name: name) }
                    .keyboardShortcut(.defaultAction).disabled(running || nameError != nil)
            }
        }.padding(24).frame(width: 510)
            .interactiveDismissDisabled(running)
    }
}
