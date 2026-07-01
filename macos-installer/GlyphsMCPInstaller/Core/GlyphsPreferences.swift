import Foundation

public enum GlyphsMajorVersion: String, CaseIterable {
	case v3 = "3"
	case v4 = "4"

	public var applicationSupportName: String {
		"Glyphs \(rawValue)"
	}

	public var preferencesSuiteName: String {
		switch self {
		case .v3: return "com.GeorgSeifert.Glyphs3"
		case .v4: return "com.GeorgSeifert.Glyphs4"
		}
	}
}

public enum GlyphsPreferences {
	public static func suiteName(glyphsVersion: GlyphsMajorVersion = .v3) -> String {
		glyphsVersion.preferencesSuiteName
	}

	/// Best-effort read of the Python framework path selected in Glyphs:
	/// Glyphs → Settings → Addons → Python.
	///
	/// Example: `/Library/Frameworks/Python.framework/Versions/3.12`
	public static func pythonFrameworkPath(glyphsVersion: GlyphsMajorVersion = .v3) -> String? {
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
