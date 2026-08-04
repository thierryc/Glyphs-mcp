import CryptoKit
import Foundation

public enum UpdateHelperProtocol {
	public static let currentVersion = 1
	public static let helperVersion = "1.0.0"
	public static let expectedTeamIdentifier = "N9U29A4T8J"
	public static let expectedDeveloperIDAuthority = "Developer ID Application: Thierry Charbonnel (N9U29A4T8J)"
	public static let executableName = "GlyphsMCPUpdater"
	public static let optInDefaultsKey = "com.ap.cx.glyphs-mcp.inAppUpdatesEnabled"
	public static let managedMarker = "cx.ap.glyphs-mcp-updater-v1"
}

public struct UpdateHelperProbe: Codable, Equatable {
	public let protocolVersion: Int
	public let helperVersion: String
	public let teamIdentifier: String
	public let capabilities: [String]
	public let build: String

	public init(
		protocolVersion: Int = UpdateHelperProtocol.currentVersion,
		helperVersion: String = UpdateHelperProtocol.helperVersion,
		teamIdentifier: String = UpdateHelperProtocol.expectedTeamIdentifier,
		capabilities: [String] = ["prepare"],
		build: String
	) {
		self.protocolVersion = protocolVersion
		self.helperVersion = helperVersion
		self.teamIdentifier = teamIdentifier
		self.capabilities = capabilities
		self.build = build
	}
}

public enum UpdatePreparationPhase: String, Codable, Equatable {
	case resolving
	case downloading
	case verifying
	case preparing
	case ready
	case failed
	case cancelled
}

public struct UpdatePreparationStatus: Codable, Equatable {
	public let protocolVersion: Int
	public let requestID: String
	public let version: String
	public let glyphsMajor: Int
	public let phase: UpdatePreparationPhase
	public let errorCode: String?
	public let message: String?
	public let updatedAt: Date

	public init(
		requestID: String,
		version: String,
		glyphsMajor: Int,
		phase: UpdatePreparationPhase,
		errorCode: String? = nil,
		message: String? = nil,
		updatedAt: Date = Date()
	) {
		self.protocolVersion = UpdateHelperProtocol.currentVersion
		self.requestID = requestID
		self.version = version
		self.glyphsMajor = glyphsMajor
		self.phase = phase
		self.errorCode = errorCode
		self.message = message
		self.updatedAt = updatedAt
	}
}

public struct UpdateStageReceipt: Codable, Equatable {
	public let protocolVersion: Int
	public let version: String
	public let tag: String
	public let assetName: String
	public let assetSHA256: String
	public let pluginCDHash: String
	public let teamIdentifier: String
	public let helperVersion: String
	public let preparedAt: Date
}

public struct UpdateAuthorizationReceipt: Codable, Equatable {
	public let protocolVersion: Int
	public let requestID: String
	public let version: String
	public let glyphsMajor: Int
	public let authorizedAt: Date
}

public struct UpdateVerifiedPlugin: Equatable {
	public let bundleURL: URL
	public let version: String
	public let cdHash: String
	public let teamIdentifier: String
	public let authority: String

	public init(
		bundleURL: URL,
		version: String,
		cdHash: String,
		teamIdentifier: String,
		authority: String
	) {
		self.bundleURL = bundleURL
		self.version = version
		self.cdHash = cdHash
		self.teamIdentifier = teamIdentifier
		self.authority = authority
	}
}

public struct UpdatePrepareRequest: Equatable {
	public let protocolVersion: Int
	public let version: String
	public let glyphsMajor: Int
	public let requestID: UUID

	public init(protocolVersion: Int, version: String, glyphsMajor: Int, requestID: UUID) throws {
		guard protocolVersion == UpdateHelperProtocol.currentVersion else {
			throw UpdateStagingError("invalid_protocol", "Unsupported updater protocol.")
		}
		guard Self.isStrictVersion(version) else {
			throw UpdateStagingError("invalid_version", "Update version must be MAJOR.MINOR.PATCH.")
		}
		guard glyphsMajor == 3 || glyphsMajor == 4 else {
			throw UpdateStagingError("invalid_glyphs_version", "Glyphs major version must be 3 or 4.")
		}
		self.protocolVersion = protocolVersion
		self.version = version
		self.glyphsMajor = glyphsMajor
		self.requestID = requestID
	}

	public static func parse(arguments: [String]) throws -> UpdatePrepareRequest {
		guard arguments.first == "prepare" else {
			throw UpdateStagingError("invalid_command", "Expected the prepare command.")
		}
		let optionArguments = Array(arguments.dropFirst())
		guard optionArguments.count == 8, optionArguments.count.isMultiple(of: 2) else {
			throw UpdateStagingError("invalid_arguments", "Prepare requires protocol, version, Glyphs major, and request ID.")
		}
		var options: [String: String] = [:]
		for index in stride(from: 0, to: optionArguments.count, by: 2) {
			let key = optionArguments[index]
			guard ["--protocol", "--version", "--glyphs-major", "--request-id"].contains(key),
				  options[key] == nil else {
				throw UpdateStagingError("invalid_arguments", "Prepare contains an unknown or duplicate option.")
			}
			options[key] = optionArguments[index + 1]
		}
		guard
			let protocolText = options["--protocol"],
			let protocolVersion = Int(protocolText),
			let version = options["--version"],
			let glyphsText = options["--glyphs-major"],
			let glyphsMajor = Int(glyphsText),
			let requestText = options["--request-id"],
			let requestID = UUID(uuidString: requestText),
			requestID.uuidString.lowercased() == requestText.lowercased()
		else {
			throw UpdateStagingError("invalid_arguments", "Prepare contains an invalid option value.")
		}
		return try UpdatePrepareRequest(
			protocolVersion: protocolVersion,
			version: version,
			glyphsMajor: glyphsMajor,
			requestID: requestID
		)
	}

	public static func isStrictVersion(_ value: String) -> Bool {
		value.range(
			of: #"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"#,
			options: .regularExpression
		) != nil
	}
}

