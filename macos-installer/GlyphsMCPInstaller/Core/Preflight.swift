import AppKit
import Foundation
import SwiftUI

public struct PreflightItem: Identifiable {
	public enum Level {
		case ok
		case warn
		case bad

		public var symbolName: String {
			switch self {
			case .ok: return "checkmark.circle.fill"
			case .warn: return "exclamationmark.triangle.fill"
			case .bad: return "xmark.octagon.fill"
			}
		}

		public var color: Color {
			switch self {
			case .ok: return .green
			case .warn: return .orange
			case .bad: return .red
			}
		}
	}

	public let id = UUID()
	public let level: Level
	public let title: String
	public let details: String
}

public struct PythonCandidate: Hashable {
	public let path: String
	public let version: String
	public let source: String
}

public struct PreflightResult {
	public var items: [PreflightItem]
	public var glyphsPipPath: String?
	public var glyphsSelectedPythonFrameworkPath: String?
	public var glyphsSelectedPythonVersion: String?
	public var customPythons: [PythonCandidate]
	public var customPythonTooOldCount: Int
	public var customPythonTooNewCount: Int
	public var customPythonUnknownCount: Int
	public var codexPath: String?
	public var claudePath: String?
	public var nodePath: String?

	public init(items: [PreflightItem], glyphsPipPath: String?, glyphsSelectedPythonFrameworkPath: String?, glyphsSelectedPythonVersion: String?, customPythons: [PythonCandidate], customPythonTooOldCount: Int, customPythonTooNewCount: Int, customPythonUnknownCount: Int, codexPath: String?, claudePath: String?, nodePath: String?) {
		self.items = items
		self.glyphsPipPath = glyphsPipPath
		self.glyphsSelectedPythonFrameworkPath = glyphsSelectedPythonFrameworkPath
		self.glyphsSelectedPythonVersion = glyphsSelectedPythonVersion
		self.customPythons = customPythons
		self.customPythonTooOldCount = customPythonTooOldCount
		self.customPythonTooNewCount = customPythonTooNewCount
		self.customPythonUnknownCount = customPythonUnknownCount
		self.codexPath = codexPath
		self.claudePath = claudePath
		self.nodePath = nodePath
	}

	public static let empty = PreflightResult(items: [], glyphsPipPath: nil, glyphsSelectedPythonFrameworkPath: nil, glyphsSelectedPythonVersion: nil, customPythons: [], customPythonTooOldCount: 0, customPythonTooNewCount: 0, customPythonUnknownCount: 0, codexPath: nil, claudePath: nil, nodePath: nil)
}

