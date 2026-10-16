import Foundation
import XCTest
@testable import GlyphsMCPInstallerCore

final class FontPackageCopyTests: XCTestCase {
    func testDiscoveryIncludesCleanSourcesWithoutGitAndSkipsPackagesAndLinks() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false)
        defer { try? FileManager.default.removeItem(at: root) }
        for directory in ["sources", ".hidden", "Family.glyphspackage", "Other.app"] {
            try FileManager.default.createDirectory(at: root.appendingPathComponent(directory), withIntermediateDirectories: true)
        }
        for name in ["sources/Font é.glyphs", ".hidden/Hidden.glyphs", "Family.glyphspackage/Nested.glyphs", "Other.app/Inside.glyphs"] {
            try Data().write(to: root.appendingPathComponent(name))
        }
        try FileManager.default.createSymbolicLink(at: root.appendingPathComponent("Link.glyphs"),
            withDestinationURL: root.appendingPathComponent("sources/Font é.glyphs"))
        try FileManager.default.createSymbolicLink(at: root.appendingPathComponent("linked-folder"),
            withDestinationURL: root.appendingPathComponent("sources"))
        let sources = try FontSourceDiscovery.scan(root)
        XCTAssertEqual(Set(sources.map(\.relativePath)), ["Family.glyphspackage", "sources/Font é.glyphs"])
        XCTAssertEqual(sources.filter(\.canCreatePackageCopy).count, 1)
    }

    func testDestinationRequiresSiblingNameAndNeverOffersReplacement() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false)
        defer { try? FileManager.default.removeItem(at: root) }
        let source = root.appendingPathComponent("Font é.glyphs")
        let destination = try FontPackageCopyService.destination(source: source, name: "Copy é.glyphspackage")
        XCTAssertEqual(destination.deletingLastPathComponent().path, root.path)
        for name in ["../Escape.glyphspackage", "folder/Copy.glyphspackage", "Font.glyphs", ".glyphspackage", "a\n.glyphspackage"] {
            XCTAssertThrowsError(try FontPackageCopyService.destination(source: source, name: name))
        }
        try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: false)
        XCTAssertThrowsError(try FontPackageCopyService.destination(source: source, name: destination.lastPathComponent))
        try FileManager.default.removeItem(at: destination)
        try FileManager.default.createSymbolicLink(at: destination, withDestinationURL: root.appendingPathComponent("missing"))
        XCTAssertThrowsError(try FontPackageCopyService.destination(source: source, name: destination.lastPathComponent))
    }
}