public struct UpdateStagingError: LocalizedError, Equatable {
	public let code: String
	public let message: String

	public init(_ code: String, _ message: String) {
		self.code = code
		self.message = message
	}

	public var errorDescription: String? { message }
}

public struct UpdateStagingPaths {
	public let home: URL

	public init(home: URL = FileManager.default.homeDirectoryForCurrentUser) {
		self.home = home
	}

	public var root: URL {
		home.appendingPathComponent("Library/Application Support/Glyphs MCP/Updater", isDirectory: true)
	}
	public var helperExecutable: URL { root.appendingPathComponent(UpdateHelperProtocol.executableName) }
	public var managedMarker: URL { root.appendingPathComponent(".managed-by-glyphs-mcp") }
	public var installReceipt: URL { root.appendingPathComponent("InstallReceipt.json") }
	public var requests: URL { root.appendingPathComponent("Requests", isDirectory: true) }
	public var staged: URL { root.appendingPathComponent("Staged", isDirectory: true) }
	public var authorizations: URL { root.appendingPathComponent("Authorizations", isDirectory: true) }
	public var temporary: URL { root.appendingPathComponent("Temporary", isDirectory: true) }

	public func requestStatus(_ requestID: UUID) -> URL {
		requests.appendingPathComponent("\(requestID.uuidString.lowercased()).json")
	}

	public func stagedVersion(_ version: String) -> URL {
		staged.appendingPathComponent("v\(version)", isDirectory: true)
	}

	public func stagedPlugin(_ version: String) -> URL {
		stagedVersion(version).appendingPathComponent("Glyphs MCP.glyphsPlugin", isDirectory: true)
	}

	public func stageReceipt(_ version: String) -> URL {
		stagedVersion(version).appendingPathComponent("receipt.json")
	}

	public func authorization(version: String, glyphsMajor: Int) -> URL {
		authorizations
			.appendingPathComponent("v\(version)", isDirectory: true)
			.appendingPathComponent("glyphs-\(glyphsMajor).json")
	}
}

public protocol UpdateHTTPClienting {
	func data(from url: URL, timeout: TimeInterval, maximumBytes: Int) async throws -> Data
}

public struct UpdateURLSessionClient: UpdateHTTPClienting {
	public init() {}

	public func data(from url: URL, timeout: TimeInterval, maximumBytes: Int) async throws -> Data {
		var request = URLRequest(url: url)
		request.timeoutInterval = timeout
		request.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
		request.setValue("Glyphs-MCP-Updater/\(UpdateHelperProtocol.helperVersion)", forHTTPHeaderField: "User-Agent")
		return try await UpdateBoundedURLSession.fetch(
			request,
			timeout: timeout,
			maximumBytes: maximumBytes
		)
	}
}

private final class UpdateBoundedURLSession: NSObject, URLSessionDataDelegate, URLSessionTaskDelegate, @unchecked Sendable {
	private let maximumBytes: Int
	private let initialHost: String?
	private let lock = NSLock()
	private var buffer = Data()
	private var continuation: CheckedContinuation<Data, Error>?
	private var session: URLSession?
	private var completed = false

	private init(maximumBytes: Int, initialHost: String?) {
		self.maximumBytes = maximumBytes
		self.initialHost = initialHost
	}

	static func fetch(
		_ request: URLRequest,
		timeout: TimeInterval,
		maximumBytes: Int
	) async throws -> Data {
		guard maximumBytes > 0 else {
			throw UpdateStagingError("size_limit", "The update response size limit is invalid.")
		}
		let delegate = UpdateBoundedURLSession(
			maximumBytes: maximumBytes,
			initialHost: request.url?.host?.lowercased()
		)
		return try await withTaskCancellationHandler {
			try await withCheckedThrowingContinuation { continuation in
				delegate.begin(
					request,
					timeout: timeout,
					continuation: continuation
				)
			}
		} onCancel: {
			delegate.cancel()
		}
	}

	private func begin(
		_ request: URLRequest,
		timeout: TimeInterval,
		continuation: CheckedContinuation<Data, Error>
	) {
		lock.lock()
		guard !completed else {
			lock.unlock()
			continuation.resume(throwing: CancellationError())
			return
		}
		self.continuation = continuation
		let configuration = URLSessionConfiguration.ephemeral
		configuration.timeoutIntervalForRequest = timeout
		configuration.timeoutIntervalForResource = timeout
		configuration.httpCookieStorage = nil
		configuration.urlCache = nil
		let session = URLSession(configuration: configuration, delegate: self, delegateQueue: nil)
		self.session = session
		lock.unlock()
		session.dataTask(with: request).resume()
	}

	private func cancel() {
		lock.lock()
		guard !completed else {
			lock.unlock()
			return
		}
		completed = true
		let continuation = continuation
		self.continuation = nil
		let session = session
		self.session = nil
		lock.unlock()
		session?.invalidateAndCancel()
		continuation?.resume(throwing: CancellationError())
	}

	func urlSession(
		_ session: URLSession,
		dataTask: URLSessionDataTask,
		didReceive response: URLResponse,
		completionHandler: @escaping (URLSession.ResponseDisposition) -> Void
	) {
		guard let http = response as? HTTPURLResponse,
			  (200...299).contains(http.statusCode) else {
			completionHandler(.cancel)
			finish(.failure(UpdateStagingError("network", "The update server returned an unexpected response.")))
			return
		}
		if http.expectedContentLength > Int64(maximumBytes) {
			completionHandler(.cancel)
			finish(.failure(UpdateStagingError("size_limit", "The update response exceeds the allowed size.")))
			return
		}
		completionHandler(.allow)
	}

