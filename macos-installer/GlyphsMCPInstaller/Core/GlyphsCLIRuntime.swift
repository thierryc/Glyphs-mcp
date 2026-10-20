import Foundation

public struct GlyphsCLIRuntime: Equatable, Sendable {
    public enum Purpose: Sendable { case glyphDiff, packageCopy }
    public enum Source: String, Equatable, Sendable { case bundled, installed }

    public let glyphsCLI: URL
    public let sidecar: URL
    public let source: Source
    public let notice: String?

    public init(glyphsCLI: URL, sidecar: URL, source: Source = .bundled, notice: String? = nil) {
        self.glyphsCLI = glyphsCLI
        self.sidecar = sidecar
        self.source = source
        self.notice = notice
    }

    private struct LeanManifest: Decodable {
        struct Runtime: Decodable { let path: String; let glyphsCLI: String }
        let glyphDiffReader: GlyphDiffReaderContract
        let runtimes: [String: Runtime]
    }

    public static var processArchitecture: String {
        #if arch(arm64)
        return "arm64"
        #elseif arch(x86_64)
        return "x86_64"
        #else
        return "unsupported"
        #endif
    }

    /// Prefer the already-validated app payload. The installed fallback must
    /// match its immutable receipt and the exact reader contract.
    public static func resolve(
        installation: DesktopInstallation = DesktopInstallation(),
        validatedPayload: InstallerPayload?,
        bundledPayloadError: String? = nil,
        architecture: String = processArchitecture,
        purpose: Purpose = .glyphDiff,
        fileManager: FileManager = .default
    ) throws -> GlyphsCLIRuntime {
        var failures: [String] = []
        if let validatedPayload {
            do { return try bundled(payload: validatedPayload.payloadDir, architecture: architecture, purpose: purpose, fileManager: fileManager) }
            catch { failures.append("Bundled reader: \(error.localizedDescription)") }
        }
        if let bundledPayloadError { failures.append("Bundled payload: \(bundledPayloadError)") }
        do {
            return try installed(installation: installation, purpose: purpose, fileManager: fileManager)
        } catch {
            failures.append("Installed reader: \(error.localizedDescription)")
        }
        throw ProjectError(
            (purpose == .glyphDiff ? "Visual preview components are out of sync. Rebuild or update Glyphs MCP. The text diff remains available. "
             : NSLocalizedString("Package copy components are unavailable. Rebuild or update Glyphs MCP. ", comment: "")) + failures.joined(separator: " ")
        )
    }

    private static func bundled(
        payload: URL,
        architecture: String,
        purpose: Purpose,
        fileManager: FileManager
    ) throws -> GlyphsCLIRuntime {
        let lean = payload.appendingPathComponent("Lean", isDirectory: true)
        let manifest = try JSONDecoder().decode(
            LeanManifest.self,
            from: Data(contentsOf: lean.appendingPathComponent("manifest.json"))
        )
        guard (purpose != .glyphDiff || manifest.glyphDiffReader == .expected),
              let runtime = manifest.runtimes[architecture],
              runtime.path == "runtimes/\(architecture)", runtime.glyphsCLI == "bin/glyphs" else {
            throw ProjectError("The reader contract or architecture is unsupported.")
        }
        let candidate = GlyphsCLIRuntime(
            glyphsCLI: lean.appendingPathComponent(runtime.path).appendingPathComponent(runtime.glyphsCLI),
            sidecar: lean.appendingPathComponent("sidecar", isDirectory: true),
            source: .bundled
        )
        try validateFiles(candidate, purpose: purpose, fileManager: fileManager)
        return candidate
    }

    private static func installed(
        installation: DesktopInstallation,
        purpose: Purpose,
        fileManager: FileManager
    ) throws -> GlyphsCLIRuntime {
        guard (purpose != .glyphDiff || installation.glyphDiffReader == .expected),
              let sidecarIdentity = installation.expectedSidecarIdentity,
              let runtimeIdentity = installation.expectedRuntimeIdentity else {
            throw ProjectError("The installation receipt has no compatible reader contract.")
        }
        let sidecar = installation.root.appendingPathComponent("sidecar", isDirectory: true)
        let runtime = installation.root.appendingPathComponent("runtime", isDirectory: true)
        try rejectSymbolicLink(installation.root, fileManager: fileManager)
        try rejectSymbolicLink(sidecar, fileManager: fileManager)
        try rejectSymbolicLink(runtime, fileManager: fileManager)
        guard try InstallerPayloadManifestResolver.treeIdentity(sidecar) == sidecarIdentity,
              try InstallerPayloadManifestResolver.treeIdentity(runtime) == runtimeIdentity else {
            throw ProjectError("The installed sidecar or runtime does not match its receipt.")
        }
        let candidate = GlyphsCLIRuntime(
            glyphsCLI: runtime.appendingPathComponent("bin/glyphs"),
            sidecar: sidecar,
            source: .installed,
            notice: "Using the verified installed visual reader because the bundled reader was unavailable."
        )
        try validateFiles(candidate, purpose: purpose, fileManager: fileManager)
        return candidate
    }

    private static func rejectSymbolicLink(_ url: URL, fileManager: FileManager) throws {
        let attributes = try fileManager.attributesOfItem(atPath: url.path)
        guard attributes[.type] as? FileAttributeType != .typeSymbolicLink else {
            throw ProjectError("The visual reader path contains a symbolic link.")
        }
    }

    private static func validateFiles(_ runtime: GlyphsCLIRuntime, purpose: Purpose, fileManager: FileManager) throws {
        let modules = purpose == .glyphDiff
            ? ["glyphs_mcp_sidecar/glyph_diff_worker.py", "glyphs_mcp_protocol/geometry.py"]
            : ["glyphs_mcp_sidecar/package_copy.py", "glyphs_mcp_sidecar/package_copy_native.py", "glyphs_mcp_protocol/python_runtime.py"]
        let required = modules.map { runtime.sidecar.appendingPathComponent($0) }
        guard fileManager.isExecutableFile(atPath: runtime.glyphsCLI.path) else {
            throw ProjectError("The Glyphs command-line runtime is unavailable.")
        }
        for file in required {
            let values = try file.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey])
            guard values.isRegularFile == true, values.isSymbolicLink != true else {
                throw ProjectError("The Glyphs command-line runtime contains a missing or unsafe module.")
            }
        }
    }
}


// Retain the existing preview API while sharing runtime validation.
public typealias GlyphDiffRuntime = GlyphsCLIRuntime
