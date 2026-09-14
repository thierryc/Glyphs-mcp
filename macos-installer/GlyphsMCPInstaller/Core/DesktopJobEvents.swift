import CoreServices
import Foundation

/// File notifications only wake the authenticated status reader. Job contents
/// never become UI state directly. The service remains the source of truth.
public final class DesktopJobEvents {
    private final class Context {
        let root: URL
        var changed: (() -> Void)?
        init(root: URL, changed: @escaping () -> Void) { self.root = root; self.changed = changed }
    }
    private var stream: FSEventStreamRef?
    private let context: Context

    public init?(root: URL, changed: @escaping () -> Void) {
        precondition(Thread.isMainThread)
        let root = Self.canonicalURL(root)
        context = Context(root: root, changed: changed)
        // The managed root may not exist on a fresh installation yet.
        var watch = root.deletingLastPathComponent()
        while !FileManager.default.fileExists(atPath: watch.path), watch.path != "/" {
            watch.deleteLastPathComponent()
        }
        var info = FSEventStreamContext(version: 0, info: Unmanaged.passUnretained(context).toOpaque(),
            retain: { pointer in
                guard let pointer else { return nil }
                _ = Unmanaged<Context>.fromOpaque(pointer).retain()
                return pointer
            }, release: { pointer in
                if let pointer { Unmanaged<Context>.fromOpaque(pointer).release() }
            }, copyDescription: nil)
        let flags = kFSEventStreamCreateFlagUseCFTypes | kFSEventStreamCreateFlagFileEvents | kFSEventStreamCreateFlagWatchRoot
        stream = FSEventStreamCreate(nil, { _, info, count, paths, flags, _ in
            guard let info else { return }
            let context = Unmanaged<Context>.fromOpaque(info).takeUnretainedValue()
            let paths = unsafeBitCast(paths, to: NSArray.self) as! [String]
            let rescan = UInt32(kFSEventStreamEventFlagMustScanSubDirs | kFSEventStreamEventFlagRootChanged)
            if (0..<count).contains(where: { flags[$0] & rescan != 0 ||
                DesktopJobEvents.isRelevant(path: paths[$0], root: context.root) }) {
                context.changed?()
            }
        }, &info, [watch.path] as CFArray, FSEventStreamEventId(kFSEventStreamEventIdSinceNow),
            0.2, FSEventStreamCreateFlags(flags))
        guard let stream else { return nil }
        FSEventStreamSetDispatchQueue(stream, .main)
        guard FSEventStreamStart(stream) else { stop(); return nil }
    }

    public static func isRelevant(path: String, root: URL) -> Bool {
        // FSEvents uses /private/var while Foundation may use /var for the
        // same location (including home directories reached through aliases).
        let path = canonicalURL(URL(fileURLWithPath: path)).path
        let root = canonicalURL(root)
        if path == root.path || path == root.appendingPathComponent("installation.json").path { return true }
        let prefix = root.appendingPathComponent("jobs").path + "/"
        guard path.hasPrefix(prefix) else { return false }
        let parts = path.dropFirst(prefix.count).split(separator: "/")
        return parts.count == 2 && parts[1] == "state.json"
    }

    private static func canonicalURL(_ url: URL) -> URL {
        // An atomic rename can remove the reported path before delivery.
        // Resolve the existing ancestor, then append any missing components.
        var ancestor = url
        var suffix: [String] = []
        while !FileManager.default.fileExists(atPath: ancestor.path), ancestor.path != "/" {
            suffix.append(ancestor.lastPathComponent)
            ancestor.deleteLastPathComponent()
        }
        return suffix.reversed().reduce(ancestor.resolvingSymlinksInPath().standardizedFileURL) {
            $0.appendingPathComponent($1)
        }
    }

    public func stop() {
        precondition(Thread.isMainThread)
        context.changed = nil
        guard let stream else { return }
        FSEventStreamStop(stream)
        FSEventStreamInvalidate(stream)
        FSEventStreamRelease(stream)
        self.stream = nil
    }
    deinit { stop() }
}