	func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
		lock.lock()
		guard !completed else {
			lock.unlock()
			return
		}
		if buffer.count > maximumBytes - data.count {
			lock.unlock()
			dataTask.cancel()
			finish(.failure(UpdateStagingError("size_limit", "The update response exceeds the allowed size.")))
			return
		}
		buffer.append(data)
		lock.unlock()
	}

	func urlSession(
		_ session: URLSession,
		task: URLSessionTask,
		willPerformHTTPRedirection response: HTTPURLResponse,
		newRequest request: URLRequest,
		completionHandler: @escaping (URLRequest?) -> Void
	) {
		guard let url = request.url, url.scheme == "https", let host = url.host?.lowercased() else {
			completionHandler(nil)
			finish(.failure(UpdateStagingError("network", "The update server attempted an unsafe redirect.")))
			return
		}
		let githubRedirect = host == "github.com"
			|| host.hasSuffix(".githubusercontent.com")
		let sameHost = host == initialHost
		guard githubRedirect || sameHost else {
			completionHandler(nil)
			finish(.failure(UpdateStagingError("network", "The update server attempted an untrusted redirect.")))
			return
		}
		completionHandler(request)
	}

	func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
		if let error {
			if (error as NSError).code == NSURLErrorCancelled {
				lock.lock()
				let alreadyCompleted = completed
				lock.unlock()
				if alreadyCompleted { return }
			}
			finish(.failure(UpdateStagingError("network", "The update request failed: \(error.localizedDescription)")))
		} else {
			lock.lock()
			let data = buffer
			lock.unlock()
			finish(.success(data))
		}
	}

	private func finish(_ result: Result<Data, Error>) {
		lock.lock()
		guard !completed else {
			lock.unlock()
			return
		}
		completed = true
		let continuation = continuation
		self.continuation = nil
		let session = session
		self.session = nil
		lock.unlock()
		session?.finishTasksAndInvalidate()
		continuation?.resume(with: result)
	}
}

public struct UpdateCommandRunner {
	public let run: @Sendable (URL, [String]) throws -> String

	public init(run: @escaping @Sendable (URL, [String]) throws -> String) {
		self.run = run
	}

	public static let live = UpdateCommandRunner { executable, arguments in
		let process = Process()
		process.executableURL = executable
		process.arguments = arguments
		let pipe = Pipe()
		process.standardOutput = pipe
		process.standardError = pipe
		do {
			try process.run()
			let data = pipe.fileHandleForReading.readDataToEndOfFile()
			process.waitUntilExit()
			let output = String(data: data, encoding: .utf8) ?? ""
			guard process.terminationStatus == 0 else {
				throw UpdateStagingError(
					"verification",
					"\(executable.lastPathComponent) rejected the update: \(String(output.trimmingCharacters(in: .whitespacesAndNewlines).prefix(2_000)))"
				)
			}
			return output
		} catch {
			if let updateError = error as? UpdateStagingError { throw updateError }
			throw UpdateStagingError(
				"verification",
				"Could not run \(executable.lastPathComponent): \(error.localizedDescription)"
			)
		}
	}
}

public struct UpdateTrustVerifier {
	public let verifyArchive: @Sendable (URL, String) throws -> UpdateVerifiedPlugin
	public let verifyPlugin: @Sendable (URL, String) throws -> UpdateVerifiedPlugin

	public init(
		verifyArchive: @escaping @Sendable (URL, String) throws -> UpdateVerifiedPlugin,
		verifyPlugin: @escaping @Sendable (URL, String) throws -> UpdateVerifiedPlugin
	) {
		self.verifyArchive = verifyArchive
		self.verifyPlugin = verifyPlugin
	}

