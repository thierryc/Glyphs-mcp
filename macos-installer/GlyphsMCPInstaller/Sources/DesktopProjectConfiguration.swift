import SwiftUI
import GlyphsMCPInstallerCore

struct DesktopProjectConfiguration: View {
    @ObservedObject var model: DesktopProjectsModel
    let path: String

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                DesktopFontSources(model: model)
                VStack(alignment: .leading, spacing: 12) {
                    Text("Project").font(.headline)
                    VStack(spacing: 0) {
                        HStack(spacing: 16) {
                            Text("Name").frame(width: 80, alignment: .leading)
                            Text(model.navigation.name(for: path)).lineLimit(1).truncationMode(.middle)
                            Spacer()
                            Button("Edit…") { model.edit(path) }
                        }.padding(12)
                        Divider().padding(.horizontal, 12)
                        HStack(spacing: 16) {
                            Text("Folder").frame(width: 80, alignment: .leading)
                            Text((path as NSString).abbreviatingWithTildeInPath)
                                .foregroundStyle(.secondary).textSelection(.enabled)
                                .lineLimit(1).truncationMode(.middle)
                                .frame(minWidth: 0, maxWidth: .infinity, alignment: .leading).help(path)
                            Spacer(minLength: 0)
                        }.padding(12)
                    }.font(.callout).modifier(DesktopCardSurface())
                }
                VStack(alignment: .leading, spacing: 12) {
                    Text("Open project").font(.headline)
                    VStack(spacing: 0) {
                        action("Open in Finder", symbol: "folder") { model.showInFinder(path) }
                        Divider().padding(.horizontal, 12)
                        action("Open in Editor…", symbol: "curlybraces") { model.openExternal("projectEditor") }
                        Divider().padding(.horizontal, 12)
                        action("Open in Git Client…", symbol: "terminal") { model.openExternal("projectGitClient") }
                    }.modifier(DesktopCardSurface()).disabled(!model.folderExists(path))
                }
            }
            .frame(maxWidth: 850, alignment: .leading)
            .padding(24).frame(maxWidth: .infinity, alignment: .leading)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .accessibilityIdentifier("project-config-view")
    }

    private func action(_ title: LocalizedStringKey, symbol: String, perform: @escaping () -> Void) -> some View {
        Button(action: perform) {
            HStack(spacing: 10) {
                Image(systemName: symbol).foregroundStyle(.secondary).frame(width: 18)
                Text(title)
                Spacer()
                Image(systemName: "arrow.up.right").foregroundStyle(.secondary).accessibilityHidden(true)
            }.font(.callout).padding(12).contentShape(Rectangle())
        }.buttonStyle(.plain)
    }
}
