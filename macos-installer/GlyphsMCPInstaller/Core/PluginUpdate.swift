import Foundation

public struct PluginBundleVersion: Equatable, Comparable, CustomStringConvertible {
	public let shortVersion: String?
	public let buildVersion: String?

	public init(shortVersion: String?, buildVersion: String?) {
		self.shortVersion = shortVersion?.trimmingCharacters(in: .whitespacesAndNewlines)
		self.buildVersion = buildVersion?.trimmingCharacters(in: .whitespacesAndNewlines)
	}

	public var description: String { displayString }

	public var displayString: String {
		let short = shortVersion?.isEmpty == false ? shortVersion : nil
		let build = buildVersion?.isEmpty == false ? buildVersion : nil
		if let short, let build, short != build {
			return "\(short) (\(build))"
		}
		return short ?? build ?? "unknown"
	}

	private var comparableString: String {
		(shortVersion?.isEmpty == false ? shortVersion : buildVersion) ?? ""
	}

	public static func < (lhs: PluginBundleVersion, rhs: PluginBundleVersion) -> Bool {
		let a = PluginVersionKey(lhs.comparableString)
		let b = PluginVersionKey(rhs.comparableString)
		return a < b
	}
}

public struct PluginVersionKey: Comparable, Equatable {
	public let raw: String
	public let tuple: (Int, Int, Int)?

	public init(_ raw: String) {
		self.raw = raw.trimmingCharacters(in: .whitespacesAndNewlines)
		self.tuple = PluginVersionKey.parseTuple(self.raw)
	}

	private static func parseTuple(_ s: String) -> (Int, Int, Int)? {
		// Extract leading numeric dotted version. Examples:
		// "1.2.3" -> (1,2,3)
		// "1.2" -> (1,2,0)
		// "1.2.3-beta1" -> (1,2,3)
		let head = s.split(whereSeparator: { !($0.isNumber || $0 == ".") }).first.map(String.init) ?? s
		let parts = head.split(separator: ".").prefix(3).map { Int($0) ?? 0 }
		guard parts.count >= 1 else { return nil }
		let major = parts.count > 0 ? parts[0] : 0
		let minor = parts.count > 1 ? parts[1] : 0
		let patch = parts.count > 2 ? parts[2] : 0
		return (major, minor, patch)
	}

	public static func < (lhs: PluginVersionKey, rhs: PluginVersionKey) -> Bool {
		switch (lhs.tuple, rhs.tuple) {
		case let (.some(a), .some(b)):
			if a == b { return lhs.raw < rhs.raw }
			return a < b
		case (.some, .none):
			return false
		case (.none, .some):
			return true
		case (.none, .none):
			return lhs.raw < rhs.raw
		}
	}

	public static func == (lhs: PluginVersionKey, rhs: PluginVersionKey) -> Bool {
		switch (lhs.tuple, rhs.tuple) {
		case let (.some(a), .some(b)):
			return a == b
		case (.none, .none):
			return lhs.raw == rhs.raw
		default:
			return false
		}
	}
}

public enum PluginVersionReader {
	public static func readPluginVersion(pluginBundle: URL) -> PluginBundleVersion? {
		let info = pluginBundle.appendingPathComponent("Contents/Info.plist")
		guard let data = try? Data(contentsOf: info) else { return nil }
		return readInfoPlist(data: data)
	}

	public static func readInfoPlist(data: Data) -> PluginBundleVersion? {
		guard let obj = try? PropertyListSerialization.propertyList(from: data, format: nil) as? [String: Any] else { return nil }
		let short = obj["CFBundleShortVersionString"] as? String
		let build = obj["CFBundleVersion"] as? String
		return PluginBundleVersion(shortVersion: short, buildVersion: build)
	}
}

public enum PluginUpdateStatus: Equatable {
	case idle
	case checking
	case upToDate(latest: PluginBundleVersion)
	case updateAvailable(installed: PluginBundleVersion?, latest: PluginBundleVersion)
	case error(message: String)
}

public protocol HTTPClienting {
	func data(from url: URL, timeout: TimeInterval) async throws -> Data
}

public struct URLSessionHTTPClient: HTTPClienting {
	public init() {}

	public func data(from url: URL, timeout: TimeInterval) async throws -> Data {
		var req = URLRequest(url: url)
		req.timeoutInterval = timeout
		let (data, _) = try await URLSession.shared.data(for: req)
		return data
	}
}

