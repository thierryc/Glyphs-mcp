import Foundation
import XCTest
@testable import GlyphsMCPInstallerCore

final class DesktopTemplateCatalogTests: XCTestCase {
    private func preferences() -> UserDefaults {
        let name = "DesktopTemplateCatalogTests." + UUID().uuidString
        let defaults = UserDefaults(suiteName: name)!
        addTeardownBlock { defaults.removePersistentDomain(forName: name) }
        return defaults
    }
    private func template(_ id: String = "online", name: String = "Online", repository: String = "https://github.com/example/fonts",
                          directory: String = ".", revision: String = String(repeating: "a", count: 40)) throws -> ProjectTemplate {
        let data = try JSONSerialization.data(withJSONObject: ["id": id, "name": name, "description": "Description", "author": "Author",
            "license": "MIT", "repository": repository, "templateDirectory": directory, "revision": revision,
            "archiveSHA256": String(repeating: "b", count: 64)])
        return try JSONDecoder().decode(ProjectTemplate.self, from: data)
    }
    func testMixedSourcesUseOneAlphabeticalListAndNoInitialFavorites() throws {
        let favorites = DesktopTemplateFavorites(defaults: preferences())
        let entries = DesktopTemplateEntry.catalog(templates: [try template(name: "alpha")],
            localPaths: ["/Templates/zebra", "/Templates/beta"], favorites: favorites)
        XCTAssertEqual(entries.map(\.name), ["alpha", "beta", "Font Project Starter", "zebra"])
        XCTAssertTrue(entries.allSatisfy { !favorites.contains($0.choice) })
        XCTAssertEqual(entries.map(\.choice), [.registry("online"), .local("/Templates/beta"), .starter, .local("/Templates/zebra")])
    }
    func testFavoritesAndOthersAreAlphabeticalAndUnfavoritingReorders() throws {
        var favorites = DesktopTemplateFavorites(defaults: preferences())
        favorites.toggle(.local("/Templates/zebra")); favorites.toggle(.starter)
        let templates = [try template(name: "alpha")]
        let paths = ["/Templates/zebra", "/Templates/beta"]
        XCTAssertEqual(DesktopTemplateEntry.catalog(templates: templates, localPaths: paths, favorites: favorites).map(\.name),
                       ["Font Project Starter", "zebra", "alpha", "beta"])
        favorites.toggle(.starter)
        XCTAssertEqual(DesktopTemplateEntry.catalog(templates: templates, localPaths: paths, favorites: favorites).map(\.name),
                       ["zebra", "alpha", "beta", "Font Project Starter"])
    }
    func testPersistenceRefreshAndAbsentEntriesRetainIdentity() throws {
        let defaults = preferences()
        var favorites = DesktopTemplateFavorites(defaults: defaults)
        favorites.toggle(.registry("online")); favorites.toggle(.local("/Templates/child/../Local")); favorites.toggle(.starter)
        favorites.save(to: defaults)
        var reloaded = DesktopTemplateFavorites(defaults: defaults)
        XCTAssertTrue(reloaded.contains(.local("/Templates/Local")))
        XCTAssertTrue(reloaded.contains(.starter))
        XCTAssertFalse(reloaded.contains(.registry("builtin:starter")))
        _ = DesktopTemplateEntry.catalog(templates: [], localPaths: [], favorites: reloaded)
        reloaded.save(to: defaults)
        reloaded = DesktopTemplateFavorites(defaults: defaults)
        let refreshed = try template(name: "Renamed", revision: String(repeating: "c", count: 40))
        let entries = DesktopTemplateEntry.catalog(templates: [refreshed], localPaths: [], favorites: reloaded)
        XCTAssertTrue(reloaded.contains(entries.first(where: { $0.name == "Renamed" })!.choice))
        reloaded.toggle(.registry("online")); reloaded.save(to: defaults)
        XCTAssertFalse(DesktopTemplateFavorites(defaults: defaults).contains(.registry("online")))
    }
    func testNaturalOrderingTiesAndNormalizedLocalDuplicates() throws {
        let favorites = DesktopTemplateFavorites(defaults: preferences())
        let templates = [try template("second", name: "Same"), try template("first", name: "Same")]
        let paths = ["/T/font 10", "/T/Font 2", "/T/Same", "/T/sub/../Same", "/T/alpha", "relative"]
        let entries = DesktopTemplateEntry.catalog(templates: templates, localPaths: paths, favorites: favorites)
        XCTAssertEqual(entries.filter { $0.name != "Font Project Starter" }.map(\.name),
                       ["alpha", "Font 2", "font 10", "Same", "Same", "Same"])
        XCTAssertEqual(entries.filter { $0.name == "Same" }.map(\.id), ["local:/T/Same", "registry:first", "registry:second"])
        XCTAssertEqual(entries.first(where: { $0.name == "Same" })?.localURL?.path, "/T/Same")
    }
    func testPinnedRootAndRepositoryLinks() throws {
        let entry = try template(repository: "https://github.com/example/fonts/")
        XCTAssertEqual(entry.githubTemplateURL?.absoluteString, "https://github.com/example/fonts/tree/" + String(repeating: "a", count: 40))
        XCTAssertEqual(entry.issuesURL?.absoluteString, "https://github.com/example/fonts/issues")
        XCTAssertEqual(entry.starURL?.absoluteString, "https://github.com/example/fonts")
        XCTAssertEqual(entry.archiveURL?.absoluteString, "https://codeload.github.com/example/fonts/zip/" + String(repeating: "a", count: 40))
    }
    func testNestedTemplatePathsAreEncodedWithoutQueryOrFragment() throws {
        let entry = try template(directory: "templates/Font #1 50%?/é")
        let url = try XCTUnwrap(entry.githubTemplateURL)
        XCTAssertEqual(url.path, "/example/fonts/tree/" + String(repeating: "a", count: 40) + "/templates/Font #1 50%?/é")
        XCTAssertNil(url.query); XCTAssertNil(url.fragment)
        XCTAssertTrue(url.absoluteString.contains("Font%20%231%2050%25%3F"))
    }
    func testInvalidRepositoryAndDirectoryNeverProduceTemplateLinks() throws {
        for repository in ["http://github.com/example/fonts", "https://evil.example/example/fonts", "https://github.com@evil.example/example/fonts",
                           "https://user@github.com/example/fonts", "https://github.com:443/example/fonts", "https://github.com/example/fonts?query=1",
                           "https://github.com/example/fonts#fragment", "https://github.com/example", "https://github.com/example/fonts/tree/main",
                           "https://github.com/../fonts"] {
            let entry = try template(repository: repository)
            XCTAssertNil(entry.githubTemplateURL, repository); XCTAssertNil(entry.issuesURL, repository); XCTAssertNil(entry.starURL, repository)
        }
        for directory in ["../escape", "/absolute", "a//b", "a/./b", "a\\b"] {
            XCTAssertNil(try template(directory: directory).githubTemplateURL)
        }
        XCTAssertNil(try template(revision: "main").githubTemplateURL)
    }

