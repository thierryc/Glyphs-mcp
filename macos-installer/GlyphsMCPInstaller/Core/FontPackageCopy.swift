import Foundation

public struct ProjectFontSource: Identifiable, Equatable, Sendable {
    public let url: URL
    public let relativePath: String
    public var id: String { url.path }
    public var canCreatePackageCopy: Bool { url.pathExtension.lowercased() == "glyphs" }
}

public enum FontSourceDiscovery {
    public static func scan(_ project: URL) throws -> [ProjectFontSource] {
        let root = project.resolvingSymlinksInPath().standardizedFileURL
        let manager = FileManager.default
        var failure: Error?
        let keys: Set<URLResourceKey> = [.isRegularFileKey, .isDirectoryKey, .isSymbolicLinkKey, .isPackageKey]
        guard let entries = manager.enumerator(at: root, includingPropertiesForKeys: Array(keys),
            options: [.skipsHiddenFiles], errorHandler: { _, error in failure = error; return false }) else {
            throw ProjectError(NSLocalizedString("The font sources could not be read.", comment: ""))
        }
        var sources: [ProjectFontSource] = []
        while let url = entries.nextObject() as? URL {
            try Task.checkCancellation()
            let values = try url.resourceValues(forKeys: keys)
            // Directory enumeration does not follow symbolic links. Calling
            // skipDescendants on a symlink to a file can skip the next folder.
            if values.isSymbolicLink == true { continue }
            let ext = url.pathExtension.lowercased()
            if (ext == "glyphs" && values.isRegularFile == true)
                || (ext == "glyphspackage" && values.isDirectory == true) {
                let canonical = url.resolvingSymlinksInPath().standardizedFileURL
                let relative = canonical.pathComponents.dropFirst(root.pathComponents.count).joined(separator: "/")
                sources.append(.init(url: canonical, relativePath: relative))
            }
            if values.isDirectory == true && (values.isPackage == true || ext == "glyphspackage") {
                entries.skipDescendants()
            }
        }
        if let failure { throw failure }
        return sources.sorted { $0.relativePath.localizedStandardCompare($1.relativePath) == .orderedAscending }
    }
}

public struct FontPackageCopyResult: Decodable, Equatable, Sendable {
    public let destination: String
    public let sourceSHA256: String
    public let glyphCount: Int
    public let masterCount: Int
    public let formatVersion: Int
    public var url: URL { URL(fileURLWithPath: destination) }
}

public actor FontPackageCopyService {
    public static let shared = FontPackageCopyService()
    private var activeSources: Set<String> = []
    public init() {}

    public static func destination(source: URL, name: String) throws -> URL {
        guard !name.isEmpty, !name.hasPrefix("."), !name.contains("/"), !name.contains("\\"),
              !name.unicodeScalars.contains(where: CharacterSet.controlCharacters.contains),
              name.hasSuffix(".glyphspackage"), name != ".glyphspackage" else {
            throw ProjectError(NSLocalizedString("Enter a filename ending in .glyphspackage, without folders.", comment: ""))
        }
        let destination = source.deletingLastPathComponent().appendingPathComponent(name)
        if (try? FileManager.default.attributesOfItem(atPath: destination.path)) != nil {
            throw ProjectError(NSLocalizedString("That destination already exists. Choose another filename.", comment: ""))
        }
        return destination
    }

    public func create(source: URL, name: String) async throws -> FontPackageCopyResult {
        let values = try source.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey])
        guard source.pathExtension.lowercased() == "glyphs", values.isRegularFile == true,
              values.isSymbolicLink != true else {
            throw ProjectError(NSLocalizedString("Choose a regular .glyphs source file.", comment: ""))
        }
        let source = source.resolvingSymlinksInPath().standardizedFileURL
        let destination = try Self.destination(source: source, name: name)
        guard activeSources.insert(source.path).inserted else {
            throw ProjectError(NSLocalizedString("A package copy is already running for this source.", comment: ""))
        }
        defer { activeSources.remove(source.path) }

        let (runtime, application) = try await ProjectFiles.perform {
            let payload: InstallerPayload?
            let payloadError: String?
            do { payload = try InstallerPayload.resolve(); payloadError = nil }
            catch { payload = nil; payloadError = error.localizedDescription }
            let installation = DesktopInstallation()
            let runtime = try GlyphsCLIRuntime.resolve(installation: installation, validatedPayload: payload,
                bundledPayloadError: payloadError, purpose: .packageCopy)
            var applications = GlyphsApplicationDetector.detect()
            if let selected = installation.application {
                applications.append(contentsOf: GlyphsApplicationDetector.detect(candidates: [selected]))
            }
            let supported = applications.filter { $0.majorVersion == .v4 }
            let application = supported.first(where: { $0.appURL.standardizedFileURL == installation.application?.standardizedFileURL })?.appURL
                ?? supported.first?.appURL
            guard let application else {
                throw ProjectError(NSLocalizedString("Glyphs 4 is required to create a package copy.", comment: ""))
            }
            return (runtime, application)
        }
        let temporary = FileManager.default.temporaryDirectory.appendingPathComponent("glyphs-package-copy-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporary, withIntermediateDirectories: false)
        defer { try? FileManager.default.removeItem(at: temporary) }
        let request = temporary.appendingPathComponent("request.json")
        let output = temporary.appendingPathComponent("result.json")
        let body = ["source": source.path, "destination": destination.path, "cli": runtime.glyphsCLI.path,
                    "application": application.path, "result": output.path]
        try JSONSerialization.data(withJSONObject: body).write(to: request, options: .atomic)
        let python = runtime.glyphsCLI.deletingLastPathComponent().appendingPathComponent("python3")
        let worker = runtime.sidecar.appendingPathComponent("glyphs_mcp_sidecar/package_copy.py")
        let runner = ProcessRunner()
        let executionError: Error?
        do {
            _ = try await runner.runCapturing(executable: python, args: ["-B", worker.path, request.path],
                environment: ["PATH": "/usr/bin:/bin", "PYTHONPATH": runtime.sidecar.path,
                              "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
                              "HOME": FileManager.default.homeDirectoryForCurrentUser.path], timeout: 330)
            executionError = nil
        } catch { executionError = error }
        // A cancellation racing with publication can still have a verified
        // result. Reconcile that result before reporting cancellation.
        struct Response: Decodable {
            let ok: Bool
            let data: FontPackageCopyResult?
            let error: String?
            let cancelled: Bool?
        }
        if let data = try? Data(contentsOf: output), let response = try? JSONDecoder().decode(Response.self, from: data) {
            if response.ok, let result = response.data,
               result.url.resolvingSymlinksInPath().standardizedFileURL.path == destination.resolvingSymlinksInPath().standardizedFileURL.path,
               FileManager.default.fileExists(atPath: destination.path) { return result }
            if response.cancelled == true || Task.isCancelled { throw CancellationError() }
            throw ProjectError(response.error ?? NSLocalizedString("The package copy could not be verified.", comment: ""))
        }
        if let executionError { throw executionError }
        throw ProjectError(NSLocalizedString("The package copy worker returned no result. Rebuild or update Glyphs MCP.", comment: ""))
    }
}
