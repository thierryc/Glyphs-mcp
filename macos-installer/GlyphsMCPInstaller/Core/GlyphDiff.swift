import Foundation

public struct GlyphPathElement: Codable, Equatable, Sendable {
    public let kind: Int
    public let points: [[Double]]

    public init(kind: Int, points: [[Double]]) {
        self.kind = kind
        self.points = points
    }
}

public struct GlyphMetrics: Codable, Equatable, Sendable {
    public let ascender: Double
    public let capHeight: Double
    public let xHeight: Double
    public let descender: Double

    public init(ascender: Double, capHeight: Double, xHeight: Double, descender: Double) {
        self.ascender = ascender
        self.capHeight = capHeight
        self.xHeight = xHeight
        self.descender = descender
    }
}

public struct GlyphLayerSnapshot: Codable, Equatable, Identifiable, Sendable {
    public let id: String
    public let label: String
    public let isMaster: Bool
    public let outline: [GlyphPathElement]
    public let openOutline: [GlyphPathElement]
    public let anchors: [String: [Double]]
    public let width: Double
    public let metrics: GlyphMetrics
    public let bounds: [Double]?

    public init(
        id: String,
        label: String,
        isMaster: Bool,
        outline: [GlyphPathElement],
        openOutline: [GlyphPathElement],
        anchors: [String: [Double]],
        width: Double,
        metrics: GlyphMetrics,
        bounds: [Double]? = nil
    ) {
        self.id = id
        self.label = label
        self.isMaster = isMaster
        self.outline = outline
        self.openOutline = openOutline
        self.anchors = anchors
        self.width = width
        self.metrics = metrics
        self.bounds = bounds
    }
}

public struct GlyphFontSnapshot: Codable, Equatable, Sendable {
    public let missingGlyph: Bool
    public let glyphName: String?
    public let layers: [GlyphLayerSnapshot]

    public init(missingGlyph: Bool, glyphName: String?, layers: [GlyphLayerSnapshot]) {
        self.missingGlyph = missingGlyph
        self.glyphName = glyphName
        self.layers = layers
    }
}

public struct GlyphChangedAnchor: Codable, Equatable, Sendable {
    public let name: String
    public let before: [Double]?
    public let after: [Double]?

    public init(name: String, before: [Double]?, after: [Double]?) {
        self.name = name
        self.before = before
        self.after = after
    }
}

public struct GlyphDifferenceRegion: Codable, Equatable, Identifiable, Sendable {
    public enum Kind: String, Codable, Sendable {
        case geometry
        case anchor
        case width
    }

    public let id: String
    public let kind: Kind
    public let bounds: [Double]

    public init(id: String, kind: Kind, bounds: [Double]) {
        self.id = id
        self.kind = kind
        self.bounds = bounds
    }
}

public struct GlyphLayerDifference: Codable, Equatable, Identifiable, Sendable {
    public let id: String
    public let label: String
    public let outlineChanged: Bool
    public let referenceOutline: [GlyphPathElement]
    public let currentOutline: [GlyphPathElement]
    public let referenceSegments: [GlyphPathElement]
    public let currentSegments: [GlyphPathElement]
    public let anchors: [GlyphChangedAnchor]
    public let width: [Double?]?
    public let metricRange: [Double]
    public let regions: [GlyphDifferenceRegion]
    public let hasVisibleDifference: Bool

    public init(
        id: String,
        label: String,
        outlineChanged: Bool,
        referenceOutline: [GlyphPathElement],
        currentOutline: [GlyphPathElement],
        referenceSegments: [GlyphPathElement],
        currentSegments: [GlyphPathElement],
        anchors: [GlyphChangedAnchor],
        width: [Double?]?,
        metricRange: [Double],
        regions: [GlyphDifferenceRegion],
        hasVisibleDifference: Bool
    ) {
        self.id = id
        self.label = label
        self.outlineChanged = outlineChanged
        self.referenceOutline = referenceOutline
        self.currentOutline = currentOutline
        self.referenceSegments = referenceSegments
        self.currentSegments = currentSegments
        self.anchors = anchors
        self.width = width
        self.metricRange = metricRange
        self.regions = regions
        self.hasVisibleDifference = hasVisibleDifference
    }
}

