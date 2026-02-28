import Foundation

public final class ProcessRunner {
	public struct Result {
		public let exitCode: Int32
		public let stdout: String
		public let stderr: String
	}

	public init() {}

	public func runSync(executable: URL, args: [String], environment: [String: String]? = nil) -> String {
		let res = runSyncWithStderr(executable: executable, args: args, environment: environment)
		return res.stdout
	}

	public func runSyncWithStderr(executable: URL, args: [String], environment: [String: String]? = nil) -> Result {
		let proc = Process()
		proc.executableURL = executable
		proc.arguments = args
		if let environment {
			proc.environment = environment
		}

		let outPipe = Pipe()
		let errPipe = Pipe()
		proc.standardOutput = outPipe
		proc.standardError = errPipe

		do {
			try proc.run()
		} catch {
			return Result(exitCode: -1, stdout: "", stderr: "Failed to run \(executable.path): \(error)")
		}
		proc.waitUntilExit()

		let stdout = String(data: outPipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
		let stderr = String(data: errPipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
		return Result(exitCode: proc.terminationStatus, stdout: stdout, stderr: stderr)
	}

	public func runStreaming(executable: URL, args: [String], environment: [String: String]? = nil, onLine: @escaping (String) -> Void) async throws {
		if Task.isCancelled { throw CancellationError() }

		let proc = Process()
		proc.executableURL = executable
		proc.arguments = args
		if let environment {
			proc.environment = environment
		}

		let outPipe = Pipe()
		let errPipe = Pipe()
		proc.standardOutput = outPipe
		proc.standardError = errPipe

		let outHandle = outPipe.fileHandleForReading
		let errHandle = errPipe.fileHandleForReading

		let outTask = Task {
			do {
				for try await line in outHandle.bytes.lines {
					onLine(String(line))
				}
			} catch {
				// Ignore stream errors; termination status will still be checked.
			}
		}
		let errTask = Task {
			do {
				for try await line in errHandle.bytes.lines {
					onLine(String(line))
				}
			} catch {
				// Ignore stream errors; termination status will still be checked.
			}
		}

		let status: Int32 = try await withTaskCancellationHandler {
			if proc.isRunning {
				proc.terminate()
			}
		} operation: {
			try await withCheckedThrowingContinuation { cont in
				proc.terminationHandler = { p in
					cont.resume(returning: p.terminationStatus)
				}
				do {
					try proc.run()
				} catch {
					cont.resume(throwing: error)
				}
			}
		}

		_ = await outTask.value
		_ = await errTask.value
		if Task.isCancelled { throw CancellationError() }

		if status != 0 {
			throw InstallerError.userFacing("Command failed (\(status)): \(executable.lastPathComponent) \(args.joined(separator: " "))")
		}
	}
}
