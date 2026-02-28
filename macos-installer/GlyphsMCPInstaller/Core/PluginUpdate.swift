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

public struct GitHubPluginVersionFetcher {
	public struct Result: Equatable {
		public let version: PluginBundleVersion
		public let fetchedAt: Date
	}

	private static let cacheKeyDate = "gmcp.githubPluginVersionFetchedAt"
	private static let cacheKeyVersion = "gmcp.githubPluginVersionString"
	private static var inMemory: Result?

	public static let infoPlistURL = URL(string: "https://raw.githubusercontent.com/thierryc/Glyphs-mcp/main/src/glyphs-mcp/Glyphs%20MCP.glyphsPlugin/Contents/Info.plist")!

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

		let data = try await client.data(from: infoPlistURL, timeout: timeout)
		guard let version = PluginVersionReader.readInfoPlist(data: data) else {
			throw InstallerError.userFacing("GitHub Info.plist could not be parsed.")
		}

		let res = Result(version: version, fetchedAt: Date())
		inMemory = res
		defaults.set(res.fetchedAt, forKey: cacheKeyDate)
		defaults.set(version.shortVersion ?? version.buildVersion ?? "", forKey: cacheKeyVersion)
		return res
	}
}