public struct GlyphLayerPair: Equatable, Identifiable, Sendable {
    public let id: String
    public let label: String
    public let before: GlyphLayerSnapshot?
    public let after: GlyphLayerSnapshot?
    public let difference: GlyphLayerDifference?
    public var changed: Bool { difference?.hasVisibleDifference ?? (before != after) }
}

public struct GlyphDiffDocument: Codable, Equatable, Sendable {
    public let schemaVersion: Int
    public let before: GlyphFontSnapshot
    public let after: GlyphFontSnapshot
    public let changedLayerIDs: [String]
    public let differences: [GlyphLayerDifference]

    public init(
        schemaVersion: Int,
        before: GlyphFontSnapshot,
        after: GlyphFontSnapshot,
        changedLayerIDs: [String] = [],
        differences: [GlyphLayerDifference] = []
    ) {
        self.schemaVersion = schemaVersion
        self.before = before
        self.after = after
        self.changedLayerIDs = changedLayerIDs
        self.differences = differences
    }

    public var layers: [GlyphLayerPair] {
        var unusedBefore = before.layers
        var result: [GlyphLayerPair] = []
        for layer in after.layers {
            let match = unusedBefore.firstIndex(where: { $0.id == layer.id })
                ?? unusedBefore.firstIndex(where: { $0.label == layer.label })
            let old = match.map { unusedBefore.remove(at: $0) }
            let difference = differences.first(where: { $0.id == layer.id })
                ?? differences.first(where: { $0.label == layer.label })
            result.append(.init(id: layer.id, label: layer.label, before: old, after: layer, difference: difference))
        }
        result.append(contentsOf: unusedBefore.map { layer in
            .init(id: layer.id, label: layer.label, before: layer, after: nil,
                  difference: differences.first(where: { $0.id == layer.id }))
        })
        return result
    }

    public var initialLayerID: String? {
        changedLayerIDs.first(where: { changed in layers.contains(where: { $0.id == changed }) })
            ?? layers.first(where: \.changed)?.id
            ?? layers.first?.id
    }
}

public struct GlyphViewportState: Equatable, Sendable {
    public let centerX: Double
    public let centerY: Double
    public let magnification: Double

    public init(centerX: Double, centerY: Double, magnification: Double) {
        self.centerX = centerX
        self.centerY = centerY
        self.magnification = magnification
    }
}

public enum GlyphViewportMath {
    public static let minimumMagnification = 0.25
    public static let maximumMagnification = 32.0
    public static let step = 1.25

    public static func clamped(_ value: Double) -> Double {
        min(maximumMagnification, max(minimumMagnification, value))
    }

    public static func stepped(_ value: Double, direction: Int) -> Double {
        clamped(value * (direction < 0 ? 1 / step : step))
    }

    public static func smooth(_ value: Double, wheelDelta: Double) -> Double {
        clamped(value * exp(wheelDelta * 0.0025))
    }

    public static func fitted(_ viewBox: CGRect) -> GlyphViewportState {
        GlyphViewportState(centerX: viewBox.midX, centerY: viewBox.midY, magnification: 1)
    }

    public static func focused(viewport: CGSize, viewBox: CGRect, target: CGRect) -> GlyphViewportState {
        GlyphViewportState(centerX: target.midX, centerY: target.midY,
                           magnification: magnificationToFit(viewport: viewport, viewBox: viewBox, target: target))
    }

    /// Preserve the content-space anchor under a root-SVG point while changing scale.
    public static func anchored(_ state: GlyphViewportState, magnification: Double,
                                contentAnchor: CGPoint, rootAnchor: CGPoint,
                                viewBox: CGRect) -> GlyphViewportState {
        let next = clamped(magnification)
        return GlyphViewportState(
            centerX: contentAnchor.x - (rootAnchor.x - viewBox.midX) / next,
            centerY: contentAnchor.y - (rootAnchor.y - viewBox.midY) / next,
            magnification: next
        )
    }

