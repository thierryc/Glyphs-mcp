import Foundation
import XCTest
@testable import GlyphsMCPInstallerCore

final class DesktopTests: XCTestCase {
    func testOptionalToolAvailabilitySeparatesQualificationFromPlatformAndProtection() throws {
        func state(_ extra: String) throws -> OptionalToolState {
            try JSONDecoder().decode(OptionalToolState.self, from: Data(("{\"id\":\"diffenator\",\"available\":false,\"installed\":false," + extra + "}").utf8))
        }
        XCTAssertEqual(try state("\"distributionQualified\":true").label, "Unavailable on this Mac")
        XCTAssertEqual(try state("\"distributionQualified\":false").label, "Awaiting release qualification")
        XCTAssertEqual(try state("\"reason\":\"pending\"").label, "Awaiting release qualification")
        for value in ["unmanaged", "development_link", "conflict"] {
            XCTAssertTrue(try state("\"state\":\"" + value + "\"").protectedInstallation)
        }
    }

    func testCompanionStableIdentityIgnoresSignaturesButDetectsContentAndNativeCodeChanges() throws {
        let bundle = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: bundle) }
        let resources = bundle.appendingPathComponent("Contents/Resources")
        let signatures = bundle.appendingPathComponent("Contents/_CodeSignature")
        for path in [resources, signatures] { try FileManager.default.createDirectory(at: path, withIntermediateDirectories: true) }
        try Data("plist".utf8).write(to: bundle.appendingPathComponent("Contents/Info.plist"))
        try Data("original code".utf8).write(to: resources.appendingPathComponent("plugin.py"))
        try Data("signature one".utf8).write(to: signatures.appendingPathComponent("CodeResources"))
        let first = try ComponentUpdatePolicy.stableContentIdentity(bundle, nativeCodeHashes: ["arm64:code", "x86_64:code"])
        try Data("signature two plus ticket".utf8).write(to: signatures.appendingPathComponent("CodeResources"))
        try Data("bytecode cache".utf8).write(to: resources.appendingPathComponent("plugin.pyc"))
        XCTAssertEqual(first, try ComponentUpdatePolicy.stableContentIdentity(bundle, nativeCodeHashes: ["arm64:code", "x86_64:code"]))
        XCTAssertNotEqual(first, try ComponentUpdatePolicy.stableContentIdentity(bundle, nativeCodeHashes: ["arm64:new code", "x86_64:code"]))
        try Data("modified code".utf8).write(to: resources.appendingPathComponent("plugin.py"))
        XCTAssertNotEqual(first, try ComponentUpdatePolicy.stableContentIdentity(bundle, nativeCodeHashes: ["arm64:code", "x86_64:code"]))
    }

    func testComponentReminderExplainsTheServerUpdateAndNamesTheCorrectCard() {
        XCTAssertEqual(ComponentUpdateReminder.dismissalTitle, "Dismiss This Reminder")
        XCTAssertTrue(ComponentUpdateReminder.dismissalExplanation.contains("once per app version and build"))
        XCTAssertTrue(ComponentUpdateReminder.dismissalExplanation.contains("does not schedule another reminder"))
        XCTAssertTrue(ComponentUpdateReminder.dismissalExplanation.contains("available updates remain in Setup"))
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
        // Dismissing this reminder does not clear the card's Update available status.
        XCTAssertTrue(statuses["mcp"]!.needsUpdate)
        XCTAssertFalse(ComponentUpdateReminder.shouldPresent(statuses: ["beztrace-glyphs": .updateAvailable],
            alreadyShown: false, interactive: true, busy: false, otherDialog: false))
    }

    func testStatusRequestPreservesLegacyDeadlineAndDecodesHealthyResponse() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [HealthyStatusURLProtocol.self]
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

    func testTaskRefreshOnlyReportsStoppedWithConnectionAndProcessEvidence() {
        let connectionFailure = URLError(.cannotConnectToHost)
        XCTAssertEqual(DesktopDiagnostics.taskRefreshFailure(connectionFailure, processRunning: false), "Server stopped")
        XCTAssertEqual(DesktopDiagnostics.taskRefreshFailure(connectionFailure, processRunning: true), "Could not refresh Tasks.")
        XCTAssertEqual(DesktopDiagnostics.taskRefreshFailure(connectionFailure), "Could not refresh Tasks.")

        for code in [URLError.timedOut, .badServerResponse, .cannotParseResponse] {
            XCTAssertEqual(DesktopDiagnostics.taskRefreshFailure(URLError(code), processRunning: false), "Could not refresh Tasks.")
        }
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

    func testSuccessfulSetupAndPreservedSkillsUseInformation() {
        for preserved in [false, true] {
            let notice = ComponentNotice.setupCompletion(failedConnections: 0, preservedSkills: preserved)
            XCTAssertFalse(notice.isFailure)
            XCTAssertTrue(notice.text.contains("Setup is complete"))
            XCTAssertFalse(notice.text.contains("attention"))
        }
        let preserved = ComponentNotice.setupCompletion(failedConnections: 0, preservedSkills: true)
        XCTAssertTrue(preserved.text.contains("existing skills were kept"))
        let failed = ComponentNotice.setupCompletion(failedConnections: 1, preservedSkills: true)
        XCTAssertTrue(failed.isFailure)
        XCTAssertTrue(failed.text.contains("could not be configured"))
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
        XCTAssertEqual(DesktopDiagnostics.statusTone(running: true, stale: false, status: status), .ready)
        XCTAssertEqual(DesktopDiagnostics.statusTone(running: true, stale: true, status: status), .unavailable)
        XCTAssertEqual(DesktopDiagnostics.statusTone(running: false, stale: false, status: status), .unavailable)
        XCTAssertEqual(DesktopDiagnostics.statusTone(running: true, stale: false, status: nil), .active)
        XCTAssertEqual(DesktopDiagnostics.serverTitle(hasServer: true, running: true,
            status: nil, hasNotice: true, stale: true), "Status unavailable")
    }

    func testHealthWarningAndRecoveredStatusKeepConnectionPresentationIndependent() throws {
        let observed = try JSONDecoder().decode(DesktopServerStatus.self, from: Data(#"{"sidecarVersion":"2.6.0","bridge":{"reachable":true},"worker":{"available":true},"health":{"version":1,"available":true,"state":"caution","reasons":["memory_pressure_warning"]}}"#.utf8))
        XCTAssertEqual(observed.health?.title, "Reduce load")
        XCTAssertEqual(DesktopDiagnostics.serverTitle(hasServer: true, running: true,
            status: observed, hasNotice: false), "Ready")
        XCTAssertEqual(DesktopDiagnostics.statusTone(running: true, stale: false, status: observed), .ready)
        XCTAssertEqual(DesktopDiagnostics.statusSymbol(running: true, stale: true, status: observed), "exclamationmark.circle")
        XCTAssertEqual(DesktopDiagnostics.statusTone(running: true, stale: true, status: observed), .unavailable)
        // A subsequent fresh response restores readiness without changing the
        // independent pressure warning or requiring a process restart.
        XCTAssertEqual(DesktopDiagnostics.statusSymbol(running: true, stale: false, status: observed), "checkmark.circle.fill")
        XCTAssertEqual(observed.health?.state, "caution")
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


/// Decode a healthy response; timeout compatibility is asserted on the request.
private final class HealthyStatusURLProtocol: URLProtocol {
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
        DispatchQueue.global().async(execute: work)
    }
    override func stopLoading() { reply?.cancel(); reply = nil }
}

final class DesktopLocalizationTests: XCTestCase {
    private let languages = ["en", "fr", "zh-Hans", "de", "es", "pt-BR"]

    private func resources(_ language: String) throws -> Bundle {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        return try XCTUnwrap(Bundle(url: root.appendingPathComponent("Resources/\(language).lproj")))
    }

    func testEveryLanguageResolvesAppTextAndUnknownKeysFallBack() throws {
        for language in languages {
            let bundle = try resources(language)
            XCTAssertFalse(AppLocalization.text("Show Window", bundle: bundle).isEmpty)
            if language != "en" { XCTAssertNotEqual(AppLocalization.text("Cancel", bundle: bundle), "Cancel") }
            XCTAssertEqual(AppLocalization.text("an-unknown-key", bundle: bundle), "an-unknown-key")
        }
    }

    func testStructuredErrorTranslatesWithoutChangingDiagnosticOrArguments() throws {
        let path = "/tmp/100%/échantillon.glyphs"
        let detail = "RAW_EXTERNAL_ERROR 42"
        let error = InstallerError.localized("Could not verify \(path): \(detail)")
        XCTAssertEqual(error.localizedDescription, "Could not verify \(path): \(detail)")
        for language in languages {
            let translated = error.presentationDescription(bundle: try resources(language), locale: Locale(identifier: language))
            XCTAssertTrue(translated.contains(path))
            XCTAssertTrue(translated.contains(detail))
            if language != "en" { XCTAssertNotEqual(translated, error.localizedDescription) }
        }
        let project = ProjectError(localized: "The template folder could not be read.")
        XCTAssertEqual(project.localizedDescription, "The template folder could not be read.")
        XCTAssertNotEqual(project.presentationDescription(bundle: try resources("fr")), project.localizedDescription)
    }

    func testPercentInInterpolatedDiagnosticIsNotAFormatArgument() {
        let value = "font%name"
        let message: AppMessage = "100% of \(value)"
        XCTAssertEqual(message.diagnostic, "100% of font%name")
        XCTAssertEqual(message.localized(), message.diagnostic)
    }

    func testPluralResourcesHandleZeroOneAndMultipleCounts() throws {
        for language in languages {
            let bundle = try resources(language)
            let locale = Locale(identifier: language)
            for key in ["%lld days", "%lld active tasks", "%lld changed files", "Warn at %lld open fonts",
                        "%lld skills have updates"] {
                for count in [0, 1, 2, 21] {
                    let value = AppLocalization.count(key, count, bundle: bundle, locale: locale)
                    XCTAssertFalse(value.contains("%"), "\(language): \(value)")
                    XCTAssertTrue(value.contains(String(count)), "\(language): \(value)")
                }
            }
        }
        XCTAssertEqual(AppLocalization.count("%lld days", 1, bundle: try resources("en")), "1 day")
        XCTAssertEqual(AppLocalization.count("%lld days", 2, bundle: try resources("en")), "2 days")
        XCTAssertEqual(AppLocalization.count("%lld skills have updates", 1, bundle: try resources("de"),
                                             locale: Locale(identifier: "de")), "Für 1 Skill ist ein Update verfügbar")
        XCTAssertEqual(AppLocalization.count("%lld skills have updates", 2, bundle: try resources("de"),
                                             locale: Locale(identifier: "de")), "Für 2 Skills sind Updates verfügbar")
    }

    func testLanguagePreferencesAndEnglishFallback() {
        XCTAssertEqual(Bundle.preferredLocalizations(from: languages, forPreferences: ["pt-BR", "en"]).first, "pt-BR")
        XCTAssertEqual(Bundle.preferredLocalizations(from: languages, forPreferences: ["fr-CA", "en"]).first, "fr")
        XCTAssertEqual(Bundle.preferredLocalizations(from: languages, forPreferences: ["es-MX", "en"]).first, "es")
        XCTAssertEqual(Bundle.preferredLocalizations(from: languages, forPreferences: ["zz-ZZ"]).first, "en")
    }

    func testExternalDiagnosticsAreNotTranslatedAndTimeoutIsTyped() throws {
        let external = NSError(domain: "external", code: 7, userInfo: [NSLocalizedDescriptionKey: "unmodified external detail"])
        XCTAssertEqual(external.presentationDescription(bundle: try resources("de")), "unmodified external detail")
        let timeout = ProcessTimeoutError(duration: 2, executable: "git")
        XCTAssertEqual(timeout.localizedDescription, "Command timed out after 2 seconds: git.")
        XCTAssertNotEqual(timeout.presentationDescription(bundle: try resources("de")), timeout.localizedDescription)
        let german = timeout.presentationDescription(bundle: try resources("de"), locale: Locale(identifier: "de"))
        XCTAssertTrue(german.contains("Sekunden"))
        XCTAssertFalse(german.contains("seconds"))
    }
}

final class AntigravityConnectorTests: XCTestCase {
    private let files = FileManager.default
    private let endpoint = URL(string: "http://127.0.0.1:9680/mcp/")!

    func testDesktopDetectionAndBulkSetupForEitherOrBothApps() {
        let app = "com.google.antigravity"
        let ide = "com.google.antigravity-ide"
        for installed in [[], [app], [ide], [app, ide]] {
            let detected = AntigravityConnector.isDetected { bundleID in
                installed.contains(bundleID) ? URL(fileURLWithPath: "/Applications/Test.app") : nil
            }
            XCTAssertEqual(detected, !installed.isEmpty)
            let plan = SetupQueuePolicy.bulkPlan(
                installedComponents: [], installedConnectors: [],
                detectedConnectors: detected ? [.antigravity] : []
            )
            XCTAssertEqual(plan.filter { $0 == .connector(.antigravity, .install) }.count, detected ? 1 : 0)
        }
        let update = SetupQueuePolicy.bulkPlan(
            installedComponents: [], installedConnectors: [.antigravity], detectedConnectors: [.antigravity]
        )
        XCTAssertTrue(update.contains(.connector(.antigravity, .update)))
    }

    func testFreshSetupRepeatedSetupPortChangeAndOwnedRemoval() throws {
        try withHome { home, connector in
            XCTAssertEqual(connector.connectionStatus(), .missing)
            XCTAssertFalse(try connector.configureConnection())
            XCTAssertEqual(connector.connectionStatus(), .configured)
            XCTAssertTrue(connector.hasOwnershipReceipt)
            let original = try Data(contentsOf: connector.configURL)
            XCTAssertFalse(try connector.configureConnection())
            XCTAssertEqual(try Data(contentsOf: connector.configURL), original)
            XCTAssertTrue(try backups(for: connector).isEmpty)
            let initial = try servers(for: connector)
            XCTAssertEqual(Set(initial.keys), ["glyphs-mcp"])
            XCTAssertEqual(initial["glyphs-mcp"]?["serverUrl"] as? String, endpoint.absoluteString)

            let newEndpoint = URL(string: "http://127.0.0.1:9771/mcp/")!
            let updated = AntigravityConnector(home: home, endpoint: newEndpoint)
            XCTAssertEqual(updated.connectionStatus(), .updateAvailable)
            XCTAssertFalse(try updated.configureConnection())
            XCTAssertEqual(updated.connectionStatus(), .configured)
            XCTAssertEqual(try servers(for: updated)["glyphs-mcp"]?["serverUrl"] as? String, newEndpoint.absoluteString)
            let backup = try XCTUnwrap(backups(for: updated).first)
            XCTAssertEqual(try Data(contentsOf: backup), original)

            XCTAssertFalse(try updated.removeConnection())
            XCTAssertFalse(updated.hasOwnershipReceipt)
            XCTAssertTrue(try servers(for: updated).isEmpty)
            XCTAssertFalse(try updated.removeConnection())
            XCTAssertEqual(updated.connectionStatus(), .missing)
        }
    }

    func testManualAliasWithCustomHeadersRemainsByteIdenticalAcrossSetupAndRemoval() throws {
        try withHome { home, connector in
            let manual = #"{"extra":true,"mcpServers":{"unrelated":{"command":"other"},"glyphs-mcp-server":{"serverUrl":"http://localhost:9680/mcp","headers":{"X-Test":"keep"},"disabled":false}}}"#
            try write(manual, to: connector.configURL)
            XCTAssertEqual(connector.connectionStatus(), .configured)
            XCTAssertTrue(try connector.configureConnection())
            XCTAssertTrue(try connector.removeConnection())
            let changedPort = AntigravityConnector(home: home, endpoint: URL(string: "http://127.0.0.1:9771/mcp/")!)
            XCTAssertEqual(changedPort.connectionStatus(), .conflict)
            XCTAssertThrowsError(try changedPort.configureConnection())
            XCTAssertEqual(try Data(contentsOf: connector.configURL), Data(manual.utf8))
            XCTAssertTrue(try backups(for: connector).isEmpty)
            XCTAssertFalse(connector.hasOwnershipReceipt)
        }
    }

    func testModifiedInstallerEntryIsPreserved() throws {
        try withHome { home, connector in
            try connector.configureConnection()
            let modified = #"{"mcpServers":{"glyphs-mcp":{"serverUrl":"http://127.0.0.1:9680/mcp/","headers":{"X-Test":"local"}}}}"#
            try write(modified, to: connector.configURL)
            XCTAssertTrue(try connector.configureConnection())
            XCTAssertTrue(try connector.removeConnection())
            let changedPort = AntigravityConnector(home: home, endpoint: URL(string: "http://127.0.0.1:9771/mcp/")!)
            XCTAssertThrowsError(try changedPort.configureConnection())
            XCTAssertEqual(try Data(contentsOf: connector.configURL), Data(modified.utf8))
        }
    }

    func testMalformedDisabledConflictingAndDuplicateEntriesArePreserved() throws {
        try withHome { _, connector in
            for contents in [
                "{broken",
                #"{"mcpServers":[]}"#,
                #"{"mcpServers":{"glyphs-mcp":false}}"#,
                #"{"mcpServers":{"glyphs-mcp":{"serverUrl":"http://127.0.0.1:9680/mcp/","disabled":true}}}"#,
                #"{"mcpServers":{"glyphs-mcp":{"serverUrl":"http://127.0.0.1:9680/mcp/","url":"https://example.com/mcp"}}}"#,
                #"{"mcpServers":{"glyphs-mcp":{"serverUrl":"http://127.0.0.1:9680/mcp/"},"custom":{"serverUrl":"http://localhost:9680/mcp"}}}"#
            ] {
                try write(contents, to: connector.configURL)
                XCTAssertEqual(connector.connectionStatus(), .conflict, contents)
                XCTAssertThrowsError(try connector.configureConnection(), contents)
                XCTAssertEqual(try Data(contentsOf: connector.configURL), Data(contents.utf8))
                XCTAssertFalse(connector.hasOwnershipReceipt)
            }
            XCTAssertTrue(try backups(for: connector).isEmpty)
        }
    }

    func testLegacyRelativeSymlinkStaysInPlaceAcrossSharedWrites() throws {
        try withHome { home, connector in
            let legacy = home.appendingPathComponent(".gemini/antigravity/mcp_config.json")
            try files.createDirectory(at: legacy.deletingLastPathComponent(), withIntermediateDirectories: true)
            let target = "../config/mcp_config.json"
            try files.createSymbolicLink(atPath: legacy.path, withDestinationPath: target)

            try connector.configureConnection()
            XCTAssertEqual(try Data(contentsOf: legacy), try Data(contentsOf: connector.configURL))
            try connector.removeConnection()
            XCTAssertEqual(try files.destinationOfSymbolicLink(atPath: legacy.path), target)
            XCTAssertEqual(try Data(contentsOf: legacy), try Data(contentsOf: connector.configURL))
        }
    }

    func testSeparateLegacyFileAndRedirectedSharedFilesArePreserved() throws {
        try withHome { home, connector in
            let legacy = home.appendingPathComponent(".gemini/antigravity/mcp_config.json")
            try write("{}", to: legacy)
            XCTAssertThrowsError(try connector.configureConnection())
            XCTAssertEqual(try Data(contentsOf: legacy), Data("{}".utf8))
            XCTAssertFalse(files.fileExists(atPath: connector.configURL.path))

            try files.removeItem(at: legacy)
            let external = home.appendingPathComponent("external.json")
            try write("{}", to: external)
            try files.createDirectory(at: connector.configURL.deletingLastPathComponent(), withIntermediateDirectories: true)
            try files.createSymbolicLink(at: connector.configURL, withDestinationURL: external)
            XCTAssertThrowsError(try connector.configureConnection())
            XCTAssertEqual(try Data(contentsOf: external), Data("{}".utf8))
        }
    }

    func testOwnedSkillsUpgradeAndRemovalPreserveModifiedAndLinkedCopies() throws {
        try withHome { home, connector in
            let source = home.appendingPathComponent("payload/skills")
            let payload = InstallerPayload(payloadDir: source.deletingLastPathComponent(),
                                           pluginBundle: home.appendingPathComponent("plugin"),
                                           requirementsTxt: home.appendingPathComponent("requirements.txt"), skillsDir: source)
            let manifest = #"{"schemaVersion":1,"managedSkills":[{"name":"glyphs","surface":"glyphs-mcp-v2"},{"name":"glyphs-mcp-spacing","surface":"glyphs-mcp-v2"},{"name":"glyphs-mcp-scripting","surface":"glyphs-mcp-v2"},{"name":"glyphs-mcp-development","surface":"workspace"}]}"#
            try write(manifest, to: source.appendingPathComponent("manifest.json"))
            for name in ["glyphs", "glyphs-mcp-spacing", "glyphs-mcp-scripting", "glyphs-mcp-development"] {
                try write("bundled old", to: source.appendingPathComponent(name + "/SKILL.md"))
            }
            let installed = connector.skillsURL
            let external = home.appendingPathComponent("external/glyphs-mcp-scripting")
            try write("external", to: external.appendingPathComponent("SKILL.md"))
            try files.createDirectory(at: installed, withIntermediateDirectories: true)
            let link = installed.appendingPathComponent("glyphs-mcp-scripting")
            try files.createSymbolicLink(at: link, withDestinationURL: external)

            XCTAssertEqual(connector.skillsStatus(payload: payload, includeDevelopmentSkills: false), .partial)
            let result = try connector.installSkills(from: payload, includeDevelopmentSkills: false, log: { _ in })
            XCTAssertEqual(result.entries.filter { $0.outcome == .installed }.map(\.name), ["glyphs", "glyphs-mcp-spacing"])
            XCTAssertEqual(result.conflicts.map(\.name), ["glyphs-mcp-scripting"])
            XCTAssertTrue(connector.hasOwnershipReceipt)
            XCTAssertEqual(connector.skillsStatus(payload: payload, includeDevelopmentSkills: false), .available)
            XCTAssertFalse(files.fileExists(atPath: home.appendingPathComponent(".claude").path))

            let edited = installed.appendingPathComponent("glyphs-mcp-spacing/SKILL.md")
            try write("user edit", to: edited)
            try write("bundled new", to: source.appendingPathComponent("glyphs/SKILL.md"))
            XCTAssertEqual(connector.skillsStatus(payload: payload, includeDevelopmentSkills: false), .updateAvailable)
            let upgrade = try connector.installSkills(from: payload, includeDevelopmentSkills: false, log: { _ in })
            XCTAssertEqual(upgrade.conflicts.map(\.name), ["glyphs-mcp-scripting", "glyphs-mcp-spacing"])
            let current = installed.appendingPathComponent("glyphs/SKILL.md")
            XCTAssertEqual(try String(contentsOf: current, encoding: .utf8), "bundled new")
            XCTAssertEqual(connector.skillsStatus(payload: payload, includeDevelopmentSkills: false), .available)
            let removal = try connector.removeSkills(from: payload, log: { _ in })
            XCTAssertEqual(removal.entries.filter { $0.outcome == .removed }.map(\.name), ["glyphs"])
            XCTAssertFalse(files.fileExists(atPath: current.path))
            XCTAssertEqual(try String(contentsOf: edited, encoding: .utf8), "user edit")
            XCTAssertEqual(try String(contentsOf: link.appendingPathComponent("SKILL.md"), encoding: .utf8), "external")
        }
    }

    func testSkillRetryKeepsOwnershipOfEarlierCompletedCopies() throws {
        try withHome { home, connector in
            let source = home.appendingPathComponent("payload/skills")
            let payload = InstallerPayload(payloadDir: source.deletingLastPathComponent(),
                                           pluginBundle: home.appendingPathComponent("plugin"),
                                           requirementsTxt: home.appendingPathComponent("requirements.txt"), skillsDir: source)
            let manifest = #"{"schemaVersion":1,"managedSkills":[{"name":"glyphs","surface":"glyphs-mcp-v2"},{"name":"glyphs-mcp-spacing","surface":"glyphs-mcp-v2"}]}"#
            try write(manifest, to: source.appendingPathComponent("manifest.json"))
            let glyphs = source.appendingPathComponent("glyphs/SKILL.md")
            let spacing = source.appendingPathComponent("glyphs-mcp-spacing/SKILL.md")
            try write("first revision", to: glyphs)
            try files.createDirectory(at: spacing.deletingLastPathComponent(), withIntermediateDirectories: true)
            try files.createSymbolicLink(at: spacing, withDestinationURL: glyphs)

            XCTAssertThrowsError(try connector.installSkills(from: payload, includeDevelopmentSkills: false, log: { _ in }))
            XCTAssertTrue(connector.hasOwnershipReceipt)
            XCTAssertEqual(connector.skillsStatus(payload: payload, includeDevelopmentSkills: false), .partial)

            try files.removeItem(at: spacing)
            try write("spacing skill", to: spacing)
            try write("second revision", to: glyphs)
            let result = try connector.installSkills(from: payload, includeDevelopmentSkills: false, log: { _ in })
            XCTAssertTrue(result.conflicts.isEmpty)
            XCTAssertEqual(try String(contentsOf: connector.skillsURL.appendingPathComponent("glyphs/SKILL.md"),
                                      encoding: .utf8), "second revision")
            XCTAssertEqual(connector.skillsStatus(payload: payload, includeDevelopmentSkills: false), .available)

            // A link replacing an owned directory remains user-managed even when its contents match the receipt.
            let installed = connector.skillsURL.appendingPathComponent("glyphs")
            try files.removeItem(at: installed)
            try files.createSymbolicLink(at: installed, withDestinationURL: glyphs.deletingLastPathComponent())
            let removal = try connector.removeSkills(from: payload, log: { _ in })
            XCTAssertEqual(removal.conflicts.map(\.name), ["glyphs"])
            XCTAssertEqual(try files.destinationOfSymbolicLink(atPath: installed.path), glyphs.deletingLastPathComponent().path)
            XCTAssertEqual(try String(contentsOf: glyphs, encoding: .utf8), "second revision")
        }
    }

    private func withHome(_ body: (URL, AntigravityConnector) throws -> Void) throws {
        let home = files.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        try files.createDirectory(at: home, withIntermediateDirectories: false)
        defer { try? files.removeItem(at: home) }
        try body(home, AntigravityConnector(home: home, endpoint: endpoint))
    }

    private func write(_ text: String, to url: URL) throws {
        try files.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try text.write(to: url, atomically: true, encoding: .utf8)
    }

    private func backups(for connector: AntigravityConnector) throws -> [URL] {
        try files.contentsOfDirectory(at: connector.configURL.deletingLastPathComponent(), includingPropertiesForKeys: nil)
            .filter { $0.lastPathComponent.hasPrefix("mcp_config.json.bak-") }
    }

    private func servers(for connector: AntigravityConnector) throws -> [String: [String: Any]] {
        let root = try JSONSerialization.jsonObject(with: Data(contentsOf: connector.configURL)) as? [String: Any]
        return try XCTUnwrap(root?["mcpServers"] as? [String: [String: Any]])
    }
}