public enum Preflight {
	public static func scan() -> PreflightResult {
		var items: [PreflightItem] = []
		let runner = ProcessRunner()

		let glyphsBase = InstallerPaths.glyphsBaseDir
		let pluginsDir = InstallerPaths.glyphsPluginsDir
		items.append(.init(level: .ok, title: "Glyphs base folder", details: glyphsBase.path))
		items.append(.init(level: .ok, title: "Glyphs plugins folder", details: pluginsDir.path))

		// Payload + installed plugin versions (best-effort; payload exists only in the built app).
		let payloadInfo = Preflight.readPluginVersion(bundle: .main, pluginBundleURL: nil)
		switch payloadInfo {
		case .some(let v):
			items.append(.init(level: .ok, title: "Payload plugin version", details: v))
		case .none:
			items.append(.init(level: .warn, title: "Payload plugin version", details: "Unavailable (payload not found yet)."))
		}

		let installedPlugin = pluginsDir.appendingPathComponent("Glyphs MCP.glyphsPlugin", isDirectory: true)
		if let installedVer = Preflight.readPluginVersionFromBundle(pluginBundle: installedPlugin) {
			items.append(.init(level: .ok, title: "Installed plugin version", details: installedVer))
		} else {
			items.append(.init(level: .warn, title: "Installed plugin version", details: "Not installed (yet)."))
		}

		let glyphsPip = InstallerPaths.glyphsPythonPip3()
		if let pip = glyphsPip {
			items.append(.init(level: .ok, title: "Glyphs Python pip3", details: pip.path))
		} else {
			items.append(.init(level: .warn, title: "Glyphs Python pip3", details: "Not found (install GlyphsPythonPlugin in Glyphs → Settings → Addons)"))
		}

		let glyphsSelectedFramework = GlyphsPreferences.pythonFrameworkPath()
		let glyphsSelectedVersion: String? = {
			guard let glyphsSelectedFramework else { return nil }
			let python3 = URL(fileURLWithPath: glyphsSelectedFramework, isDirectory: true).appendingPathComponent("bin/python3")
			let res = runner.runSyncWithStderr(executable: python3, args: ["-c", "import sys; print(sys.version.split()[0])"])
			guard res.exitCode == 0 else { return GlyphsPreferences.pythonFrameworkMajorMinor(from: glyphsSelectedFramework) }
			let v = res.stdout.trimmingCharacters(in: .whitespacesAndNewlines)
			return v.isEmpty ? GlyphsPreferences.pythonFrameworkMajorMinor(from: glyphsSelectedFramework) : v
		}()

		if let glyphsSelectedFramework {
			let detail = glyphsSelectedVersion != nil
				? "Selected: \(glyphsSelectedVersion!) (\(glyphsSelectedFramework))"
				: "Selected framework: \(glyphsSelectedFramework)"
			items.append(.init(level: .ok, title: "Glyphs Python setting", details: detail))
		} else {
			items.append(.init(level: .warn, title: "Glyphs Python setting", details: "Unknown (could not read Glyphs preferences)."))
		}

		let scan = PythonDetector.scanCustomPythons()
		let customPythons = scan.good
		let summary = PythonDetector.formatSummary(scan: scan)
		items.append(.init(level: customPythons.isEmpty ? .warn : .ok, title: "Custom Python", details: summary))

		let codex = ToolLocator.findTool(named: "codex", extraCandidates: ["/opt/homebrew/bin/codex", "/usr/local/bin/codex"])
		items.append(.init(level: codex == nil ? .warn : .ok, title: "Codex CLI", details: codex ?? "Not found (will patch ~/.codex/config.toml instead)."))

		let claude = ToolLocator.findTool(named: "claude", extraCandidates: ["/opt/homebrew/bin/claude", "/usr/local/bin/claude"])
		items.append(.init(level: claude == nil ? .warn : .ok, title: "Claude CLI", details: claude ?? "Not found (Claude Code will not be auto-configured)."))

		let node = ToolLocator.findTool(named: "node", extraCandidates: ["/opt/homebrew/bin/node", "/usr/local/bin/node"])
		items.append(.init(level: node == nil ? .warn : .ok, title: "Node", details: node ?? "Not found (Claude Desktop proxy via npx may fail)."))

		return PreflightResult(
			items: items,
			glyphsPipPath: glyphsPip?.path,
			glyphsSelectedPythonFrameworkPath: glyphsSelectedFramework,
			glyphsSelectedPythonVersion: glyphsSelectedVersion,
			customPythons: customPythons,
			customPythonTooOldCount: scan.tooOldCount,
			customPythonTooNewCount: scan.tooNewCount,
			customPythonUnknownCount: scan.unknownCount,
			codexPath: codex,
			claudePath: claude,
			nodePath: node
		)
	}

	static func readPluginVersion(bundle: Bundle, pluginBundleURL: URL?) -> String? {
		if let pluginBundleURL {
			return readPluginVersionFromBundle(pluginBundle: pluginBundleURL)
		}
		// In the built app, the plugin is placed under Resources/Payload/Glyphs MCP.glyphsPlugin.
		if let payload = try? InstallerPayload.resolve(bundle: bundle) {
			return readPluginVersionFromBundle(pluginBundle: payload.pluginBundle)
		}
		return nil
	}

