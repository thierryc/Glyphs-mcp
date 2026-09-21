import Foundation
import XCTest
@testable import GlyphsMCPInstallerCore

final class DesktopProjectTests: XCTestCase {
    private func temporary() throws -> URL {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        addTeardownBlock { try? FileManager.default.removeItem(at: root) }
        return root
    }

    private func requiredGit(
        _ reader: ReadOnlyGit,
        file: StaticString = #filePath,
        line: UInt = #line
    ) throws -> URL {
        try XCTUnwrap(
            reader.executable,
            "The macOS project workflow and its release gate require a Git executable.",
            file: file,
            line: line
        )
    }

    func testStarterUsesActualPortAndCreatesIndependentFolders() throws {
        let parent = try temporary()
        let files = ProjectFiles.starter(agents: StarterProjectCreator.builtinTemplate)
        let project = try ProjectFiles.create(files, in: parent, name: "Test Font", endpoint: URL(string: "http://127.0.0.1:9790/mcp/")!)
        let text = try String(contentsOf: project.appendingPathComponent("AGENTS.md"))
        XCTAssertTrue(text.contains("http://127.0.0.1:9790/mcp/"))
        XCTAssertTrue(text.contains("get_status")); XCTAssertTrue(text.contains("list_documents"))
        XCTAssertTrue(text.contains("document_id"))
        XCTAssertFalse(text.contains("{{ENDPOINT_URL}}"))
        XCTAssertFalse(text.contains("list_open_fonts"))
        XCTAssertTrue(FileManager.default.fileExists(atPath: project.appendingPathComponent("proofs").path))
        XCTAssertFalse(FileManager.default.fileExists(atPath: project.appendingPathComponent(".git").path))
        XCTAssertThrowsError(try ProjectFiles.create(files, in: parent, name: "Test Font", endpoint: DesktopInstallation().endpoint))
        XCTAssertEqual(try String(contentsOf: project.appendingPathComponent("AGENTS.md")), text)
    }

