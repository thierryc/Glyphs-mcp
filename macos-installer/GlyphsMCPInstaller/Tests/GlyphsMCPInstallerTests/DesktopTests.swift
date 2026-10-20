import Foundation
import XCTest
@testable import GlyphsMCPInstallerCore

final class DesktopTests: XCTestCase {
    func testComponentReminderExplainsTheServerUpdateAndNamesTheCorrectCard() {
        XCTAssertEqual(ComponentUpdateReminder.title(needsServerUpdate: true), "A new version of the MCP server in Glyphs is available.")
        XCTAssertTrue(ComponentUpdateReminder.message(needsServerUpdate: true).contains("click Update on the Glyphs MCP card"))
        XCTAssertTrue(ComponentUpdateReminder.message(needsServerUpdate: true).contains("\n\n"))
        XCTAssertEqual(ComponentUpdateReminder.title(needsServerUpdate: false), "Updates for your Glyphs plugins are available.")
        XCTAssertFalse(ComponentUpdateReminder.message(needsServerUpdate: false).contains("server"))
        XCTAssertTrue(ComponentUpdateReminder.message(needsServerUpdate: false).contains("highlighted plugin cards"))
    }

    func testComponentUpdateComparisonRequiresVerifiedIndependentIdentities() {
        let old = "sha256:" + String(repeating: "a", count: 64)
        let new = "sha256:" + String(repeating: "b", count: 64)
        func compare(_ installed: String?, _ bundled: String?, _ left: String?, _ right: String?) -> ComponentUpdateStatus {
            ComponentUpdatePolicy.compare(installedVersion: installed, bundledVersion: bundled,
                installedIdentities: [left], bundledIdentities: [right])
        }
        XCTAssertEqual(compare("2.1.0", "2.2.0", old, new), .updateAvailable)
        XCTAssertEqual(compare("2.2.0", "2.2.0", new, new), .current)
        XCTAssertEqual(compare("2.2.0", "2.2.0", old, new), .updateAvailable)
        XCTAssertEqual(compare("2.3.0", "2.2.0", old, new), .newerInstalled)
        XCTAssertEqual(compare("0.5.2", "0.5.2", old, old), .current)
        XCTAssertEqual(compare(nil, "2.2.0", old, new), .unableToVerify)
        XCTAssertEqual(compare("unknown", "2.2.0", old, new), .unableToVerify)
        XCTAssertEqual(compare("2.1.0", "2.2.0", nil, new), .unableToVerify)
        XCTAssertEqual(compare("2.1.0", "2.2.0", old, "invalid"), .unableToVerify)
        XCTAssertEqual(ComponentUpdatePolicy.compare(installedVersion: "2.2.0", bundledVersion: "2.2.0",
            installedIdentities: [old], bundledIdentities: [new], installedBuild: 68, bundledBuild: 67), .newerInstalled)
        XCTAssertEqual(ComponentUpdatePolicy.compare(installedVersion: "2.1.0", bundledVersion: "2.2.0",
            installedIdentities: [old], bundledIdentities: [new], developmentLinked: true), .developmentLinked)
    }

