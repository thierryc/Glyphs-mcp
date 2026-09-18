import Foundation

public enum DesktopIdentity {
    public static let bundleIdentifier = "cx.ap.glyphsMcp"
    public static let serviceLabel = "com.ap.cx.glyphs-mcp-sidecar"
    public static let showMenuBarKey = "showMenuBar"
    public static var isBeta: Bool { Bundle.main.object(forInfoDictionaryKey: "GMCPReleaseChannel") as? String == "beta" }
    public static var applicationTitle: String { isBeta ? "Glyphs MCP Beta" : "Glyphs MCP" }
    public static var versionLabel: String {
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "unknown"
        let build = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "unknown"
        let beta = Bundle.main.object(forInfoDictionaryKey: "GMCPBetaNumber") as? Int ?? 0
        return "\(version)\(isBeta ? " Beta \(beta)" : "") · Build \(build)"
    }
    public static var documentation: URL {
        isBeta ? URL(string: "https://github.com/thierryc/Glyphs-mcp/blob/lit/v2-beta/BETA.md")!
               : URL(string: "https://thierryc.github.io/Glyphs-mcp/docs/v2/")!
    }
    public static func componentDocumentation(_ id: String) -> URL {
        URL(string: documentation.absoluteString + (isBeta ? "#" : "getting-started/desktop#") + id)!
    }
    public static let issues = URL(string: "https://github.com/thierryc/Glyphs-mcp/issues")!
    public static let support = URL(string: "https://github.com/sponsors/thierryc")!
    public static let linkedIn = URL(string: "https://www.linkedin.com/in/thierrycharbonnel/")!
}

public struct DesktopComponent: Identifiable {
    public let id: String
    public let title: String
    public let detail: String
    public let bundle: String
    public let symbol: String
    public let previewAsset: String
    public let documentation: URL

    public static let all: [DesktopComponent] = [
        .init(id: "mcp", title: "Glyphs MCP", detail: "Connect AI assistants to Glyphs for font analysis and editing.",
              bundle: "Glyphs MCP Bridge.glyphsPlugin", symbol: "sparkles", previewAsset: "ComponentMCP",
              documentation: DesktopIdentity.documentation),
        .init(id: "curve-inspector", title: "Curve Inspector", detail: "Inspect curve geometry and handles directly on the canvas.",
              bundle: "Glyphs Curve Inspector.glyphsReporter", symbol: "point.topleft.down.curvedto.point.bottomright.up", previewAsset: "ComponentCurveInspector",
              documentation: DesktopIdentity.componentDocumentation("curve-inspector")),
        .init(id: "reference-inspector", title: "Reference Inspector", detail: "Compare outlines and spacing with the last saved version, another font file, or a Git revision. In Glyphs: Changes Against Reference.",
              bundle: "Glyphs Reference Inspector.glyphsReporter", symbol: "square.on.square", previewAsset: "ComponentReferenceInspector",
              documentation: DesktopIdentity.componentDocumentation("reference-inspector"))
    ]
    public static let ids = Set(all.map(\.id))
}

public enum SetupOperation: String, Equatable, Sendable {
    case install, update, remove

    public var progressLabel: String {
        switch self {
        case .install: return "Installing…"
        case .update: return "Updating…"
        case .remove: return "Removing…"
        }
    }
}

public enum SetupItemState: Equatable, Sendable {
    case notInstalled
    case queued(SetupOperation)
    case active(SetupOperation)
    case installed
    case developmentLinked
    case failed(SetupOperation, String)

    public var statusLabel: String {
        switch self {
        case .notInstalled: return "Not installed"
        case .queued: return "Queued"
        case .active(let operation): return operation.progressLabel
        case .installed: return "Installed"
        case .developmentLinked: return "Development link"
        case .failed: return "Failed"
        }
    }

    public var operation: SetupOperation? {
        switch self {
        case .queued(let operation), .active(let operation), .failed(let operation, _): return operation
        case .notInstalled, .installed, .developmentLinked: return nil
        }
    }

    public var failureMessage: String? {
        if case .failed(_, let message) = self { return message }
        return nil
    }

    public var isActive: Bool {
        if case .active = self { return true }
        return false
    }
}

