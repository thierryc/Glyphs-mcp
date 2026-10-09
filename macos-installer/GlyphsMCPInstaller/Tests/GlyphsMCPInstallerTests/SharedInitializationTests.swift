import Foundation
import XCTest
@testable import GlyphsMCPInstallerCore

private final class InitializationCalls: @unchecked Sendable {
    let lock = NSLock()
    private var count = 0
    func next() -> Int { lock.lock(); defer { lock.unlock() }; count += 1; return count }
}

final class SharedInitializationTests: XCTestCase {
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
