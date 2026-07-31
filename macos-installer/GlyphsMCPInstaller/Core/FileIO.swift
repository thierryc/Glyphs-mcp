import Foundation

public enum InstallerError: LocalizedError {
	case userFacing(String)

	public var errorDescription: String? {
		switch self {
		case .userFacing(let s): return s
		}
	}
}

public enum FileIO {
	static func timestampString(now: Date = Date()) -> String {
		let f = DateFormatter()
		f.locale = Locale(identifier: "en_US_POSIX")
		f.timeZone = TimeZone.current
		f.dateFormat = "yyyyMMdd-HHmmss"
		return f.string(from: now)
	}

	static func ensureParentDir(_ url: URL) throws {
		let dir = url.deletingLastPathComponent()
		try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true, attributes: nil)
	}

	static func backupIfExists(_ url: URL) throws -> URL? {
		guard FileManager.default.fileExists(atPath: url.path) else { return nil }
		let backup = url.appendingPathExtension("bak-\(timestampString())")
		try FileManager.default.copyItem(at: url, to: backup)
		return backup
	}

	static func writeAtomically(_ data: Data, to url: URL) throws {
		try ensureParentDir(url)
		let tmp = url.deletingLastPathComponent().appendingPathComponent(".tmp-\(UUID().uuidString)")
		try data.write(to: tmp, options: .atomic)
		if FileManager.default.fileExists(atPath: url.path) {
			_ = try FileManager.default.replaceItemAt(url, withItemAt: tmp)
		} else {
			try FileManager.default.moveItem(at: tmp, to: url)
		}
	}

	static func writeUTF8Atomically(_ text: String, to url: URL) throws {
		var s = text
		if !s.hasSuffix("\n") { s += "\n" }
		guard let data = s.data(using: .utf8) else {
			throw InstallerError.userFacing("Failed to encode UTF-8 for \(url.path)")
		}
		try writeAtomically(data, to: url)
	}
}

public enum InstallerConstants {
	public static let endpointURL = URL(string: "http://127.0.0.1:9680/mcp/")!
	public static let codexServerName = "glyphs-mcp-server"
	public static let claudeDesktopServerName = "glyphs-mcp-server"
	public static let claudeCodeServerName = "glyphs-mcp"
}

public enum InstallerPaths {
	public static var home: URL { FileManager.default.homeDirectoryForCurrentUser }
	public static var glyphsBaseDir: URL {
		glyphsBaseDir(glyphsVersion: .installerDefault)
	}
	public static func glyphsBaseDir(glyphsVersion: GlyphsMajorVersion = .installerDefault) -> URL {
		home.appendingPathComponent("Library/Application Support/\(glyphsVersion.applicationSupportName)", isDirectory: true)
	}
	public static var glyphsPluginsDir: URL {
		glyphsPluginsDir(glyphsVersion: .installerDefault)
	}
	public static func glyphsPluginsDir(glyphsVersion: GlyphsMajorVersion = .installerDefault) -> URL {
		glyphsBaseDir(glyphsVersion: glyphsVersion).appendingPathComponent("Plugins", isDirectory: true)
	}
	public static func glyphsScriptsSitePackages(glyphsVersion: GlyphsMajorVersion = .installerDefault) -> URL {
		glyphsBaseDir(glyphsVersion: glyphsVersion).appendingPathComponent("Scripts/site-packages", isDirectory: true)
	}
	public static func glyphsPythonPip3() -> URL? {
		glyphsPythonPip3(glyphsVersion: .installerDefault)
	}
	public static func glyphsPythonPip3(glyphsVersion: GlyphsMajorVersion = .installerDefault) -> URL? {
		let base = glyphsBaseDir(glyphsVersion: glyphsVersion).appendingPathComponent("Repositories/GlyphsPythonPlugin/Python.framework/Versions/Current/bin/pip3")
		return FileManager.default.isExecutableFile(atPath: base.path) ? base : nil
	}
	public static var codexConfig: URL {
		home.appendingPathComponent(".codex/config.toml")
	}
	public static var codexSkillsDir: URL {
		home.appendingPathComponent(".codex/skills", isDirectory: true)
	}
	public static var claudeDesktopConfig: URL {
		home.appendingPathComponent("Library/Application Support/Claude/claude_desktop_config.json")
	}
	public static var claudeCodeConfig: URL {
		home.appendingPathComponent(".claude.json")
	}
	public static var claudeCodeSkillsDir: URL {
		home.appendingPathComponent(".claude/skills", isDirectory: true)
	}
}

public struct InstallerPayload {
	public static let legacyManagedSkillNames = ["glyphs-mcp-connect"]
	private static let extractionLock = NSLock()
	private static var extractedPayloads: [String: URL] = [:]

	public let payloadDir: URL
	public let pluginBundle: URL
	public let requirementsTxt: URL
	public let runtimeProbe: URL
	public let skillsDir: URL?