    public static func isRestorable(_ state: GlyphViewportState, in viewBox: CGRect) -> Bool {
        guard state.centerX.isFinite, state.centerY.isFinite, state.magnification.isFinite,
              state.magnification >= minimumMagnification,
              state.magnification <= maximumMagnification,
              viewBox.width > 0, viewBox.height > 0 else { return false }
        return viewBox.insetBy(dx: -viewBox.width, dy: -viewBox.height)
            .contains(CGPoint(x: state.centerX, y: state.centerY))
    }

    public static func focusRect(for bounds: [Double]) -> CGRect? {
        guard bounds.count >= 4 else { return nil }
        let width = max(160, bounds[2] * 1.2)
        let height = max(160, bounds[3] * 1.2)
        return CGRect(x: bounds[0] + (bounds[2] - width) / 2,
                      y: bounds[1] + (bounds[3] - height) / 2,
                      width: width, height: height)
    }

    public static func fitScale(viewport: CGSize, viewBox: CGRect) -> Double {
        guard viewport.width > 0, viewport.height > 0, viewBox.width > 0, viewBox.height > 0 else { return 1 }
        return min(viewport.width / viewBox.width, viewport.height / viewBox.height)
    }

    public static func magnificationToFit(viewport: CGSize, viewBox: CGRect, target: CGRect) -> Double {
        let base = fitScale(viewport: viewport, viewBox: viewBox)
        guard target.width > 0, target.height > 0, base > 0 else { return 1 }
        return clamped(min(viewport.width / target.width, viewport.height / target.height) / base)
    }

    public static func actualSizeMagnification(viewport: CGSize, viewBox: CGRect) -> Double {
        clamped(1 / fitScale(viewport: viewport, viewBox: viewBox))
    }
}

public struct GlyphDiffRuntime: Equatable, Sendable {
    public let glyphsCLI: URL
    public let sidecar: URL

    public init(glyphsCLI: URL, sidecar: URL) {
        self.glyphsCLI = glyphsCLI
        self.sidecar = sidecar
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

    /// Prefer the app's version-matched payload. An existing installation is
    /// retained as a fallback for development builds that do not embed it.
    public static func resolve(
        installation: DesktopInstallation = DesktopInstallation(),
        resourceURL: URL? = Bundle.main.resourceURL,
        extractedPayloadURL: URL? = nil,
        architecture: String = processArchitecture,
        fileManager: FileManager = .default
    ) throws -> GlyphDiffRuntime {
        var candidates: [GlyphDiffRuntime] = []
        if let resourceURL {
            let lean = resourceURL.appendingPathComponent("Payload/Lean", isDirectory: true)
            candidates.append(.init(
                glyphsCLI: lean.appendingPathComponent("runtimes/\(architecture)/bin/glyphs"),
                sidecar: lean.appendingPathComponent("sidecar", isDirectory: true)
            ))
        }
        if let extractedPayloadURL {
            let lean = extractedPayloadURL.appendingPathComponent("Lean", isDirectory: true)
            candidates.append(.init(
                glyphsCLI: lean.appendingPathComponent("runtimes/\(architecture)/bin/glyphs"),
                sidecar: lean.appendingPathComponent("sidecar", isDirectory: true)
            ))
        }
        candidates.append(.init(
            glyphsCLI: installation.root.appendingPathComponent("runtime/bin/glyphs"),
            sidecar: installation.root.appendingPathComponent("sidecar", isDirectory: true)
        ))
        if let runtime = candidates.first(where: {
            fileManager.isExecutableFile(atPath: $0.glyphsCLI.path)
                && fileManager.isReadableFile(atPath: $0.sidecar.appendingPathComponent(
                    "glyphs_mcp_sidecar/glyph_diff_worker.py"
                ).path)
        }) {
            return runtime
        }
        throw ProjectError(
            "Install or update the Glyphs MCP component to enable visual glyph diffs. " +
            "The text diff remains available."
        )
    }
}

public struct GlyphDiffService {
    private struct WorkerRequest: Encodable {
        let beforePackage: String?
        let beforeGlyph: String?
        let afterPackage: String?
        let afterGlyph: String?
        let output: String
    }
    private struct WorkerResponse: Decodable {
        let ok: Bool
        let data: GlyphDiffDocument?
        let error: String?
    }
    private struct PackageLocation {
        let packagePath: String
        let glyphPath: String
    }