	public static func readPluginVersionFromBundle(pluginBundle: URL) -> String? {
		let info = pluginBundle.appendingPathComponent("Contents/Info.plist")
		guard let data = try? Data(contentsOf: info) else { return nil }
		guard let obj = try? PropertyListSerialization.propertyList(from: data, format: nil) as? [String: Any] else { return nil }
		let short = obj["CFBundleShortVersionString"] as? String
		let build = obj["CFBundleVersion"] as? String
		if let short, let build, short != build {
			return "\(short) (\(build))"
		}
		return short ?? build
	}
}

enum PythonDetector {
	struct PythonScanResult {
		var good: [PythonCandidate]
		var tooOldCount: Int
		var tooNewCount: Int
		var unknownCount: Int
	}

	static func formatSummary(scan: PythonScanResult) -> String {
		let good = scan.good.count
		let ignored = scan.tooOldCount + scan.tooNewCount + scan.unknownCount

		var parts: [String] = []
		if good == 0 {
			parts.append("No supported interpreters (3.11–3.13).")
		} else if good == 1 {
			parts.append("Good candidates: 1 (3.11–3.13).")
		} else {
			parts.append("Good candidates: \(good) (3.11–3.13).")
		}

		if ignored > 0 {
			var ignoredParts: [String] = []
			if scan.tooOldCount > 0 { ignoredParts.append("\(scan.tooOldCount) too old") }
			if scan.tooNewCount > 0 { ignoredParts.append("\(scan.tooNewCount) too new") }
			if scan.unknownCount > 0 { ignoredParts.append("\(scan.unknownCount) unknown") }
			parts.append("Ignored: " + ignoredParts.joined(separator: ", ") + ".")
		}

		if let top = scan.good.first {
			parts.append("Top: \(top.version) (\(top.source)).")
		}

		if scan.good.count > 1 {
			let shown = scan.good.prefix(3).map { "\($0.version) (\($0.source))" }.joined(separator: ", ")
			parts.append("Candidates: \(shown)\(scan.good.count > 3 ? ", …" : "").")
		}

		return parts.joined(separator: " ")
	}

