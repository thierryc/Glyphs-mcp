import Foundation

private final class ProcessTimeout {
	private let lock = NSLock()
	private var expired = false
	let error: Error
	init(_ message: String) { error = InstallerError.userFacing(message) }
	func expire() { lock.lock(); expired = true; lock.unlock() }
	func check() throws {
		lock.lock(); let value = expired; lock.unlock()
		if value { throw error }
	}
}

public final class ProcessRunner {
	public struct Result {
		public let exitCode: Int32
		public let stdoutData: Data
		public let stderrData: Data
		public var stdout: String { String(decoding: stdoutData, as: UTF8.self) }
		public var stderr: String { String(decoding: stderrData, as: UTF8.self) }

		init(exitCode: Int32, stdoutData: Data, stderrData: Data) {
			self.exitCode = exitCode
			self.stdoutData = stdoutData
			self.stderrData = stderrData
		}
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
			return Result(exitCode: -1, stdoutData: Data(), stderrData: Data("Failed to run \(executable.path): \(error)".utf8))
		}
		proc.waitUntilExit()

		let stdout = outPipe.fileHandleForReading.readDataToEndOfFile()
		let stderr = errPipe.fileHandleForReading.readDataToEndOfFile()
		return Result(exitCode: proc.terminationStatus, stdoutData: stdout, stderrData: stderr)
	}

	public func runCapturing(
		executable: URL,
		args: [String],
		environment: [String: String]? = nil,
		timeout: TimeInterval
	) async throws -> Result {
		if Task.isCancelled { throw CancellationError() }
		let deadline = ProcessTimeout("Command timed out after \(Self.timeoutDescription(timeout)): \(executable.lastPathComponent).")

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

		let outTask = Task {
			var data = Data()
			do {
				for try await byte in outPipe.fileHandleForReading.bytes {
					data.append(byte)
				}
			} catch {
				// A launch or exit error is reported separately below.
			}
			return data
		}
		let errTask = Task {
			var data = Data()
			do {
				for try await byte in errPipe.fileHandleForReading.bytes {
					data.append(byte)
				}
			} catch {
				// A launch or exit error is reported separately below.
			}
			return data
		}

		let status: Int32
		do {
			status = try await withTaskCancellationHandler(operation: {
				try await withThrowingTaskGroup(of: Int32.self) { group in
					group.addTask {
						try await withCheckedThrowingContinuation { continuation in
							proc.terminationHandler = { process in
								continuation.resume(returning: process.terminationStatus)
							}
							do {
								try proc.run()
								outPipe.fileHandleForWriting.closeFile()
								errPipe.fileHandleForWriting.closeFile()
							} catch {
								outPipe.fileHandleForWriting.closeFile()
								errPipe.fileHandleForWriting.closeFile()
								continuation.resume(throwing: error)
							}
						}
					}
					group.addTask {
						let nanoseconds = UInt64(max(0, timeout) * 1_000_000_000)
						try await Task.sleep(nanoseconds: nanoseconds)
						deadline.expire()
						if proc.isRunning {
							proc.terminate()
						}
						throw deadline.error
					}
					defer { group.cancelAll() }
					guard let first = try await group.next() else {
						throw InstallerError.userFacing("Command did not return a result: \(executable.lastPathComponent)")
					}
					return first
				}
			}, onCancel: {
				if proc.isRunning {
					proc.terminate()
				}
			})
			// Termination can reach the task group before the timeout task throws.
			// Preserve the timeout that initiated it instead of reporting exit 15.
			try deadline.check()
		} catch {
			_ = await outTask.value
			_ = await errTask.value
			if Task.isCancelled { throw CancellationError() }
			throw error
		}

		let stdout = await outTask.value
		let stderr = await errTask.value
		if Task.isCancelled { throw CancellationError() }
		return Result(exitCode: status, stdoutData: stdout, stderrData: stderr)
	}

	public func runStreaming(
		executable: URL,
		args: [String],
		environment: [String: String]? = nil,
		timeout: TimeInterval = 600,
		onLine: @escaping (String) -> Void
	) async throws {
		if Task.isCancelled { throw CancellationError() }
		let deadline = ProcessTimeout("Command timed out after \(Self.timeoutDescription(timeout)): \(executable.lastPathComponent).")

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

		let status: Int32
		do {
			status = try await withTaskCancellationHandler(operation: {
				try await withThrowingTaskGroup(of: Int32.self) { group in
					group.addTask {
						try await withCheckedThrowingContinuation { cont in
							proc.terminationHandler = { p in
								cont.resume(returning: p.terminationStatus)
							}
							do {
								try proc.run()
								outPipe.fileHandleForWriting.closeFile()
								errPipe.fileHandleForWriting.closeFile()
							} catch {
								outPipe.fileHandleForWriting.closeFile()
								errPipe.fileHandleForWriting.closeFile()
								cont.resume(throwing: error)
							}
						}
					}
					group.addTask {
						let nanoseconds = UInt64(max(0, timeout) * 1_000_000_000)
						try await Task.sleep(nanoseconds: nanoseconds)
						deadline.expire()
						if proc.isRunning {
							proc.terminate()
						}
						throw deadline.error
					}

					defer { group.cancelAll() }
					guard let first = try await group.next() else {
						throw InstallerError.userFacing("Command did not return a result: \(executable.lastPathComponent)")
					}
					return first
				}
			}, onCancel: {
				if proc.isRunning {
					proc.terminate()
				}
			})
			try deadline.check()
		} catch {
			_ = await outTask.value
			_ = await errTask.value
			if Task.isCancelled {
				throw CancellationError()
			}
			throw error
		}

		_ = await outTask.value
		_ = await errTask.value
		if Task.isCancelled { throw CancellationError() }

		if status != 0 {
			throw InstallerError.userFacing("Command failed (\(status)): \(executable.lastPathComponent) \(args.joined(separator: " "))")
		}
	}

	private static func timeoutDescription(_ timeout: TimeInterval) -> String {
		if timeout.rounded() == timeout {
			return "\(Int(timeout)) seconds"
		}
		return String(format: "%.1f seconds", timeout)
	}
}