    private let runner = ProcessRunner()
    private let fileManager = FileManager.default

    public init() {}

    public func compare(
        project: URL,
        change: GitObservation.Change,
        headRevision: String?
    ) async throws -> GlyphDiffDocument {
        guard change.isGlyphPackageGlyph else { throw ProjectError("Visual comparison is available for glyph files inside .glyphspackage sources.") }
        let afterLocation = try location(change.path)
        let beforeLocation = try location(change.originalPath ?? change.path)
        let runtime = try await ProjectFiles.perform {
            let payload = try? InstallerPayload.resolve()
            return try GlyphDiffRuntime.resolve(extractedPayloadURL: payload?.payloadDir)
        }
        let installation = DesktopInstallation()
        var applications = GlyphsApplicationDetector.detect()
        if let installed = installation.application {
            applications.append(contentsOf: GlyphsApplicationDetector.detect(candidates: [installed]))
        }
        let glyphs4 = applications.filter { $0.majorVersion == .v4 }
        let application = glyphs4.first(where: { $0.appURL.standardizedFileURL == installation.application?.standardizedFileURL })?.appURL
            ?? glyphs4.first?.appURL
        guard let application else { throw ProjectError("Glyphs 4 is required for the visual glyph diff.") }

        let temporary = fileManager.temporaryDirectory.appendingPathComponent("glyphs-git-diff-\(UUID().uuidString)", isDirectory: true)
        try fileManager.createDirectory(at: temporary, withIntermediateDirectories: true)
        defer { try? fileManager.removeItem(at: temporary) }

        let beforePackage: URL?
        if let headRevision {
            beforePackage = try await materialize(
                project: project,
                revision: headRevision,
                location: beforeLocation,
                temporary: temporary
            )
        } else {
            beforePackage = nil
        }
        let afterPackage = project.appendingPathComponent(afterLocation.packagePath, isDirectory: true)
        let afterGlyph = project.appendingPathComponent(afterLocation.glyphPath)
        if fileManager.fileExists(atPath: afterPackage.path) {
            try Self.validateMaterializedPackage(afterPackage)
        }
        let beforeGlyph = beforePackage?.appendingPathComponent(
            String(beforeLocation.glyphPath.dropFirst(beforeLocation.packagePath.count + 1))
        )
        let output = temporary.appendingPathComponent("result.json")
        let request = temporary.appendingPathComponent("request.json")
        let payload = WorkerRequest(
            beforePackage: beforePackage?.path,
            beforeGlyph: beforeGlyph?.path,
            afterPackage: fileManager.fileExists(atPath: afterPackage.path) ? afterPackage.path : nil,
            afterGlyph: fileManager.fileExists(atPath: afterGlyph.path) ? afterGlyph.path : nil,
            output: output.path
        )
        try JSONEncoder().encode(payload).write(to: request, options: .atomic)
        let result = try await runner.runCapturing(
            executable: runtime.glyphsCLI,
            args: ["run", "--quiet", "--app", application.path, "--plugins", "", "-m",
                   "glyphs_mcp_sidecar.glyph_diff_worker", "--", request.path],
            environment: ["PATH": "/usr/bin:/bin", "PYTHONPATH": runtime.sidecar.path,
                          "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1", "HOME": fileManager.homeDirectoryForCurrentUser.path],
            timeout: 90
        )
        guard result.exitCode == 0 else {
            if result.stderr.contains("No module named glyphs_mcp_sidecar.glyph_diff_worker") {
                throw ProjectError(
                    "Update the installed Glyphs MCP component to enable visual glyph diffs. " +
                    "The text diff remains available."
                )
            }
            let detail = result.stderr.split(whereSeparator: \.isNewline).last.map(String.init)
            throw ProjectError(detail.map { "The Glyphs geometry reader could not start: \($0)" }
                ?? "The Glyphs geometry reader could not start.")
        }
        let response = try JSONDecoder().decode(WorkerResponse.self, from: Data(contentsOf: output))
        guard response.ok, let document = response.data, document.schemaVersion == 2 else {
            throw ProjectError(response.error ?? "The Glyphs geometry reader returned an unsupported result.")
        }
        return document
    }

