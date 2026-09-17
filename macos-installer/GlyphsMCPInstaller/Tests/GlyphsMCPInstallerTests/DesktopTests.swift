import Foundation
import XCTest
@testable import GlyphsMCPInstallerCore

final class DesktopTests: XCTestCase {
    func testQuitNoticeClearsOnlyWhenGlyphsActuallyCloses() {
        var notice = ComponentNotice.waitingForGlyphs
        notice.glyphsRunningChanged(true)
        XCTAssertEqual(notice, .waitingForGlyphs) // A cancelled save prompt leaves Glyphs open.
        XCTAssertFalse(notice.isFailure)
        notice.glyphsRunningChanged(false)
        XCTAssertEqual(notice, .none)
        notice.glyphsRunningChanged(true)
        XCTAssertEqual(notice, .none) // A later launch must not revive an old waiting message.
    }

    func testAppEventsDoNotEraseInstallationErrorsOrResults() {
        for original in [ComponentNotice.failure("Verification failed"), .information("Components installed")] {
            var notice = original
            notice.glyphsRunningChanged(false)
            XCTAssertEqual(notice, original)
        }
        XCTAssertTrue(ComponentNotice.failure("Failed").isFailure)
        XCTAssertFalse(ComponentNotice.information("Checking…").isFailure)
    }

    func testConnectionFailuresDoNotInventAnAvailableUpdate() {
        for code in [nil, 401, 403, 404, 500, 503] as [Int?] {
            let text = DesktopDiagnostics.statusFailure(code)
            XCTAssertFalse(text.lowercased().contains("update components"))
            XCTAssertEqual(text.contains("authentication"), code == 401 || code == 403)
        }
    }