    func testPreviewTreeIncludesImplicitAndEmptyFoldersWithNaturalOrdering() {
        let files = [ProjectFile(path: "sources/Font 10.glyphs", data: Data()),
                     ProjectFile(path: "sources/Font 2.glyphs", data: Data()),
                     ProjectFile(path: "sources", data: nil),
                     ProjectFile(path: "proofs", data: nil),
                     ProjectFile(path: "documentation/help/README.md", data: Data()),
                     ProjectFile(path: ".gitignore", data: Data())]
        let nodes = ProjectPreviewNode.hierarchy(files)
        XCTAssertEqual(nodes.map(\.name), ["documentation", "proofs", "sources", ".gitignore"])
        XCTAssertEqual(nodes[1].children, [])
        XCTAssertEqual(nodes[2].children?.map(\.name), ["Font 2.glyphs", "Font 10.glyphs"])
        XCTAssertEqual(nodes[0].children?.first?.children?.first?.path, "documentation/help/README.md")
        XCTAssertNil(nodes.last?.children)
        XCTAssertEqual(ProjectPreviewNode.hierarchy(Array(files.reversed())), nodes)
    }

    func testPreviewRenderingMatchesCreatedProjectWithoutChangingTemplateSnapshot() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let data = Data("# {{PROJECT_NAME}}\n{{SERVER_NAME}} at {{ENDPOINT_URL}}\n".utf8)
        let endpoint = URL(string: "http://127.0.0.1:9790/mcp/")!
        let expected = ProjectFiles.renderedData(data, projectName: "My Font", endpoint: endpoint)
        let project = try ProjectFiles.create([ProjectFile(path: "README.md", data: data)], in: root,
                                              name: "  My Font  ", endpoint: endpoint)
        XCTAssertEqual(try Data(contentsOf: project.appendingPathComponent("README.md")), expected)
        XCTAssertTrue(String(decoding: expected, as: UTF8.self).contains("My Font"))
        XCTAssertTrue(String(decoding: data, as: UTF8.self).contains("{{PROJECT_NAME}}"))
    }

    func testTextPreviewIsBoundedAndDoesNotSplitUTF8Scalars() throws {
        let data = Data("A😀B".utf8)
        XCTAssertEqual(ProjectTextPreview.read(data, maximumBytes: 4)?.text, "A")
        XCTAssertEqual(ProjectTextPreview.read(data, maximumBytes: 5)?.text, "A😀")
        XCTAssertEqual(ProjectTextPreview.read(data)?.truncated, false)
        let large = Data(repeating: 65, count: 300_000)
        let preview = try XCTUnwrap(ProjectTextPreview.read(large, maximumBytes: 1_000_000))
        XCTAssertEqual(preview.text.utf8.count, 256 * 1024)
        XCTAssertTrue(preview.truncated)
    }

    func testBinaryAndLargeFilesAreNeverRenderedAsProjectTemplates() {
        let endpoint = URL(string: "http://127.0.0.1:9680/mcp/")!
        let binary = Data([0, 255, 1])
        XCTAssertNil(ProjectTextPreview.read(binary))
        XCTAssertNil(ProjectTextPreview.read(Data([255, 254])))
        XCTAssertEqual(ProjectFiles.renderedData(binary, projectName: "Font", endpoint: endpoint), binary)
        let data = Data(("{{PROJECT_NAME}}" + String(repeating: "x", count: 1_000_000)).utf8)
        XCTAssertEqual(ProjectFiles.renderedData(data, projectName: "Font", endpoint: endpoint), data)
        XCTAssertEqual(ProjectTextPreview.read(Data())?.text, "")
        XCTAssertEqual(ProjectTextPreview.read(Data())?.truncated, false)
    }
}
