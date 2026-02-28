import Foundation

public enum GlyphsPreferences {
	private static let suite = "com.GeorgSeifert.Glyphs3"

	/// Best-effort read of the Python framework path selected in Glyphs:
	/// Glyphs → Settings → Addons → Python.
	///
	/// Example: `/Library/Frameworks/Python.framework/Versions/3.12`
	public static func pythonFrameworkPath() -> String? {
		guard let defaults = UserDefaults(suiteName: suite) else { return nil }
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

