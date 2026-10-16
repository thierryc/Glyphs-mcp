import Foundation
import CryptoKit
import ImageIO
import UniformTypeIdentifiers
import Darwin

public enum GitImageFailure: String, Equatable, Sendable {
    case invalid, oversized, dimensions, symbolicLink, unreadable
    public var message: String {
        switch self {
        case .invalid: return "This version is not a readable PNG, JPEG, or WebP image."
        case .oversized: return "This image exceeds the 16 MB preview limit."
        case .dimensions: return "This image exceeds the 32-megapixel preview limit."
        case .symbolicLink: return "Symbolic links and nonregular files are not previewed."
        case .unreadable: return "This image could not be read. Refresh the comparison to try again."
        }
    }
}

public struct GitRasterImage: Equatable, Sendable {
    public let identity: String
    public let width: Int
    public let height: Int
    public let format: String
    public let frameCount: Int
    /// Orientation-normalized, bounded raster. No arbitrary file URLs or SVG.
    public let previewData: Data
    public static let maximumBytes = 16 * 1024 * 1024
    public static let maximumPixels = 32_000_000
    public static let previewDimension = 2048

    public static func read(_ data: Data) -> GitImageSide {
        guard data.count <= maximumBytes else { return .unavailable(.oversized) }
        guard let source = CGImageSourceCreateWithData(data as CFData, [kCGImageSourceShouldCache: false] as CFDictionary),
              let type = CGImageSourceGetType(source) as String?,
              let format = [UTType.png.identifier: "PNG", UTType.jpeg.identifier: "JPEG", UTType.webP.identifier: "WebP"][type],
              let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
              let w = (properties[kCGImagePropertyPixelWidth] as? NSNumber)?.intValue,
              let h = (properties[kCGImagePropertyPixelHeight] as? NSNumber)?.intValue,
              w > 0, h > 0 else { return .unavailable(.invalid) }
        guard w <= maximumPixels / h else { return .unavailable(.dimensions) }
        let orientation = (properties[kCGImagePropertyOrientation] as? NSNumber)?.intValue ?? 1
        let rotated = (5...8).contains(orientation)
        let options: [CFString: Any] = [kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true, kCGImageSourceThumbnailMaxPixelSize: previewDimension,
            kCGImageSourceShouldCacheImmediately: true]
        guard let raster = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary) else { return .unavailable(.invalid) }
        let normalized = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(normalized, UTType.png.identifier as CFString, 1, nil) else {
            return .unavailable(.invalid)
        }
        CGImageDestinationAddImage(destination, raster, nil)
        guard CGImageDestinationFinalize(destination) else { return .unavailable(.invalid) }
        return .image(GitRasterImage(identity: SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined(),
            width: rotated ? h : w, height: rotated ? w : h, format: format,
            frameCount: CGImageSourceGetCount(source), previewData: normalized as Data))
    }
}

public enum GitImageSide: Equatable, Sendable {
    case image(GitRasterImage), missing, unavailable(GitImageFailure)
    public var image: GitRasterImage? { if case .image(let value) = self { return value }; return nil }
    public var message: String {
        switch self {
        case .image(let image): return "\(image.width) × \(image.height) px · \(image.format)"
        case .missing: return "Not present in this version."
        case .unavailable(let error): return error.message
        }
    }
    var identity: String {
        switch self { case .image(let value): return value.identity; case .missing: return "missing"; case .unavailable(let reason): return reason.rawValue }
    }
    var fileContent: GitFileContent {
        if case .missing = self { return .missing }
        return .binary
    }
}

public struct GitImageComparison: Equatable, Sendable {
    public let previous: GitImageSide
    public let current: GitImageSide
    public init(previous: GitImageSide, current: GitImageSide) { self.previous = previous; self.current = current }
    public var identity: String { previous.identity + ":" + current.identity }
    public var canCompare: Bool { previous.image != nil && current.image != nil }
    public var dimensionsDiffer: Bool {
        guard let before = previous.image, let after = current.image else { return false }
        return before.width != after.width || before.height != after.height
    }
    public var canvasWidth: Int { max(previous.image?.width ?? 1, current.image?.width ?? 1) }
    public var canvasHeight: Int { max(previous.image?.height ?? 1, current.image?.height ?? 1) }
    public var cachedBytes: Int { (previous.image?.previewData.count ?? 0) + (current.image?.previewData.count ?? 0) }
    public static func supports(_ path: String) -> Bool {
        ["png", "jpg", "jpeg", "webp"].contains(URL(fileURLWithPath: path).pathExtension.lowercased())
    }

    /// Read only regular files below the selected repository, without following
    /// descendant symlinks, including links swapped in while reading.
    static func working(_ project: URL, path: String) throws -> GitImageSide {
        try ProjectFiles.validateRelativePath(path)
        let parts = path.split(separator: "/").map(String.init)
        var directory = open(project.resolvingSymlinksInPath().path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW)
        guard directory >= 0 else { return .unavailable(.unreadable) }
        defer { close(directory) }
        for part in parts.dropLast() {
            let next = openat(directory, part, O_RDONLY | O_DIRECTORY | O_NOFOLLOW)
            guard next >= 0 else { return errno == ENOENT ? .missing : .unavailable(.symbolicLink) }
            close(directory); directory = next
        }
        guard let filename = parts.last else { return .unavailable(.unreadable) }
        let descriptor = openat(directory, filename, O_RDONLY | O_NOFOLLOW | O_NONBLOCK)
        guard descriptor >= 0 else { return errno == ENOENT ? .missing : .unavailable(errno == ELOOP ? .symbolicLink : .unreadable) }
        let handle = FileHandle(fileDescriptor: descriptor, closeOnDealloc: true)
        defer { try? handle.close() }
        var facts = stat()
        guard fstat(descriptor, &facts) == 0 else { return .unavailable(.unreadable) }
        guard facts.st_mode & S_IFMT == S_IFREG else { return .unavailable(.symbolicLink) }
        guard facts.st_size <= GitRasterImage.maximumBytes else { return .unavailable(.oversized) }
        var data = Data()
        while data.count <= GitRasterImage.maximumBytes {
            try Task.checkCancellation()
            let chunk = try handle.read(upToCount: min(64 * 1024, GitRasterImage.maximumBytes + 1 - data.count)) ?? Data()
            if chunk.isEmpty { break }
            data.append(chunk)
        }
        return GitRasterImage.read(data)
    }
}
