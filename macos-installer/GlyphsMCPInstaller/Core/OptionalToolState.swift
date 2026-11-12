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
        label(bundle: nil, locale: .current)
    }

    public func presentationLabel(bundle: Bundle = .main, locale: Locale = .current) -> String {
        label(bundle: bundle, locale: locale)
    }

    private func label(bundle: Bundle?, locale: Locale) -> String {
        func display(_ message: AppMessage) -> String {
            guard let bundle else { return message.diagnostic }
            return message.localized(bundle: bundle, locale: locale)
        }

        if state == "development_link" { return display("Development link preserved") }
        if state == "unmanaged" { return display("Separate installation preserved") }
        if state == "conflict" { return display("Modified installation preserved") }
        if installed {
            var title = display("Installed")
            if let version { title = display("\(title) · \(version)") }
            if let build { title = display("\(title) (build \(build))") }
            if state == "restart_required" {
                title = display("\(title) · \(display("Restart required"))")
            } else if id == "beztrace-glyphs" && loadedVerified != true {
                title = display("\(title) · \(display("Loading unverified"))")
            }
            return title
        }
        if available { return display("Not installed") }
        return distributionQualified == true ? display("Unavailable on this Mac") : display("Awaiting release qualification")
    }
}
