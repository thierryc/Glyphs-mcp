import Foundation
import CryptoKit

/// Receipt-to-payload comparison; independent companions keep their own versions.
public enum ComponentUpdateStatus: Equatable, Sendable {
    case current, updateAvailable, newerInstalled, unableToVerify, developmentLinked
    public var needsUpdate: Bool { self == .updateAvailable }
}

public enum ComponentUpdatePolicy {
    public static func compare(installedVersion: String?, bundledVersion: String?,
                               installedIdentities: [String?], bundledIdentities: [String?],
                               installedBuild: Int? = nil, bundledBuild: Int? = nil,
                               developmentLinked: Bool = false) -> ComponentUpdateStatus {
        if developmentLinked { return .developmentLinked }
        guard let installedVersion, let bundledVersion,
              installedVersion.range(of: "^[0-9]+(\\.[0-9]+){1,3}$", options: .regularExpression) != nil,
              bundledVersion.range(of: "^[0-9]+(\\.[0-9]+){1,3}$", options: .regularExpression) != nil,
              !installedIdentities.isEmpty, installedIdentities.count == bundledIdentities.count,
              (installedIdentities + bundledIdentities).allSatisfy({ value in
                  value?.range(of: "^sha256:[0-9a-f]{64}$", options: .regularExpression) != nil
              }) else { return .unableToVerify }
        let order = installedVersion.compare(bundledVersion, options: .numeric)
        if order == .orderedDescending { return .newerInstalled }
        if order == .orderedAscending { return .updateAvailable }
        if let installedBuild, let bundledBuild, installedBuild > bundledBuild { return .newerInstalled }
        return installedIdentities == bundledIdentities ? .current : .updateAvailable
    }

