import AppKit
import Foundation

public struct RuntimeProbeDocument: Decodable, Equatable, Sendable {
	public struct Runtime: Decodable, Equatable, Sendable {
		public let executable: String
		public let version: String
		public let implementation: String
		public let soabi: String
		public let extensionSuffix: String
		public let architecture: String
	}

	public struct NativeFile: Decodable, Equatable, Sendable {
		public let file: String
		public let abi: String
		public let abiCompatible: Bool
		public let architectures: [String]
		public let architectureCompatible: Bool
	}

	public struct Check: Decodable, Equatable, Sendable {
		public let module: String
		public let present: Bool
		public let imported: Bool
		public let origin: String?
		public let error: String?
		public let nativeFiles: [NativeFile]
	}

	public struct Issue: Decodable, Equatable, Sendable {
		public let code: String
		public let module: String
		public let file: String?
		public let expected: String?
		public let detected: String?
		public let message: String
		public let blocking: Bool
	}

	public let schemaVersion: Int
	public let mode: String
	public let status: String
	public let blocking: Bool
	public let runtime: Runtime
	public let sitePackages: String
	public let checks: [Check]
	public let issues: [Issue]
}

public struct RuntimeProbeExecutor {
	public enum Mode: String, Sendable {
		case preinstall
		case postinstall
	}

	public static let schemaVersion = 1
	public static let timeout: TimeInterval = 30

	let runner: ProcessRunner
	let log: (String) -> Void

	public init(runner: ProcessRunner, log: @escaping (String) -> Void) {
		self.runner = runner
		self.log = log
	}

	public func check(
		python: URL,
		probe: URL,
		sitePackages: URL,
		mode: Mode,
		allowUserSite: Bool = false
	) async throws -> RuntimeProbeDocument {
		var args = [
			probe.path,
			"--mode", mode.rawValue,
			"--site-packages", sitePackages.path,
		]
		if mode == .postinstall {
			args += [
				"--allow-origin", sitePackages.path,
				"--allow-runtime-paths",
			]
			if allowUserSite {
				args.append("--allow-user-site")
			}
		}

		log("Python environment check: \(python.path)")
		log("Prioritized site-packages: \(sitePackages.path)")
		let result = try await runner.runCapturing(
			executable: python,
			args: args,
			timeout: Self.timeout
		)
		let stderr = result.stderr.trimmingCharacters(in: .whitespacesAndNewlines)
		guard stderr.isEmpty else {
			throw InstallerError.userFacing(
				"Python environment check wrote unexpected error output: \(stderr)"
			)
		}

		let stdout = result.stdout.trimmingCharacters(in: .whitespacesAndNewlines)
		guard let data = stdout.data(using: .utf8) else {
			throw InstallerError.userFacing("Python environment check returned unreadable output.")
		}
		let document: RuntimeProbeDocument
		do {
			document = try JSONDecoder().decode(RuntimeProbeDocument.self, from: data)
		} catch {
			throw InstallerError.userFacing(
				"Python environment check returned malformed JSON: \(error.localizedDescription)"
			)
		}
		log("Python environment diagnostic JSON:\n\(stdout)")

		guard document.schemaVersion == Self.schemaVersion else {
			throw InstallerError.userFacing(
				"Python environment check returned unsupported schema \(document.schemaVersion)."
			)
		}
		guard document.mode == mode.rawValue else {
			throw InstallerError.userFacing("Python environment check returned the wrong mode.")
		}
		let validStatuses = Set(["ok", "incomplete", "incompatible", "error"])
		guard validStatuses.contains(document.status) else {
			throw InstallerError.userFacing("Python environment check returned an invalid overall status.")
		}
		guard document.blocking == ["incompatible", "error"].contains(document.status) else {
			throw InstallerError.userFacing("Python environment check returned an inconsistent status.")
		}
		guard mode != .postinstall || document.status != "incomplete" else {
			throw InstallerError.userFacing("Post-install Python environment check was incomplete.")
		}
		let expectedExitCodes: Set<Int32> = document.blocking ? [2] : [0]
		guard expectedExitCodes.contains(result.exitCode) else {
			throw InstallerError.userFacing(
				"Python environment check exited unexpectedly (status \(result.exitCode))."
			)
		}
		if document.blocking {
			throw InstallerError.userFacing(Self.failureMessage(document, mode: mode))
		}
		return document
	}

