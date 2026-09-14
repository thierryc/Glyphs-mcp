import SwiftUI
import GlyphsMCPInstallerCore

struct DesktopProjectActions: View {
    @ObservedObject var model: DesktopProjectsModel
    var body: some View {
        Menu {
            Button { model.create() } label: { Label("New Project…", systemImage: "plus") }
            Button { model.select(.templates) } label: { Label("Browse Templates", systemImage: "doc.on.doc") }
            Button(action: model.chooseProject) { Label("Open Project…", systemImage: "folder") }
            Divider()
            Button(action: model.chooseTemplate) { Label("Add Local Template…", systemImage: "folder.badge.plus") }
            Button(action: model.refreshTemplates) { Label("Refresh Templates", systemImage: "arrow.clockwise") }
                .disabled(model.loadingTemplates)
        } label: { Image(systemName: "ellipsis").frame(width: 20, height: 18) }
        .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
        .help("More project actions").accessibilityLabel("More project actions")
    }
}

struct DesktopProjectCatalog: View {
    @ObservedObject var model: DesktopProjectsModel
    private let columns = [GridItem(.adaptive(minimum: 230, maximum: 360), spacing: 16)]
    var body: some View {
        GeometryReader { geometry in
            ScrollView {
                VStack(spacing: 32) {
                    VStack(spacing: 16) {
                        Image(systemName: "folder.badge.plus")
                            .font(.system(size: 42, weight: .regular)).symbolRenderingMode(.hierarchical)
                            .foregroundStyle(Color.accentColor).frame(width: 82, height: 82)
                            .background(Color.accentColor.opacity(0.08), in: RoundedRectangle(cornerRadius: 22, style: .continuous))
                        Text("Start your next font project")
                            .font(.system(size: 32, weight: .bold)).multilineTextAlignment(.center)
                        Text("Choose a template or open a folder. Keep your font sources, proofs, and exports in one place.")
                            .font(.body).foregroundStyle(.secondary).multilineTextAlignment(.center)
                            .lineSpacing(3).frame(maxWidth: 470)
                        HStack(spacing: 12) {
                            Button(action: model.chooseProject) { Label("Open Project…", systemImage: "folder") }
                                .buttonStyle(.bordered)
                            Button { model.create() } label: { Label("New Project…", systemImage: "plus") }
                                .buttonStyle(.borderedProminent)
                        }.controlSize(.large).padding(.top, 4)
                    }.frame(maxWidth: .infinity)
                    VStack(alignment: .leading, spacing: 16) {
                        HStack {
                            Text("Templates").font(.title3.bold())
                            Spacer()
                            Button(action: model.refreshTemplates) { Label("Refresh", systemImage: "arrow.clockwise") }
                                .disabled(model.loadingTemplates).help("Refresh the template catalog")
                            Button(action: model.chooseTemplate) { Label("Add Local Template…", systemImage: "plus") }
                                .help("Add a local template folder")
                        }
                        if !model.message.isEmpty {
                            Label(model.message, systemImage: "exclamationmark.circle").font(.callout).foregroundStyle(.red)
                        }
                        LazyVGrid(columns: columns, alignment: .center, spacing: 16) {
                            DesktopTemplateCard(title: "Font Project Starter", source: "Built-in", symbol: "folder.fill",
                                description: "Folders for font sources, proofs, exports, and documentation.") { model.create(.starter) }
                            ForEach(model.templates) { template in
                                DesktopTemplateCard(title: template.name, source: "GitHub", symbol: "square.stack.3d.up.fill",
                                    description: template.description, author: template.author) { model.create(.registry(template.id)) }
                            }
                            ForEach(model.localTemplates, id: \.self) { path in
                                DesktopTemplateCard(title: URL(fileURLWithPath: path).lastPathComponent, source: "Local", symbol: "folder.fill",
                                    description: "Create a project from your editable template folder.") { model.create(.local(path)) }
                                    .help(path)
                            }
                        }
                    }.frame(maxWidth: 760)
                }.padding(36).frame(maxWidth: 850).frame(maxWidth: .infinity)
                    .frame(minHeight: geometry.size.height, alignment: .center)
            }
        }
    }
}

private struct DesktopTemplateCard: View {
    let title: String
    let source: String
    let symbol: String
    let description: String
    var author: String? = nil
    let create: () -> Void
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: symbol).font(.title2).foregroundStyle(Color.accentColor)
                Spacer()
                Text(source).font(.caption.weight(.medium)).foregroundStyle(.secondary)
                    .padding(.horizontal, 8).padding(.vertical, 4)
                    .background(Color.primary.opacity(0.04), in: Capsule())
            }
            Text(title).font(.headline)
            Text(description).font(.callout).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            if let author { Text(author).font(.caption).foregroundStyle(.secondary).lineLimit(1) }
            Spacer(minLength: 4)
            Button("Use Template", action: create).accessibilityLabel("Use \(title) template")
        }.padding(20).frame(maxWidth: .infinity, minHeight: 220, alignment: .topLeading)
            .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).strokeBorder(Color.primary.opacity(0.08)))
    }
}
