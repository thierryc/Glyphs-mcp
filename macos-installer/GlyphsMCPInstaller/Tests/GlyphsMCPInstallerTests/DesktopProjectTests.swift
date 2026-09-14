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
        guard let git = reader.executable else { throw XCTSkip("Git is not installed") }
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
        XCTAssertTrue(observed.changes.contains(where: { $0.path == "font.txt" }))
        let diff = try await reader.diff(project, path: "font.txt")
        XCTAssertTrue(diff.contains("+after")); XCTAssertTrue(diff.contains("-before"))
        XCTAssertEqual(try snapshot(), before)
        XCTAssertEqual(try index.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate, indexModified)
        XCTAssertFalse(FileManager.default.fileExists(atPath: project.appendingPathComponent("helper-ran").path))
    }

    func testGitBranchLabelsDistinguishNoCommitsAndDetachedRevisionWithoutWrites() async throws {
        let reader = ReadOnlyGit()
        guard let git = reader.executable else { throw XCTSkip("Git is not installed") }
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
        guard reader.executable != nil else { throw XCTSkip("Git is not installed") }
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