	public static func live(
		runner: UpdateCommandRunner = .live,
		allowDevelopmentSignature: Bool = false
	) -> UpdateTrustVerifier {
		let command: @Sendable (String, [String]) throws -> String = { path, arguments in
			try runner.run(URL(fileURLWithPath: path), arguments)
		}

		let details: @Sendable (URL) throws -> String = { subject in
			try command("/usr/bin/codesign", ["-d", "--verbose=4", subject.path])
		}

		let field: @Sendable (String, String) -> String? = { name, details in
			details
				.split(separator: "\n")
				.map(String.init)
				.first(where: { $0.hasPrefix("\(name)=") })?
				.dropFirst(name.count + 1)
				.description
		}

		let verifyPlugin: @Sendable (URL, String) throws -> UpdateVerifiedPlugin = { plugin, expectedVersion in
			let executable = plugin.appendingPathComponent("Contents/MacOS/plugin")
			guard FileManager.default.fileExists(atPath: executable.path) else {
				throw UpdateStagingError("signature", "The signed plug-in executable is missing.")
			}
			_ = try command("/usr/bin/codesign", ["--verify", "--deep", "--strict", "--verbose=2", plugin.path])
			let signatureDetails = try details(executable)
			guard field("TeamIdentifier", signatureDetails) == UpdateHelperProtocol.expectedTeamIdentifier else {
				throw UpdateStagingError("signature", "The plug-in is not signed by the expected developer team.")
			}
			let authority = field("Authority", signatureDetails) ?? ""
			let trustedAuthority = authority == UpdateHelperProtocol.expectedDeveloperIDAuthority
			let allowedDevelopmentAuthority = allowDevelopmentSignature && authority.hasPrefix("Apple Development:")
			guard trustedAuthority || allowedDevelopmentAuthority else {
				throw UpdateStagingError("signature", "The plug-in has an unexpected signing authority.")
			}
			guard signatureDetails.range(of: #"flags=.*\(runtime\)"#, options: .regularExpression) != nil else {
				throw UpdateStagingError("signature", "The plug-in signature is missing the hardened runtime.")
			}
			if !allowDevelopmentSignature {
				guard signatureDetails.split(separator: "\n").contains(where: { $0.hasPrefix("Timestamp=") }) else {
					throw UpdateStagingError("signature", "The plug-in signature is missing a secure timestamp.")
				}
				_ = try command("/usr/bin/xcrun", ["stapler", "validate", plugin.path])
			}
			let info = plugin.appendingPathComponent("Contents/Info.plist")
			guard
				let data = try? Data(contentsOf: info),
				let plist = try? PropertyListSerialization.propertyList(from: data, format: nil) as? [String: Any],
				(plist["CFBundleShortVersionString"] as? String) == expectedVersion
			else {
				throw UpdateStagingError("version", "The plug-in version does not match the authorized release.")
			}
			guard let cdHash = field("CDHash", signatureDetails), !cdHash.isEmpty else {
				throw UpdateStagingError("signature", "The plug-in signature has no CDHash.")
			}
			return UpdateVerifiedPlugin(
				bundleURL: plugin,
				version: expectedVersion,
				cdHash: cdHash,
				teamIdentifier: UpdateHelperProtocol.expectedTeamIdentifier,
				authority: authority
			)
		}

		let verifyArchive: @Sendable (URL, String) throws -> UpdateVerifiedPlugin = { extractedRoot, expectedVersion in
			let app = extractedRoot.appendingPathComponent("GlyphsMCPInstaller.app", isDirectory: true)
			guard FileManager.default.fileExists(atPath: app.path) else {
				throw UpdateStagingError("archive", "The release archive does not contain GlyphsMCPInstaller.app.")
			}
			_ = try command("/usr/bin/codesign", ["--verify", "--deep", "--strict", "--verbose=2", app.path])
			let appDetails = try details(app)
			guard field("TeamIdentifier", appDetails) == UpdateHelperProtocol.expectedTeamIdentifier else {
				throw UpdateStagingError("signature", "The installer is not signed by the expected developer team.")
			}
			let appAuthority = field("Authority", appDetails) ?? ""
			let trustedAuthority = appAuthority == UpdateHelperProtocol.expectedDeveloperIDAuthority
			let allowedDevelopmentAuthority = allowDevelopmentSignature && appAuthority.hasPrefix("Apple Development:")
			guard trustedAuthority || allowedDevelopmentAuthority else {
				throw UpdateStagingError("signature", "The installer has an unexpected signing authority.")
			}
			guard appDetails.range(of: #"flags=.*\(runtime\)"#, options: .regularExpression) != nil else {
				throw UpdateStagingError("signature", "The installer signature is missing the hardened runtime.")
			}
			if !allowDevelopmentSignature {
				guard appDetails.split(separator: "\n").contains(where: { $0.hasPrefix("Timestamp=") }) else {
					throw UpdateStagingError("signature", "The installer signature is missing a secure timestamp.")
				}
				_ = try command("/usr/bin/xcrun", ["stapler", "validate", app.path])
				_ = try command("/usr/sbin/spctl", ["--assess", "--type", "execute", "--verbose=2", app.path])
			}
			guard
				let appVersion = Bundle(url: app)?
					.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String,
				appVersion == expectedVersion
			else {
				throw UpdateStagingError("version", "The installer version does not match the authorized release.")
			}

			let resources = app.appendingPathComponent("Contents/Resources", isDirectory: true)
			let directPayload = resources.appendingPathComponent("Payload", isDirectory: true)
			let plugin: URL
			if FileManager.default.fileExists(atPath: directPayload.path) {
				plugin = directPayload.appendingPathComponent("Glyphs MCP.glyphsPlugin", isDirectory: true)
			} else {
				let archive = resources.appendingPathComponent("Payload.gmcparchive")
				guard FileManager.default.fileExists(atPath: archive.path) else {
					throw UpdateStagingError("archive", "The signed installer payload is missing.")
				}
				let listing = try command("/usr/bin/tar", ["-tzf", archive.path])
				let entries = listing.split(whereSeparator: \.isNewline).map(String.init)
				guard !entries.isEmpty,
					  entries.contains("Payload/Glyphs MCP.glyphsPlugin/Contents/Info.plist") else {
					throw UpdateStagingError("archive", "The signed installer payload archive is malformed.")
				}
				for rawEntry in entries {
					let entry = rawEntry.hasSuffix("/") ? String(rawEntry.dropLast()) : rawEntry
					let components = entry.split(separator: "/", omittingEmptySubsequences: false)
					guard
						!entry.isEmpty,
						!entry.hasPrefix("/"),
						!entry.contains("\\"),
						!components.contains(where: { $0.isEmpty || $0 == "." || $0 == ".." }),
						entry == "Payload" || entry.hasPrefix("Payload/")
					else {
						throw UpdateStagingError("archive", "The signed installer payload contains an unsafe path.")
					}
				}
				let payloadRoot = extractedRoot.appendingPathComponent(".payload-\(UUID().uuidString)", isDirectory: true)
				try FileManager.default.createDirectory(at: payloadRoot, withIntermediateDirectories: true, attributes: nil)
				_ = try command("/usr/bin/tar", ["-xzf", archive.path, "-C", payloadRoot.path])
				try UpdateExtractedTreeValidator.validate(payloadRoot)
				plugin = payloadRoot
					.appendingPathComponent("Payload", isDirectory: true)
					.appendingPathComponent("Glyphs MCP.glyphsPlugin", isDirectory: true)
			}
			guard FileManager.default.fileExists(atPath: plugin.path) else {
				throw UpdateStagingError("archive", "The signed installer payload does not contain the plug-in.")
			}
			return try verifyPlugin(plugin, expectedVersion)
		}

		return UpdateTrustVerifier(
			verifyArchive: verifyArchive,
			verifyPlugin: { plugin, version in
				try verifyPlugin(plugin, version)
			}
		)
	}
}

public struct UpdatePublishedRelease: Decodable, Equatable {
	public struct Asset: Decodable, Equatable {
		public let name: String
		public let browserDownloadURL: URL

		enum CodingKeys: String, CodingKey {
			case name
			case browserDownloadURL = "browser_download_url"
		}
	}

	public let tagName: String
	public let draft: Bool
	public let prerelease: Bool
	public let publishedAt: String?
	public let assets: [Asset]

	enum CodingKeys: String, CodingKey {
		case tagName = "tag_name"
		case draft
		case prerelease
		case publishedAt = "published_at"
		case assets
	}

