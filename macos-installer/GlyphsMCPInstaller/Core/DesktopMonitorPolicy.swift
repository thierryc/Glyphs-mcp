import Foundation

public struct DesktopMonitorPolicy {
    public var dashboardVisible = false
    public var surfaces: Set<String> = []
    public var menuBarVisible = false
    public init() {}
    public var visible: Bool { surfaces.contains("popover") || (dashboardVisible && surfaces.contains("setup")) }
    public func interval(busy: Bool) -> UInt64? {
        visible ? (busy ? 2 : 5) : menuBarVisible && busy ? 2 : nil
    }
}

public enum DesktopLaunchPolicy {
    public static let welcomeCompletedKey = "desktopWelcomeCompleted.v1"
    public static func showsWelcome(loginLaunch: Bool, defaults: UserDefaults) -> Bool {
        !loginLaunch && !defaults.bool(forKey: welcomeCompletedKey)
    }
    public static func completeWelcome(defaults: UserDefaults) {
        defaults.set(true, forKey: welcomeCompletedKey)
    }
    public static func showsDashboard(loginLaunch: Bool) -> Bool { !loginLaunch }
    public static func showsMenuBar(defaults: UserDefaults) -> Bool {
        defaults.object(forKey: DesktopIdentity.showMenuBarKey) as? Bool ?? true
    }
}
