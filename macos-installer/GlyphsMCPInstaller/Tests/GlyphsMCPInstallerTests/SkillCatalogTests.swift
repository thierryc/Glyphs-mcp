import Foundation
import XCTest
@testable import GlyphsMCPInstallerCore

final class SkillCatalogTests: XCTestCase {
    private var temporary: URL!
    override func setUpWithError() throws {
        temporary = URL(fileURLWithPath: "/private/tmp").appendingPathComponent("SkillCatalogTests-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: temporary, withIntermediateDirectories: true)
    }
    override func tearDownWithError() throws { try FileManager.default.removeItem(at: temporary) }
    private func skill(_ revision: Character = "a") -> CatalogSkill {
        .init(id: "test/test-skill", name: "test-skill", description: "A focused workflow", author: "Tester", license: "MIT", classification: .community,
              source: .init(repository: "https://github.com/test/skills", directory: "skills/test-skill", revision: String(repeating: String(revision), count: 40), archiveSHA256: String(repeating: "b", count: 64)),
              compatibleClients: [.codex, .cursor, .claudeCode], requirements: [])
    }
    private func files(_ text: String = "Original") -> [ProjectFile] {
        [.init(path: "SKILL.md", data: Data(("---\nname: test-skill\ndescription: A focused workflow\n---\n" + text).utf8))]
    }
    func testCatalogRejectsFloatingSourceMissingHashDuplicatesAndImports() throws {
        let valid = skill()
        _ = try SkillCatalog.decode(JSONEncoder().encode(SkillCatalog(skills: [valid])))
        var floating = valid; floating.source.revision = "main"
        var noHash = valid; noHash.source.archiveSHA256 = nil
        var imported = valid; imported.classification = .imported
        for entries in [[floating], [noHash], [valid, valid], [imported]] {
            XCTAssertThrowsError(try SkillCatalog.decode(JSONEncoder().encode(SkillCatalog(skills: entries))))
        }
    }
    func testMetadataAndContainedReferences() throws {
        let metadata = try SkillMetadata.parse(Data("---\nname: test-skill\ndescription: >-\n  A focused\n  workflow\n---\n".utf8))
        XCTAssertEqual(metadata.description, "A focused workflow")
        XCTAssertThrowsError(try SkillMetadata.parse(Data("---\nname: one\nname: two\ndescription: x\n---\n".utf8)))
        XCTAssertThrowsError(try SkillMetadata.validate(files("[x](../outside.md)")))
        XCTAssertThrowsError(try SkillMetadata.validate(files("[x](missing.md)")))
        _ = try SkillMetadata.validate(files("[x](references/details.md)") + [
            .init(path: "references", data: nil), .init(path: "references/details.md", data: Data("[x](../assets/info.txt)".utf8)),
            .init(path: "assets", data: nil), .init(path: "assets/info.txt", data: Data("info".utf8))])
    }
    func testSupplementalInstallUpdateRemoveAndBackup() throws {
        let installer = SupplementalSkillInstaller(home: temporary)
        let root = LocalSkillTarget.agents.root(home: temporary)
        _ = try installer.install(skill(), files: files(), root: root)
        XCTAssertEqual(installer.status(skill(), root: root).state, .installed)
        XCTAssertEqual(installer.status(skill("c"), root: root).state, .updateAvailable)
        let result = try installer.install(skill("c"), files: files("Updated"), root: root)
        XCTAssertTrue(result.contains("Backup:"))
        XCTAssertEqual(installer.status(skill("c"), root: root).state, .installed)
        let removal = try installer.remove(skill("c"), root: root)
        XCTAssertTrue(removal.contains("Backup:"))
        XCTAssertEqual(installer.status(skill(), root: root).state, .notInstalled)
    }
    func testEditedAndUnownedCopiesRemainPreservedUntilExplicitReplacement() throws {
        let installer = SupplementalSkillInstaller(home: temporary)
        let root = LocalSkillTarget.agents.root(home: temporary)
        _ = try installer.install(skill(), files: files(), root: root)
        let path = root.appendingPathComponent("test-skill/SKILL.md")
        try Data("User edits".utf8).write(to: path)
        XCTAssertEqual(installer.status(skill(), root: root).state, .modified)
        XCTAssertThrowsError(try installer.install(skill("c"), files: files(), root: root))
        XCTAssertThrowsError(try installer.remove(skill(), root: root))
        XCTAssertEqual(try String(contentsOf: path), "User edits")
        _ = try installer.install(skill(), files: files(), root: root, replace: true)
        try FileManager.default.removeItem(at: root.appendingPathComponent(".glyphs-mcp-catalog-skills.json"))
        XCTAssertEqual(installer.status(skill(), root: root).state, .unowned)
        XCTAssertThrowsError(try installer.install(skill(), files: files(), root: root))
    }
    func testLegacyAndSymbolicLinkCollisionsCannotBeOverwritten() throws {
        let installer = SupplementalSkillInstaller(home: temporary)
        let root = LocalSkillTarget.agents.root(home: temporary)
        let old = temporary.appendingPathComponent(".codex/skills/test-skill")
        try FileManager.default.createDirectory(at: old, withIntermediateDirectories: true)
        try Data("legacy".utf8).write(to: old.appendingPathComponent("SKILL.md"))
        XCTAssertThrowsError(try installer.install(skill(), files: files(), root: root, replace: true))
        try FileManager.default.removeItem(at: temporary.appendingPathComponent(".codex"))
        let source = temporary.appendingPathComponent("original")
        try FileManager.default.createDirectory(at: source, withIntermediateDirectories: true)
        try Data("source".utf8).write(to: source.appendingPathComponent("SKILL.md"))
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        try FileManager.default.createSymbolicLink(at: root.appendingPathComponent("test-skill"), withDestinationURL: source)
        XCTAssertThrowsError(try installer.install(skill(), files: files(), root: root, replace: true))
        XCTAssertEqual(try String(contentsOf: source.appendingPathComponent("SKILL.md")), "source")
    }
    func testLegacyCopyIsDiscoveredAndUpdatedAtItsActualLocation() throws {
        let installer = SupplementalSkillInstaller(home: temporary)
        let root = temporary.appendingPathComponent(".codex/skills")
        let folder = root.appendingPathComponent("test-skill")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        try files()[0].data!.write(to: folder.appendingPathComponent("SKILL.md"))
        let status = installer.status(skill(), target: .agents)
        XCTAssertEqual(status.state, .unowned)
        XCTAssertEqual(status.path, folder.path)
        XCTAssertTrue(status.isInstalled)
        XCTAssertTrue(status.requiresBackupConfirmation)
        let found = installer.installationRoot(skill(), target: .agents)
        XCTAssertEqual(found.path, root.path)
        _ = try installer.install(skill("c"), files: files("Updated"), root: found, replace: true)
        XCTAssertEqual(installer.status(skill("c"), target: .agents).state, .installed)
        XCTAssertFalse(FileManager.default.fileExists(atPath: LocalSkillTarget.agents.root(home: temporary).appendingPathComponent("test-skill").path))
        _ = try installer.remove(skill("c"), root: found)
        XCTAssertEqual(installer.status(skill(), target: .agents).state, .notInstalled)
    }
    func testExplicitRemovalBacksUpUnmanagedAndEditedCopies() throws {
        let installer = SupplementalSkillInstaller(home: temporary)
        let root = LocalSkillTarget.agents.root(home: temporary)
        _ = try installer.install(skill(), files: files(), root: root)
        let path = root.appendingPathComponent("test-skill/SKILL.md")
        try Data("Keep my edits".utf8).write(to: path)
        let result = try installer.remove(skill(), root: root, preserveExisting: true)
        let backup = String(result.components(separatedBy: "Backup: ").last!)
        XCTAssertEqual(try String(contentsOf: URL(fileURLWithPath: backup).appendingPathComponent("SKILL.md")), "Keep my edits")
        let legacyRoot = temporary.appendingPathComponent(".cursor/skills")
        let legacy = legacyRoot.appendingPathComponent("test-skill")
        try FileManager.default.createDirectory(at: legacy, withIntermediateDirectories: true)
        try files()[0].data!.write(to: legacy.appendingPathComponent("SKILL.md"))
        XCTAssertThrowsError(try installer.remove(skill(), root: legacyRoot))
        _ = try installer.remove(skill(), root: legacyRoot, preserveExisting: true)
        XCTAssertEqual(installer.status(skill(), target: .agents).state, .notInstalled)
    }
    func testLinkedCopyRemovalPreservesSourceAndThenAllowsInstall() throws {
        let installer = SupplementalSkillInstaller(home: temporary)
        let source = temporary.appendingPathComponent("development")
        try FileManager.default.createDirectory(at: source, withIntermediateDirectories: true)
        try Data("My development source".utf8).write(to: source.appendingPathComponent("SKILL.md"))
        let root = temporary.appendingPathComponent(".codex/skills")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let link = root.appendingPathComponent("test-skill")
        try FileManager.default.createSymbolicLink(at: link, withDestinationURL: source)
        XCTAssertEqual(installer.status(skill(), target: .agents).state, .linked)
        XCTAssertThrowsError(try installer.install(skill(), files: files(), root: root, replace: true))
        XCTAssertThrowsError(try installer.remove(skill(), root: root))
        let result = try installer.remove(skill(), root: root, preserveExisting: true)
        let backup = URL(fileURLWithPath: String(result.components(separatedBy: "Backup: ").last!))
        XCTAssertEqual(try FileManager.default.destinationOfSymbolicLink(atPath: backup.path), source.path)
        XCTAssertEqual(try String(contentsOf: source.appendingPathComponent("SKILL.md")), "My development source")
        XCTAssertEqual(installer.status(skill(), target: .agents).state, .notInstalled)
        let newRoot = installer.installationRoot(skill(), target: .agents)
        _ = try installer.install(skill(), files: files(), root: newRoot)
        XCTAssertEqual(installer.status(skill(), target: .agents).state, .installed)
        XCTAssertEqual(try String(contentsOf: source.appendingPathComponent("SKILL.md")), "My development source")
    }
    func testBrokenRelativeLinkCanBeRemovedWithoutReadingTarget() throws {
        let installer = SupplementalSkillInstaller(home: temporary)
        let root = LocalSkillTarget.agents.root(home: temporary)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let link = root.appendingPathComponent("test-skill")
        try FileManager.default.createSymbolicLink(atPath: link.path, withDestinationPath: "../../missing-source")
        XCTAssertEqual(installer.status(skill(), target: .agents).state, .linked)
        _ = try installer.remove(skill(), root: root, preserveExisting: true)
        XCTAssertEqual(installer.status(skill(), target: .agents).state, .notInstalled)
    }
    func testConfirmedLinkedUpdateBacksUpLinkWithoutChangingSource() throws {
        let installer = SupplementalSkillInstaller(home: temporary)
        let source = temporary.appendingPathComponent("development")
        try FileManager.default.createDirectory(at: source, withIntermediateDirectories: true)
        try Data("Development edits".utf8).write(to: source.appendingPathComponent("SKILL.md"))
        let root = temporary.appendingPathComponent(".codex/skills")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let destination = root.appendingPathComponent("test-skill")
        try FileManager.default.createSymbolicLink(atPath: destination.path, withDestinationPath: "../../development")
        XCTAssertThrowsError(try installer.install(skill(), files: files(), root: root, replace: true))
        XCTAssertEqual(try FileManager.default.destinationOfSymbolicLink(atPath: destination.path), "../../development")
        let result = try installer.install(skill(), files: files("Catalog version"), root: root, replace: true, replaceLink: true)
        let backup = String(result.components(separatedBy: "Backup: ").last!)
        XCTAssertEqual(try FileManager.default.destinationOfSymbolicLink(atPath: backup), "../../development")
        XCTAssertEqual(installer.status(skill(), target: .agents).state, .installed)
        XCTAssertEqual(try String(contentsOf: source.appendingPathComponent("SKILL.md")), "Development edits")
        XCTAssertEqual(try ProjectFiles.read(destination), files("Catalog version"))
    }
    func testInterruptedLinkedUpdateRestoresLiteralLink() throws {
        let installer = SupplementalSkillInstaller(home: temporary)
        let root = LocalSkillTarget.agents.root(home: temporary)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let destination = root.appendingPathComponent("test-skill")
        let literal = "../../development"
        let backup = root.deletingLastPathComponent().appendingPathComponent("glyphs-mcp-skill-backups/catalog/link-recovery/test-skill")
        try FileManager.default.createDirectory(at: backup.deletingLastPathComponent(), withIntermediateDirectories: true)
        try FileManager.default.createSymbolicLink(atPath: backup.path, withDestinationPath: literal)
        try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: true)
        try files("Interrupted")[0].data!.write(to: destination.appendingPathComponent("SKILL.md"))
        let next = try JSONSerialization.jsonObject(with: JSONEncoder().encode(["test-skill": SupplementalSkillReceipt(skill: skill(), contentSHA256: SupplementalSkillInstaller.hash(files("Interrupted")))]))
        let journal: [String: Any] = ["name": "test-skill", "newHash": SupplementalSkillInstaller.hash(files("Interrupted")),
                                     "oldHash": TemplateStore.checksum(Data(("symbolic-link\0" + literal).utf8)),
                                     "backup": backup.path, "previous": [:], "next": next]
        try JSONSerialization.data(withJSONObject: journal).write(to: root.appendingPathComponent(".glyphs-mcp-catalog-transaction.json"))
        try installer.recover(root: root)
        XCTAssertEqual(try FileManager.default.destinationOfSymbolicLink(atPath: destination.path), literal)
        XCTAssertEqual(installer.status(skill(), target: .agents).state, .linked)
    }
    func testExistingPersonalCopyDoesNotBlockIndependentAgentOrProject() throws {
        let installer = SupplementalSkillInstaller(home: temporary)
        let legacy = temporary.appendingPathComponent(".codex/skills/test-skill")
        try FileManager.default.createDirectory(at: legacy, withIntermediateDirectories: true)
        try files()[0].data!.write(to: legacy.appendingPathComponent("SKILL.md"))
        _ = try installer.install(skill(), files: files(), root: LocalSkillTarget.claudeCode.root(home: temporary))
        let project = temporary.appendingPathComponent("Project")
        _ = try installer.install(skill(), files: files(), root: LocalSkillTarget.agents.root(home: temporary, project: project), project: project)
        XCTAssertEqual(installer.status(skill(), target: .agents, project: project).state, .installed)
        XCTAssertEqual(try Data(contentsOf: legacy.appendingPathComponent("SKILL.md")), files()[0].data)
    }
    func testSeparateManagedCopiesAndProjectRoots() throws {
        let installer = SupplementalSkillInstaller(home: temporary)
        let shared = LocalSkillTarget.agents.root(home: temporary)
        let claude = LocalSkillTarget.claudeCode.root(home: temporary)
        _ = try installer.install(skill(), files: files(), root: shared)
        _ = try installer.install(skill(), files: files(), root: claude)
        let project = temporary.appendingPathComponent("font-project")
        let projectRoot = LocalSkillTarget.agents.root(home: temporary, project: project)
        _ = try installer.install(skill(), files: files(), root: projectRoot, project: project)
        XCTAssertEqual(installer.status(skill(), root: projectRoot).state, .installed)
        XCTAssertFalse(FileManager.default.fileExists(atPath: project.appendingPathComponent(".git").path))
    }
    func testNavigationDestinationsPreserveLastProject() throws {
        let suite = "SkillNavigation-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        var navigation = DesktopProjectNavigation(defaults: defaults, hasInstallation: true)
        navigation.select(.project("/Fonts/Example"))
        for destination in [DesktopDestination.companions, .agents, .skills, .setup] {
            navigation.select(destination)
            XCTAssertEqual(navigation.destination, destination)
            XCTAssertEqual(navigation.lastProject, "/Fonts/Example")
            XCTAssertEqual(navigation.recent, ["/Fonts/Example"])
        }
    }
    func testInterruptedInstallRestoresOriginalBeforeFurtherWrites() throws {
        let installer = SupplementalSkillInstaller(home: temporary)
        let root = LocalSkillTarget.agents.root(home: temporary)
        _ = try installer.install(skill(), files: files(), root: root)
        let ledger = try Data(contentsOf: root.appendingPathComponent(".glyphs-mcp-catalog-skills.json"))
        let previous = try JSONSerialization.jsonObject(with: ledger)
        let destination = root.appendingPathComponent("test-skill")
        let backup = root.deletingLastPathComponent().appendingPathComponent("glyphs-mcp-skill-backups/catalog/recovery/test-skill")
        try FileManager.default.createDirectory(at: backup.deletingLastPathComponent(), withIntermediateDirectories: true)
        try FileManager.default.copyItem(at: destination, to: backup)
        let oldHash = SupplementalSkillInstaller.hash(files())
        try files("Interrupted")[0].data!.write(to: destination.appendingPathComponent("SKILL.md"))
        let journal: [String: Any] = ["name": "test-skill", "newHash": SupplementalSkillInstaller.hash(files("Interrupted")), "oldHash": oldHash,
                                     "backup": backup.path, "previous": previous, "next": [:]]
        try JSONSerialization.data(withJSONObject: journal).write(to: root.appendingPathComponent(".glyphs-mcp-catalog-transaction.json"))
        try installer.recover(root: root)
        XCTAssertEqual(try ProjectFiles.read(destination), files())
        XCTAssertEqual(installer.status(skill(), root: root).state, .installed)
    }
    func testInterruptedInstallWithLaterEditsFailsClosed() throws {
        let installer = SupplementalSkillInstaller(home: temporary)
        let root = LocalSkillTarget.agents.root(home: temporary)
        _ = try installer.install(skill(), files: files(), root: root)
        let previous = try JSONSerialization.jsonObject(with: Data(contentsOf: root.appendingPathComponent(".glyphs-mcp-catalog-skills.json")))
        let journal: [String: Any] = ["name":"test-skill", "newHash":SupplementalSkillInstaller.hash(files("New")), "oldHash":SupplementalSkillInstaller.hash(files()), "previous":previous, "next":[:]]
        try JSONSerialization.data(withJSONObject: journal).write(to: root.appendingPathComponent(".glyphs-mcp-catalog-transaction.json"))
        try Data("Later user edits".utf8).write(to: root.appendingPathComponent("test-skill/SKILL.md"))
        XCTAssertThrowsError(try installer.recover(root: root))
        XCTAssertEqual(try String(contentsOf: root.appendingPathComponent("test-skill/SKILL.md")), "Later user edits")
    }
}