    func testFailedCreationRemovesOnlyItsOwnStagingFolder() throws {
        let parent = try temporary()
        let keep = parent.appendingPathComponent("existing.txt"); try Data("original".utf8).write(to: keep)
        let files = [ProjectFile(path: "valid.txt", data: Data("valid".utf8)), ProjectFile(path: "../escape", data: Data())]
        XCTAssertThrowsError(try ProjectFiles.create(files, in: parent, name: "New Project", endpoint: DesktopInstallation().endpoint))
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: parent.path), ["existing.txt"])
        XCTAssertEqual(try Data(contentsOf: keep), Data("original".utf8))
    }

    func testLocalTemplatesRejectLinksAndLeaveSourceUnchanged() throws {
        let root = try temporary()
        try Data("content".utf8).write(to: root.appendingPathComponent("README.md"))
        let git = root.appendingPathComponent(".git"); try FileManager.default.createDirectory(at: git, withIntermediateDirectories: false)
        try Data("repository".utf8).write(to: git.appendingPathComponent("HEAD"))
        XCTAssertEqual(try ProjectFiles.read(root).map(\.path), ["README.md"])
        try FileManager.default.createSymbolicLink(atPath: root.appendingPathComponent("linked").path, withDestinationPath: "/etc/passwd")
        XCTAssertThrowsError(try ProjectFiles.read(root))
        XCTAssertEqual(try Data(contentsOf: root.appendingPathComponent("README.md")), Data("content".utf8))
    }

    func testCancelledCreationPublishesNothing() async throws {
        let root = try temporary()
        let task = Task {
            withUnsafeCurrentTask { $0?.cancel() }
            return try await ProjectFiles.perform {
                try ProjectFiles.create([ProjectFile(path: "one", data: Data())], in: root, name: "Cancelled", endpoint: URL(string: "http://127.0.0.1:9680/mcp/")!)
            }
        }
        do { _ = try await task.value; XCTFail("Cancellation must propagate to the file operation") } catch is CancellationError { }
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: root.path), [])
    }

    func testTemplateZIPRejectsTraversalLinksDuplicateNamesAndLocalMismatch() throws {
        XCTAssertEqual(try TemplateArchive.validate(zip([("root/README.md", "hello", 0o100644)])), "root")
        for entries: [(String, String, UInt32)] in [
            [("root/../escape", "", 0o100644)], [("/root/file", "", 0o100644)],
            [("root/link", "/etc/passwd", 0o120777)],
            [("root/A", "", 0o100644), ("root/a", "", 0o100644)],
            [("one/a", "", 0o100644), ("two/b", "", 0o100644)]
        ] { XCTAssertThrowsError(try TemplateArchive.validate(zip(entries))) }
        var mismatch = zip([("root/file", "hello", 0o100644)])
        mismatch[30] = UInt8(ascii: "/")
        XCTAssertThrowsError(try TemplateArchive.validate(mismatch))
        XCTAssertThrowsError(try TemplateArchive.validate(Data(mismatch.prefix(20))))
    }

    func testCachedTemplateWorksOfflineAndPreservesCache() async throws {
        let root = try temporary()
        let archive = zip([("template/README.md", "# {{PROJECT_NAME}}", 0o100644)])
        let hash = TemplateStore.checksum(archive)
        let cached = root.appendingPathComponent(hash + ".zip"); try archive.write(to: cached)
        let template = try JSONDecoder().decode(ProjectTemplate.self, from: Data("""
        {"id":"offline","name":"Offline","description":"Test","author":"Test","license":"MIT","repository":"https://github.com/example/template","templateDirectory":".","revision":"0000000000000000000000000000000000000000","archiveSHA256":"\(hash)"}
        """.utf8))
        let configuration = URLSessionConfiguration.ephemeral; configuration.protocolClasses = [OfflineTemplateProtocol.self]
        let store = TemplateStore(root: root, session: URLSession(configuration: configuration))
        let files = try await store.files(template)
        XCTAssertEqual(files.map(\.path), ["README.md"])
        XCTAssertEqual(try Data(contentsOf: cached), archive)
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: root.path), [hash + ".zip"])
        try Data("corrupt".utf8).write(to: cached)
        do { _ = try await store.files(template); XCTFail("An invalid cache must not be used offline") } catch { }
        XCTAssertEqual(try Data(contentsOf: cached), Data("corrupt".utf8))
    }

    func testInterruptedAndWrongChecksumDownloadsNeverPublishCache() async throws {
        let template = try JSONDecoder().decode(ProjectTemplate.self, from: Data("""
        {"id":"download","name":"Download","description":"Test","author":"Test","license":"MIT","repository":"https://github.com/example/template","templateDirectory":".","revision":"0000000000000000000000000000000000000000","archiveSHA256":"0000000000000000000000000000000000000000000000000000000000000000"}
        """.utf8))
        for transport in [InterruptedTemplateProtocol.self, InvalidTemplateProtocol.self] {
            let root = try temporary()
            let keep = root.appendingPathComponent("existing.zip")
            try Data("preserved".utf8).write(to: keep)
            let configuration = URLSessionConfiguration.ephemeral; configuration.protocolClasses = [transport]
            let store = TemplateStore(root: root, session: URLSession(configuration: configuration))
            do { _ = try await store.files(template); XCTFail("Failed downloads must not produce templates") } catch { }
            XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: root.path), ["existing.zip"])
            XCTAssertEqual(try Data(contentsOf: keep), Data("preserved".utf8))
        }
    }

    func testGitInspectionPreservesIndexReferencesAndWorktreeAndDisablesHelpers() async throws {
        let reader = ReadOnlyGit()
        let git = try requiredGit(reader)
        let project = try temporary(), runner = ProcessRunner()
        func command(_ args: [String]) throws {
            let result = runner.runSyncWithStderr(executable: git, args: ["-C", project.path] + args)
            guard result.exitCode == 0 else { throw ProjectError(result.stderr) }
        }
        // Repository mutation is test-fixture setup only, never application code.
        try command(["init"])
        try Data("before\n".utf8).write(to: project.appendingPathComponent("font.txt"))
        try Data("*.txt diff=poison\n".utf8).write(to: project.appendingPathComponent(".gitattributes"))
        try command(["add", "."])
        try command(["-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "fixture"])
        try Data("after\n".utf8).write(to: project.appendingPathComponent("font.txt"))
        let helper = project.appendingPathComponent("external-helper")
        try Data("#!/bin/sh\necho bad > '\(project.path)/helper-ran'\n".utf8).write(to: helper)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: helper.path)
        try command(["config", "diff.poison.textconv", helper.path])
        try command(["config", "diff.external", helper.path])
        try command(["config", "core.fsmonitor", helper.path])
        func snapshot() throws -> [String: Data] {
            let enumerator = FileManager.default.enumerator(at: project, includingPropertiesForKeys: [.isRegularFileKey])!
            var result: [String: Data] = [:]
            while let path = enumerator.nextObject() as? URL {
                if try path.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile == true { result[path.path] = try Data(contentsOf: path) }
            }
            return result
        }
        let before = try snapshot()
        let index = project.appendingPathComponent(".git/index")
        let indexModified = try index.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate
        let observed = try await reader.inspect(project)
        let change = try XCTUnwrap(observed.changes.first(where: { $0.path == "font.txt" }))
        let comparison = try await reader.comparison(project, change: change, headRevision: observed.headRevision)
        XCTAssertEqual(comparison.oldContent, .text("before\n"))
        XCTAssertEqual(comparison.newContent, .text("after\n"))
        let diff = try await reader.diff(project, path: "font.txt")
        XCTAssertTrue(diff.contains("+after")); XCTAssertTrue(diff.contains("-before"))
        XCTAssertEqual(try snapshot(), before)
        XCTAssertEqual(try index.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate, indexModified)
        XCTAssertFalse(FileManager.default.fileExists(atPath: project.appendingPathComponent("helper-ran").path))
    }

    func testCombinedHeadToWorkingTreeComparisonsCoverGitChangeKinds() async throws {
        let reader = ReadOnlyGit()
        let git = try requiredGit(reader)
        let project = try temporary(), runner = ProcessRunner()
        func command(_ args: [String]) throws {
            let result = runner.runSyncWithStderr(executable: git, args: ["-C", project.path] + args)
            guard result.exitCode == 0 else { throw ProjectError(result.stderr) }
        }
        func write(_ path: String, _ text: String) throws {
            try Data(text.utf8).write(to: project.appendingPathComponent(path))
        }
        try command(["init"])
        try write("staged.txt", "staged before\n")
        try write("unstaged.txt", "unstaged before\n")
        try write("mixed.txt", "mixed before\n")
        try write("deleted.txt", "deleted before\n")
        try write("rename-old.txt", "rename line one\nrename line two\n")
        try command(["add", "."])
        try command(["-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "fixture"])

        try write("staged.txt", "staged after\n"); try command(["add", "staged.txt"])
        try write("unstaged.txt", "unstaged after\n")
        try write("mixed.txt", "mixed staged\n"); try command(["add", "mixed.txt"]); try write("mixed.txt", "mixed final\n")
        try write("added.txt", "added\n"); try command(["add", "added.txt"])
        try write("untracked.txt", "untracked\n")
        try command(["rm", "deleted.txt"])
        try command(["mv", "rename-old.txt", "rename-new.txt"])

        let observed = try await reader.inspect(project)
        func comparison(_ path: String) async throws -> GitFileComparison {
            let change = try XCTUnwrap(observed.changes.first(where: { $0.path == path }), "Missing status for \(path)")
            return try await reader.comparison(project, change: change, headRevision: observed.headRevision)
        }
        var value = try await comparison("staged.txt")
        XCTAssertEqual(value.oldContent, .text("staged before\n")); XCTAssertEqual(value.newContent, .text("staged after\n"))
        XCTAssertEqual(try XCTUnwrap(observed.changes.first(where: { $0.path == "staged.txt" })).stagedStatus, "M")
        value = try await comparison("unstaged.txt")
        XCTAssertEqual(value.oldContent, .text("unstaged before\n")); XCTAssertEqual(value.newContent, .text("unstaged after\n"))
        XCTAssertEqual(try XCTUnwrap(observed.changes.first(where: { $0.path == "unstaged.txt" })).workingStatus, "M")
        value = try await comparison("mixed.txt")
        XCTAssertEqual(value.oldContent, .text("mixed before\n")); XCTAssertEqual(value.newContent, .text("mixed final\n"))
        XCTAssertEqual(try XCTUnwrap(observed.changes.first(where: { $0.path == "mixed.txt" })).status, "MM")
        value = try await comparison("added.txt")
        XCTAssertEqual(value.kind, .added); XCTAssertEqual(value.oldContent, .missing); XCTAssertEqual(value.newContent, .text("added\n"))
        value = try await comparison("untracked.txt")
        XCTAssertEqual(value.kind, .untracked); XCTAssertEqual(value.oldContent, .missing); XCTAssertEqual(value.newContent, .text("untracked\n"))
        value = try await comparison("deleted.txt")
        XCTAssertEqual(value.kind, .deleted); XCTAssertEqual(value.oldContent, .text("deleted before\n")); XCTAssertEqual(value.newContent, .missing)
        value = try await comparison("rename-new.txt")
        XCTAssertEqual(value.kind, .renamed); XCTAssertEqual(value.originalPath, "rename-old.txt")
        XCTAssertEqual(value.oldContent, .text("rename line one\nrename line two\n")); XCTAssertEqual(value.newContent, value.oldContent)
    }

    func testComparisonClassifiesUnsafeAndNonRenderingWorkingFiles() async throws {
        let reader = ReadOnlyGit()
        let git = try requiredGit(reader)
        let project = try temporary(), outside = try temporary(), runner = ProcessRunner()
        func command(_ args: [String]) throws {
            let result = runner.runSyncWithStderr(executable: git, args: ["-C", project.path] + args)
            guard result.exitCode == 0 else { throw ProjectError(result.stderr) }
        }
        try command(["init"])
        try Data("outside".utf8).write(to: outside.appendingPathComponent("secret"))
        try Data([0, 1, 2]).write(to: project.appendingPathComponent("binary.dat"))
        try Data([0xff, 0xfe]).write(to: project.appendingPathComponent("invalid.txt"))
        try Data(repeating: 65, count: GitFileComparison.maximumBytes + 1).write(to: project.appendingPathComponent("large.txt"))
        try FileManager.default.createSymbolicLink(atPath: project.appendingPathComponent("link.txt").path,
                                                    withDestinationPath: outside.appendingPathComponent("secret").path)
        let observed = try await reader.inspect(project)
        func value(_ path: String) async throws -> GitFileContent {
            let change = try XCTUnwrap(observed.changes.first(where: { $0.path == path }))
            return try await reader.comparison(project, change: change, headRevision: nil).newContent
        }
        let binary = try await value("binary.dat")
        let invalidText = try await value("invalid.txt")
        let oversized = try await value("large.txt")
        let link = try await value("link.txt")
        XCTAssertEqual(binary, .binary)
        XCTAssertEqual(invalidText, .invalidUTF8)
        XCTAssertEqual(oversized, .oversized(GitFileComparison.maximumBytes + 1))
        XCTAssertEqual(link, .symbolicLink(outside.appendingPathComponent("secret").path))

        try FileManager.default.createSymbolicLink(atPath: project.appendingPathComponent("escape").path,
                                                    withDestinationPath: outside.path)
        let escaping = GitObservation.Change(status: "??", stagedStatus: "?", workingStatus: "?",
                                             kind: .untracked, path: "escape/secret")
        do { _ = try await reader.comparison(project, change: escaping, headRevision: nil); XCTFail("An intermediate link must be rejected") }
        catch { XCTAssertTrue(error.localizedDescription.contains("symbolic link")) }
        let invalid = GitObservation.Change(status: "??", stagedStatus: "?", workingStatus: "?",
                                            kind: .untracked, path: "../secret")
        do { _ = try await reader.comparison(project, change: invalid, headRevision: nil); XCTFail("An invalid path must be rejected") }
        catch { }
        let cancelled = Task {
            withUnsafeCurrentTask { $0?.cancel() }
            return try await reader.comparison(project, change: escaping, headRevision: nil)
        }
        do { _ = try await cancelled.value; XCTFail("A pre-cancelled comparison must stop") }
        catch is CancellationError { }
    }

    func testLargeTrackedFileUsesBoundedCombinedPatchPreview() async throws {
        let reader = ReadOnlyGit()
        let git = try requiredGit(reader)
        let project = try temporary(), runner = ProcessRunner()
        func command(_ args: [String]) throws {
            let result = runner.runSyncWithStderr(executable: git, args: ["-C", project.path] + args)
            guard result.exitCode == 0 else { throw ProjectError(result.stderr) }
        }
        let file = project.appendingPathComponent("fontinfo.plist")
        let unchanged = String(repeating: "unchanged\n", count: 240_000)
        try Data(("appVersion = 4.0;\n" + unchanged + "tail = before;\n").utf8).write(to: file)
        try command(["init"])
        try command(["add", "fontinfo.plist"])
        try command(["-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "fixture"])

        try Data(("appVersion = 4.1;\n" + unchanged + "tail = before;\n").utf8).write(to: file)
        try command(["add", "fontinfo.plist"])
        try Data(("appVersion = 4.1;\n" + unchanged + "tail = working;\n").utf8).write(to: file)

        let observed = try await reader.inspect(project)
        let change = try XCTUnwrap(observed.changes.first(where: { $0.path == "fontinfo.plist" }))
        let comparison = try await reader.comparison(project, change: change, headRevision: observed.headRevision)
        guard case let .oversized(oldBytes) = comparison.oldContent,
              case let .oversized(newBytes) = comparison.newContent else {
            return XCTFail("Both full-file sides should remain subject to the 2 MiB limit")
        }
        XCTAssertGreaterThan(oldBytes, GitFileComparison.maximumBytes)
        XCTAssertGreaterThan(newBytes, GitFileComparison.maximumBytes)
        guard case let .patch(patch, oldSize, newSize) = comparison.textPreview else {
            return XCTFail("Expected a bounded patch preview, got \(comparison.textPreview)")
        }
        XCTAssertEqual(oldSize, oldBytes)
        XCTAssertEqual(newSize, newBytes)
        XCTAssertLessThan(patch.utf8.count, GitFileComparison.maximumBytes)
        XCTAssertTrue(patch.contains("-appVersion = 4.0;"), patch)
        XCTAssertTrue(patch.contains("+appVersion = 4.1;"), patch)
        XCTAssertTrue(patch.contains("-tail = before;"), patch)
        XCTAssertTrue(patch.contains("+tail = working;"), patch)
    }

    func testOversizedLargeFilePatchStopsAtCaptureLimit() async throws {
        let reader = ReadOnlyGit()
        let git = try requiredGit(reader)
        let project = try temporary(), runner = ProcessRunner()
        func command(_ args: [String]) throws {
            let result = runner.runSyncWithStderr(executable: git, args: ["-C", project.path] + args)
            guard result.exitCode == 0 else { throw ProjectError(result.stderr) }
        }
        let file = project.appendingPathComponent("huge.txt")
        try command(["init"])
        try Data((String(repeating: "a", count: GitFileComparison.maximumBytes + 1) + "\n").utf8).write(to: file)
        try command(["add", "huge.txt"])
        try command(["-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "fixture"])
        try Data((String(repeating: "b", count: GitFileComparison.maximumBytes + 1) + "\n").utf8).write(to: file)

        let observed = try await reader.inspect(project)
        let change = try XCTUnwrap(observed.changes.first(where: { $0.path == "huge.txt" }))
        let comparison = try await reader.comparison(project, change: change, headRevision: observed.headRevision)
        guard case let .unavailable(reason, oldSize, newSize) = comparison.textPreview,
              case let .oversizedPatch(limit, observedAtLeast) = reason else {
            return XCTFail("Expected an oversized-patch explanation, got \(comparison.textPreview)")
        }
        XCTAssertEqual(limit, GitFileComparison.maximumBytes)
        XCTAssertGreaterThan(observedAtLeast, limit)
        XCTAssertGreaterThan(oldSize ?? 0, limit)
        XCTAssertGreaterThan(newSize ?? 0, limit)
    }

    func testNoCommitRepositoryTreatsTrackedAndUntrackedFilesAsAdditions() async throws {
        let reader = ReadOnlyGit()
        let git = try requiredGit(reader)
        let project = try temporary(), runner = ProcessRunner()
        func command(_ args: [String]) throws {
            let result = runner.runSyncWithStderr(executable: git, args: ["-C", project.path] + args)
            guard result.exitCode == 0 else { throw ProjectError(result.stderr) }
        }
        try command(["init"])
        try Data("tracked\n".utf8).write(to: project.appendingPathComponent("tracked.txt")); try command(["add", "tracked.txt"])
        try Data("untracked\n".utf8).write(to: project.appendingPathComponent("untracked.txt"))
        let observed = try await reader.inspect(project)
        XCTAssertNil(observed.headRevision)
        for path in ["tracked.txt", "untracked.txt"] {
            let change = try XCTUnwrap(observed.changes.first(where: { $0.path == path }))
            let value = try await reader.comparison(project, change: change, headRevision: observed.headRevision)
            XCTAssertEqual(value.oldContent, .missing)
            XCTAssertEqual(value.newContent, .text(path == "tracked.txt" ? "tracked\n" : "untracked\n"))
        }
    }

    func testGlyphDiffLayerPairingSelectsFirstChangedLayer() throws {
        let metrics = GlyphMetrics(ascender: 800, capHeight: 700, xHeight: 500, descender: -200)
        func layer(_ id: String, _ label: String, _ width: Double,
                   componentOutlines: [[GlyphPathElement]]? = nil) -> GlyphLayerSnapshot {
            GlyphLayerSnapshot(id: id, label: label, isMaster: true, outline: [], openOutline: [], anchors: [:],
                               width: width, metrics: metrics, componentOutlines: componentOutlines)
        }
        let before = GlyphFontSnapshot(missingGlyph: false, glyphName: "A", layers: [layer("one", "Regular", 600), layer("two", "Bold", 700)])
        let component = [[GlyphPathElement(kind: 0, points: [[10, 20]]),
                          GlyphPathElement(kind: 1, points: [[30, 40]]),
                          GlyphPathElement(kind: 3, points: [])]]
        let after = GlyphFontSnapshot(missingGlyph: false, glyphName: "A", layers: [
            layer("one", "Regular", 600), layer("two", "Bold", 710, componentOutlines: component)
        ])
        let difference = GlyphLayerDifference(
            id: "two", label: "Bold", outlineChanged: false,
            referenceOutline: [], currentOutline: [], referenceSegments: [], currentSegments: [], anchors: [],
            width: [700, 710], metricRange: [-200, 800],
            regions: [.init(id: "difference-1", kind: .width, bounds: [676, -224, 58, 1048])],
            hasVisibleDifference: true
        )
        let document = GlyphDiffDocument(schemaVersion: 3, before: before, after: after,
                                         changedLayerIDs: ["two"], differences: [difference])
        XCTAssertEqual(document.layers.map(\.changed), [false, true])
        XCTAssertEqual(document.initialLayerID, "two")
        XCTAssertEqual(document.layers[1].difference, difference)
        XCTAssertEqual(document.layers[1].after?.componentOutlines, component)
        XCTAssertEqual(try JSONDecoder().decode(GlyphDiffDocument.self, from: JSONEncoder().encode(document)), document)
    }

    func testGlyphViewportMathUsesGlyphsStyleStepsLimitsAndRegionFraming() throws {
        XCTAssertEqual(GlyphViewportMath.stepped(1, direction: 1), 1.25, accuracy: 0.000_001)
        XCTAssertEqual(GlyphViewportMath.stepped(1, direction: -1), 0.8, accuracy: 0.000_001)
        XCTAssertEqual(GlyphViewportMath.clamped(0.01), 0.25, accuracy: 0.000_001)
        XCTAssertEqual(GlyphViewportMath.clamped(100), 32, accuracy: 0.000_001)

        let region = try XCTUnwrap(GlyphViewportMath.focusRect(for: [10, 20, 20, 40]))
        XCTAssertEqual(region.width, 160, accuracy: 0.000_001)
        XCTAssertEqual(region.height, 160, accuracy: 0.000_001)
        XCTAssertEqual(region.midX, 20, accuracy: 0.000_001)
        XCTAssertEqual(region.midY, 40, accuracy: 0.000_001)

        let viewport = CGSize(width: 800, height: 600)
        let viewBox = CGRect(x: 0, y: 0, width: 1_000, height: 1_000)
        XCTAssertEqual(GlyphViewportMath.fitScale(viewport: viewport, viewBox: viewBox), 0.6, accuracy: 0.000_001)
        XCTAssertEqual(GlyphViewportMath.actualSizeMagnification(viewport: viewport, viewBox: viewBox), 5.0 / 3.0, accuracy: 0.000_001)
        XCTAssertEqual(GlyphViewportMath.magnificationToFit(viewport: viewport, viewBox: viewBox, target: region), 6.25, accuracy: 0.000_001)

        let fitted = GlyphViewportMath.fitted(viewBox)
        XCTAssertEqual(fitted, .init(centerX: 500, centerY: 500, magnification: 1))
        let contentAnchor = CGPoint(x: 250, y: 400)
        let rootAnchor = CGPoint(x: 250, y: 400)
        let anchored = GlyphViewportMath.anchored(fitted, magnification: 2,
                                                 contentAnchor: contentAnchor,
                                                 rootAnchor: rootAnchor, viewBox: viewBox)
        XCTAssertEqual(anchored.centerX, 375, accuracy: 0.000_001)
        XCTAssertEqual(anchored.centerY, 450, accuracy: 0.000_001)
        XCTAssertEqual(viewBox.midX + anchored.magnification * (contentAnchor.x - anchored.centerX),
                       rootAnchor.x, accuracy: 0.000_001)
        XCTAssertEqual(viewBox.midY + anchored.magnification * (contentAnchor.y - anchored.centerY),
                       rootAnchor.y, accuracy: 0.000_001)
        XCTAssertTrue(GlyphViewportMath.isRestorable(anchored, in: viewBox))
        XCTAssertFalse(GlyphViewportMath.isRestorable(.init(centerX: .infinity, centerY: 0, magnification: 1),
                                                      in: viewBox))
        XCTAssertGreaterThan(GlyphViewportMath.smooth(1, wheelDelta: 20), 1)
        XCTAssertLessThan(GlyphViewportMath.smooth(1, wheelDelta: -20), 1)
    }

    func testGlyphDiffRejectsMaterializedPackageSymlinks() throws {
        let package = try temporary().appendingPathComponent("Fixture.glyphspackage")
        try FileManager.default.createDirectory(at: package.appendingPathComponent("glyphs"), withIntermediateDirectories: true)
        try Data("glyphname = A;".utf8).write(to: package.appendingPathComponent("glyphs/A_.glyph"))
        try GlyphDiffService.validateMaterializedPackage(package)
        try FileManager.default.createSymbolicLink(
            at: package.appendingPathComponent("glyphs/escape.glyph"),
            withDestinationURL: URL(fileURLWithPath: "/etc/passwd")
        )
        XCTAssertThrowsError(try GlyphDiffService.validateMaterializedPackage(package)) { error in
            XCTAssertTrue(error.localizedDescription.contains("Symbolic links"))
        }
    }

    private func readerContract(schema: Int = 3) -> [String: Any] {
        ["schemaVersion": schema, "protocolAPIVersion": 1,
         "workerModule": "glyphs_mcp_sidecar.glyph_diff_worker"]
    }

    private func makeBundledReader(at payload: URL, schema: Int = 3) throws -> GlyphDiffRuntime {
        let lean = payload.appendingPathComponent("Lean", isDirectory: true)
        let cli = lean.appendingPathComponent("runtimes/test/bin/glyphs")
        let worker = lean.appendingPathComponent("sidecar/glyphs_mcp_sidecar/glyph_diff_worker.py")
        let geometry = lean.appendingPathComponent("sidecar/glyphs_mcp_protocol/geometry.py")
        for file in [cli, worker, geometry] {
            try FileManager.default.createDirectory(at: file.deletingLastPathComponent(),
                                                    withIntermediateDirectories: true)
            try Data("fixture".utf8).write(to: file)
        }
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: cli.path)
        let manifest: [String: Any] = [
            "glyphDiffReader": readerContract(schema: schema),
            "runtimes": ["test": ["path": "runtimes/test", "glyphsCLI": "bin/glyphs"]],
        ]
        try JSONSerialization.data(withJSONObject: manifest).write(
            to: lean.appendingPathComponent("manifest.json")
        )
        return GlyphDiffRuntime(glyphsCLI: cli, sidecar: lean.appendingPathComponent("sidecar"))
    }

    private func makeInstalledReader(home: URL, schema: Int = 3) throws -> GlyphDiffRuntime {
        let root = home.appendingPathComponent(
            "Library/Application Support/Glyphs MCP/lean-v2", isDirectory: true
        )
        let cli = root.appendingPathComponent("runtime/bin/glyphs")
        let worker = root.appendingPathComponent("sidecar/glyphs_mcp_sidecar/glyph_diff_worker.py")
        let geometry = root.appendingPathComponent("sidecar/glyphs_mcp_protocol/geometry.py")
        for file in [cli, worker, geometry] {
            try FileManager.default.createDirectory(at: file.deletingLastPathComponent(),
                                                    withIntermediateDirectories: true)
            try Data("fixture".utf8).write(to: file)
        }
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: cli.path)
        let sidecar = root.appendingPathComponent("sidecar", isDirectory: true)
        let runtime = root.appendingPathComponent("runtime", isDirectory: true)
        let receipt: [String: Any] = [
            "components": ["mcp"],
            "sidecar": [
                "identity": try InstallerPayloadManifestResolver.treeIdentity(sidecar),
                "glyphDiffReader": readerContract(schema: schema),
            ],
            "runtime": ["identity": try InstallerPayloadManifestResolver.treeIdentity(runtime)],
        ]
        try JSONSerialization.data(withJSONObject: receipt).write(
            to: root.appendingPathComponent("installation.json")
        )
        return GlyphDiffRuntime(glyphsCLI: cli, sidecar: sidecar, source: .installed)
    }

    private func resolvedPayloadFixture(_ payload: URL) -> InstallerPayload {
        InstallerPayload(payloadDir: payload, pluginBundle: payload,
                         requirementsTxt: payload, skillsDir: nil)
    }

    func testGlyphDiffRuntimePrefersValidatedBundledPayload() throws {
        let root = try temporary()
        let payload = root.appendingPathComponent("Payload", isDirectory: true)
        let expected = try makeBundledReader(at: payload)
        let home = root.appendingPathComponent("home", isDirectory: true)
        _ = try makeInstalledReader(home: home)

        let resolved = try GlyphDiffRuntime.resolve(
            installation: DesktopInstallation(home: home),
            validatedPayload: resolvedPayloadFixture(payload),
            architecture: "test"
        )

        XCTAssertEqual(resolved.glyphsCLI, expected.glyphsCLI)
        XCTAssertEqual(resolved.sidecar, expected.sidecar)
        XCTAssertEqual(resolved.source, .bundled)
        XCTAssertNil(resolved.notice)
    }

    func testGlyphDiffRuntimeUsesIdentityVerifiedInstalledFallback() throws {
        let root = try temporary(), home = root.appendingPathComponent("home", isDirectory: true)
        let expected = try makeInstalledReader(home: home)

        let resolved = try GlyphDiffRuntime.resolve(
            installation: DesktopInstallation(home: home), validatedPayload: nil,
            bundledPayloadError: "fixture payload rejected", architecture: "test"
        )

        XCTAssertEqual(resolved.glyphsCLI, expected.glyphsCLI)
        XCTAssertEqual(resolved.sidecar, expected.sidecar)
        XCTAssertEqual(resolved.source, .installed)
        XCTAssertNotNil(resolved.notice)
    }

    func testGlyphDiffRuntimeRejectsTamperedInstalledReader() throws {
        let root = try temporary(), home = root.appendingPathComponent("home", isDirectory: true)
        let installed = try makeInstalledReader(home: home)
        try Data("tampered".utf8).write(
            to: installed.sidecar.appendingPathComponent("glyphs_mcp_protocol/geometry.py")
        )

        XCTAssertThrowsError(try GlyphDiffRuntime.resolve(
            installation: DesktopInstallation(home: home), validatedPayload: nil,
            bundledPayloadError: "fixture payload rejected", architecture: "test"
        )) { error in
            XCTAssertTrue(error.localizedDescription.contains("does not match its receipt"))
        }
    }

    func testGlyphDiffRuntimeRejectsInstalledReaderSymlink() throws {
        let root = try temporary(), home = root.appendingPathComponent("home", isDirectory: true)
        let installed = try makeInstalledReader(home: home)
        let linked = installed.sidecar.deletingLastPathComponent().appendingPathComponent("sidecar-real")
        try FileManager.default.moveItem(at: installed.sidecar, to: linked)
        try FileManager.default.createSymbolicLink(at: installed.sidecar, withDestinationURL: linked)

        XCTAssertThrowsError(try GlyphDiffRuntime.resolve(
            installation: DesktopInstallation(home: home), validatedPayload: nil,
            bundledPayloadError: "fixture payload rejected", architecture: "test"
        )) { error in
            XCTAssertTrue(error.localizedDescription.contains("symbolic link"))
        }
    }

    func testGlyphDiffRuntimeRejectsWrongSchemaAndMissingReceipt() throws {
        let root = try temporary()
        let payload = root.appendingPathComponent("Payload", isDirectory: true)
        _ = try makeBundledReader(at: payload, schema: 2)
        let home = root.appendingPathComponent("home", isDirectory: true)

        XCTAssertThrowsError(try GlyphDiffRuntime.resolve(
            installation: DesktopInstallation(home: home),
            validatedPayload: resolvedPayloadFixture(payload),
            architecture: "test"
        )) { error in
            XCTAssertTrue(error.localizedDescription.contains("out of sync"))
            XCTAssertTrue(error.localizedDescription.contains("receipt"))
        }
    }

    func testGitChangeTreeBuildsHierarchyAndFiltersCurrentOrOriginalPath() throws {
        let changes = [
            GitObservation.Change(status: " M", stagedStatus: " ", workingStatus: "M", kind: .modified,
                                  path: "Sources/App.swift"),
            GitObservation.Change(status: "R ", stagedStatus: "R", workingStatus: " ", kind: .renamed,
                                  path: "Docs/New.md", originalPath: "Documentation/Old.md"),
            GitObservation.Change(status: "??", stagedStatus: "?", workingStatus: "?", kind: .untracked,
                                  path: "README.md"),
        ]
        let tree = GitChangeTree.hierarchy(changes)
        XCTAssertEqual(tree.map(\.name), ["Docs", "Sources", "README.md"])
        XCTAssertEqual(tree.first?.children?.first?.change?.statusLabel, "R")
        XCTAssertEqual(GitChangeTree.filtered(changes, query: "app").map(\.path), ["Sources/App.swift"])
        XCTAssertEqual(GitChangeTree.filtered(changes, query: "old").map(\.path), ["Docs/New.md"])
        XCTAssertEqual(GitChangeTree.filtered(changes, query: "  "), changes)
    }

    func testGitBranchLabelsDistinguishNoCommitsAndDetachedRevisionWithoutWrites() async throws {
        let reader = ReadOnlyGit()
        let git = try requiredGit(reader)
        let root = try temporary(), runner = ProcessRunner()
        func command(_ args: [String]) throws -> String {
            let result = runner.runSyncWithStderr(executable: git, args: ["-C", root.path] + args)
            guard result.exitCode == 0 else { throw ProjectError(result.stderr) }
            return result.stdout.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        func snapshot() throws -> [String: Data] {
            var files: [String: Data] = [:]
            let entries = FileManager.default.enumerator(at: root, includingPropertiesForKeys: [.isRegularFileKey])!
            while let url = entries.nextObject() as? URL {
                if try url.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile == true { files[url.path] = try Data(contentsOf: url) }
            }
            return files
        }
        _ = try command(["init", "-b", "main"])
        var before = try snapshot()
        var result = try await reader.inspect(root)
        XCTAssertEqual(result.branch, "main · No commits yet")
        XCTAssertEqual(try snapshot(), before)
        _ = try command(["-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "--allow-empty", "-m", "fixture"])
        before = try snapshot()
        result = try await reader.inspect(root)
        XCTAssertEqual(result.branch, "main")
        XCTAssertEqual(try snapshot(), before)
        _ = try command(["checkout", "--detach"])
        let revision = try command(["rev-parse", "--short", "HEAD"])
        before = try snapshot()
        result = try await reader.inspect(root)
        XCTAssertEqual(result.branch, "Detached at " + revision)
        XCTAssertEqual(try snapshot(), before)
    }

    func testOrdinaryProjectNeedsNoGitRepository() async throws {
        let reader = ReadOnlyGit(), root = try temporary()
        _ = try requiredGit(reader)
        do { _ = try await reader.inspect(root); XCTFail("An ordinary folder has no Git status") }
        catch { XCTAssertTrue(error.localizedDescription.contains("This folder isn’t a Git repository")) }
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: root.path), [])
    }

    private func zip(_ entries: [(String, String, UInt32)]) -> Data {
        func le(_ n: UInt32, _ width: Int) -> Data { Data((0..<width).map { UInt8(truncatingIfNeeded: n >> ($0 * 8)) }) }
        var local = Data(), central = Data()
        for (path, text, mode) in entries {
            let name = Data(path.utf8), content = Data(text.utf8), offset = UInt32(local.count)
            var crc: UInt32 = 0xffffffff
            for byte in content { crc ^= UInt32(byte); for _ in 0..<8 { crc = (crc >> 1) ^ (crc & 1 == 1 ? 0xedb88320 : 0) } }
            crc ^= 0xffffffff
            let common = [le(0, 2), le(0, 2), le(0, 2), le(0, 2), le(crc, 4), le(UInt32(content.count), 4), le(UInt32(content.count), 4)].reduce(Data(), +)
            local += [le(0x04034b50, 4), le(20, 2), common, le(UInt32(name.count), 2), le(0, 2), name, content].reduce(Data(), +)
            central += [le(0x02014b50, 4), le(0x0314, 2), le(20, 2), common, le(UInt32(name.count), 2), le(0, 2), le(0, 2), le(0, 2), le(0, 2), le(mode << 16, 4), le(offset, 4), name].reduce(Data(), +)
        }
        return [local, central, le(0x06054b50, 4), le(0, 2), le(0, 2), le(UInt32(entries.count), 2), le(UInt32(entries.count), 2), le(UInt32(central.count), 4), le(UInt32(local.count), 4), le(0, 2)].reduce(Data(), +)
    }
}

private final class OfflineTemplateProtocol: URLProtocol {
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() { client?.urlProtocol(self, didFailWithError: URLError(.notConnectedToInternet)) }
    override func stopLoading() {}
}

private class InvalidTemplateProtocol: URLProtocol {
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data("incomplete archive".utf8))
        finish()
    }
    func finish() { client?.urlProtocolDidFinishLoading(self) }
    override func stopLoading() {}
}
private final class InterruptedTemplateProtocol: InvalidTemplateProtocol {
    override func finish() { client?.urlProtocol(self, didFailWithError: URLError(.networkConnectionLost)) }
}
