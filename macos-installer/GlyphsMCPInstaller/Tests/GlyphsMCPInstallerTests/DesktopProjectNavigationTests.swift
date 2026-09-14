import XCTest
@testable import GlyphsMCPInstallerCore

final class DesktopProjectNavigationTests: XCTestCase {
    private func defaults() -> UserDefaults {
        let name = "project-navigation-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: name)!
        addTeardownBlock { defaults.removePersistentDomain(forName: name) }
        return defaults
    }

    func testExistingRecentsAreAdoptedAndLastSelectionSurvivesRelaunch() {
        let preferences = defaults()
        preferences.set(["/Fonts/Alpha", "/Fonts/Beta"], forKey: "recentProjects")
        preferences.set("preserved", forKey: "unrelated")
        var state = DesktopProjectNavigation(defaults: preferences, hasInstallation: true)
        XCTAssertEqual(state.selectedProject, "/Fonts/Alpha")
        state.select(.project("/Fonts/Beta")); state.save(to: preferences)
        let reopened = DesktopProjectNavigation(defaults: preferences, hasInstallation: true)
        XCTAssertEqual(reopened.selectedProject, "/Fonts/Beta")
        XCTAssertEqual(reopened.recent, ["/Fonts/Beta", "/Fonts/Alpha"])
        XCTAssertEqual(preferences.string(forKey: "unrelated"), "preserved")
    }

    func testTemplatesHeaderIsExplicitAndDoesNotClearRememberedProject() {
        let preferences = defaults()
        var state = DesktopProjectNavigation(defaults: preferences, hasInstallation: true)
        state.select(.project("/Fonts/Alpha"))
        state.select(.templates); state.save(to: preferences)
        XCTAssertEqual(state.destination, .templates)
        XCTAssertNil(state.selectedProject)
        XCTAssertEqual(state.lastProject, "/Fonts/Alpha")
        XCTAssertEqual(DesktopProjectNavigation(defaults: preferences, hasInstallation: true).selectedProject, "/Fonts/Alpha")
        state.select(.overview)
        XCTAssertNil(state.selectedProject)
        state.select(nil)
        XCTAssertEqual(state.selectedProject, "/Fonts/Alpha")
    }

    func testNoSelectionShowsTemplatesWithoutInventingAProject() {
        var state = DesktopProjectNavigation(defaults: defaults(), hasInstallation: true)
        state.select(nil)
        XCTAssertEqual(state.destination, .templates)
        XCTAssertTrue(state.recent.isEmpty)
    }

    func testFirstInstallationStillOpensComponents() {
        let preferences = defaults()
        preferences.set(["/Fonts/Alpha"], forKey: "recentProjects")
        let state = DesktopProjectNavigation(defaults: preferences, hasInstallation: false)
        XCTAssertEqual(state.destination, .components)
        XCTAssertEqual(state.lastProject, "/Fonts/Alpha")
    }

    func testProjectIdentityUsesFullPathAndRetainsUnavailableFolders() {
        let preferences = defaults()
        preferences.set(["/One/Font", "/Two/Font", "/One/./Font", "not-a-path"], forKey: "recentProjects")
        preferences.set("/forgotten", forKey: "lastSelectedProject")
        var state = DesktopProjectNavigation(defaults: preferences, hasInstallation: true)
        XCTAssertEqual(state.recent, ["/One/Font", "/Two/Font"])
        state.select(.project("/Two/Font"))
        XCTAssertEqual(state.selectedProject, "/Two/Font")
        for index in 0..<20 { state.select(.project("/Fonts/\(index)")) }
        XCTAssertEqual(state.recent.count, 12)
        XCTAssertEqual(state.recent.first, "/Fonts/19")
    }

    func testRemovingSelectedProjectUsesNextProjectThenGalleryAndPersists() {
        let preferences = defaults()
        var state = DesktopProjectNavigation(defaults: preferences, hasInstallation: true)
        state.select(.project("/Fonts/Alpha")); state.select(.project("/Fonts/Beta"))
        state.remove("/Fonts/Beta")
        XCTAssertEqual(state.selectedProject, "/Fonts/Alpha")
        state.remove("/Fonts/Alpha"); state.save(to: preferences)
        XCTAssertEqual(state.destination, .templates)
        XCTAssertNil(state.lastProject)
        let removed = state
        state.remove("/Fonts/Alpha")
        XCTAssertEqual(state, removed)
        let reopened = DesktopProjectNavigation(defaults: preferences, hasInstallation: true)
        XCTAssertTrue(reopened.recent.isEmpty)
        XCTAssertNil(reopened.lastProject)
    }

    func testRemovingOtherProjectAndRememberedProjectKeepsCurrentDestination() {
        var state = DesktopProjectNavigation(defaults: defaults(), hasInstallation: true)
        state.select(.project("/Fonts/Alpha")); state.select(.project("/Fonts/Beta"))
        state.remove("/Fonts/Alpha")
        XCTAssertEqual(state.selectedProject, "/Fonts/Beta")
        state.select(.templates); state.remove("/Fonts/Beta")
        XCTAssertEqual(state.destination, .templates)
        XCTAssertNil(state.lastProject)
    }

