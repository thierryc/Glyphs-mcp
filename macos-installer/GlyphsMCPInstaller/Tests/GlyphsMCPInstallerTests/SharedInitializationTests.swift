import Foundation
import XCTest
@testable import GlyphsMCPInstallerCore

private final class InitializationCalls: @unchecked Sendable {
    let lock = NSLock()
    private var count = 0
    func next() -> Int { lock.lock(); defer { lock.unlock() }; count += 1; return count }
}

private final class FailedCapture: @unchecked Sendable {
    private let lock = NSLock()
    private var value: ProcessRunner.Result?
    func store(_ result: ProcessRunner.Result) { lock.lock(); defer { lock.unlock() }; value = result }
    func read() -> ProcessRunner.Result? { lock.lock(); defer { lock.unlock() }; return value }
}

final class SharedInitializationTests: XCTestCase {
    private func copy(_ path: String, identifier: String = "com.GeorgSeifert.Glyphs4", major: GlyphsMajorVersion = .v4) -> GlyphsApplicationInfo {
        GlyphsApplicationInfo(majorVersion: major, appURL: URL(fileURLWithPath: path), bundleIdentifier: identifier,
                              shortVersion: major == .v4 ? "4.1.1" : "3.5", displayName: "Glyphs", isBeta: identifier.contains("Beta"))
    }

    func testCopySelectorCountsDistinctGlyphs4CopiesAndPreservesChoice() {
        let stable = copy("/Applications/Glyphs 4.app")
        let duplicate = copy("/Users/tester/Applications/Glyphs 4.app")
        let beta = copy("/Applications/Glyphs Beta.app", identifier: "com.GeorgSeifert.Glyphs4Beta")
        let v3 = copy("/Applications/Glyphs 3.app", identifier: "com.GeorgSeifert.Glyphs3", major: .v3)
        XCTAssertFalse(GlyphsCopySelectionPolicy.showsSelector(for: []))
        XCTAssertFalse(GlyphsCopySelectionPolicy.showsSelector(for: [stable, stable, v3]))
        XCTAssertTrue(GlyphsCopySelectionPolicy.showsSelector(for: [stable, duplicate, beta, v3]))
        XCTAssertEqual(GlyphsCopySelectionPolicy.selected(from: [beta, duplicate, stable], preferredPath: nil), stable)
        XCTAssertEqual(GlyphsCopySelectionPolicy.selected(from: [beta, duplicate, stable], preferredPath: duplicate.appURL.path), duplicate)
        XCTAssertEqual(GlyphsCopySelectionPolicy.selected(from: [beta, stable], preferredPath: duplicate.appURL.path), stable)
    }

    func testSwitchingCopiesDropsOverrideAndRejectsLateChecksIncludingReturnToOriginalCopy() {
        let first = copy("/Applications/Glyphs 4.app")
        let second = copy("/Applications/Glyphs 4 Copy.app")
        var session = GlyphsPythonCheckSession()
        session.bind(first)
        let firstCheck = session.begin()
        session.finish(firstCheck, state: .failed("failed", canSkip: true))
        session.allowUnverifiedInstallation()
        XCTAssertTrue(session.state.allowsInstallation)
        session.bind(second)
        XCTAssertEqual(session.state, .notChecked)
        XCTAssertFalse(session.state.allowsInstallation)
        let secondCheck = session.begin()
        XCTAssertFalse(session.finish(firstCheck, state: .ready("stale")))
        XCTAssertEqual(session.state, .checking)
        XCTAssertTrue(session.finish(secondCheck, state: .ready("3.14.6")))
        XCTAssertFalse(session.bind(second))
        XCTAssertEqual(session.state, .ready("3.14.6"))
        session.bind(first)
        let newFirstCheck = session.begin()
        XCTAssertFalse(session.finish(firstCheck, state: .ready("stale")))
        XCTAssertTrue(session.finish(newFirstCheck, state: .ready("3.14.6")))
    }

    func testDetectedPythonUsesSelectedCheckNativeEvidenceAndIgnoresPrivateRuntime() throws {
        func event(_ values: [String: Any]) throws -> String {
            "GLYPHS_MCP_SETUP:" + String(decoding: try JSONSerialization.data(withJSONObject: values), as: UTF8.self)
        }
        let context = "GLYPHS_MCP_NATIVE_CONTEXT:" + "{\"version\":\"3.14.6\",\"prefix\":\"~/Library/Application Support/Glyphs 4/Repositories/Python/Python.framework/Versions/3.14\"}"
        let diagnostics = try [
            event(["checkId": "old-copy", "event": "python.preference", "selectedPath": "/wrong/Python"]),
            event(["checkId": "new-copy", "event": "python.check-started", "privatePythonVersion": "3.14.7"]),
            event(["checkId": "new-copy", "event": "python.selection", "framework": "/staged/Python"]),
            event(["checkId": "new-copy", "event": "python.native-result", "stdout": context]),
        ].joined(separator: "\n")
        let detected = try XCTUnwrap(GlyphsPythonDetection.parse(diagnostics, checkID: "new-copy"))
        XCTAssertEqual(detected.nativeVersion, "3.14.6")
        XCTAssertTrue(detected.isGlyphsModule)
        XCTAssertFalse(detected.path?.contains("wrong") == true)
        XCTAssertNil(GlyphsPythonDetection.parse(diagnostics, checkID: "unknown"))
        var session = GlyphsPythonCheckSession()
        session.bind(copy("/Applications/Glyphs 4.app"))
        let check = session.begin()
        session.finish(check, state: .ready("3.14.6"), detection: detected)
        session.bind(copy("/Applications/Glyphs Copy.app"))
        XCTAssertNil(session.detection)
    }

