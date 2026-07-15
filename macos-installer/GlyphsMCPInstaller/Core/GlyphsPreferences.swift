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