	public static func parse(
		_ data: Data,
		expectedVersion: String,
		allowLoopbackAssets: Bool = false
	) throws -> UpdatePublishedRelease {
		let release: UpdatePublishedRelease
		do {
			release = try JSONDecoder().decode(UpdatePublishedRelease.self, from: data)
		} catch {
			throw UpdateStagingError("release_metadata", "Release metadata could not be parsed.")
		}
		guard release.tagName == "v\(expectedVersion)",
			  !release.draft,
			  !release.prerelease,
			  release.publishedAt?.isEmpty == false else {
			throw UpdateStagingError("release_metadata", "Release metadata does not describe the authorized stable version.")
		}
		_ = try release.requiredAsset(named: "GlyphsMCPInstaller.zip", allowLoopback: allowLoopbackAssets)
		_ = try release.requiredAsset(named: "SHA256SUMS", allowLoopback: allowLoopbackAssets)
		return release
	}

	public func requiredAsset(named name: String, allowLoopback: Bool = false) throws -> Asset {
		let matches = assets.filter { $0.name == name }
		guard matches.count == 1, let asset = matches.first else {
			throw UpdateStagingError(
				"release_asset",
				matches.isEmpty ? "The release is missing \(name)." : "The release contains duplicate \(name) assets."
			)
		}
		let url = asset.browserDownloadURL
		let trustedGitHub = url.scheme == "https"
			&& url.host == "github.com"
			&& url.path == "/thierryc/Glyphs-mcp/releases/download/\(tagName)/\(name)"
			&& url.query == nil
			&& url.fragment == nil
		let loopbackHost = url.host == "127.0.0.1" || url.host == "localhost"
		let trustedLoopback = allowLoopback && url.scheme == "http" && loopbackHost
		guard (trustedGitHub || trustedLoopback), url.lastPathComponent == name else {
			throw UpdateStagingError("release_asset", "The release contains an untrusted download URL for \(name).")
		}
		return asset
	}
}

public enum UpdateChecksumManifest {
	public static func expectedSHA256(_ data: Data, assetName: String) throws -> String {
		guard !assetName.contains("/"), !assetName.contains("\\") else {
			throw UpdateStagingError("checksum", "The release asset name is unsafe.")
		}
		guard let manifest = String(data: data, encoding: .utf8) else {
			throw UpdateStagingError("checksum", "The checksum manifest is not UTF-8.")
		}
		let matches = manifest.split(whereSeparator: \.isNewline).compactMap { rawLine -> String? in
			let parts = rawLine.split(maxSplits: 1, whereSeparator: \.isWhitespace).map(String.init)
			guard parts.count == 2 else { return nil }
			let logicalPath = parts[1].trimmingCharacters(in: CharacterSet(charactersIn: " *"))
			let components = logicalPath.split(separator: "/", omittingEmptySubsequences: false)
			guard
				!logicalPath.hasPrefix("/"),
				!logicalPath.contains("\\"),
				!components.contains(".."),
				components.last.map(String.init) == assetName
			else { return nil }
			return parts[0].lowercased()
		}
		guard matches.count == 1, let expected = matches.first else {
			throw UpdateStagingError(
				"checksum",
				matches.isEmpty ? "The checksum manifest does not list \(assetName)." : "The checksum manifest lists \(assetName) more than once."
			)
		}
		guard expected.range(of: #"^[0-9a-f]{64}$"#, options: .regularExpression) != nil else {
			throw UpdateStagingError("checksum", "The checksum manifest contains an invalid SHA-256.")
		}
		return expected
	}

	public static func sha256(_ data: Data) -> String {
		SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
	}
}

public enum UpdateZipValidator {
	public static func validate(
		_ data: Data,
		expectedRoot: String = "GlyphsMCPInstaller.app",
		maximumEntries: Int = 100_000,
		maximumUncompressedBytes: UInt64 = 512 * 1024 * 1024
	) throws {
		guard data.count >= 22 else {
			throw UpdateStagingError("archive", "The installer ZIP is truncated.")
		}
		let bytes = [UInt8](data)
		let minimumEOCD = max(0, bytes.count - 65_557)
		var endOffset: Int?
		if bytes.count >= 22 {
			for offset in stride(from: bytes.count - 22, through: minimumEOCD, by: -1) {
				if uint32(bytes, offset) == 0x0605_4b50 {
					endOffset = offset
					break
				}
			}
		}
		guard let endOffset else {
			throw UpdateStagingError("archive", "The installer ZIP has no valid end record.")
		}
		guard
			uint16(bytes, endOffset + 4) == 0,
			uint16(bytes, endOffset + 6) == 0
		else {
			throw UpdateStagingError("archive", "Multi-disk installer ZIPs are not supported.")
		}
		let entryCount = Int(uint16(bytes, endOffset + 10))
		guard entryCount > 0,
			  entryCount == Int(uint16(bytes, endOffset + 8)),
			  entryCount <= maximumEntries else {
			throw UpdateStagingError("archive", "The installer ZIP has an invalid entry count.")
		}
		let centralSize = Int(uint32(bytes, endOffset + 12))
		let centralOffset = Int(uint32(bytes, endOffset + 16))
		let commentLength = Int(uint16(bytes, endOffset + 20))
		guard
			endOffset + 22 + commentLength == bytes.count,
			centralOffset >= 0,
			centralSize >= 0,
			centralOffset + centralSize == endOffset
		else {
			throw UpdateStagingError("archive", "The installer ZIP central directory is inconsistent.")
		}

		var cursor = centralOffset
		var names = Set<String>()
		var totalUncompressed: UInt64 = 0
		var containsInstallerInfo = false
		for _ in 0..<entryCount {
			guard cursor + 46 <= endOffset, uint32(bytes, cursor) == 0x0201_4b50 else {
				throw UpdateStagingError("archive", "The installer ZIP central directory is malformed.")
			}
			let flags = uint16(bytes, cursor + 8)
			guard flags & 0x0001 == 0 else {
				throw UpdateStagingError("archive", "Encrypted installer ZIP entries are not supported.")
			}
			let compressedSize = UInt64(uint32(bytes, cursor + 20))
			let uncompressedSize = UInt64(uint32(bytes, cursor + 24))
			let nameLength = Int(uint16(bytes, cursor + 28))
			let extraLength = Int(uint16(bytes, cursor + 30))
			let entryCommentLength = Int(uint16(bytes, cursor + 32))
			let externalAttributes = uint32(bytes, cursor + 38)
			let localOffset = Int(uint32(bytes, cursor + 42))
			let next = cursor + 46 + nameLength + extraLength + entryCommentLength
			guard nameLength > 0, next <= endOffset, localOffset + 30 <= centralOffset,
				  uint32(bytes, localOffset) == 0x0403_4b50 else {
				throw UpdateStagingError("archive", "The installer ZIP contains an invalid entry.")
			}
			let nameData = Data(bytes[(cursor + 46)..<(cursor + 46 + nameLength)])
			guard let name = String(data: nameData, encoding: .utf8) else {
				throw UpdateStagingError("archive", "The installer ZIP contains a non-UTF-8 path.")
			}
			try validateEntryName(name, expectedRoot: expectedRoot)
			guard names.insert(name).inserted else {
				throw UpdateStagingError("archive", "The installer ZIP contains duplicate paths.")
			}

			let unixMode = UInt16((externalAttributes >> 16) & 0xffff)
			let fileType = unixMode & 0xf000
			if fileType != 0 && fileType != 0x8000 && fileType != 0x4000 {
				throw UpdateStagingError("archive", "The installer ZIP contains a link or special file.")
			}
			let isDirectory = name.hasSuffix("/")
			if isDirectory && uncompressedSize != 0 {
				throw UpdateStagingError("archive", "The installer ZIP contains an invalid directory entry.")
			}
			if compressedSize > 128 * 1024 * 1024 {
				throw UpdateStagingError("size_limit", "A compressed installer ZIP entry is too large.")
			}
			totalUncompressed += uncompressedSize
			guard totalUncompressed <= maximumUncompressedBytes else {
				throw UpdateStagingError("size_limit", "The expanded installer ZIP is too large.")
			}
			if name == "\(expectedRoot)/Contents/Info.plist" {
				containsInstallerInfo = true
			}
			cursor = next
		}
		guard cursor == endOffset, containsInstallerInfo else {
			throw UpdateStagingError("archive", "The installer ZIP does not contain the expected installer app.")
		}
	}

