import Foundation

public struct GitObservation: Equatable {
    public let branch: String
    public let changes: [Change]
    public struct Change: Equatable, Identifiable {
        public let status: String
        public let path: String
        public let originalPath: String?
        public var id: String { path }
    }
}

public struct ReadOnlyGit {
    public let executable: URL?
    private let runner = ProcessRunner()
    public init(executable: URL? = nil) {
        self.executable = executable ?? ["/Applications/Xcode.app/Contents/Developer/usr/bin/git", "/Library/Developer/CommandLineTools/usr/bin/git", "/opt/homebrew/bin/git", "/usr/local/bin/git"]
            .first(where: { FileManager.default.isExecutableFile(atPath: $0) }).map { URL(fileURLWithPath: $0) }
    }
    public func inspect(_ project: URL) async throws -> GitObservation {
        let branch = try await run(project, ["symbolic-ref", "--quiet", "--short", "HEAD"], allowFailure: true)
        let status = try await run(project, ["status", "--porcelain=v1", "-z", "--untracked-files=normal"])
        let fields = status.split(separator: "\0", omittingEmptySubsequences: true).map(String.init)
        var changes: [GitObservation.Change] = []; var i = 0
        while i < fields.count {
            let field = fields[i]; i += 1
            guard field.count >= 4 else { throw ProjectError("Git returned an invalid status record.") }
            let state = String(field.prefix(2)), path = String(field.dropFirst(3))
            var original: String?
            if state.contains("R") || state.contains("C") {
                guard i < fields.count else { throw ProjectError("Git returned an incomplete renamed-file record.") }
                original = fields[i]; i += 1
            }
            changes.append(.init(status: state, path: path, originalPath: original))
        }
        let name = branch.trimmingCharacters(in: .whitespacesAndNewlines)
        let revision = try await run(project, ["rev-parse", "--verify", "--short", "HEAD"], allowFailure: true)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let label = revision.isEmpty ? (name.isEmpty ? "No commits yet" : name + " · No commits yet")
            : (name.isEmpty ? "Detached at " + revision : name)
        return GitObservation(branch: label, changes: changes)
    }
    public func diff(_ project: URL, path: String) async throws -> String {
        try ProjectFiles.validateRelativePath(path)
        let arguments = ["diff", "--no-ext-diff", "--no-textconv", "--no-color", "--submodule=short"]
        let unstaged = try await run(project, arguments + ["--", path])
        let staged = try await run(project, arguments + ["--cached", "--", path])
        let text = (staged.isEmpty ? "" : "Staged changes\n" + staged + "\n") + (unstaged.isEmpty ? "" : "Working-tree changes\n" + unstaged)
        return text.isEmpty ? "No tracked text diff. New, binary or untracked files can be opened in your editor." : String(text.prefix(100_000)) + (text.count > 100_000 ? "\n… Diff truncated for display." : "")
    }
    private func run(_ project: URL, _ arguments: [String], allowFailure: Bool = false) async throws -> String {
        guard let executable else { throw ProjectError("Git is unavailable. Project creation and templates remain available.") }
        let args = ["--no-optional-locks", "--no-pager", "--literal-pathspecs", "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false", "-c", "core.hooksPath=/dev/null", "-c", "credential.helper=", "-c", "diff.external=", "-C", project.path] + arguments
        let result = try await runner.runCapturing(executable: executable, args: args,
            environment: ["PATH": "/usr/bin:/bin", "HOME": FileManager.default.homeDirectoryForCurrentUser.path,
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"], timeout: 10)
        guard result.exitCode == 0 || allowFailure else {
            if result.stderr.contains("not a git repository") { throw ProjectError("This folder isn’t a Git repository.") }
            throw ProjectError(String(result.stderr.prefix(1000)).trimmingCharacters(in: .whitespacesAndNewlines))
        }
        return result.stdout
    }
}
