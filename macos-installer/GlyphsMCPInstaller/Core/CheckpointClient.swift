import Foundation

/// Authenticated app access to the same sidecar services used by the twelve tools.
public enum CheckpointClient {
    public static func call(_ body: [String: Any]) async throws -> Any {
        let installation = DesktopInstallation()
        let token = try String(contentsOf: installation.tokenURL, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines)
        var request = URLRequest(url: URL(string: "http://127.0.0.1:\(installation.port)/internal/checkpoints")!)
        request.httpMethod = "POST"; request.timeoutInterval = 60
        request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        request.cachePolicy = .reloadIgnoringLocalCacheData
        let (bytes, response) = try await URLSession.shared.bytes(for: request)
        var data = Data()
        for try await byte in bytes {
            guard data.count < 9 * 1024 * 1024 else { throw ProjectError("Checkpoint response exceeds the read limit.") }
            data.append(byte)
        }
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else { throw ProjectError("Invalid checkpoint response.") }
        guard (response as? HTTPURLResponse)?.statusCode == 200, object["ok"] as? Bool == true, let result = object["data"] else {
            let error = object["error"] as? [String: Any]
            throw ProjectError(error?["message"] as? String ?? "Update the MCP component to use font checkpoints.")
        }
        return result
    }
    public static func read(documentID: String, selector: [String: Any]) async throws -> [String: Any] {
        guard let rows = try await call(["action":"read", "document_id":documentID, "selector":selector]) as? [[String: Any]],
              let value = rows.first?["checkpoint"] as? [String: Any] else { throw ProjectError("Invalid checkpoint read response.") }
        return value
    }
}

public struct FontCheckpoint: Identifiable, Equatable {
    public let revision: String
    public let summary: String
    public let date: Date?
    public var id: String { revision }
    public init?(dictionary: [String: Any]) {
        guard let revision = dictionary["revision"] as? String, !revision.isEmpty else { return nil }
        self.revision = revision
        summary = dictionary["summary"] as? String ?? ""
        date = (dictionary["timestamp"] as? NSNumber).map { Date(timeIntervalSince1970: $0.doubleValue) }
    }
    public var title: String {
        let prefix = "Font checkpoint:"
        let text = summary.hasPrefix(prefix) ? String(summary.dropFirst(prefix.count)).trimmingCharacters(in: .whitespacesAndNewlines) : summary
        return text.isEmpty ? "Untitled checkpoint" : text
    }
    public var timeLabel: String { date?.formatted(date: .omitted, time: .shortened) ?? "Time unavailable" }
    public var dateLabel: String { date?.formatted(date: .abbreviated, time: .shortened) ?? "Date unavailable" }
    public var helpText: String {
        let formatter = DateFormatter()
        formatter.dateFormat = "EEEE, MMMM d, yyyy 'at' HH:mm:ss zzz"
        return "\(summary)\n\(date.map { formatter.string(from: $0) } ?? "Date unavailable")\n\(revision)"
    }
    public func dayLabel(now: Date = Date(), calendar: Calendar = .current) -> String {
        guard let date else { return "Date unavailable" }
        if calendar.isDate(date, inSameDayAs: now) { return "Today" }
        if let yesterday = calendar.date(byAdding: .day, value: -1, to: now), calendar.isDate(date, inSameDayAs: yesterday) { return "Yesterday" }
        let formatter = DateFormatter(); formatter.calendar = calendar; formatter.timeZone = calendar.timeZone
        formatter.dateStyle = .long
        return formatter.string(from: date)
    }
}

public struct CheckpointDocument: Identifiable, Equatable {
    public let id: String
    public let path: String
    public var filename: String { URL(fileURLWithPath: path).lastPathComponent }
    public static func eligible(_ rows: [[String: Any]], project: String) -> [Self] {
        let root = URL(fileURLWithPath: project).standardizedFileURL.path
        return rows.compactMap { row in
            guard let id = row["id"] as? String, let path = row["path"] as? String,
                  URL(fileURLWithPath: path).standardizedFileURL.path.hasPrefix(root + "/") else { return nil }
            return Self(id: id, path: path)
        }.sorted { $0.path.localizedStandardCompare($1.path) == .orderedAscending }
    }
}

public struct CheckpointFontSource: Identifiable, Equatable, Sendable {
    public let path: String
    public var id: String { path }
    public var filename: String { URL(fileURLWithPath: path).lastPathComponent }

