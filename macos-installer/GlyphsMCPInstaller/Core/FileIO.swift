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
	public static let claudeCodeServerName = "glyphs-mcp"
}

public enum InstallerPaths {
	public static var home: URL { FileManager.default.homeDirectoryForCurrentUser }
	public static var glyphsBaseDir: URL {
		home.appendingPathComponent("Library/Application Support/Glyphs 3", isDirectory: true)
	}
	public static var glyphsPluginsDir: URL {
		glyphsBaseDir.appendingPathComponent("Plugins", isDirectory: true)
	}
	public static func glyphsPythonPip3() -> URL? {
		let base = glyphsBaseDir.appendingPathComponent("Repositories/GlyphsPythonPlugin/Python.framework/Versions/Current/bin/pip3")
		return FileManager.default.isExecutableFile(atPath: base.path) ? base : nil
	}
	public static var claudeDesktopConfig: URL {
		home.appendingPathComponent("Library/Application Support/Claude/claude_desktop_config.json")
	}
	public static var antigravityConfig: URL {
		home.appendingPathComponent(".gemini/antigravity/mcp_config.json")
	}
	public static var codexConfig: URL {
		home.appendingPathComponent(".codex/config.toml")
	}
}

public struct InstallerPayload {
	public let payloadDir: URL
	public let pluginBundle: URL
	public let requirementsTxt: URL

	public static func resolve(bundle: Bundle = .main) throws -> InstallerPayload {
		let fm = FileManager.default
		let payloadDir: URL? = {
			// Prefer a direct path lookup to avoid any resource indexing weirdness for folder-based payloads.
			if let root = bundle.resourceURL {
				let direct = root.appendingPathComponent("Payload", isDirectory: true)
				if fm.fileExists(atPath: direct.path) { return direct }
			}
			return bundle.url(forResource: "Payload", withExtension: nil)
		}()
		guard let payloadDir else {
			throw InstallerError.userFacing("Installer payload is missing. Rebuild the app (Copy Payload build phase).")
		}
		let plugin = payloadDir.appendingPathComponent("Glyphs MCP.glyphsPlugin", isDirectory: true)
		let req = payloadDir.appendingPathComponent("requirements.txt")
		guard FileManager.default.fileExists(atPath: plugin.path) else {
			throw InstallerError.userFacing("Missing payload plugin bundle: \(plugin.path)")
		}
		guard FileManager.default.fileExists(atPath: req.path) else {
			throw InstallerError.userFacing("Missing payload requirements.txt: \(req.path)")
		}
		return InstallerPayload(payloadDir: payloadDir, pluginBundle: plugin, requirementsTxt: req)
	}
}