    /// CodeDirectory hashes omit CMS timestamps; resource hashing omits only signatures and generated caches.
    public static func stableContentIdentity(_ bundle: URL, nativeCodeHashes: [String]) throws -> String {
        guard !nativeCodeHashes.isEmpty,
              let enumerator = FileManager.default.enumerator(atPath: bundle.path) else {
            throw InstallerError.userFacing("Component content is unavailable.")
        }
        var entries: [(String, URL)] = []
        while let relative = enumerator.nextObject() as? String {
            let url = bundle.appendingPathComponent(relative)
            let parts = relative.split(separator: "/").map(String.init)
            let values = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .isDirectoryKey])
            guard values.isSymbolicLink != true else { throw InstallerError.userFacing("Component link cannot be verified.") }
            if parts.contains("_CodeSignature") || parts.contains("__pycache__") {
                if values.isDirectory == true { enumerator.skipDescendants() }
                continue
            }
            if relative == "Contents/Info.plist" || relative.hasPrefix("Contents/Resources/") {
                if values.isRegularFile == true && !["pyc", "pyo"].contains(url.pathExtension) && url.lastPathComponent != ".DS_Store" {
                    entries.append((relative, url))
                }
            }
        }
        guard entries.contains(where: { $0.0 == "Contents/Info.plist" }) else {
            throw InstallerError.userFacing("Component metadata is unavailable.")
        }
        var digest = SHA256()
        for code in nativeCodeHashes.sorted() { digest.update(data: Data((code + "\0").utf8)) }
        for (relative, url) in entries.sorted(by: { $0.0 < $1.0 }) {
            let name = Data(relative.utf8)
            var length = UInt64(name.count).bigEndian
            withUnsafeBytes(of: &length) { digest.update(data: Data($0)) }
            digest.update(data: name)
            digest.update(data: try Data(contentsOf: url))
        }
        return "sha256:" + digest.finalize().map { String(format: "%02x", $0) }.joined()
    }

    private static func nativeCodeHashes(_ bundle: URL) throws -> [String] {
        let runner = ProcessRunner(), tool = URL(fileURLWithPath: "/usr/bin/codesign")
        guard runner.runSyncWithStderr(executable: tool, args: ["--verify", "--deep", "--strict", bundle.path]).exitCode == 0 else {
            throw InstallerError.userFacing("Component signature cannot be verified.")
        }
        return try ["arm64", "x86_64"].map { architecture in
            let result = runner.runSyncWithStderr(executable: tool, args: ["-d", "--verbose=4", "--arch", architecture, bundle.path])
            guard result.exitCode == 0, let line = result.stderr.split(separator: "\n").first(where: { $0.hasPrefix("CDHash=") }),
                  line.dropFirst(7).range(of: "^[0-9a-f]{40,64}$", options: .regularExpression) != nil else {
                throw InstallerError.userFacing("Component code identity cannot be verified.")
            }
            return architecture + ":" + line.dropFirst(7)
        }
    }

    public static func discover(installation: DesktopInstallation, lean: URL,
                                architecture: String) -> [String: ComponentUpdateStatus] {
        func object(_ url: URL) -> [String: Any] {
            (try? Data(contentsOf: url)).flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] } ?? [:]
        }
        let receipt = object(installation.root.appendingPathComponent("installation.json"))
        let manifest = object(lean.appendingPathComponent("manifest.json"))
        let installedCompanions = receipt["companions"] as? [[String: Any]] ?? []
        let bundledCompanions = manifest["companions"] as? [[String: Any]] ?? []
        let plugins = installation.root.deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Glyphs 4/Plugins")
        var result: [String: ComponentUpdateStatus] = [:]
        for component in DesktopComponent.all where installation.components.contains(component.id) {
            let path = plugins.appendingPathComponent(component.bundle)
            guard !installation.developmentLinkedComponents.contains(component.id),
                  !installation.brokenDevelopmentLinkedComponents.contains(component.id) else {
                result[component.id] = .developmentLinked; continue
            }
            guard FileManager.default.fileExists(atPath: path.path) else {
                result[component.id] = .unableToVerify; continue
            }
            if component.id == "mcp" {
                let installedBridge = receipt["bridge"] as? [String: Any] ?? [:]
                let installedSidecar = receipt["sidecar"] as? [String: Any] ?? [:]
                let bundledBridge = manifest["bridge"] as? [String: Any] ?? [:]
                let bundledSidecar = manifest["sidecar"] as? [String: Any] ?? [:]
                let runtime = receipt["runtime"] as? [String: Any] ?? [:]
                let runtimes = manifest["runtimes"] as? [String: [String: Any]] ?? [:]
                let release = installedBridge["release"] as? [String: Any] ?? [:]
                // A partial or mixed receipt is not evidence of an available update.
                let sidecarRelease = installedSidecar["release"] as? [String: Any] ?? [:]
                let version = installedBridge["version"] as? String
                guard version == receipt["version"] as? String,
                      version == sidecarRelease["version"] as? String else {
                    result[component.id] = .unableToVerify; continue
                }
                result[component.id] = compare(installedVersion: version,
                    bundledVersion: manifest["version"] as? String,
                    installedIdentities: [installedBridge["identity"] as? String, installedSidecar["identity"] as? String, runtime["identity"] as? String],
                    bundledIdentities: [bundledBridge["identity"] as? String, bundledSidecar["identity"] as? String, runtimes[architecture]?["identity"] as? String],
                    installedBuild: release["installerBuild"] as? Int, bundledBuild: manifest["installerBuild"] as? Int)
            } else {
                let installed = installedCompanions.filter { $0["id"] as? String == component.id }
                let bundled = bundledCompanions.filter { $0["id"] as? String == component.id }
                guard installed.count == 1, bundled.count == 1 else {
                    result[component.id] = .unableToVerify; continue
                }
                let state = compare(installedVersion: installed[0]["version"] as? String,
                    bundledVersion: bundled[0]["version"] as? String,
                    installedIdentities: [installed[0]["identity"] as? String],
                    bundledIdentities: [bundled[0]["identity"] as? String])
                if state == .updateAvailable, installed[0]["version"] as? String == bundled[0]["version"] as? String {
                    // Re-signing and stapling change full identities without changing code.
                    // First retain exact ownership checks; then compare stable signed content.
                    let source = lean.appendingPathComponent(component.bundle)
                    do {
                        guard try InstallerPayloadManifestResolver.treeIdentity(path) == installed[0]["identity"] as? String,
                              try InstallerPayloadManifestResolver.treeIdentity(source) == bundled[0]["identity"] as? String else {
                            result[component.id] = .unableToVerify; continue
                        }
                        result[component.id] = try stableContentIdentity(path, nativeCodeHashes: nativeCodeHashes(path))
                            == stableContentIdentity(source, nativeCodeHashes: nativeCodeHashes(source)) ? .current : .updateAvailable
                    } catch { result[component.id] = .unableToVerify }
                } else { result[component.id] = state }
            }
        }
        return result
    }
}

