import Foundation

public enum InstallerAdvancedModePolicy {
	public static let preferenceKey = "cx.ap.glyphsMcpInstaller.advancedModeEnabled"
	public static let allTabIDs = ["wizard", "install", "link", "skill", "status", "help"]
	public static let advancedTabIDs: Set<String> = ["install", "link", "skill"]

	public static func visibleTabIDs(isAdvancedModeEnabled: Bool) -> [String] {
		isAdvancedModeEnabled ? allTabIDs : allTabIDs.filter { !advancedTabIDs.contains($0) }
	}

	public static func fallbackTabID(currentTabID: String, isAdvancedModeEnabled: Bool) -> String {
		guard !isAdvancedModeEnabled, advancedTabIDs.contains(currentTabID) else {
			return currentTabID
		}
		return "wizard"
	}
}

public enum InstallerAdvancedModePreferences {
	public static func load(from defaults: UserDefaults = .standard) -> Bool {
		defaults.bool(forKey: InstallerAdvancedModePolicy.preferenceKey)
	}

	public static func save(_ isEnabled: Bool, to defaults: UserDefaults = .standard) {
		defaults.set(isEnabled, forKey: InstallerAdvancedModePolicy.preferenceKey)
	}
}
