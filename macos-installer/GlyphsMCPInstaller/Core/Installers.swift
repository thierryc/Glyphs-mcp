import AppKit
import Foundation

public let requiredRuntimeModules = [
	"mcp",
	"fastmcp",
	"pydantic_core",
	"starlette",
	"uvicorn",
	"httpx",
	"sse_starlette",
	"typing_extensions",
	"pkg_resources",
	"fontParts",
	"fontTools",
	"objc",
	"Foundation",
	"AppKit",
]

public enum InstallerProgressText {
	public static func detail(for line: String, limit: Int = 180) -> String? {
		let text = line.trimmingCharacters(in: .whitespacesAndNewlines)
		guard !text.isEmpty else { return nil }

		let detail: String?
		if text.hasPrefix("-- "), text.hasSuffix(" --"), text.count > 6 {
			detail = String(text.dropFirst(3).dropLast(3))
		} else if text.hasPrefix("Checking for missing or outdated Python dependencies") {
			detail = "Checking installed Python dependencies…"
		} else if text.hasPrefix("Collecting ") {
			detail = "Resolving " + text.dropFirst("Collecting ".count)
		} else if text.hasPrefix("Requirement already satisfied: ") {
			detail = "Already installed: " + text.dropFirst("Requirement already satisfied: ".count)
		} else if text.hasPrefix("Using cached ") || text.hasPrefix("Downloading ") || text.hasPrefix("Processing ") {
			detail = text
		} else if text.hasPrefix("Installing collected packages:") {
			detail = "Installing resolved Python packages…"
		} else if text.hasPrefix("Successfully installed")
			|| text.hasPrefix("Python dependencies are up to date")
			|| text.hasPrefix("Python dependencies are already up to date") {
			detail = "Python dependencies are ready."
		} else if text.hasPrefix("Verifying imports in:") {
			detail = "Verifying Python dependencies…"
		} else if text.hasPrefix("ERROR:") || text == "Still working…" {
			detail = text
		} else {
			detail = nil
		}

		guard let detail else { return nil }
		if detail.count <= limit { return detail }
		return String(detail.prefix(max(1, limit - 1))) + "…"
	}
}

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
	static let dependencyCommandTimeout: TimeInterval = 600

	let runner: ProcessRunner
	let log: (String) -> Void

	public init(runner: ProcessRunner, log: @escaping (String) -> Void) {
		self.runner = runner
		self.log = log
	}

	public func installAndVerify(
		python: PythonSelection,
		requirementsTxt: URL,
		glyphsVersion: GlyphsMajorVersion = .installerDefault
	) async throws {
		switch python {
		case .glyphs(let pip3, let python3):
			let target = InstallerPaths.glyphsScriptsSitePackages(glyphsVersion: glyphsVersion)
			try FileManager.default.createDirectory(at: target, withIntermediateDirectories: true, attributes: nil)
			log("Installing into: \(target.path)")
			if await canReuseInstalledDependencies(
				python: python3,
				requirementsTxt: requirementsTxt,
				extraSitePackages: target
			) {
				return
			}
			log("Checking for missing or outdated Python dependencies…")
			try await runner.runStreaming(
				executable: pip3,
				args: pipInstallArgs(requirementsTxt: requirementsTxt, target: target),
				environment: pipEnvironment(target: target),
				timeout: Self.dependencyCommandTimeout,
				onLine: log
			)
			log("Python dependencies are up to date.")
			try await verify(python: python3, extraSitePackages: target)
		case .custom(let python3):
			let ver = runner.runSync(executable: python3, args: ["-c", "import sys; print(sys.version.split()[0])"]).trimmingCharacters(in: .whitespacesAndNewlines)
			if !VersionGate.isSupported(version: ver) {
				throw InstallerError.userFacing("Selected Python \(ver) is not supported. Please use 3.11–3.14.")
			}
			if await canReuseInstalledDependencies(python: python3, requirementsTxt: requirementsTxt) {
				return
			}
			log("Checking for missing or outdated Python dependencies…")
			try await runner.runStreaming(
				executable: python3,
				args: ["-m", "pip"] + pipInstallArgs(requirementsTxt: requirementsTxt),
				timeout: Self.dependencyCommandTimeout,
				onLine: log
			)
			log("Python dependencies are up to date.")
			try await verify(python: python3)
		}
	}

	private func canReuseInstalledDependencies(
		python: URL,
		requirementsTxt: URL,
		extraSitePackages: URL? = nil
	) async -> Bool {
		guard requirementsAreSatisfied(
			python: python,
			requirementsTxt: requirementsTxt,
			extraSitePackages: extraSitePackages
		) else {
			return false
		}

		do {
			try await verify(python: python, extraSitePackages: extraSitePackages)
			log("Python dependencies are already up to date; skipped installation.")
			return true
		} catch {
			log("Installed Python dependencies need repair; reinstalling them.")
			return false
		}
	}

	func requirementsAreSatisfied(
		python: URL,
		requirementsTxt: URL,
		extraSitePackages: URL? = nil
	) -> Bool {
		let code = """
import importlib.metadata as metadata
import re
import site
import sys
extra_site=\(Self.pythonStringLiteral(extraSitePackages?.path ?? ""))
if extra_site:
  site.addsitedir(extra_site)
  if extra_site in sys.path:
    sys.path.remove(extra_site)
  sys.path.insert(0, extra_site)
requirements_path=\(Self.pythonStringLiteral(requirementsTxt.path))
mismatches=[]
try:
  with open(requirements_path, encoding='utf-8') as requirements_file:
    for raw_line in requirements_file:
      line=raw_line.partition('#')[0].strip()
      if not line:
        continue
      match=re.fullmatch(r'([A-Za-z0-9_.-]+)==([^\\s;]+)', line)
      if not match:
        mismatches.append((line, 'unsupported requirement'))
        continue
      name,wanted=match.groups()
      try:
        installed=metadata.version(name)
      except metadata.PackageNotFoundError:
        installed=None
      if installed != wanted:
        mismatches.append((name, installed, wanted))
except Exception as error:
  mismatches.append(('requirements', str(error)))
print('SATISFIED' if not mismatches else 'MISMATCH:'+repr(mismatches))
"""
		let result = runner.runSyncWithStderr(executable: python, args: ["-c", code])
		return result.exitCode == 0
			&& result.stdout.trimmingCharacters(in: .whitespacesAndNewlines) == "SATISFIED"
	}

	func pipInstallArgs(requirementsTxt: URL, target: URL? = nil) -> [String] {
		var args = [
			"install",
			"--upgrade",
			"--upgrade-strategy", "only-if-needed",
			"--disable-pip-version-check",
			"--no-input",
			"--progress-bar", "off",
			"--timeout", "30",
			"--retries", "2",
			"--no-compile",
			"--only-binary=:all:",
		]
		if let target {
			args += ["--target", target.path]
		} else {
			args.append("--user")
		}
		args += ["-r", requirementsTxt.path]
		return args
	}

	func pipEnvironment(target: URL) -> [String: String] {
		var environment = ProcessInfo.processInfo.environment
		if let existing = environment["PYTHONPATH"], !existing.isEmpty {
			environment["PYTHONPATH"] = target.path + ":" + existing
		} else {
			environment["PYTHONPATH"] = target.path
		}
		return environment
	}

	private func verify(python: URL, extraSitePackages: URL? = nil) async throws {
		log("Verifying imports in: \(python.path)")
		let code = """
import sys
import site
extra_site=\(Self.pythonStringLiteral(extraSitePackages?.path ?? ""))
if extra_site:
  site.addsitedir(extra_site)
  if extra_site in sys.path:
    sys.path.remove(extra_site)
  sys.path.insert(0, extra_site)
mods=\(Self.pythonListLiteral(requiredRuntimeModules))
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
			throw InstallerError.userFacing("Some packages failed to import. If objc, Foundation, or AppKit are listed, PyObjC did not install into the Python selected in Glyphs. See log for details.")
		}
	}

	private static func pythonListLiteral(_ values: [String]) -> String {
		let quoted = values.map { value in
			pythonStringLiteral(value)
		}
		return "[" + quoted.joined(separator: ",") + "]"
	}

	private static func pythonStringLiteral(_ value: String) -> String {
		"'\(value.replacingOccurrences(of: "\\", with: "\\\\").replacingOccurrences(of: "'", with: "\\'"))'"
	}
}

public struct PluginInstaller {
	let log: (String) -> Void
	let signer: PluginExecutableSigner

	public init(log: @escaping (String) -> Void, signer: PluginExecutableSigner = .live) {
		self.log = log
		self.signer = signer
	}

	public struct InstalledPluginInspection: Equatable {
		public enum Mode: Equatable {
			case notInstalled
			case bundle
			case symlink
		}

		public let bundleURL: URL
		public let mode: Mode
		public let version: PluginBundleVersion?
		public let symlinkTargetPath: String?

		public static func notInstalled(
			at bundleURL: URL = InstallerPaths.glyphsPluginsDir.appendingPathComponent("Glyphs MCP.glyphsPlugin", isDirectory: true)
		) -> InstalledPluginInspection {
			InstalledPluginInspection(bundleURL: bundleURL, mode: .notInstalled, version: nil, symlinkTargetPath: nil)
		}

		public var isSymlink: Bool { mode == .symlink }

		public var statusSummary: String {
			switch mode {
			case .notInstalled:
				return "Not installed"
			case .bundle:
				return version?.displayString ?? "Installed"
			case .symlink:
				if let version {
					return "Development symlink • \(version.displayString)"
				}
				return "Development symlink"
			}
		}
	}

	public struct Outcome: Equatable {
		public let didWrite: Bool
		public let didReplace: Bool
		public let previousVersion: PluginBundleVersion?
		public let installedVersion: PluginBundleVersion?
		public let destBundle: URL
	}

	public static func inspectInstalledPlugin(
		at bundleURL: URL = InstallerPaths.glyphsPluginsDir.appendingPathComponent("Glyphs MCP.glyphsPlugin", isDirectory: true)
	) -> InstalledPluginInspection {
		let fm = FileManager.default

		if let symlinkTarget = try? fm.destinationOfSymbolicLink(atPath: bundleURL.path) {
			let targetURL: URL
			if symlinkTarget.hasPrefix("/") {
				targetURL = URL(fileURLWithPath: symlinkTarget)
			} else {
				targetURL = bundleURL.deletingLastPathComponent().appendingPathComponent(symlinkTarget).standardizedFileURL
			}
			let version = PluginVersionReader.readPluginVersion(pluginBundle: targetURL)
				?? PluginVersionReader.readPluginVersion(pluginBundle: bundleURL)
			return InstalledPluginInspection(
				bundleURL: bundleURL,
				mode: .symlink,
				version: version,
				symlinkTargetPath: targetURL.path
			)
		}

		guard fm.fileExists(atPath: bundleURL.path) else {
			return .notInstalled(at: bundleURL)
		}

		return InstalledPluginInspection(
			bundleURL: bundleURL,
			mode: .bundle,
			version: PluginVersionReader.readPluginVersion(pluginBundle: bundleURL),
			symlinkTargetPath: nil
		)
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
		log("Ad-hoc signing plug-in executable.")
		try signer.sign(dest)
		let installed = PluginVersionReader.readPluginVersion(pluginBundle: dest)
		return Outcome(didWrite: true, didReplace: prev != nil, previousVersion: prev, installedVersion: installed, destBundle: dest)
	}
}

public struct PluginExecutableSigner {
	public let sign: (URL) throws -> Void

	public init(sign: @escaping (URL) throws -> Void) {
		self.sign = sign
	}

	public static let live = PluginExecutableSigner { bundleURL in
		let executable = bundleURL.appendingPathComponent("Contents/MacOS/plugin")
		guard FileManager.default.fileExists(atPath: executable.path) else {
			return
		}

		try runCodesign(arguments: ["--force", "--sign", "-", executable.path], executable: executable)
		try runCodesign(arguments: ["--verify", "--verbose=2", executable.path], executable: executable)
	}

	private static func runCodesign(arguments: [String], executable: URL) throws {
		let process = Process()
		process.executableURL = URL(fileURLWithPath: "/usr/bin/codesign")
		process.arguments = arguments

		let pipe = Pipe()
		process.standardOutput = pipe
		process.standardError = pipe

		do {
			try process.run()
			process.waitUntilExit()
		} catch {
			throw InstallerError.userFacing("Could not run codesign for \(executable.path): \(error.localizedDescription)")
		}

		guard process.terminationStatus == 0 else {
			let data = pipe.fileHandleForReading.readDataToEndOfFile()
			let details = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines)
			throw InstallerError.userFacing("Could not ad-hoc sign \(executable.path): \(details ?? "codesign exited with \(process.terminationStatus)")")
		}
	}
}
