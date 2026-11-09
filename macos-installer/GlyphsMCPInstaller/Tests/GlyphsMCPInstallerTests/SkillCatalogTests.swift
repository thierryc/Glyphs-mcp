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
    private func canonicalSkill(bundled: Bool) -> CatalogSkill {
        .init(id: "builtin:glyphs-mcp-path-doctor", name: "glyphs-mcp-path-doctor",
              description: "Diagnose paths and qualify explicit repairs", author: "Glyphs MCP contributors",
              license: "Apache-2.0", classification: .curated,
              source: .init(repository: "https://github.com/thierryc/Glyphs-mcp",
                            directory: "skills/glyphs-mcp-path-doctor", revision: String(repeating: "a", count: 40),
                            archiveSHA256: bundled ? nil : String(repeating: "b", count: 64)),
              compatibleClients: [.codex], requirements: [], bundled: bundled)
    }
    func testVersionVerificationDistinguishesCurrentOutdatedAndEditedCopies() throws {
        let installer = SupplementalSkillInstaller(home: temporary)
        var item = skill()
        item.version = "1"
        let original = SkillPackageVersion(label: item.version, files: files())
        let initial = installer.scopeStatus(item)
        let target = initial.missing(for: [.codex])
        XCTAssertTrue(installer.apply(.install, to: target, skill: item, files: files(), package: original).failures.isEmpty)

        let current = try XCTUnwrap(installer.scopeStatus(item, package: original).installed(for: .codex).first)
        XCTAssertEqual(current.status.matchesPackage, true)
        XCTAssertEqual(current.status.availableVersion, "1")
        let unversioned = try XCTUnwrap(installer.scopeStatus(item, package: .init(label: nil, files: files()))
            .installed(for: .codex).first)
        XCTAssertEqual(unversioned.status.matchesPackage, true)
        XCTAssertNil(unversioned.status.availableVersion)
        XCTAssertEqual(installer.apply(.reinstall, to: [current], skill: item, files: files(), package: original).completed.count, 1)

        var updated = skill("c")
        updated.version = "1.1.1"
        let newFiles = files("Updated")
        let latest = SkillPackageVersion(label: updated.version, files: newFiles)
        let outdated = try XCTUnwrap(installer.scopeStatus(updated, package: latest).installed(for: .codex).first)
        XCTAssertEqual(outdated.status.state, .updateAvailable)
        XCTAssertEqual(outdated.status.matchesPackage, false)
        XCTAssertEqual(outdated.status.installedVersion, original.label)
        XCTAssertEqual(outdated.status.availableVersion, latest.label)

        let file = URL(fileURLWithPath: current.status.path).appendingPathComponent("SKILL.md")
        try XCTUnwrap(files("Local changes").first?.data).write(to: file)
        let edited = try XCTUnwrap(installer.scopeStatus(updated, package: latest).installed(for: .codex).first)
        XCTAssertEqual(edited.status.state, .modified)
        XCTAssertEqual(edited.status.matchesPackage, false)
    }

    func testLinkedFolderIgnoresPythonCachesButDetectsSourceEdits() throws {
        let installer = SupplementalSkillInstaller(home: temporary)
        let item = skill()
        let script = Data("print('original')".utf8)
        let authored = files() + [
            ProjectFile(path: "scripts", data: nil),
            ProjectFile(path: "scripts/tool.py", data: script)
        ]
        let version = SkillPackageVersion(label: "1.0", files: authored)
        let source = temporary.appendingPathComponent("source", isDirectory: true)
        let root = temporary.appendingPathComponent(SkillPlacement.shared.rawValue, isDirectory: true)
        try FileManager.default.createDirectory(at: source, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let file = source.appendingPathComponent("SKILL.md")
        try XCTUnwrap(files().first?.data).write(to: file)
        let cache = source.appendingPathComponent("scripts/__pycache__", isDirectory: true)
        try FileManager.default.createDirectory(at: cache, withIntermediateDirectories: true)
        let sourceScript = source.appendingPathComponent("scripts/tool.py")
        try script.write(to: sourceScript)
        try Data([1]).write(to: cache.appendingPathComponent("tool.cpython-314.pyc"))
        try Data([2]).write(to: source.appendingPathComponent("scripts/tool.pyc"))
        try Data([3]).write(to: source.appendingPathComponent("scripts/tool.pyo"))
        let link = root.appendingPathComponent(item.name)
        try FileManager.default.createSymbolicLink(at: link, withDestinationURL: source)

        let current = try XCTUnwrap(installer.scopeStatus(item, package: version).installed(for: .codex).first)
        XCTAssertEqual(current.status.state, .linked)
        XCTAssertEqual(current.status.matchesPackage, true)
        XCTAssertEqual(current.status.availableVersion, version.label)
        XCTAssertEqual(installer.apply(.reinstall, to: [current], skill: item, files: authored).failures.count, 1)
        XCTAssertTrue(FileManager.default.fileExists(atPath: cache.appendingPathComponent("tool.cpython-314.pyc").path))
        try Data("print('changed')".utf8).write(to: sourceScript)
        let edited = try XCTUnwrap(installer.scopeStatus(item, package: version).installed(for: .codex).first)
        XCTAssertEqual(edited.status.state, .linked)
        XCTAssertEqual(edited.status.matchesPackage, false)
        XCTAssertEqual(try FileManager.default.destinationOfSymbolicLink(atPath: link.path), source.path)
    }

    func testProjectInstallCoversEveryLocalAgentAndKeepsGlobalCopy() throws {
        let installer = SupplementalSkillInstaller(home: temporary)
        let item = skill()
        let project = temporary.appendingPathComponent("project", isDirectory: true)
        try FileManager.default.createDirectory(at: project, withIntermediateDirectories: true)

        let global = installer.scopeStatus(item)
        let codex = global.missing(for: [.codex])
        XCTAssertEqual(codex.map(\.placement), [.shared])
        XCTAssertTrue(installer.apply(.install, to: codex, skill: item, files: files()).failures.isEmpty)

        let before = installer.scopeStatus(item, project: project)
        let targets = before.missing(for: before.agents)
        XCTAssertEqual(targets.map(\.placement), [.shared, .claudeCode])
        let result = installer.apply(.install, to: targets, skill: item, files: files(), project: project)
        XCTAssertEqual(result.completed.count, 2)
        XCTAssertTrue(result.failures.isEmpty)
        let after = installer.scopeStatus(item, project: project)
        XCTAssertTrue(after.missing(for: after.agents).isEmpty)
        XCTAssertEqual(after.installed(for: .cursor).map(\.placement), [.shared, .claudeCode])

        let copies = after.copies.filter { $0.status.isInstalled }
        let removed = installer.apply(.remove, to: copies, skill: item, files: [], project: project)
        XCTAssertEqual(removed.completed.count, 2)
        XCTAssertTrue(removed.failures.isEmpty)
        XCTAssertTrue(installer.scopeStatus(item, project: project).installed(for: .codex).isEmpty)
        XCTAssertEqual(installer.scopeStatus(item).installed(for: .codex).map(\.placement), [.shared])
    }

    func testAgentInstallReusesLegacyAndPluginLocations() throws {
        let installer = SupplementalSkillInstaller(home: temporary)
        let item = skill()
        let initial = installer.scopeStatus(item)
        XCTAssertEqual(initial.missing(for: [.cursor]).map(\.placement), [.cursor])
        for placement in [SkillPlacement.codex, .cursorPlugin] {
            let folder = temporary.appendingPathComponent(placement.rawValue).appendingPathComponent(item.name)
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            try XCTUnwrap(files().first?.data).write(to: folder.appendingPathComponent("SKILL.md"))
        }
        let scope = installer.scopeStatus(item)
        XCTAssertEqual(scope.installed(for: .codex).map(\.placement), [.codex])
        XCTAssertEqual(scope.installed(for: .cursor).map(\.placement), [.codex, .cursorPlugin])
        XCTAssertEqual(scope.missing(for: scope.agents).map(\.placement), [.claudeCode])
        let plugin = try XCTUnwrap(scope.installed(for: .cursor).last)
        XCTAssertEqual(installer.apply(.remove, to: [plugin], skill: item, files: [], replace: true).failures.count, 1)
        XCTAssertTrue(FileManager.default.fileExists(atPath: plugin.status.path))
    }

    func testDefaultAndTwoProjectCopiesCanBeUpdatedAndRemovedIndependently() throws {
        let installer = SupplementalSkillInstaller(home: temporary)
        let item = skill()
        let first = temporary.appendingPathComponent("first", isDirectory: true)
        let second = temporary.appendingPathComponent("second", isDirectory: true)
        for project in [first, second] {
            try FileManager.default.createDirectory(at: project, withIntermediateDirectories: true)
        }
        for scope in [nil, first, second] {
            let status = installer.scopeStatus(item, project: scope)
            let installed = installer.apply(.install, to: status.missing(for: status.agents),
                                            skill: item, files: files(), project: scope)
            XCTAssertEqual(installed.completed.count, 2)
            XCTAssertTrue(installed.failures.isEmpty)
        }
        let next = skill("c")
        let updated = installer.apply(.update, to: installer.scopeStatus(next, project: first).editableCopies,
                                      skill: next, files: files("New"), project: first)
        XCTAssertEqual(updated.completed.count, 2)
        XCTAssertTrue(updated.failures.isEmpty)
        XCTAssertTrue(installer.scopeStatus(next, project: first).editableCopies.allSatisfy { $0.status.state == .installed })

        let defaults = installer.scopeStatus(next).editableCopies
        XCTAssertTrue(defaults.allSatisfy { $0.status.state == .updateAvailable })
        let updatedDefaults = installer.apply(.update, to: defaults, skill: next, files: files("New"))
        XCTAssertEqual(updatedDefaults.completed.count, 2)
        XCTAssertTrue(updatedDefaults.failures.isEmpty)
        XCTAssertTrue(installer.scopeStatus(next, project: second).editableCopies.allSatisfy { $0.status.state == .updateAvailable })

        let defaultCopies = installer.scopeStatus(next).editableCopies
        XCTAssertTrue(installer.scopeStatus(item, project: temporary).editableCopies.isEmpty)
        XCTAssertFalse(installer.apply(.remove, to: defaultCopies, skill: next, files: [], project: temporary).failures.isEmpty)
        let removed = installer.apply(.remove, to: defaultCopies, skill: next, files: [])
        XCTAssertEqual(removed.completed.count, 2)
        XCTAssertTrue(removed.failures.isEmpty)
        XCTAssertTrue(installer.scopeStatus(next).editableCopies.isEmpty)
        XCTAssertEqual(installer.scopeStatus(next, project: first).editableCopies.count, 2)
        XCTAssertEqual(installer.scopeStatus(item, project: second).editableCopies.count, 2)
    }

    func testAgentManagementListsEachCopyUnderItsOwner() throws {
        let installer = SupplementalSkillInstaller(home: temporary)
        let item = skill()
        func createCopy(_ placement: SkillPlacement) throws {
            let folder = temporary.appendingPathComponent(placement.rawValue).appendingPathComponent(item.name)
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            try XCTUnwrap(files().first?.data).write(to: folder.appendingPathComponent("SKILL.md"))
        }
        try createCopy(.codex)
        try createCopy(.claudeCode)

        let inherited = installer.scopeStatus(item)
        XCTAssertEqual(inherited.installed(for: .cursor).map(\.placement), [.codex, .claudeCode])
        XCTAssertTrue(inherited.managedCopies(for: .cursor).isEmpty)
        XCTAssertTrue(inherited.missing(for: [.cursor]).isEmpty)

        try createCopy(.cursorPlugin)
        let withPlugin = installer.scopeStatus(item)
        XCTAssertEqual(withPlugin.editableCopies.map(\.placement), [.codex, .claudeCode])
        XCTAssertEqual(withPlugin.managedCopies(for: .codex).map(\.placement), [.codex])
        XCTAssertEqual(withPlugin.managedCopies(for: .claudeCode).map(\.placement), [.claudeCode])
        XCTAssertEqual(withPlugin.managedCopies(for: .cursor).map(\.placement), [.cursorPlugin])
        XCTAssertTrue(try XCTUnwrap(withPlugin.managedCopies(for: .cursor).first).status.path
            .hasSuffix(".cursor/plugins/local/glyphs-mcp/skills/test-skill"))
    }

    func testCursorInstallAndUpdateRemainAvailableWithAnInheritedCodexCopy() throws {
        let installer = SupplementalSkillInstaller(home: temporary)
        var item = skill()
        item.testedClients = [.codex]
        let initial = installer.scopeStatus(item)
        let codex = try XCTUnwrap(initial.installTarget(for: .codex))
        XCTAssertEqual(installer.apply(.install, to: [codex], skill: item, files: files(), forAgent: .codex).completed.count, 1)

        let shared = installer.scopeStatus(item)
        XCTAssertEqual(shared.installed(for: .cursor).map(\.placement), [.shared])
        XCTAssertTrue(shared.missing(for: [.cursor]).isEmpty)
        let cursor = try XCTUnwrap(shared.installTarget(for: .cursor))
        XCTAssertEqual(cursor.placement, .cursor)
        XCTAssertEqual(installer.apply(.install, to: [cursor], skill: item, files: files(), forAgent: .cursor).completed.count, 1)
        XCTAssertNil(installer.scopeStatus(item).installTarget(for: .cursor))

        let next = skill("c")
        let cursorCopy = try XCTUnwrap(installer.scopeStatus(next).managedCopies(for: .cursor).first)
        XCTAssertEqual(cursorCopy.status.state, .updateAvailable)
        XCTAssertEqual(installer.apply(.update, to: [cursorCopy], skill: next, files: files("New")).completed.count, 1)
        let updated = try XCTUnwrap(installer.scopeStatus(next).managedCopies(for: .cursor).first)
        XCTAssertEqual(updated.status.state, .installed)
        XCTAssertEqual(installer.apply(.remove, to: [updated], skill: next, files: []).completed.count, 1)
        XCTAssertEqual(installer.scopeStatus(item).managedCopies(for: .codex).map(\.placement), [.shared])
    }

    func testProjectInstallCanRetryOnlyMissingDestinations() throws {
        let installer = SupplementalSkillInstaller(home: temporary)
        let item = skill()
        let project = temporary.appendingPathComponent("project", isDirectory: true)
        try FileManager.default.createDirectory(at: project, withIntermediateDirectories: true)
        let blocked = project.appendingPathComponent(".claude")
        try FileManager.default.createSymbolicLink(at: blocked, withDestinationURL: temporary)
        let initial = installer.scopeStatus(item, project: project)
        let partial = installer.apply(.install, to: initial.missing(for: initial.agents),
                                      skill: item, files: files(), project: project)
        XCTAssertEqual(partial.completed.count, 1)
        XCTAssertEqual(partial.failures.count, 1)
        XCTAssertFalse(FileManager.default.fileExists(atPath: temporary.appendingPathComponent("skills").path))

        try FileManager.default.removeItem(at: blocked)
        let current = installer.scopeStatus(item, project: project)
        let missing = current.missing(for: current.agents)
        XCTAssertEqual(missing.map(\.placement), [.claudeCode])
        let retried = installer.apply(.install, to: missing, skill: item, files: files(), project: project)
        XCTAssertEqual(retried.completed.count, 1)
        XCTAssertTrue(retried.failures.isEmpty)
    }

    func testBundledLegacyRemovalSurvivesSetupAndExplicitReinstall() throws {
        let item = canonicalSkill(bundled: true)
        let package = [ProjectFile(path: "SKILL.md", data: Data(
            "---\nname: \(item.name)\ndescription: A focused workflow\n---\nInspect outlines.".utf8))]
        let source = temporary.appendingPathComponent("payload-skills", isDirectory: true)
        let bundled = source.appendingPathComponent(item.name, isDirectory: true)
        try FileManager.default.createDirectory(at: bundled, withIntermediateDirectories: true)
        try XCTUnwrap(package.first?.data).write(to: bundled.appendingPathComponent("SKILL.md"))
        try JSONSerialization.data(withJSONObject: ["schemaVersion": 1, "managedSkills": [
            ["name": item.name, "surface": "glyphs-mcp-v2"]
        ]]).write(to: source.appendingPathComponent("manifest.json"))
        let payload = InstallerPayload(payloadDir: temporary, pluginBundle: temporary, requirementsTxt: temporary, skillsDir: source)
        let root = temporary.appendingPathComponent(".codex/skills", isDirectory: true)
        let setup = AgentSkillBundleInstaller(log: { _ in })
        let direct = SupplementalSkillInstaller(home: temporary, bundledNames: [item.name])

        XCTAssertEqual(try setup.installManagedSkills(from: payload, to: root, clientName: "Codex",
                                                     overwriteExisting: false).entries.first?.outcome, .installed)
        let version = SkillPackageVersion(label: "2.6.0", files: package)
        let oldCopy = try XCTUnwrap(direct.scopeStatus(item, package: version).installed(for: .codex).first)
        XCTAssertEqual(oldCopy.status.state, .installed)
        XCTAssertEqual(oldCopy.status.matchesPackage, true)
        XCTAssertEqual(oldCopy.status.availableVersion, "2.6.0")
        XCTAssertEqual(direct.apply(.remove, to: [oldCopy], skill: item, files: []).completed.count, 1)
        XCTAssertTrue(try setup.installManagedSkills(from: payload, to: root, clientName: "Codex",
                                                     overwriteExisting: true).entries.isEmpty)
        XCTAssertTrue(direct.scopeStatus(item).installed(for: .codex).isEmpty)

        let absent = direct.scopeStatus(item)
        let installed = direct.apply(.install, to: absent.missing(for: [.codex]), skill: item, files: package)
        XCTAssertEqual(installed.completed.count, 1)
        XCTAssertTrue(installed.failures.isEmpty)
        XCTAssertEqual(direct.scopeStatus(item).installed(for: .codex).map(\.placement), [.shared])
        XCTAssertTrue(try setup.installManagedSkills(from: payload, to: root, clientName: "Codex",
                                                     overwriteExisting: false).entries.isEmpty)
    }

    func testRemovalRejectsAChangedCopyAfterConfirmation() throws {
        let installer = SupplementalSkillInstaller(home: temporary)
        let item = skill()
        let initial = installer.scopeStatus(item)
        XCTAssertTrue(installer.apply(.install, to: initial.missing(for: [.codex]), skill: item, files: files()).failures.isEmpty)
        let copy = try XCTUnwrap(installer.scopeStatus(item).installed(for: .codex).first)
        let file = URL(fileURLWithPath: copy.status.path).appendingPathComponent("SKILL.md")
        let changed = try XCTUnwrap(files("New user edit").first?.data)
        try changed.write(to: file)
        XCTAssertEqual(installer.apply(.remove, to: [copy], skill: item, files: [], replace: true).failures.count, 1)
        XCTAssertEqual(try Data(contentsOf: file), changed)
    }

    func testDownloadableCanonicalSkillAppearsBeforeAppIncludesIt() throws {
        let remote = try SkillCatalog.decode(JSONEncoder().encode(SkillCatalog(skills: [canonicalSkill(bundled: false)])))
        let result = try remote.includingBundled(SkillCatalog(skills: []))
        XCTAssertEqual(result.skills.map(\.name), ["glyphs-mcp-path-doctor"])
        XCTAssertFalse(result.skills[0].bundled)
    }
    func testIncludedPayloadWinsAfterDownloadableCanonicalSkillBecomesBundled() throws {
        let included = canonicalSkill(bundled: true)
        var remote = canonicalSkill(bundled: false)
        remote.source.revision = String(repeating: "c", count: 40)
        remote.description = "Changed remote instructions"
        let result = try SkillCatalog(skills: [remote, skill()]).includingBundled(SkillCatalog(skills: [included]))
        XCTAssertEqual(result.skills, [included, skill()])
        remote.source.repository = "https://github.com/thierryc/glyphs-mcp-skills"
        let distributed = try SkillCatalog(skills: [remote]).includingBundled(SkillCatalog(skills: [included]))
        XCTAssertEqual(distributed.skills, [included])
    }
    func testIncludedNamesStillRejectNoncanonicalCollisions() throws {
        let included = canonicalSkill(bundled: true)
        let valid = canonicalSkill(bundled: false)
        var wrongID = valid; wrongID.id = "other/glyphs-mcp-path-doctor"
        var wrongRepository = valid; wrongRepository.source.repository = "https://github.com/other/skills"
        var wrongDirectory = valid; wrongDirectory.source.directory = "other/path-doctor"
        var community = valid; community.classification = .community
        for remote in [wrongID, wrongRepository, wrongDirectory, community] {
            XCTAssertThrowsError(try SkillCatalog(skills: [remote]).includingBundled(SkillCatalog(skills: [included])))
        }
    }
    func testReadableTitlesPreserveLegacyCatalogAndReceiptCompatibility() throws {
        let legacy = skill()
        let decoded = try SkillCatalog.decode(JSONEncoder().encode(SkillCatalog(skills: [legacy])))
        XCTAssertNil(decoded.skills[0].displayName)
        XCTAssertEqual(decoded.skills[0].title, "Test Skill")
        var labeled = legacy; labeled.displayName = "Glyphs Spacing"
        let updated = try SkillCatalog.decode(JSONEncoder().encode(SkillCatalog(skills: [labeled])))
        XCTAssertEqual(updated.skills[0].name, legacy.name)
        XCTAssertEqual(updated.skills[0].title, "Glyphs Spacing")
        let receipt = SupplementalSkillReceipt(skill: legacy, contentSHA256: SupplementalSkillInstaller.hash(files()))
        XCTAssertNil(try JSONDecoder().decode(SupplementalSkillReceipt.self, from: JSONEncoder().encode(receipt)).skill.displayName)
        let merged = try SkillCatalog(skills: [legacy]).includingBundled(SkillCatalog(skills: [labeled]))
        XCTAssertEqual(merged.skills[0].title, "Glyphs Spacing")
        for title in ["", "\n", String(repeating: "x", count: 81), "Glyphs\nSpacing"] {
            labeled.displayName = title
            XCTAssertThrowsError(try SkillCatalog.decode(JSONEncoder().encode(SkillCatalog(skills: [labeled]))))
        }
    }
    func testReviewedMetadataRepairsLegacyCompatibilityOnlyForTheSamePackage() throws {
        var legacy = skill()
        legacy.compatibleClients = [.codex]
        var reviewed = legacy
        reviewed.compatibleClients = [.codex, .cursor, .claudeCode]
        reviewed.testedClients = [.codex]
        reviewed.version = "1.0"
        let snapshot = SkillCatalog(skills: [reviewed])

        let merged = try SkillCatalog(skills: [legacy]).includingBundled(snapshot)
        XCTAssertEqual(merged.skills, [reviewed])
        var newRevision = legacy
        newRevision.source.revision = String(repeating: "d", count: 40)
        XCTAssertEqual(try SkillCatalog(skills: [newRevision]).includingBundled(snapshot).skills, [newRevision])
        var explicit = legacy
        explicit.testedClients = [.codex]
        XCTAssertEqual(try SkillCatalog(skills: [explicit]).includingBundled(snapshot).skills.first?.compatibleClients, [.codex])
    }

    func testCatalogAcceptsIndependentVersionsAndValidatesTestedAgents() throws {
        var entry = skill()
        entry.testedClients = [.codex]
        for version in ["1", "3.2", "3.1.1"] {
            entry.version = version
            let decoded = try SkillCatalog.decode(JSONEncoder().encode(SkillCatalog(skills: [entry])))
            XCTAssertEqual(decoded.skills.first?.version, version)
            XCTAssertEqual(decoded.skills.first?.testedClients, [.codex])
        }
        let feedback = try XCTUnwrap(entry.feedbackURL)
        XCTAssertEqual(feedback.path, "/test/skills/issues/new")
        XCTAssertEqual(URLComponents(url: feedback, resolvingAgainstBaseURL: false)?.queryItems?.first?.value,
                       "Feedback on Test Skill")
        entry.version = "Revision abcd"
        XCTAssertThrowsError(try SkillCatalog.decode(JSONEncoder().encode(SkillCatalog(skills: [entry]))))
        entry.version = "1.0"
        entry.testedClients = [.chatgpt]
        XCTAssertThrowsError(try SkillCatalog.decode(JSONEncoder().encode(SkillCatalog(skills: [entry]))))
    }

    func testImportReadsOptionalUINameWithoutChangingInvocationIdentifier() throws {
        let ui = ProjectFile(path: "agents/openai.yaml", data: Data("interface:\n  display_name: \"Glyphs Project Brief\"\npolicy:\n  allow_implicit_invocation: false\n".utf8))
        XCTAssertEqual(try SkillMetadata.displayName(in: files() + [ui]), "Glyphs Project Brief")
        XCTAssertEqual(try SkillMetadata.validate(files() + [ui]).name, "test-skill")
        XCTAssertNil(try SkillMetadata.displayName(in: files()))
        let invalid = ProjectFile(path: "agents/openai.yaml", data: Data("interface:\n  display_name: !unsafe title\n".utf8))
        XCTAssertThrowsError(try SkillMetadata.displayName(in: [invalid]))
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