public struct GitHubReleaseAsset: Decodable, Equatable {
	public let name: String
	public let browserDownloadURL: URL

	enum CodingKeys: String, CodingKey {
		case name
		case browserDownloadURL = "browser_download_url"
	}
}

public struct GitHubPublishedRelease: Decodable, Equatable {
	public let tagName: String
	public let draft: Bool
	public let prerelease: Bool
	public let assets: [GitHubReleaseAsset]

	enum CodingKeys: String, CodingKey {
		case tagName = "tag_name"
		case draft
		case prerelease
		case assets
	}

	public var version: String {
		tagName.hasPrefix("v") ? String(tagName.dropFirst()) : tagName
	}

	public func requiredAsset(named name: String) throws -> GitHubReleaseAsset {
		let matches = assets.filter { $0.name == name }
		guard matches.count == 1, let asset = matches.first else {
			if matches.isEmpty {
				throw InstallerError.userFacing("Published release \(tagName) is missing \(name).")
			}
			throw InstallerError.userFacing("Published release \(tagName) contains duplicate \(name) assets.")
		}
		guard asset.browserDownloadURL.scheme == "https",
			  asset.browserDownloadURL.host == "github.com" else {
			throw InstallerError.userFacing("Published release \(tagName) has an untrusted download URL for \(name).")
		}
		guard asset.browserDownloadURL.path.contains("/thierryc/Glyphs-mcp/releases/download/") else {
			throw InstallerError.userFacing("Published release \(tagName) has an unexpected download path for \(name).")
		}
		guard asset.browserDownloadURL.lastPathComponent == name else {
			throw InstallerError.userFacing("Published release \(tagName) is missing \(name).")
		}
		return asset
	}
}

public enum GitHubReleaseResolver {
	public static let latestReleaseURL = URL(
		string: "https://api.github.com/repos/thierryc/Glyphs-mcp/releases/latest"
	)!

	public static func parsePublishedRelease(_ data: Data) throws -> GitHubPublishedRelease {
		let release: GitHubPublishedRelease
		do {
			release = try JSONDecoder().decode(GitHubPublishedRelease.self, from: data)
		} catch {
			throw InstallerError.userFacing("GitHub release metadata could not be parsed.")
		}
		guard !release.draft, !release.prerelease else {
			throw InstallerError.userFacing("GitHub returned a draft or prerelease instead of a published stable release.")
		}
		guard PluginVersionKey(release.version).tuple != nil else {
			throw InstallerError.userFacing("Published release tag is not a valid numeric version.")
		}
		return release
	}
}

public struct GitHubPluginVersionFetcher {
	public struct Result: Equatable {
		public let version: PluginBundleVersion
		public let fetchedAt: Date
	}

	private static let cacheKeyDate = "gmcp.githubPluginVersionFetchedAt"
	private static let cacheKeyVersion = "gmcp.githubPluginVersionString"
	private static var inMemory: Result?

	public static func fetchLatestVersion(client: HTTPClienting = URLSessionHTTPClient(), timeout: TimeInterval = 10, cacheMaxAge: TimeInterval = 3600) async throws -> Result {
		if let cached = inMemory, Date().timeIntervalSince(cached.fetchedAt) <= cacheMaxAge {
			return cached
		}

		let defaults = UserDefaults.standard
		if let date = defaults.object(forKey: cacheKeyDate) as? Date,
		   Date().timeIntervalSince(date) <= cacheMaxAge,
		   let s = defaults.string(forKey: cacheKeyVersion),
		   !s.isEmpty {
			let cached = Result(version: PluginBundleVersion(shortVersion: s, buildVersion: s), fetchedAt: date)
			inMemory = cached
			return cached
		}

		let data = try await client.data(from: GitHubReleaseResolver.latestReleaseURL, timeout: timeout)
		let release = try GitHubReleaseResolver.parsePublishedRelease(data)
		let version = PluginBundleVersion(shortVersion: release.version, buildVersion: release.version)

		let res = Result(version: version, fetchedAt: Date())
		inMemory = res
		defaults.set(res.fetchedAt, forKey: cacheKeyDate)
		defaults.set(version.shortVersion ?? version.buildVersion ?? "", forKey: cacheKeyVersion)
		return res
	}
}
