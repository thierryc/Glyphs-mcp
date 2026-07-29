import CryptoKit
import Foundation

public struct GitHubPluginDownloader {
	public let runner: ProcessRunner
	public let log: (String) -> Void
	public let client: HTTPClienting
	public let archiveVerifier: InstallerArchiveVerifier

	public init(
		runner: ProcessRunner,
		log: @escaping (String) -> Void,
		client: HTTPClienting = URLSessionHTTPClient(),
		archiveVerifier: InstallerArchiveVerifier = .live
	) {
		self.runner = runner
		self.log = log
		self.client = client
		self.archiveVerifier = archiveVerifier
	}

	public func downloadAndExtractPluginBundle(timeout: TimeInterval = 30) async throws -> URL {
		log("Resolving the latest signed Glyphs MCP release…")
		let releaseData = try await client.data(from: GitHubReleaseResolver.latestReleaseURL, timeout: timeout)
		let release = try GitHubReleaseResolver.parsePublishedRelease(releaseData)
		let installerAsset = try release.requiredAsset(named: "GlyphsMCPInstaller.zip")
		let checksumsAsset = try release.requiredAsset(named: "SHA256SUMS")

		log("Downloading signed installer payload \(release.version)…")
		async let installerData = client.data(from: installerAsset.browserDownloadURL, timeout: timeout)
		async let checksumsData = client.data(from: checksumsAsset.browserDownloadURL, timeout: timeout)
		let (zipData, checksumData) = try await (installerData, checksumsData)
		try Self.verifyChecksum(
			zipData,
			manifestData: checksumData,
			assetName: installerAsset.name
		)

		let tmp = FileManager.default.temporaryDirectory
			.appendingPathComponent("glyphs-mcp-release-\(UUID().uuidString)", isDirectory: true)
		try FileManager.default.createDirectory(at: tmp, withIntermediateDirectories: true, attributes: nil)
		let zipPath = tmp.appendingPathComponent(installerAsset.name)
		try zipData.write(to: zipPath, options: .atomic)
		let extractDir = tmp.appendingPathComponent("extracted", isDirectory: true)
		try FileManager.default.createDirectory(at: extractDir, withIntermediateDirectories: true, attributes: nil)

		log("Extracting verified installer archive…")
		try await runner.runStreaming(
			executable: URL(fileURLWithPath: "/usr/bin/ditto"),
			args: ["-x", "-k", zipPath.path, extractDir.path],
			onLine: { _ in }
		)

		let plugin = try archiveVerifier.verifyAndResolvePlugin(extractDir, release.version)
		log("Verified signed release plug-in \(release.version).")
		return plugin
	}

	public static func verifyChecksum(_ data: Data, manifestData: Data, assetName: String) throws {
		guard !assetName.contains("/"), !assetName.contains("\\") else {
			throw InstallerError.userFacing("Release asset name is unsafe.")
		}
		guard let manifest = String(data: manifestData, encoding: .utf8) else {
			throw InstallerError.userFacing("Release checksum manifest is not UTF-8.")
		}
		let matches = manifest
			.split(whereSeparator: \.isNewline)
			.compactMap { line -> String? in
				let parts = line.split(maxSplits: 1, whereSeparator: \.isWhitespace).map(String.init)
				guard parts.count == 2 else { return nil }
				let logicalPath = parts[1].trimmingCharacters(in: CharacterSet(charactersIn: " *"))
				let pathComponents = logicalPath.split(separator: "/", omittingEmptySubsequences: false)
				guard !logicalPath.hasPrefix("/"),
					  !logicalPath.contains("\\"),
					  !pathComponents.contains(".."),
					  pathComponents.last.map(String.init) == assetName else {
					return nil
				}
				return parts[0].lowercased()
			}
		guard matches.count == 1, let expected = matches.first else {
			if matches.isEmpty {
				throw InstallerError.userFacing("Release checksum manifest does not list \(assetName).")
			}
			throw InstallerError.userFacing("Release checksum manifest contains duplicate entries for \(assetName).")
		}
		let hexCharacters = CharacterSet(charactersIn: "0123456789abcdef")
		guard expected.count == 64,
			  expected.unicodeScalars.allSatisfy({ hexCharacters.contains($0) }) else {
			throw InstallerError.userFacing("Release checksum manifest contains an invalid SHA-256 for \(assetName).")
		}
		let actual = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
		guard actual == expected else {
			throw InstallerError.userFacing("Downloaded installer checksum does not match the published manifest.")
		}
	}
}

public struct InstallerArchiveVerifier {
	public let verifyAndResolvePlugin: (URL, String) throws -> URL

	public init(verifyAndResolvePlugin: @escaping (URL, String) throws -> URL) {
		self.verifyAndResolvePlugin = verifyAndResolvePlugin
	}

	public static let live = InstallerArchiveVerifier { extractedRoot, expectedVersion in
		let app = extractedRoot.appendingPathComponent("GlyphsMCPInstaller.app", isDirectory: true)
		guard FileManager.default.fileExists(atPath: app.path) else {
			throw InstallerError.userFacing("Signed installer archive does not contain GlyphsMCPInstaller.app.")
		}

		_ = try run(
			"/usr/bin/codesign",
			["--verify", "--deep", "--strict", "--verbose=2", app.path],
			subject: app
		)
		let appDetails = try run(
			"/usr/bin/codesign",
			["-d", "--verbose=4", app.path],
			subject: app
		)
		guard appDetails.contains("Authority=\(PluginExecutableVerifier.expectedDeveloperIDAuthority)"),
			  appDetails.contains("TeamIdentifier=\(PluginExecutableVerifier.expectedTeamIdentifier)") else {
			throw InstallerError.userFacing("Installer archive is not signed by the expected Developer ID.")
		}
		_ = try run("/usr/bin/xcrun", ["stapler", "validate", app.path], subject: app)
		_ = try run("/usr/sbin/spctl", ["--assess", "--type", "execute", "--verbose=2", app.path], subject: app)

		let appVersion = Bundle(url: app)?
			.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
		guard appVersion == expectedVersion else {
			throw InstallerError.userFacing("Installer archive version does not match the published release.")
		}

		guard let appBundle = Bundle(url: app) else {
			throw InstallerError.userFacing("Signed installer archive is not a readable app bundle.")
		}
		let plugin = try InstallerPayload.resolve(bundle: appBundle).pluginBundle
		guard PluginVersionReader.readPluginVersion(pluginBundle: plugin)?.displayString == expectedVersion else {
			throw InstallerError.userFacing("Installer payload plug-in version does not match the published release.")
		}
		let pluginSignature = try PluginExecutableVerifier.live.verify(plugin)
		guard pluginSignature.authority == PluginExecutableVerifier.expectedDeveloperIDAuthority else {
			throw InstallerError.userFacing("Installer payload plug-in is not signed by the expected Developer ID.")
		}
		return plugin
	}

	private static func run(_ executablePath: String, _ arguments: [String], subject: URL) throws -> String {
		let process = Process()
		process.executableURL = URL(fileURLWithPath: executablePath)
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
				throw InstallerError.userFacing(
					"Release verification failed for \(subject.lastPathComponent): \(output.trimmingCharacters(in: .whitespacesAndNewlines))"
				)
			}
			return output
		} catch {
			if let installerError = error as? InstallerError {
				throw installerError
			}
			throw InstallerError.userFacing("Could not verify \(subject.lastPathComponent): \(error.localizedDescription)")
		}
	}
}