	static func scanCustomPythons() -> PythonScanResult {
		let fm = FileManager.default
		let runner = ProcessRunner()
		let regex = try? NSRegularExpression(pattern: "^python3(\\.\\d+)?$", options: [])

		func iterPythonBins(in binDir: URL) -> [URL] {
			guard let regex else { return [] }
			var isDir: ObjCBool = false
			guard fm.fileExists(atPath: binDir.path, isDirectory: &isDir), isDir.boolValue else { return [] }

			let entries: [URL]
			do {
				entries = try fm.contentsOfDirectory(at: binDir, includingPropertiesForKeys: nil, options: [.skipsHiddenFiles])
			} catch {
				return []
			}

			var out: [URL] = []
			for url in entries.sorted(by: { $0.lastPathComponent < $1.lastPathComponent }) {
				let name = url.lastPathComponent
				let range = NSRange(location: 0, length: (name as NSString).length)
				guard regex.firstMatch(in: name, options: [], range: range) != nil else { continue }

				var isCandidateDir: ObjCBool = false
				guard fm.fileExists(atPath: url.path, isDirectory: &isCandidateDir), !isCandidateDir.boolValue else { continue }
				guard fm.isExecutableFile(atPath: url.path) else { continue }

				out.append(url)
			}

			return out
		}

		func pythonVersion(_ python: URL) -> String? {
			let res = runner.runSyncWithStderr(executable: python, args: ["-c", "import sys; print(sys.version.split()[0])"])
			guard res.exitCode == 0 else { return nil }
			let v = res.stdout.trimmingCharacters(in: .whitespacesAndNewlines)
			return v.isEmpty ? nil : v
		}

		var candidates: [(url: URL, source: String)] = []

		func addPythonOrgFramework(_ base: URL) {
			let versions = base.appendingPathComponent("Versions", isDirectory: true)
			let currentBin = versions.appendingPathComponent("Current/bin", isDirectory: true)
			for py in iterPythonBins(in: currentBin) { candidates.append((py, "python.org")) }

			var isDir: ObjCBool = false
			guard fm.fileExists(atPath: versions.path, isDirectory: &isDir), isDir.boolValue else { return }
			guard let versionDirs = try? fm.contentsOfDirectory(at: versions, includingPropertiesForKeys: nil, options: [.skipsHiddenFiles]) else { return }
			for vdir in versionDirs.sorted(by: { $0.lastPathComponent < $1.lastPathComponent }) {
				if vdir.lastPathComponent == "Current" { continue }
				var isVersionDir: ObjCBool = false
				guard fm.fileExists(atPath: vdir.path, isDirectory: &isVersionDir), isVersionDir.boolValue else { continue }
				for py in iterPythonBins(in: vdir.appendingPathComponent("bin", isDirectory: true)) {
					candidates.append((py, "python.org"))
				}
			}
		}

		addPythonOrgFramework(URL(fileURLWithPath: "/Library/Frameworks/Python.framework", isDirectory: true))
		addPythonOrgFramework(InstallerPaths.home.appendingPathComponent("Library/Frameworks/Python.framework", isDirectory: true))

		for brewBin in ["/opt/homebrew/bin", "/usr/local/bin"] {
			let dir = URL(fileURLWithPath: brewBin, isDirectory: true)
			for py in iterPythonBins(in: dir) { candidates.append((py, "homebrew")) }
		}

		for sysBin in ["/usr/bin", "/bin"] {
			let dir = URL(fileURLWithPath: sysBin, isDirectory: true)
			for py in iterPythonBins(in: dir) { candidates.append((py, "system")) }
		}

		if let pathEnv = ProcessInfo.processInfo.environment["PATH"] {
			for p in pathEnv.split(separator: ":").map(String.init) where !p.isEmpty {
				let dir = URL(fileURLWithPath: p, isDirectory: true)
				let source: String = {
					if p.contains("homebrew") || p.hasPrefix("/opt/homebrew") || p.hasPrefix("/usr/local") { return "homebrew" }
					if p.hasPrefix("/usr") || p.hasPrefix("/bin") { return "system" }
					return "path"
				}()
				for py in iterPythonBins(in: dir) { candidates.append((py, source)) }
			}
		}

		candidates.append((URL(fileURLWithPath: "/usr/bin/python3"), "system"))

		// Version managers (best-effort).
		let pyenv = InstallerPaths.home.appendingPathComponent(".pyenv/versions", isDirectory: true)
		if let versionDirs = try? fm.contentsOfDirectory(at: pyenv, includingPropertiesForKeys: nil, options: [.skipsHiddenFiles]) {
			for vdir in versionDirs {
				for py in iterPythonBins(in: vdir.appendingPathComponent("bin", isDirectory: true)) {
					candidates.append((py, "path"))
				}
			}
		}
		let asdf = InstallerPaths.home.appendingPathComponent(".asdf/installs/python", isDirectory: true)
		if let versionDirs = try? fm.contentsOfDirectory(at: asdf, includingPropertiesForKeys: nil, options: [.skipsHiddenFiles]) {
			for vdir in versionDirs {
				for py in iterPythonBins(in: vdir.appendingPathComponent("bin", isDirectory: true)) {
					candidates.append((py, "path"))
				}
			}
		}

		var seen = Set<String>()
		var good: [PythonCandidate] = []
		var tooOldCount = 0
		var tooNewCount = 0
		var unknownCount = 0

		for (url, source) in candidates {
			guard fm.isExecutableFile(atPath: url.path) else { continue }
			let resolved = url.resolvingSymlinksInPath()
			if seen.contains(resolved.path) { continue }
			seen.insert(resolved.path)

			guard let ver = pythonVersion(resolved) else {
				unknownCount += 1
				continue
			}
			let t = VersionGate.tuple(ver)
			if t < (3, 11, 0) {
				tooOldCount += 1
				continue
			}
			if t >= (3, 14, 0) {
				tooNewCount += 1
				continue
			}
			good.append(.init(path: resolved.path, version: ver, source: source))
		}

		good.sort {
			let c = VersionGate.compare($0.version, $1.version)
			if c != 0 { return c > 0 }
			return ($0.source == "python.org") && ($1.source != "python.org")
		}

		return PythonScanResult(good: good, tooOldCount: tooOldCount, tooNewCount: tooNewCount, unknownCount: unknownCount)
	}

