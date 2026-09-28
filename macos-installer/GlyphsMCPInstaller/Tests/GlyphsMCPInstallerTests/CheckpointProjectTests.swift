import Foundation
import XCTest
@testable import GlyphsMCPInstallerCore

final class CheckpointProjectTests: XCTestCase {
    func testPolicyRejectsBrokenSymlinkAndBooleanSchemaVersion() throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: false)
        defer { try? FileManager.default.removeItem(at: folder) }
        let config = folder.appendingPathComponent(".glyphs-mcp.json")
        try FileManager.default.createSymbolicLink(atPath: config.path, withDestinationPath: folder.appendingPathComponent("missing.json").path)
        XCTAssertThrowsError(try FontCheckpointPolicy.read(folder))
        XCTAssertThrowsError(try FontCheckpointPolicy.write(folder, enabled: true, expected: nil))
        try FileManager.default.removeItem(at: config)
        try Data(#"{"schemaVersion":true,"gitCheckpoints":{"enabled":true}}"#.utf8).write(to: config)
        XCTAssertThrowsError(try FontCheckpointPolicy.read(folder))
    }

    func testPolicyIsExplicitAndPreservesOtherConfiguration() throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: false)
        defer { try? FileManager.default.removeItem(at: folder) }
        let config = folder.appendingPathComponent(".glyphs-mcp.json")
        let before = Data(#"{"schemaVersion":1,"gitCheckpoints":{"enabled":false},"other":"keep"}"#.utf8)
        try before.write(to: config)
        XCTAssertFalse(try FontCheckpointPolicy.read(folder).enabled)
        try FontCheckpointPolicy.write(folder, enabled: true, expected: before)
        XCTAssertTrue(try FontCheckpointPolicy.read(folder).enabled)
        let object = try JSONSerialization.jsonObject(with: Data(contentsOf: config)) as! [String: Any]
        XCTAssertEqual(object["other"] as? String, "keep")
        XCTAssertThrowsError(try FontCheckpointPolicy.write(folder, enabled: false, expected: before))
        XCTAssertFalse(FileManager.default.fileExists(atPath: folder.appendingPathComponent(".git").path))
    }

    func testBundledCheckpointTemplateIsDiscoverableOffline() throws {
        let registry = try TemplateRegistry.decode(Data("{\"schemaVersion\":1,\"templates\":[]}".utf8)).includingBuiltIns()
        let entry = try XCTUnwrap(registry.templates.first { $0.id == "font-git-checkpoints" })
        XCTAssertEqual(entry.name, "Font project with Git checkpoints")
        XCTAssertTrue(entry.isBundled)
        XCTAssertNil(entry.archiveURL)
    }

    func testGitInitializationIsExplicitAndDoesNotCommit() throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: false)
        defer { try? FileManager.default.removeItem(at: folder) }
        let files = ProjectFiles.starter(agents: "test")
        let result = try ProjectFiles.create(files, in: folder, name: "Git Font", endpoint: DesktopInstallation().endpoint, initializeGit: true)
        XCTAssertTrue(FileManager.default.fileExists(atPath: result.appendingPathComponent(".git/HEAD").path))
        let check = ProcessRunner().runSyncWithStderr(executable: URL(fileURLWithPath: "/usr/bin/git"), args: ["-C", result.path, "rev-parse", "--verify", "HEAD"])
        XCTAssertNotEqual(check.exitCode, 0)
        XCTAssertThrowsError(try ProjectFiles.create(files, in: result, name: "Nested", endpoint: DesktopInstallation().endpoint, initializeGit: true))
    }
}

final class CheckpointHistoryTests: XCTestCase {
    func testReadableTitlesAndCalendarBoundaries() throws {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = try XCTUnwrap(TimeZone(secondsFromGMT: -4 * 3600))
        let now = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-09-28T04:05:00Z"))
        let today = try XCTUnwrap(FontCheckpoint(dictionary: ["revision":"today", "summary":"Font checkpoint: Add 0.125 units", "timestamp":now.timeIntervalSince1970]))
        let yesterday = try XCTUnwrap(FontCheckpoint(dictionary: ["revision":"yesterday", "timestamp":now.addingTimeInterval(-600).timeIntervalSince1970]))
        XCTAssertEqual(today.title, "Add 0.125 units")
        XCTAssertEqual(today.summary, "Font checkpoint: Add 0.125 units")
        XCTAssertEqual(today.dayLabel(now: now, calendar: calendar), "Today")
        XCTAssertEqual(yesterday.dayLabel(now: now, calendar: calendar), "Yesterday")
        XCTAssertEqual(yesterday.title, "Untitled checkpoint")
        XCTAssertTrue(today.helpText.contains("today"))
        XCTAssertEqual(FontCheckpoint(dictionary: ["revision":"missing"])?.dayLabel(), "Date unavailable")
        XCTAssertNil(FontCheckpoint(dictionary: [:]))
    }

