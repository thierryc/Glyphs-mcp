import AppKit
import XCTest
@testable import GlyphsMCPInstallerCore

final class DesktopActivityTests: XCTestCase {
    private func job(_ id: String, _ phase: String, message: String? = nil) -> DesktopActivity {
        DesktopActivity(jobId: id, document: "Test", kind: "spacing", phase: phase,
            startedAt: 10, finishedAt: nil, completed: nil, total: nil, message: message)
    }

    func testRepeatedHistoryBecomesOneRecentResult() {
        let observed = (1...5).map { job("job_\($0)", "discarded") }
        let summary = DesktopActivitySummary(jobs: observed)
        XCTAssertEqual(summary.jobs.map(\.id), ["job_1"])
        XCTAssertEqual(summary.heading, "Last result")
        XCTAssertEqual(summary.history.count, 4)
    }

    func testActiveAndReadyJobsTakePriorityWithoutCombiningDistinctOperations() {
        let ready = job("ready", "ready")
        let active = job("active", "applying")
        let history = job("history", "discarded")
        let working = DesktopActivitySummary(jobs: [history, ready, active])
        XCTAssertEqual(working.jobs.map(\.id), [active.id])
        XCTAssertEqual(working.heading, "In progress")
        XCTAssertEqual(working.history.map(\.id), [history.id, ready.id])
        let idle = DesktopActivitySummary(jobs: [history, ready])
        XCTAssertEqual(idle.jobs.map(\.id), [ready.id])
        XCTAssertEqual(idle.heading, "Awaiting review")
        let concurrent = DesktopActivitySummary(jobs: (1...5).map { job("job_\($0)", "preparing") }, activeCount: 8)
        XCTAssertEqual(concurrent.jobs.count, 3)
        XCTAssertEqual(concurrent.additionalCount, 5)
    }

    func testCancellationOmitsOnlyRedundantExplanationAndRetainsRecoveryErrors() {
        XCTAssertNil(job("a", "cancelled", message: "application was cancelled").detailMessage)
        XCTAssertNil(job("a", "cancelled", message: "Job cancelled.").detailMessage)
        XCTAssertEqual(job("a", "cancelled").title, "Spacing cancelled")
        XCTAssertEqual(job("a", "cancelled", message: "Recovery is incomplete").detailMessage, "Recovery is incomplete")
        XCTAssertEqual(job("a", "failed", message: "job cancelled").detailMessage, "job cancelled")
        XCTAssertEqual(job("a", "applied").title, "Spacing applied")
    }

    func testDotRequiresObservedWorkRatherThanExecutableAvailabilityOrReadyProposals() {
        func status(active: Int = 0, operations: Int = 0, jobs: [DesktopActivity] = [], workers: [DesktopServerStatus.Worker.Execution] = []) -> DesktopServerStatus {
            DesktopServerStatus(sidecarVersion: "2.1.0", bridge: .init(reachable: true, activeOperations: operations),
                worker: .init(available: true, executable: "/worker", executions: workers),
                activity: .init(jobs: jobs, activeCount: active), controlProtocol: 1)
        }
        XCTAssertFalse(status().showsActivityDot(stale: false, running: true))
        XCTAssertFalse(status(jobs: [job("a", "ready")]).showsActivityDot(stale: false, running: true))
        for working in [status(active: 1), status(operations: 1), status(jobs: [job("a", "cancelling")]),
                        status(workers: [.init(jobId: "a", pid: nil, startedAt: 10, phase: "starting")])] {
            XCTAssertTrue(working.showsActivityDot(stale: false, running: true))
            XCTAssertFalse(working.showsActivityDot(stale: true, running: true))
            XCTAssertFalse(working.showsActivityDot(stale: false, running: false))
            XCTAssertFalse(working.showsActivityDot(stale: false, running: nil))
        }
    }