	public static func validateEntryName(
		_ rawName: String,
		expectedRoot: String = "GlyphsMCPInstaller.app"
	) throws {
		guard !rawName.isEmpty,
			  !rawName.contains("\0"),
			  !rawName.contains("\\"),
			  !rawName.hasPrefix("/") else {
			throw UpdateStagingError("archive", "The installer ZIP contains an unsafe path.")
		}
		let name = rawName.hasSuffix("/") ? String(rawName.dropLast()) : rawName
		let components = name.split(separator: "/", omittingEmptySubsequences: false)
		guard !components.isEmpty,
			  !components.contains(where: { $0.isEmpty || $0 == "." || $0 == ".." }),
			  name == expectedRoot || name.hasPrefix(expectedRoot + "/") else {
			throw UpdateStagingError("archive", "The installer ZIP contains a path outside the installer app.")
		}
	}

	private static func uint16(_ bytes: [UInt8], _ offset: Int) -> UInt16 {
		guard offset >= 0, offset + 2 <= bytes.count else { return 0 }
		return UInt16(bytes[offset]) | (UInt16(bytes[offset + 1]) << 8)
	}

	private static func uint32(_ bytes: [UInt8], _ offset: Int) -> UInt32 {
		guard offset >= 0, offset + 4 <= bytes.count else { return 0 }
		return UInt32(bytes[offset])
			| (UInt32(bytes[offset + 1]) << 8)
			| (UInt32(bytes[offset + 2]) << 16)
			| (UInt32(bytes[offset + 3]) << 24)
	}
}

public enum UpdateExtractedTreeValidator {
	public static func validate(
		_ root: URL,
		fileManager: FileManager = .default
	) throws {
		let rootValues = try root.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
		guard rootValues.isDirectory == true, rootValues.isSymbolicLink != true else {
			throw UpdateStagingError("archive", "The extracted installer root is unsafe.")
		}
		let canonicalRoot = root.resolvingSymlinksInPath().standardizedFileURL
		var inspectionError: Error?
		guard let enumerator = fileManager.enumerator(
			at: root,
			includingPropertiesForKeys: [.isSymbolicLinkKey],
			options: [],
			errorHandler: { _, error in
				inspectionError = error
				return false
			}
		) else {
			throw UpdateStagingError("archive", "The extracted installer contents could not be inspected.")
		}
		while let entry = enumerator.nextObject() as? URL {
			let values = try entry.resourceValues(forKeys: [.isSymbolicLinkKey])
			guard values.isSymbolicLink == true else { continue }
			let resolved = entry.resolvingSymlinksInPath().standardizedFileURL
			guard
				(resolved.path == canonicalRoot.path
					|| resolved.path.hasPrefix(canonicalRoot.path + "/")),
				fileManager.fileExists(atPath: resolved.path)
			else {
				throw UpdateStagingError("archive", "The installer contains a symbolic link outside its extracted bundle.")
			}
		}
		if inspectionError != nil {
			throw UpdateStagingError("archive", "The extracted installer contents could not be inspected completely.")
		}
	}
}

public struct UpdateStagingService {
	public let paths: UpdateStagingPaths
	public let client: UpdateHTTPClienting
	public let runner: UpdateCommandRunner
	public let verifier: UpdateTrustVerifier
	public let environment: [String: String]
	public let now: @Sendable () -> Date
	public let validateArchive: @Sendable (Data) throws -> Void

	public init(
		paths: UpdateStagingPaths = UpdateStagingPaths(),
		client: UpdateHTTPClienting = UpdateURLSessionClient(),
		runner: UpdateCommandRunner = .live,
		verifier: UpdateTrustVerifier? = nil,
		environment: [String: String] = ProcessInfo.processInfo.environment,
		now: @escaping @Sendable () -> Date = { Date() },
		validateArchive: @escaping @Sendable (Data) throws -> Void = {
			try UpdateZipValidator.validate($0)
		}
	) {
		self.paths = paths
		self.client = client
		self.runner = runner
		self.environment = environment
		self.now = now
		self.validateArchive = validateArchive
		self.verifier = verifier ?? .live(
			runner: runner,
			allowDevelopmentSignature: Self.debugLoopbackURL(environment: environment) != nil
		)
	}

