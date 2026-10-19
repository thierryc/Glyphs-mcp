import Foundation

enum InstallerError: LocalizedError {
    case userFacing(String)
    var errorDescription: String? { if case .userFacing(let text) = self { return text }; return nil }
}

@main struct PoolProbe {
    static func main() async throws {
        let runner = ProcessRunner()
        let mode = CommandLine.arguments[1]
        switch mode {
        case "capture":
            let result = try await runner.runCapturing(executable: URL(fileURLWithPath: "/bin/sh"),
                args: ["-c", "printf 'output'; printf 'diagnostic' >&2; exit 7"], timeout: 2)
            precondition(result.exitCode == 7 && result.stdout == "output" && result.stderr == "diagnostic")
        case "timeout":
            do {
                _ = try await runner.runCapturing(executable: URL(fileURLWithPath: "/bin/sleep"), args: ["5"], timeout: 0.1)
                fatalError("Missing timeout")
            } catch { precondition(error.localizedDescription.contains("timed out")) }
        case "cancel":
            let task = Task {
                try await runner.runCapturing(executable: URL(fileURLWithPath: "/bin/sleep"), args: ["5"], timeout: 4)
            }
            try await Task.sleep(nanoseconds: 100_000_000)
            task.cancel()
            do { _ = try await task.value; fatalError("Missing cancellation") }
            catch is CancellationError { }
        case "limit":
            do {
                _ = try await runner.runCapturing(executable: URL(fileURLWithPath: "/usr/bin/yes"), args: [],
                                                  timeout: 2, maximumStandardOutputBytes: 128)
                fatalError("Missing output limit")
            } catch let error as ProcessOutputLimitError { precondition(error.limit == 128 && error.observedAtLeast > 128) }
        case "launch-failure":
            do {
                _ = try await runner.runCapturing(executable: URL(fileURLWithPath: "/gmcp-test-missing-executable"), args: [], timeout: 2)
                fatalError("Missing launch failure")
            } catch { precondition(!error.localizedDescription.contains("timed out")) }
        default: fatalError("Unknown probe")
        }
        print("passed:\(mode)")
    }
}