    func testClosedPopoverPollsOnlyWhileMenuBarIndicatesWork() {
        var policy = DesktopMonitorPolicy()
        policy.menuBarVisible = true
        XCTAssertEqual(policy.interval(busy: true), 2)
        XCTAssertNil(policy.interval(busy: false))
        policy.menuBarVisible = false
        XCTAssertNil(policy.interval(busy: true))
    }

    func testFileEventFilterIgnoresArtifactsAndOtherApplications() {
        let root = URL(fileURLWithPath: "/managed/lean-v2")
        XCTAssertTrue(DesktopJobEvents.isRelevant(path: "/managed/lean-v2/jobs/job_1/state.json", root: root))
        XCTAssertTrue(DesktopJobEvents.isRelevant(path: "/managed/lean-v2/installation.json", root: root))
        XCTAssertTrue(DesktopJobEvents.isRelevant(path: "/private/var/tmp/lean-v2/jobs/job_1/state.json", root: URL(fileURLWithPath: "/var/tmp/lean-v2")))
        for path in ["/managed/lean-v2/jobs/job_1/state.json.tmp", "/managed/lean-v2/jobs/job_1/source/a.glyph",
                     "/managed/lean-v2/jobs/job_1/patch.json", "/elsewhere/jobs/job_1/state.json"] {
            XCTAssertFalse(DesktopJobEvents.isRelevant(path: path, root: root))
        }
    }

    @MainActor
    func testNativeFileEventsObserveAtomicJobWritesAndStopCleanly() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString).resolvingSymlinksInPath()
        defer { try? FileManager.default.removeItem(at: root) }
        let directory = root.appendingPathComponent("jobs/job_1")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let observed = expectation(description: "Atomic state publication")
        observed.assertForOverFulfill = false
        var count = 0
        let watcher = try XCTUnwrap(DesktopJobEvents(root: root) {
            if (try? String(contentsOf: directory.appendingPathComponent("state.json"))) == "ready" {
                count += 1; observed.fulfill()
            }
        })
        try Data("ready".utf8).write(to: directory.appendingPathComponent("state.json"), options: .atomic)
        await fulfillment(of: [observed], timeout: 6)
        watcher.stop()
        let stoppedCount = count
        try Data("applied".utf8).write(to: directory.appendingPathComponent("state.json"), options: .atomic)
        try await Task.sleep(for: .milliseconds(600))
        XCTAssertEqual(count, stoppedCount)
    }

    @MainActor
    func testIdleLogoIsCenteredAndActiveLogoLeavesRoomForTheDot() throws {
        let logo = NSImage(size: NSSize(width: 18, height: 18), flipped: false) { _ in
            NSColor.black.setFill(); NSRect(x: 0, y: 0, width: 18, height: 18).fill(); return true
        }
        for active in [false, true] {
            let image = DesktopMenuImage.make(logo: logo, active: active)
            XCTAssertTrue(image.isTemplate)
            XCTAssertEqual(image.size, NSSize(width: 24, height: 18))
            for scale in 1...2 {
                let bitmap = try render(size: image.size, scale: scale) {
                    image.draw(in: NSRect(origin: .zero, size: image.size))
                }
                let occupied = (0..<bitmap.pixelsWide).filter {
                    (bitmap.colorAt(x: $0, y: 9 * scale)?.alphaComponent ?? 0) > 0.5
                }
                let first = try XCTUnwrap(occupied.first), last = try XCTUnwrap(occupied.last)
                XCTAssertEqual(occupied.count, 18 * scale)
                if active {
                    XCTAssertEqual(first, 0)
                    XCTAssertLessThan(last, 20 * scale) // Two-point gap before the activity dot.
                } else {
                    XCTAssertEqual(first, bitmap.pixelsWide - 1 - last)
                }
            }
        }
    }

    @MainActor
    func testActivityDotUsesExactUnboostedCyan() throws {
        let dot = DesktopActivityDot(frame: NSRect(x: 0, y: 0, width: 4, height: 4))
        dot.updateLayer()
        XCTAssertFalse(dot.allowsVibrancy)
        XCTAssertNil(dot.hitTest(NSPoint(x: 2, y: 2)))
        let layer = try XCTUnwrap(dot.layer)
        let color = try XCTUnwrap(NSColor(cgColor: try XCTUnwrap(layer.backgroundColor)))
        if #available(macOS 26, *) {
            XCTAssertEqual(color.linearExposure, 1, accuracy: 0.00001)
            XCTAssertEqual(layer.preferredDynamicRange, .standard)
        }
        let rgb = try XCTUnwrap(color.usingColorSpace(.sRGB))
        XCTAssertEqual(rgb.redComponent, 0, accuracy: 0.00001)
        XCTAssertEqual(rgb.greenComponent, 187 / 255.0, accuracy: 0.00001)
        XCTAssertEqual(rgb.blueComponent, 208 / 255.0, accuracy: 0.00001)
        XCTAssertEqual(rgb.alphaComponent, 1)
        XCTAssertNil(layer.animationKeys())
    }

    @MainActor
    func testActivityDotIsTheSamePlainCircleInBothAppearances() throws {
        let dot = DesktopActivityDot(frame: NSRect(x: 0, y: 0, width: 4, height: 4))
        for scale in 1...2 {
            var samples: [Data] = []
            for appearance in [NSAppearance.Name.aqua, .darkAqua] {
                dot.appearance = NSAppearance(named: appearance)
                dot.updateLayer()
                let layer = try XCTUnwrap(dot.layer)
                XCTAssertEqual(layer.borderWidth, 0)
                XCTAssertEqual(layer.shadowOpacity, 0)
                XCTAssertEqual(layer.cornerRadius, 2)
                let bitmap = try render(size: dot.bounds.size, scale: scale) {
                    layer.render(in: NSGraphicsContext.current!.cgContext)
                }
                samples.append(try XCTUnwrap(bitmap.representation(using: .png, properties: [:])))
                XCTAssertEqual(dot.bounds.size, NSSize(width: 4, height: 4))
                XCTAssertNil(layer.animationKeys())
            }
            XCTAssertEqual(samples[0], samples[1], "Appearance must not add an outline or recolor the circle")
        }
    }

    private func render(size: NSSize, scale: Int, draw: () -> Void) throws -> NSBitmapImageRep {
        let bitmap = try XCTUnwrap(NSBitmapImageRep(bitmapDataPlanes: nil,
            pixelsWide: Int(size.width) * scale, pixelsHigh: Int(size.height) * scale,
            bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
            colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0))
        bitmap.size = size
        NSGraphicsContext.saveGraphicsState()
        defer { NSGraphicsContext.restoreGraphicsState() }
        NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: bitmap)
        draw()
        return bitmap
    }
}