public enum SetupQueueItem: Equatable, Sendable {
    case component(String, SetupOperation)
    case connector(InstallerClientKind, SetupOperation)
}

public enum SetupQueuePolicy {
    public static func bulkPlan(
        installedComponents: Set<String>,
        installedConnectors: Set<InstallerClientKind>
    ) -> [SetupQueueItem] {
        let components = DesktopComponent.all.map {
            SetupQueueItem.component($0.id, installedComponents.contains($0.id) ? .update : .install)
        }
        let connectors = InstallerClientKind.allCases.map {
            SetupQueueItem.connector($0, installedConnectors.contains($0) ? .update : .install)
        }
        return components + connectors
    }
}

/// Checkboxes describe the desired installation; the existing transaction still
/// receives explicit removals so unchecked, absent components are untouched.
public struct DesktopComponentPlan: Sendable {
    public let installed: Set<String>
    public let selected: Set<String>
    public var removals: Set<String> { installed.subtracting(selected) }
    public var hasWork: Bool { !selected.isEmpty || !removals.isEmpty }
    public init(installed: Set<String>, selected: Set<String>) {
        self.installed = installed.intersection(DesktopComponent.ids)
        self.selected = selected.intersection(DesktopComponent.ids)
    }
    public static func initialSelection(installed: Set<String>, hasReceipt: Bool) -> Set<String> {
        hasReceipt || !installed.isEmpty ? installed.intersection(DesktopComponent.ids) : DesktopComponent.ids
    }
    public var arguments: [String] {
        var result = selected.contains("mcp") ? [] : ["--no-mcp"]
        for id in selected.sorted() where id != "mcp" { result += ["--companion", id] }
        for id in removals.sorted() { result += ["--remove", id] }
        return result
    }
    public func action(for id: String) -> String {
        selected.contains(id) ? (installed.contains(id) ? "Install bundled version" : "Install") : (installed.contains(id) ? "Remove" : "Not installed")
    }
}

public struct ComponentTransactionExecutor: Sendable {
    private let handler: @Sendable (DesktopComponentPlan) async throws -> Void

    public init(_ handler: @escaping @Sendable (DesktopComponentPlan) async throws -> Void) {
        self.handler = handler
    }

    public func execute(_ plan: DesktopComponentPlan) async throws {
        try await handler(plan)
    }
}

public struct ConnectorChangeExecutor: Sendable {
    private let handler: @Sendable (InstallerClientKind, SetupOperation) async throws -> Void

    public init(_ handler: @escaping @Sendable (InstallerClientKind, SetupOperation) async throws -> Void) {
        self.handler = handler
    }

    public func execute(_ client: InstallerClientKind, operation: SetupOperation) async throws {
        try await handler(client, operation)
    }
}

/// Waiting is tied to Glyphs' lifetime; errors survive unrelated app events.
public enum ComponentNotice: Equatable {
    case none, waitingForGlyphs, information(String), failure(String)
    public var text: String {
        switch self {
        case .none: return ""
        case .waitingForGlyphs: return "Waiting for Glyphs to close. If a save dialog is open, finish it in Glyphs."
        case .information(let text), .failure(let text): return text
        }
    }
    public var isFailure: Bool { if case .failure = self { return true }; return false }
    public mutating func glyphsRunningChanged(_ running: Bool) {
        if !running && self == .waitingForGlyphs { self = .none }
    }
}

/// Read the existing installation without migrating or rewriting preferences.
public struct DesktopInstallation: Equatable {
    public let root: URL
    public let components: Set<String>
    public let version: String?
    public let python: URL?
    public let application: URL?
    public let port: Int
    public let autoStart: Bool
    public let tokenURL: URL
    public let hasLegacyInstallation: Bool
    public let expectedSidecarHash: String?
    public let expectedBridgeHash: String?
    public let expectedSidecarIdentity: String?
    public let expectedRuntimeIdentity: String?
    public let glyphDiffReader: GlyphDiffReaderContract?
    public let developmentLinkedComponents: Set<String>
    public let brokenDevelopmentLinkedComponents: Set<String>

    public var hasInstallation: Bool { !components.isEmpty || hasLegacyInstallation }
    public var hasServer: Bool { components.contains("mcp") }
    public var isDevelopmentLinked: Bool { !developmentLinkedComponents.isEmpty }
    public var endpoint: URL { URL(string: "http://127.0.0.1:\(port)/mcp/")! }