	public func prepare(_ request: UpdatePrepareRequest) async throws -> UpdateStageReceipt {
		try ensureManagedDirectories()
		try writeStatus(request, phase: .resolving)
		do {
			try Task.checkCancellation()
			if let receipt = try reusableReceipt(for: request) {
				try writeAuthorization(request)
				try writeStatus(request, phase: .ready)
				return receipt
			}

			let releaseURL = Self.releaseURL(version: request.version, environment: environment)
			let allowLoopback = Self.debugLoopbackURL(environment: environment) != nil
			let releaseData = try await client.data(from: releaseURL, timeout: 10, maximumBytes: 1_000_000)
			let release = try UpdatePublishedRelease.parse(
				releaseData,
				expectedVersion: request.version,
				allowLoopbackAssets: allowLoopback
			)
			let installerAsset = try release.requiredAsset(named: "GlyphsMCPInstaller.zip", allowLoopback: allowLoopback)
			let checksumsAsset = try release.requiredAsset(named: "SHA256SUMS", allowLoopback: allowLoopback)

			try Task.checkCancellation()
			try writeStatus(request, phase: .downloading)
			async let installerDataTask = client.data(
				from: installerAsset.browserDownloadURL,
				timeout: 30,
				maximumBytes: 128 * 1024 * 1024
			)
			async let checksumsDataTask = client.data(
				from: checksumsAsset.browserDownloadURL,
				timeout: 15,
				maximumBytes: 1_000_000
			)
			let (installerData, checksumsData) = try await (installerDataTask, checksumsDataTask)

			try Task.checkCancellation()
			try writeStatus(request, phase: .verifying)
			let expectedChecksum = try UpdateChecksumManifest.expectedSHA256(
				checksumsData,
				assetName: installerAsset.name
			)
			let actualChecksum = UpdateChecksumManifest.sha256(installerData)
			guard actualChecksum == expectedChecksum else {
				throw UpdateStagingError("checksum", "The downloaded installer checksum does not match the published manifest.")
			}
			try validateArchive(installerData)

			let work = paths.temporary.appendingPathComponent(request.requestID.uuidString.lowercased(), isDirectory: true)
			try removeManagedPathIfPresent(work)
			try createPrivateDirectory(work)
			defer { try? FileManager.default.removeItem(at: work) }
			let zip = work.appendingPathComponent(installerAsset.name)
			try installerData.write(to: zip, options: .atomic)
			let extracted = work.appendingPathComponent("Extracted", isDirectory: true)
			try createPrivateDirectory(extracted)
			_ = try runner.run(
				URL(fileURLWithPath: "/usr/bin/ditto"),
				["-x", "-k", zip.path, extracted.path]
			)
			try UpdateExtractedTreeValidator.validate(extracted)
			let verified = try verifier.verifyArchive(extracted, request.version)

			try Task.checkCancellation()
			try writeStatus(request, phase: .preparing)
			let receipt = try stage(
				verified,
				request: request,
				tag: release.tagName,
				assetName: installerAsset.name,
				assetSHA256: actualChecksum
			)
			try writeAuthorization(request)
			try writeStatus(request, phase: .ready)
			return receipt
		} catch is CancellationError {
			try? writeStatus(request, phase: .cancelled, errorCode: "cancelled", message: "Update preparation was cancelled.")
			throw UpdateStagingError("cancelled", "Update preparation was cancelled.")
		} catch {
			let updateError = error as? UpdateStagingError
				?? UpdateStagingError("preparation", error.localizedDescription)
			try? writeStatus(
				request,
				phase: .failed,
				errorCode: updateError.code,
				message: updateError.message
			)
			throw updateError
		}
	}

	public static func releaseURL(version: String, environment: [String: String]) -> URL {
		if let loopback = debugLoopbackURL(environment: environment) {
			return loopback
		}
		return URL(
			string: "https://api.github.com/repos/thierryc/Glyphs-mcp/releases/tags/v\(version)"
		)!
	}

	public static func debugLoopbackURL(environment: [String: String]) -> URL? {
#if DEBUG
		guard
			let raw = environment["GLYPHS_MCP_UPDATE_API_URL"],
			let url = URL(string: raw),
			url.scheme == "http",
			url.host == "127.0.0.1" || url.host == "localhost"
		else { return nil }
		return url
#else
		return nil
#endif
	}

	private func stage(
		_ verified: UpdateVerifiedPlugin,
		request: UpdatePrepareRequest,
		tag: String,
		assetName: String,
		assetSHA256: String
	) throws -> UpdateStageReceipt {
		guard verified.version == request.version,
			  verified.teamIdentifier == UpdateHelperProtocol.expectedTeamIdentifier else {
			throw UpdateStagingError("signature", "The verified plug-in does not match the authorized release.")
		}
		let destination = paths.stagedVersion(request.version)
		let temporary = paths.staged.appendingPathComponent(".v\(request.version).staging-\(request.requestID.uuidString.lowercased())", isDirectory: true)
		try removeManagedPathIfPresent(temporary)
		try createPrivateDirectory(temporary)
		do {
			let stagedPlugin = temporary.appendingPathComponent("Glyphs MCP.glyphsPlugin", isDirectory: true)
			try FileManager.default.copyItem(at: verified.bundleURL, to: stagedPlugin)
			let stagedVerification = try verifier.verifyPlugin(stagedPlugin, request.version)
			guard stagedVerification.cdHash == verified.cdHash,
				  stagedVerification.teamIdentifier == verified.teamIdentifier else {
				throw UpdateStagingError("signature", "The staged plug-in signature changed during copy.")
			}
			let receipt = UpdateStageReceipt(
				protocolVersion: UpdateHelperProtocol.currentVersion,
				version: request.version,
				tag: tag,
				assetName: assetName,
				assetSHA256: assetSHA256,
				pluginCDHash: verified.cdHash,
				teamIdentifier: verified.teamIdentifier,
				helperVersion: UpdateHelperProtocol.helperVersion,
				preparedAt: now()
			)
			try writeJSON(receipt, to: temporary.appendingPathComponent("receipt.json"))
			try removeManagedPathIfPresent(destination)
			try FileManager.default.moveItem(at: temporary, to: destination)
			return receipt
		} catch {
			try? FileManager.default.removeItem(at: temporary)
			throw error
		}
	}