    public static func discover(project: String, fileManager: FileManager = .default) -> [Self] {
        let root = URL(fileURLWithPath: project, isDirectory: true).standardizedFileURL
        guard let enumerator = fileManager.enumerator(
            at: root,
            includingPropertiesForKeys: [.isDirectoryKey, .isRegularFileKey, .isSymbolicLinkKey],
            options: [.skipsHiddenFiles],
            errorHandler: { _, _ in true }
        ) else { return [] }

        var fonts: [Self] = []
        while let url = enumerator.nextObject() as? URL {
            let values = try? url.resourceValues(forKeys: [.isDirectoryKey, .isRegularFileKey, .isSymbolicLinkKey])
            if values?.isSymbolicLink == true {
                if values?.isDirectory == true { enumerator.skipDescendants() }
                continue
            }
            let ext = url.pathExtension.lowercased()
            if ext == "glyphspackage", values?.isDirectory == true {
                fonts.append(.init(path: url.standardizedFileURL.path))
                enumerator.skipDescendants()
            } else if ext == "glyphs", values?.isRegularFile == true {
                fonts.append(.init(path: url.standardizedFileURL.path))
            }
        }
        return fonts.sorted { $0.path.localizedStandardCompare($1.path) == .orderedAscending }
    }
}

public struct CheckpointComparisonContext: Equatable {
    public let document: CheckpointDocument
    public let checkpoint: FontCheckpoint
    public let after: String
    public var projectRoot: String
    public var totalCount: Int = 0
    public var documentID: String { document.id }
    public var before: String { checkpoint.revision }
    public init(document: CheckpointDocument, checkpoint: FontCheckpoint, after: String, projectRoot: String) {
        self.document = document; self.checkpoint = checkpoint; self.after = after; self.projectRoot = projectRoot
    }
}

import Combine

/// Lives outside the popover so dismissing it cannot discard loading/error state.
@MainActor
public final class CheckpointHistoryStore: ObservableObject {
    public typealias Call = ([String: Any]) async throws -> Any
    @Published public private(set) var documents: [CheckpointDocument] = []
    @Published public private(set) var projectFonts: [CheckpointFontSource] = []
    @Published public private(set) var documentID = ""
    @Published public private(set) var rows: [FontCheckpoint] = []
    @Published public private(set) var cursor: String?
    @Published public private(set) var head = ""
    @Published public private(set) var busy = false
    @Published public private(set) var error = ""
    @Published public private(set) var documentsLoaded = false
    private let call: Call
    private var generation = UUID()
    private var task: Task<Void, Never>?
    public init(call: @escaping Call = { try await CheckpointClient.call($0) }) { self.call = call }
    public var document: CheckpointDocument? { documents.first { $0.id == documentID } }
    public var latestRevision: String? { rows.first?.revision }
    public var unopenedFonts: [CheckpointFontSource] {
        let openPaths = Set(documents.map { URL(fileURLWithPath: $0.path).standardizedFileURL.path })
        return projectFonts.filter { !openPaths.contains($0.path) }
    }
    public func cancel() { generation = UUID(); task?.cancel(); busy = false }
    public func open(project: String, preferredDocument: String?) {
        cancel(); let request = generation
        documents = []; projectFonts = []; documentsLoaded = false; rows = []; cursor = nil; head = ""; error = ""; busy = true
        task = Task {
            do {
                let fontTask = Task.detached(priority: .userInitiated) { CheckpointFontSource.discover(project: project) }
                let values = try await call(["action": "documents"]) as? [[String: Any]] ?? []
                let fonts = await fontTask.value
                guard generation == request, !Task.isCancelled else { return }
                documents = CheckpointDocument.eligible(values, project: project); projectFonts = fonts; documentsLoaded = true
                documentID = documents.first(where: { $0.id == preferredDocument })?.id ?? (documents.count == 1 ? documents[0].id : "")
                busy = false
                if !documentID.isEmpty { load(more: false) }
            } catch {
                guard generation == request, !Task.isCancelled else { return }
                self.error = error.localizedDescription; busy = false
            }
        }
    }
    public func choose(_ id: String) {
        cancel(); documentID = id; rows = []; cursor = nil; head = ""; error = ""
        if document != nil { load(more: false) }
    }
    public func load(more: Bool) {
        guard !busy, document != nil, !more || cursor != nil else { return }
        cancel(); let request = generation; let id = documentID
        busy = true; error = ""
        var selector: [String: Any] = ["kind": "checkpoint_history", "limit": 20]
        if more, let cursor { selector["cursor"] = cursor }
        task = Task {
            do {
                let response = try await call(["action": "read", "document_id": id, "selector": selector])
                guard generation == request, !Task.isCancelled else { return }
                guard let values = response as? [[String: Any]], let value = values.first?["checkpoint"] as? [String: Any] else { throw ProjectError("Invalid checkpoint history response.") }
                let page = (value["checkpoints"] as? [[String: Any]] ?? []).compactMap(FontCheckpoint.init(dictionary:))
                var seen = Set<String>()
                rows = ((more ? rows : []) + page).filter { seen.insert($0.id).inserted }
                cursor = value["nextCursor"] as? String; head = value["head"] as? String ?? ""
                busy = false
            } catch {
                guard generation == request, !Task.isCancelled else { return }
                self.error = error.localizedDescription; busy = false
            }
        }
    }
}