extension DesktopActivityTests {
    func testIndependentComponentIdentityAndUnavailableLegacyEvidence() throws {
        let a = "sha256:" + String(repeating: "a", count: 64)
        let b = "sha256:" + String(repeating: "b", count: 64)
        let json: [String: Any] = ["sidecarVersion":"2.0.0", "codeHash":a, "runtimeId":"2.0.0-beta.1+aaaaaaaaaaaa",
            "bridge":["reachable":true, "codeHash":b, "bridgeVersion":"2.0.0"], "worker":["available":true]]
        let status = try JSONDecoder().decode(DesktopServerStatus.self, from: JSONSerialization.data(withJSONObject: json))
        XCTAssertTrue(status.identityIssues(expectedSidecar: a, expectedBridge: b).isEmpty)
        XCTAssertTrue(status.identityIssues(expectedSidecar: b, expectedBridge: b).first!.contains("Sidecar fingerprint differs"))
        XCTAssertTrue(status.identityIssues(expectedSidecar: a, expectedBridge: a).first!.contains("Bridge fingerprint differs"))
        XCTAssertEqual(status.identityIssues(expectedSidecar: nil, expectedBridge: nil).count, 2)
        let legacy = try JSONDecoder().decode(DesktopServerStatus.self, from: Data(#"{"sidecarVersion":"0.1.0","bridge":{"reachable":true},"worker":{"available":false}}"#.utf8))
        XCTAssertEqual(legacy.identityIssues(expectedSidecar: a, expectedBridge: b).count, 2)
        XCTAssertTrue(legacy.identityIssues(expectedSidecar: a, expectedBridge: b).allSatisfy { $0.contains("unavailable") })
        XCTAssertEqual(status.bridge.bridgeVersion, "2.0.0")
    }
}


final class DesktopTaskTests: XCTestCase {
    func testArchiveIsAnOrphanInterruptedActionAndRetainsUnverifiedOutcome() throws {
        var object: [String: Any] = ["jobId": "job_exact", "revision": 12, "state": "interrupted",
            "documentName": "HandPrint", "message": "Review before archiving", "closed": false, "pending": false,
            "actions": [["action": "archive_interrupted", "label": "Archive Interrupted Task",
                         "consequence": "Outcome remains Unverified; diagnostics retained", "token": "current-token"]]]
        func decode() throws -> DesktopTaskRecovery {
            try JSONDecoder().decode(DesktopTaskRecovery.self, from: JSONSerialization.data(withJSONObject: object))
        }
        let eligible = try decode()
        XCTAssertNil(eligible.workflowId); XCTAssertEqual(eligible.jobId, "job_exact")
        XCTAssertEqual(eligible.closingActions.map(\.action), ["archive_interrupted"])
        XCTAssertFalse(eligible.closingActions[0].isCancellation)
        object["workflowId"] = "edit_owner"
        XCTAssertTrue(try decode().closingActions.isEmpty)
        object.removeValue(forKey: "workflowId"); object["state"] = "applying"
        XCTAssertTrue(try decode().closingActions.isEmpty)
        object["state"] = "archived"; object["closed"] = true
        object["receipt"] = "Task archived. Outcome: Unverified. Diagnostics retained."
        let archived = try decode()
        XCTAssertEqual(archived.statusLabel, "Unverified")
        XCTAssertTrue(archived.closingActions.isEmpty); XCTAssertNotNil(archived.receipt)
        XCTAssertEqual(try task(state: "archived").statusLabel, "Unverified")
    }

    func testRecoveryOffersOnlyClosingActionsAndPreservesPendingOutcome() throws {
        func snapshot(closed: Bool, pending: Bool, receipt: String?) throws -> DesktopTaskRecovery {
            var object: [String: Any] = ["workflowId": "edit_exact", "revision": 12, "state": "discarding",
                "documentName": "Bryan", "message": "Check again", "closed": closed, "pending": pending,
                "actions": ["finish_script", "finish_edit", "cancel", "discard", "save_result", "restore_saved_script", "run_script", "acknowledge_script_outcome"].map {
                    ["action": $0, "label": $0, "consequence": "Explicit consequences", "token": "current-token"]
                }]
            if let receipt { object["receipt"] = receipt }
            return try JSONDecoder().decode(DesktopTaskRecovery.self, from: JSONSerialization.data(withJSONObject: object))
        }
        let pending = try snapshot(closed: false, pending: true, receipt: nil)
        XCTAssertEqual(pending.workflowId, "edit_exact"); XCTAssertEqual(pending.revision, 12)
        XCTAssertTrue(pending.pending); XCTAssertFalse(pending.closed); XCTAssertNil(pending.receipt)
        XCTAssertEqual(pending.statusLabel, "Cancellation pending")
        XCTAssertEqual(pending.closingActions.map(\.action), ["finish_script", "finish_edit", "cancel", "discard"])
        XCTAssertEqual(pending.closingActions.filter(\.isCancellation).map(\.action), ["cancel", "discard"])
        let closed = try snapshot(closed: true, pending: false, receipt: "Task closed without saving.")
        XCTAssertTrue(closed.closingActions.isEmpty); XCTAssertNotNil(closed.receipt)
        XCTAssertEqual(closed.statusLabel, "Closed")
    }
    private func task(_ id: String = "edit_a", agent: String = "codex", identity: String = "01a13f8f-4e03-76f2-b8ce-96acc7f0627d", closed: Bool = false, conflict: Bool = false, state: String = "needs_decision") throws -> DesktopTask {
        let value: [String: Any] = ["id": id, "workflowId": id, "title": "Run script", "documentName": "Bryan", "state": state, "closed": closed, "createdAt": 1, "updatedAt": 2, "blockedBy": [], "blocking": [], "origin": ["agent": agent, "conversationId": identity, "conflict": conflict]]
        return try JSONDecoder().decode(DesktopTask.self, from: JSONSerialization.data(withJSONObject: value))
    }
    func testOnlyVerifiedCodexOriginBuildsFixedSchemeLink() throws {
        XCTAssertEqual(try task().conversationURL?.absoluteString, "codex://threads/01a13f8f-4e03-76f2-b8ce-96acc7f0627d")
        XCTAssertNil(try task(agent: "claude_code").conversationURL)
        XCTAssertNil(try task(identity: "https://example.com").conversationURL)
        XCTAssertNil(try task(conflict: true).conversationURL)
        XCTAssertTrue(try task().copyRequest.contains("edit_a"))
        XCTAssertTrue(try task().copyRequest.contains("Do not repeat"))
    }
    func testClosePromptRequiresFreshStateAndASeparateWorkflowDecision() throws {
        for state in ["running", "blocked", "needs_decision", "interrupted", "unknown"] {
            let value = try task(state: state)
            XCTAssertEqual(value.prompt(for: .review), value.copyRequest)
            let prompt = value.prompt(for: .closeTask)
            XCTAssertTrue(prompt.contains("task edit_a for Bryan: Run script"))
            XCTAssertTrue(prompt.contains("Retrieve its current state and blockers"))
            XCTAssertTrue(prompt.contains("If running, explain cancellation limits"))
            XCTAssertTrue(prompt.contains("Show only currently available actions and wait for my choice"))
            XCTAssertTrue(prompt.contains("Do not rerun the script or automatically cancel, save, restore, or close"))
            XCTAssertNotEqual(prompt, value.copyRequest)
            XCTAssertFalse(value.closed)
        }
    }
    func testJobOnlyClosePromptUsesExactIdentity() throws {
        let json = #"{"id":"job_fallback","jobId":"job_exact","title":"Run script","documentName":"LeftyNote","state":"unknown","closed":false,"createdAt":1,"updatedAt":2,"blockedBy":[],"blocking":[]}"#
        let value = try JSONDecoder().decode(DesktopTask.self, from: Data(json.utf8))
        XCTAssertTrue(value.prompt(for: .closeTask).contains("task job_exact for LeftyNote"))
        XCTAssertNil(value.conversationURL)
        XCTAssertNotNil(value.conversationUnavailableMessage)
    }
    func testUnavailableConversationExplainsFallbackWithoutGuessingALink() throws {
        XCTAssertNil(try task().conversationUnavailableMessage)
        for value in [try task(agent: "claude_code"), try task(conflict: true), try task(identity: "not-a-conversation")] {
            XCTAssertNil(value.conversationURL)
            XCTAssertTrue(try XCTUnwrap(value.conversationUnavailableMessage).contains("Copy the prompt into your agent"))
            XCTAssertFalse(value.prompt(for: .closeTask).isEmpty)
        }
        XCTAssertTrue(try XCTUnwrap(task(agent: "claude_code").conversationUnavailableMessage).contains("Claude Code"))
        XCTAssertTrue(try XCTUnwrap(task(conflict: true).conversationUnavailableMessage).contains("reliably"))
    }
    func testReadCountPersistsWithoutResolvingTask() throws {
        let suite = "tasks-test-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let open = try task(), closed = try task("old", closed: true, state: "closed")
        var state = DesktopTaskReadState(defaults: defaults, namespace: "fixture")
        state.observe([open, closed])
        XCTAssertTrue(state.isUnread(open)); XCTAssertFalse(state.isUnread(closed))
        state.read(open)
        XCTAssertFalse(state.isUnread(open)); XCTAssertFalse(open.closed)
        let restored = DesktopTaskReadState(defaults: defaults, namespace: "fixture")
        XCTAssertFalse(restored.isUnread(open))
        let other = DesktopTaskReadState(defaults: defaults, namespace: "another-installation")
        XCTAssertTrue(other.isUnread(open))
    }
    func testOlderHistoryPageDoesNotInflateNewTaskCount() throws {
        let suite = "tasks-test-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        var state = DesktopTaskReadState(defaults: defaults, namespace: "fixture")
        let first = try task()
        state.observe([first])
        let old = try task("older-page", closed: true, state: "closed")
        state.observe([first, old])
        XCTAssertFalse(state.isUnread(old)); XCTAssertTrue(state.isUnread(first))
        let resolved = try task(closed: true, state: "closed")
        state.observe([resolved])
        XCTAssertTrue(state.isUnread(resolved))
    }
    func testTasksVisibilityAndFileEventsWakeExistingMonitor() {
        var policy = DesktopMonitorPolicy()
        policy.dashboardVisible = true; policy.surfaces.insert("tasks")
        XCTAssertEqual(policy.interval(busy: false), 5)
        XCTAssertEqual(policy.interval(busy: true), 2)
        let root = URL(fileURLWithPath: "/tmp/task-installation")
        XCTAssertTrue(DesktopJobEvents.isRelevant(path: root.appendingPathComponent("jobs/edit-workflows/edit_a.json").path, root: root))
        XCTAssertTrue(DesktopJobEvents.isRelevant(path: root.appendingPathComponent("jobs/task-origins/edit_a.json").path, root: root))
        XCTAssertFalse(DesktopJobEvents.isRelevant(path: root.appendingPathComponent("jobs/task-origins/secret.txt").path, root: root))
    }
    func testDefaultClosedStatusHasNoCompletedBadge() throws {
        XCTAssertNil(try task(closed: true, state: "closed").statusLabel)
        XCTAssertEqual(try task(state: "unknown").statusLabel, "Outcome unknown")
        XCTAssertEqual(try task(state: "needs_decision").statusLabel, "Needs decision")
    }
    func testClearHistoryPersistsOnlyClosedIdentitiesIncludingUnloadedPages() throws {
        let suite = "tasks-history-test-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let closed = try task("closed", closed: true, state: "closed")
        let unloaded = try task("unloaded", closed: true, state: "failed")
        let open = try task("open", state: "interrupted")
        let running = try task("running", state: "running")
        let index = [closed, unloaded, open, running].map(DesktopTaskReference.init)
        var history = DesktopTaskHistoryState(defaults: defaults, namespace: "fixture")
        history.clearClosed(index)
        XCTAssertEqual(history.clearedIDs, Set(["closed", "unloaded"]))
        let restored = DesktopTaskHistoryState(defaults: defaults, namespace: "fixture")
        XCTAssertFalse(restored.isVisible(closed)); XCTAssertFalse(restored.isVisible(index[1]))
        XCTAssertTrue(restored.isVisible(open)); XCTAssertTrue(restored.isVisible(running))
        XCTAssertFalse(open.closed); XCTAssertEqual(open.state, "interrupted")
        XCTAssertTrue(DesktopTaskHistoryState(defaults: defaults, namespace: "other-installation").isVisible(closed))
    }
    func testNewlyClosedAndReopenedTasksRemainVisibleAfterClearing() throws {
        let suite = "tasks-history-test-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let closed = try task("old", closed: true, state: "closed")
        let newClosed = try task("new", closed: true, state: "closed")
        var history = DesktopTaskHistoryState(defaults: defaults, namespace: "fixture")
        history.clearClosed([DesktopTaskReference(task: closed)])
        history.observeIndex([closed, newClosed].map(DesktopTaskReference.init))
        XCTAssertFalse(history.isVisible(closed)); XCTAssertTrue(history.isVisible(newClosed))
        let reopened = try task("old", state: "needs_decision")
        XCTAssertTrue(history.isVisible(reopened))
        history.observeIndex([DesktopTaskReference(task: reopened)])
        XCTAssertTrue(history.isVisible(closed))
        XCTAssertTrue(DesktopTaskHistoryState(defaults: defaults, namespace: "fixture").isVisible(closed))
    }
    func testRestoringClearedHistoryPreservesReadStateAndUnreadFiltering() throws {
        let suite = "tasks-history-test-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let open = try task("open")
        let closed = try task("old", closed: true, state: "closed")
        var read = DesktopTaskReadState(defaults: defaults, namespace: "fixture")
        read.observe([open])
        let index = [open, closed].map(DesktopTaskReference.init)
        var history = DesktopTaskHistoryState(defaults: defaults, namespace: "fixture")
        XCTAssertEqual(index.filter { history.isVisible($0) && read.isUnread($0) }.count, 2)
        history.clearClosed(index)
        XCTAssertEqual(index.filter { history.isVisible($0) && read.isUnread($0) }.count, 1)
        XCTAssertTrue(read.isUnread(closed))
        history.restore()
        XCTAssertTrue(history.isVisible(closed)); XCTAssertTrue(history.clearedIDs.isEmpty)
        XCTAssertTrue(DesktopTaskHistoryState(defaults: defaults, namespace: "fixture").isVisible(closed))
    }
}

extension DesktopTaskTests {
    func testLegacyClearedHistoryGetsFreshGracePeriodAndPersistentOutbox() throws {
        let suite = "tasks-retention-test-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        defaults.set(["old"], forKey: "taskHistory.v1.fixture")
        let adoption = Date(timeIntervalSince1970: 1_000_000)
        let migrated = DesktopTaskHistoryState(defaults: defaults, namespace: "fixture", now: adoption)
        XCTAssertEqual(migrated.clearedAt["old"], adoption.timeIntervalSince1970)
        XCTAssertEqual(migrated.pendingOperations.map(\.action), ["clear"])
        XCTAssertEqual(migrated.pendingOperations[0].records.map(\.id), ["old"])
        let loaded = DesktopTaskHistoryState(defaults: defaults, namespace: "fixture", now: adoption.addingTimeInterval(86400))
        XCTAssertEqual(loaded.pendingOperations, migrated.pendingOperations)
        XCTAssertEqual(loaded.clearedAt, migrated.clearedAt)
    }
    func testRepeatedClearDoesNotResetDateAndRestoreReclearKeepsOperationOrder() throws {
        let suite = "tasks-retention-test-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let day = Date(timeIntervalSince1970: 1_000_000)
        let index = [DesktopTaskReference(task: try task("closed", closed: true))]
        var state = DesktopTaskHistoryState(defaults: defaults, namespace: "fixture")
        state.clearClosed(index, now: day)
        let first = try XCTUnwrap(state.pendingOperations.first)
        state.clearClosed(index, now: day.addingTimeInterval(86400))
        XCTAssertEqual(state.clearedAt["closed"], day.timeIntervalSince1970)
        XCTAssertEqual(state.pendingOperations.count, 1)
        state.restore(now: day.addingTimeInterval(2*86400))
        state.clearClosed(index, now: day.addingTimeInterval(3*86400))
        XCTAssertEqual(state.pendingOperations.map(\.action), ["clear", "restore", "clear"])
        state.acknowledge(first)
        state.acknowledge(first) // A late duplicate reply must not acknowledge the next operation.
        XCTAssertEqual(state.pendingOperations.map(\.action), ["restore", "clear"])
        let restore = try XCTUnwrap(state.pendingOperations.first)
        state.acknowledge(restore)
        XCTAssertTrue(state.clearedIDs.contains("closed"))
        XCTAssertEqual(state.clearedAt["closed"], day.addingTimeInterval(3*86400).timeIntervalSince1970)
    }
    func testOldCachedHistoryWaitsForServerBeforeRestoringAndMissingExpiredRowsArePruned() throws {
        let suite = "tasks-retention-test-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let start = Date(timeIntervalSince1970: 1_000_000)
        let closed = try task("closed", closed: true)
        var state = DesktopTaskHistoryState(defaults: defaults, namespace: "fixture")
        state.clearClosed([DesktopTaskReference(task: closed)], now: start)
        state.acknowledge(try XCTUnwrap(state.pendingOperations.first))
        state.restore(now: start.addingTimeInterval(31*86400))
        XCTAssertFalse(state.isVisible(closed))
        XCTAssertEqual(state.pendingOperations.map(\.action), ["restore"])
        state.observeIndex([], pruneMissing: true)
        XCTAssertTrue(state.clearedIDs.isEmpty)
    }
    func testClearOutboxChunksLargeHistoryAndLeavesOpenTasksAlone() throws {
        let suite = "tasks-retention-test-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let closed = try (0..<205).map { DesktopTaskReference(task: try task("closed-\($0)", closed: true)) }
        let open = try task("open", state: "interrupted")
        var state = DesktopTaskHistoryState(defaults: defaults, namespace: "fixture")
        state.clearClosed(closed + [DesktopTaskReference(task: open)])
        XCTAssertEqual(state.pendingOperations.map { $0.records.count }, [100, 100, 5])
        XCTAssertTrue(state.isVisible(open)); XCTAssertNil(state.clearedAt[open.id])
    }
    func testHistoryRevisionTravelsWithClearAndLedgerChangesWakeMonitor() throws {
        let revision = String(repeating: "a", count: 64)
        let json = "{\"id\":\"closed\",\"createdAt\":1,\"closed\":true,\"historyRevision\":\"\(revision)\"}"
        let reference = try JSONDecoder().decode(DesktopTaskReference.self, from: Data(json.utf8))
        let suite = "tasks-retention-test-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        var state = DesktopTaskHistoryState(defaults: defaults, namespace: "fixture")
        state.clearClosed([reference])
        XCTAssertEqual(state.pendingOperations[0].records[0].revision, revision)
        let root = URL(fileURLWithPath: "/tmp/task-installation")
        XCTAssertTrue(DesktopJobEvents.isRelevant(path: root.appendingPathComponent("jobs/task-history/ledger.json").path, root: root))
        XCTAssertFalse(DesktopJobEvents.isRelevant(path: root.appendingPathComponent("jobs/task-history/ledger.lock").path, root: root))
    }

    func testRefreshRetainsLoadedHistoryAndDoesNotResetPagination() throws {
        func page(_ ids: [Int]) throws -> DesktopTaskPage {
            let tasks: [[String: Any]] = ids.map { ["id": "old-\($0)", "title": "Spacing", "documentName": "Test", "state": "closed", "closed": true, "createdAt": 1, "updatedAt": 2, "blockedBy": [], "blocking": []] }
            let index: [[String: Any]] = (0..<6).map { ["id": "old-\($0)", "createdAt": 1, "closed": true] }
            let object: [String: Any] = ["version": 1, "observedAt": 3, "tasks": tasks, "index": index, "nextCursor": 2]
            return try JSONDecoder().decode(DesktopTaskPage.self, from: JSONSerialization.data(withJSONObject: object))
        }
        let first = try page([0, 1])
        XCTAssertNil(first.nextHistoryCursor(in: [], ignoring: Set((0..<6).map { "old-\($0)" })))
        XCTAssertEqual(first.nextHistoryCursor(in: [], ignoring: Set(["old-0", "old-1"])), 2)
        var loaded = first.mergingHistory([])
        XCTAssertEqual(first.nextHistoryCursor(in: loaded), 2)
        let second = try page([2, 3])
        loaded = second.mergingHistory(loaded)
        XCTAssertEqual(second.nextHistoryCursor(in: loaded), 4)
        loaded = first.mergingHistory(loaded)
        XCTAssertEqual(loaded.count, 4)
        XCTAssertEqual(first.nextHistoryCursor(in: loaded), 4)
        let final = try page([4, 5])
        loaded = final.mergingHistory(loaded)
        XCTAssertNil(final.nextHistoryCursor(in: loaded))
    }
}
