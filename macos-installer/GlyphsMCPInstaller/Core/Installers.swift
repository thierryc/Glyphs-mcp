import AppKit
import Foundation

public enum PythonSelection {
	case glyphs(pip3: URL, python3: URL)
	case custom(python3: URL)

	public var pythonExecutable: URL {
		switch self {
		case .glyphs(_, let python3): return python3
		case .custom(let python3): return python3
		}
	}
}

extension PythonSelection: Sendable {}

public struct DepsInstaller {
	let runner: ProcessRunner
	let log: (String) -> Void

	public init(runner: ProcessRunner, log: @escaping (String) -> Void) {
		self.runner = runner
		self.log = log
	}

	public func installAndVerify(python: PythonSelection, requirementsTxt: URL) async throws {
		switch python {
		case .glyphs(let pip3, let python3):
			let target = InstallerPaths.glyphsBaseDir.appendingPathComponent("Scripts/site-packages", isDirectory: true)
			try FileManager.default.createDirectory(at: target, withIntermediateDirectories: true, attributes: nil)
			log("Installing into: \(target.path)")
			try await runner.runStreaming(executable: pip3, args: ["install", "--upgrade", "pip"], onLine: log)
			try await runner.runStreaming(executable: pip3, args: ["install", "--target", target.path, "-r", requirementsTxt.path], onLine: log)
			try await verify(python: python3)
		case .custom(let python3):
			let ver = runner.runSync(executable: python3, args: ["-c", "import sys; print(sys.version.split()[0])"]).trimmingCharacters(in: .whitespacesAndNewlines)
			if !VersionGate.isSupported(version: ver) {
				throw InstallerError.userFacing("Selected Python \(ver) is not supported. Please use 3.11–3.13.")
			}
			try await runner.runStreaming(executable: python3, args: ["-m", "pip", "install", "--upgrade", "pip"], onLine: log)
			try await runner.runStreaming(executable: python3, args: ["-m", "pip", "install", "--user", "-r", requirementsTxt.path], onLine: log)
			try await verify(python: python3)
		}
	}

	private func verify(python: URL) async throws {
		log("Verifying imports in: \(python.path)")
		let code = """
import sys
mods=['mcp','fastmcp','pydantic_core','starlette','uvicorn','httpx','sse_starlette','typing_extensions','fontParts','fontTools']
missing=[]
import importlib
for m in mods:
  try:
    importlib.import_module(m)
  except Exception as e:
    missing.append((m,str(e)))
try:
  import mcp.types as _t
  if not hasattr(_t, 'AnyFunction'):
    missing.append(('mcp.types.AnyFunction', 'missing (upgrade mcp)'))
except Exception as e:
  missing.append(('mcp.types', str(e)))
print('Python:', sys.executable)
print('Version:', sys.version.split()[0])
print('OK' if not missing else 'MISSING:'+str(missing))
"""
		let res = runner.runSyncWithStderr(executable: python, args: ["-c", code])
		log(res.stdout.trimmingCharacters(in: .whitespacesAndNewlines))
		if res.stdout.contains("MISSING:") {
			throw InstallerError.userFacing("Some packages failed to import. See log for details.")
		}
	}
}

public struct PluginInstaller {
	let log: (String) -> Void

	public init(log: @escaping (String) -> Void) {
		self.log = log
	}

	public struct Outcome: Equatable {
		public let didWrite: Bool
		public let didReplace: Bool
		public let previousVersion: PluginBundleVersion?
		public let installedVersion: PluginBundleVersion?
		public let destBundle: URL
	}

	public func installPluginBundle(from srcBundle: URL, toPluginsDir pluginsDir: URL, allowReplace: Bool) throws -> Outcome {
		try FileManager.default.createDirectory(at: pluginsDir, withIntermediateDirectories: true, attributes: nil)
		let dest = pluginsDir.appendingPathComponent(srcBundle.lastPathComponent, isDirectory: true)
		let prev = PluginVersionReader.readPluginVersion(pluginBundle: dest)
		if FileManager.default.fileExists(atPath: dest.path) {
			if !allowReplace {
				log("Keeping existing plugin at: \(dest.path)")
				return Outcome(didWrite: false, didReplace: false, previousVersion: prev, installedVersion: prev, destBundle: dest)
			}
			log("Replacing existing plugin: \(dest.path)")
			try FileManager.default.removeItem(at: dest)
		}
		log("Copying plugin to: \(dest.path)")
		try FileManager.default.copyItem(at: srcBundle, to: dest)
		let installed = PluginVersionReader.readPluginVersion(pluginBundle: dest)
		return Outcome(didWrite: true, didReplace: prev != nil, previousVersion: prev, installedVersion: installed, destBundle: dest)
	}
}