	public init(
		payloadDir: URL,
		pluginBundle: URL,
		requirementsTxt: URL,
		runtimeProbe: URL? = nil,
		skillsDir: URL?
	) {
		self.payloadDir = payloadDir
		self.pluginBundle = pluginBundle
		self.requirementsTxt = requirementsTxt
		self.runtimeProbe = runtimeProbe
			?? pluginBundle.appendingPathComponent("Contents/Resources/runtime_probe.py")
		self.skillsDir = skillsDir
	}

	public func managedSkillDirectories() -> [URL] {
		guard let skillsDir else { return [] }
		let prefix = "glyphs-mcp-"
		guard let entries = try? FileManager.default.contentsOfDirectory(at: skillsDir, includingPropertiesForKeys: [.isDirectoryKey], options: [.skipsHiddenFiles]) else {
			return []
		}
		return entries
			.filter { $0.lastPathComponent == "glyphs" || $0.lastPathComponent.hasPrefix(prefix) }
			.filter { (try? $0.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) ?? false }
			.sorted { $0.lastPathComponent < $1.lastPathComponent }
	}

	public static func resolve(bundle: Bundle = .main) throws -> InstallerPayload {
		let fm = FileManager.default
		let directPayloadDir: URL? = {
			// Prefer a direct path lookup to avoid any resource indexing weirdness for folder-based payloads.
			if let root = bundle.resourceURL {
				let direct = root.appendingPathComponent("Payload", isDirectory: true)
				if fm.fileExists(atPath: direct.path) { return direct }
			}
			return bundle.url(forResource: "Payload", withExtension: nil)
		}()
		let payloadDir: URL?
		if let directPayloadDir {
			payloadDir = directPayloadDir
		} else if let resourceRoot = bundle.resourceURL {
			let archive = resourceRoot.appendingPathComponent("Payload.gmcparchive")
			payloadDir = fm.fileExists(atPath: archive.path)
				? try extractPayloadArchive(archive)
				: nil
		} else {
			payloadDir = nil
		}
		guard let payloadDir else {
			throw InstallerError.userFacing("Installer payload is missing. Rebuild the signed installer app.")
		}
		let plugin = payloadDir.appendingPathComponent("Glyphs MCP.glyphsPlugin", isDirectory: true)
		let req = payloadDir.appendingPathComponent("requirements.txt")
		let runtimeProbe = plugin.appendingPathComponent("Contents/Resources/runtime_probe.py")
		let skillsDir = payloadDir.appendingPathComponent("skills", isDirectory: true)
		guard FileManager.default.fileExists(atPath: plugin.path) else {
			throw InstallerError.userFacing("Missing payload plugin bundle: \(plugin.path)")
		}
		guard FileManager.default.fileExists(atPath: req.path) else {
			throw InstallerError.userFacing("Missing payload requirements.txt: \(req.path)")
		}
		guard FileManager.default.fileExists(atPath: runtimeProbe.path) else {
			throw InstallerError.userFacing("Missing payload Python runtime probe: \(runtimeProbe.path)")
		}
		let resolvedSkillsDir = FileManager.default.fileExists(atPath: skillsDir.path) ? skillsDir : nil
		return InstallerPayload(
			payloadDir: payloadDir,
			pluginBundle: plugin,
			requirementsTxt: req,
			runtimeProbe: runtimeProbe,
			skillsDir: resolvedSkillsDir
		)
	}

	private static func extractPayloadArchive(_ archive: URL) throws -> URL {
		extractionLock.lock()
		defer { extractionLock.unlock() }

		if let cached = extractedPayloads[archive.path],
		   FileManager.default.fileExists(atPath: cached.path) {
			return cached
		}

		let root = FileManager.default.temporaryDirectory
			.appendingPathComponent("glyphs-mcp-installer-payload-\(UUID().uuidString)", isDirectory: true)
		try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true, attributes: nil)
		let process = Process()
		process.executableURL = URL(fileURLWithPath: "/usr/bin/tar")
		process.arguments = ["-xzf", archive.path, "-C", root.path]
		let pipe = Pipe()
		process.standardOutput = pipe
		process.standardError = pipe
		do {
			try process.run()
			let data = pipe.fileHandleForReading.readDataToEndOfFile()
			process.waitUntilExit()
			guard process.terminationStatus == 0 else {
				let details = String(data: data, encoding: .utf8)?
					.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
				throw InstallerError.userFacing("Could not extract the signed installer payload: \(details)")
			}
		} catch {
			try? FileManager.default.removeItem(at: root)
			if let installerError = error as? InstallerError {
				throw installerError
			}
			throw InstallerError.userFacing("Could not extract the signed installer payload: \(error.localizedDescription)")
		}

		let payload = root.appendingPathComponent("Payload", isDirectory: true)
		guard FileManager.default.fileExists(atPath: payload.path) else {
			try? FileManager.default.removeItem(at: root)
			throw InstallerError.userFacing("Signed installer payload archive does not contain Payload.")
		}
		extractedPayloads[archive.path] = payload
		return payload
	}
}