	private func reusableReceipt(for request: UpdatePrepareRequest) throws -> UpdateStageReceipt? {
		let receiptURL = paths.stageReceipt(request.version)
		let pluginURL = paths.stagedPlugin(request.version)
		guard
			FileManager.default.fileExists(atPath: receiptURL.path),
			FileManager.default.fileExists(atPath: pluginURL.path),
			let data = try? Data(contentsOf: receiptURL),
			let receipt = try? Self.decoder.decode(UpdateStageReceipt.self, from: data),
			receipt.protocolVersion == UpdateHelperProtocol.currentVersion,
			receipt.version == request.version,
			receipt.tag == "v\(request.version)",
			receipt.teamIdentifier == UpdateHelperProtocol.expectedTeamIdentifier
		else { return nil }
		let verified = try verifier.verifyPlugin(pluginURL, request.version)
		guard verified.cdHash == receipt.pluginCDHash,
			  verified.teamIdentifier == receipt.teamIdentifier else {
			return nil
		}
		return receipt
	}

	private func writeAuthorization(_ request: UpdatePrepareRequest) throws {
		let receipt = UpdateAuthorizationReceipt(
			protocolVersion: UpdateHelperProtocol.currentVersion,
			requestID: request.requestID.uuidString.lowercased(),
			version: request.version,
			glyphsMajor: request.glyphsMajor,
			authorizedAt: now()
		)
		try writeJSON(receipt, to: paths.authorization(version: request.version, glyphsMajor: request.glyphsMajor))
	}

	private func writeStatus(
		_ request: UpdatePrepareRequest,
		phase: UpdatePreparationPhase,
		errorCode: String? = nil,
		message: String? = nil
	) throws {
		try writeJSON(
			UpdatePreparationStatus(
				requestID: request.requestID.uuidString.lowercased(),
				version: request.version,
				glyphsMajor: request.glyphsMajor,
				phase: phase,
				errorCode: errorCode,
				message: message,
				updatedAt: now()
			),
			to: paths.requestStatus(request.requestID)
		)
	}

	private func ensureManagedDirectories() throws {
		let productRoot = paths.root.deletingLastPathComponent()
		try createPrivateDirectory(productRoot)
		try createPrivateDirectory(paths.root)
		if entryExists(paths.managedMarker) {
			guard try !isSymbolicLink(paths.managedMarker),
				  let marker = try? String(contentsOf: paths.managedMarker, encoding: .utf8),
				  marker == UpdateHelperProtocol.managedMarker else {
				throw UpdateStagingError("unsafe_path", "The updater directory is not marked as managed.")
			}
		} else {
			try Data(UpdateHelperProtocol.managedMarker.utf8).write(to: paths.managedMarker, options: .atomic)
			try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: paths.managedMarker.path)
		}
		try createPrivateDirectory(paths.requests)
		try createPrivateDirectory(paths.staged)
		try createPrivateDirectory(paths.authorizations)
		try createPrivateDirectory(paths.temporary)
	}

	private func createPrivateDirectory(_ url: URL) throws {
		if entryExists(url) {
			let values = try url.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
			guard values.isSymbolicLink != true, values.isDirectory == true else {
				throw UpdateStagingError("unsafe_path", "A managed updater directory is a symbolic link.")
			}
			try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: url.path)
			return
		}
		try FileManager.default.createDirectory(
			at: url,
			withIntermediateDirectories: true,
			attributes: [.posixPermissions: 0o700]
		)
	}

	private func removeManagedPathIfPresent(_ url: URL) throws {
		guard entryExists(url) else { return }
		guard try !isSymbolicLink(url), url.standardizedFileURL.path.hasPrefix(paths.root.standardizedFileURL.path + "/") else {
			throw UpdateStagingError("unsafe_path", "Refusing to remove an unsafe updater path.")
		}
		try FileManager.default.removeItem(at: url)
	}

	private func isSymbolicLink(_ url: URL) throws -> Bool {
		if (try? FileManager.default.destinationOfSymbolicLink(atPath: url.path)) != nil {
			return true
		}
		return try url.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink == true
	}

	private func entryExists(_ url: URL) -> Bool {
		FileManager.default.fileExists(atPath: url.path)
			|| (try? FileManager.default.destinationOfSymbolicLink(atPath: url.path)) != nil
	}

	private func writeJSON<T: Encodable>(_ value: T, to url: URL) throws {
		try createPrivateDirectory(url.deletingLastPathComponent())
		let data = try Self.encoder.encode(value)
		let temporary = url.deletingLastPathComponent().appendingPathComponent(".\(url.lastPathComponent).tmp-\(UUID().uuidString)")
		try data.write(to: temporary, options: .atomic)
		try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: temporary.path)
		if FileManager.default.fileExists(atPath: url.path) {
			_ = try FileManager.default.replaceItemAt(url, withItemAt: temporary)
		} else {
			try FileManager.default.moveItem(at: temporary, to: url)
		}
	}

	private static let encoder: JSONEncoder = {
		let encoder = JSONEncoder()
		encoder.outputFormatting = [.sortedKeys]
		encoder.dateEncodingStrategy = .iso8601
		return encoder
	}()

	private static let decoder: JSONDecoder = {
		let decoder = JSONDecoder()
		decoder.dateDecodingStrategy = .iso8601
		return decoder
	}()
}
