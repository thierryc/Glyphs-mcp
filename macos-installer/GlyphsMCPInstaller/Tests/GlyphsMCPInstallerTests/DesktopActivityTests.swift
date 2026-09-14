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