    func testDiagnosticEventsKeepCorrelationAndRedactBeforePersistence() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: root) }
        let collector = InstallerLogCollector(logDirectory: root)
        let text = collector.diagnosticEvent("python-check.failed", sessionID: "session-1", operationID: "check-1",
            details: ["path": "/Users/another/Applications/Glyphs 4.app", "stderr": "token=private-value"])
        let payload = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(text.dropFirst("GLYPHS_MCP_SETUP:".count).utf8)) as? [String: Any])
        XCTAssertEqual(payload["sessionId"] as? String, "session-1")
        XCTAssertEqual(payload["checkId"] as? String, "check-1")
        XCTAssertFalse(text.contains("private-value"))
        XCTAssertFalse(text.contains("/Users/another"))
        let logger = InstallerEventLogger(directory: root)
        logger.append("token=unsafe license=private-license /Users/another/Python")
        let saved = try String(contentsOf: logger.fileURL, encoding: .utf8)
        XCTAssertFalse(saved.contains("unsafe"))
        XCTAssertFalse(saved.contains("private-license"))
        XCTAssertFalse(saved.contains("/Users/another"))
    }

    func testCapturingTimeoutRetainsPartialDiagnosticOutput() async throws {
        let captured = FailedCapture()
        do {
            _ = try await ProcessRunner().runCapturing(executable: URL(fileURLWithPath: "/bin/sh"),
                args: ["-c", "printf 'started'; printf 'native stage' >&2; exec /bin/sleep 5"], timeout: 0.2,
                onFailureOutput: { captured.store($0) })
            XCTFail("Expected timeout")
        } catch {
            XCTAssertTrue(error.localizedDescription.contains("timed out"))
        }
        XCTAssertEqual(captured.read()?.stdout, "started")
        XCTAssertEqual(captured.read()?.stderr, "native stage")
    }

    func testUnverifiedPythonNeedsExplicitChoiceAndKeepsFailureDetails() {
        let failure = GlyphsPythonCheckState.failed("Native Python did not start", canSkip: true)
        XCTAssertFalse(failure.allowsInstallation)
        let skipped = failure.allowingUnverifiedInstallation()
        XCTAssertTrue(skipped.allowsInstallation)
        XCTAssertTrue(skipped.isSkipped)
        XCTAssertFalse(skipped.verified)
        XCTAssertNil(skipped.version)
        XCTAssertEqual(skipped.error, failure.error)
    }

    func testOnlyPythonCheckFailuresCanBeSkipped() {
        for state in [GlyphsPythonCheckState.notChecked, .checking,
                      .failed("Invalid payload", canSkip: false)] {
            XCTAssertFalse(state.allowsInstallation)
            XCTAssertFalse(state.canSkip)
            XCTAssertEqual(state.allowingUnverifiedInstallation(), state)
        }
        XCTAssertTrue(GlyphsPythonCheckState.ready("3.14.6").allowsInstallation)
    }

    func testConcurrentCallersShareOneLoadAndCacheResult() async throws {
        let shared = SharedInitialization<Int>()
        let calls = InitializationCalls()
        let load: @Sendable () throws -> Int = { let n = calls.next(); Thread.sleep(forTimeInterval: 0.1); return n }
        async let first = shared.resolve(load)
        async let second = shared.resolve(load)
        let pair = try await (first, second)
        XCTAssertEqual(pair.0, 1)
        XCTAssertEqual(pair.1, 1)
        let cached = try await shared.resolve(load)
        XCTAssertEqual(cached, 1)
    }

    func testFailedLoadCanBeRetried() async throws {
        let shared = SharedInitialization<Int>()
        do {
            _ = try await shared.resolve { throw NSError(domain: "test", code: 1) }
            XCTFail("Expected failure")
        } catch {}
        let recovered = try await shared.resolve { 42 }
        XCTAssertEqual(recovered, 42)
    }

    @MainActor func testSlowDiscoveryDoesNotBlockMainActor() async throws {
        let shared = SharedInitialization<Int>()
        let load = Task { try await shared.resolve { Thread.sleep(forTimeInterval: 0.2); return 1 } }
        let start = Date()
        try await Task.sleep(for: .milliseconds(20))
        XCTAssertLessThan(Date().timeIntervalSince(start), 0.15)
        _ = try await load.value
    }
}