    func testRunningListenerRemainsVisibleWhenActivityStatusIsUnavailable() throws {
        XCTAssertEqual(DesktopDiagnostics.serverTitle(
            hasServer: true, running: true, status: nil, hasNotice: true
        ), "Server running")
        XCTAssertEqual(DesktopDiagnostics.serverTitle(
            hasServer: true, running: nil, status: nil, hasNotice: true
        ), "Server unavailable")
        XCTAssertEqual(DesktopDiagnostics.serverTitle(
            hasServer: true, running: nil, status: nil, hasNotice: false
        ), "Checking server")
        XCTAssertEqual(DesktopDiagnostics.serverTitle(
            hasServer: true, running: false, status: nil, hasNotice: false
        ), "Server stopped")
        XCTAssertEqual(DesktopDiagnostics.serverTitle(
            hasServer: false, running: true, status: nil, hasNotice: false
        ), "MCP server not installed")

        let status = try JSONDecoder().decode(
            DesktopServerStatus.self,
            from: Data(#"{"sidecarVersion":"2.1.0","bridge":{"reachable":true},"worker":{"available":true},"controlProtocol":1}"#.utf8)
        )
        XCTAssertEqual(DesktopDiagnostics.serverTitle(
            hasServer: true, running: true, status: status, hasNotice: false
        ), "Ready")
    }

    func testControlFeedbackDistinguishesServiceActions() {
        XCTAssertNil(DesktopDiagnostics.controlProgress(nil))
        XCTAssertEqual(DesktopDiagnostics.controlProgress("start"), "Starting…")
        XCTAssertEqual(DesktopDiagnostics.controlProgress("stop"), "Stopping…")
        XCTAssertEqual(DesktopDiagnostics.controlProgress("port"), "Applying…")
    }

    func testStoppedAndUnreachableServersDoNotUseTheReadySymbol() throws {
        let status = try JSONDecoder().decode(DesktopServerStatus.self, from: Data(#"{"sidecarVersion":"2.1.0","bridge":{"reachable":true},"worker":{"available":true},"controlProtocol":1}"#.utf8))
        XCTAssertEqual(DesktopDiagnostics.statusSymbol(running: true, stale: false, status: status), "checkmark.circle.fill")
        XCTAssertEqual(DesktopDiagnostics.statusSymbol(running: false, stale: true, status: status), "stop.circle")
        XCTAssertEqual(DesktopDiagnostics.statusSymbol(running: nil, stale: true, status: status), "exclamationmark.circle")
        XCTAssertEqual(DesktopDiagnostics.statusSymbol(running: nil, stale: false, status: nil), "circle")
    }

    func testComponentCheckboxesCoverEveryInstalledAndSelectedCombination() {
        let ids = DesktopComponent.all.map(\.id)
        func selection(_ mask: Int) -> Set<String> {
            Set(ids.enumerated().filter { mask & (1 << $0.offset) != 0 }.map(\.element))
        }
        for before in 0..<8 {
            for after in 0..<8 {
                let installed = selection(before), selected = selection(after)
                let plan = DesktopComponentPlan(installed: installed, selected: selected)
                var requested = Set<String>(), removed = Set<String>()
                if !plan.arguments.contains("--no-mcp") { requested.insert("mcp") }
                for (index, argument) in plan.arguments.enumerated() {
                    if argument == "--companion" { requested.insert(plan.arguments[index + 1]) }
                    if argument == "--remove" { removed.insert(plan.arguments[index + 1]) }
                }
                // The Python transaction merges requests into the installed
                // set, then applies explicit removals. Check the final result.
                XCTAssertEqual(installed.union(requested).subtracting(removed), selected)
                XCTAssertTrue(removed.isSubset(of: installed))
                XCTAssertTrue(requested.isDisjoint(with: removed))
                XCTAssertEqual(plan.hasWork, !selected.isEmpty || !installed.isEmpty)
            }
        }
    }

    func testComponentChoicesDistinguishFreshInstallFromAnEmptyReceipt() {
        XCTAssertEqual(DesktopComponentPlan.initialSelection(installed: [], hasReceipt: false), DesktopComponent.ids)
        XCTAssertEqual(DesktopComponentPlan.initialSelection(installed: [], hasReceipt: true), [])
        XCTAssertEqual(DesktopComponentPlan.initialSelection(installed: ["curve-inspector"], hasReceipt: false), ["curve-inspector"])
    }

    func testRecheckingAnInstalledComponentCancelsItsRemoval() {
        let installed: Set<String> = ["mcp", "curve-inspector"]
        let removed = DesktopComponentPlan(installed: installed, selected: ["mcp"])
        XCTAssertEqual(removed.removals, ["curve-inspector"])
        XCTAssertEqual(removed.action(for: "curve-inspector"), "Remove")
        let checked = DesktopComponentPlan(installed: installed, selected: installed)
        XCTAssertTrue(checked.removals.isEmpty)
        XCTAssertEqual(checked.action(for: "curve-inspector"), "Install bundled version")
        XCTAssertEqual(checked.action(for: "reference-inspector"), "Not installed")
    }

    func testComponentPlanNeverTargetsUnknownFilesOrComponents() {
        let plan = DesktopComponentPlan(installed: ["unrelated", "mcp"], selected: ["custom-plugin", "curve-inspector"])
        XCTAssertEqual(plan.selected, ["curve-inspector"])
        XCTAssertEqual(plan.removals, ["mcp"])
        XCTAssertFalse(plan.arguments.contains("unrelated"))
        XCTAssertFalse(plan.arguments.contains("custom-plugin"))
    }

    func testBulkSetupQueuesThreeComponentsBeforeAllFourConnectors() {
        let plan = SetupQueuePolicy.bulkPlan(
            installedComponents: ["mcp"],
            installedConnectors: [.codex, .cursor]
        )
        XCTAssertEqual(plan, [
            .component("mcp", .update),
            .component("curve-inspector", .install),
            .component("reference-inspector", .install),
            .connector(.codex, .update),
            .connector(.claudeCode, .install),
            .connector(.claudeDesktop, .install),
            .connector(.cursor, .update),
        ])
    }

    func testSetupItemStateExposesInlineProgressAndRetryOperation() {
        XCTAssertEqual(SetupItemState.queued(.install).statusLabel, "Queued")
        XCTAssertEqual(SetupItemState.active(.update).statusLabel, "Updating…")
        XCTAssertEqual(SetupItemState.failed(.remove, "blocked").operation, .remove)
        XCTAssertEqual(SetupItemState.failed(.remove, "blocked").failureMessage, "blocked")
        XCTAssertTrue(SetupItemState.active(.install).isActive)
        XCTAssertFalse(SetupItemState.installed.isActive)
    }

    func testAdoptionPreservesReceiptChoicesAndUsesActualAgentPort() throws {
        let home = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: home) }
        let root = home.appendingPathComponent("Library/Application Support/Glyphs MCP/lean-v2")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let receipt = try JSONSerialization.data(withJSONObject: ["version": "2.0.0", "components": ["reference-inspector"], "port": 9680])
        try receipt.write(to: root.appendingPathComponent("installation.json"))
        let agent = home.appendingPathComponent("Library/LaunchAgents/\(DesktopIdentity.serviceLabel).plist")
        try FileManager.default.createDirectory(at: agent.deletingLastPathComponent(), withIntermediateDirectories: true)
        let data = try PropertyListSerialization.data(fromPropertyList: ["ProgramArguments": ["python", "run.py", "--port", "9790"], "RunAtLoad": false], format: .xml, options: 0)
        try data.write(to: agent)
        let state = DesktopInstallation(home: home)
        XCTAssertEqual(state.components, ["reference-inspector"])
        XCTAssertEqual(state.port, 9790)
        XCTAssertFalse(state.autoStart)
        XCTAssertTrue(state.hasInstallation)
        XCTAssertFalse(state.hasServer)
        XCTAssertEqual(try Data(contentsOf: agent), data)
        XCTAssertEqual(try Data(contentsOf: root.appendingPathComponent("installation.json")), receipt)
    }

    func testMissingInstallationDoesNotInventARunningServer() {
        let state = DesktopInstallation(home: URL(fileURLWithPath: "/nonexistent/desktop-test"))
        XCTAssertFalse(state.hasInstallation)
        XCTAssertFalse(state.hasServer)
        XCTAssertNil(state.python)
    }

    func testProgressUsesChangesAndPreparationDoesNotInventPercentage() throws {
        let decoder = JSONDecoder()
        let preparing = try decoder.decode(DesktopActivity.self, from: Data(#"{"jobId":"a","document":"Test","kind":"spacing","phase":"preparing","startedAt":10}"#.utf8))
        XCTAssertNil(preparing.progressText)
        XCTAssertTrue(preparing.isBusy)
        let applying = try decoder.decode(DesktopActivity.self, from: Data(#"{"jobId":"a","document":"Test","kind":"spacing","phase":"applying","startedAt":10,"completed":5,"total":20}"#.utf8))
        XCTAssertEqual(applying.progressText, "5 of 20 changes")
    }

    func testDiagnosticsRemoveCredentials() {
        let result = DesktopDiagnostics.redact("Authorization: Bearer abc.def\ntoken=secret123\ncustom=actual-token", secrets: ["actual-token"])
        XCTAssertFalse(result.contains("abc.def"))
        XCTAssertFalse(result.contains("secret123"))
        XCTAssertFalse(result.contains("actual-token"))
    }

    func testActivityDistinguishesNativeRestorationFromDiscardingAProposal() throws {
        func job(_ fields: String) throws -> DesktopActivity {
            try JSONDecoder().decode(DesktopActivity.self, from: Data((#"{"jobId":"a","document":"Test","kind":"spacing","startedAt":10,"phase":"discarded""# + fields + "}").utf8))
        }
        XCTAssertEqual(try job(",\"completed\":2634,\"total\":2634").title, "Spacing reverted")
        XCTAssertEqual(try job("").title, "Spacing proposal discarded")
        XCTAssertEqual(try job(",\"completed\":12,\"total\":20").progressText, "12 changes")
    }

    func testMonitoringStopsWhenBothSurfacesAreHidden() {
        var policy = DesktopMonitorPolicy()
        XCTAssertNil(policy.interval(busy: true))
        policy.surfaces.insert("setup")
        XCTAssertNil(policy.interval(busy: false))
        policy.dashboardVisible = true
        XCTAssertEqual(policy.interval(busy: true), 2)
        XCTAssertEqual(policy.interval(busy: false), 5)
        policy.surfaces.insert("popover")
        policy.dashboardVisible = false
        XCTAssertEqual(policy.interval(busy: true), 2)
        policy.surfaces.remove("popover")
        XCTAssertNil(policy.interval(busy: true))
    }

    func testMenuDefaultAndLoginLaunchRemainSeparate() {
        let name = UUID().uuidString
        let defaults = UserDefaults(suiteName: name)!
        defer { defaults.removePersistentDomain(forName: name) }
        XCTAssertTrue(DesktopLaunchPolicy.showsMenuBar(defaults: defaults))
        XCTAssertNil(defaults.object(forKey: DesktopIdentity.showMenuBarKey))
        XCTAssertFalse(DesktopLaunchPolicy.showsDashboard(loginLaunch: true))
        XCTAssertTrue(DesktopLaunchPolicy.showsDashboard(loginLaunch: false))
        defaults.set(false, forKey: DesktopIdentity.showMenuBarKey)
        XCTAssertFalse(DesktopLaunchPolicy.showsMenuBar(defaults: defaults))
    }
}
