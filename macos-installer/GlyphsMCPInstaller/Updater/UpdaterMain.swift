import Foundation

@main
enum GlyphsMCPUpdaterMain {
	static func main() async {
		do {
			let arguments = Array(CommandLine.arguments.dropFirst())
			if arguments == ["probe", "--json"] {
#if DEBUG
				let build = "debug"
#else
				let build = "release"
#endif
				try writeJSON(
					UpdateHelperProbe(build: build),
					to: FileHandle.standardOutput
				)
				return
			}

			let request = try UpdatePrepareRequest.parse(arguments: arguments)
			let task = Task {
				try await UpdateStagingService().prepare(request)
			}
			let signalSource = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .global())
			signal(SIGTERM, SIG_IGN)
			signalSource.setEventHandler {
				task.cancel()
			}
			signalSource.resume()
			defer { signalSource.cancel() }

			let receipt = try await task.value
			try writeJSON(receipt, to: FileHandle.standardOutput)
		} catch {
			let updateError = error as? UpdateStagingError
				?? UpdateStagingError("unexpected", error.localizedDescription)
			let payload = [
				"errorCode": updateError.code,
				"message": updateError.message,
			]
			try? writeJSON(payload, to: FileHandle.standardError)
			exit(updateError.code == "cancelled" ? 130 : 1)
		}
	}

	private static func writeJSON<T: Encodable>(_ value: T, to handle: FileHandle) throws {
		let encoder = JSONEncoder()
		encoder.outputFormatting = [.sortedKeys]
		encoder.dateEncodingStrategy = .iso8601
		var data = try encoder.encode(value)
		data.append(0x0A)
		try handle.write(contentsOf: data)
	}
}