    func testDocumentScopeUsesPathBoundaryAndAllowsDuplicateFilenames() {
        let documents = CheckpointDocument.eligible([
            ["id":"a", "path":"/project/a/Font.glyphs"],
            ["id":"b", "path":"/project/b/Font.glyphs"],
            ["id":"outside", "path":"/project-other/Font.glyphs"],
            ["id":"escape", "path":"/project/../other/Font.glyphs"],
            ["id":"unsaved"]
        ], project: "/project")
        XCTAssertEqual(documents.map(\.id), ["a", "b"])
    }

    @MainActor
    private func settle(_ store: CheckpointHistoryStore) async throws {
        for _ in 0..<200 {
            if !store.busy { return }
            try await Task.sleep(for: .milliseconds(5))
        }
        XCTFail("History request did not finish")
    }

    @MainActor
    func testSingleFontAutoloadPaginationAndReopeningRefreshes() async throws {
        var selectors: [[String: Any]] = []
        let store = CheckpointHistoryStore { body in
            if body["action"] as? String == "documents" { return [["id":"font", "path":"/project/Font.glyphs"]] }
            let selector = body["selector"] as! [String: Any]; selectors.append(selector)
            let older = selector["cursor"] != nil
            var page: [String: Any] = ["head":"latest", "checkpoints":older ? [["revision":"two"], ["revision":"one"]] : [["revision":"two"]]]
            if !older { page["nextCursor"] = "next" }
            return [["checkpoint":page]]
        }
        store.open(project: "/project", preferredDocument: nil)
        try await settle(store)
        XCTAssertEqual(store.documentID, "font")
        XCTAssertEqual(selectors.first?["limit"] as? Int, 20)
        XCTAssertEqual(store.rows.map(\.id), ["two"])
        store.load(more: true); try await settle(store)
        XCTAssertEqual(store.rows.map(\.id), ["two", "one"])
        XCTAssertNil(store.cursor)
        XCTAssertEqual(selectors.last?["cursor"] as? String, "next")
        store.open(project: "/project", preferredDocument: "font"); try await settle(store)
        XCTAssertEqual(store.rows.map(\.id), ["two"])
        XCTAssertNil(selectors.last?["cursor"])
    }

    @MainActor
    func testMultipleFontsRequireSelectionAndOldResponseCannotReplaceNewFont() async throws {
        var oldResponse: CheckedContinuation<Any, Error>?
        let store = CheckpointHistoryStore { body in
            if body["action"] as? String == "documents" { return [["id":"a", "path":"/project/A.glyphs"], ["id":"b", "path":"/project/B.glyphs"]] }
            if body["document_id"] as? String == "a" {
                return try await withCheckedThrowingContinuation { oldResponse = $0 }
            }
            return [["checkpoint":["head":"b-head", "checkpoints":[["revision":"b"]]]]]
        }
        store.open(project: "/project", preferredDocument: nil); try await settle(store)
        XCTAssertEqual(store.documentID, "")
        store.choose("a")
        for _ in 0..<200 { if oldResponse != nil { break }; try await Task.sleep(for: .milliseconds(5)) }
        let pending = try XCTUnwrap(oldResponse)
        store.choose("b"); try await settle(store)
        pending.resume(returning: [["checkpoint":["head":"a-head", "checkpoints":[["revision":"a"]]]]])
        await Task.yield()
        XCTAssertEqual(store.documentID, "b")
        XCTAssertEqual(store.rows.map(\.id), ["b"])
        XCTAssertEqual(store.head, "b-head")
    }

    @MainActor
    func testPaginationFailureKeepsRowsAndCursorForRetry() async throws {
        var fail = true
        let store = CheckpointHistoryStore { body in
            if body["action"] as? String == "documents" { return [["id":"a", "path":"/project/A.glyphs"]] }
            let selector = body["selector"] as! [String: Any]
            if selector["cursor"] != nil {
                if fail { throw ProjectError("History changed. Read the first page again.") }
                return [["checkpoint":["head":"head", "checkpoints":[["revision":"old"]]]]]
            }
            return [["checkpoint":["head":"head", "checkpoints":[["revision":"new"]], "nextCursor":"next"]]]
        }
        store.open(project: "/project", preferredDocument: nil); try await settle(store)
        store.load(more: true); try await settle(store)
        XCTAssertEqual(store.rows.map(\.id), ["new"])
        XCTAssertEqual(store.cursor, "next")
        XCTAssertFalse(store.error.isEmpty)
        fail = false
        store.load(more: true); try await settle(store)
        XCTAssertEqual(store.rows.map(\.id), ["new", "old"])
        XCTAssertTrue(store.error.isEmpty)
    }
}