    func testDisplayNameSurvivesRelaunchAndDoesNotRenameOrRemoveFiles() throws {
        let preferences = defaults(), folder = try temporaryFolder()
        let source = folder.appendingPathComponent("font.glyphs")
        let bytes = Data("untouched source".utf8); try bytes.write(to: source)
        var state = DesktopProjectNavigation(defaults: preferences, hasInstallation: true)
        state.select(.project(folder.path))
        try state.update(folder.path, name: "  Display name  ", folder: folder)
        state.save(to: preferences)
        XCTAssertEqual(state.name(for: folder.path), "Display name")
        XCTAssertEqual(DesktopProjectNavigation(defaults: preferences, hasInstallation: true), state)
        state.remove(folder.path); state.save(to: preferences)
        XCTAssertEqual(state.name(for: folder.path), folder.lastPathComponent)
        XCTAssertTrue((preferences.dictionary(forKey: "projectDisplayNames") ?? [:]).isEmpty)
        XCTAssertEqual(try Data(contentsOf: source), bytes)
    }

    func testReconnectingFolderPreservesOrderAndCurrentSelection() throws {
        let preferences = defaults(), folder = try temporaryFolder()
        var state = DesktopProjectNavigation(defaults: preferences, hasInstallation: true)
        state.select(.project("/Fonts/Other")); state.select(.project("/Fonts/Moved"))
        try state.update("/Fonts/Moved", name: "Font Family", folder: folder)
        XCTAssertEqual(state.recent, [folder.path, "/Fonts/Other"])
        XCTAssertEqual(state.selectedProject, folder.path)
        XCTAssertEqual(state.lastProject, folder.path)
        state.save(to: preferences)
        XCTAssertEqual(DesktopProjectNavigation(defaults: preferences, hasInstallation: true), state)
        state.select(.components)
        try state.update("/Fonts/Other", name: "Other Family", folder: URL(fileURLWithPath: "/Fonts/Other"))
        XCTAssertEqual(state.destination, .components)
        XCTAssertEqual(state.lastProject, folder.path)
    }

    func testInvalidSettingsLeaveAllStateUntouched() throws {
        let folder = try temporaryFolder(), file = folder.appendingPathComponent("file")
        try Data().write(to: file)
        var state = DesktopProjectNavigation(defaults: defaults(), hasInstallation: true)
        state.select(.project("/Fonts/One")); state.select(.project(folder.path))
        let before = state
        for (path, name, target) in [
            ("/Fonts/One", " ", folder),
            ("/Fonts/One", "Name", folder),
            ("/Fonts/One", "Name", file),
            ("/Fonts/One", "Name", folder.appendingPathComponent("missing")),
            ("/Fonts/One", "Name", URL(string: "https://example.com/font")!),
            ("/forgotten", "Name", folder)
        ] {
            XCTAssertThrowsError(try state.update(path, name: name, folder: target))
            XCTAssertEqual(state, before)
        }
    }

    func testCancelledEditDraftHasNoEffectAndUnrelatedPreferencesSurviveSave() throws {
        let preferences = defaults()
        preferences.set("keep", forKey: "unrelated")
        var state = DesktopProjectNavigation(defaults: preferences, hasInstallation: true)
        state.select(.project("/Fonts/Alpha"))
        var draft = state
        try draft.update("/Fonts/Alpha", name: "Draft name", folder: URL(fileURLWithPath: "/Fonts/Alpha"))
        XCTAssertEqual(state.name(for: "/Fonts/Alpha"), "Alpha")
        state.save(to: preferences)
        XCTAssertEqual(preferences.string(forKey: "unrelated"), "keep")
        XCTAssertEqual(DesktopProjectNavigation(defaults: preferences, hasInstallation: true).name(for: "/Fonts/Alpha"), "Alpha")
    }

    func testNamesOfEvictedProjectsAreNotRetained() throws {
        let preferences = defaults()
        var state = DesktopProjectNavigation(defaults: preferences, hasInstallation: true)
        state.select(.project("/Fonts/Alpha"))
        try state.update("/Fonts/Alpha", name: "Custom", folder: URL(fileURLWithPath: "/Fonts/Alpha"))
        for index in 0..<12 { state.select(.project("/Fonts/\(index)")) }
        state.save(to: preferences)
        XCTAssertEqual(state.name(for: "/Fonts/Alpha"), "Alpha")
        XCTAssertTrue((preferences.dictionary(forKey: "projectDisplayNames") ?? [:]).isEmpty)
    }

    private func temporaryFolder() throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString).standardizedFileURL
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: false)
        addTeardownBlock { try? FileManager.default.removeItem(at: url) }
        return url
    }
}