	public static func failureMessage(
		_ document: RuntimeProbeDocument,
		mode: Mode
	) -> String {
		let details = document.issues
			.filter(\.blocking)
			.map { issue in
				issue.file.map { "\(issue.message)\nFile: \($0)" } ?? issue.message
			}
			.joined(separator: "\n")
		let summary = details.isEmpty
			? "The Python environment could not be verified."
			: details
		let boundary = mode == .preinstall
			? "Installation stopped before changing dependencies or the plug-in."
			: "Post-install verification failed, so installation will not be reported as successful."
		return """
Glyphs uses Python \(document.runtime.version) at \(document.runtime.executable), but its ABI does not match one or more existing native packages, or the environment could not be verified.
\(summary)
\(boundary) See the Glyphs MCP troubleshooting guide.
"""
	}
}

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
		runtimeProbe: URL,
		glyphsVersion: GlyphsMajorVersion = .installerDefault
	) async throws {
		switch python {
		case .glyphs(let pip3, let python3):
			let target = InstallerPaths.glyphsScriptsSitePackages(glyphsVersion: glyphsVersion)
			try FileManager.default.createDirectory(at: target, withIntermediateDirectories: true, attributes: nil)
			log("Installing into: \(target.path)")
			if try await canReuseInstalledDependencies(
				python: python3,
				requirementsTxt: requirementsTxt,
				extraSitePackages: target,
				runtimeProbe: runtimeProbe
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
			try await verify(
				python: python3,
				runtimeProbe: runtimeProbe,
				extraSitePackages: target
			)
		case .custom(let python3):
			let ver = runner.runSync(executable: python3, args: ["-c", "import sys; print(sys.version.split()[0])"]).trimmingCharacters(in: .whitespacesAndNewlines)
			if !VersionGate.isSupported(version: ver) {
				throw InstallerError.userFacing("Selected Python \(ver) is not supported. Please use 3.11–3.14.")
			}
			let target = InstallerPaths.glyphsScriptsSitePackages(glyphsVersion: glyphsVersion)
			if try await canReuseInstalledDependencies(
				python: python3,
				requirementsTxt: requirementsTxt,
				extraSitePackages: target,
				runtimeProbe: runtimeProbe,
				allowUserSite: true
			) {
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
			try await verify(
				python: python3,
				runtimeProbe: runtimeProbe,
				extraSitePackages: target,
				allowUserSite: true
			)
		}
	}

	private func canReuseInstalledDependencies(
		python: URL,
		requirementsTxt: URL,
		extraSitePackages: URL,
		runtimeProbe: URL,
		allowUserSite: Bool = false
	) async throws -> Bool {
		guard requirementsAreSatisfied(
			python: python,
			requirementsTxt: requirementsTxt,
			extraSitePackages: extraSitePackages
		) else {
			return false
		}

		try await verify(
			python: python,
			runtimeProbe: runtimeProbe,
			extraSitePackages: extraSitePackages,
			allowUserSite: allowUserSite
		)
		log("Python dependencies are already up to date; skipped installation.")
		return true
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

	private func verify(
		python: URL,
		runtimeProbe: URL,
		extraSitePackages: URL,
		allowUserSite: Bool = false
	) async throws {
		log("Verifying imports in: \(python.path)")
		_ = try await RuntimeProbeExecutor(runner: runner, log: log).check(
			python: python,
			probe: runtimeProbe,
			sitePackages: extraSitePackages,
			mode: .postinstall,
			allowUserSite: allowUserSite
		)
	}

	private static func pythonStringLiteral(_ value: String) -> String {
		"'\(value.replacingOccurrences(of: "\\", with: "\\\\").replacingOccurrences(of: "'", with: "\\'"))'"
	}
}

public struct PluginInstaller {
	let log: (String) -> Void
	let verifier: PluginExecutableVerifier

	public init(log: @escaping (String) -> Void, verifier: PluginExecutableVerifier = .live) {
		self.log = log
		self.verifier = verifier
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
		let fm = FileManager.default
		try fm.createDirectory(at: pluginsDir, withIntermediateDirectories: true, attributes: nil)
		let dest = pluginsDir.appendingPathComponent(srcBundle.lastPathComponent, isDirectory: true)
		let prev = PluginVersionReader.readPluginVersion(pluginBundle: dest)
		let hadExisting = Self.pathExists(dest, fileManager: fm)
		if hadExisting {
			if !allowReplace {
				log("Keeping existing plugin at: \(dest.path)")
				return Outcome(didWrite: false, didReplace: false, previousVersion: prev, installedVersion: prev, destBundle: dest)
			}
		}

		log("Verifying trusted plug-in payload.")
		let sourceSignature = try verifier.verify(srcBundle)
		let nonce = UUID().uuidString
		let staged = pluginsDir.appendingPathComponent(".\(srcBundle.lastPathComponent).installing-\(nonce)", isDirectory: true)
		let backup = pluginsDir.appendingPathComponent(".\(srcBundle.lastPathComponent).backup-\(nonce)", isDirectory: true)
		var movedExistingToBackup = false
		var installedNewBundle = false

		do {
			log("Staging plug-in at: \(staged.path)")
			try fm.copyItem(at: srcBundle, to: staged)
			let stagedSignature = try verifier.verify(staged)
			guard stagedSignature == sourceSignature else {
				throw InstallerError.userFacing("The staged plug-in signature changed during copy.")
			}

			if hadExisting {
				log("Backing up existing plug-in before replacement.")
				try fm.moveItem(at: dest, to: backup)
				movedExistingToBackup = true
			}

			log("Installing verified plug-in at: \(dest.path)")
			try fm.moveItem(at: staged, to: dest)
			installedNewBundle = true

			let installedSignature = try verifier.verify(dest)
			guard installedSignature == sourceSignature else {
				throw InstallerError.userFacing("The installed plug-in signature does not match the trusted payload.")
			}

			if movedExistingToBackup {
				try fm.removeItem(at: backup)
			}
			let installed = PluginVersionReader.readPluginVersion(pluginBundle: dest)
			return Outcome(didWrite: true, didReplace: hadExisting, previousVersion: prev, installedVersion: installed, destBundle: dest)
		} catch {
			if installedNewBundle, Self.pathExists(dest, fileManager: fm) {
				try? fm.removeItem(at: dest)
			}
			if Self.pathExists(staged, fileManager: fm) {
				try? fm.removeItem(at: staged)
			}
			if movedExistingToBackup, Self.pathExists(backup, fileManager: fm) {
				do {
					try fm.moveItem(at: backup, to: dest)
				} catch {
					throw InstallerError.userFacing(
						"Plug-in installation failed and the previous plug-in could not be restored: \(error.localizedDescription)"
					)
				}
			}
			throw error
		}
	}

	private static func pathExists(_ url: URL, fileManager: FileManager) -> Bool {
		fileManager.fileExists(atPath: url.path)
			|| (try? fileManager.destinationOfSymbolicLink(atPath: url.path)) != nil
	}
}

public struct PluginExecutableSignature: Equatable {
	public let cdHash: String
	public let teamIdentifier: String
	public let authority: String
	public let hardenedRuntime: Bool
	public let timestamped: Bool

	public init(
		cdHash: String,
		teamIdentifier: String,
		authority: String,
		hardenedRuntime: Bool,
		timestamped: Bool
	) {
		self.cdHash = cdHash
		self.teamIdentifier = teamIdentifier
		self.authority = authority
		self.hardenedRuntime = hardenedRuntime
		self.timestamped = timestamped
	}
}

public struct PluginExecutableVerifier {
	public static let expectedTeamIdentifier = "N9U29A4T8J"
	public static let expectedDeveloperIDAuthority = "Developer ID Application: Thierry Charbonnel (N9U29A4T8J)"
	public let verify: (URL) throws -> PluginExecutableSignature

	public init(verify: @escaping (URL) throws -> PluginExecutableSignature) {
		self.verify = verify
	}

	public static let live = PluginExecutableVerifier { bundleURL in
		let executable = bundleURL.appendingPathComponent("Contents/MacOS/plugin")
		guard FileManager.default.fileExists(atPath: executable.path) else {
			throw InstallerError.userFacing("Trusted plug-in executable is missing: \(executable.path)")
		}

		_ = try runCodesign(arguments: ["--verify", "--deep", "--strict", "--verbose=2", bundleURL.path], executable: executable)
		let details = try runCodesign(arguments: ["-d", "--verbose=4", executable.path], executable: executable)
		let fields = parseDetails(details)
		guard let cdHash = fields["CDHash"], !cdHash.isEmpty else {
			throw InstallerError.userFacing("Trusted plug-in signature has no CDHash.")
		}
		guard fields["TeamIdentifier"] == expectedTeamIdentifier else {
			throw InstallerError.userFacing("Trusted plug-in is not signed by the expected developer team.")
		}
		let authority = details
			.split(separator: "\n")
			.map(String.init)
			.first(where: { $0.hasPrefix("Authority=") })?
			.dropFirst("Authority=".count)
			.description ?? ""
		guard authority.hasPrefix("Developer ID Application:") || authority.hasPrefix("Apple Development:") else {
			throw InstallerError.userFacing("Trusted plug-in has an unexpected signing authority.")
		}
		let runtime = details.range(of: #"flags=.*\(runtime\)"#, options: .regularExpression) != nil
		guard runtime else {
			throw InstallerError.userFacing("Trusted plug-in signature is missing the hardened runtime.")
		}
		let timestamped = details
			.split(separator: "\n")
			.contains(where: { $0.hasPrefix("Timestamp=") })
		guard timestamped else {
			throw InstallerError.userFacing("Trusted plug-in signature is missing a secure timestamp.")
		}
		if authority.hasPrefix("Developer ID Application:") {
			_ = try runCommand(
				executablePath: "/usr/bin/xcrun",
				arguments: ["stapler", "validate", bundleURL.path],
				subject: bundleURL
			)
			let ticket = bundleURL.appendingPathComponent("Contents/CodeResources")
			guard FileManager.default.fileExists(atPath: ticket.path) else {
				throw InstallerError.userFacing("Trusted plug-in is missing its stapled notarization ticket.")
			}
		}
		return PluginExecutableSignature(
			cdHash: cdHash,
			teamIdentifier: expectedTeamIdentifier,
			authority: authority,
			hardenedRuntime: runtime,
			timestamped: timestamped
		)
	}

	private static func parseDetails(_ details: String) -> [String: String] {
		var fields: [String: String] = [:]
		for line in details.split(separator: "\n") {
			let parts = line.split(separator: "=", maxSplits: 1).map(String.init)
			if parts.count == 2, fields[parts[0]] == nil {
				fields[parts[0]] = parts[1]
			}
		}
		return fields
	}

	private static func runCodesign(arguments: [String], executable: URL) throws -> String {
		try runCommand(
			executablePath: "/usr/bin/codesign",
			arguments: arguments,
			subject: executable
		)
	}

	private static func runCommand(
		executablePath: String,
		arguments: [String],
		subject: URL
	) throws -> String {
		let process = Process()
		process.executableURL = URL(fileURLWithPath: executablePath)
		process.arguments = arguments

		let pipe = Pipe()
		process.standardOutput = pipe
		process.standardError = pipe

		do {
			try process.run()
			let data = pipe.fileHandleForReading.readDataToEndOfFile()
			process.waitUntilExit()
			let output = String(data: data, encoding: .utf8) ?? ""
			guard process.terminationStatus == 0 else {
				let details = output.trimmingCharacters(in: .whitespacesAndNewlines)
				let tool = URL(fileURLWithPath: executablePath).lastPathComponent
				let message = details.isEmpty ? "\(tool) exited with \(process.terminationStatus)" : details
				throw InstallerError.userFacing("Plug-in security verification failed for \(subject.path): \(message)")
			}
			return output
		} catch {
			if let installerError = error as? InstallerError {
				throw installerError
			}
			let tool = URL(fileURLWithPath: executablePath).lastPathComponent
			throw InstallerError.userFacing("Could not run \(tool) for \(subject.path): \(error.localizedDescription)")
		}
	}
}