    func testComponentDiscoveryKeepsUnchangedInspectorsCurrentAndReconcilesReceipts() throws {
        let home = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: home) }
        let root = home.appendingPathComponent("Library/Application Support/Glyphs MCP/lean-v2")
        let plugins = home.appendingPathComponent("Library/Application Support/Glyphs 4/Plugins")
        let lean = home.appendingPathComponent("bundled/Lean")
        for path in [root, lean] + DesktopComponent.all.map({ plugins.appendingPathComponent($0.bundle) }) {
            try FileManager.default.createDirectory(at: path, withIntermediateDirectories: true)
        }
        let old = "sha256:" + String(repeating: "a", count: 64)
        let new = "sha256:" + String(repeating: "b", count: 64)
        let companions: [[String: Any]] = [
            ["id": "curve-inspector", "version": "0.5.2", "identity": old],
            ["id": "reference-inspector", "version": "0.1.0", "identity": old]]
        var receipt: [String: Any] = ["components": Array(DesktopComponent.ids), "version": "2.1.0",
            "bridge": ["version": "2.1.0", "identity": old, "release": ["installerBuild": 63]],
            "sidecar": ["identity": old, "release": ["version": "2.1.0"]],
            "runtime": ["identity": old], "companions": companions]
        let manifest: [String: Any] = ["version": "2.2.0", "installerBuild": 67,
            "bridge": ["identity": new], "sidecar": ["identity": new],
            "runtimes": ["arm64": ["identity": old]], "companions": companions]
        try JSONSerialization.data(withJSONObject: manifest).write(to: lean.appendingPathComponent("manifest.json"))
        func discover() throws -> [String: ComponentUpdateStatus] {
            try JSONSerialization.data(withJSONObject: receipt).write(to: root.appendingPathComponent("installation.json"))
            return ComponentUpdatePolicy.discover(installation: DesktopInstallation(home: home), lean: lean, architecture: "arm64")
        }
        let pending = try discover()
        XCTAssertEqual(pending["mcp"], .updateAvailable)
        XCTAssertEqual(pending["curve-inspector"], .current)
        XCTAssertEqual(pending["reference-inspector"], .current)
        // A failed/cancelled update leaves the original receipt and indication intact.
        XCTAssertEqual(try discover(), pending)
        receipt["version"] = "2.2.0"
        receipt["bridge"] = ["version": "2.2.0", "identity": new, "release": ["installerBuild": 67]]
        receipt["sidecar"] = ["identity": new, "release": ["version": "2.2.0"]]
        XCTAssertEqual(try discover()["mcp"], .current)
        receipt["sidecar"] = ["identity": new, "release": ["version": "2.1.0"]]
        XCTAssertEqual(try discover()["mcp"], .unableToVerify)
        try FileManager.default.removeItem(at: plugins.appendingPathComponent("Glyphs Curve Inspector.glyphsReporter"))
        XCTAssertEqual(try discover()["curve-inspector"], .unableToVerify)
        receipt["components"] = ["mcp"]
        XCTAssertNil(try discover()["reference-inspector"])
        let bridge = plugins.appendingPathComponent("Glyphs MCP Bridge.glyphsPlugin")
        try FileManager.default.removeItem(at: bridge)
        try FileManager.default.createSymbolicLink(at: bridge, withDestinationURL: lean)
        XCTAssertEqual(try discover()["mcp"], .developmentLinked)
        try Data("invalid receipt".utf8).write(to: root.appendingPathComponent("installation.json"))
        let unknown = ComponentUpdatePolicy.discover(installation: DesktopInstallation(home: home), lean: lean, architecture: "arm64")
        XCTAssertFalse(unknown.values.contains(where: \.needsUpdate))
    }

    func testComponentReminderIsOncePerAppBuildAndInstallationAndDefersWithoutConsumption() {
        let statuses: [String: ComponentUpdateStatus] = ["mcp": .updateAvailable]
        XCTAssertTrue(ComponentUpdateReminder.shouldPresent(statuses: statuses, alreadyShown: false,
            interactive: true, busy: false, otherDialog: false))
        for conditions in [(true, true, false, false), (false, false, false, false),
                           (false, true, true, false), (false, true, false, true)] {
            XCTAssertFalse(ComponentUpdateReminder.shouldPresent(statuses: statuses, alreadyShown: conditions.0,
                interactive: conditions.1, busy: conditions.2, otherDialog: conditions.3))
        }
        for state in [ComponentUpdateStatus.current, .newerInstalled, .unableToVerify, .developmentLinked] {
            XCTAssertFalse(ComponentUpdateReminder.shouldPresent(statuses: ["mcp": state], alreadyShown: false,
                interactive: true, busy: false, otherDialog: false))
        }
        let root = URL(fileURLWithPath: "/fixture/installation")
        let key = ComponentUpdateReminder.key(version: "2.2.0", build: "67", root: root)
        XCTAssertEqual(key, ComponentUpdateReminder.key(version: "2.2.0", build: "67", root: root))
        XCTAssertNotEqual(key, ComponentUpdateReminder.key(version: "2.2.0", build: "68", root: root))
        XCTAssertNotEqual(key, ComponentUpdateReminder.key(version: "2.3.0", build: "67", root: root))
        XCTAssertNotEqual(key, ComponentUpdateReminder.key(version: "2.2.0", build: "67", root: root.appendingPathComponent("other")))
        // Later is tracked separately; the card still reports Update available.
        XCTAssertTrue(statuses["mcp"]!.needsUpdate)
        XCTAssertFalse(ComponentUpdateReminder.shouldPresent(statuses: ["beztrace-glyphs": .updateAvailable],
            alreadyShown: false, interactive: true, busy: false, otherDialog: false))
    }

    func testSlowHealthyStatusResponseSurvivesTheOldThreeSecondDeadline() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [SlowStatusURLProtocol.self]
        let session = URLSession(configuration: configuration)
        defer { session.invalidateAndCancel() }
        let request = DesktopStatusRequest.make(port: 9680, token: "test-token")
        // The client must outlast the bridge's 15-second reachability check.
        XCTAssertGreaterThan(request.timeoutInterval, 15)
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer test-token")
        XCTAssertEqual(request.cachePolicy, .reloadIgnoringLocalCacheData)
        let (data, response) = try await session.data(for: request)
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
        struct Envelope: Decodable { let ok: Bool; let data: DesktopServerStatus }
        let result = try JSONDecoder().decode(Envelope.self, from: data)
        XCTAssertTrue(result.ok)
        XCTAssertEqual(result.data.title, "Ready")
        XCTAssertTrue(result.data.bridge.reachable)
    }

    func testStatusTimeoutDoesNotClaimAWorkingServiceHasStopped() {
        let timeout = URLError(.timedOut)
        let running = DesktopDiagnostics.statusFailure(timeout, running: true)
        XCTAssertTrue(running.contains("server is running"))
        XCTAssertTrue(running.contains("took too long"))
        for knownRunning in [false, nil] as [Bool?] {
            let unknown = DesktopDiagnostics.statusFailure(timeout, running: knownRunning)
            XCTAssertTrue(unknown.contains("took too long"))
            XCTAssertFalse(unknown.contains("server is running"))
        }
        let connection = DesktopDiagnostics.statusFailure(URLError(.cannotConnectToHost), running: nil)
        XCTAssertFalse(connection.contains("took too long"))
        XCTAssertFalse(connection.contains("server is running"))
        let rejected = InstallerError.userFacing(DesktopDiagnostics.statusFailure(403))
        XCTAssertTrue(DesktopDiagnostics.statusFailure(rejected, running: true).contains("authentication"))
    }

    func testExternalBeztraceIsExcludedFromBundledInstallAndRemovalPlans() {
        let id = ExternalGlyphsCompanion.beztrace.id
        XCTAssertFalse(DesktopComponent.ids.contains(id))
        let plan = DesktopComponentPlan(installed: [id], selected: [id])
        XCTAssertFalse(plan.hasWork)
        let bulk = SetupQueuePolicy.bulkPlan(installedComponents: [id], installedConnectors: [])
        XCTAssertFalse(bulk.contains(.component(id, .install)))
        XCTAssertFalse(bulk.contains(.component(id, .update)))
        XCTAssertEqual(DesktopComponent.ids, ["mcp", "curve-inspector", "reference-inspector"])
    }

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

    func testFailedRefreshCannotPresentCachedReadyOrWorkingAsLiveStatus() throws {
        for activeCount in [0, 1] {
            let status = try JSONDecoder().decode(DesktopServerStatus.self, from: Data("""
                {"sidecarVersion":"2.0.0","bridge":{"reachable":true},"worker":{"available":true},
                 "activity":{"jobs":[],"activeCount":\(activeCount)},"controlProtocol":1}
                """.utf8))
            for running in [true, nil] as [Bool?] {
                XCTAssertEqual(DesktopDiagnostics.serverTitle(hasServer: true, running: running,
                    status: status, hasNotice: true, stale: true), "Status unavailable")
                XCTAssertEqual(DesktopDiagnostics.statusSymbol(running: running, stale: true, status: status),
                               "exclamationmark.circle")
                XCTAssertFalse(status.showsActivityDot(stale: true, running: running))
            }
            XCTAssertEqual(DesktopDiagnostics.serverTitle(hasServer: true, running: false,
                status: status, hasNotice: true, stale: true), "Server stopped")
            XCTAssertEqual(DesktopDiagnostics.serverTitle(hasServer: true, running: true,
                status: status, hasNotice: false, stale: false), activeCount == 0 ? "Ready" : "Working")
        }
    }

    func testGlyphsRecoveryRequiresAFreshUnreachableBridge() throws {
        let ready = try JSONDecoder().decode(DesktopServerStatus.self,
            from: Data(#"{"sidecarVersion":"2.0.0","bridge":{"reachable":true},"worker":{"available":true}}"#.utf8))
        let waiting = try JSONDecoder().decode(DesktopServerStatus.self,
            from: Data(#"{"sidecarVersion":"2.0.0","bridge":{"reachable":false},"worker":{"available":true}}"#.utf8))
        XCTAssertFalse(DesktopDiagnostics.needsGlyphsRecovery(hasServer: true, running: true,
            stale: false, status: nil, hasNotice: true))
        XCTAssertFalse(DesktopDiagnostics.needsGlyphsRecovery(hasServer: true, running: nil,
            stale: true, status: ready, hasNotice: true))
        XCTAssertFalse(DesktopDiagnostics.needsGlyphsRecovery(hasServer: true, running: true,
            stale: true, status: waiting, hasNotice: true))
        XCTAssertTrue(DesktopDiagnostics.needsGlyphsRecovery(hasServer: true, running: true,
            stale: false, status: waiting, hasNotice: true))
        // An identity notice on a reachable bridge is not a startup-dialog signal.
        XCTAssertFalse(DesktopDiagnostics.needsGlyphsRecovery(hasServer: true, running: true,
            stale: false, status: ready, hasNotice: true))
        XCTAssertFalse(DesktopDiagnostics.needsGlyphsRecovery(hasServer: true, running: false,
            stale: true, status: ready, hasNotice: false))
        XCTAssertFalse(DesktopDiagnostics.needsGlyphsRecovery(hasServer: false, running: nil,
            stale: true, status: waiting, hasNotice: true))
        XCTAssertFalse(DesktopDiagnostics.needsGlyphsRecovery(hasServer: true, running: nil,
            stale: false, status: nil, hasNotice: false))
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
        XCTAssertEqual(SetupItemState.developmentLinked.statusLabel, "Development link")
        XCTAssertNil(SetupItemState.developmentLinked.operation)
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

    func testLinkedDevelopmentComponentsAreDetectedWithoutAReadableReceipt() throws {
        let fm = FileManager.default
        let home = fm.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? fm.removeItem(at: home) }
        let build = home.appendingPathComponent("development/simple-v2", isDirectory: true)
        let plugins = home.appendingPathComponent("Library/Application Support/Glyphs 4/Plugins", isDirectory: true)
        let root = home.appendingPathComponent("Library/Application Support/Glyphs MCP/lean-v2", isDirectory: true)
        try fm.createDirectory(at: build, withIntermediateDirectories: true)
        try fm.createDirectory(at: plugins, withIntermediateDirectories: true)
        try fm.createDirectory(at: root.appendingPathComponent("runtime/bin"), withIntermediateDirectories: true)
        try Data().write(to: root.appendingPathComponent("runtime/bin/python3"))
        let bundles = ["mcp": "Glyphs MCP Bridge.glyphsPlugin",
                       "curve-inspector": "Glyphs Curve Inspector.glyphsReporter",
                       "reference-inspector": "Glyphs Reference Inspector.glyphsReporter"]
        for name in bundles.values {
            let target = build.appendingPathComponent(name, isDirectory: true)
            try fm.createDirectory(at: target, withIntermediateDirectories: true)
            try fm.createSymbolicLink(at: plugins.appendingPathComponent(name), withDestinationURL: target)
        }
        try fm.createSymbolicLink(
            at: root.appendingPathComponent("installation.json"),
            withDestinationURL: build.appendingPathComponent("missing-installation.dev.json")
        )

        let state = DesktopInstallation(home: home)
        XCTAssertEqual(state.components, Set(bundles.keys))
        XCTAssertEqual(state.developmentLinkedComponents, Set(bundles.keys))
        XCTAssertTrue(state.brokenDevelopmentLinkedComponents.isEmpty)
        XCTAssertTrue(state.isDevelopmentLinked)
        XCTAssertEqual(state.python, root.appendingPathComponent("runtime/bin/python3"))
        XCTAssertTrue(state.hasServer)
    }

    func testDanglingDevelopmentComponentLinksAreReportedButNotInstalled() throws {
        let fm = FileManager.default
        let home = fm.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? fm.removeItem(at: home) }
        let plugins = home.appendingPathComponent("Library/Application Support/Glyphs 4/Plugins", isDirectory: true)
        try fm.createDirectory(at: plugins, withIntermediateDirectories: true)
        try fm.createSymbolicLink(
            at: plugins.appendingPathComponent("Glyphs MCP Bridge.glyphsPlugin"),
            withDestinationURL: home.appendingPathComponent("missing/Glyphs MCP Bridge.glyphsPlugin")
        )

        let state = DesktopInstallation(home: home)
        XCTAssertFalse(state.components.contains("mcp"))
        XCTAssertEqual(state.brokenDevelopmentLinkedComponents, ["mcp"])
        XCTAssertFalse(state.hasServer)
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
        policy.surfaces.insert("statusMenu")
        policy.dashboardVisible = false
        XCTAssertEqual(policy.interval(busy: true), 2)
        policy.surfaces.remove("statusMenu")
        XCTAssertNil(policy.interval(busy: true))
    }

    func testWelcomeCompletionPersistsWithoutChangingBridgeOrMenuPreferences() {
        let name = UUID().uuidString
        let defaults = UserDefaults(suiteName: name)!
        defer { defaults.removePersistentDomain(forName: name) }
        XCTAssertTrue(DesktopLaunchPolicy.showsWelcome(loginLaunch: false, defaults: defaults))
        XCTAssertFalse(DesktopLaunchPolicy.showsWelcome(loginLaunch: true, defaults: defaults))
        XCTAssertNil(defaults.object(forKey: DesktopLaunchPolicy.welcomeCompletedKey))
        DesktopLaunchPolicy.completeWelcome(defaults: defaults)
        let reopened = UserDefaults(suiteName: name)!
        XCTAssertFalse(DesktopLaunchPolicy.showsWelcome(loginLaunch: false, defaults: reopened))
        XCTAssertFalse(DesktopLaunchPolicy.showsWelcome(loginLaunch: true, defaults: reopened))
        XCTAssertNil(defaults.object(forKey: "com.ap.cx.glyphs-mcp.welcomeShown"))
        XCTAssertNil(defaults.object(forKey: DesktopIdentity.showMenuBarKey))
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


/// Reproduce a healthy bridge response arriving after Setup's old deadline.
private final class SlowStatusURLProtocol: URLProtocol {
    private var reply: DispatchWorkItem?
    override class func canInit(with request: URLRequest) -> Bool {
        request.url?.path == "/internal/status"
    }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let work = DispatchWorkItem { [weak self] in
            guard let self, let url = self.request.url,
                  let response = HTTPURLResponse(url: url, statusCode: 200,
                    httpVersion: "HTTP/1.1", headerFields: ["Content-Type": "application/json"]) else { return }
            let body = Data(#"{"ok":true,"data":{"sidecarVersion":"2.1.0","bridge":{"reachable":true},"worker":{"available":true},"controlProtocol":1}}"#.utf8)
            self.client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            self.client?.urlProtocol(self, didLoad: body)
            self.client?.urlProtocolDidFinishLoading(self)
        }
        reply = work
        DispatchQueue.global().asyncAfter(deadline: .now() + 3.5, execute: work)
    }
    override func stopLoading() { reply?.cancel(); reply = nil }
}