	static func detectCustomPythons() -> [PythonCandidate] {
		scanCustomPythons().good
	}
}

enum VersionGate {
	static func isSupported(version: String) -> Bool {
		let t = tuple(version)
		return t >= (3, 11, 0) && t < (3, 14, 0)
	}

	static func compare(_ a: String, _ b: String) -> Int {
		let ta = tuple(a)
		let tb = tuple(b)
		if ta == tb { return 0 }
		return ta < tb ? -1 : 1
	}

	static func tuple(_ v: String) -> (Int, Int, Int) {
		let parts = v.split(separator: ".").prefix(3).map { Int($0) ?? 0 }
		let major = parts.count > 0 ? parts[0] : 0
		let minor = parts.count > 1 ? parts[1] : 0
		let patch = parts.count > 2 ? parts[2] : 0
		return (major, minor, patch)
	}
}

enum ToolLocator {
	static func findTool(named: String, extraCandidates: [String] = []) -> String? {
		let fm = FileManager.default
		let home = InstallerPaths.home

		var candidates: [String] = []

		// Explicit candidates first.
		candidates.append(contentsOf: extraCandidates)

		// Common user-level install locations (Finder-launched apps often have a minimal PATH).
		candidates.append(home.appendingPathComponent(".local/bin/\(named)").path)
		candidates.append(home.appendingPathComponent("bin/\(named)").path)
		candidates.append(home.appendingPathComponent(".npm/bin/\(named)").path)
		candidates.append(home.appendingPathComponent(".npm-global/bin/\(named)").path)
		candidates.append(home.appendingPathComponent(".yarn/bin/\(named)").path)
		candidates.append(home.appendingPathComponent(".config/yarn/global/node_modules/.bin/\(named)").path)
		candidates.append(home.appendingPathComponent("Library/pnpm/\(named)").path)
		candidates.append(home.appendingPathComponent(".volta/bin/\(named)").path)
		candidates.append(home.appendingPathComponent(".asdf/shims/\(named)").path)
		candidates.append(home.appendingPathComponent(".bun/bin/\(named)").path)
		candidates.append(home.appendingPathComponent(".cargo/bin/\(named)").path)
		candidates.append(home.appendingPathComponent(".claude/local/bin/\(named)").path)

		// Common system locations.
		let systemDirs = [
			"/opt/homebrew/bin",
			"/usr/local/bin",
			"/usr/bin",
			"/bin",
			"/usr/sbin",
			"/sbin",
		]
		candidates.append(contentsOf: systemDirs.map { "\($0)/\(named)" })

		// Current process PATH (may include nvm/asdf, etc when launched from a shell).
		if let pathEnv = ProcessInfo.processInfo.environment["PATH"] {
			let envDirs = pathEnv.split(separator: ":").map(String.init)
			candidates.append(contentsOf: envDirs.map { "\($0)/\(named)" })
		}

		// nvm installs (best-effort).
		let nvm = home.appendingPathComponent(".nvm/versions/node", isDirectory: true)
		if let nodeVers = try? fm.contentsOfDirectory(at: nvm, includingPropertiesForKeys: nil, options: [.skipsHiddenFiles]) {
			for v in nodeVers {
				candidates.append(v.appendingPathComponent("bin/\(named)").path)
			}
		}

		// De-dup while preserving order.
		var seen = Set<String>()
		for p in candidates {
			guard !seen.contains(p) else { continue }
			seen.insert(p)
			if fm.isExecutableFile(atPath: p) {
				return p
			}
		}

		return nil
	}
}
