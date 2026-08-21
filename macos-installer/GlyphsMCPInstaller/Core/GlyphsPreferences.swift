import Foundation

public enum GlyphsMajorVersion: String, CaseIterable, Identifiable, Comparable, Sendable {
	case v3 = "3"
	case v4 = "4"

	public static let installerDefault: GlyphsMajorVersion = .v4

	public var applicationSupportName: String {
		"Glyphs \(rawValue)"
	}

	public var id: String { rawValue }

	public var displayName: String {
		"Glyphs \(rawValue)"
	}

	public var stableBundleIdentifier: String {
		switch self {
		case .v3: return "com.GeorgSeifert.Glyphs3"
		case .v4: return "com.GeorgSeifert.Glyphs4"
		}
	}

	public var bundleIdentifiers: [String] {
		switch self {
		case .v3:
			return [stableBundleIdentifier, "com.GeorgSeifert.Glyphs3Beta"]
		case .v4:
			return [stableBundleIdentifier, "com.GeorgSeifert.Glyphs4Beta"]
		}
	}

	public var applicationNames: [String] {
		switch self {
		case .v3: return ["Glyphs 3", "Glyphs3"]
		case .v4: return ["Glyphs 4", "Glyphs4"]
		}
	}

	public var preferencesSuiteName: String {
		switch self {
		case .v3: return "com.GeorgSeifert.Glyphs3"
		case .v4: return "com.GeorgSeifert.Glyphs4"
		}
	}

	public static func < (lhs: GlyphsMajorVersion, rhs: GlyphsMajorVersion) -> Bool {
		lhs.rawValue < rhs.rawValue
	}
}

public enum GlyphsPreferences {
	public static func suiteName(glyphsVersion: GlyphsMajorVersion = .installerDefault) -> String {
		glyphsVersion.preferencesSuiteName
	}

	/// Best-effort read of the Python framework path selected in Glyphs:
	/// Glyphs → Settings → Addons → Python.
	///
	/// Example: `/Library/Frameworks/Python.framework/Versions/3.12`
	public static func pythonFrameworkPath(glyphsVersion: GlyphsMajorVersion = .installerDefault) -> String? {
		guard let defaults = UserDefaults(suiteName: suiteName(glyphsVersion: glyphsVersion)) else { return nil }
		return defaults.string(forKey: "GSPythonFrameworkPath")
	}

	/// Returns `3.12` if the path ends with `.../Versions/3.12`.
	public static func pythonFrameworkMajorMinor(from frameworkPath: String) -> String? {
		let url = URL(fileURLWithPath: frameworkPath)
		let last = url.lastPathComponent.trimmingCharacters(in: .whitespacesAndNewlines)
		guard !last.isEmpty else { return nil }
		return last
	}
}

public struct Glyphs3UpdatePinStore: Sendable {
	public let read: @Sendable (String) -> Bool?
	public let write: @Sendable (String, Bool) -> Void
	public let remove: @Sendable (String) -> Void

	public init(
		read: @escaping @Sendable (String) -> Bool?,
		write: @escaping @Sendable (String, Bool) -> Void,
		remove: @escaping @Sendable (String) -> Void
	) {
		self.read = read
		self.write = write
		self.remove = remove
	}

	public static let live = Glyphs3UpdatePinStore(
		read: { key in
			UserDefaults(suiteName: GlyphsMajorVersion.v3.preferencesSuiteName)?.object(forKey: key) as? Bool
		},
		write: { key, value in
			let defaults = UserDefaults(suiteName: GlyphsMajorVersion.v3.preferencesSuiteName)
			defaults?.set(value, forKey: key)
			defaults?.synchronize()
		},
		remove: { key in
			let defaults = UserDefaults(suiteName: GlyphsMajorVersion.v3.preferencesSuiteName)
			defaults?.removeObject(forKey: key)
			defaults?.synchronize()
		}
	)
}

public struct Glyphs3UpdatePinManager: Sendable {
	private struct Receipt: Codable {
		struct Previous: Codable {
			let existed: Bool
			let value: Bool?
		}
		let schemaVersion: Int
		let writtenValue: Bool
		let previous: [String: Previous]
	}

	public static let notificationKey = "com.ap.cx.glyphs-mcp.updateChecksEnabled"
	public static let preparationKey = UpdateHelperProtocol.optInDefaultsKey
	public static let managedKeys = [notificationKey, preparationKey]

	public let receiptURL: URL
	public let store: Glyphs3UpdatePinStore

	public init(
		receiptURL: URL = FileManager.default.homeDirectoryForCurrentUser
			.appendingPathComponent("Library/Application Support/Glyphs MCP/Installer/Glyphs3UpdatePin.json"),
		store: Glyphs3UpdatePinStore = .live
	) {
		self.receiptURL = receiptURL
		self.store = store
	}

	public func pin() throws {
		var prior: [String: Receipt.Previous] = [:]
		let receiptValues = try? receiptURL.resourceValues(forKeys: [.isSymbolicLinkKey])
		if FileManager.default.fileExists(atPath: receiptURL.path) || receiptValues?.isSymbolicLink == true {
			let current = try readReceipt()
			guard current.schemaVersion == 1, current.writtenValue == false else {
				throw InstallerError.userFacing("The Glyphs 3 update pin receipt is not recognized and was preserved.")
			}
			prior = current.previous
		}
		for key in Self.managedKeys {
			let current = store.read(key)
			if prior[key] == nil || current != false {
				prior[key] = Receipt.Previous(existed: current != nil, value: current)
			}
			store.write(key, false)
		}
		let receipt = Receipt(schemaVersion: 1, writtenValue: false, previous: prior)
		let encoder = JSONEncoder()
		encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
		var data = try encoder.encode(receipt)
		data.append(Data("\n".utf8))
		try FileIO.writeAtomically(data, to: receiptURL)
		try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: receiptURL.path)
	}

	public func restoreIfOwned() throws {
		guard FileManager.default.fileExists(atPath: receiptURL.path) else { return }
		let receipt = try readReceipt()
		guard receipt.schemaVersion == 1, receipt.writtenValue == false else {
			throw InstallerError.userFacing("The Glyphs 3 update pin receipt is not recognized and was preserved.")
		}
		for key in Self.managedKeys {
			guard store.read(key) == receipt.writtenValue, let previous = receipt.previous[key] else {
				continue
			}
			if previous.existed, let value = previous.value {
				store.write(key, value)
			} else {
				store.remove(key)
			}
		}
		try FileManager.default.removeItem(at: receiptURL)
	}

	private func readReceipt() throws -> Receipt {
		let values = try receiptURL.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
		guard values.isRegularFile == true, values.isSymbolicLink != true, (values.fileSize ?? 0) <= 64 * 1024 else {
			throw InstallerError.userFacing("The Glyphs 3 update pin receipt is unsafe and was preserved.")
		}
		return try JSONDecoder().decode(Receipt.self, from: Data(contentsOf: receiptURL))
	}
}