public enum ComponentUpdateReminder {
    public static func title(needsServerUpdate: Bool) -> String {
        needsServerUpdate ? "A new version of the MCP server in Glyphs is available." : "Updates for your Glyphs plugins are available."
    }
    public static func message(needsServerUpdate: Bool) -> String {
        needsServerUpdate ? "The desktop app has been updated, but the server used by Glyphs still needs updating.\n\nOpen Setup, then click Update on the Glyphs MCP card to get the latest features and fixes. You may need to quit and reopen Glyphs." : "Open Setup, then click Update on the highlighted plugin cards to get the latest features and fixes.\n\nYou may need to quit and reopen Glyphs."
    }
    public static func key(version: String, build: String, root: URL) -> String {
        "componentUpdateReminder." + version + "." + build + "." + root.standardizedFileURL.path
    }
    public static func shouldPresent(statuses: [String: ComponentUpdateStatus], alreadyShown: Bool,
                                     interactive: Bool, busy: Bool, otherDialog: Bool) -> Bool {
        !alreadyShown && interactive && !busy && !otherDialog && statuses.contains {
            DesktopComponent.ids.contains($0.key) && $0.value.needsUpdate
        }
    }
}

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

/// Independently distributed companions are visible in Setup but never enter
/// the bundled component transaction or its Install All queue.
public struct ExternalGlyphsCompanion: Identifiable {
    public let id: String
    public let title: String
    public let detail: String
    public let versionLabel: String
    public let availability: String
    public let requirements: String
    public let documentation: URL
    public let engineRelease: URL

    public static let beztrace = ExternalGlyphsCompanion(
        id: "beztrace-glyphs", title: "Beztrace",
        detail: "Trace images and match master outlines in Glyphs.",
        versionLabel: "Bundled engine 0.2.1 · Companion 0.2.0 build 25",
        availability: "Qualified companion · Build 25 · Apple Silicon",
        requirements: "Managed setup: Apple Silicon and macOS 26.6.2 or later. Requires Glyphs 4.1 (build 4107 or later) and Python 3.9 or later in Glyphs. The app includes the beztrace 0.2.1 stable engine. Native companion testing covers Glyphs 4.2 build 4202.",
        documentation: URL(string: "https://github.com/thierryc/beztrace/blob/217dcc0aad50a4c4a6b7e8c65e6bacc0931e2054/Companions/Glyphs/README.md")!,
        engineRelease: URL(string: "https://github.com/thierryc/beztrace/releases/tag/v0.2.1")!
    )
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
    public static func setupCompletion(failedConnections: Int, preservedSkills: Bool) -> ComponentNotice {
        if failedConnections > 0 {
            return .failure("Components installed. Some connections could not be configured. See their details.")
        }
        return .information(preservedSkills
            ? "Setup is complete. Your existing skills were kept. Reload your connected apps and open Glyphs."
            : "Setup is complete. Reload your connected apps and open Glyphs.")
    }
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