    public init(home: URL = FileManager.default.homeDirectoryForCurrentUser) {
        root = home.appendingPathComponent("Library/Application Support/Glyphs MCP/lean-v2")
        let receipt = (try? Data(contentsOf: root.appendingPathComponent("installation.json")))
            .flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] } ?? [:]
        let plugins = home.appendingPathComponent("Library/Application Support/Glyphs 4/Plugins")
        let bundles = ["mcp": "Glyphs MCP Bridge.glyphsPlugin",
                       "curve-inspector": "Glyphs Curve Inspector.glyphsReporter",
                       "reference-inspector": "Glyphs Reference Inspector.glyphsReporter"]
        let linked = bundles.compactMap { id, name -> (String, Bool)? in
            let bundle = plugins.appendingPathComponent(name)
            guard (try? FileManager.default.destinationOfSymbolicLink(atPath: bundle.path)) != nil else { return nil }
            return (id, FileManager.default.fileExists(atPath: bundle.path))
        }
        developmentLinkedComponents = Set(linked.compactMap { $0.1 ? $0.0 : nil })
        brokenDevelopmentLinkedComponents = Set(linked.compactMap { $0.1 ? nil : $0.0 })
        if let selected = receipt["components"] as? [String] {
            components = Set(selected).intersection(bundles.keys)
        } else {
            components = Set(bundles.compactMap { key, name in
                FileManager.default.fileExists(atPath: plugins.appendingPathComponent(name).path) ? key : nil
            })
        }
        let sidecarReceipt = receipt["sidecar"] as? [String: Any]
        let runtimeReceipt = receipt["runtime"] as? [String: Any]
        expectedSidecarHash = sidecarReceipt?["codeHash"] as? String
        expectedBridgeHash = (receipt["bridge"] as? [String: Any])?["codeHash"] as? String
        expectedSidecarIdentity = sidecarReceipt?["identity"] as? String
        expectedRuntimeIdentity = runtimeReceipt?["identity"] as? String
        glyphDiffReader = (sidecarReceipt?["glyphDiffReader"] as? [String: Any])
            .flatMap(GlyphDiffReaderContract.init(dictionary:))
        version = receipt["version"] as? String
        let agent = home.appendingPathComponent("Library/LaunchAgents/\(DesktopIdentity.serviceLabel).plist")
        let settings = (try? Data(contentsOf: agent)).flatMap {
            try? PropertyListSerialization.propertyList(from: $0, format: nil) as? [String: Any]
        } ?? [:]
        let args = settings["ProgramArguments"] as? [String] ?? []
        let environment = settings["EnvironmentVariables"] as? [String: String] ?? [:]
        let fallbackPython = root.appendingPathComponent("runtime/bin/python3")
        python = (receipt["python"] as? String).map { URL(fileURLWithPath: $0) }
            ?? (FileManager.default.fileExists(atPath: fallbackPython.path) ? fallbackPython : nil)
        let applicationIndex = args.firstIndex(of: "--glyphs-app")
        let configuredApplication = applicationIndex.flatMap { $0 + 1 < args.count ? args[$0 + 1] : nil }
        application = ((receipt["application"] as? String) ?? configuredApplication).map { URL(fileURLWithPath: $0) }
        tokenURL = environment["GLYPHS_MCP_BRIDGE_TOKEN_FILE"].map { URL(fileURLWithPath: ($0 as NSString).expandingTildeInPath) }
            ?? root.deletingLastPathComponent().appendingPathComponent("bridge-token")
        let index = args.firstIndex(of: "--port")
        let configuredPort = index.flatMap { $0 + 1 < args.count ? Int(args[$0 + 1]) : nil }
            ?? receipt["port"] as? Int ?? 9680
        port = (1024...65535).contains(configuredPort) ? configuredPort : 9680
        autoStart = settings["RunAtLoad"] as? Bool ?? receipt["autoStart"] as? Bool ?? false
        hasLegacyInstallation = FileManager.default.fileExists(atPath:
            home.appendingPathComponent("Library/Application Support/Glyphs 3/Plugins/Glyphs MCP.glyphsPlugin").path)
    }
}