    public static func validateMaterializedPackage(_ package: URL) throws {
        let manager = FileManager.default
        let root = package.standardizedFileURL
        let rootAttributes = try manager.attributesOfItem(atPath: root.path)
        guard rootAttributes[.type] as? FileAttributeType == .typeDirectory else {
            throw ProjectError("The glyph package is not a regular directory.")
        }
        guard let enumerator = manager.enumerator(
            at: root,
            includingPropertiesForKeys: [.isSymbolicLinkKey],
            options: [.skipsHiddenFiles]
        ) else { throw ProjectError("The glyph package could not be inspected safely.") }
        while let entry = enumerator.nextObject() as? URL {
            if try entry.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink == true {
                enumerator.skipDescendants()
                throw ProjectError("Symbolic links are not allowed in a visual glyph comparison package.")
            }
        }
    }

    private func location(_ path: String) throws -> PackageLocation {
        try ProjectFiles.validateRelativePath(path)
        let parts = path.split(separator: "/").map(String.init)
        guard let packageIndex = parts.firstIndex(where: { $0.hasSuffix(".glyphspackage") }),
              packageIndex + 2 == parts.count - 1,
              parts[packageIndex + 1] == "glyphs",
              parts.last?.hasSuffix(".glyph") == true else {
            throw ProjectError("The selected file is not a glyph inside a .glyphspackage source.")
        }
        return .init(packagePath: parts[...packageIndex].joined(separator: "/"), glyphPath: parts.joined(separator: "/"))
    }

    private func materialize(
        project: URL,
        revision: String,
        location: PackageLocation,
        temporary: URL
    ) async throws -> URL? {
        guard let git = ReadOnlyGit().executable else { throw ProjectError("Git is unavailable.") }
        let archive = temporary.appendingPathComponent("before.tar")
        let extracted = temporary.appendingPathComponent("before", isDirectory: true)
        try fileManager.createDirectory(at: extracted, withIntermediateDirectories: true)
        let environment = ["PATH": "/usr/bin:/bin", "HOME": fileManager.homeDirectoryForCurrentUser.path,
                           "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_OPTIONAL_LOCKS": "0",
                           "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"]
        let archived = try await runner.runCapturing(
            executable: git,
            args: ["--no-optional-locks", "--literal-pathspecs", "-c", "core.hooksPath=/dev/null", "-C", project.path,
                   "archive", "--format=tar", "--output", archive.path, revision, "--", location.packagePath],
            environment: environment,
            timeout: 30
        )
        if archived.exitCode != 0 { return nil }
        let unpacked = try await runner.runCapturing(
            executable: URL(fileURLWithPath: "/usr/bin/tar"),
            args: ["-xf", archive.path, "-C", extracted.path],
            environment: ["PATH": "/usr/bin:/bin"],
            timeout: 30
        )
        guard unpacked.exitCode == 0 else { throw ProjectError("Could not unpack the reference glyph package.") }
        let package = extracted.appendingPathComponent(location.packagePath, isDirectory: true)
        guard fileManager.fileExists(atPath: package.path) else { return nil }
        try Self.validateMaterializedPackage(package)
        return package
    }
}