private final class CatalogURLProtocol: URLProtocol {
    static var response: ((URLRequest) throws -> (Int, Data))?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        do {
            guard let handler = Self.response, let url = request.url else { throw ProjectError("Unexpected fixture request") }
            let (status, data) = try handler(request)
            let response = HTTPURLResponse(url: url, statusCode: status, httpVersion: "HTTP/1.1", headerFields: ["Content-Length": String(data.count)])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() {}
}

extension SkillCatalogTests {
    private func store() -> SkillStore {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CatalogURLProtocol.self]
        return SkillStore(root: temporary.appendingPathComponent("cache"), session: URLSession(configuration: configuration))
    }
    func testOfflineSnapshotAndInvalidRefreshPreserveLastGoodCatalog() async throws {
        let service = store()
        let snapshot = try JSONEncoder().encode(SkillCatalog(skills: [skill()]))
        let offline = try await service.catalog(snapshot: snapshot)
        XCTAssertEqual(offline.skills.first?.source.revision, skill().source.revision)
        CatalogURLProtocol.response = { _ in (200, try JSONEncoder().encode(SkillCatalog(skills: [self.skill("c")]))) }
        _ = try await service.catalog(snapshot: snapshot, refresh: true)
        CatalogURLProtocol.response = { _ in (200, Data("malformed".utf8)) }
        do { _ = try await service.catalog(snapshot: snapshot, refresh: true); XCTFail("Malformed refresh was accepted") } catch {}
        let cached = try await service.catalog(snapshot: snapshot)
        XCTAssertEqual(cached.skills.first?.source.revision, skill("c").source.revision)
        CatalogURLProtocol.response = nil
    }
    func testGitHubDiscoveryResolvesCommitAndValidatesCachedPackage() async throws {
        let repository = temporary.appendingPathComponent("fixture-source")
        let folder = repository.appendingPathComponent("skills/test-skill")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        try files()[0].data!.write(to: folder.appendingPathComponent("SKILL.md"))
        let zip = temporary.appendingPathComponent("source.zip")
        let result = try await ProcessRunner().runCapturing(executable: URL(fileURLWithPath: "/usr/bin/ditto"), args: ["-c", "-k", "--keepParent", repository.path, zip.path], timeout: 30)
        XCTAssertEqual(result.exitCode, 0)
        let archive = try Data(contentsOf: zip)
        CatalogURLProtocol.response = { request in
            let url = request.url!
            if url.host == "api.github.com" && url.path.contains("/commits/") { return (200, Data(("{\"sha\":\"" + String(repeating: "a", count: 40) + "\"}").utf8)) }
            if url.host == "api.github.com" { return (200, Data("{\"private\":false,\"default_branch\":\"main\"}".utf8)) }
            return (200, archive)
        }
        defer { CatalogURLProtocol.response = nil }
        let service = store()
        let found = try await service.discover(repository: "https://github.com/test/skills", directory: "skills")
        XCTAssertEqual(found.count, 1)
        XCTAssertEqual(found.first?.classification, .imported)
        XCTAssertEqual(found.first?.source.directory, "skills/test-skill")
        XCTAssertEqual(found.first?.source.archiveSHA256, TemplateStore.checksum(archive))
        try await service.remember(found[0])
        let imports = try await service.imports()
        XCTAssertEqual(imports, found)
        let downloaded = try await service.files(found[0])
        XCTAssertEqual(downloaded, files())
        var invalid = found[0]; invalid.source.archiveSHA256 = String(repeating: "f", count: 64)
        do { _ = try await service.files(invalid); XCTFail("A mismatched archive was accepted") } catch {}
    }
    func testGitHubPrivateMissingAndRateLimitedSourcesFailWithoutImporting() async throws {
        let service = store()
        for response in [(200, Data("{\"private\":true}".utf8)), (404, Data()), (429, Data())] {
            CatalogURLProtocol.response = { _ in response }
            do { _ = try await service.discover(repository: "https://github.com/test/skills"); XCTFail("Unavailable source was accepted") } catch {}
        }
        CatalogURLProtocol.response = nil
        let imports = try await service.imports()
        XCTAssertTrue(imports.isEmpty)
    }
    func testRecoveryWithoutJournalDoesNotWriteIntoDiscoveryRoot() throws {
        let root = temporary.appendingPathComponent("existing-skills")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        try SupplementalSkillInstaller(home: temporary).recover(root: root)
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: root.path), [])
    }
}
