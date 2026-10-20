import Foundation

public struct OptionalToolState: Decodable, Identifiable {
    public let id: String
    public let distributionQualified: Bool?
    public let available: Bool
    public let installed: Bool
    public let reason: String?
    public let state: String?
    public let version: String?
    public let build: String?
    public let loadedVerified: Bool?

    public var protectedInstallation: Bool {
        state == "unmanaged" || state == "development_link" || state == "conflict"
    }
    public var label: String {
        if state == "development_link" { return "Development link preserved" }
        if state == "unmanaged" { return "Separate installation preserved" }
        if state == "conflict" { return "Modified installation preserved" }
        if installed {
            let revision = version.map { " · " + $0 } ?? ""
            let buildLabel = build.map { " (build " + $0 + ")" } ?? ""
            return "Installed" + revision + buildLabel + (state == "restart_required" ? " · Restart required" : id == "beztrace-glyphs" && loadedVerified != true ? " · Loading unverified" : "")
        }
        if available { return "Not installed" }
        return distributionQualified == true ? "Unavailable on this Mac" : "Awaiting release qualification"
    }
}
